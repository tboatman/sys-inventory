"""Parse 'D OMVS,F' dumps (see ansible/roles/zos_extract/tasks/uss_mounts.yml)
into UssMount records -- one per currently-mounted USS filesystem.

Dump format: the raw console reply, unchanged -- no sentinel headers
needed, since this captures exactly one D-command's output (unlike
sysinfo.txt, which bundles two under ##SYMBOLS/##IPLINFO).

CONFIRMED against a real 'D OMVS,F' reply. The real message ID seen was
BPXO045I (not BPXO047I, the number originally guessed from IBM's generic
BPXO04xI message documentation before a real reply was available -- the
exact BPXO04xI number apparently varies; this parser never matched on the
message ID itself, so that didn't matter). The real per-filesystem shape,
confirmed:

    BPXO045I 06.25.08 DISPLAY OMVS 726
    OMVS     0010 ACTIVE             OMVS=(00,BN)
    TYPENAME   DEVICE ----------STATUS----------- MODE  MOUNTED    LATCHES
    ZFS           117 ACTIVE                      RDWR  07/01/2026  L=77
      NAME=USSHOME.XYZTYB                               12.05.52    Q=0
      PATH=/home/xyztyb
      OWNER=SYSB     AUTOMOVE=Y CLIENT=N

One notable difference from the originally-guessed shape: NAME= and PATH=
land on *separate* continuation lines here, each with extra trailing
fields this parser doesn't capture (a mount time next to NAME=, a queue
count `Q=`, `OWNER=`/`AUTOMOVE=`/`CLIENT=`, and occasionally an extra
`MOUNT PARM=...` line for some filesystem types e.g. TFS/AUTOMNT). None of
that broke parsing: the loop below matches NAME=/PATH= independently per
continuation line rather than requiring both on one line, so it handles
this real shape (and the originally-guessed combined-line shape) the
same way. Each filesystem is one unindented "header" line (TYPENAME/
DEVICE/STATUS/MODE/MOUNTED date) followed by one or more indented
continuation lines. The header line is recognized generically -- a
TYPENAME token, a numeric DEVICE, then a RDWR/READ/RDONLY MODE token
somewhere on the line -- confirmed tolerant of the real column
spacing/widths, which don't line up exactly with the originally-guessed
example.
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
