from pathlib import Path

from inventory import grscnf_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return grscnf_parser.parse_grscnf_snapshot(FIXTURES / "sample_grscnf_snapshot.txt")


def test_single_grsdef_statement_captured():
    statements = load_statements()
    assert len(statements) == 1
    assert statements[0].stmt == "GRSDEF"


def test_commented_out_subparameters_are_stripped_not_captured():
    """The real member comments out every sub-parameter except GRSQ (to
    document defaulted/removed settings) -- those must not leak into the
    operand text."""
    statements = load_statements()
    operands = statements[0].operands
    assert "GRSQ(LOCAL)" in operands
    for commented in ("GRSQ(CONTENTION)", "RESMIL", "TOLINT", "ACCELSYS", "RESTART", "REJOIN", "CTRACE"):
        assert commented not in operands


def test_source_member_set():
    statements = load_statements()
    assert statements[0].source_member == "GRSCNF00"
