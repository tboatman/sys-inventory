from pathlib import Path

from inventory import grsrnl_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return grsrnl_parser.parse_grsrnl_snapshot(FIXTURES / "sample_grsrnl_snapshot.txt")


def test_all_rnldef_entries_captured():
    statements = load_statements()
    assert len(statements) == 2
    assert all(s.stmt == "RNLDEF" for s in statements)


def test_specific_rnl_entry_operands():
    statements = load_statements()
    assert statements[0].operands == (
        "RNL(EXCL) TYPE(SPECIFIC) QNAME(SYSIGGV2) RNAME('ICFCAT.CAT1.SHARED')"
    )


def test_generic_rnl_entry_operands():
    statements = load_statements()
    assert statements[1].operands == "RNL(INCL) TYPE(GENERIC) QNAME(SYSDSN)"


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "GRSRNL00" for s in statements)
