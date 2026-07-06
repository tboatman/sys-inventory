from pathlib import Path

from inventory import grsrnl_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return grsrnl_parser.parse_grsrnl_snapshot(FIXTURES / "sample_grsrnl_snapshot.txt")


def test_all_rnldef_entries_captured():
    statements = load_statements()
    assert all(s.stmt == "RNLDEF" for s in statements)


def test_specific_rnl_entry_operands():
    statements = load_statements()
    grsrnl00 = [s for s in statements if s.source_member == "GRSRNL00"]
    assert grsrnl00[0].operands == (
        "RNL(EXCL) TYPE(SPECIFIC) QNAME(SYSIGGV2) RNAME('ICFCAT.CAT1.SHARED')"
    )


def test_generic_rnl_entry_operands():
    statements = load_statements()
    grsrnl00 = [s for s in statements if s.source_member == "GRSRNL00"]
    assert grsrnl00[1].operands == "RNL(INCL) TYPE(GENERIC) QNAME(SYSDSN)"


def test_source_member_set_correctly_across_concatenated_members():
    statements = load_statements()
    by_member = {"GRSRNL00": 0, "GRSRNL01": 0}
    for s in statements:
        by_member[s.source_member] += 1
    assert by_member == {"GRSRNL00": 2, "GRSRNL01": 5}


def test_real_member_qname_rname_on_own_continuation_lines():
    # GRSRNL01 -- CONFIRMED against a real (partial) GRSRNLxx member:
    # unlike the GRSRNL00 sample above, QNAME(...)/RNAME(...) each sit on
    # their own physical line rather than sharing the RNLDEF line, with a
    # blank line separating entries -- both must fold/skip correctly.
    statements = load_statements()
    grsrnl01 = [s for s in statements if s.source_member == "GRSRNL01"]
    assert len(grsrnl01) == 5
    assert grsrnl01[0].operands == "RNL(EXCL) TYPE(SPECIFIC) QNAME(SYSDSN) RNAME(PASSWORD)"
    assert grsrnl01[1].operands == "RNL(EXCL) TYPE(SPECIFIC) QNAME(SYSDSN) RNAME(SYS1.BRODCAST)"
    assert grsrnl01[3].operands == "RNL(EXCL) TYPE(SPECIFIC) QNAME(SYSDSN) RNAME(SYS1.DCMLIB)"


def test_real_member_trailing_incomplete_entry_kept_as_is():
    # The real sample was itself pasted partial/truncated -- its last
    # RNLDEF entry has no QNAME/RNAME. The parser doesn't validate
    # completeness, it just captures whatever operand text is there.
    statements = load_statements()
    grsrnl01 = [s for s in statements if s.source_member == "GRSRNL01"]
    assert grsrnl01[-1].operands == "RNL(EXCL) TYPE(GENERIC)"
