from pathlib import Path

from inventory import iggcat_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return iggcat_parser.parse_iggcat_snapshot(FIXTURES / "sample_iggcat_snapshot.txt")


def test_all_keywords_captured_as_one_dict():
    statements = load_statements()
    by_keyword = {s.keyword: s.value for s in statements}
    assert by_keyword == {
        "GDGEXTENDED": "NO",
        "VVDSSPACE": "10,10",
        "NOTIFYEXTENT": "80",
        "TASKMAX": "180",
        "NOSWAP": None,
    }


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "IGGCAT00" for s in statements)


def test_comment_mentioning_a_keyword_is_stripped_not_parsed():
    """The real member's own header comment mentions 'GDGEXTENDED(YES)' as
    prose (documenting why the real value below is set to NO) -- this must
    not produce a second, bogus GDGEXTENDED entry."""
    statements = load_statements()
    gdgextended = [s for s in statements if s.keyword == "GDGEXTENDED"]
    assert len(gdgextended) == 1
    assert gdgextended[0].value == "NO"


def test_bare_keyword_with_no_parens_has_none_value():
    statements = load_statements()
    noswap = next(s for s in statements if s.keyword == "NOSWAP")
    assert noswap.value is None
