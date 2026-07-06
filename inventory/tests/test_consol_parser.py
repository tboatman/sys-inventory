from pathlib import Path

from inventory import consol_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return consol_parser.parse_consol_snapshot(FIXTURES / "sample_consol_snapshot.txt")


def test_all_statements_captured():
    statements = load_statements()
    assert len(statements) == 9
    assert [s.stmt for s in statements] == [
        "INIT", "DEFAULT", "CONSOLE", "CONSOLE", "CONSOLE", "CONSOLE", "CONSOLE", "CONSOLE", "HARDCOPY",
    ]


def test_init_statement_with_quote_char_value_and_continuation_lines():
    # CMDDELIM(") -- the value is itself a literal quote character inside
    # the parens; must not confuse the parser or get treated as an
    # unterminated string.
    statements = load_statements()
    init = statements[0]
    assert init.operands == (
        'CMDDELIM(") MLIM(1500) APPLID(SMCS&SYSCLONE.) MONITOR(DSNAME) '
        "MPF(00) PFK(00) RLIM(10) UEXIT(N) CNGRP(00) AMRF(N)"
    )


def test_default_statement():
    statements = load_statements()
    default = next(s for s in statements if s.stmt == "DEFAULT")
    assert default.operands == "ROUTCODE(ALL)"


def test_multiple_console_statements_all_captured_in_order():
    statements = load_statements()
    consoles = [s.operands for s in statements if s.stmt == "CONSOLE"]
    assert len(consoles) == 6
    assert consoles[0].startswith("DEVNUM(SMCS)")
    assert consoles[1].startswith("DEVNUM(700)")
    assert consoles[-1] == "DEVNUM(SUBSYSTEM) AUTH(ALL) NAME(S908)"


def test_console_statement_with_keywords_sharing_the_console_line():
    # CONSOLE   DEVNUM(SYSCONS) LEVEL(ALL) -- unlike the other CONSOLE
    # entries, this one's first keywords share the CONSOLE line itself
    # rather than all starting on a continuation line.
    statements = load_statements()
    consoles = [s.operands for s in statements if s.stmt == "CONSOLE"]
    assert consoles[3] == "DEVNUM(SYSCONS) LEVEL(ALL) NAME(HWCI) AUTH(MASTER) ROUTCODE(ALL)"


def test_hardcopy_statement():
    statements = load_statements()
    hardcopy = next(s for s in statements if s.stmt == "HARDCOPY")
    assert hardcopy.operands == "DEVNUM(SYSLOG,OPERLOG) CMDLEVEL(CMDS) ROUTCODE(ALL)"


def test_trailing_comment_block_stripped():
    statements = load_statements()
    hardcopy = next(s for s in statements if s.stmt == "HARDCOPY")
    assert "END OF CONSOLE" not in hardcopy.operands


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "CONSOL00" for s in statements)
