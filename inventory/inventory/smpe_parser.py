"""Parse SMP/E LIST command report output (LIST DDDEF / LIST MOD /
LIST SYSMOD, as driven by zos-extract/python/smplist.py) into
Zone objects.

SMP/E's printed LIST report layout is documented (see the SMP/E for z/OS
Reference) but varies cosmetically between releases — page headers, GIM
message-ID prefixes, and column widths can differ by shop. Rather than
match fixed columns, this parser anchors on the stable keyword tokens that
always appear in LIST output (ZONE, DDNAME, DSNAME, FMID, STATUS) and is
deliberately tolerant of surrounding whitespace/noise. If your
installation's report differs enough that this misses data, tune the
regexes below — the section state machine itself shouldn't need to change.
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import Zone

_ZONE_HDR = re.compile(r"\bZONE\s+([A-Za-z0-9$#@]+)\b")
# Each LIST report opens with a "<zone>  <TYPE> ENTRIES" title (confirmed for
# DDDEF against real output) that doubles as both the section marker and the
# zone name -- there's no separate command echo to key off of.
_SECTION_HDR = re.compile(
    r"^\s*([A-Za-z0-9$#@]+)\s+(DDDEF|MOD|SYSMOD)\s+ENTRIES\b", re.IGNORECASE
)
_SECTION_DDDEF = re.compile(r"\bLIST\s+DDDEF\b", re.IGNORECASE)
_SECTION_FILE = re.compile(r"\bLIST\s+MOD\b", re.IGNORECASE)
_SECTION_SYSMOD = re.compile(r"\bLIST\s+SYSMOD\b", re.IGNORECASE)

# LIST DDDEF prints one entry per DD as a two-line block, e.g.:
#   AACBCNTL  DATASET         = SYS1.AACBCNTL
#             SHR
_DDDEF_ENTRY = re.compile(
    r"^\s*([A-Za-z0-9$#@]+)\s+DATASET\s*=\s*([A-Za-z0-9$#@.()]+)", re.IGNORECASE
)
# LIST MOD prints one entry per element as a small multi-line block, e.g.:
#   ADMAET0A  LASTUPD         = JGD3219  TYPE=ADD
#             LIBRARIES       = DISTLIB=AADMMOD
#             FMID            = JGD3219
#             RMID            = JGD3219
#             LMOD            = ADMAET0A
# -- the element name and its FMID are on separate lines, so track the
# pending element name from the LASTUPD line until the FMID line arrives.
_FILE_MODULE = re.compile(r"^\s*([A-Za-z0-9$#@]+)\s+LASTUPD\b", re.IGNORECASE)
_FILE_FMID = re.compile(r"^\s*FMID\s*=\s*([A-Za-z0-9$#@]+)", re.IGNORECASE)
# LIST SYSMOD prints one entry per SYSMOD as a multi-line block. Two shapes
# seen in real output:
#   WA64497   TYPE            = SUPERSEDED       <- TYPE line IS the status
#             LASTSUP         = UJ93389             (no STATUS line follows)
# and:
#   UY88772   TYPE            = PTF               <- TYPE is the real type
#             LASTUPD         = UCLIN    TYPE=UPD    (PTF/APAR/USERMOD/...);
#             STATUS          = REC  BYP  APP        the real status is a
#             FMID            = ETI1106               separate STATUS line.
_SYSMOD_HDR = re.compile(
    r"^\s*([A-Za-z0-9$#@]+)\s+TYPE\s*=\s*([A-Za-z]+)", re.IGNORECASE
)
_SYSMOD_STATUS = re.compile(r"^\s*STATUS\s*=\s*(.+?)\s*$", re.IGNORECASE)


def parse_smplist(path: Path) -> dict[str, Zone]:
    """Parse one SMPLIST.jcl SYSPRINT dump into {zone_name: Zone}."""
    zones: dict[str, Zone] = {}
    current_zone: Zone | None = None
    section = None  # one of None, "DDDEF", "FILE", "SYSMOD"
    pending_modname: str | None = None
    pending_sysmod: str | None = None

    _SECTION_BY_TYPE = {"DDDEF": "DDDEF", "MOD": "FILE", "SYSMOD": "SYSMOD"}

    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.rstrip()

        hdr_match = _SECTION_HDR.match(line)
        if hdr_match:
            zname, rtype = hdr_match.groups()
            section = _SECTION_BY_TYPE[rtype.upper()]
            current_zone = zones.setdefault(zname, Zone(name=zname))
            pending_modname = None
            pending_sysmod = None
            continue

        if _SECTION_DDDEF.search(line):
            section = "DDDEF"
            continue
        if _SECTION_FILE.search(line):
            section = "FILE"
            pending_modname = None
            continue
        if _SECTION_SYSMOD.search(line):
            section = "SYSMOD"
            pending_sysmod = None
            continue

        zone_match = _ZONE_HDR.search(line)
        if zone_match:
            zname = zone_match.group(1)
            current_zone = zones.setdefault(zname, Zone(name=zname))
            continue

        if current_zone is None:
            continue

        if section == "DDDEF":
            dd_match = _DDDEF_ENTRY.match(line)
            if dd_match:
                ddname, dsn = dd_match.groups()
                current_zone.dddefs[ddname] = dsn

        elif section == "FILE":
            mod_match = _FILE_MODULE.match(line)
            if mod_match:
                pending_modname = mod_match.group(1)
                continue
            fmid_match = _FILE_FMID.match(line)
            if fmid_match and pending_modname:
                current_zone.module_fmid[pending_modname] = fmid_match.group(1)
                pending_modname = None

        elif section == "SYSMOD":
            hdr_match = _SYSMOD_HDR.match(line)
            if hdr_match:
                sysmod, sysmod_type = hdr_match.groups()
                # SUPERSEDED entries have no separate STATUS line -- TYPE
                # itself is the status in that case.
                if sysmod_type.upper() == "SUPERSEDED":
                    current_zone.fmid_status[sysmod] = "SUPERSEDED"
                    pending_sysmod = None
                else:
                    pending_sysmod = sysmod
                continue
            status_match = _SYSMOD_STATUS.match(line)
            if status_match and pending_sysmod:
                status = "/".join(status_match.group(1).split())
                current_zone.fmid_status[pending_sysmod] = status.upper()
                pending_sysmod = None

    return zones


def merge_zones(*zone_maps: dict[str, Zone]) -> dict[str, Zone]:
    """Merge multiple {zone_name: Zone} maps (e.g. one per SMPLIST.jcl run)
    into one, combining dddefs/module_fmid for zones reported more than
    once."""
    merged: dict[str, Zone] = {}
    for zmap in zone_maps:
        for name, zone in zmap.items():
            target = merged.setdefault(name, Zone(name=name))
            target.dddefs.update(zone.dddefs)
            target.module_fmid.update(zone.module_fmid)
            target.fmid_status.update(zone.fmid_status)
    return merged
