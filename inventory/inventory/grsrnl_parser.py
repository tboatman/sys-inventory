"""Parse active GRSRNLxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/grsrnl_snapshot.yml) into
GrsrnlStatement records -- global resource serialization resource name
lists, named by IEASYSxx's own GRSRNL= keyword (see ieasys_parser.py)
the same way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/
SCH=/COUPLE= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/
DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active GRSRNLxx
member, e.g.:

    ##MEMBER GRSRNL00
    RNLDEF RNL(EXCL) TYPE(SPECIFIC) QNAME(SYSIGGV2) RNAME('ICFCAT.CAT1.SHARED')
    RNLDEF RNL(INCL) TYPE(GENERIC) QNAME(SYSDSN)

Statement syntax: a real GRSRNLxx member is a repeated single statement
shape -- 'RNLDEF RNL(EXCL|INCL|CON) TYPE(GENERIC|SPECIFIC|PATTERN)
QNAME(...) RNAME(...)', one entry per resource, possibly wrapping onto a
continuation line with no continuation character (same "known keyword
vocabulary, fold everything else into the current statement" idea
SchedStatement/CoupleStatement already use), so this module just calls
parmlib_engines.statement_engine() with a one-keyword vocabulary
({"RNLDEF"}) instead of hand-modeling RNL/TYPE/QNAME/RNAME individually.

The RNLDEF statement shape is confirmed against IBM's documented GRS
resource name list syntax (RNL/TYPE/QNAME/RNAME).

NOT YET VALIDATED against a real GRSRNLxx member -- the statement shape
is confirmed, but the parser itself hasn't been checked against a real
member, same caveat couple_parser.py carries for its own unconfirmed
parsing surface.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import GrsrnlStatement
from .parmlib_engines import statement_engine

_GRSRNL_STATEMENT_KEYWORDS = {
    "RNLDEF",
}


def parse_member(name: str, raw_lines: list[str]) -> list[GrsrnlStatement]:
    return [
        GrsrnlStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _GRSRNL_STATEMENT_KEYWORDS)
    ]


def parse_grsrnl_snapshot(path: Path) -> list[GrsrnlStatement]:
    """Parse one grsrnl_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active GRSRNLxx member's raw content) into GrsrnlStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[GrsrnlStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
