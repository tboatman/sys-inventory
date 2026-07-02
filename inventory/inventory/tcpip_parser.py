"""Parse TCP/IP dumps produced by ansible/roles/zos_extract/tasks/tcpip.yml
into TcpipHomeAddress/TcpipProfileStatement records.

Dump format: a "##NETSTAT_HOME" block (always present) holding
'D TCPIP,,NETSTAT,HOME''s raw reply, and an optional "##PROFILE" block
(only present if zos_extract_tcpip_profile_dsn was configured) holding
the PROFILE.TCPIP-style dataset's raw text, verbatim -- same bare-sentinel
vocabulary sysinfo_parser.py/catalog_parser.py already share, split via
blocks.split_named_blocks().

'D TCPIP,,NETSTAT,HOME' reply CONFIRMED against a real system on
2026-07-02 -- the real shape differs from the original guess in two
ways: (1) entries come in two flavors, legacy "LINKNAME:" rows and
OSA-Express QDIO "INTFNAME:" rows, both belonging to the same HOME
ADDRESS LIST and needing the same treatment; (2) each entry is followed
by a "FLAGS:" line (sometimes carrying "PRIMARY", marking the stack's
primary home address) and IPv6 loopback entries additionally carry a
"TYPE:" line before FLAGS. A real reply:

    HOME ADDRESS LIST:
    LINKNAME:   EZASAMEMVS
      ADDRESS:  192.168.11.168
        FLAGS:
    INTFNAME:   QDIOLE2
      ADDRESS:  192.168.11.167
        FLAGS:  PRIMARY
    INTFNAME:   LOOPBACK6
      ADDRESS:  ::1
        TYPE:   LOOPBACK
        FLAGS:
    6 OF 6 RECORDS DISPLAYED
    END OF THE REPORT

Each entry is only appended once its FLAGS: line is seen (that's what
resolves is_primary), or when the next LINKNAME:/INTFNAME: row starts a
new entry -- see _parse_netstat_home. Trailing "N OF N RECORDS
DISPLAYED"/"END OF THE REPORT" lines and the leading console-echo/message
ID lines (EZD0101I, ISF031I, the "-D TCPIP,,NETSTAT,HOME" echo, etc.)
don't match any of this parser's regexes and are ignored, the same
"regexes .search() anywhere in the line" tolerance the rest of this
pipeline relies on for MVS console prefix junk.

PROFILE.TCPIP statement parsing CONFIRMED against a real member on
2026-07-02 -- and the real shape needed a real redesign, not just regex
tuning. The original guess ("every non-comment, non-blank line is its
own statement") was wrong: real PROFILE.TCPIP statements like
INTERFACE/PORT/AUTOLOG/BEGINROUTES/SMFCONFIG span multiple physical
lines -- some via indented continuation lines carrying the same
statement's own sub-parameters (INTERFACE's DEFINE/IPADDR/PORTNAME),
some via whole indented *tables* bracketed by a start keyword and,
where one exists, an END* keyword (PORT's ~80-row port-reservation
table; AUTOLOG's job-name list terminated by ENDAUTOLOG; BEGINROUTES's
ROUTE rows terminated by ENDROUTES). Indentation alone can't reliably
tell a new statement from a continuation line either -- in the real
member, SMFCONFIG statements themselves are indented by 2 spaces (no
structural reason found, just how the file was originally typed), the
same indentation depth continuation lines could plausibly use. So
_parse_profile instead recognizes a fixed, evidence-based vocabulary of
known top-level statement keywords (_PROFILE_STATEMENT_KEYWORDS,
built from IBM's documented PROFILE.TCPIP statement list plus every
keyword actually observed in the real member) -- a line starting with
one of those (case-insensitive, regardless of indentation) begins a new
TcpipProfileStatement; any other non-comment, non-blank line is folded
into the *current* statement's operands (whitespace-normalized and
space-joined), whatever its indentation. A keyword this vocabulary
doesn't know about would incorrectly get folded into the preceding
statement rather than starting its own -- a known, documented limitation
of capturing generically against a keyword list instead of modeling
z/OS's real (undocumented-here) statement grammar.

';' starts a comment that runs to the end of the line, even mid-line
(confirmed in the real member, e.g. port-table rows commented with a
trailing "; description" -- descriptive text, not part of the
statement) -- comments are stripped before any other processing, and a
line that's comment-only (or blank after stripping) is skipped
entirely, whether or not it's also inside a PORT/AUTOLOG/BEGINROUTES
block (e.g. a disabled AUTOLOG entry or PORT reservation prefixed with
';' is correctly excluded rather than merged in as if active).

tcpip.yml writes a leading ";;SOURCE_DSN=<dsn>" marker line as the first
line of the ##PROFILE block (the fetched dataset's own text has no
opinion on its own name) -- this parser strips that line and uses it to
populate TcpipProfileStatement.source_dsn, defaulting to "" if a
hand-edited/older dump doesn't have it.
"""
from __future__ import annotations

import re
from pathlib import Path

from .blocks import split_named_blocks
from .models import TcpipHomeAddress, TcpipProfileStatement

_LINK_OR_INTF = re.compile(r"\b(?:LINKNAME|INTFNAME):\s*(\S+)", re.IGNORECASE)
_ADDRESS = re.compile(r"\bADDRESS:\s*(\S+)", re.IGNORECASE)
_FLAGS = re.compile(r"\bFLAGS:\s*(\S.*)?$", re.IGNORECASE)
_SOURCE_DSN_MARKER = re.compile(r"^;;SOURCE_DSN=(\S+)\s*$")

# Top-level PROFILE.TCPIP statement keywords -- see the module docstring
# for how this vocabulary was built and its known limitation (an
# unrecognized keyword gets folded into the preceding statement instead
# of starting its own).
_PROFILE_STATEMENT_KEYWORDS = {
    "ARPAGE",
    "AUTOLOG",
    "ENDAUTOLOG",
    "BEGINROUTES",
    "ENDROUTES",
    "DEVICE",
    "LINK",
    "HOME",
    "HOSTNAME",
    "GATEWAY",
    "GLOBALCONFIG",
    "INTERFACE",
    "IPCONFIG",
    "IPCONFIG6",
    "PORT",
    "PORTRANGE",
    "SACONFIG",
    "SMFCONFIG",
    "SOMAXCONN",
    "START",
    "STOP",
    "TCPCONFIG",
    "UDPCONFIG",
}


def _parse_netstat_home(lines: list[str]) -> list[TcpipHomeAddress]:
    addresses: list[TcpipHomeAddress] = []
    current_link: str | None = None
    current_address: str | None = None
    current_primary = False

    def flush() -> None:
        if current_link is not None and current_address is not None:
            addresses.append(
                TcpipHomeAddress(link_name=current_link, ip_address=current_address, is_primary=current_primary)
            )

    for line in lines:
        link_match = _LINK_OR_INTF.search(line)
        if link_match:
            flush()
            current_link = link_match.group(1)
            current_address = None
            current_primary = False
            continue
        address_match = _ADDRESS.search(line)
        if address_match:
            current_address = address_match.group(1)
            continue
        flags_match = _FLAGS.search(line)
        if flags_match and "PRIMARY" in (flags_match.group(1) or "").upper():
            current_primary = True
    flush()
    return addresses


def _parse_profile(lines: list[str]) -> list[TcpipProfileStatement]:
    statements: list[TcpipProfileStatement] = []
    source_dsn = ""
    current: TcpipProfileStatement | None = None

    for line in lines:
        marker_match = _SOURCE_DSN_MARKER.match(line)
        if marker_match:
            source_dsn = marker_match.group(1)
            continue
        content = " ".join(line.split(";", 1)[0].split())
        if not content:
            continue
        stmt, sep, operands = content.partition(" ")
        if stmt.upper() in _PROFILE_STATEMENT_KEYWORDS:
            current = TcpipProfileStatement(stmt=stmt.upper(), operands=operands.strip(), source_dsn=source_dsn)
            statements.append(current)
        elif current is not None:
            current.operands = f"{current.operands} {content}".strip()
    return statements


def parse_tcpip(path: Path) -> tuple[list[TcpipHomeAddress], list[TcpipProfileStatement]]:
    """Parse one tcpip.txt dump into (home addresses, profile statements)."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return (
        _parse_netstat_home(blocks.get("NETSTAT_HOME", [])),
        _parse_profile(blocks.get("PROFILE", [])),
    )
