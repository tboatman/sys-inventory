"""Parse TCP/IP dumps produced by ansible/roles/zos_extract/tasks/tcpip.yml
into TcpipHomeAddress/TcpipProfileStatement records.

Dump format: a "##NETSTAT_HOME" block (always present) holding
'D TCPIP,,NETSTAT,HOME''s raw reply, and an optional "##PROFILE" block
(only present if zos_extract_tcpip_profile_dsn was configured) holding
the PROFILE.TCPIP-style dataset's raw text, verbatim -- same bare-sentinel
vocabulary sysinfo_parser.py/catalog_parser.py already share, split via
blocks.split_named_blocks().

NOT YET VALIDATED against a real system or a real PROFILE.TCPIP sample:
IBM's docs site 403'd on direct fetch and no secondary source turned up
real sample output for either piece while writing this (both checked).
Treat the patterns below as a starting point, the same situation
sysinfo_parser.py documents for its own regexes -- run tcpip.yml against a
real system, diff the actual reply/profile text against what's expected
here, and tune accordingly before relying on this in production.

'D TCPIP,,NETSTAT,HOME' reply (expected shape, not confirmed): a home
address list, one entry per interface, each shaped as a "LINKNAME:" line
followed by an "ADDRESS:" line (paired, not necessarily on the same
physical line):

    LINKNAME: ETH0LINK
      ADDRESS: 10.1.1.2
    LINKNAME: LOOPBACK
      ADDRESS: 127.0.0.1

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

_LINKNAME = re.compile(r"\bLINKNAME:\s*(\S+)", re.IGNORECASE)
_ADDRESS = re.compile(r"\bADDRESS:\s*(\S+)", re.IGNORECASE)
_SOURCE_DSN_MARKER = re.compile(r"^;;SOURCE_DSN=(\S+)\s*$")


def _parse_netstat_home(lines: list[str]) -> list[TcpipHomeAddress]:
    addresses: list[TcpipHomeAddress] = []
    current_link: str | None = None
    for line in lines:
        link_match = _LINKNAME.search(line)
        if link_match:
            current_link = link_match.group(1)
            continue
        address_match = _ADDRESS.search(line)
        if address_match and current_link is not None:
            addresses.append(TcpipHomeAddress(link_name=current_link, ip_address=address_match.group(1)))
            current_link = None
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
