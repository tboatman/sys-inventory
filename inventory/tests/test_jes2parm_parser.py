from pathlib import Path

from inventory import jes2parm_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return jes2parm_parser.parse_dump(FIXTURES / "sample_jes2parm.txt")


def test_all_statements_parsed():
    statements = load_statements()
    stmts = [s.stmt for s in statements]
    assert stmts == ["MASDEF", "JOBCLASS", "JOBDEF", "OUTCLASS"]


def test_comment_line_skipped():
    statements = load_statements()
    assert all(s.stmt != "/*" for s in statements)


def test_continuation_joined_across_lines():
    statements = load_statements()
    masdef = next(s for s in statements if s.stmt == "MASDEF")
    assert masdef.subscript is None
    assert masdef.params == {"OWNMASN": "1", "NAME": "NJE1"}
    assert masdef.source_member == "JES2PARM"


def test_subscript_parsed():
    statements = load_statements()
    jobclass = next(s for s in statements if s.stmt == "JOBCLASS")
    assert jobclass.subscript == "1"
    assert jobclass.params == {"JOBPRTY": "16", "COMMAND": "NO"}


def test_parenthesized_value_not_split_on_inner_commas():
    statements = load_statements()
    jobdef = next(s for s in statements if s.stmt == "JOBDEF")
    assert jobdef.params["JOBNUM"] == "(999,999,1)"
    assert jobdef.params["RESTART"] == "YES"


def test_outclass_subscript_and_params():
    statements = load_statements()
    outclass = next(s for s in statements if s.stmt == "OUTCLASS")
    assert outclass.subscript == "A"
    assert outclass.params == {"QUEUE": "YES", "BURST": "YES"}
