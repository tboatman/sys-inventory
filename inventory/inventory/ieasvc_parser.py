"""Parse active IEASVCxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/ieasvc_snapshot.yml) into IeasvcStatement
records -- user SVC (Supervisor Call) routine additions/replacements,
named by IEASYSxx's own SVC= keyword (see ieasys_parser.py) the same way
SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/
GRSRNL=/SMF=/IOS=/CON=/SMS=/IZU=/DIAG=/CATALOG=/GRSCNF=/PROG= name
IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/
AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx/IGDSMSxx/
IZUPRMxx/DIAGxx/IGGCATxx/GRSCNFxx/PROGxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active IEASVCxx member.

Statement syntax: the Category D shape from doc/TODO.md "9.2" --
`SVCPARM nnn,KEYWORD(value),...`, comma-continued across physical lines
the same way JES2's own init deck is (jes2parm_parser.py's
_join_continuations, reused here as-is since the continuation rule is
identical). Unlike JES2's `STMT(subscript) key=val,...` shape, IEASVCxx's
positional value right after the statement name is a *bare* SVC number
(e.g. `254`), not a parenthesized subscript like JES2's own
`JOBCLASS(1)` -- so this module has its own small statement regex rather
than reusing jes2parm_parser.py's _STMT, which would otherwise swallow
the leading number as a bogus bare keyword via split_params().

CONFIRMED syntax via a real IEASVCxx member's own documented example
(commented out in the member, still confirming the real syntax):

    /* SVCPARM 254,REPLACE,TYPE(1),APF(NO)                   IMS    SVC  */ 00010003

Two wrinkles this confirms:
1. A traditional MVS PARMLIB sequence number (columns 73-80) trails the
   line, same as DIAGxx's confirmed member -- parmlib_engines.
   strip_sequence_numbers() handles it here too.
2. The example itself is a `/* ... */` comment (an IBM-documented sample
   line, not a live definition) -- strip_comments() (invoked inside
   jes2parm_parser._join_continuations()) removes it entirely, so it
   correctly produces zero live IeasvcStatement rows on its own; a real
   site's *uncommented* SVCPARM statements would follow the identical
   syntax once actually present in a member.
"""
from __future__ import annotations

import re
from pathlib import Path

from .jcl_parser import split_members
from .jes2parm_parser import _join_continuations
from .models import IeasvcStatement
from .parmlib_engines import split_params, strip_sequence_numbers

_STMT = re.compile(r"^([A-Z0-9$#@]+)\s+(\d+)\s*,?\s*(.*)$")


def parse_member(name: str, raw_lines: list[str]) -> list[IeasvcStatement]:
    statements = []
    for line in _join_continuations(strip_sequence_numbers(raw_lines)):
        match = _STMT.match(line)
        if not match:
            continue
        stmt, svc_number, rest = match.groups()
        statements.append(
            IeasvcStatement(
                stmt=stmt.upper(),
                svc_number=svc_number,
                params=split_params(rest),
                source_member=name,
            )
        )
    return statements


def parse_ieasvc_snapshot(path: Path) -> list[IeasvcStatement]:
    """Parse one ieasvc_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active IEASVCxx member's raw content) into IeasvcStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[IeasvcStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
