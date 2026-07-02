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

Every `Zone` parsed from one file is stamped with that file's owning CSI,
via an optional `##CSI <dsn>` sentinel line -- the same `##BLOCKNAME`
convention `sysinfo_parser.py`/`vtam_parser.py` use, just a single value
rather than a whole block. Both producers of `*.smplist.txt`
(`zos-extract/python/smplist.py` and
`ansible/roles/zos_extract/tasks/_smplist_zone.yml`) write this line ahead
of GIMSMP's own report text. A file with no `##CSI` line (e.g. one
captured before this was added) simply leaves `Zone.csi` as `""` --
nothing here requires the sentinel to be present. See `doc/TODO.md`
("8a. Zone.csi field") for why this exists: this site alone has at least
four separate real CSIs (`ansible/output/bes2/smpe_csi_candidates.txt`),
and without this, merging zones from more than one of them loses which
CSI each zone actually belongs to.
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import Zone, ZoneIndexEntry

_CSI_HDR = re.compile(r"^\s*##CSI\s+(\S+)", re.IGNORECASE)
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
    csi_name: str | None = None

    _SECTION_BY_TYPE = {"DDDEF": "DDDEF", "MOD": "FILE", "SYSMOD": "SYSMOD"}

    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.rstrip()

        csi_match = _CSI_HDR.match(line)
        if csi_match:
            csi_name = csi_match.group(1)
            continue

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

    if csi_name:
        for zone in zones.values():
            zone.csi = csi_name

    return zones


def merge_zones(*zone_maps: dict[str, Zone]) -> dict[str, Zone]:
    """Merge multiple {zone_name: Zone} maps (e.g. one per SMPLIST.jcl run)
    into one, combining dddefs/module_fmid for zones reported more than
    once.

    Now that a single ingest can cover more than one CSI (doc/TODO.md
    "8c"), two *different* zones can legitimately share a bare name (e.g.
    two vendor products each define a "TZONE1"). When that's detected --
    same name, but a different non-empty `csi` than what's already merged
    under that name -- the incoming zone is kept under a disambiguated
    key (`"NAME@CSI"`) instead of silently overwriting the first one.
    `Zone(name=name)` is constructed with that same disambiguated string,
    so `resolver._dataset_to_zone()`'s `return zone.name` always yields a
    string that's a valid key back into this dict.

    This only prevents the *zone* entries from colliding -- it does not
    resolve the deeper ambiguity of one physical dataset being claimed by
    more than one zone's DDDEF across different CSIs (a real DSN like
    SYS1.LINKLIB could appear in several sites' CSIs); `_dataset_to_zone`
    still returns the first match it finds, same as before. Flagged, not
    fixed, this round -- see doc/TODO.md ("8c")."""
    merged: dict[str, Zone] = {}
    for zmap in zone_maps:
        for name, zone in zmap.items():
            existing = merged.get(name)
            if existing is not None and existing.csi and zone.csi and existing.csi != zone.csi:
                name = f"{name}@{zone.csi}"
            target = merged.setdefault(name, Zone(name=name))
            target.csi = zone.csi or target.csi
            target.dddefs.update(zone.dddefs)
            target.module_fmid.update(zone.module_fmid)
            target.fmid_status.update(zone.fmid_status)
    return merged

_GLOBALZONE_HDR = re.compile(r"^\s*(\S+)\s+ZONE\s+ENTRIES\b", re.IGNORECASE)
# First ZONEINDEX row is on the same line as the "ZONEINDEX =" label,
# prefixed by the owning (global) zone's own entry name; e.g.:
#   GLOBAL    ZONEINDEX       = DZONE  DLIB    CICS.REL41.DZONE.CSI
_ZONEINDEX_FIRST = re.compile(
    r"^\s*\S+\s+ZONEINDEX\s*=\s*([A-Za-z0-9$#@]+)\s+([A-Za-z]+)\s+(\S+)\s*$",
    re.IGNORECASE,
)
# Further rows are indented continuation lines with no "KEY =" label, just
# the same three tokens again, e.g.:
#                             TZONE   TARGET  CICS.REL41.TZONE.CSI
_ZONEINDEX_CONT = re.compile(r"^\s+([A-Za-z0-9$#@]+)\s+([A-Za-z]+)\s+(\S+)\s*$")


def parse_globalzone(path: Path) -> list[ZoneIndexEntry]:
    """Parse one LIST GLOBALZONE report (see discover_smpe_zones.yml /
    _smplist_globalzone.yml) into ZoneIndexEntry rows -- one per zone
    listed in a CSI's global-zone ZONEINDEX attribute: SMP/E's own
    authoritative census of every zone tied to that CSI, unlike
    discover_smpe_csis.yml's naming-heuristic CSI search.

    Real report shape (a "<name> ZONE ENTRIES" section -- the same
    "<zone> <TYPE> ENTRIES" convention DDDEF/MOD/SYSMOD sections already
    use above, just with ZONE as the type -- containing one GLOBAL-zone
    entry whose ZONEINDEX attribute lists zone name / zone type / owning
    CSI dataset, one per line, first row inline with "ZONEINDEX =" and
    the rest on indented continuation lines with no label) confirmed
    against a real third-party ZOAU/Ansible SMP/E role built against real
    system output (github.com/LuiggiTorricelli/zos_smpe_list's
    filter_plugins/parse_gimsmp.py -- its ZONEINDEX regex expects exactly
    this NAME/TYPE/CSI triple shape), not yet against this site's own
    system -- same "confirmed via third-party reference, not a real reply
    from this shop yet" caveat racf_parser.py's byte offsets carry. Tune
    the regexes above against your real *.smpzones.txt if this comes back
    empty; see doc/TODO.md ("8d") for the full detail.
    """
    csi_name: str | None = None
    entries: list[ZoneIndexEntry] = []
    in_zoneindex = False

    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.rstrip()

        csi_match = _CSI_HDR.match(line)
        if csi_match:
            csi_name = csi_match.group(1)
            continue

        if _GLOBALZONE_HDR.match(line):
            in_zoneindex = False
            continue

        first_match = _ZONEINDEX_FIRST.match(line)
        if first_match:
            zone_name, zone_type, zone_csi = first_match.groups()
            entries.append(ZoneIndexEntry(zone_name, zone_type.upper(), zone_csi, csi_name or ""))
            in_zoneindex = True
            continue

        if in_zoneindex:
            # A line with "=" (or blank) starts a new attribute/entry and
            # ends the ZONEINDEX continuation run.
            if "=" in line or not line.strip():
                in_zoneindex = False
            else:
                cont_match = _ZONEINDEX_CONT.match(line)
                if cont_match:
                    zone_name, zone_type, zone_csi = cont_match.groups()
                    entries.append(ZoneIndexEntry(zone_name, zone_type.upper(), zone_csi, csi_name or ""))
                else:
                    in_zoneindex = False

    return entries
