"""Parse active DIAGxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/diag_snapshot.yml) into DiagStatement
records -- diagnostic function defaults (common storage tracking,
GETMAIN/FREEMAIN/storage trace), named by IEASYSxx's own DIAG= keyword
(see ieasys_parser.py) the same way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/
DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/SMF=/IOS=/CON=/SMS=/
IZU= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/
IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/
CONSOLxx/IGDSMSxx/IZUPRMxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active DIAGxx member.

Statement syntax: a real DIAG00 member is statement-oriented, one
keyword per physical line (`VSM TRACK CSA(ON) SQA(ON)`, `VSM TRACE
GETFREE(OFF)`) -- the same shape parmlib_engines.statement_engine()
already handles for BPXPRMxx/AUTORxx/etc.

CONFIRMED wrinkle no earlier Category C domain's confirming member
exercised: a real DIAG00 member carries traditional MVS PARMLIB
sequence numbers in columns 73-80 of every physical line (data in
columns 1-71/72, sequence number ignored by the system) -- e.g.

    /********************************************************************/  00050000
     VSM TRACK CSA(ON) SQA(ON)                                              01350000

Left unstripped, that trailing 8-digit field would get folded into the
statement's own operand text as a bogus trailing token (`"TRACK
CSA(ON) SQA(ON) 01350000"`), since it lives on the same physical line as
real content, not a separate line strip_comments()/statement_engine()
would otherwise drop. parmlib_engines.strip_sequence_numbers() removes
it up front, before handing lines to statement_engine() -- this was the
first domain to need it; a second (IEASVCxx, ieasvc_parser.py) needed
the identical logic, so it now lives there as a shared helper instead of
being copy-pasted a second time.

Statement vocabulary CONFIRMED against a real DIAG00 member: VSM (the
only top-level keyword exercised -- `VSM TRACK ...`/`VSM TRACE ...` are
two separate statements, both kept in order since VSM starts each one).
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import DiagStatement
from .parmlib_engines import statement_engine, strip_sequence_numbers

_DIAG_STATEMENT_KEYWORDS = {
    "VSM",
}


def parse_member(name: str, raw_lines: list[str]) -> list[DiagStatement]:
    return [
        DiagStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(strip_sequence_numbers(raw_lines), _DIAG_STATEMENT_KEYWORDS)
    ]


def parse_diag_snapshot(path: Path) -> list[DiagStatement]:
    """Parse one diag_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active DIAGxx member's raw content) into DiagStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[DiagStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
