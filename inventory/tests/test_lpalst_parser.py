from pathlib import Path

from inventory import lpalst_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_entries():
    return lpalst_parser.parse_lpalst_snapshot(FIXTURES / "sample_lpalst_snapshot.txt")


def test_all_entries_captured():
    entries = load_entries()
    assert len(entries) == 18


def test_entry_with_volume_hint():
    entries = load_entries()
    by_dsn = {e.dsn: e.volume for e in entries}
    assert by_dsn["ISM403.SEQALPA"] == "C3PRD1"


def test_entry_without_volume_hint():
    entries = load_entries()
    by_dsn = {e.dsn: e.volume for e in entries}
    assert by_dsn["SYS1.LPALIB"] is None


def test_unresolved_system_symbol_kept_literal():
    entries = load_entries()
    dsns = [e.dsn for e in entries]
    assert "USER.&SYSVER..LPALIB" in dsns


def test_last_entry_with_no_trailing_comma_still_captured():
    entries = load_entries()
    assert entries[-1].dsn == "ISM403.SFEKLPA"
    assert entries[-1].volume == "C3PRD1"


def test_source_member_set_for_every_entry():
    entries = load_entries()
    assert all(e.source_member == "LPALST00" for e in entries)
