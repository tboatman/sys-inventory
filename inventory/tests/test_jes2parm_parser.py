from pathlib import Path

from inventory import jes2parm_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return jes2parm_parser.parse_dump(FIXTURES / "sample_jes2parm.txt")


def test_all_statements_parsed():
    statements = load_statements()
    stmts = [s.stmt for s in statements]
    assert stmts == ["CKPTDEF", "CKPTSPACE", "FSS", "INIT", "INCLUDE", "NETSRV", "NODE", "SOCKET"]


def test_comment_lines_and_decorative_box_comments_skipped():
    statements = load_statements()
    stmts = [s.stmt for s in statements]
    assert "/*" not in stmts
    assert "CHECKPOINT" not in stmts
    assert "FUNCTIONAL" not in stmts


def test_trailing_same_line_comment_does_not_corrupt_params():
    statements = load_statements()
    ckptspace = next(s for s in statements if s.stmt == "CKPTSPACE")
    assert ckptspace.params == {"BERTNUM": "6500", "BERTWARN": "80"}


def test_nested_paren_value_with_interleaved_comments_captured_whole():
    statements = load_statements()
    ckptdef = next(s for s in statements if s.stmt == "CKPTDEF")
    assert ckptdef.params["CKPT1"] == "(DSNAME=SYS1.BES2.HASPCKPT, VOLSER=BES2W1, INUSE=YES)"
    assert ckptdef.params["DUPLEX"] == "ON"


def test_subscript_only_statement_with_no_live_params_not_dropped():
    statements = load_statements()
    fss = next(s for s in statements if s.stmt == "FSS")
    assert fss.subscript == "PRINTOFF"
    assert fss.params == {}


def test_bare_flag_parameter_captured_with_empty_value():
    statements = load_statements()
    init = next(s for s in statements if s.stmt == "INIT")
    assert init.subscript == "1"
    assert init.params == {"NAME": "1", "CLASS": "QE", "START": ""}


def test_include_statement_captured_generically():
    statements = load_statements()
    include = next(s for s in statements if s.stmt == "INCLUDE")
    assert include.params == {"DSNAME": "SYS1.BES2.PARMLIB(JES2NJE)", "VOLSER": "BES2W1"}


def test_second_member_parsed_with_its_own_source_member():
    statements = load_statements()
    nje_statements = [s for s in statements if s.source_member == "JES2NJE"]
    assert [s.stmt for s in nje_statements] == ["NETSRV", "NODE", "SOCKET"]
    node = next(s for s in nje_statements if s.stmt == "NODE")
    assert node.subscript == "1"
    assert node.params == {"NAME": "SYSP", "PATHMGR": "NO", "NETSRV": "1"}
    socket = next(s for s in nje_statements if s.stmt == "SOCKET")
    assert socket.subscript == "SYSP"
    assert socket.params == {"IPADDR": "SYSP.BMC.COM", "PORT": "175", "NODE": "1"}


def test_first_member_source_member_recorded():
    statements = load_statements()
    assert all(s.source_member == "JES2PARM" for s in statements if s.stmt in {"CKPTDEF", "CKPTSPACE", "FSS", "INIT", "INCLUDE"})
