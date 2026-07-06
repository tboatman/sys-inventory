from pathlib import Path

from inventory import igdsms_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return igdsms_parser.parse_igdsms_snapshot(FIXTURES / "sample_igdsms_snapshot.txt")


def test_single_sms_statement_captured():
    statements = load_statements()
    assert len(statements) == 1
    assert statements[0].stmt == "SMS"


def test_sms_statement_operands_joined_across_continuation_lines():
    statements = load_statements()
    assert statements[0].operands == (
        "ACDS(SYS1.ZDT3.ACDS) COMMDS(SYS1.ZDT3.COMMDS) INTERVAL(15) "
        "DINTERVAL(150) REVERIFY(NO) ACSDEFAULTS(NO) OAMPROC(OAM) "
        "TRACE(ON) SIZE(128K) TYPE(ALL) JOBNAME(*) ASID(*) SELECT(ALL)"
    )


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "IGDSMSTB" for s in statements)
