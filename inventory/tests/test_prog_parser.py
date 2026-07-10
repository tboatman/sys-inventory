from pathlib import Path

from inventory import prog_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return prog_parser.parse_prog_snapshot(FIXTURES / "sample_prog_snapshot.txt")


def test_total_statement_count():
    statements = load_statements()
    assert len(statements) == 193


def test_apf_and_lnklst_counts():
    statements = load_statements()
    apf = [s for s in statements if s.stmt == "APF"]
    lnklst = [s for s in statements if s.stmt == "LNKLST"]
    assert len(apf) == 122
    assert len(lnklst) == 71


def test_apf_format_statement_is_its_own_row():
    statements = load_statements()
    assert statements[0].stmt == "APF"
    assert statements[0].operands == "FORMAT(DYNAMIC)"


def test_two_line_apf_add_entry_joins_continuation():
    statements = load_statements()
    linklib = next(s for s in statements if s.stmt == "APF" and "SYS1.LINKLIB" in s.operands)
    assert linklib.operands == "ADD DSNAME(SYS1.LINKLIB) VOLUME(******)"


def test_one_line_apf_add_entry():
    statements = load_statements()
    mqseries = next(s for s in statements if s.stmt == "APF" and "MQSERIES" in s.operands)
    assert mqseries.operands == "ADD DSNAME(MQS.MQSERIES.LOADLIB) SMS"


def test_lnklst_define_and_activate_are_their_own_rows():
    statements = load_statements()
    lnklst = [s for s in statements if s.stmt == "LNKLST"]
    assert lnklst[0].operands == "DEFINE NAME(LNKLSTBN)"
    assert lnklst[-1].operands == "ACTIVATE NAME(LNKLSTBN)"


def test_inline_comment_on_lnklst_add_does_not_leak_into_operands():
    """A real entry has a trailing '/* STROBE */' comment on the same
    line as its own statement text, continuing onto the next line for
    its DSNAME/VOLSER -- the comment must not appear in the operands."""
    statements = load_statements()
    strobe = next(s for s in statements if s.stmt == "LNKLST" and "SSTRAUTH" in s.operands)
    assert "STROBE" not in strobe.operands
    assert strobe.operands == "ADD NAME(LNKLSTBN) DSNAME(CSGI.CW.&GAMNTSB..SBR21.SSTRAUTH) VOLSER(ABCHR1)"


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "PROG00" for s in statements)
