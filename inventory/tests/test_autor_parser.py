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
    msgids = [s for s in statements if s.stmt == "MSGID" and s.source_member == "AUTORBN"]
    assert len(msgids) == 2
    assert msgids[0].operands == "(ARC0380A) DELAY(60S) REPLY(CANCEL)"


def test_msgid_with_noautorreply_folded_in():
    statements = load_statements()
    msgids = [s for s in statements if s.stmt == "MSGID" and s.source_member == "AUTORBN"]
    assert msgids[1].operands == "(IEE094D) NOAUTORREPLY"


def test_source_member_set_correctly_across_concatenated_members():
    statements = load_statements()
    by_member = {"AUTORBN": 0, "AUTOR01": 0}
    for s in statements:
        by_member[s.source_member] += 1
    assert by_member == {"AUTORBN": 3, "AUTOR01": 1}


def test_single_line_msgid_with_leading_multiline_comment_block():
    # AUTOR01 -- CONFIRMED against a real AUTORxx member: a multi-line
    # /* ... */ comment block preceding a live (not commented-out)
    # statement must be stripped without corrupting it, and MSGID's full
    # operand list can appear on one physical line (not just spread
    # across continuation lines like AUTORBN's own sample above).
    statements = load_statements()
    msgid = next(s for s in statements if s.source_member == "AUTOR01")
    assert msgid.stmt == "MSGID"
    assert msgid.operands == "(IEFC166D) DELAY(2S) REPLY(Y)"
