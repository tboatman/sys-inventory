from pathlib import Path

from inventory import cics_proc_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load():
    return cics_proc_parser.parse_cics_proc(FIXTURES / "sample_cics_deepening.txt")


def test_dfhrpl_entries_parsed():
    dfhrpl, _ = load()
    assert [(e.dsn, e.proc) for e in dfhrpl] == [
        ("CICS.SDFHLOAD", "CICSPROC"),
        ("MY.SITE.LOADLIB", "CICSPROC"),
    ]
    # zone/apf_authorized are left unset by the parser -- resolved later
    # at ingest time via resolver.dataset_zone()/apf.txt membership.
    assert dfhrpl[0].zone is None
    assert dfhrpl[0].apf_authorized is None


def test_sit_overrides_parsed_generically():
    _, overrides = load()
    by_keyword = {o.keyword: (o.value, o.proc) for o in overrides}
    assert by_keyword == {
        "APPLID": ("CICSA", "CICSPROC"),
        "GRPLIST": ("DFHLIST", "CICSPROC"),
        "SEC": ("YES", "CICSPROC"),
    }


def test_csd_block_not_modeled_by_this_parser():
    # ##CSD is consumed in-play by cics_deepening.yml to drive the
    # DFHCSDUP job and isn't re-parsed here -- cics_csdup_parser.py gets
    # the CSD dsn from its own ";;CSD_DSN=" marker instead.
    dfhrpl, overrides = load()
    assert len(dfhrpl) == 2
    assert len(overrides) == 3
