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
REAL=(4096,ONLINE)). So this reuses parmlib_engines.split_params() (the
same paren-depth-tracking comma-split jes2parm_parser.py uses) but runs
it once across the whole member's continuation-joined text instead of
per statement line, since there's no per-line statement name to split on
first. A bare keyword with no '=' (e.g. CLPA above) is captured with an
empty value, same convention jes2parm_parser.py's bare-flag handling
(e.g. START) already uses.

The underlying KEYWORD=value/comma-continuation shape is CONFIRMED
against a real IEASYSxx sample -- see discover_active_members.yml's own
header comment, which already does this same extraction in Jinja, just
narrowed to three hand-picked keywords (SSN=/CMD=/PROD=/MSTRJCL=) and
never saved. This module generalizes that confirmed shape to every
keyword in the member using parmlib_engines.flat_keyword_engine(), the
same shape doc/TODO.md's "9.1" identified as reusable across Category B
of the further active-PARMLIB-member domains. One deliberate improvement
over the Jinja version: its regex requires a trailing comma after each
KEYWORD=value to match at all, so a member's very last keyword (no comma
following it) would be silently dropped; flat_keyword_engine() has no
such requirement (it flushes whatever's left over even with no trailing
comma).
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import IeasysStatement
from .parmlib_engines import flat_keyword_engine


def parse_member(name: str, raw_lines: list[str]) -> list[IeasysStatement]:
    params = flat_keyword_engine(raw_lines)
    return [
        IeasysStatement(keyword=keyword, value=value, source_member=name)
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
