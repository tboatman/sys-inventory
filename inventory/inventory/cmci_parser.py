"""Parse cics_cmci.txt dumps produced by
ansible/roles/zos_extract/tasks/cics_cmci.yml (CMCI queries run via
ibm.ibm_zos_cics's cmci_get module) into CmciResource records.

Dump format: JSON Lines, one line per (context, resource_type) query --
this pipeline's OWN file format, not an external API's response saved
verbatim, since cmci_get already returns clean parsed records (a list of
dicts) rather than raw report text. Each line looks like:

    {"context": "CICSA", "resource_type": "cicsdefinitionprogram", "records": [{...}, {...}]}

Unlike db2_catalog_parser.py/wlm_zosmf_parser.py/cics_csdup_parser.py,
there's no report-format guessing here at all -- cmci_get itself already
parsed CMCI's XML wire format, and this pipeline controls the JSON Lines
shape above, so parsing it is a straightforward line-by-line json.loads().
A line that isn't valid JSON, or doesn't have the expected
context/resource_type/records shape, is skipped rather than raising --
same "tolerant of surrounding noise" precedent as every other parser here
(e.g. a truncated/malformed line at the end of a partially-written file).

What IS still a guess: which attribute in a resource's own record dict is
its primary "name" -- CMCI attribute names vary by resource type, and
this is looked up PER RESOURCE TYPE (_NAME_KEY_BY_TYPE), not via one
flat candidate list -- a flat list bit us during testing: an installed
CICSTransaction record legitimately carries both its own "tranid" and a
"program" attribute (the program it invokes), and if "program" outranks
"tranid" in a shared priority list, every transaction's own name gets
misidentified as whatever program it happens to invoke instead. The
following are confirmed against cmci_get's own module documentation
examples (real, not guessed): CSD-defined resources
(cicsdefinitionprogram/cicsdefinitiontransaction/cicsdefinitionfile/
cicsdefinitionbundle) are identified by a "name" attribute (see
cmci_get's own "Get a progdef from CSD"/"Ignore errors when bundle
definition is not found" examples, both filtering on `name`). The
currently-installed equivalents are NOT confirmed the same way -- the
"program" attribute is confirmed for the installed CICSProgram sample
in cmci_get's own RETURN documentation (`"program": "ANSITEST"`), but
CICSTransaction/CICSLocalFile's own installed-resource primary-identifier
attribute names ("tranid", "file") are inferred from CMCI's general
naming convention and cmci_get's own filter-example key names
(`file: "DFH*"` used against CICSLocalFile), not independently confirmed
against a real response. A resource type not in _NAME_KEY_BY_TYPE (or
missing its own expected key) falls back to scanning every candidate key
across all types, then "?" if still nothing matches -- same
graceful-degradation precedent as wlm_zosmf_parser.py's _entry_name() --
the full attributes dict is preserved either way.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import CmciResource

_NAME_KEY_BY_TYPE = {
    "cicsdefinitionprogram": "name",
    "cicsdefinitiontransaction": "name",
    "cicsdefinitionfile": "name",
    "cicsdefinitionbundle": "name",
    "CICSProgram": "program",
    "CICSTransaction": "tranid",
    "CICSLocalFile": "file",
}
_FALLBACK_NAME_KEYS = ("name", "program", "tranid", "transid", "file", "dsname")


def _resource_name(resource_type: str, attributes: dict) -> str:
    expected_key = _NAME_KEY_BY_TYPE.get(resource_type)
    if expected_key:
        value = attributes.get(expected_key)
        if isinstance(value, str) and value:
            return value

    for key in _FALLBACK_NAME_KEYS:
        value = attributes.get(key)
        if isinstance(value, str) and value:
            return value
    return "?"


def parse_cmci(path: Path) -> list[CmciResource]:
    """Parse one cics_cmci.txt dump (JSON Lines, one line per
    (context, resource_type) query) into CmciResource rows."""
    resources: list[CmciResource] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue

        context = payload.get("context")
        resource_type = payload.get("resource_type")
        records = payload.get("records")
        if not isinstance(context, str) or not isinstance(resource_type, str) or not isinstance(records, list):
            continue

        for record in records:
            if not isinstance(record, dict):
                continue
            resources.append(
                CmciResource(
                    resource_type=resource_type,
                    context=context,
                    name=_resource_name(resource_type, record),
                    attributes=record,
                )
            )
    return resources
