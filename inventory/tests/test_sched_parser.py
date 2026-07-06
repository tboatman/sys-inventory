from pathlib import Path

from inventory import sched_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return sched_parser.parse_sched_snapshot(FIXTURES / "sample_sched_snapshot.txt")


def test_all_ppt_entries_captured():
    statements = load_statements()
    assert len(statements) == 3
    assert all(s.stmt == "PPT" for s in statements)


def test_simple_ppt_entry_operands():
    statements = load_statements()
    assert statements[0].operands == "PGMNAME(IEDQTCAM) NOSWAP KEY(1) SYST"
    assert statements[1].operands == "PGMNAME(ZWESIS01) KEY(4) NOSWAP"


def test_continuation_line_folded_into_current_ppt_entry():
    statements = load_statements()
    assert statements[2].operands == (
        "PGMNAME(XGMMAIN) CANCEL KEY(4) NOSYST PRIV NOSWAP DSI PASS AFF(NONE) NOPREF"
    )


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "SCHEDBN" for s in statements)
