"""Parse active IEAOPTxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/opt_snapshot.yml) into OptStatement
records -- system tuning/options parameters, named by IEASYSxx's own
OPT= keyword (see ieasys_parser.py) the same way SSN=/CMD=/PROD=/OMVS=/
MSTRJCL=/DEVSUP= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/
DEVSUPxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active IEAOPTxx
member, e.g.:

    ##MEMBER IEAOPTBN
    MCCFXEPR=YES,MCCAFCTH=90,
    CNTRYCD=1

Statement syntax: like IEASYSxx/DEVSUPxx, an IEAOPTxx member has no
per-line "STMT keyword=val,..." grouping -- it's one comma-separated
sequence of KEYWORD=value pairs for the whole member, a trailing comma
continuing onto the next line. Second of the Category B active-PARMLIB-
member domains from doc/TODO.md "9.2" -- this is the same flat,
comma-continued shape IEASYSxx/DEVSUPxx have, so this module just calls
parmlib_engines.flat_keyword_engine() directly instead of hand-writing
another copy of that logic (see doc/TODO.md "9.1").

NOT YET VALIDATED against a real IEAOPTxx member -- built from IBM's
documented IEAOPTxx keyword syntax only, same caveat devsup_parser.py
carries for its own unconfirmed parsing surface.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import OptStatement
from .parmlib_engines import flat_keyword_engine


def parse_member(name: str, raw_lines: list[str]) -> list[OptStatement]:
    params = flat_keyword_engine(raw_lines)
    return [
        OptStatement(keyword=keyword, value=value, source_member=name)
        for keyword, value in params.items()
    ]


def parse_opt_snapshot(path: Path) -> list[OptStatement]:
    """Parse one opt_snapshot.txt dump (one or more ##MEMBER blocks, each
    an active IEAOPTxx member's raw content) into OptStatement rows."""
    text = path.read_text(errors="replace")
    statements: list[OptStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
