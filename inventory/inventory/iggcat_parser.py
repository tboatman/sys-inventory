"""Parse active IGGCATxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/iggcat_snapshot.yml) into IggcatStatement
records -- catalog system parameters, named by IEASYSxx's own CATALOG=
keyword (see ieasys_parser.py) the same way SSN=/CMD=/PROD=/.../DIAG=
name IEFSSNxx/COMMNDxx/IFAPRDxx/.../DIAGxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active IGGCATxx member,
e.g.:

    ##MEMBER IGGCAT00
    GDGEXTENDED(NO)
    VVDSSPACE(10,10)
    NOTIFYEXTENT(80)
    TASKMAX(180)

Statement syntax: CONFIRMED against a real IGGCAT00 member -- one
independent `KEYWORD(value)` (or bare `KEYWORD`) entry per physical
line, with no `=`, no commas joining entries, and no continuation
character. This is neither of the two existing shared engines in
parmlib_engines.py: flat_keyword_engine() assumes entries are
comma-separated on one continued logical line (IEASYSxx/DEVSUPxx), which
would misparse this real member (there's no comma between entries at
all, so the whole member would be swallowed as one bogus bare-paren
match); statement_engine() assumes a per-domain top-level statement
vocabulary grouping further sub-parameters (AUTORxx/SCHEDxx/...), which
IGGCATxx doesn't have either -- every entry stands alone. Closest
existing precedent is CLOCKxx's own small dedicated parser (Category G),
just tokenizing `KEYWORD(value)` pairs instead of splitting `KEYWORD
value` on whitespace. The tokenizer below scans the whole (comment
stripped) member text for `KEYWORD` or `KEYWORD(value)` tokens directly,
tolerant of one-per-line or several-per-line layouts alike, rather than
hand-listing IGGCATxx's full documented keyword set.
"""
from __future__ import annotations

import re
from pathlib import Path

from .jcl_parser import split_members
from .models import IggcatStatement
from .parmlib_engines import strip_comments

_TOKEN = re.compile(r"([A-Za-z0-9$#@_]+)(\([^()]*\))?")


def parse_member(name: str, raw_lines: list[str]) -> list[IggcatStatement]:
    text = strip_comments("\n".join(raw_lines))
    statements: list[IggcatStatement] = []
    for match in _TOKEN.finditer(text):
        keyword = match.group(1).upper()
        paren = match.group(2)
        value = paren[1:-1].strip() if paren else None
        statements.append(IggcatStatement(keyword=keyword, value=value, source_member=name))
    return statements


def parse_iggcat_snapshot(path: Path) -> list[IggcatStatement]:
    """Parse one iggcat_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active IGGCATxx member's raw content) into IggcatStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[IggcatStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
