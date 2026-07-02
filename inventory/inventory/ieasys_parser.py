"""Parse active IEASYSxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/ieasys_snapshot.yml) into IeasysStatement
records -- the real "actual parms" (system parameters active at IPL),
as opposed to parmlib_parser.py's ParmlibDataset (just the PARMLIB
dataset search order, all 'D PARMLIB' itself can report).

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active IEASYSxx member
(there can be more than one concatenated -- see
discover_active_parmlib_suffixes.yml), e.g.:

    ##MEMBER IEASYSBN
    SSN=(BN),CMD=(BN),PROD=(BN),
    REAL=(4096,ONLINE),CLPA,

Statement syntax: unlike JES2's own init deck (jes2parm_parser.py), an
IEASYSxx member has no per-line "STMT keyword=val,..." grouping -- it's
one comma-separated sequence of KEYWORD=value pairs for the whole
member, a trailing comma continuing onto the next line, and a value can
itself be a parenthesized, comma-containing list (e.g. SSN=(BN) or
REAL=(4096,ONLINE)). So this reuses jes2parm_parser.py's proven
paren-depth-tracking comma-split (_split_params) but runs it once across
the whole member's continuation-joined text instead of per statement
line, since there's no per-line statement name to split on first. A
bare keyword with no '=' (e.g. CLPA above) is captured with an empty
value, same convention jes2parm_parser.py's bare-flag handling (e.g.
START) already uses.

The underlying KEYWORD=value/comma-continuation shape is CONFIRMED
against a real IEASYSxx sample -- see discover_active_members.yml's own
header comment, which already does this same extraction in Jinja, just
narrowed to three hand-picked keywords (SSN=/CMD=/PROD=/MSTRJCL=) and
never saved. This module generalizes that confirmed shape to every
keyword in the member. One deliberate improvement over that Jinja
version: its regex requires a trailing comma after each KEYWORD=value to
match at all, so a member's very last keyword (no comma following it)
would be silently dropped; _split_params here has no such requirement
(it flushes whatever's left over even with no trailing comma).
"""
from __future__ import annotations

import re
from pathlib import Path

from .jcl_parser import split_members
from .models import IeasysStatement

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(text: str) -> str:
    return _COMMENT.sub(" ", text)


def _split_params(text: str) -> dict[str, str]:
    parts: list[str] = []
    current = ""
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current:
        parts.append(current)

    params: dict[str, str] = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition("=")
        params[key.strip().upper()] = value.strip() if sep else ""
    return params


def parse_member(name: str, raw_lines: list[str]) -> list[IeasysStatement]:
    text = _strip_comments("\n".join(raw_lines))
    joined = " ".join(line.strip() for line in text.splitlines() if line.strip())
    params = _split_params(joined)
    return [
        IeasysStatement(keyword=keyword, value=value or None, source_member=name)
        for keyword, value in params.items()
    ]


def parse_ieasys_snapshot(path: Path) -> list[IeasysStatement]:
    """Parse one ieasys_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active IEASYSxx member's raw content) into IeasysStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[IeasysStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
