"""Parse db2_catalog.txt dumps produced by
ansible/roles/zos_extract/tasks/db2_catalog.yml (DSNTEP2 batch SQL
queries against SYSIBM.SYSPACKAGE/SYSPLAN) into Db2Package/Db2Plan
records.

CONFIRMED against a real DSNTEP2 report (this site's DBDG subsystem) --
and the real shape turned out completely different from the original
one-row-per-line "NAME CREATOR BINDTIME" guess. DSNTEP2's SYSIBM.SYSPACKAGE
NAME column is wide enough that DSNTEP2 doesn't print rows side-by-side at
all: it TRANSPOSES the result set, printing one column at a time as its
own boxed section (headed by "| NAME |", then "| CREATOR |", then
"| BINDTIME |", in that order, each spanning as many physical print pages
as it needs), and the only thing tying a value in one section back to the
same value in another is a shared row number prefix, e.g.:

    +----------------------------------------------------------------+
    |                              NAME                               |
    +----------------------------------------------------------------+
    479_| SYSSN401                                                   |
    480_| SYSSN402                                                   |
    -------------------------------------------------------------------
    |                            CREATOR                              |
    -------------------------------------------------------------------
    479_| IBMUSER                                                    |
    480_| IBMUSER                                                    |
                                        -----------------------------+
                                        |          BINDTIME          |
                                        -----------------------------+
                                    479_| 2022-09-20-11.33.55.056138 |
                                    480_| 2022-09-20-11.33.55.080844 |

Each column section is accumulated into its own {row_number: value} dict,
keyed by that row number (an int) rather than position, so a page break
splitting one section across several physical pages (confirmed real --
e.g. "PAGE 28.1", a sub-page continuation) just keeps writing into the
same dict instead of needing special-casing (the row-number key itself
makes this immune to the same "section title reprints on every page"
class of bug _smplist_zone.yml's LIST MOD parsing had -- there's no
separate pending-state to accidentally reset here). Once a whole block is
read, rows are reconstructed by NAME's own row numbers (every real row has
a NAME), looking up CREATOR/BINDTIME by that same row number and falling
back to None if a section is short a row for any reason.

Dump format: two blocks, each introduced by a "##BLOCKNAME" sentinel line
("##SYSPACKAGE", "##SYSPLAN"), split via blocks.split_named_blocks() --
same bare-sentinel vocabulary sysinfo_parser.py/vtam_parser.py/
tcpip_parser.py/sms_parser.py already share. Each block's first line is a
";;SSID=xxxx" marker (written by db2_catalog.yml, not part of DSNTEP2's
own report) identifying which DB2 subsystem the query ran against -- same
";;SOURCE_DSN=" marker-line idiom tcpip_parser.py/TcpipProfileStatement
use for tcpip.txt's PROFILE block.

Everything that isn't a "| COLUMNNAME |" section header or a "nnn_| value
|" data row -- border lines (dashes/plus signs, with or without a trailing
"PAGE nn[.n]" page-break marker), blank lines, "DSNnnnnX" message lines --
is skipped by pattern rather than relying on a fixed line shape, the same
"tolerant of surrounding whitespace/noise" approach every other parser in
this pipeline uses.

NOTE: package/plan NAME/CREATOR values are assumed not to contain embedded
whitespace (true for DB2 identifiers) -- if a real value ever did, the
value-capture regex below (non-greedy up to the closing "|") would still
capture it correctly as a single field, since it isn't whitespace-split
the way the original guess was.
"""
from __future__ import annotations

import re
from pathlib import Path

from .blocks import split_named_blocks
from .models import Db2Package, Db2Plan

_SSID_MARKER = re.compile(r"^;;SSID=(\S*)\s*$")
_SECTION_HEADER = re.compile(r"^\s*\|\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*$")
_DATA_ROW = re.compile(r"^\s*(\d+)_\|\s*(.*?)\s*\|\s*$")

_COLUMNS = ("NAME", "CREATOR", "BINDTIME")


def _parse_columns(lines: list[str]) -> tuple[dict[int, str], str]:
    """Read one block's lines into {column: {row_number: value}} plus ssid."""
    columns: dict[str, dict[int, str]] = {c: {} for c in _COLUMNS}
    ssid = ""
    current_column: str | None = None

    for line in lines:
        marker = _SSID_MARKER.match(line)
        if marker:
            ssid = marker.group(1)
            continue

        header = _SECTION_HEADER.match(line)
        if header:
            candidate = header.group(1).upper()
            if candidate in columns:
                current_column = candidate
            continue

        if current_column is None:
            continue

        row = _DATA_ROW.match(line)
        if row:
            row_num, value = row.groups()
            columns[current_column][int(row_num)] = value

    return columns, ssid


def _build_rows(lines: list[str], factory):
    columns, ssid = _parse_columns(lines)
    names = columns["NAME"]
    creators = columns["CREATOR"]
    bindtimes = columns["BINDTIME"]
    return [
        factory(
            name=names[row_num],
            creator=creators.get(row_num),
            bind_timestamp=bindtimes.get(row_num),
            ssid=ssid,
        )
        for row_num in sorted(names)
    ]


def parse_db2_catalog(path: Path) -> tuple[list[Db2Package], list[Db2Plan]]:
    """Parse one db2_catalog.txt dump into (packages, plans)."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return (
        _build_rows(blocks.get("SYSPACKAGE", []), Db2Package),
        _build_rows(blocks.get("SYSPLAN", []), Db2Plan),
    )
