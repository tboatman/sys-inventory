"""Parse active DEVSUPxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/devsup_snapshot.yml) into DevsupStatement
records -- device support definitions, named by IEASYSxx's own DEVSUP=
keyword (see ieasys_parser.py) the same way SSN=/CMD=/PROD=/OMVS=/
MSTRJCL= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active DEVSUPxx member,
e.g.:

    ##MEMBER DEVSUPBN
    RTYPTABL=DTRT00,LOWAD=YES,
    IZBGENQ=NO,ITASKID=NO,

Statement syntax: like IEASYSxx (ieasys_parser.py), a DEVSUPxx member has
no per-line "STMT keyword=val,..." grouping -- it's one comma-separated
sequence of KEYWORD=value pairs for the whole member, a trailing comma
continuing onto the next line. First of the Category B active-PARMLIB-
member domains from doc/TODO.md "9.2" -- this is the same flat,
comma-continued shape IEASYSxx has, so this module just calls
parmlib_engines.flat_keyword_engine() directly instead of hand-writing a
third copy of that logic (see doc/TODO.md "9.1").

NOT YET VALIDATED against a real DEVSUPxx member -- built from IBM's
documented DEVSUPxx keyword syntax only, same caveat bpxprm_parser.py
carries for its own unconfirmed parsing surface.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import DevsupStatement
from .parmlib_engines import flat_keyword_engine


def parse_member(name: str, raw_lines: list[str]) -> list[DevsupStatement]:
    params = flat_keyword_engine(raw_lines)
    return [
        DevsupStatement(keyword=keyword, value=value, source_member=name)
        for keyword, value in params.items()
    ]


def parse_devsup_snapshot(path: Path) -> list[DevsupStatement]:
    """Parse one devsup_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active DEVSUPxx member's raw content) into DevsupStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[DevsupStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
