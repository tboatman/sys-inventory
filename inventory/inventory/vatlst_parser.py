"""Parse active VATLSTxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/vatlst_snapshot.yml) into
VatlstDefaults/VatlstEntry records -- the volume attribute list, named
by IEASYSxx's own VAL= keyword (see ieasys_parser.py) the same way
MLPA=/FIX= name IEALPAxx/IEAFIXxx (see mlpa_parser.py's module
docstring for the full IEASYSxx keyword chain).

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active VATLSTxx member.

Statement syntax: the second Category E (positional/list) shape from
doc/TODO.md "9.2" -- CONFIRMED against a real VATLSTxx member. One
`VATDEF` statement (`VATDEF IPLUSE(attr),SYSUSE(attr)`, a flat
KEYWORD(value) pair reused via parmlib_engines.split_params()) followed
by one comma-separated positional row per volume:

    VATDEF IPLUSE(PRIVATE),SYSUSE(PRIVATE)
    C3SYS1,0,0,3390    ,Y
    C3DBAR,0,0,3390    ,Y

Fields per volume row: volser, attribute (a numeric code -- 0 in the
confirming member's rows, not the PRIVATE/PUBLIC/STORAGE word VATDEF's
own IPLUSE/SYSUSE use), percent-full threshold, device type (padded
with trailing spaces in the real member), and a Y/N convertible flag.
Not KEYWORD=value at all, so this gets its own small dedicated parser
rather than either shared parmlib_engines.py engine, the same as
LpalstEntry.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import VatlstDefaults, VatlstEntry
from .parmlib_engines import split_params, strip_comments


def parse_member(name: str, raw_lines: list[str]) -> tuple[list[VatlstDefaults], list[VatlstEntry]]:
    defaults: list[VatlstDefaults] = []
    entries: list[VatlstEntry] = []
    text = strip_comments("\n".join(raw_lines))
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith("VATDEF"):
            params = split_params(stripped[len("VATDEF"):].strip())
            defaults.append(
                VatlstDefaults(
                    ipluse=params.get("IPLUSE"),
                    sysuse=params.get("SYSUSE"),
                    source_member=name,
                )
            )
            continue
        fields = [f.strip() for f in stripped.split(",")]
        if len(fields) < 5:
            continue
        volser, attribute, percent_full, device_type, convertible = fields[:5]
        entries.append(
            VatlstEntry(
                volser=volser,
                attribute=attribute,
                percent_full=percent_full,
                device_type=device_type,
                convertible=convertible,
                source_member=name,
            )
        )
    return defaults, entries


def parse_vatlst_snapshot(path: Path) -> tuple[list[VatlstDefaults], list[VatlstEntry]]:
    """Parse one vatlst_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active VATLSTxx member's raw content) into
    (VatlstDefaults, VatlstEntry) rows."""
    text = path.read_text(errors="replace")
    defaults: list[VatlstDefaults] = []
    entries: list[VatlstEntry] = []
    for name, raw_lines in split_members(text).items():
        member_defaults, member_entries = parse_member(name, raw_lines)
        defaults.extend(member_defaults)
        entries.extend(member_entries)
    return defaults, entries
