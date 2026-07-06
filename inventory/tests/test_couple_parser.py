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


def test_source_member_set_correctly_across_concatenated_members():
    statements = load_statements()
    by_member = {"COUPLE00": 0, "COUPLE01": 0}
    for s in statements:
        by_member[s.source_member] += 1
    assert by_member == {"COUPLE00": 2, "COUPLE01": 5}


def test_multiple_data_statements_all_captured_in_order():
    # COUPLE01 -- CONFIRMED against a real COUPLExx member: one COUPLE
    # plus four distinct DATA TYPE(...) statements (CFRM/LOGR/BPXMCDS/
    # WLM), all kept, not collapsed to the last one.
    statements = load_statements()
    couple01 = [s for s in statements if s.source_member == "COUPLE01"]
    assert [s.stmt for s in couple01] == ["COUPLE", "DATA", "DATA", "DATA", "DATA"]
    data_operands = [s.operands for s in couple01 if s.stmt == "DATA"]
    assert data_operands == [
        "TYPE(CFRM) PCOUPLE(SYS1.ADCDPL.CFRM.CDS01) ACOUPLE(SYS1.ADCDPL.CFRM.CDS02)",
        "TYPE(LOGR) PCOUPLE(SYS1.ADCDPL.LOGR.CDS01) ACOUPLE(SYS1.ADCDPL.LOGR.CDS02)",
        "TYPE(BPXMCDS) PCOUPLE(SYS1.ADCDPL.OMVS.CDS01) ACOUPLE(SYS1.ADCDPL.OMVS.CDS02)",
        "TYPE(WLM) PCOUPLE(SYS1.ADCDPL.WLM.CDS01) ACOUPLE(SYS1.ADCDPL.WLM.CDS02)",
    ]
