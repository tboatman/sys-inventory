from pathlib import Path

from inventory import ieasvc_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return ieasvc_parser.parse_ieasvc_snapshot(FIXTURES / "sample_ieasvc_snapshot.txt")


def test_commented_out_example_produces_no_statements():
    # The fixture's header includes a real IEASVCxx member's own
    # documented sample statement, wrapped in '/* ... */' -- it confirms
    # the real syntax but must not itself produce a live row.
    statements = load_statements()
    assert all(s.svc_number != "254" for s in statements)


def test_two_live_svcparm_statements_captured():
    statements = load_statements()
    assert len(statements) == 2
    assert [s.svc_number for s in statements] == ["200", "201"]


def test_bare_keyword_and_paren_value_params_captured():
    statements = load_statements()
    first = statements[0]
    assert first.stmt == "SVCPARM"
    assert first.params == {"REPLACE": "", "TYPE": "(3)", "APF": "(YES)"}


def test_statement_with_single_param():
    statements = load_statements()
    second = statements[1]
    assert second.svc_number == "201"
    assert second.params == {"TYPE": "(1)"}


def test_sequence_numbers_stripped_from_params():
    statements = load_statements()
    for s in statements:
        assert "00020001" not in str(s.params)
        assert "00020002" not in str(s.params)


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "IEASVC00" for s in statements)
