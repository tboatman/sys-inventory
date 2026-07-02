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
list, e.g. JOBNUM=(999,999,1) above -- _split_params tracks paren depth
so those inner commas aren't mistaken for parameter separators). A
trailing comma continues the statement onto the next line, the same
"continuation" idea jcl_parser.join_continuations() handles for JCL, but
JES2 statements have no leading '//' to strip, so that helper doesn't
apply as-is and this module has its own continuation-joiner below.
Comment lines (leading '/*') and blank lines are skipped.

NOT YET VALIDATED against a real JES2 init deck -- this module's
continuation-joining and comma-splitting are built from JES2's documented
statement syntax (stable across releases), not confirmed against an
actual member from this site. Confirm before relying on it, same caveat
racf_parser.py carries for its own unconfirmed byte offsets.
"""
from __future__ import annotations

import re
from pathlib import Path

from .jcl_parser import split_members
from .models import Jes2InitStatement

_STMT = re.compile(r"^([A-Z0-9$#@]+)(?:\(([^)]*)\))?\s+(.+)$")


def _join_continuations(lines: list[str]) -> list[str]:
    joined: list[str] = []
    buf = ""
    continuing = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("/*"):
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
        part = part.strip().rstrip(",")
        if not part:
            continue
        key, sep, value = part.partition("=")
        params[key.strip().upper()] = value.strip() if sep else ""
    return params


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
                params=_split_params(rest),
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
