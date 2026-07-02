"""Parse SMS dumps produced by ansible/roles/zos_extract/tasks/sms.yml
into SmsStorageGroup/SmsStorageClass/SmsManagementClass records.

Dump format: three blocks, each introduced by a "##BLOCKNAME" sentinel
line ("##STORGRP", "##STORCLAS", "##MGMTCLAS") followed by that command's
raw reply text, unchanged -- same bare-sentinel vocabulary
sysinfo_parser.py/vtam_parser.py/tcpip_parser.py already share, split via
blocks.split_named_blocks().

NOT YET VALIDATED against a real system: none of 'D SMS,STORGRP(*),
LISTVOL', 'D SMS,SC(*)', or 'D SMS,MC(*)' has been checked against real
sample output while writing this (same situation vtam_parser.py/
tcpip_parser.py document for their own commands). Treat the patterns
below as a starting point -- run sms.yml against a real system, diff the
actual reply text against what's expected here, and tune accordingly
before relying on this in production.

'D SMS,STORGRP(*),LISTVOL' reply (expected shape, not confirmed): one
header line per storage group (a NAME token followed somewhere by an
ENABLE/DISABLE/NOTCNCT status token), followed by one or more indented
continuation lines listing that group's VOLSERs -- the same "header line
+ indented continuation lines" shape uss_mounts_parser.py already
tolerates for 'D OMVS,F'.

'D SMS,SC(*)'/'D SMS,MC(*)' replies (expected shape, not confirmed): one
header line per class (just the class name, alone on its own line),
followed by indented attribute lines in "KEYWORD(VALUE)" form (ISMF's own
storage/management class display convention) -- captured generically via
one regex_findall pass per class, the same "one generic keyword pass,
not per-field regexes" idiom VtamStartOption/Jes2InitStatement use.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, TypeVar

from .blocks import split_named_blocks
from .models import SmsManagementClass, SmsStorageClass, SmsStorageGroup

_STATUS_TOKENS = r"ENABLE|DISABLE|NOTCNCT"
_STORGRP_HEADER = re.compile(
    r"^(?P<name>[A-Z0-9$#@]{1,8})\b.*?\b(?P<status>" + _STATUS_TOKENS + r")\b",
    re.IGNORECASE,
)
_VOLSER = re.compile(r"\b([A-Z0-9$#@]{1,6})\b", re.IGNORECASE)
_VOLSER_NOISE = {"ENABLE", "DISABLE", "NOTCNCT", "VOLUME", "VOLUMES", "STATUS"}

# z/OS console message IDs (e.g. "IGD002I") -- excluded so banner/footer
# lines aren't mistaken for a bare class-name header line below.
_MSG_ID = re.compile(r"^[A-Z]{2,4}\d{3,5}[A-Z]?$")
_CLASS_HEADER = re.compile(r"^(?P<name>[A-Z0-9$#@]{1,8}):?$", re.IGNORECASE)
_CLASS_HEADER_NOISE = {"END", "DISPLAY"}
_ATTR_PAREN = re.compile(r"([A-Z][A-Z0-9$#@]*)\(([^()]*)\)", re.IGNORECASE)

T = TypeVar("T")


def _parse_storgrps(lines: list[str]) -> list[SmsStorageGroup]:
    groups: list[SmsStorageGroup] = []
    current: SmsStorageGroup | None = None
    for line in lines:
        header = _STORGRP_HEADER.match(line)
        if header:
            current = SmsStorageGroup(name=header.group("name").upper(), status=header.group("status").upper())
            groups.append(current)
            continue
        if current is None or not line.startswith((" ", "\t")):
            continue
        current.volumes.extend(
            token.upper() for token in _VOLSER.findall(line) if token.upper() not in _VOLSER_NOISE
        )
    return groups


def _parse_classes(lines: list[str], factory: Callable[..., T]) -> list[T]:
    classes: list[T] = []
    current: T | None = None
    for line in lines:
        stripped = line.strip()
        if stripped and not line.startswith((" ", "\t")):
            header = _CLASS_HEADER.match(stripped)
            if header and not _MSG_ID.match(header.group("name")) and \
                    header.group("name").upper() not in _CLASS_HEADER_NOISE:
                current = factory(name=header.group("name").upper())
                classes.append(current)
                continue
        if current is None:
            continue
        for keyword, value in _ATTR_PAREN.findall(line):
            current.params[keyword.upper()] = value.strip()
    return classes


def parse_sms(path: Path) -> tuple[list[SmsStorageGroup], list[SmsStorageClass], list[SmsManagementClass]]:
    """Parse one sms.txt dump into (storage groups, storage classes, management classes)."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return (
        _parse_storgrps(blocks.get("STORGRP", [])),
        _parse_classes(blocks.get("STORCLAS", []), SmsStorageClass),
        _parse_classes(blocks.get("MGMTCLAS", []), SmsManagementClass),
    )
