"""Parse a 'D PARMLIB' console reply (as dumped by
ansible/roles/zos_extract/tasks/parmlib_snapshot.yml) into ParmlibDataset
rows -- the live PARMLIB concatenation in search order.

Same confirmed 4-column reply shape LNKLST/APF use (see
discover_parmlib.yml's own header comment, which already established this
against a real reply):

    ENTRY  FLAGS  VOLUME  DATA SET
      1      S    HCD000  SYS1.COMMON.PARMLIB
      2      S    BES2W1  SYS3.BES2.PARMLIB

so this is a straight Python port of the same select/regex_replace idiom
lnklst.yml/discover_parmlib.yml already use in Jinja, just kept as its
own file/table/command (unlike LNKLST/APF, which are reduced to a bare
DSN list in Ansible and never saved as their own inventory dimension) so
the FLAGS/VOLUME columns aren't thrown away.
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import ParmlibDataset

_ENTRY_ROW = re.compile(r"^\s*([0-9]+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")


def parse_parmlib_snapshot(path: Path) -> list[ParmlibDataset]:
    """Parse one 'D PARMLIB' reply dump into ParmlibDataset rows, in the
    reply's own search-order sequence."""
    datasets: list[ParmlibDataset] = []
    for raw_line in path.read_text(errors="replace").splitlines():
        match = _ENTRY_ROW.match(raw_line.rstrip())
        if not match:
            continue
        entry, flags, volume, dsn = match.groups()
        datasets.append(ParmlibDataset(entry=entry, flags=flags, volume=volume, dsn=dsn))
    return datasets
