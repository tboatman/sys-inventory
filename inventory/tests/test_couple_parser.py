from pathlib import Path

from inventory import couple_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return couple_parser.parse_couple_snapshot(FIXTURES / "sample_couple_snapshot.txt")


def test_couple_statement_with_continuation_lines_folded_in():
    statements = load_statements()
    couple = next(s for s in statements if s.stmt == "COUPLE")
    assert couple.operands == (
        "SYSPLEX(PLEX1) PCOUPLE(SYS1.XCF.CDS01,VOL001) ACOUPLE(SYS1.XCF.CDS02,VOL002)"
    )


def test_data_statement_with_continuation_lines_folded_in():
    statements = load_statements()
    data = next(s for s in statements if s.stmt == "DATA")
    assert data.operands == (
        "TYPE(LOGR) PCOUPLE(SYS1.LOGR.CDS01,VOL001) ACOUPLE(SYS1.LOGR.CDS02,VOL002)"
    )


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "COUPLE00" for s in statements)
