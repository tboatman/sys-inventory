"""Parse cics_deepening.txt's "##CSDUP_REPORT" block -- the SYSPRINT
report text from running DFHCSDUP's LIST command (see
ansible/roles/zos_extract/tasks/_cics_csdup_dump.yml) -- into
CicsCsdDefinition records.

THE MOST SPECULATIVE PARSER IN THIS PIPELINE, alongside
db2_catalog_parser.py and wlm_zosmf_parser.py -- and unlike those two,
this is speculative on *two* independent axes at once:

1. DFHCSDUP's LIST command *syntax* actually is confirmed against real
   IBM CICS Transaction Server documentation this round (see
   cics_deepening.yml's own header comment for the specifics: LIST ALL /
   LIST LIST(name) OBJECTS, and PARM='CSD(READONLY)' for the read-only
   access this pipeline actually uses) -- so the SYSIN control statements
   sent to DFHCSDUP are on solid ground.
2. DFHCSDUP's LIST report *print format* (the actual column layout of
   its SYSPRINT output) is NOT confirmed -- no real sample of this report
   was found while writing this (IBM's own docs pages 403'd on direct
   fetch, same situation sysinfo_parser.py/vtam_parser.py/tcpip_parser.py
   already document for their own commands), only a secondhand forum
   mention of some column positions for a *different* DFHCSDUP report
   variant. Given that, this deliberately does NOT attempt fixed-column
   slicing (racf_parser.py's approach, used there only because a working
   third-party reference implementation existed to derive real byte
   offsets from -- no such reference exists for DFHCSDUP). Instead, each
   report line is matched against a generic "TWO-TOKEN" heuristic --
   an all-caps resource-type-like first token (e.g. PROGRAM, TRANSACTION,
   MAPSET, FILE) followed by a resource-name-shaped second token (1-8
   alnum/$#@ characters, CICS's own resource-name length limit) -- with
   the current GROUP name (from a "GROUP: name" or "GROUP name"-shaped
   line, tolerant of exact separator) carried forward onto each
   subsequent match, the same "capture what's confidently recognizable,
   skip everything else" tolerance uss_mounts_parser.py/sms_parser.py use
   for their own unconfirmed report shapes. Lines that don't match either
   pattern are silently skipped rather than guessed at -- this WILL
   under-report against a real DFHCSDUP LIST report until the real column
   layout is confirmed and this parser is rewritten against it; treat any
   count from this dimension as a floor, not a real total.

Also carries the real, documented operational-risk caveat from
cics_deepening.yml's own header comment: whether a live CICS region's own
CSD access mode still lets a concurrent CSD(READONLY) batch DFHCSDUP LIST
succeed cleanly hasn't been confirmed against a real region, only against
IBM's general RLS/quiescing documentation.

Dump format: the raw SYSPRINT report text for each queried CSD DSN,
prefixed by a ";;CSD_DSN=dsn" marker line (not part of DFHCSDUP's own
report -- same marker-line idiom db2_catalog_parser.py's ";;SSID="/
tcpip_parser.py's ";;SOURCE_DSN=" already use), inside the
"##CSDUP_REPORT" block (see blocks.split_named_blocks()).
"""
from __future__ import annotations

import re
from pathlib import Path

from .blocks import split_named_blocks
from .models import CicsCsdDefinition

_CSD_DSN_MARKER = re.compile(r"^;;CSD_DSN=(\S*)\s*$")
_GROUP_LINE = re.compile(r"^\s*GROUP\s*[:=]?\s+(\S+)\s*$", re.IGNORECASE)
_TYPE_NAME_ROW = re.compile(r"^\s*([A-Z][A-Z0-9]{2,15})\s+([A-Za-z0-9$#@]{1,8})\s*$")
_SKIP_LINE = re.compile(
    r"^\s*$|DFHCSDUP|^\s*PAGE\s+\d+|^[\s\-=+]+$|^\s*LIST\b", re.IGNORECASE
)


def _parse_report(lines: list[str]) -> list[CicsCsdDefinition]:
    definitions: list[CicsCsdDefinition] = []
    csd_dsn = ""
    group = ""
    for line in lines:
        marker = _CSD_DSN_MARKER.match(line)
        if marker:
            csd_dsn = marker.group(1)
            group = ""
            continue
        group_match = _GROUP_LINE.match(line)
        if group_match:
            group = group_match.group(1)
            continue
        if _SKIP_LINE.search(line):
            continue
        row_match = _TYPE_NAME_ROW.match(line)
        if row_match:
            definitions.append(
                CicsCsdDefinition(
                    def_type=row_match.group(1),
                    name=row_match.group(2),
                    group=group,
                    csd_dsn=csd_dsn,
                )
            )
    return definitions


def parse_cics_csdup(path: Path) -> list[CicsCsdDefinition]:
    """Parse one cics_deepening.txt dump's ##CSDUP_REPORT block into
    CicsCsdDefinition records."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return _parse_report(blocks.get("CSDUP_REPORT", []))
