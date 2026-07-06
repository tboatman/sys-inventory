from pathlib import Path

from inventory import clock_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return clock_parser.parse_clock_snapshot(FIXTURES / "sample_clock_snapshot.txt")


def test_all_keywords_captured_as_one_dict():
    statements = load_statements()
    by_keyword = {s.keyword: s.value for s in statements}
    assert by_keyword == {
        "ETRMODE": "YES",
        "ETRZONE": "00",
        "TIMEZONE": "W05.00.00",
    }


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "CLOCKBN" for s in statements)


def test_last_keyword_captured_even_with_no_trailing_comma():
    statements = load_statements()
    assert any(s.keyword == "TIMEZONE" for s in statements)
