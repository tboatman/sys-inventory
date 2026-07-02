"""Parse VTAM dumps produced by ansible/roles/zos_extract/tasks/vtam.yml
into VtamMajorNode/VtamStartOption/VtamTopologySummary records.

Dump format: three blocks, each introduced by a "##BLOCKNAME" sentinel
line ("##MAJNODES", "##VTAMOPTS", "##TOPO") followed by that command's
raw reply text, unchanged, up to the next sentinel or end of file -- same
bare-sentinel vocabulary sysinfo_parser.py/catalog_parser.py already
share, split via blocks.split_named_blocks().

'D NET,MAJNODES' and 'D NET,VTAMOPTS' are now BOTH CONFIRMED against real
replies (a follow-up round provided both). 'D NET,MAJNODES' first:
real per-row shape turned out to be different from the original guess (no
separate NAME/STATUS-only columns; each row is IST089I-prefixed with a
TYPE field in between), but the same tolerant "name token, then a known
status token found anywhere later on the line" match -- not fixed column
positions -- already handled it correctly without any regex changes:

    IST097I DISPLAY ACCEPTED
    IST350I DISPLAY TYPE = MAJOR NODES 769
    IST089I VTAMSEG  TYPE = APPL SEGMENT     , ACTIV
    IST089I ISTADJCP TYPE = ADJCP MAJOR NODE , ACTIV
    IST1454I 29 RESOURCE(S) DISPLAYED
    IST314I END

'D NET,VTAMOPTS' reply, confirmed: a set of "IST1189I KEYWORD = VALUE"
pairs, two per line in most cases (VTAM's own start-option display
convention) -- e.g. "IST1189I NODETYPE = NN       CPNAME   = NN01". The
same generic regex_findall pass over the whole block (not per-field
regexes) handled the real reply correctly, including its real NODETYPE/
CPNAME confirmation ("NODETYPE = NN" parsed clean) -- same "one generic
KEYWORD=value pass" idiom
ansible/roles/zos_extract/tasks/discover_active_members.yml already uses
for IEASYSxx (done here in Python instead of Jinja). Answering "is APPN
enabled, and as what role" is then just filtering this table for the
NODETYPE/CPNAME keywords -- no dedicated field needed.

One confirmed, minor, low-impact limitation: a handful of keywords (seen:
HPRPST, IQDIOSTG) have a *two-token* value in the real reply (e.g.
"HPRPST = LOW          480S" -- a priority name plus a separate timer
value), and this regex only captures the first token (VtamStartOption's
`value` is a single string) -- the second token is silently dropped
rather than misattributed to a bogus keyword (it doesn't itself look like
"WORD = something", so it's just skipped). Doesn't affect NODETYPE/CPNAME
or the vast majority of keywords, which are single-token; not worth a
more complex regex for the couple of outliers unless a future need
actually requires those specific fields.

'D NET,TOPO' reply, by contrast, IS CONFIRMED against a real system this
round -- unlike the two commands above. Its actual shape is a topology
*database summary*, not a list of individual known nodes by name (which
an earlier round assumed, and used to justify skipping this command
entirely as "even less certain" than MAJNODES/VTAMOPTS): a single record
with two message-ID-anchored data rows --

    IST1306I LAST CHECKPOINT   ADJ  NN   EN   SERVED EN CDSERVR ICN  BN
    IST1307I NONE              1    2    0    0         0       0    0
    IST1781I INITDB CHECKPOINT DATASET   LAST GARBAGE COLLECTION
    IST1785I NONE                        07/01/26 21:44:28

IST1307I's data columns (after the LAST CHECKPOINT token) are always the
same seven numeric counts in that order: ADJ, NN, EN, SERVED EN, CDSERVR,
ICN, BN. IST1785I's data columns are the INITDB checkpoint dataset name
(or "NONE") followed by a date and a time (two whitespace-separated
tokens, joined back together here with a space).
"""
from __future__ import annotations

import re
from pathlib import Path

from .blocks import split_named_blocks
from .models import VtamMajorNode, VtamStartOption, VtamTopologySummary

_STATUS_TOKENS = r"ACTIV|ACT/S|INACT|PEND\w*|ACTIVAT\w*"
_MAJNODE_ROW = re.compile(
    r"^\s*(?:IST\d+I\s+)?(?P<name>[A-Z0-9$#@]+)\b.*?\b(?P<status>" + _STATUS_TOKENS + r")\b",
    re.IGNORECASE,
)
_VTAMOPT_KV = re.compile(r"([A-Z][A-Z0-9$#@]*)\s*=\s*(\S+)", re.IGNORECASE)
_IST1307 = re.compile(
    r"IST1307I\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"
)
_IST1785 = re.compile(r"IST1785I\s+(\S+)\s+(\S+)\s+(\S+)")


def _parse_majnodes(lines: list[str]) -> list[VtamMajorNode]:
    # Matched positively (a name token followed somewhere by one of the
    # known status values), rather than negatively filtering out banner/
    # footer lines by message ID -- VTAM data rows may themselves carry a
    # repeated ISTnnnnI prefix (same idiom discover_proclib.yml's $HASP319
    # repeated-per-line prefix uses for '$D PROCLIB'), so a blanket
    # "starts with IST" exclusion would risk dropping real rows too.
    # Banner/footer lines ("IST097I DISPLAY ACCEPTED", "IST314I END",
    # column-header rows) simply don't contain a real status token and
    # so never match.
    nodes = []
    for line in lines:
        match = _MAJNODE_ROW.match(line)
        if match:
            nodes.append(VtamMajorNode(name=match.group("name"), status=match.group("status").upper()))
    return nodes


def _parse_vtamopts(lines: list[str]) -> list[VtamStartOption]:
    text = "\n".join(lines)
    return [
        VtamStartOption(keyword=keyword.upper(), value=value)
        for keyword, value in _VTAMOPT_KV.findall(text)
    ]


def _parse_topo(lines: list[str]) -> VtamTopologySummary | None:
    text = "\n".join(lines)
    counts = _IST1307.search(text)
    checkpoint_meta = _IST1785.search(text)
    if counts is None and checkpoint_meta is None:
        return None
    summary = VtamTopologySummary()
    if counts:
        summary.last_checkpoint = counts.group(1)
        summary.adj = int(counts.group(2))
        summary.nn = int(counts.group(3))
        summary.en = int(counts.group(4))
        summary.served_en = int(counts.group(5))
        summary.cdservr = int(counts.group(6))
        summary.icn = int(counts.group(7))
        summary.bn = int(counts.group(8))
    if checkpoint_meta:
        summary.initdb_checkpoint_dataset = checkpoint_meta.group(1)
        summary.last_garbage_collection = f"{checkpoint_meta.group(2)} {checkpoint_meta.group(3)}"
    return summary


def parse_vtam(
    path: Path,
) -> tuple[list[VtamMajorNode], list[VtamStartOption], VtamTopologySummary | None]:
    """Parse one vtam.txt dump into (major nodes, start options, topology summary)."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return (
        _parse_majnodes(blocks.get("MAJNODES", [])),
        _parse_vtamopts(blocks.get("VTAMOPTS", [])),
        _parse_topo(blocks.get("TOPO", [])),
    )
