from pathlib import Path

from inventory import diag_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return diag_parser.parse_diag_snapshot(FIXTURES / "sample_diag_snapshot.txt")


def test_two_vsm_statements_captured_in_order():
    statements = load_statements()
    assert [(s.stmt, s.operands) for s in statements] == [
        ("VSM", "TRACK CSA(ON) SQA(ON)"),
        ("VSM", "TRACE GETFREE(OFF)"),
    ]


def test_sequence_numbers_stripped_from_operands():
    statements = load_statements()
    for s in statements:
        assert "01350000" not in s.operands
        assert "01400000" not in s.operands


def test_comment_header_with_sequence_numbers_produces_no_bogus_statements():
    statements = load_statements()
    assert len(statements) == 2


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "DIAG00" for s in statements)
