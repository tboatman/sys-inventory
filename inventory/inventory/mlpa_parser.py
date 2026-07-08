"""Parse active IEALPAxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/mlpa_snapshot.yml) into MlpaStatement
records -- Modified Link Pack Area (MLPA) module additions, named by
IEASYSxx's own MLPA= keyword (see ieasys_parser.py) the same way SSN=/
CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/
GRSRNL=/SMF=/IOS=/CON=/SMS=/IZU=/DIAG=/CATALOG=/GRSCNF=/PROG=/SVC=/
LPA= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/
IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/
CONSOLxx/IGDSMSxx/IZUPRMxx/DIAGxx/IGGCATxx/GRSCNFxx/PROGxx/IEASVCxx/
LPALSTxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active IEALPAxx member.

Statement syntax: originally planned in doc/TODO.md as a bespoke
"modname,ddname pairs" Category E format, before a real member was seen
-- CONFIRMED against a real member to actually be statement-oriented,
`INCLUDE LIBRARY(dsn)` / `MODULES(mod1,mod2,...)`, the same shape every
Category C domain already has:

    INCLUDE LIBRARY(ADCD.&SYSVER..LINKLIB)
    MODULES(DFSAFMD0,
            IGC0020B)

So this reuses parmlib_engines.statement_engine() directly with a
two-keyword vocabulary (`INCLUDE`, `MODULES`) instead of a bespoke
library/module-list dataclass -- each becomes its own generic row;
associating a MODULES list back to its preceding INCLUDE LIBRARY is a
query-time concern, not a parse-time one.

CONFIRMED wrinkle no earlier domain's confirming member exercised: a
real IEALPAxx member's trailing descriptive comment lines each begin
with `/*` but never close with a matching `*/` anywhere in the member
(e.g. a block of lines like ` /* IGC0020B - IMS TYPE 4 SVC FOR DBRC
(SVC 202)` with no closing `*/` at all). parmlib_engines.strip_comments()
can't remove these -- its balanced-pair regex requires an actual closing
`*/` to match anything -- so they'd otherwise survive as raw text and
get folded into the preceding statement's operands as garbage. Fixed by
dropping any line that still starts with `/*` after the normal
strip_comments() pass.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import MlpaStatement
from .parmlib_engines import statement_engine, strip_comments

_MLPA_STATEMENT_KEYWORDS = {
    "INCLUDE",
    "MODULES",
}


def _drop_unterminated_comment_lines(raw_lines: list[str]) -> list[str]:
    text = strip_comments("\n".join(raw_lines))
    return [line for line in text.splitlines() if not line.strip().startswith("/*")]


def parse_member(name: str, raw_lines: list[str]) -> list[MlpaStatement]:
    cleaned = _drop_unterminated_comment_lines(raw_lines)
    return [
        MlpaStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(cleaned, _MLPA_STATEMENT_KEYWORDS)
    ]


def parse_mlpa_snapshot(path: Path) -> list[MlpaStatement]:
    """Parse one mlpa_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active IEALPAxx member's raw content) into MlpaStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[MlpaStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
