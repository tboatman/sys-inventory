from pathlib import Path

from inventory import cics_csdup_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load():
    return cics_csdup_parser.parse_cics_csdup(FIXTURES / "sample_cics_deepening.txt")


def test_definitions_parsed_with_group_carried_forward():
    definitions = load()
    assert [(d.def_type, d.name, d.group, d.csd_dsn) for d in definitions] == [
        ("PROGRAM", "PROG1", "GRP1", "CICS.PROD.DFHCSD"),
        ("TRANSACTION", "TRAN1", "GRP1", "CICS.PROD.DFHCSD"),
        ("FILE", "FILE001", "GRP2", "CICS.PROD.DFHCSD"),
    ]


def test_banner_and_page_lines_not_treated_as_rows():
    definitions = load()
    assert len(definitions) == 3
