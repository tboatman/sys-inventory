"""Parse active BPXPRMxx PARMLIB member dumps (see
ansible/roles/zos_extract/tasks/bpxprm_snapshot.yml) into
BpxprmStatement records -- z/OS UNIX System Services (OMVS)
configuration, named by IEASYSxx's own OMVS= keyword (see
ieasys_parser.py) the same way SSN=/CMD=/PROD=/MSTRJCL= name
IEFSSNxx/COMMNDxx/IFAPRDxx/MSTJCLxx.

Dump format: same ##MEMBER sentinel-delimited shape as PROCLIB/PARMLIB
dumps (jcl_parser.split_members()), one block per active BPXPRMxx
member (there can be more than one concatenated -- see
zos_extract_active_omvs_suffixes), e.g.:

    ##MEMBER BPXPRM00
    ROOT FILESYSTEM('OMVS.ROOT.ZFS')
         TYPE(ZFS) MODE(RDWR)
    MOUNT FILESYSTEM('OMVS.ETC.ZFS')
          MOUNTPOINT('/etc')
          TYPE(ZFS) MODE(RDWR)
    MAXPROCSYS(3000)
    TZ(EST5EDT)

Statement syntax: unlike IEASYSxx's flat KEYWORD=value,comma-continued
shape (ieasys_parser.py), a real BPXPRMxx member is statement-oriented --
STMT KEYWORD(value) KEYWORD2(value2)..., continuing onto further
physical lines with *no* continuation character until the next
recognized top-level statement keyword starts. This is the same shape
this project already solved for PROFILE.TCPIP
(tcpip_parser.py/TcpipProfileStatement) -- indentation alone can't
reliably separate a new statement from a continuation line (BPXPRMxx
samples show continuation lines indented to line up under the parent
statement, but that's a stylistic convention, not something a parser can
rely on), so this reuses that same "known keyword vocabulary, fold
anything else into the current statement's operands" approach rather
than modeling z/OS's real (undocumented-here) statement grammar.
_BPXPRM_STATEMENT_KEYWORDS is built from IBM's documented BPXPRMxx
statement list; an unrecognized keyword would incorrectly get folded
into the preceding statement instead of starting its own -- same
documented limitation _PROFILE_STATEMENT_KEYWORDS carries in
tcpip_parser.py.

'/* ... */' comments (the standard MVS PARMLIB convention IEASYSxx/JES2
init decks also use) are stripped before any other processing, same
approach ieasys_parser.py/jes2parm_parser.py use.

The "known keyword vocabulary, fold anything else into the current
statement" logic itself lives in parmlib_engines.statement_engine() --
shared with any future Category C domain from doc/TODO.md's "9.1" that
turns out to have the same statement shape, parameterized by each
domain's own keyword vocabulary (_BPXPRM_STATEMENT_KEYWORDS below).

NOT YET VALIDATED against a real BPXPRMxx member -- built from IBM's
documented statement syntax only, same caveat db2_catalog_parser.py/
wlm_zosmf_parser.py/cics_csdup_parser.py carry for their own unconfirmed
parsing surfaces.
"""
from __future__ import annotations

from pathlib import Path

from .jcl_parser import split_members
from .models import BpxprmStatement
from .parmlib_engines import statement_engine

# Top-level BPXPRMxx statement keywords, from IBM's documented BPXPRMxx
# reference -- see the module docstring for the known limitation (an
# unrecognized keyword gets folded into the preceding statement).
_BPXPRM_STATEMENT_KEYWORDS = {
    "ROOT",
    "MOUNT",
    "FILESYSTYPE",
    "SUBFILESYSTYPE",
    "NETWORK",
    "STARTUP_PROC",
    "MAXPROCSYS",
    "MAXPROCUSER",
    "MAXUIDS",
    "MAXPTYS",
    "MAXFILEPROC",
    "MAXTHREADS",
    "MAXTHREADTASKS",
    "MAXCPUTIME",
    "MAXASSIZE",
    "MAXCORESIZE",
    "MAXSHAREPAGES",
    "MAXMMAPAREA",
    "IPCMSGNIDS",
    "IPCMSGQBYTES",
    "IPCMSGQMNUM",
    "IPCSEMNIDS",
    "IPCSHMNIDS",
    "IPCSHMNSEGS",
    "IPCSHMSPAGES",
    "TZ",
    "PATH",
    "PATHDISP",
    "PATHMODE",
    "PATHOPTS",
    "SYSCALL_COUNTS",
    "USERIDALIASTABLE",
    "VERSION",
    "AUTOCVT",
    "KERNELSTACKS",
    "MAXFILESIZE",
    "SUPERUSER",
    "FILESYSEXCEPTIONS",
}


def parse_member(name: str, raw_lines: list[str]) -> list[BpxprmStatement]:
    return [
        BpxprmStatement(stmt=stmt, operands=operands, source_member=name)
        for stmt, operands in statement_engine(raw_lines, _BPXPRM_STATEMENT_KEYWORDS)
    ]


def parse_bpxprm_snapshot(path: Path) -> list[BpxprmStatement]:
    """Parse one bpxprm_snapshot.txt dump (one or more ##MEMBER blocks,
    each an active BPXPRMxx member's raw content) into BpxprmStatement
    rows."""
    text = path.read_text(errors="replace")
    statements: list[BpxprmStatement] = []
    for name, raw_lines in split_members(text).items():
        statements.extend(parse_member(name, raw_lines))
    return statements
