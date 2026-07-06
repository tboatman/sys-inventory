"""Parse active CLOCKxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/clock_snapshot.yml) into ClockStatement
records -- TOD clock/timezone parameters, named by IEASYSxx's own
CLOCK= keyword (see ieasys_parser.py) the same way SSN=/CMD=/PROD=/
OMVS=/MSTRJCL=/DEVSUP=/OPT= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/
MSTJCLxx/DEVSUPxx/IEAOPTxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active CLOCKxx member,
e.g.:

    ##MEMBER CLOCKBN
    ETRMODE=YES,ETRZONE=00,
    TIMEZONE=W05.00.00

Statement syntax: like IEASYSxx/DEVSUPxx/IEAOPTxx, a CLOCKxx member has
no per-line "STMT keyword=val,..." grouping -- it's one comma-separated
sequence of KEYWORD=value pairs for the whole member, a trailing comma
continuing onto the next line. Third of the Category B active-PARMLIB-
member domains from doc/TODO.md "9.2" -- this is the same flat,
comma-continued shape IEASYSxx/DEVSUPxx/IEAOPTxx have, so this module
just calls parmlib_engines.flat_keyword_engine() directly instead of
hand-writing another copy of that logic (see doc/TODO.md "9.1").

NOT YET VALIDATED against a real CLOCKxx member -- built from IBM's
documented CLOCKxx keyword syntax only, same caveat devsup_parser.py/
opt_parser.py carry for their own unconfirmed parsing surfaces.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import ClockStatement
from .parmlib_engines import flat_keyword_engine


def parse_member(name: str, raw_lines: list[str]) -> list[ClockStatement]:
    params = flat_keyword_engine(raw_lines)
    return [
        ClockStatement(keyword=keyword, value=value, source_member=name)
        for keyword, value in params.items()
    ]


def parse_clock_snapshot(path: Path) -> list[ClockStatement]:
    """Parse one clock_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active CLOCKxx member's raw content) into ClockStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[ClockStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
