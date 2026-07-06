from pathlib import Path

from inventory import autor_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return autor_parser.parse_autor_snapshot(FIXTURES / "sample_autor_snapshot.txt")


def test_notifymsgs_captured():
    statements = load_statements()
    notifymsgs = next(s for s in statements if s.stmt == "NOTIFYMSGS")
    assert notifymsgs.operands == "(CONSOLE)"


def test_msgid_with_delay_reply_continuation_lines_folded_in():
    statements = load_statements()
    msgids = [s for s in statements if s.stmt == "MSGID"]
    assert len(msgids) == 2
    assert msgids[0].operands == "(ARC0380A) DELAY(60S) REPLY(CANCEL)"


def test_msgid_with_noautorreply_folded_in():
    statements = load_statements()
    msgids = [s for s in statements if s.stmt == "MSGID"]
    assert msgids[1].operands == "(IEE094D) NOAUTORREPLY"


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "AUTORBN" for s in statements)
