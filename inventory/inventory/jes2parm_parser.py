"""Parse JES2 initialization-statement PARMLIB dumps (see
ansible/roles/zos_extract/tasks/jes2parm.yml) into Jes2InitStatement
records.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), but each member's raw text is JES2's
own initialization-statement syntax, not JCL:

    ##MEMBER JES2PARM
    MASDEF   OWNMASN=1,NAME=NJE1
    JOBCLASS(1) JOBPRTY=16,COMMAND=NO
    JOBDEF   JOBNUM=(999,999,1),RESTART=YES
    OUTCLASS(A) QUEUE=YES,BURST=YES

Statement syntax: STMT, optionally followed immediately by a parenthesized
subscript (e.g. JOBCLASS(1)), then whitespace, then comma-separated
KEY=VALUE pairs (a value can itself be a parenthesized, comma-containing
list, e.g. JOBNUM=(999,999,1) above -- split_params (parmlib_engines.py) tracks paren depth
so those inner commas aren't mistaken for parameter separators). A
trailing comma continues the statement onto the next line, the same
"continuation" idea jcl_parser.join_continuations() handles for JCL, but
JES2 statements have no leading '//' to strip, so that helper doesn't
apply as-is and this module has its own continuation-joiner below.

CONFIRMED against a real JES2 init deck on 2026-07-02 (a site copy of
IBM's own HASPPARM-derived template, comments and all -- a common,
legitimate way shops build their real init deck, not just documentation
noise). Two real shapes the original guess didn't account for:

1. Comments are NOT only whole standalone lines -- per the real member's
   own header ("Comments and Blanks may appear anywhere before, after,
   or in-between statements, parameters, and delimiters... Comments must
   be bounded by the slash-asterisk, asterisk-slash type delimiters"),
   '/* ... */' appears trailing on the same line as real content
   (commonly right after a parameter's trailing comma, e.g.
   'BERTNUM=6500,      /* Number of BERTs   oc*/'), and can even span
   multiple physical lines (a decorative section-divider box comment, or
   a '/*' opened on one line with the column-layout caption text closed
   by '*/' several lines later). The original "skip a line if its
   stripped text starts with '/*'" check missed both: a trailing same-
   line comment left comment text glued onto real params (corrupting
   split_params with a garbage key), and a multi-line comment's
   non-'/*'-prefixed continuation line got fed to the statement parser
   as if it were real content. Fixed by stripping every '/* ... */' span
   (DOTALL, so a multi-line span is stripped as a whole) from the raw
   member text up front, before any line-based processing -- see
   strip_comments (parmlib_engines.py).
2. A statement can legitimately have a subscript and *no* live
   parameters at all if every real parameter on it happens to be
   documented-but-commented-out in this particular member (e.g.
   'FSS(PRINTOFF)' and 'LOADMOD(JESEXIT5)' in the real member, both with
   only comment lines as their would-be parameters) -- contrary to the
   header's own stated rule that "Statements must have at least one
   parameter coded on the same line," which apparently isn't strictly
   enforced by JES2 itself. The original _STMT regex required at least
   one non-blank character after the statement/subscript and silently
   dropped these; the trailing params group is now optional so they
   parse to an empty params dict instead of vanishing.
"""
from __future__ import annotations

import re
from pathlib import Path

from .jcl_parser import split_members
from .models import Jes2InitStatement
from .parmlib_engines import split_params, strip_comments

_STMT = re.compile(r"^([A-Z0-9$#@]+)(?:\(([^)]*)\))?(?:\s+(.+))?$")


def _join_continuations(lines: list[str]) -> list[str]:
    text = strip_comments("\n".join(lines))
    joined: list[str] = []
    buf = ""
    continuing = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        buf = f"{buf} {stripped}" if continuing else stripped
        if buf.endswith(","):
            continuing = True
            continue
        continuing = False
        joined.append(buf)
        buf = ""
    if buf:
        joined.append(buf)
    return joined


def parse_member(name: str, raw_lines: list[str]) -> list[Jes2InitStatement]:
    statements = []
    for line in _join_continuations(raw_lines):
        match = _STMT.match(line)
        if not match:
            continue
        stmt, subscript, rest = match.groups()
        statements.append(
            Jes2InitStatement(
                stmt=stmt.upper(),
                subscript=subscript,
                params=split_params(rest or ""),
                source_member=name,
            )
        )
    return statements


def parse_dump(path: Path) -> list[Jes2InitStatement]:
    text = path.read_text(errors="replace")
    statements: list[Jes2InitStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
