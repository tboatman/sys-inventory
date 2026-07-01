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


def test_missing_field_yields_none(tmp_path):
    text = (
        "##SYMBOLS\n"
        "SYSTEM SYMBOL LIST\n"
        "SYSNAME  = &SYSNAME.  = \"SYS2\"\n"
        "SYSCLONE = &SYSCLONE. = \"S2\"\n"
        "##IPLINFO\n"
        "SYSTEM IPLED FROM 01A0  IPL PARM 01\n"
        "IPL DEVICE: 01A0  VOLUME: RES0S2\n"
    )
    path = tmp_path / "sysinfo.txt"
    path.write_text(text)

    info = sysinfo_parser.parse_sysinfo(path)
    assert info.sysname == "SYS2"
    assert info.sysclone == "S2"
    assert info.sysplex is None
    assert info.ipl_volume == "RES0S2"
    assert info.ipl_parm_member == "01"
