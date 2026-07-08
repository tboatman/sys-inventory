from pathlib import Path

from inventory import fix_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return fix_parser.parse_fix_snapshot(FIXTURES / "sample_fix_snapshot.txt")


def test_two_include_statements_captured_in_order():
    statements = load_statements()
    assert len(statements) == 2
    assert all(s.stmt == "INCLUDE" for s in statements)


def test_modules_on_same_line_folded_into_include_operands():
    statements = load_statements()
    first = statements[0]
    assert first.operands == "LIBRARY(SYS1.LPALIB) MODULES( IEAVAR00 IEAVAR06 IGC0001G )"


def test_second_include_statement():
    statements = load_statements()
    second = statements[1]
    assert second.operands == "LIBRARY(FFST.V120ESA.SEPWMOD2) MODULES( EPWSTUB )"


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "IEAFIX00" for s in statements)
