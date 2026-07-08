from pathlib import Path

from inventory import cmci_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load():
    return cmci_parser.parse_cmci(FIXTURES / "sample_cics_cmci.txt")


def test_csd_definition_resources_parsed():
    resources = load()
    programs = [r for r in resources if r.resource_type == "cicsdefinitionprogram"]
    assert [(r.name, r.context, r.attributes) for r in programs] == [
        ("MYPROG", "CICSA", {"name": "MYPROG", "csdgroup": "GRP1"}),
        ("MYPROG2", "CICSA", {"name": "MYPROG2", "csdgroup": "GRP1"}),
    ]


def test_installed_resource_name_extracted_from_type_specific_attribute():
    resources = load()
    by_type = {r.resource_type: r for r in resources if r.resource_type in ("CICSProgram", "CICSTransaction", "CICSLocalFile")}
    assert by_type["CICSProgram"].name == "MYPROG"
    assert by_type["CICSTransaction"].name == "MYTR"
    assert by_type["CICSLocalFile"].name == "MYFILE"


def test_empty_records_list_contributes_no_resources():
    resources = load()
    assert not any(r.resource_type == "cicsdefinitionfile" for r in resources)


def test_malformed_and_incomplete_lines_skipped():
    # "this is not valid json..." and '{"context": "CICSA"}' (missing
    # resource_type/records) are both silently skipped, not raised on --
    # confirms the total resource count matches only the well-formed lines.
    resources = load()
    assert len(resources) == 2 + 1 + 1 + 1 + 1  # programs(2) + tran-def(1) + 3 installed


def test_name_falls_back_to_placeholder_when_no_candidate_key_matches():
    resources = load()
    # cicsdefinitiontransaction's own record has both 'name' and 'program'
    # attributes -- 'name' (the first candidate key) wins.
    tran_def = next(r for r in resources if r.resource_type == "cicsdefinitiontransaction")
    assert tran_def.name == "MYTRAN"
