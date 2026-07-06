from pathlib import Path

from inventory import opt_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return opt_parser.parse_opt_snapshot(FIXTURES / "sample_opt_snapshot.txt")


def test_all_keywords_captured_as_one_dict():
    statements = load_statements()
    by_keyword = {s.keyword: s.value for s in statements}
    assert by_keyword == {
        "MCCFXEPR": "YES",
        "MCCAFCTH": "90",
        "CNTRYCD": "1",
    }


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "IEAOPTBN" for s in statements)


def test_last_keyword_captured_even_with_no_trailing_comma():
    statements = load_statements()
    assert any(s.keyword == "CNTRYCD" for s in statements)
