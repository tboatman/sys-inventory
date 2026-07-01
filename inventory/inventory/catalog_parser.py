"""Parse the catalog dump produced by zos-extract/python/extrcat.py (a
##NONVSAM block from ZOAU's datasets.list_datasets(), plus a ##LISTCAT
block of raw IDCAMS LISTCAT ... ALL output) into CatalogDataset/VsamCluster
records.

The ##NONVSAM block is this project's own simple space-separated format
(like activity_parser.py's dumps) -- no "tune against your real system"
caveat needed there. The ##LISTCAT block is different: like smpe_parser.py/
sysinfo_parser.py, it anchors on the stable keyword tokens IDCAMS LISTCAT
ALL output always contains (CLUSTER/DATA/INDEX headers, VOLSER/KEYLEN/RKP
dash-filled fields, and the INDEXED/NONINDEXED/LINEAR/NUMBERED keywords
that ibm_zos_core's own data_set_type() uses to tell VSAM cluster types
apart) and is tolerant of surrounding whitespace/report formatting. There
was no real system available to calibrate these regexes against -- treat
them as a starting point to verify/tune against real LISTCAT output. Any
field that doesn't match is left None, not an error.
"""
from __future__ import annotations

import re
from pathlib import Path

from .blocks import split_named_blocks
from .models import CatalogDataset, VsamCluster

_CLUSTER_HDR = re.compile(r"^\s*CLUSTER\s*-+\s*(\S+)", re.IGNORECASE)
_DATA_HDR = re.compile(r"^\s*DATA\s*-+\s*(\S+)", re.IGNORECASE)
_INDEX_HDR = re.compile(r"^\s*INDEX\s*-+\s*(\S+)", re.IGNORECASE)
_VOLSER = re.compile(r"\bVOLSER-+([A-Za-z0-9$#@]+)", re.IGNORECASE)
_KEYLEN = re.compile(r"\bKEYLEN-+(\d+)", re.IGNORECASE)
_RKP = re.compile(r"\bRKP-+(\d+)", re.IGNORECASE)
_CLUSTER_TYPE_KEYWORDS = (
    ("INDEXED", "KSDS"),
    ("NONINDEXED", "ESDS"),
    ("LINEAR", "LINEAR"),
    ("NUMBERED", "RRDS"),
)


def _parse_nonvsam(lines: list[str]) -> list[CatalogDataset]:
    datasets_ = []
    for line in lines:
        fields = line.split()
        if not fields:
            continue
        dsn, volser, dsorg, recfm, lrecl, blksize = (fields + ["?"] * 6)[:6]
        datasets_.append(CatalogDataset(
            dsn=dsn,
            volser=None if volser == "?" else volser,
            dsorg=None if dsorg == "?" else dsorg,
            recfm=None if recfm == "?" else recfm,
            lrecl=None if lrecl == "?" else int(lrecl),
            blksize=None if blksize == "?" else int(blksize),
        ))
    return datasets_


def _parse_listcat(lines: list[str]) -> list[VsamCluster]:
    clusters: list[VsamCluster] = []
    current: VsamCluster | None = None

    for line in lines:
        cluster_match = _CLUSTER_HDR.match(line)
        if cluster_match:
            current = VsamCluster(name=cluster_match.group(1))
            clusters.append(current)
            continue

        if current is None:
            continue

        data_match = _DATA_HDR.match(line)
        if data_match:
            current.data_component = data_match.group(1)
            continue

        index_match = _INDEX_HDR.match(line)
        if index_match:
            current.index_component = index_match.group(1)
            continue

        volser_match = _VOLSER.search(line)
        if volser_match and current.volser is None:
            current.volser = volser_match.group(1)

        keylen_match = _KEYLEN.search(line)
        if keylen_match and current.key_length is None:
            current.key_length = int(keylen_match.group(1))

        rkp_match = _RKP.search(line)
        if rkp_match and current.key_offset is None:
            current.key_offset = int(rkp_match.group(1))

        if current.cluster_type is None:
            for keyword, cluster_type in _CLUSTER_TYPE_KEYWORDS:
                if re.search(r"\b{}\b".format(keyword), line, re.IGNORECASE):
                    current.cluster_type = cluster_type
                    break

    return clusters


def parse_catalog(path: Path) -> tuple[list[CatalogDataset], list[VsamCluster]]:
    """Parse one extrcat.py dump into (non-VSAM datasets, VSAM clusters)."""
    text = path.read_text(errors="replace")
    blocks = split_named_blocks(text)
    return (
        _parse_nonvsam(blocks.get("NONVSAM", [])),
        _parse_listcat(blocks.get("LISTCAT", [])),
    )
