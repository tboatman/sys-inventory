from pathlib import Path

from inventory import catalog_parser

FIXTURES = Path(__file__).parent / "fixtures"


def test_nonvsam_datasets_parsed():
    datasets, _clusters = catalog_parser.parse_catalog(FIXTURES / "sample_catalog.txt")
    assert len(datasets) == 2

    loadlib = next(d for d in datasets if d.dsn == "MY.SITE.LOADLIB")
    assert loadlib.volser == "VOL001"
    assert loadlib.dsorg == "PO"
    assert loadlib.recfm == "FB"
    assert loadlib.lrecl == 80
    assert loadlib.blksize == 27920

    seqfile = next(d for d in datasets if d.dsn == "MY.SITE.SEQFILE")
    assert seqfile.volser == "VOL002"
    assert seqfile.lrecl == 133


def test_vsam_cluster_fully_parsed():
    _datasets, clusters = catalog_parser.parse_catalog(FIXTURES / "sample_catalog.txt")
    ksds = next(c for c in clusters if c.name == "MY.VSAM.KSDS1")

    assert ksds.cluster_type == "KSDS"
    assert ksds.volser == "VOL001"
    assert ksds.key_length == 20
    assert ksds.key_offset == 0
    assert ksds.data_component == "MY.VSAM.KSDS1.DATA"
    assert ksds.index_component == "MY.VSAM.KSDS1.INDEX"


def test_vsam_cluster_missing_fields_are_none():
    _datasets, clusters = catalog_parser.parse_catalog(FIXTURES / "sample_catalog.txt")
    esds = next(c for c in clusters if c.name == "MY.VSAM.ESDS1")

    assert esds.cluster_type == "ESDS"
    assert esds.data_component == "MY.VSAM.ESDS1.DATA"
    assert esds.index_component is None
    assert esds.volser is None
    assert esds.key_length is None
    assert esds.key_offset is None
