"""Parse CICS startup PROC detail dumps produced by
ansible/roles/zos_extract/tasks/cics_deepening.yml into
CicsDfhrplEntry/CicsSitOverride records.

Dump format: three "##BLOCKNAME" sentineled sections, split via
blocks.split_named_blocks() (same bare-sentinel vocabulary
sysinfo_parser.py/vtam_parser.py/db2_catalog_parser.py already share):

  ##DFHRPL -- one "dsn ;;PROC=procname" line per DFHRPL dataset (DFHRPL is
              CICS's own load-library concatenation, functionally
              STEPLIB/JOBLIB for CICS's own dynamic program loading)
  ##SIT    -- ";;PROC=procname" marker lines, each followed by that PROC's
              own raw inline SYSIN card text (SIT override cards) up to
              the next marker or end of block -- KEYWORD=VALUE pairs are
              extracted generically from that raw text (same idiom
              Jes2InitStatement/VtamStartOption use), tolerant of either
              one KEYWORD=VALUE per line or several separated by commas
              on one line
  ##CSD    -- one "dsn ;;PROC=procname" line per discovered DFHCSD DSN
              (not modeled here -- cics_deepening.yml uses this block
              in-play to drive the DFHCSDUP job; cics_csdup_parser.py
              re-derives the CSD DSN from its own ";;CSD_DSN=" marker in
              the ##CSDUP_REPORT block instead of from this module)

NOT YET VALIDATED against a real CICS startup PROC -- the DFHRPL DD-group
extraction is reused near-verbatim from
discover_mstrjcl_proclibs.yml's confirmed IEFPDSI handling (see that
file's own header comment), but that reuse itself, and the SIT
KEYWORD=VALUE extraction alongside it, haven't been checked against a
real CICS startup PROC's actual JCL text.
"""
from __future__ import annotations

import re
from pathlib import Path

from .blocks import split_named_blocks
from .models import CicsDfhrplEntry, CicsSitOverride

_PROC_MARKER = re.compile(r"^;;PROC=(\S*)\s*$")
_DSN_LINE = re.compile(r"^(\S+)\s+;;PROC=(\S*)\s*$")
_KEYWORD_VALUE = re.compile(r"([A-Za-z0-9$#@]+)\s*=\s*([^,\s]+)")


def _parse_dfhrpl(lines: list[str]) -> list[CicsDfhrplEntry]:
    entries: list[CicsDfhrplEntry] = []
    for line in lines:
        m = _DSN_LINE.match(line)
        if m:
            entries.append(CicsDfhrplEntry(dsn=m.group(1), proc=m.group(2)))
    return entries


def _parse_sit(lines: list[str]) -> list[CicsSitOverride]:
    overrides: list[CicsSitOverride] = []
    proc = ""
    for line in lines:
        marker = _PROC_MARKER.match(line)
        if marker:
            proc = marker.group(1)
            continue
        for kv in _KEYWORD_VALUE.finditer(line):
            overrides.append(CicsSitOverride(keyword=kv.group(1), value=kv.group(2), proc=proc))
    return overrides


def parse_cics_proc(path: Path) -> tuple[list[CicsDfhrplEntry], list[CicsSitOverride]]:
    """Parse one cics_deepening.txt dump into (dfhrpl_entries, sit_overrides)."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return (
        _parse_dfhrpl(blocks.get("DFHRPL", [])),
        _parse_sit(blocks.get("SIT", [])),
    )
