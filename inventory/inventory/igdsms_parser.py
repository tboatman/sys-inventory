"""Parse active IGDSMSxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/igdsms_snapshot.yml) into
IgdsmsStatement records -- SMS (Storage Management Subsystem) base
configuration, named by IEASYSxx's own SMS= keyword (see
ieasys_parser.py) the same way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/
OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/SMF=/IOS=/CON= name
IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/
AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx.

NAMING, deliberately distinct from sms_parser.py/SmsStorageGroup: this
project already has an unrelated `sms` tag/`SmsStorageGroup` table for
the *live* `D SMS,STORGRP` console command -- a completely different
dimension (live storage-group status vs. this member's static base
configuration). This module, its model (IgdsmsStatement), its store
table (igdsms_statements), and its CLI command (`inventory igdsms`) all
use the `igdsms` name instead of `sms` throughout, exactly to keep the
two apart (doc/TODO.md "9.2").

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active IGDSMSxx
member, e.g.:

    ##MEMBER IGDSMSTB
    SMS ACDS(SYS1.ZDT3.ACDS)
        COMMDS(SYS1.ZDT3.COMMDS)
        INTERVAL(15)
        SIZE(128K)

Statement syntax: a real IGDSMSxx member is a single repeated SMS
statement, continuing onto further physical lines with no continuation
character -- the same shape BPXPRMxx/AUTORxx/COUPLExx/GRSRNLxx/
SMFPRMxx/IECIOSxx/CONSOLxx already have, so this module just calls
parmlib_engines.statement_engine() with a one-keyword vocabulary
({"SMS"}) instead of hand-modeling every sub-parameter (ACDS(...)/
COMMDS(...)/INTERVAL(...)/DINTERVAL(...)/REVERIFY(...)/
ACSDEFAULTS(...)/OAMPROC(...)/TRACE(...)/SIZE(...)/TYPE(...)/
JOBNAME(...)/ASID(...)/SELECT(...)/...) individually.

CONFIRMED against a real IGDSMSxx member.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import IgdsmsStatement
from .parmlib_engines import statement_engine

_IGDSMS_STATEMENT_KEYWORDS = {
    "SMS",
}


def parse_member(name: str, raw_lines: list[str]) -> list[IgdsmsStatement]:
    return [
        IgdsmsStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _IGDSMS_STATEMENT_KEYWORDS)
    ]


def parse_igdsms_snapshot(path: Path) -> list[IgdsmsStatement]:
    """Parse one igdsms_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active IGDSMSxx member's raw content) into IgdsmsStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[IgdsmsStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
