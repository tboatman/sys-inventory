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
its primary "name" -- CMCI attribute names vary by resource type. The
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
attribute names ("tranid"/"transid", "file") are inferred from CMCI's
general naming convention and cmci_get's own filter-example key names
(`file: "DFH*"` used against CICSLocalFile), not independently confirmed
against a real response. _NAME_KEYS tries every candidate across all
resource types (harmless: a record simply won't have the keys that don't
apply to its own resource type) and falls back to "?" if none match,
same graceful-degradation precedent as wlm_zosmf_parser.py's
_entry_name() -- the full attributes dict is preserved either way.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import CmciResource

_NAME_KEYS = ("name", "program", "tranid", "transid", "file", "dsname")


def _resource_name(attributes: dict) -> str:
    for key in _NAME_KEYS:
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
                    name=_resource_name(record),
                    attributes=record,
                )
            )
    return resources
