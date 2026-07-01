"""Parse IFAPRDxx (product enablement policy) PARMLIB member dumps,
produced by the *same* zos-extract/python/extrproc.py used for PROCLIB,
into Product objects.

IFAPRDxx complements the SMP/E FMID data this pipeline already collects:
SMP/E (smpe_parser.py) says what's installed and at what patch level;
IFAPRDxx says what's actually licensed/enabled for use via a PRODUCT
statement, e.g.:

    PRODUCT OWNER('IBM CORP')
        NAME('EMBEDDED RUNTIME ENABLEMENT FOR ZOS')
        ID(5655-EPS)
        VERSION(*) RELEASE(*) MOD(*)
        FEATURENAME(*)
        STATE(ENABLED)

Unlike D SYMBOLS/D IPLINFO console output (see sysinfo_parser.py), this
statement syntax is IBM-documented and stable across releases, not
customer console configuration -- so this parser doesn't carry the same
"tune against your real output" caveat. It also isn't JCL-style
comma-continued text, so it doesn't reuse jcl_parser.join_continuations():
a PRODUCT statement's parenthesized clauses can freely span multiple
lines with no continuation marker, so each statement is instead grabbed as
one block (from a "PRODUCT" keyword up to the next one, or end of member)
and its clauses are pulled out of that whole block at once.
"""
from __future__ import annotations

import re
from pathlib import Path

from .jcl_parser import split_members
from .models import Product

_PRODUCT_SPLIT = re.compile(r"(?=^\s*PRODUCT\b)", re.IGNORECASE | re.MULTILINE)

_ID = re.compile(r"\bID\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE | re.DOTALL)
_NAME = re.compile(r"\bNAME\s*\(\s*'([^']*)'\s*\)", re.IGNORECASE | re.DOTALL)
_VERSION = re.compile(r"\bVERSION\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE | re.DOTALL)
_RELEASE = re.compile(r"\bRELEASE\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE | re.DOTALL)
_MOD = re.compile(r"\bMOD\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE | re.DOTALL)
_FEATURENAME = re.compile(r"\bFEATURENAME\s*\(\s*'?([^')]*?)'?\s*\)", re.IGNORECASE | re.DOTALL)
_STATE = re.compile(r"\bSTATE\s*\(\s*([A-Za-z]+)\s*\)", re.IGNORECASE | re.DOTALL)


def _first_match(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def parse_products(path: Path) -> list[Product]:
    """Parse one IFAPRDxx dump (as produced by extrproc.py) into Product rows.
    A block with no ID() is skipped (not a real PRODUCT statement, or too
    malformed to identify) rather than raising -- matches this project's
    "silently skip unparseable" convention elsewhere."""
    text = path.read_text(errors="replace")
    products: list[Product] = []
    for member_name, raw_lines in split_members(text).items():
        member_text = "\n".join(raw_lines)
        for block in _PRODUCT_SPLIT.split(member_text):
            if not block.strip():
                continue
            product_id = _first_match(_ID, block)
            if product_id is None:
                continue
            state = _first_match(_STATE, block)
            products.append(
                Product(
                    id=product_id,
                    name=_first_match(_NAME, block),
                    version=_first_match(_VERSION, block),
                    release=_first_match(_RELEASE, block),
                    mod=_first_match(_MOD, block),
                    featurename=_first_match(_FEATURENAME, block),
                    state=state.upper() if state else None,
                    source_member=member_name,
                )
            )
    return products
