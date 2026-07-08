"""Parse active PROGxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/prog_snapshot.yml) into ProgStatement
records -- dynamic APF/LNKLST/LPA/EXIT/SCHED definitions, named by
IEASYSxx's own PROG= keyword (see ieasys_parser.py) the same way SSN=/
CMD=/PROD=/.../GRSCNF= name IEFSSNxx/COMMNDxx/IFAPRDxx/.../GRSCNFxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active PROGxx member,
e.g.:

    ##MEMBER PROG00
    APF FORMAT(DYNAMIC)
    APF ADD
        DSNAME(SYS1.LINKLIB)                             VOLUME(******)
    LNKLST DEFINE NAME(LNKLSTBN)
    LNKLST ADD NAME(LNKLSTBN) DSN(SYS1.LINKLIB)
    LNKLST ACTIVATE NAME(LNKLSTBN)

Statement syntax: CONFIRMED against a real PROGxx member -- despite this
domain being flagged in doc/TODO.md as "the richest and riskiest" of the
active-PARMLIB-member family (APF/LNKLST/LPA/EXIT/SCHED are all distinct
sub-statement families in a real PROGxx member), the real top-level
statement shape turned out to be a single first-word keyword per
statement (`APF ADD`/`APF FORMAT(DYNAMIC)`/`LNKLST DEFINE`/`LNKLST ADD`/
`LNKLST ACTIVATE`), with the action verb and every sub-parameter folded
into generic operand text -- exactly the same shape every other
Category C domain here already has, so this module just calls
parmlib_engines.statement_engine() with PROGxx's own top-level keyword
vocabulary instead of hand-modeling each statement family. Every `APF
ADD`/`LNKLST ADD` entry restarts with its own literal `APF`/`LNKLST`
keyword (whether written on one physical line or continued onto further
lines with no continuation character), so each becomes its own row.

`EXIT`/`LPA`/`SCHED` are included in the vocabulary on the strength of
IBM's documented PROGxx statement syntax; only `APF`/`LNKLST` were
actually exercised by the real confirming member.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import ProgStatement
from .parmlib_engines import statement_engine

_PROG_STATEMENT_KEYWORDS = {
    "APF",
    "EXIT",
    "LNKLST",
    "LPA",
    "SCHED",
}


def parse_member(name: str, raw_lines: list[str]) -> list[ProgStatement]:
    return [
        ProgStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _PROG_STATEMENT_KEYWORDS)
    ]


def parse_prog_snapshot(path: Path) -> list[ProgStatement]:
    """Parse one prog_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active PROGxx member's raw content) into ProgStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[ProgStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
