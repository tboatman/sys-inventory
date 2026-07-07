"""Parse active IZUPRMxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/izuprm_snapshot.yml) into IzuprmStatement
records -- z/OSMF (z/OS Management Facility) configuration, named by
IEASYSxx's own IZU= keyword (see ieasys_parser.py) the same way SSN=/CMD=/
PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/SMF=/
IOS=/CON=/SMS= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/
DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/
IECIOSxx/CONSOLxx/IGDSMSxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active IZUPRMxx member.

Statement syntax: a real IZUPRM00 member is statement-oriented, one
keyword per (possibly multi-line) statement -- rule 4 in the member's own
header comment says blanks (not just commas) delimit statements, and rule
9b documents a quoted value spanning multiple physical lines (closing
quote resumes in column 1 of the next line), the same "fold any
non-keyword-leading line into the current statement" shape
parmlib_engines.statement_engine() already handles for BPXPRMxx/AUTORxx/
etc. -- no design change needed, just IZUPRMxx's own top-level keyword
vocabulary.

Statement vocabulary CONFIRMED against a real IZUPRM00 member: HOSTNAME,
HTTP_SSL_PORT, INCIDENT_LOG, JAVA_HOME, KEYRING_NAME, LOGGING,
RESTAPI_FILE, COMMON_TSO, SAF_PREFIX, CLOUD_SAF_PREFIX, CLOUD_SEC_ADMIN,
SEC_GROUPS, SESSION_EXPIRE, TEMP_DIR, CSRF_SWITCH, SERVER_PROC,
ANGEL_PROC, AUTOSTART, AUTOSTART_GROUP, USER_DIR, UNAUTH_USER,
WLM_CLASSES, PLUGINS. CSRF_SWITCH appeared twice in the real member
(ON, then OFF) -- both occurrences are kept in order, not collapsed to
the last one, same as COUPLExx's repeated DATA statements. Two
AUTOSTART_GROUP lines in the real member were fully commented out
(each its own /* ... */ line) and correctly disappear entirely once
comments are stripped, rather than producing bogus statements.

IZUPRMxx's full documented keyword surface is likely larger than this
(this vocabulary reflects one shop's real member content, not IBM's
complete reference) -- an unrecognized top-level keyword still gets
folded into the preceding statement's operands instead of starting its
own, the same documented limitation every other statement_engine()
consumer here carries; broaden _IZUPRM_STATEMENT_KEYWORDS if a future
real member exercises one not yet in this set.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import IzuprmStatement
from .parmlib_engines import statement_engine

_IZUPRM_STATEMENT_KEYWORDS = {
    "HOSTNAME",
    "HTTP_SSL_PORT",
    "INCIDENT_LOG",
    "JAVA_HOME",
    "KEYRING_NAME",
    "LOGGING",
    "RESTAPI_FILE",
    "COMMON_TSO",
    "SAF_PREFIX",
    "CLOUD_SAF_PREFIX",
    "CLOUD_SEC_ADMIN",
    "SEC_GROUPS",
    "SESSION_EXPIRE",
    "TEMP_DIR",
    "CSRF_SWITCH",
    "SERVER_PROC",
    "ANGEL_PROC",
    "AUTOSTART",
    "AUTOSTART_GROUP",
    "USER_DIR",
    "UNAUTH_USER",
    "WLM_CLASSES",
    "PLUGINS",
}


def parse_member(name: str, raw_lines: list[str]) -> list[IzuprmStatement]:
    return [
        IzuprmStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _IZUPRM_STATEMENT_KEYWORDS)
    ]


def parse_izuprm_snapshot(path: Path) -> list[IzuprmStatement]:
    """Parse one izuprm_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active IZUPRMxx member's raw content) into IzuprmStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[IzuprmStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
