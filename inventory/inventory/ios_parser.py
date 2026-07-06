"""Parse active IECIOSxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/ios_snapshot.yml) into IosStatement
records -- I/O related parameters, named by IEASYSxx's own IOS=
keyword (see ieasys_parser.py) the same way SSN=/CMD=/PROD=/OMVS=/
MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/SMF= name
IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/
AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active IECIOSxx
member, e.g.:

    ##MEMBER IECIOS00
    MIH TIME=00:15:00,DEV=(0100-01FF)
    HOTIO DEV=(0100-01FF),TIME=1000
    ZHPF YES

Statement syntax: a real IECIOSxx member's own documentation states
"each record must start with MIH, HOTIO, TERMINAL, FICON, STORAGE,
CAPTUCB, EKM, or RECOVERY followed by one or more blanks, or must be a
valid CTRACE, MIDAW, HYPERPAV, HYPERWRITE, or ZHPF specification" -- the
same "known top-level keyword vocabulary" shape BPXPRMxx/AUTORxx/
COUPLExx/SMFPRMxx already have, so this module just calls
parmlib_engines.statement_engine() with that full confirmed keyword set
instead of hand-writing another copy of that logic.

The statement vocabulary (MIH, HOTIO, TERMINAL, FICON, STORAGE,
CAPTUCB, EKM, RECOVERY, CTRACE, MIDAW, HYPERPAV, HYPERWRITE, ZHPF) is
confirmed against IBM's z/OS MVS Initialization and Tuning Reference.

NOT YET VALIDATED against a real IECIOSxx member -- the statement
vocabulary is confirmed, but the parser itself hasn't been checked
against a real member, same caveat smf_parser.py carries.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import IosStatement
from .parmlib_engines import statement_engine

_IOS_STATEMENT_KEYWORDS = {
    "MIH",
    "HOTIO",
    "TERMINAL",
    "FICON",
    "STORAGE",
    "CAPTUCB",
    "EKM",
    "RECOVERY",
    "CTRACE",
    "MIDAW",
    "HYPERPAV",
    "HYPERWRITE",
    "ZHPF",
}


def parse_member(name: str, raw_lines: list[str]) -> list[IosStatement]:
    return [
        IosStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _IOS_STATEMENT_KEYWORDS)
    ]


def parse_ios_snapshot(path: Path) -> list[IosStatement]:
    """Parse one ios_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active IECIOSxx member's raw content) into IosStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[IosStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
