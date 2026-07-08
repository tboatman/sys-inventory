"""Shared parsing engines for the active-PARMLIB-member-family domains
(IEASYSxx/BPXPRMxx today, and the further keyword=value/statement-oriented
PARMLIB members sketched in doc/TODO.md's "9.1") -- factored out once two
domains (ieasys_parser.py, bpxprm_parser.py) had each proven their own
shape, rather than speculatively up front.

jes2parm_parser.py's own continuation-joiner is JES2-specific enough
(per-line STMT grouping with its own comma-trailing continuation rule)
that it stays there, but its paren-depth-tracking comma splitter is the
same algorithm ieasys_parser.py needs, so it's shared here instead of
being copy-pasted a third time.
"""
from __future__ import annotations

import re

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_comments(text: str) -> str:
    """Strip '/* ... */' comments (the standard MVS PARMLIB convention),
    including ones spanning multiple physical lines."""
    return _COMMENT.sub(" ", text)


_SEQUENCE_NUMBER = re.compile(r"^(.{0,72}?)\s*\d{8}\s*$")


def strip_sequence_numbers(raw_lines: list[str]) -> list[str]:
    """Strip a traditional MVS PARMLIB sequence number (columns 73-80,
    data in columns 1-71/72) from each physical line, if present.

    Unlike a '/* ... */' comment, a sequence number sits on the *same*
    physical line as real statement content, so strip_comments() alone
    won't remove it -- left alone, it would get folded into a
    statement's own operand/param text as a bogus trailing 8-digit
    token. First needed by diag_parser.py (a real DIAGxx member), then
    confirmed to recur in an IEASVCxx member sample too -- promoted here
    once a second domain needed the identical logic (doc/TODO.md "9.2")."""
    stripped = []
    for line in raw_lines:
        if len(line) > 72:
            match = _SEQUENCE_NUMBER.match(line)
            if match:
                line = match.group(1)
        stripped.append(line)
    return stripped


_BARE_PAREN = re.compile(r"^([A-Za-z0-9$#@_]+)(\(.*\))$")


def split_params(text: str) -> dict[str, str]:
    """Split a comma-separated KEYWORD=value (or bare KEYWORD) sequence,
    tracking paren depth so a value's own internal commas (e.g.
    REAL=(4096,ONLINE)) aren't mistaken for parameter separators.

    A keyword can also take a parenthesized value with no '=' at all
    (e.g. DEVSUPxx's own `DISABLE(SSR)`, confirmed against a real
    DEVSUPxx member) -- distinguished from a genuinely bare keyword like
    IEASYSxx's `CLPA` by trailing '(...)' with nothing after it."""
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
        if sep:
            params[key.strip().upper()] = value.strip()
            continue
        bare_paren = _BARE_PAREN.match(part)
        if bare_paren:
            params[bare_paren.group(1).upper()] = bare_paren.group(2)
        else:
            params[part.upper()] = ""
    return params


def flat_keyword_engine(raw_lines: list[str]) -> dict[str, str | None]:
    """IEASYSxx's own shape: one comma-separated, continuation-joined
    KEYWORD=value sequence for the whole member (no per-line statement
    grouping) -- see ieasys_parser.py."""
    text = strip_comments("\n".join(raw_lines))
    joined = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return {keyword: (value or None) for keyword, value in split_params(joined).items()}


_STMT_START = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(.*)$")


def statement_engine(raw_lines: list[str], keywords: set[str]) -> list[tuple[str, str]]:
    """BPXPRMxx's own shape: 'STMT KEYWORD(value)...' blocks, continuing
    onto further physical lines with no continuation character until the
    next recognized top-level statement keyword starts -- see
    bpxprm_parser.py. `keywords` is the member type's own top-level
    statement vocabulary (matched case-insensitively, always returned
    upper-cased); an unrecognized keyword is folded into the preceding
    statement's operands instead of starting its own -- the same
    documented limitation tcpip_parser.py's PROFILE.TCPIP statement
    handling carries."""
    text = strip_comments("\n".join(raw_lines))
    statements: list[tuple[str, str]] = []

    for line in text.splitlines():
        content = " ".join(line.split())
        if not content:
            continue
        match = _STMT_START.match(content)
        stmt = match.group(1) if match else content
        rest = match.group(2) if match else ""
        if stmt.upper() in keywords:
            statements.append((stmt.upper(), rest.strip()))
        elif statements:
            stmt_name, operands = statements[-1]
            statements[-1] = (stmt_name, f"{operands} {content}".strip())
    return statements
