"""Parse the RACF database unload produced by zos-extract/python/extrracf.py
(IRRDBU00's OUTDD, captured verbatim) into RacfUser/RacfGroup/
RacfGroupConnection/DatasetProfile/DatasetAccess/GeneralResourceProfile/
GeneralResourceAccess records.

*** IMPLEMENTATION ONLY -- NOT YET VALIDATED AGAINST A REAL UNLOAD ***

Format: each line starts with a 4-character record-type code, and fields
are at FIXED BYTE OFFSETS -- not delimiter-split. This matters: several
fields (INSTALL_DATA in particular, a 255-byte installation-defined free
text field present in multiple record types) can legally contain a colon
character, so a naive `line.split(":")` would silently corrupt every field
after the first embedded colon in that record. Byte-offset slicing avoids
that entirely.

IBM's own IRRDBU00 documentation pages return HTTP 403 to automated
fetches (the same recurring issue as ibm.com/docs elsewhere in this
project), so the byte offsets below were verified against a real, working,
field-labeled third-party parser instead: github.com/s1th/racf (racf.pl,
Perl), fetched and cross-checked field-by-field while writing this -- same
methodology already used for the ZOAU/IDCAMS research in catalog_parser.py.

One inconsistency was found in that reference and NOT copied verbatim: in
0500 (GENERAL RESOURCE BASIC DATA), the reference script reads both
READ_CNT and UACC from the same offset (330), which is almost certainly a
bug in that shop's own script rather than a genuine RACF field overlap.
This module instead infers UACC's offset as the next 8-byte field after
READ_CNT (336), which arithmetically lines up exactly with the next
confirmed field (AUDIT_LEVEL at 345: 336 + 8-byte UACC + 1-byte separator
= 345) -- but this ONE field is flagged here as still unconfirmed against
real output. If GeneralResourceProfile.universal_access looks wrong
against your real system's unload, this offset is the first thing to
check.

Record types kept (others are skipped): 0100 (GROUP BASIC DATA), 0200
(USER BASIC DATA), 0205 (USER CONNECT DATA), 0400 (DATASET BASIC DATA),
0404 (DATASET ACCESS), 0500 (GENERAL RESOURCE BASIC DATA), 0505 (GENERAL
RESOURCE ACCESS). 0101/0102/0203 (subgroup/group-member/bare
user-group-connection records) are deliberately not modeled -- 0205 is a
superset for this dimension's purpose, already implying membership plus
the group-scoped SPECIAL/OPERATIONS/AUDITOR/revoked attributes that are
the actually security-relevant part.

General-resource records (0500/0505) are further filtered to
CURATED_CLASSES: IRRDBU00 itself has no selective-unload option (one run
always dumps the ENTIRE database across every class), so this curation
happens off-host here, not at extraction time. Edit CURATED_CLASSES to
add classes relevant to your shop.
"""
from __future__ import annotations

from pathlib import Path

from .models import (
    DatasetAccess,
    DatasetProfile,
    GeneralResourceAccess,
    GeneralResourceProfile,
    RacfGroup,
    RacfGroupConnection,
    RacfSnapshot,
    RacfUser,
)

CURATED_CLASSES = (
    "SURROGAT",  # job submission under another userid
    "JESJOBS",   # job submit/cancel authority by class
    "FACILITY",  # broad catch-all, incl. BPX.SUPERUSER
    "OPERCMDS",  # MVS console command authority
    "STARTED",   # started-task RACF identity -- extends the started_tasks dimension
    "SERVAUTH",  # TCP/IP network resource access
    "APPL",      # VTAM application security
    "DSNR",      # DB2 subsystem resource class
)


def _f(line: str, start: int, length: int) -> str:
    return line[start:start + length].strip()


def _yn(value: str) -> bool | None:
    if value == "YES":
        return True
    if value == "NO":
        return False
    return None


def _parse_group(line: str) -> RacfGroup:
    return RacfGroup(
        name=_f(line, 5, 8),
        superior_group=_f(line, 14, 8) or None,
        owner=_f(line, 34, 8) or None,
        universal_access=_f(line, 43, 8) or None,
        description=_f(line, 57, 255) or None,
    )


def _parse_user(line: str) -> RacfUser:
    attribs = _f(line, 541, 8)
    return RacfUser(
        userid=_f(line, 5, 8),
        name=_f(line, 74, 20) or None,
        owner=_f(line, 25, 8) or None,
        default_group=_f(line, 95, 8) or None,
        special=_yn(_f(line, 39, 4)),
        operations=_yn(_f(line, 44, 4)),
        auditor=_yn(_f(line, 385, 4)),
        revoked=_yn(_f(line, 49, 4)),
        restricted=True if "RSTD" in attribs else (False if attribs else None),
    )


def _parse_group_connection(line: str) -> RacfGroupConnection:
    return RacfGroupConnection(
        userid=_f(line, 5, 8),
        group=_f(line, 14, 8),
        group_special=_yn(_f(line, 83, 4)),
        group_operations=_yn(_f(line, 88, 4)),
        group_auditor=_yn(_f(line, 108, 4)),
        group_universal_access=_f(line, 63, 8) or None,
        revoked_in_group=_yn(_f(line, 93, 4)),
    )


def _parse_dataset_profile(line: str) -> DatasetProfile:
    return DatasetProfile(
        profile=_f(line, 5, 44),
        volume=_f(line, 50, 6) or None,
        generic=_yn(_f(line, 57, 4)),
        owner=_f(line, 73, 8) or None,
        universal_access=_f(line, 128, 8) or None,
        audit_level=_f(line, 142, 8) or None,
    )


def _parse_dataset_access(line: str) -> DatasetAccess:
    return DatasetAccess(
        profile=_f(line, 5, 44),
        auth_id=_f(line, 57, 8),
        access=_f(line, 66, 8) or None,
    )


def _parse_general_resource_profile(line: str) -> GeneralResourceProfile:
    return GeneralResourceProfile(
        profile=_f(line, 5, 246),
        class_name=_f(line, 252, 8),
        owner=_f(line, 281, 8) or None,
        universal_access=_f(line, 336, 8) or None,  # unconfirmed, see module docstring
        audit_level=_f(line, 345, 8) or None,
    )


def _parse_general_resource_access(line: str) -> GeneralResourceAccess:
    return GeneralResourceAccess(
        profile=_f(line, 5, 246),
        class_name=_f(line, 252, 8),
        auth_id=_f(line, 261, 8),
        access=_f(line, 270, 8) or None,
    )


def parse_racf(path: Path) -> RacfSnapshot:
    """Parse one extrracf.py IRRDBU00 unload dump into a RacfSnapshot."""
    snapshot = RacfSnapshot()

    for raw_line in path.read_text(errors="replace").splitlines():
        if len(raw_line) < 4:
            continue
        rec_type = raw_line[0:4]

        if rec_type == "0100":
            snapshot.groups.append(_parse_group(raw_line))
        elif rec_type == "0200":
            snapshot.users.append(_parse_user(raw_line))
        elif rec_type == "0205":
            snapshot.group_connections.append(_parse_group_connection(raw_line))
        elif rec_type == "0400":
            snapshot.dataset_profiles.append(_parse_dataset_profile(raw_line))
        elif rec_type == "0404":
            snapshot.dataset_access.append(_parse_dataset_access(raw_line))
        elif rec_type == "0500":
            profile = _parse_general_resource_profile(raw_line)
            if profile.class_name in CURATED_CLASSES:
                snapshot.general_resource_profiles.append(profile)
        elif rec_type == "0505":
            access = _parse_general_resource_access(raw_line)
            if access.class_name in CURATED_CLASSES:
                snapshot.general_resource_access.append(access)

    return snapshot
