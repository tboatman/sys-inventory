from pathlib import Path

from inventory import tcpip_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_tcpip():
    return tcpip_parser.parse_tcpip(FIXTURES / "sample_tcpip.txt")


def test_home_addresses_parsed():
    addresses, _ = load_tcpip()
    by_link = {a.link_name: a.ip_address for a in addresses}
    assert by_link == {
        "EZASAMEMVS": "10.1.1.1",
        "EZAXCFS1": "10.1.1.1",
        "LOOPBACK": "127.0.0.1",
        "QDIOLE2": "10.1.1.2",
        "HPRIP": "10.1.1.1",
        "LOOPBACK6": "::1",
    }


def test_intfname_rows_parsed_same_as_linkname_rows():
    addresses, _ = load_tcpip()
    assert {a.link_name for a in addresses} >= {"QDIOLE2", "HPRIP", "LOOPBACK6"}


def test_primary_flag_parsed():
    addresses, _ = load_tcpip()
    by_link = {a.link_name: a.is_primary for a in addresses}
    assert by_link["QDIOLE2"] is True
    assert by_link["EZASAMEMVS"] is False
    assert by_link["LOOPBACK6"] is False


def test_profile_statements_parsed_generically():
    _, statements = load_tcpip()
    by_stmt = {s.stmt: s.operands for s in statements}
    assert by_stmt == {
        "HOSTNAME": "MVSTCPIP",
        "DEVICE": "OSA2080 MPCIPA",
        "LINK": "ETH0LINK IPAQENET OSA2080",
        "HOME": "10.1.1.2 ETH0LINK",
    }


def test_profile_comment_line_skipped():
    _, statements = load_tcpip()
    stmts = [s.stmt for s in statements]
    assert ";" not in stmts
    assert len(statements) == 4


def test_source_dsn_marker_parsed():
    _, statements = load_tcpip()
    assert all(s.source_dsn == "TCPIP.TCPPARMS(PROFILE1)" for s in statements)


def test_profile_omitted_without_source_dsn_marker(tmp_path):
    dump = tmp_path / "tcpip_no_profile.txt"
    dump.write_text("##NETSTAT_HOME\nLINKNAME: ETH0LINK\nADDRESS: 10.1.1.2\n")
    addresses, statements = tcpip_parser.parse_tcpip(dump)
    assert len(addresses) == 1
    assert addresses[0].link_name == "ETH0LINK"
    assert addresses[0].ip_address == "10.1.1.2"
    assert statements == []
