from pathlib import Path

from inventory import sched_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return sched_parser.parse_sched_snapshot(FIXTURES / "sample_sched_snapshot.txt")


def test_all_ppt_entries_captured():
    statements = load_statements()
    assert len(statements) == 12
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


def test_source_member_set_correctly_across_concatenated_members():
    statements = load_statements()
    by_member = {"SCHEDBN": 0, "SCHED01": 0}
    for s in statements:
        by_member[s.source_member] += 1
    assert by_member == {"SCHEDBN": 3, "SCHED01": 9}


def test_real_member_trailing_comment_stripped_from_every_continuation_line():
    # SCHED01 -- CONFIRMED against a real SCHEDxx member: every physical
    # line, including each continuation line, has its own trailing
    # '/* ... */' comment that must be stripped without corrupting the
    # PPT entry it belongs to or bleeding into the next entry.
    statements = load_statements()
    sched01 = [s for s in statements if s.source_member == "SCHED01"]
    assert sched01[0].operands == "PGMNAME(OSZSIRIS) KEY(0) SYST"
    assert sched01[1].operands == "PGMNAME(OSZMOSYS) KEY(0) NOCANCEL NOSWAP SYST"
    assert sched01[-1].operands == "PGMNAME(OSZEXEC5) KEY(5)"
    assert all("/*" not in s.operands and "*/" not in s.operands for s in sched01)
