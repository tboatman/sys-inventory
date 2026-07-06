from pathlib import Path

from inventory import bpxprm_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return bpxprm_parser.parse_bpxprm_snapshot(FIXTURES / "sample_bpxprm_snapshot.txt")


def test_multiline_statements_fold_continuation_into_operands():
    statements = load_statements()
    by_stmt = {s.stmt: s.operands for s in statements if s.source_member == "BPXPRM00"}

    assert by_stmt["ROOT"] == "FILESYSTEM('OMVS.ROOT.ZFS') TYPE(ZFS) MODE(RDWR)"
    assert by_stmt["MOUNT"] == "FILESYSTEM('OMVS.ETC.ZFS') MOUNTPOINT('/etc') TYPE(ZFS) MODE(RDWR)"


def test_scalar_statement_with_no_space_before_paren():
    # MAXPROCSYS(3000) has no space between the keyword and its value --
    # a real shape the naive "split on first space" approach would get
    # wrong (see the module's own _STMT_START comment).
    statements = load_statements()
    maxprocsys = next(s for s in statements if s.stmt == "MAXPROCSYS")
    assert maxprocsys.operands == "(3000)"


def test_trailing_comment_stripped():
    statements = load_statements()
    maxprocsys = next(s for s in statements if s.stmt == "MAXPROCSYS")
    assert "max processes" not in maxprocsys.operands


def test_last_statement_captured():
    statements = load_statements()
    tz = next(s for s in statements if s.stmt == "TZ")
    assert tz.operands == "(EST5EDT)"


def test_source_member_set_correctly_across_concatenated_members():
    statements = load_statements()
    by_member = {"BPXPRM00": 0, "BPXPRM01": 0}
    for s in statements:
        by_member[s.source_member] += 1
    assert by_member == {"BPXPRM00": 4, "BPXPRM01": 2}


def test_four_statements_total():
    statements = load_statements()
    assert {s.stmt for s in statements} == {"ROOT", "MOUNT", "MAXPROCSYS", "TZ"}


def test_multiple_mount_statements_all_captured():
    # BPXPRM01 -- CONFIRMED against a real BPXPRMxx member: two real
    # MOUNT statements, in order, both kept (not collapsed/overwritten).
    statements = load_statements()
    mounts = [s.operands for s in statements if s.source_member == "BPXPRM01" and s.stmt == "MOUNT"]
    assert mounts == [
        "FILESYSTEM('ZFS.TOMMY') MOUNTPOINT('/u/tommy') TYPE(ZFS) NOAUTOMOVE",
        "FILESYSTEM('ZFS.GRB') MOUNTPOINT('/usr/lpp/grb') TYPE(ZFS)",
    ]


def test_fully_commented_out_statement_block_excluded():
    # The commented-out MOUNT('TOMMY.PSI.ZFS') block in BPXPRM01 -- every
    # physical line is its own '/* ... */' comment -- must disappear
    # entirely, not become a third MOUNT or leak 'PSI' into another
    # statement's operands.
    statements = load_statements()
    mount_operands = " ".join(s.operands for s in statements if s.source_member == "BPXPRM01" and s.stmt == "MOUNT")
    assert "PSI" not in mount_operands
