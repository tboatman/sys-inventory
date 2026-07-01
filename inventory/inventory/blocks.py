"""Shared splitter for the bare "##BLOCKNAME" sentinel convention used by
extract dumps that capture several distinct console commands/reports into
one file (e.g. extrsys.py's 'D SYMBOLS'/'D IPLINFO' pair, extrcat.py's
NONVSAM/LISTCAT pair). This is a different sentinel vocabulary from
jcl_parser.split_members()'s "##MEMBER name" (a bare block label, not a
keyword+name pair), so it has its own tiny splitter here rather than
overloading that one.
"""
from __future__ import annotations

import re

_BLOCK_HDR = re.compile(r"^##(\S+)\s*$")


def split_named_blocks(text: str) -> dict[str, list[str]]:
    """Split text into {block_name: [raw lines]} on "##BLOCKNAME" sentinel
    lines. Lines before the first sentinel are discarded."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _BLOCK_HDR.match(line)
        if m:
            current = m.group(1)
            blocks[current] = []
            continue
        if current is not None:
            blocks[current].append(line)
    return blocks
