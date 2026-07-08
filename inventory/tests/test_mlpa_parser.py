from pathlib import Path

from inventory import mlpa_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return mlpa_parser.parse_mlpa_snapshot(FIXTURES / "sample_mlpa_snapshot.txt")


def test_include_and_modules_captured_as_separate_statements():
    statements = load_statements()
    assert [(s.stmt, s.operands) for s in statements] == [
        ("INCLUDE", "LIBRARY(ADCD.&SYSVER..LINKLIB)"),
        ("MODULES", "(DFSAFMD0, IGC0020B)"),
    ]


def test_unterminated_comment_lines_do_not_pollute_operands():
    # The fixture's trailing '/* ... ' lines never close with '*/'
    # anywhere in the member -- they must not leak into MODULES'
    # operands.
    statements = load_statements()
    modules = next(s for s in statements if s.stmt == "MODULES")
    assert "IGC0020B" in modules.operands
    assert "SVC" not in modules.operands
    assert "DBRC" not in modules.operands


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "IEALPA00" for s in statements)
