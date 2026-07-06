from pathlib import Path

from inventory import devsup_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return devsup_parser.parse_devsup_snapshot(FIXTURES / "sample_devsup_snapshot.txt")


def test_all_keywords_captured_as_one_dict():
    statements = load_statements()
    by_keyword = {s.keyword: s.value for s in statements}
    assert by_keyword == {
        "COMPACT": "YES",
        "VOLNSNS": "YES",
        "NON_VSAM_XTIOT": "YES",
        "MEDIA1": "BE01",
        "MEDIA2": "BE02",
        "MEDIA3": "BE03",
        "MEDIA4": "BE04",
        "MEDIA5": "BE05",
        "MEDIA6": "BE06",
        "MEDIA7": "BE07",
        "MEDIA8": "BE08",
        "MEDIA9": "BE09",
        "MEDIA10": "BE0A",
        "MEDIA11": "BE0B",
        "MEDIA12": "BE0C",
        "MEDIA13": "BE0D",
        "ERROR": "BE0E",
        "PRIVATE": "BE0F",
        "DISABLE": "(SSR)",
    }


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "DEVSUPBN" for s in statements)


def test_last_keyword_captured_even_with_no_trailing_comma():
    # DISABLE(SSR) is the last statement in the fixture with no trailing
    # comma -- must not be silently dropped, same guarantee
    # flat_keyword_engine() already provides for IEASYSxx.
    statements = load_statements()
    assert any(s.keyword == "DISABLE" for s in statements)


def test_bare_keyword_with_parenthesized_value_and_no_equals():
    # DISABLE(SSR) has no '=' at all -- confirmed against a real
    # DEVSUPxx member to still mean keyword DISABLE, value (SSR), not one
    # bare keyword literally named "DISABLE(SSR)".
    statements = load_statements()
    disable = next(s for s in statements if s.keyword == "DISABLE")
    assert disable.value == "(SSR)"
