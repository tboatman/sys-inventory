"""Parse active IEAFIXxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/fix_snapshot.yml) into FixStatement
records -- IBM fix/PTF-supplied Link Pack Area module additions, named
by IEASYSxx's own FIX= keyword (see ieasys_parser.py) the same way
MLPA= names IEALPAxx (see mlpa_parser.py's module docstring for the
full IEASYSxx keyword chain).

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active IEAFIXxx member.

Statement syntax: the identical `INCLUDE LIBRARY(dsn) MODULES(...)`
syntax IEALPAxx has (see mlpa_parser.py) -- CONFIRMED against a real
IEAFIXxx member, whose own formatting puts `MODULES(` on the *same*
physical line as `INCLUDE LIBRARY(...)`:

    INCLUDE LIBRARY(SYS1.LPALIB) MODULES(
                 IEAVAR00
                 IEAVAR06
                 IGC0001G
                 )

Since parmlib_engines.statement_engine() only recognizes a *leading*
keyword at the start of a line, both `LIBRARY(...)` and `MODULES(`
fold into the one `INCLUDE` statement's operands here (unlike IEALPAxx's
confirming member, which put `MODULES(...)` on its own following line
and so produced two separate top-level statements) -- both shapes are
handled correctly with zero code differences, since operands are
captured as raw generic text either way.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import FixStatement
from .parmlib_engines import statement_engine

_FIX_STATEMENT_KEYWORDS = {
    "INCLUDE",
    "MODULES",
}


def parse_member(name: str, raw_lines: list[str]) -> list[FixStatement]:
    return [
        FixStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _FIX_STATEMENT_KEYWORDS)
    ]


def parse_fix_snapshot(path: Path) -> list[FixStatement]:
    """Parse one fix_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active IEAFIXxx member's raw content) into FixStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[FixStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
