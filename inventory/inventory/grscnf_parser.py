"""Parse active GRSCNFxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/grscnf_snapshot.yml) into
GrscnfStatement records -- Global Resource Serialization configuration
parameters, named by IEASYSxx's own GRSCNF= keyword (see
ieasys_parser.py) the same way SSN=/CMD=/PROD=/.../CATALOG= name
IEFSSNxx/COMMNDxx/IFAPRDxx/.../IGGCATxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active GRSCNFxx
member, e.g.:

    ##MEMBER GRSCNF00
    GRSDEF
            GRSQ(LOCAL)
         /* GRSQ(CONTENTION)   - use in GRS STAR  */
         /* RESMIL(5)   */

Statement syntax: CONFIRMED against a real GRSCNFxx member -- a single
repeated 'GRSDEF' statement whose sub-parameters (GRSQ/RESMIL/TOLINT/
ACCELSYS/RESTART/REJOIN/CTRACE/...) continue onto further physical
lines with no continuation character, same shape GRSRNLxx's own RNLDEF
statement has (see grsrnl_parser.py) -- so this module just calls
parmlib_engines.statement_engine() with a one-keyword vocabulary
({"GRSDEF"}) instead of hand-modeling each sub-parameter individually.
The real confirming member had every sub-parameter except GRSQ commented
out as a full-line `/* ... */` (documenting the site's own defaulted or
removed settings) -- handled with no code change by
parmlib_engines.strip_comments(), leaving just `GRSDEF GRSQ(LOCAL)`.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import GrscnfStatement
from .parmlib_engines import statement_engine

_GRSCNF_STATEMENT_KEYWORDS = {
    "GRSDEF",
}


def parse_member(name: str, raw_lines: list[str]) -> list[GrscnfStatement]:
    return [
        GrscnfStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _GRSCNF_STATEMENT_KEYWORDS)
    ]


def parse_grscnf_snapshot(path: Path) -> list[GrscnfStatement]:
    """Parse one grscnf_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active GRSCNFxx member's raw content) into GrscnfStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[GrscnfStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
