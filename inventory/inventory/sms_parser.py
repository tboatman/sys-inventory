"""Parse SMS storage group dumps produced by
ansible/roles/zos_extract/tasks/sms.yml into SmsStorageGroup records.

Dump format: the raw 'D SMS,STORGRP(ALL),LISTVOL' console reply, unchanged
-- no sentinel headers needed, since this captures exactly one command's
output (same "single command, no bundling" shape uss_mounts_parser.py
already uses for 'D OMVS,F').

This module ONLY covers storage groups now -- it originally also parsed
'D SMS,SC(*)'/'D SMS,MC(*)' (storage classes/management classes), but
both commands were confirmed INVALID against a real system (and IBM's
own 'D SMS' syntax reference confirms there's no console D-command for
either at all -- see sms.yml's own header comment for the full
explanation). That parsing was removed rather than left as dead code for
commands that don't exist.

CONFIRMED against a real reply (via the 'SG' alias for 'STORGRP', both
documented as equivalent) -- and the real reply's shape turned out to be
completely different from the original guess, not just a formatting
variation. Rewritten from scratch against the real text, which has TWO
separate sections rather than one "header + indented VOLSER lines" shape
per group:

1. A storage-group summary table, one or more repeats of a "STORGRP TYPE
   SYSTEM= 1 2" header (not always once per group -- several groups can
   share one header run) followed by data rows:

       STORGRP  TYPE    SYSTEM= 1 2
       BESCLD   POOL            + +
         SPACE INFORMATION:
         TOTAL SPACE = 53110MB USAGE% = 0 ALERT% = 0
         TRACK-MANAGED SPACE = 53110MB USAGE% = 0 ALERT% = 0
       STORGRP  TYPE    SYSTEM= 1 2
       IBMVTS   TAPE            + +
       MISC     POOL            + +
         SPACE INFORMATION:
         ...

   Each data row is NAME, TYPE (POOL/TAPE/OBJECT/OBJECT BACKUP/DUMMY),
   then one status *symbol* per configured system (not an ENABLE/DISABLE/
   NOTCNCT word as originally guessed) -- '+' enabled, '-' disabled, '*'
   quiesced, and several more per the reply's own LEGEND section at the
   end. `SmsStorageGroup.status` stores this raw symbol sequence verbatim
   (e.g. "+ +") rather than decoding it into an English word, since the
   real reply doesn't summarize multi-system status as a single token and
   guessing at that mapping isn't worth it when the raw symbols plus the
   LEGEND already answer the question. Indented "SPACE INFORMATION:" /
   "TOTAL SPACE .../"TRACK-MANAGED SPACE ..." lines aren't captured (not
   part of this model) -- only TAPE-type groups skip them, which is
   itself informative but not modeled as a dedicated field beyond
   `group_type`.

2. A completely separate, flat VOLUME-to-STORGRP mapping table, NOT
   indented continuation lines under each group as originally guessed:

       VOLUME UNIT MVS  SYSTEM= 1 2                             STORGRP NAME
       BESCS1 A335 ONRW         + +                               BESCLD
       BESCS2                   + +                               BESCLD
       ...
       LISTVOL IS IGNORED FOR OBJECT, OBJECT BACKUP, AND TAPE STORAGE GROUPS
       ***************************** LEGEND *****************************
       ...

   Each row's first token is the VOLSER, its last token is the owning
   storage group's name -- middle columns (UNIT, MVS status, per-system
   symbols) vary in width/presence (blank UNIT/MVS for most volumes in
   the real reply) and aren't captured. The "LISTVOL IS IGNORED FOR
   OBJECT, OBJECT BACKUP, AND TAPE STORAGE GROUPS" line is used as the
   real, stable end-of-table marker (confirmed present, and explains why
   TAPE-type groups like IBMVTS/SGM9CDS never get volume rows) rather
   than trying to pattern-match the LEGEND text itself.
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import SmsStorageGroup

_STORGRP_HEADER_LINE = re.compile(r"^\s*STORGRP\s+TYPE\s+SYSTEM=", re.IGNORECASE)
_STORGRP_DATA_ROW = re.compile(
    r"^(?P<name>[A-Z0-9$#@]{1,8})\s+"
    r"(?P<type>POOL|TAPE|OBJECT(?:\s+BACKUP)?|DUMMY)\s+"
    r"(?P<status>[.+\-*DQ>/=\s]+)$",
    re.IGNORECASE,
)
_VOLUME_HEADER_LINE = re.compile(r"^\s*VOLUME\s+UNIT\s+MVS\s+SYSTEM=", re.IGNORECASE)
_VOLUME_TABLE_END = "LISTVOL IS IGNORED"
_VOLSER = re.compile(r"^[A-Z0-9$#@]{1,6}$", re.IGNORECASE)


def _volume_row(line: str) -> tuple[str, str] | None:
    tokens = line.split()
    if len(tokens) < 2:
        return None
    volser, storgrp = tokens[0], tokens[-1]
    if not _VOLSER.match(volser):
        return None
    return volser.upper(), storgrp.upper()


def parse_sms(path: Path) -> list[SmsStorageGroup]:
    """Parse one sms.txt dump into a list of SmsStorageGroup."""
    text = path.read_text(errors="replace")
    groups: dict[str, SmsStorageGroup] = {}
    order: list[str] = []
    in_volume_table = False

    for line in text.splitlines():
        if _VOLUME_HEADER_LINE.match(line):
            in_volume_table = True
            continue
        if _VOLUME_TABLE_END in line.upper():
            in_volume_table = False
            continue

        if in_volume_table:
            row = _volume_row(line)
            if row:
                volser, storgrp = row
                if storgrp in groups:
                    groups[storgrp].volumes.append(volser)
            continue

        if _STORGRP_HEADER_LINE.match(line):
            continue
        data = _STORGRP_DATA_ROW.match(line)
        if data:
            name = data.group("name").upper()
            groups[name] = SmsStorageGroup(
                name=name,
                status=data.group("status").strip(),
                group_type=data.group("type").upper(),
            )
            order.append(name)

    return [groups[name] for name in order]
