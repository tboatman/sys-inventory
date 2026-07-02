from pathlib import Path

from inventory import uss_mounts_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_mounts():
    return uss_mounts_parser.parse_uss_mounts(FIXTURES / "sample_uss_mounts.txt")


def test_all_mounts_parsed():
    mounts = load_mounts()
    assert {m.path for m in mounts} == {"/", "/etc", "/legacy"}


def test_root_mount_fields():
    mounts = load_mounts()
    root = next(m for m in mounts if m.path == "/")
    assert root.name == "OMVS.ROOT.ZFS"
    assert root.fs_type == "ZFS"
    assert root.device == "1"
    assert root.status == "ACTIVE"
    assert root.mode == "RDWR"
    assert root.mounted_date == "06/15/2024"


def test_read_only_mount_mode_parsed():
    mounts = load_mounts()
    legacy = next(m for m in mounts if m.path == "/legacy")
    assert legacy.fs_type == "HFS"
    assert legacy.mode == "READ"


def test_summary_and_header_lines_not_treated_as_mounts():
    mounts = load_mounts()
    assert len(mounts) == 3
