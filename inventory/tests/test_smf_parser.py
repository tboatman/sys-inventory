from pathlib import Path

from inventory import smf_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return smf_parser.parse_smf_snapshot(FIXTURES / "sample_smf_snapshot.txt")


def test_bare_flag_statements_captured_with_empty_operands():
    statements = load_statements()
    active = next(s for s in statements if s.stmt == "ACTIVE")
    noprompt = next(s for s in statements if s.stmt == "NOPROMPT")
    assert active.operands == ""
    assert noprompt.operands == ""


def test_dsname_statement_operands():
    statements = load_statements()
    dsname = next(s for s in statements if s.stmt == "DSNAME")
    assert dsname.operands == "(SYS1.MAN1,SYS1.MAN2)"


def test_sys_and_subsys_statement_operands():
    statements = load_statements()
    sys_stmt = next(s for s in statements if s.stmt == "SYS")
    subsys_stmt = next(s for s in statements if s.stmt == "SUBSYS")
    assert sys_stmt.operands == "(NOTYPE(14:19,62:69,99))"
    assert subsys_stmt.operands == "(STC,NOTYPE(17))"


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "SMFPRM00" for s in statements)
