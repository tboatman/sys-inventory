"""Parse db2_catalog.txt dumps produced by
ansible/roles/zos_extract/tasks/db2_catalog.yml (DSNTEP2 batch SQL
queries against SYSIBM.SYSPACKAGE/SYSPLAN) into Db2Package/Db2Plan
records.

THIS IS THE MOST SPECULATIVE PARSER IN THE PIPELINE: DSNTEP2's exact
report formatting (column widths, header/separator line shape, and the
DSNE6xxI message lines it appends) varies by DB2 version/site
configuration, and none of it has been checked against a real DB2
subsystem's actual output while writing this -- same "not yet validated"
situation as every other implementation-only domain in this pipeline,
but explicitly the *most* speculative one (DSNTEP2's authorization/PLAN/
STEPLIB requirements are themselves uncertain, on top of the report
format). Treat the patterns below as a rough starting point only: run
db2_catalog.yml against a real DB2 subsystem, diff the actual SYSPRINT
report text against what's expected here, and rewrite the row-splitting
logic if DSNTEP2's real column layout doesn't match a simple whitespace
split (e.g. if CREATOR could itself contain embedded whitespace, which
plain whitespace-splitting would misparse -- DB2 identifiers normally
can't, but this hasn't been confirmed against a real catalog).

Dump format: two blocks, each introduced by a "##BLOCKNAME" sentinel line
("##SYSPACKAGE", "##SYSPLAN"), split via blocks.split_named_blocks() --
same bare-sentinel vocabulary sysinfo_parser.py/vtam_parser.py/
tcpip_parser.py/sms_parser.py already share. Each block's first line is a
";;SSID=xxxx" marker (written by db2_catalog.yml, not part of DSNTEP2's
own report) identifying which DB2 subsystem the query ran against -- same
";;SOURCE_DSN=" marker-line idiom tcpip_parser.py/TcpipProfileStatement
use for tcpip.txt's PROFILE block.

Each data row is expected to be "NAME CREATOR BINDTIME" (DSNTEP2's own
column order for both SYSIBM.SYSPACKAGE and SYSIBM.SYSPLAN, as queried by
db2_catalog.yml), separated by DSNTEP2's own dashed header/separator
lines and, after the data, a "DSNE610I NUMBER OF ROWS DISPLAYED IS n"
style message -- both kinds of non-data lines are skipped by pattern (a
line of only dashes/plus signs/whitespace, the literal NAME/CREATOR/
BINDTIME header line, or one starting with a DSNnnnnX message ID), rather
than relying on a fixed row count.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, TypeVar

from .blocks import split_named_blocks
from .models import Db2Package, Db2Plan

_SSID_MARKER = re.compile(r"^;;SSID=(\S*)\s*$")
_SEPARATOR_LINE = re.compile(r"^[\s\-+]+$")
_MESSAGE_LINE = re.compile(r"^\s*DSN[A-Z]\d{3,4}[A-Z]\b", re.IGNORECASE)
_HEADER_LINE = re.compile(r"^\s*NAME\s+CREATOR\s+BINDTIME\s*$", re.IGNORECASE)

T = TypeVar("T")


def _parse_rows(lines: list[str], factory: Callable[..., T]) -> list[T]:
    rows: list[T] = []
    ssid = ""
    for line in lines:
        marker = _SSID_MARKER.match(line)
        if marker:
            ssid = marker.group(1)
            continue
        if not line.strip():
            continue
        if _SEPARATOR_LINE.match(line) or _MESSAGE_LINE.match(line) or _HEADER_LINE.match(line):
            continue
        parts = line.split()
        name = parts[0]
        creator = parts[1] if len(parts) > 1 else None
        bind_timestamp = parts[2] if len(parts) > 2 else None
        rows.append(factory(name=name, creator=creator, bind_timestamp=bind_timestamp, ssid=ssid))
    return rows


def parse_db2_catalog(path: Path) -> tuple[list[Db2Package], list[Db2Plan]]:
    """Parse one db2_catalog.txt dump into (packages, plans)."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return (
        _parse_rows(blocks.get("SYSPACKAGE", []), Db2Package),
        _parse_rows(blocks.get("SYSPLAN", []), Db2Plan),
    )
