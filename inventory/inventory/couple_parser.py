"""Parse active COUPLExx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/couple_snapshot.yml) into
CoupleStatement records -- XCF/sysplex couple dataset definitions,
named by IEASYSxx's own COUPLE= keyword (see ieasys_parser.py) the same
way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH= name
IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/
AUTORxx/SCHEDxx.

Note the real member name keeps the trailing E (COUPLExx, e.g.
COUPLE00), unlike MSTRJCL= (which drops its R to name MSTJCLxx).

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active COUPLExx
member, e.g.:

    ##MEMBER COUPLE00
    COUPLE SYSPLEX(PLEX1)
           PCOUPLE(SYS1.XCF.CDS01,VOL001)
           ACOUPLE(SYS1.XCF.CDS02,VOL002)
    DATA TYPE(LOGR)
         PCOUPLE(SYS1.LOGR.CDS01,VOL001)
         ACOUPLE(SYS1.LOGR.CDS02,VOL002)

Statement syntax: a real COUPLExx member has two top-level statement
keywords -- COUPLE (the sysplex couple dataset pair) and DATA TYPE(...)
(one per function couple dataset pair, e.g. LOGR/SFM/ARM/...) -- each
continuing onto further physical lines with no continuation character,
the same shape BPXPRMxx/AUTORxx/SCHEDxx already have, so this module
just calls parmlib_engines.statement_engine() with COUPLExx's own
top-level keyword vocabulary (COUPLE, DATA) instead of hand-modeling
every sub-parameter (SYSPLEX(...)/PCOUPLE(...)/ACOUPLE(...)/TYPE(...)/
CFRMPOL(...)/INTERVAL(...)/...) individually.

The COUPLE/DATA statement vocabulary is confirmed against IBM's z/OS MVS
Setting Up a Sysplex reference.

NOT YET VALIDATED against a real COUPLExx member -- the statement
vocabulary is confirmed, but the parser itself hasn't been checked
against a real member, same caveat autor_parser.py/sched_parser.py carry
for their own unconfirmed parsing surfaces.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import CoupleStatement
from .parmlib_engines import statement_engine

_COUPLE_STATEMENT_KEYWORDS = {
    "COUPLE",
    "DATA",
}


def parse_member(name: str, raw_lines: list[str]) -> list[CoupleStatement]:
    return [
        CoupleStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _COUPLE_STATEMENT_KEYWORDS)
    ]


def parse_couple_snapshot(path: Path) -> list[CoupleStatement]:
    """Parse one couple_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active COUPLExx member's raw content) into CoupleStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[CoupleStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
