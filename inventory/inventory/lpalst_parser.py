"""Parse active LPALSTxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/lpalst_snapshot.yml) into LpalstEntry
records -- the Link Pack Area (LPA) dataset concatenation, named by
IEASYSxx's own LPA= keyword (see ieasys_parser.py) the same way SSN=/
CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/
GRSRNL=/SMF=/IOS=/CON=/SMS=/IZU=/DIAG=/CATALOG=/GRSCNF=/PROG=/SVC=
name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/
CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx/
IGDSMSxx/IZUPRMxx/DIAGxx/IGGCATxx/GRSCNFxx/PROGxx/IEASVCxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active LPALSTxx member.

Statement syntax: the first Category E (positional/list format) shape
from doc/TODO.md "9.2" -- one dataset name per physical line,
comma-terminated (except the last entry), optionally followed
immediately by a parenthesized volser hint, e.g.:

    SYS1.LPALIB,
    SYS1.SGRBLPA,
    ISM403.SEQALPA(C3PRD1),
    ISM403.SFEKLPA(C3PRD1)

CONFIRMED against a real LPALSTxx member, which also exercised
unresolved system symbols embedded in several DSNs (e.g.
`USER.&SYSVER..LPALIB`) -- left as literal text, not resolved (this
module doesn't have access to the system's active symbol table).
"""
from __future__ import annotations

import re
from pathlib import Path

from .jcl_parser import split_members
from .models import LpalstEntry
from .parmlib_engines import strip_comments

_ENTRY = re.compile(r"^([^(),\s]+)(?:\(([^)]+)\))?,?$")


def parse_member(name: str, raw_lines: list[str]) -> list[LpalstEntry]:
    entries = []
    text = strip_comments("\n".join(raw_lines))
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _ENTRY.match(stripped)
        if not match:
            continue
        dsn, volume = match.groups()
        entries.append(LpalstEntry(dsn=dsn, volume=volume, source_member=name))
    return entries


def parse_lpalst_snapshot(path: Path) -> list[LpalstEntry]:
    """Parse one lpalst_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active LPALSTxx member's raw content) into LpalstEntry
    rows."""
    text = path.read_text(errors="replace")
    entries: list[LpalstEntry] = []
    for name, raw_lines in split_members(text).items():
        entries.extend(parse_member(name, raw_lines))
    return entries
