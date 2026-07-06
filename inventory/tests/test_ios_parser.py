from pathlib import Path

from inventory import ios_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return ios_parser.parse_ios_snapshot(FIXTURES / "sample_ios_snapshot.txt")


def test_all_statements_captured():
    statements = load_statements()
    assert [s.stmt for s in statements] == ["MIH", "HOTIO", "ZHPF"]


def test_mih_and_hotio_operands():
    statements = load_statements()
    mih = next(s for s in statements if s.stmt == "MIH")
    hotio = next(s for s in statements if s.stmt == "HOTIO")
    assert mih.operands == "TIME=00:15:00,DEV=(0100-01FF)"
    assert hotio.operands == "DEV=(0100-01FF),TIME=1000"


def test_zhpf_specification_operands():
    statements = load_statements()
    zhpf = next(s for s in statements if s.stmt == "ZHPF")
    assert zhpf.operands == "YES"


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "IECIOS00" for s in statements)
