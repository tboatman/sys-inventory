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


def test_profile_simple_statements_parsed_generically():
    _, statements = load_tcpip()
    by_stmt = {s.stmt: s.operands for s in statements if s.stmt in {"ARPAGE", "GLOBALCONFIG", "SOMAXCONN", "UDPCONFIG"}}
    assert by_stmt == {
        "ARPAGE": "20",
        "GLOBALCONFIG": "NOTCPIPSTATISTICS",
        "SOMAXCONN": "10",
        "UDPCONFIG": "RESTRICTLOWPORTS",
    }


def test_profile_repeated_statement_keyword_captured_separately():
    _, statements = load_tcpip()
    tcpconfigs = [s.operands for s in statements if s.stmt == "TCPCONFIG"]
    assert tcpconfigs == ["TTLS", "TCPSENDBFRSIZE 16K TCPRCVBUFRSIZE 16K SENDGARBAGE FALSE"]


def test_profile_interface_continuation_lines_folded_into_one_statement():
    _, statements = load_tcpip()
    interfaces = [s.operands for s in statements if s.stmt == "INTERFACE"]
    assert interfaces == [
        "QDIOLE2 DEFINE IPAQENET IPADDR 10.1.1.2/24 PORTNAME QDIOE2",
        "HPRIP DEFINE VIRTUAL IPADDR 10.1.1.1",
    ]


def test_profile_start_statement_ends_interface_continuation():
    _, statements = load_tcpip()
    by_stmt = [(s.stmt, s.operands) for s in statements]
    assert ("START", "QDIOLE2") in by_stmt


def test_profile_beginroutes_endroutes_block():
    _, statements = load_tcpip()
    by_stmt = {s.stmt: s.operands for s in statements if s.stmt in {"BEGINROUTES", "ENDROUTES"}}
    assert by_stmt["ENDROUTES"] == ""
    assert by_stmt["BEGINROUTES"] == (
        "ROUTE 10.1.1.0/24 = QDIOLE2 MTU 1500 ROUTE DEFAULT 10.1.1.254 QDIOLE2 MTU DEFAULTSIZE"
    )


def test_profile_autolog_block_excludes_commented_entries():
    _, statements = load_tcpip()
    by_stmt = {s.stmt: s.operands for s in statements if s.stmt in {"AUTOLOG", "ENDAUTOLOG"}}
    assert by_stmt["AUTOLOG"] == "FTPD TN3270"
    assert by_stmt["ENDAUTOLOG"] == ""


def test_profile_port_table_folded_and_commented_reservation_excluded():
    _, statements = load_tcpip()
    (port_operands,) = [s.operands for s in statements if s.stmt == "PORT"]
    assert port_operands == "7 UDP MISCSERV 7 TCP MISCSERV 21 TCP FTPD1 23 TCP TN3270"
    assert "25" not in port_operands


def test_profile_smfconfig_indented_statement_not_treated_as_continuation():
    _, statements = load_tcpip()
    smfconfigs = [s.operands for s in statements if s.stmt == "SMFCONFIG"]
    assert smfconfigs == [
        "TYPE118 TCPINIT TCPTERM FTPCLIENT TN3270CLIENT TCPIPSTATISTICS",
        "TYPE119 DVIPA FTPCLIENT IFSTATISTICS IPSECURITY PORTSTATISTICS PROFILE",
    ]


def test_profile_statement_count():
    _, statements = load_tcpip()
    assert len(statements) == 20


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
