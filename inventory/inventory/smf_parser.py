"""Parse active SMFPRMxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/smf_snapshot.yml) into SmfStatement
records -- System Management Facilities (SMF) recording configuration,
named by IEASYSxx's own SMF= keyword (see ieasys_parser.py) the same
way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/
COUPLE=/GRSRNL= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/
DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx.

Note the real member name is SMFPRMxx, not "SMFxx" as an earlier draft
of doc/TODO.md's plan had it -- corrected after checking a real IBM
source, the same class of naming error COUPLE=/COUPLExx had.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active SMFPRMxx
member, e.g.:

    ##MEMBER SMFPRM00
    ACTIVE
    DSNAME(SYS1.MAN1,SYS1.MAN2)
    NOPROMPT
    SYS(NOTYPE(14:19,62:69,99))
    SUBSYS(STC,NOTYPE(17))

Statement syntax: a real SMFPRMxx member is statement-oriented, one
keyword per (possibly multi-line) statement, the same shape BPXPRMxx/
AUTORxx/COUPLExx already have, so this module just calls
parmlib_engines.statement_engine() with SMFPRMxx's own top-level
keyword vocabulary instead of hand-writing another copy of that logic.

Statement vocabulary CONFIRMED against a real SMFPRMxx member: ACTIVE,
DSNAME, PROMPT, NOPROMPT, SYS, SUBSYS, plus REC, MAXDORM, STATUS, JWT,
SID, LISTDSN, INTVAL, SYNCVAL, AUTHSETSMF added after the real member
exercised them (previously folded into the preceding statement's
operands since they weren't yet in the vocabulary -- see doc/TODO.md
"9.2"). SMFPRMxx's full documented keyword surface may still be larger
than this list; an unrecognized top-level keyword still gets folded
into the preceding statement instead of starting its own, the same
documented limitation every other statement_engine() consumer here
carries -- broaden _SMF_STATEMENT_KEYWORDS further if a future real
member exercises one not yet in this set.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import SmfStatement
from .parmlib_engines import statement_engine

_SMF_STATEMENT_KEYWORDS = {
    "ACTIVE",
    "DSNAME",
    "PROMPT",
    "NOPROMPT",
    "SYS",
    "SUBSYS",
    "REC",
    "MAXDORM",
    "STATUS",
    "JWT",
    "SID",
    "LISTDSN",
    "INTVAL",
    "SYNCVAL",
    "AUTHSETSMF",
}


def parse_member(name: str, raw_lines: list[str]) -> list[SmfStatement]:
    return [
        SmfStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _SMF_STATEMENT_KEYWORDS)
    ]


def parse_smf_snapshot(path: Path) -> list[SmfStatement]:
    """Parse one smf_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active SMFPRMxx member's raw content) into SmfStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[SmfStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
