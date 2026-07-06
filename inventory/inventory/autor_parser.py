"""Parse active AUTORxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/autor_snapshot.yml) into AutorStatement
records -- WTOR auto-reply policy, named by IEASYSxx's own AUTOR=
keyword (see ieasys_parser.py) the same way SSN=/CMD=/PROD=/OMVS=/
MSTRJCL=/DEVSUP=/OPT=/CLOCK= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/
MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active AUTORxx
member, e.g.:

    ##MEMBER AUTORBN
    NOTIFYMSGS(CONSOLE)
    MSGID(ARC0380A)
       DELAY(60S)
       REPLY(CANCEL)
    MSGID(IEE094D)
       NOAUTORREPLY

Statement syntax: unlike IEASYSxx/DEVSUPxx/IEAOPTxx/CLOCKxx's flat
KEYWORD=value shape, a real AUTORxx member is statement-oriented --
NOTIFYMSGS(HC|CONSOLE) and MSGID(msgid) DELAY(nnS) REPLY(text)/
NOAUTORREPLY statements, continuing onto further physical lines with no
continuation character until the next recognized top-level statement
keyword starts -- the same shape BPXPRMxx already has (see
bpxprm_parser.py), so this module just calls
parmlib_engines.statement_engine() with AUTORxx's own top-level keyword
vocabulary (NOTIFYMSGS, MSGID) instead of hand-writing another copy of
that logic (see doc/TODO.md "9.1").

The NOTIFYMSGS/MSGID statement vocabulary is confirmed against IBM's
z/OS MVS Initialization and Tuning Reference -- this is NOT Automatic
Restart Management policy, despite the superficial name resemblance (an
earlier draft of doc/TODO.md's plan mislabeled it before being
corrected).

NOT YET VALIDATED against a real AUTORxx member -- the statement
vocabulary is confirmed, but the parser itself hasn't been checked
against a real member, same caveat bpxprm_parser.py carries for its own
unconfirmed parsing surface.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import AutorStatement
from .parmlib_engines import statement_engine

_AUTOR_STATEMENT_KEYWORDS = {
    "NOTIFYMSGS",
    "MSGID",
}


def parse_member(name: str, raw_lines: list[str]) -> list[AutorStatement]:
    return [
        AutorStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _AUTOR_STATEMENT_KEYWORDS)
    ]


def parse_autor_snapshot(path: Path) -> list[AutorStatement]:
    """Parse one autor_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active AUTORxx member's raw content) into AutorStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[AutorStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
