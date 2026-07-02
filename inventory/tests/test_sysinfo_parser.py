from pathlib import Path

from inventory import sysinfo_parser

FIXTURES = Path(__file__).parent / "fixtures"


def test_sysname_sysclone_sysplex_parsed():
    info = sysinfo_parser.parse_sysinfo(FIXTURES / "sample_sysinfo.txt")
    assert info.sysname == "SYS1"
    assert info.sysclone == "S1"
    assert info.sysplex == "PLEX1"


def test_ipl_volume_and_parm_parsed():
    info = sysinfo_parser.parse_sysinfo(FIXTURES / "sample_sysinfo.txt")
    assert info.ipl_volume == "RES0S1"
    assert info.ipl_parm_member == "00"


def test_release_and_archlvl_parsed():
    info = sysinfo_parser.parse_sysinfo(FIXTURES / "sample_sysinfo.txt")
    assert info.release == "z/OS 02.05.00"
    assert info.archlvl == "2"


def test_missing_field_yields_none(tmp_path):
    text = (
        "##SYMBOLS\n"
        "IEA007I STATIC SYSTEM SYMBOL VALUES 754\n"
        "&SYSCLONE.         = \"S2\"\n"
        "&SYSNAME.          = \"SYS2\"\n"
        "##IPLINFO\n"
        "IEASYS LIST = (01)\n"
        "IPL DEVICE: ORIGINAL(0A348) CURRENT(0A348) VOLUME(RES0S2)\n"
    )
    path = tmp_path / "sysinfo.txt"
    path.write_text(text)

    info = sysinfo_parser.parse_sysinfo(path)
    assert info.sysname == "SYS2"
    assert info.sysclone == "S2"
    assert info.sysplex is None
    assert info.ipl_volume == "RES0S2"
    assert info.ipl_parm_member == "01"
    assert info.release is None
    assert info.archlvl is None


def test_ieasys_list_with_multiple_groups_uses_first_suffix_of_first_group():
    # Real reply shape: "IEASYS LIST = (BN) (OP)" -- multiple parenthesized
    # groups, each possibly comma-separated. ipl_parm_member is the first
    # suffix of the first group only (the same suffix
    # discover_active_parmlib_suffixes.yml treats as primary).
    info = sysinfo_parser.parse_sysinfo(FIXTURES / "sample_sysinfo.txt")
    assert info.ipl_parm_member == "00"
