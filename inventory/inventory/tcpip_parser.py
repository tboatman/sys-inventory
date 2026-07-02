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

NOT YET VALIDATED: PROFILE.TCPIP statement parsing below -- no real
PROFILE.TCPIP sample has been checked yet (only NETSTAT HOME has been
confirmed so far). Treat the patterns below as a starting point, the
same situation sysinfo_parser.py originally documented for its own
regexes -- run tcpip.yml with zos_extract_tcpip_profile_dsn set against
a real system, diff the actual profile text against what's expected
here, and tune accordingly before relying on this in production.

'PROFILE.TCPIP' statement syntax (well-documented, stable convention):
each non-comment, non-blank line starts with a statement keyword (DEVICE,
LINK, HOME, HOSTNAME, PORT, ...) followed by positional operands -- not
uniform KEYWORD=VALUE the way VTAMOPTS/JES2 init statements are, so this
captures each statement generically as (stmt, raw operand text) rather
than modeling every statement type's own positional syntax. ';' starts a
comment (PROFILE.TCPIP's own comment marker); comment and blank lines are
skipped.

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
    for line in lines:
        marker_match = _SOURCE_DSN_MARKER.match(line)
        if marker_match:
            source_dsn = marker_match.group(1)
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        stmt, sep, operands = stripped.partition(" ")
        if not sep:
            stmt, operands = stripped, ""
        statements.append(TcpipProfileStatement(stmt=stmt.upper(), operands=operands.strip(), source_dsn=source_dsn))
    return statements


def parse_tcpip(path: Path) -> tuple[list[TcpipHomeAddress], list[TcpipProfileStatement]]:
    """Parse one tcpip.txt dump into (home addresses, profile statements)."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return (
        _parse_netstat_home(blocks.get("NETSTAT_HOME", [])),
        _parse_profile(blocks.get("PROFILE", [])),
    )
