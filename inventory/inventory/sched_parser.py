"""Parse active SCHEDxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/sched_snapshot.yml) into SchedStatement
records -- PPT (Program Properties Table) entries, named by IEASYSxx's
own SCH= keyword (see ieasys_parser.py) the same way SSN=/CMD=/PROD=/
OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR= name IEFSSNxx/COMMNDxx/
IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active SCHEDxx
member, e.g.:

    ##MEMBER SCHEDBN
    PPT PGMNAME(IEDQTCAM) NOSWAP KEY(1) SYST
    PPT PGMNAME(ZWESIS01) KEY(4) NOSWAP
    PPT PGMNAME(XGMMAIN) CANCEL KEY(4) NOSYST PRIV NOSWAP DSI PASS
        AFF(NONE) NOPREF

Statement syntax: a real SCHEDxx member is a repeated single statement
shape -- 'PPT PGMNAME(name) flag flag KEY(n) ...', one entry per program,
possibly wrapping onto a continuation line with no continuation
character (same "known keyword vocabulary, fold everything else into
the current statement" idea BPXPRMxx/AUTORxx already use), so this
module just calls parmlib_engines.statement_engine() with a one-keyword
vocabulary ({"PPT"}) instead of hand-modeling every PPT flag
individually (NOSWAP/PRIV/SYST/NOSYST/CANCEL/DSI/PASS/KEY(n)/AFF(...)/
NOPREF/...) -- the same generic-capture rationale CicsSitOverride/
Jes2InitStatement use for their own large keyword surfaces.

The PPT statement shape is confirmed against real-world PPT examples
(IBM's z/OS MVS Initialization and Tuning Reference, SCHEDxx chapter).

CONFIRMED against a real SCHEDxx member, including a run of PPT entries
where every physical line -- statement line and every continuation line
alike -- carries its own trailing '/* ... */' comment, stripped cleanly
without bleeding into the next PPT entry.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import SchedStatement
from .parmlib_engines import statement_engine

_SCHED_STATEMENT_KEYWORDS = {
    "PPT",
}


def parse_member(name: str, raw_lines: list[str]) -> list[SchedStatement]:
    return [
        SchedStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _SCHED_STATEMENT_KEYWORDS)
    ]


def parse_sched_snapshot(path: Path) -> list[SchedStatement]:
    """Parse one sched_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active SCHEDxx member's raw content) into SchedStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[SchedStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
