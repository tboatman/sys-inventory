"""Parse VTAM dumps produced by ansible/roles/zos_extract/tasks/vtam.yml
into VtamMajorNode/VtamStartOption records.

Dump format: two blocks, each introduced by a "##BLOCKNAME" sentinel line
("##MAJNODES", "##VTAMOPTS") followed by that command's raw reply text,
unchanged, up to the next sentinel or end of file -- same bare-sentinel
vocabulary sysinfo_parser.py/catalog_parser.py already share, split via
blocks.split_named_blocks().

NOT YET VALIDATED against a real system: IBM's docs site 403'd on direct
fetch and no secondary source turned up real sample output for either
command while writing this (both checked). Treat the patterns below as a
starting point, the same situation sysinfo_parser.py documents for its
own 'D SYMBOLS'/'D IPLINFO' regexes -- run vtam.yml against a real system,
diff the actual reply text against what's expected here, and tune
accordingly before relying on this in production.

'D NET,MAJNODES' reply (expected shape, not confirmed): a summary table,
one row per major node, name followed somewhere on the line by a status
token (ACTIV, ACT/S, INACT, PENDING, ...). Matched generically -- a NAME
token then a status token drawn from a known set anywhere after it --
rather than fixed column positions, since the exact layout isn't
confirmed (same tolerance uss_mounts_parser.py uses for 'D OMVS,F').

'D NET,VTAMOPTS' reply (expected shape, not confirmed): a set of
"KEYWORD = VALUE" pairs, several per line (VTAM's own start-option
display convention) -- e.g. "NODETYPE = NN" / "CPNAME = NN01". Captured
generically via one regex_findall pass over the whole block, the same
"one generic KEYWORD=value pass, not per-field regexes" idiom
ansible/roles/zos_extract/tasks/discover_active_members.yml already uses
for IEASYSxx (done here in Python instead of Jinja). Answering "is APPN
enabled, and as what role" is then just filtering this table for the
NODETYPE/CPNAME keywords -- no dedicated field needed.
"""
from __future__ import annotations

import re
from pathlib import Path

from .blocks import split_named_blocks
from .models import VtamMajorNode, VtamStartOption

_STATUS_TOKENS = r"ACTIV|ACT/S|INACT|PEND\w*|ACTIVAT\w*"
_MAJNODE_ROW = re.compile(
    r"^\s*(?:IST\d+I\s+)?(?P<name>[A-Z0-9$#@]+)\b.*?\b(?P<status>" + _STATUS_TOKENS + r")\b",
    re.IGNORECASE,
)
_VTAMOPT_KV = re.compile(r"([A-Z][A-Z0-9$#@]*)\s*=\s*(\S+)", re.IGNORECASE)


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


def parse_vtam(path: Path) -> tuple[list[VtamMajorNode], list[VtamStartOption]]:
    """Parse one vtam.txt dump into (major nodes, start options)."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return (
        _parse_majnodes(blocks.get("MAJNODES", [])),
        _parse_vtamopts(blocks.get("VTAMOPTS", [])),
    )
