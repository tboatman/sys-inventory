"""Parse 'D WLM' dumps (see ansible/roles/zos_extract/tasks/wlm.yml) into
a single WlmPolicy record -- the active policy name and, if determinable,
its mode (GOAL vs. COMPATIBILITY).

CONFIRMED against a real system -- and this wasn't just a formatting fix,
the originally-guessed command ('D WLM,POLICY') doesn't exist at all: a
real system rejected it outright ("WLM SYNTAX ERROR, UNIDENTIFIABLE
KEYWORD" for the 'POLICY' keyword). The real command is bare 'D WLM' (no
operand), which returns message IWM025I -- confirmed against both IBM's
own documentation and a real reply from this site:

    IWM025I  06.44.43  WLM DISPLAY 879
    ACTIVE WORKLOAD MANAGEMENT SERVICE POLICY NAME: BMCPROD1
    ACTIVATED: 2023/09/11  AT: 12:47:50  BY: CSTSYP    FROM: BES2
    DESCRIPTION: BMC Production Service Policy
    RELATED SERVICE DEFINITION NAME: bmcprod1
    INSTALLED: 2023/09/11  AT: 12:45:09  BY: CSTSYP    FROM: BES2
    WLM VERSION LEVEL:       LEVEL040
    WLM FUNCTIONALITY LEVEL: LEVEL035
    WLM CDS FORMAT LEVEL:    FORMAT 3
    STRUCTURE SYSZWLM_WORKUNIT STATUS: DISCONNECTED

The real reply never contains a "MODE=" token anywhere (the originally
guessed field) -- IWM025I only reports an *active service policy* at
all, which is inherently a goal-mode concept, and WLM compatibility mode
has been desupported on modern z/OS releases (IBM message IRA903I "WLM
COMPATIBILITY MODE IS NOT SUPPORTED"). So `mode` is set to "GOAL" purely
from the presence of a parsed policy name -- a documented inference from
how the real message works, not a guessed keyword match -- rather than
left None or removed as a field.

Modeled directly on sysinfo_parser.py: anchor on the stable "POLICY
NAME:" token, tolerant of surrounding whitespace/noise. This is only a
first cut (policy name/mode); full service-class/goal/resource-group
definitions need the z/OSMF WLM REST API, not attempted here. Dump
format: the raw console reply, unchanged -- no sentinel headers needed,
since this captures exactly one D-command's output (same "single
command, no bundling" shape uss_mounts_parser.py already uses for
'D OMVS,F').
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import WlmPolicy

_POLICY_NAME = re.compile(r"\bPOLICY\s+NAME\s*:\s*(\S+)", re.IGNORECASE)


def parse_wlm(path: Path) -> WlmPolicy | None:
    """Parse one wlm.txt dump into a single WlmPolicy record, or None if
    no policy name could be found at all (an empty/unrecognized dump)."""
    text = path.read_text(errors="replace")
    m = _POLICY_NAME.search(text)
    if m is None:
        return None
    return WlmPolicy(policy_name=m.group(1), mode="GOAL")
