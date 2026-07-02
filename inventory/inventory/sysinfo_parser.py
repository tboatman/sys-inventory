"""Parse the sysinfo.txt dump produced by zos-extract/python/extrsys.py
('D SYMBOLS' + 'D IPLINFO' console replies) into a single SystemInfo
record.

CONFIRMED against real 'D SYMBOLS'/'D IPLINFO' replies -- and the real
shape differed from the original guess in several ways that mattered
(regexes below were rewritten against the real text, not just re-flagged
as confirmed):

'D SYMBOLS' reply -- no "SYSNAME  = &SYSNAME. = value" label prefix as
originally guessed; each line is just "&SYMBOL.  = value" directly:

    IEA007I STATIC SYSTEM SYMBOL VALUES 754
    &SYSALVL.          = "2"
    &SYSCLONE.         = "S2"
    &SYSNAME.          = "BES2"
    &SYSOSLVL.         = "Z1020500"
    &SYSPLEX.          = "BESCFCC"
    ...

'D IPLINFO' reply -- RELEASE and ARCHLVL happened to still match the
original guess (they're matched by regex.search() over the whole block,
not a specific line/column position, so line reflow didn't break them),
but the IPL volume and parm-member fields needed real fixes: there is no
"IPL PARM nn" text anywhere in a real reply (that was invented), and the
volume is "VOLUME(xxxxxx)" (parenthesized), not "VOLUME: xxxxxx"
(colon-separated) as guessed:

    IEE254I  06.26.05 IPLINFO DISPLAY 740
    SYSTEM IPLED AT 21.35.16 ON 06/12/2026
    RELEASE z/OS 02.05.00    LICENSE = z/OS
    USED LOADBN IN SYS0.IPLPARM ON 0A113
    ARCHLVL = 2   MTLSHARE = N
    VALIDATED BOOT: NO
    IEASYM LIST = (BN,L)
    IEASYS LIST = (BN) (OP)
    IODF DEVICE: ORIGINAL(0A113) CURRENT(0A113)
    IPL DEVICE: ORIGINAL(0A348) CURRENT(0A348) VOLUME(BES25A)
    VM CPID = z/VM    7.4.0

`ipl_parm_member` is now sourced from "IEASYS LIST = (...)" instead (the
first suffix in the first parenthesized group) -- the real, documented
mechanism for the active IEASYSxx member, same field
ansible/roles/zos_extract/tasks/discover_active_parmlib_suffixes.yml
already parses (confirmed there too) for the same purpose, just read
here directly off the raw text instead of via Jinja.

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

_SYSNAME = re.compile(r"&SYSNAME\.\s*=\s*\"([A-Za-z0-9$#@]+)\"", re.IGNORECASE)
_SYSCLONE = re.compile(r"&SYSCLONE\.\s*=\s*\"([A-Za-z0-9$#@]+)\"", re.IGNORECASE)
_SYSPLEX = re.compile(r"&SYSPLEX\.\s*=\s*\"([A-Za-z0-9$#@]+)\"", re.IGNORECASE)

_IPL_VOLUME = re.compile(r"\bVOLUME\(([A-Za-z0-9$#@]+)\)", re.IGNORECASE)
_IEASYS_LIST = re.compile(r"\bIEASYS\s+LIST\s*=\s*\(([^)]*)\)", re.IGNORECASE)
_RELEASE = re.compile(r"\bRELEASE\s+(z/OS\s+\S+)", re.IGNORECASE)
_ARCHLVL = re.compile(r"\bARCHLVL\s*=\s*(\S+)", re.IGNORECASE)


def _first_match(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def _first_ieasys_suffix(text: str) -> str | None:
    m = _IEASYS_LIST.search(text)
    if not m:
        return None
    first_suffix = m.group(1).split(",")[0].strip()
    return first_suffix or None


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
        ipl_parm_member=_first_ieasys_suffix(iplinfo_text),
        release=_first_match(_RELEASE, iplinfo_text),
        archlvl=_first_match(_ARCHLVL, iplinfo_text),
    )
