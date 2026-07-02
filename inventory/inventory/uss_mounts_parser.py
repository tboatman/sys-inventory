"""Parse 'D OMVS,F' dumps (see ansible/roles/zos_extract/tasks/uss_mounts.yml)
into UssMount records -- one per currently-mounted USS filesystem.

Dump format: the raw console reply, unchanged -- no sentinel headers
needed, since this captures exactly one D-command's output (unlike
sysinfo.txt, which bundles two under ##SYMBOLS/##IPLINFO). Expected shape,
based on IBM's own BPXO04xI message documentation (NOT yet independently
confirmed against a real reply at this site -- see uss_mounts.yml's own
header comment for the same caveat):

    BPXO047I 15.34.10 DISPLAY OMVS 678
    OMVS     000E ACTIVE                          OMVS=(ZOS)
    TYPENAME DEVICE ----------STATUS------------ MODE  LATCHES
    ZFS           1 ACTIVE                        RDWR    L=136
          NAME=OMVS.ROOT.ZFS               PATH=/
          OWNER=ZOS      AUTOMOVE=Y    CLIENT=N
    ZFS           2 ACTIVE                        RDWR    L=1
          NAME=OMVS.ETC.ZFS                PATH=/etc
          OWNER=ZOS      AUTOMOVE=Y    CLIENT=N

Each filesystem is one unindented "header" line (TYPENAME/DEVICE/STATUS/
MODE) followed by one or more indented continuation lines carrying NAME=/
PATH= (plus other attributes this parser doesn't capture). A header line
is recognized generically -- a TYPENAME token, a numeric DEVICE, then a
RDWR/READ/RDONLY MODE token somewhere on the line -- rather than by fixed
column positions, since exact spacing isn't confirmed here the way
racf_parser.py's byte offsets are (at least) confirmed against a working
third-party reference. Tolerate reasonable drift in spacing/extra columns
rather than being exact-match.
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import UssMount

_HEADER = re.compile(
    r"^(?P<type>[A-Z0-9]+)\s+(?P<device>\d+)\s+(?P<status>\S+)\s+.*?"
    r"(?P<mode>RDWR|READ|RDONLY)\b"
)
_NAME = re.compile(r"\bNAME=(\S+)")
_PATH = re.compile(r"\bPATH=(\S+)")
_MOUNTED_DATE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")


def parse_uss_mounts(path: Path) -> list[UssMount]:
    text = path.read_text(errors="replace")
    mounts: list[UssMount] = []
    current: UssMount | None = None

    for line in text.splitlines():
        header = _HEADER.match(line)
        if header:
            date_match = _MOUNTED_DATE.search(line)
            current = UssMount(
                path="",
                fs_type=header.group("type"),
                device=header.group("device"),
                status=header.group("status"),
                mode=header.group("mode"),
                mounted_date=date_match.group(1) if date_match else None,
            )
            mounts.append(current)
            continue

        if current is None or not line.startswith((" ", "\t")):
            continue

        name_match = _NAME.search(line)
        if name_match:
            current.name = name_match.group(1)
        path_match = _PATH.search(line)
        if path_match:
            current.path = path_match.group(1)

    # drop any header block where a PATH= line never showed up (malformed
    # or unrecognized continuation-line shape) rather than surfacing a
    # half-populated record
    return [m for m in mounts if m.path]
