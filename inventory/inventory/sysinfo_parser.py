"""Parse the sysinfo.txt dump produced by zos-extract/python/extrsys.py
('D SYMBOLS' + 'D IPLINFO' console replies) into a single SystemInfo
record.

Like smpe_parser.py, this anchors on the keyword tokens that identify each
field (SYSNAME, SYSCLONE, SYSPLEX, VOLUME, IPL PARM) and is tolerant of
surrounding whitespace/noise -- but unlike SMP/E's LIST report format
(documented in the SMP/E Reference and fairly stable), 'D SYMBOLS'/
'D IPLINFO' reply formatting is known to vary more by release and by which
symbols a shop has defined, and there was no real system available to
calibrate these regexes against. Treat the patterns below as a starting
point: run extrsys.py against a real system, diff the actual reply text
against what's expected here, and tune the regexes accordingly before
relying on this in production. Any field whose pattern doesn't match is
left None -- a partially-populated SystemInfo is normal, not an error.

Dump format: two blocks, each introduced by a "##BLOCKNAME" sentinel line
(e.g. "##SYMBOLS", "##IPLINFO") followed by that command's raw reply text,
unchanged, up to the next sentinel or end of file. Split via
blocks.split_named_blocks(), shared with catalog_parser.py (extrcat.py's
NONVSAM/LISTCAT dump uses the same bare-sentinel vocabulary).
"""
from __future__ import annotations

import re
from pathlib import Path

from .blocks import split_named_blocks
from .models import SystemInfo

# 'D SYMBOLS' reply (abbreviated, real output has many more &SYSxxx lines):
#   SYSTEM SYMBOL LIST
#   SYSNAME  = &SYSNAME.  = "SYS1"
#   SYSCLONE = &SYSCLONE. = "S1"
#   SYSPLEX  = &SYSPLEX.  = "PLEX1"
_SYSNAME = re.compile(r"\bSYSNAME\s*=.*?\"([A-Za-z0-9$#@]+)\"", re.IGNORECASE)
_SYSCLONE = re.compile(r"\bSYSCLONE\s*=.*?\"([A-Za-z0-9$#@]+)\"", re.IGNORECASE)
_SYSPLEX = re.compile(r"\bSYSPLEX\s*=.*?\"([A-Za-z0-9$#@]+)\"", re.IGNORECASE)

# 'D IPLINFO' reply (abbreviated):
#   SYSTEM IPLED AT 08.00.00 ON 07/01/2026  RELEASE z/OS 02.05.00
#   SYSTEM IPLED FROM 01A0  IPL PARM 00
#   ARCHLVL = 2       MTLSHARE = N
#   IPL DEVICE: 01A0  VOLUME: RES0S1
_IPL_VOLUME = re.compile(r"\bVOLUME:\s*([A-Za-z0-9$#@]+)", re.IGNORECASE)
_IPL_PARM = re.compile(r"\bIPL\s+PARM\s+([A-Za-z0-9$#@]+)", re.IGNORECASE)
_RELEASE = re.compile(r"\bRELEASE\s+(z/OS\s+\S+)", re.IGNORECASE)
_ARCHLVL = re.compile(r"\bARCHLVL\s*=\s*(\S+)", re.IGNORECASE)


def _first_match(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def parse_sysinfo(path: Path) -> SystemInfo:
    """Parse one extrsys.py dump into a single SystemInfo record."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)

    symbols_text = "\n".join(blocks.get("SYMBOLS", []))
    iplinfo_text = "\n".join(blocks.get("IPLINFO", []))

    return SystemInfo(
        sysname=_first_match(_SYSNAME, symbols_text),
        sysclone=_first_match(_SYSCLONE, symbols_text),
        sysplex=_first_match(_SYSPLEX, symbols_text),
        ipl_volume=_first_match(_IPL_VOLUME, iplinfo_text),
        ipl_parm_member=_first_match(_IPL_PARM, iplinfo_text),
        release=_first_match(_RELEASE, iplinfo_text),
        archlvl=_first_match(_ARCHLVL, iplinfo_text),
    )
