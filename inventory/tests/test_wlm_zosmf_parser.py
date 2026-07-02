import json
from pathlib import Path

from inventory import wlm_zosmf_parser

FIXTURES = Path(__file__).parent / "fixtures"


def test_entries_parsed_from_policies_key():
    entries = wlm_zosmf_parser.parse_wlm_zosmf(FIXTURES / "sample_wlm_zosmf.txt")
    names = {e.name for e in entries}
    assert names == {"WLMPOL01", "WLMPOL02"}


def test_raw_json_preserved_verbatim():
    entries = wlm_zosmf_parser.parse_wlm_zosmf(FIXTURES / "sample_wlm_zosmf.txt")
    pol01 = next(e for e in entries if e.name == "WLMPOL01")
    assert pol01.raw["description"] == "Standard goal-mode policy"
    assert pol01.raw["service_classes"] == [
        {"name": "SYSSTC", "importance": 1},
        {"name": "PRODBAT", "importance": 2},
    ]


def test_bare_list_response_supported(tmp_path):
    dump = tmp_path / "wlm_zosmf.txt"
    dump.write_text(json.dumps([{"name": "A"}, {"name": "B"}]))
    entries = wlm_zosmf_parser.parse_wlm_zosmf(dump)
    assert {e.name for e in entries} == {"A", "B"}


def test_single_object_response_wrapped_as_one_entry(tmp_path):
    dump = tmp_path / "wlm_zosmf.txt"
    dump.write_text(json.dumps({"policyName": "SOLO", "mode": "GOAL"}))
    entries = wlm_zosmf_parser.parse_wlm_zosmf(dump)
    assert len(entries) == 1
    assert entries[0].name == "SOLO"
    assert entries[0].raw == {"policyName": "SOLO", "mode": "GOAL"}


def test_missing_name_keys_fall_back_to_unknown(tmp_path):
    dump = tmp_path / "wlm_zosmf.txt"
    dump.write_text(json.dumps([{"unexpected_field": 1}]))
    entries = wlm_zosmf_parser.parse_wlm_zosmf(dump)
    assert entries[0].name == "?"


def test_malformed_json_returns_empty_list(tmp_path):
    dump = tmp_path / "wlm_zosmf.txt"
    dump.write_text("<html>not json</html>")
    assert wlm_zosmf_parser.parse_wlm_zosmf(dump) == []
