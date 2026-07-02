from pathlib import Path

from inventory import parmlib_parser

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_parmlib_snapshot_reads_all_entries():
    datasets = parmlib_parser.parse_parmlib_snapshot(FIXTURES / "sample_parmlib_snapshot.txt")
    assert len(datasets) == 3

    first, second, third = datasets
    assert first.entry == "1"
    assert first.flags == "S"
    assert first.volume == "HCD000"
    assert first.dsn == "SYS1.COMMON.PARMLIB"

    assert second.entry == "2"
    assert second.flags == "S"
    assert second.volume == "BES2W1"
    assert second.dsn == "SYS3.BES2.PARMLIB"

    assert third.entry == "3"
    assert third.flags == "D"
    assert third.volume == "BES2W1"
    assert third.dsn == "SYS3.BES2.LOCAL.PARMLIB"


def test_parse_parmlib_snapshot_skips_banner_and_header_lines():
    # The IEE250I banner and FORMAT:/ENTRY header lines don't start with a
    # numeric entry, so they must not be mistaken for data rows.
    datasets = parmlib_parser.parse_parmlib_snapshot(FIXTURES / "sample_parmlib_snapshot.txt")
    assert all(d.dsn.endswith("PARMLIB") for d in datasets)
