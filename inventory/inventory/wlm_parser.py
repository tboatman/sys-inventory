"""Parse 'D WLM,POLICY' dumps (see ansible/roles/zos_extract/tasks/wlm.yml)
into a single WlmPolicy record -- the active policy name and, if the
reply exposes it, its mode (GOAL vs. COMPATIBILITY).

Modeled directly on sysinfo_parser.py: anchor on the keyword tokens that
identify each field, tolerant of surrounding whitespace/noise, leaving a
field None if its pattern doesn't match rather than erroring. Dump format:
the raw console reply, unchanged -- no sentinel headers needed, since
this captures exactly one D-command's output (same "single command, no
bundling" shape uss_mounts_parser.py already uses for 'D OMVS,F').

NOT YET VALIDATED against a real system: 'D WLM,POLICY' hasn't been
checked against an actual reply from this site (same situation
vtam_parser.py/tcpip_parser.py/sms_parser.py document for their own
commands). Treat the patterns below as a starting point -- run wlm.yml
against a real system, diff the actual reply text against what's
expected here, and tune accordingly before relying on this in
production. This is only a first cut (policy name/mode); full
service-class/goal/resource-group definitions need the z/OSMF WLM REST
API, not attempted here.
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import WlmPolicy

_POLICY_NAME = re.compile(r"\bPOLICY\s+NAME\s*=\s*(\S+)", re.IGNORECASE)
_MODE = re.compile(r"\bMODE\s*=\s*(\S+)", re.IGNORECASE)


def _first_match(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def parse_wlm(path: Path) -> WlmPolicy | None:
    """Parse one wlm.txt dump into a single WlmPolicy record, or None if
    no policy name could be found at all (an empty/unrecognized dump)."""
    text = path.read_text(errors="replace")
    policy_name = _first_match(_POLICY_NAME, text)
    if policy_name is None:
        return None
    return WlmPolicy(policy_name=policy_name, mode=_first_match(_MODE, text))
