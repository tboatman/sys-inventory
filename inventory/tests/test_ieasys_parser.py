from pathlib import Path

from inventory import ieasys_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return ieasys_parser.parse_ieasys_snapshot(FIXTURES / "sample_ieasys_snapshot.txt")


def test_all_keywords_captured_as_one_dict():
    statements = load_statements()
    by_keyword = {s.keyword: s.value for s in statements}
    assert by_keyword == {
        "SSN": "(BN)",
        "CMD": "(BN)",
        "PROD": "(BN)",
        "REAL": "(4096,ONLINE)",
        "CLPA": None,
        "SQA": "(16,32)",
    }


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "IEASYSBN" for s in statements)


def test_last_keyword_captured_even_with_no_trailing_comma():
    # SQA=(16,32) is the last statement in the fixture with no trailing
    # comma -- must not be silently dropped (a real limitation of the
    # Jinja-side regex this module improves on, see its own docstring).
    statements = load_statements()
    assert any(s.keyword == "SQA" for s in statements)


def test_trailing_comment_stripped_and_bare_flag_captured():
    statements = load_statements()
    clpa = next(s for s in statements if s.keyword == "CLPA")
    assert clpa.value is None
