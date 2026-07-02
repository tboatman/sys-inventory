from pathlib import Path

from inventory import wlm_parser

FIXTURES = Path(__file__).parent / "fixtures"


def test_policy_name_and_mode_parsed():
    policy = wlm_parser.parse_wlm(FIXTURES / "sample_wlm.txt")
    assert policy.policy_name == "WLMPOL01"
    assert policy.mode == "GOAL"


def test_missing_policy_name_returns_none(tmp_path):
    empty = tmp_path / "wlm.txt"
    empty.write_text("SOME UNRELATED TEXT\n")
    assert wlm_parser.parse_wlm(empty) is None
