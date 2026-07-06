"""Parse active CONSOLxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/consol_snapshot.yml) into
ConsolStatement records -- MCS/EMCS console definitions, named by
IEASYSxx's own CON= keyword (see ieasys_parser.py) the same way
SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/
COUPLE=/GRSRNL=/SMF=/IOS= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/
MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/
SMFPRMxx/IECIOSxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active CONSOLxx
member, e.g.:

    ##MEMBER CONSOL00
    INIT     CMDDELIM(")
             MLIM(1500)
    DEFAULT ROUTCODE(ALL)
    CONSOLE
      DEVNUM(SMCS)
      AUTH(ALL)
      NAME(SMCS01)
    HARDCOPY
      DEVNUM(SYSLOG,OPERLOG)
      ROUTCODE(ALL)

Statement syntax: a real CONSOLxx member is statement-oriented -- INIT/
DEFAULT/CONSOLE/HARDCOPY statements, continuing onto further physical
lines with no continuation character until the next recognized
top-level statement keyword starts, the same shape BPXPRMxx/AUTORxx/
COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx already have, so this module just
calls parmlib_engines.statement_engine() with CONSOLxx's own top-level
keyword vocabulary instead of hand-writing another copy of that logic.

CONFIRMED against a real CONSOLxx member: multiple CONSOLE statements
(one per device, e.g. seven in the confirming member), a CONSOLE
statement with its first keyword(s) sharing the CONSOLE line itself
rather than starting on a continuation line, and an INIT statement
whose CMDDELIM(") value is itself a literal quote character inside the
parens -- all handled correctly by statement_engine() without any
special-casing.

PARTIAL statement vocabulary: only INIT, DEFAULT, CONSOLE, and HARDCOPY
were exercised by the confirming member -- CONSOLxx's full documented
statement surface may still be larger (e.g. ALTGRP, CNGRP, MSCOPE,
SPECIAL). An unrecognized top-level keyword gets folded into the
preceding statement's operands instead of starting its own, the same
documented limitation every other statement_engine() consumer here
carries -- broaden _CONSOL_STATEMENT_KEYWORDS if a future real member
exercises one not yet in this set.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import ConsolStatement
from .parmlib_engines import statement_engine

_CONSOL_STATEMENT_KEYWORDS = {
    "INIT",
    "DEFAULT",
    "CONSOLE",
    "HARDCOPY",
}


def parse_member(name: str, raw_lines: list[str]) -> list[ConsolStatement]:
    return [
        ConsolStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _CONSOL_STATEMENT_KEYWORDS)
    ]


def parse_consol_snapshot(path: Path) -> list[ConsolStatement]:
    """Parse one consol_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active CONSOLxx member's raw content) into ConsolStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[ConsolStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
