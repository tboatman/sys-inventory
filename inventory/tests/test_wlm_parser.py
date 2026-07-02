from pathlib import Path

from inventory import wlm_parser

FIXTURES = Path(__file__).parent / "fixtures"


def test_policy_name_parsed():
    policy = wlm_parser.parse_wlm(FIXTURES / "sample_wlm.txt")
    assert policy.policy_name == "PROD1"


def test_mode_inferred_as_goal():
    # The real IWM025I reply never contains a "MODE=" token -- mode is
    # inferred as GOAL purely from a policy name being present (WLM
    # compatibility mode is desupported on modern z/OS releases), not
    # parsed from a keyword match. See wlm_parser.py's module docstring.
    policy = wlm_parser.parse_wlm(FIXTURES / "sample_wlm.txt")
    assert policy.mode == "GOAL"


def test_missing_policy_name_returns_none(tmp_path):
    empty = tmp_path / "wlm.txt"
    empty.write_text("SOME UNRELATED TEXT\n")
    assert wlm_parser.parse_wlm(empty) is None
