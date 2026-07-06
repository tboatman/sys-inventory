from pathlib import Path

from inventory import devsup_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return devsup_parser.parse_devsup_snapshot(FIXTURES / "sample_devsup_snapshot.txt")


def test_all_keywords_captured_as_one_dict():
    statements = load_statements()
    by_keyword = {s.keyword: s.value for s in statements}
    assert by_keyword == {
        "RTYPTABL": "DTRT00",
        "LOWAD": "YES",
        "IZBGENQ": "NO",
        "ITASKID": "NO",
        "QTIP": "(600,50)",
    }


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "DEVSUPBN" for s in statements)


def test_last_keyword_captured_even_with_no_trailing_comma():
    # QTIP=(600,50) is the last statement in the fixture with no trailing
    # comma -- must not be silently dropped, same guarantee
    # flat_keyword_engine() already provides for IEASYSxx.
    statements = load_statements()
    assert any(s.keyword == "QTIP" for s in statements)


def test_trailing_comment_stripped():
    statements = load_statements()
    lowad = next(s for s in statements if s.keyword == "LOWAD")
    assert lowad.value == "YES"
