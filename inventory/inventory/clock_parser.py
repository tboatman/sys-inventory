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
    OPERATOR NOPROMPT
    TIMEZONE W.05.00.00
    ETRMODE  NO
    ETRZONE  NO
    ETRDELTA 1
    STPMODE  NO

Statement syntax: CONFIRMED against a real CLOCKxx member -- unlike
IEASYSxx/DEVSUPxx/IEAOPTxx, CLOCKxx is one bare "KEYWORD value" pair per
physical line, with no `=`, no comma, and no continuation character (see
doc/TODO.md "9.2" Category G). Its own small line-oriented parser below,
not parmlib_engines.flat_keyword_engine(), which assumes the wrong,
comma-continued shape.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import ClockStatement
from .parmlib_engines import strip_comments


def parse_member(name: str, raw_lines: list[str]) -> list[ClockStatement]:
    text = strip_comments("\n".join(raw_lines))
    statements: list[ClockStatement] = []
    for line in text.splitlines():
        parts = line.split(None, 1)
        if not parts:
            continue
        keyword = parts[0].upper()
        value = parts[1].strip() if len(parts) > 1 else None
        statements.append(ClockStatement(keyword=keyword, value=value, source_member=name))
    return statements


def parse_clock_snapshot(path: Path) -> list[ClockStatement]:
    """Parse one clock_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active CLOCKxx member's raw content) into ClockStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[ClockStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
