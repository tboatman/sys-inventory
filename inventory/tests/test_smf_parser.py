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


def test_source_member_set_correctly_across_concatenated_members():
    statements = load_statements()
    by_member = {"SMFPRM00": 0, "SMFPRM01": 0}
    for s in statements:
        by_member[s.source_member] += 1
    assert by_member == {"SMFPRM00": 5, "SMFPRM01": 15}


def _smfprm01():
    return [s for s in load_statements() if s.source_member == "SMFPRM01"]


def test_real_member_keywords_previously_missing_from_vocabulary():
    # CONFIRMED against a real SMFPRMxx member: REC/MAXDORM/STATUS/JWT/
    # SID/LISTDSN/INTVAL/SYNCVAL/AUTHSETSMF weren't in the original
    # partial vocabulary and would have been folded into NOPROMPT's
    # operands instead of starting their own statements.
    by_stmt = {s.stmt: s.operands for s in _smfprm01()}
    assert by_stmt["NOPROMPT"] == ""
    assert by_stmt["REC"] == "(PERM)"
    assert by_stmt["MAXDORM"] == "(3000)"
    assert by_stmt["STATUS"] == "(010000)"
    assert by_stmt["JWT"] == "(0400)"
    assert by_stmt["SID"] == "(&SYSNAME(1:4))"
    assert by_stmt["LISTDSN"] == ""
    assert by_stmt["INTVAL"] == "(05)"
    assert by_stmt["SYNCVAL"] == "(05)"
    assert by_stmt["AUTHSETSMF"] == ""


def test_real_member_multiline_dsname_joined():
    by_stmt = {s.stmt: s.operands for s in _smfprm01()}
    assert by_stmt["DSNAME"] == "(SYS1.&SYSNAME..MAN1, SYS1.&SYSNAME..MAN2)"


def test_real_member_two_subsys_statements_kept_with_standalone_comment_blocks_stripped():
    # Standalone '/* ... */' comment lines (not trailing on a statement
    # line) sit between and after the SYS/SUBSYS statements -- must
    # disappear entirely, not leak into either SUBSYS's operands.
    subsys = [s.operands for s in _smfprm01() if s.stmt == "SUBSYS"]
    assert len(subsys) == 2
    assert subsys[0] == "(STC,EXITS(IEFU29,IEFUTL,IEFUSI,IEFUJV,IEFACTRT, IEFU83,IEFU84,IEFU85,IEFU86), INTERVAL(000500),NODETAIL)"
    assert subsys[1] == "(TSO, EXITS(IEFACTRT,IEFUSI,IEFUJI,IEFUTL,IEFUJV,IEFU83,IEFU84,IEFU85), INTERVAL(001000),DETAIL)"
    assert all("/*" not in s and "*/" not in s for s in subsys)
