from pathlib import Path

from inventory import vatlst_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load():
    return vatlst_parser.parse_vatlst_snapshot(FIXTURES / "sample_vatlst_snapshot.txt")


def test_vatdef_defaults_captured():
    defaults, _ = load()
    assert len(defaults) == 1
    assert defaults[0].ipluse == "(PRIVATE)"
    assert defaults[0].sysuse == "(PRIVATE)"


def test_volume_entries_captured():
    _, entries = load()
    assert len(entries) == 2
    assert entries[0].volser == "C3SYS1"
    assert entries[0].attribute == "0"
    assert entries[0].percent_full == "0"
    assert entries[0].device_type == "3390"
    assert entries[0].convertible == "Y"


def test_device_type_field_stripped_of_padding():
    _, entries = load()
    assert entries[0].device_type == "3390"
    assert " " not in entries[0].device_type


def test_source_member_set_for_defaults_and_entries():
    defaults, entries = load()
    assert all(d.source_member == "VATLST00" for d in defaults)
    assert all(e.source_member == "VATLST00" for e in entries)
