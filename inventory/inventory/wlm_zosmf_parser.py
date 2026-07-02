"""Parse wlm_zosmf.txt dumps produced by
ansible/roles/zos_extract/tasks/wlm_zosmf.yml (a z/OSMF WLM REST API
response, saved verbatim) into WlmZosmfEntry records.

THE SINGLE MOST SPECULATIVE PARSER IN THIS PIPELINE. Every other domain
here parses a well-documented, stable console command or MVS program
report; this one instead expects a JSON response from z/OSMF's WLM REST
API, whose exact endpoint path (zos_extract_wlm_zosmf_path) and response
schema are NOT confirmed against IBM's own current REST API reference or
a real response -- there's no other REST/JSON precedent anywhere else in
this codebase to lean on either. Treat everything below as a rough
starting point only: run wlm_zosmf.yml (via playbooks/wlm_zosmf.yml)
against a real z/OSMF instance, compare the actual response shape
against what's guessed here, and rewrite parse_wlm_zosmf() to match --
don't assume this is even close.

Best-guess response shape: a JSON object with a top-level list of entries
under one of a few candidate key names ("policies", "items", "data"), OR
a bare JSON list at the top level, where each entry is itself a JSON
object. If neither shape matches (e.g. the top level is a single object,
not a list), the whole response is wrapped as one single entry rather
than raising -- something is better than nothing when the schema is this
uncertain, and a caller can still inspect WlmZosmfEntry.raw either way.

Each entry's `name` is extracted via a few candidate JSON key names
("name", "policy_name", "policyName", "service_class_name",
"serviceClassName") -- if none of those are present, `name` falls back
to "?" rather than failing, since which key (if any) actually holds a
name in the real schema isn't known. The entire original JSON object for
that entry is preserved in `raw` regardless, so nothing is lost even if
`name` extraction guesses wrong.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import WlmZosmfEntry

_LIST_KEYS = ("policies", "items", "data")
_NAME_KEYS = ("name", "policy_name", "policyName", "service_class_name", "serviceClassName")


def _entry_name(entry: dict) -> str:
    for key in _NAME_KEYS:
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return "?"


def parse_wlm_zosmf(path: Path) -> list[WlmZosmfEntry]:
    """Parse one wlm_zosmf.txt dump (a saved z/OSMF JSON response) into
    WlmZosmfEntry rows. Returns an empty list if the file isn't valid
    JSON at all (e.g. an HTML error page from a misconfigured endpoint)
    rather than raising -- a malformed/empty dump is treated as "nothing
    to report", not a hard error."""
    text = path.read_text(errors="replace")
    try:
        payload = json.loads(text)
    except ValueError:
        return []

    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = next(
            (payload[key] for key in _LIST_KEYS if isinstance(payload.get(key), list)),
            None,
        )
        if entries is None:
            entries = [payload]
    else:
        return []

    return [
        WlmZosmfEntry(name=_entry_name(entry), raw=entry)
        for entry in entries
        if isinstance(entry, dict)
    ]
