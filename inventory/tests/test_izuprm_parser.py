from pathlib import Path

from inventory import izuprm_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_statements():
    return izuprm_parser.parse_izuprm_snapshot(FIXTURES / "sample_izuprm_snapshot.txt")


def by_stmt(statements, name):
    return [s for s in statements if s.stmt == name]


def test_simple_paren_value_statements_captured():
    statements = load_statements()
    assert by_stmt(statements, "HOSTNAME")[0].operands == "('s0w1.dal-ebis.ihost.com')"
    assert by_stmt(statements, "HTTP_SSL_PORT")[0].operands == "(10443)"
    assert by_stmt(statements, "SESSION_EXPIRE")[0].operands == "(495)"


def test_sub_keyword_statements_captured_generically():
    statements = load_statements()
    assert by_stmt(statements, "INCIDENT_LOG")[0].operands == "UNIT('SYSALLDA')"
    assert by_stmt(statements, "RESTAPI_FILE")[0].operands == (
        "ACCT(IZUACCT) REGION(65536) PROC(IZUFPROC)"
    )
    assert by_stmt(statements, "SEC_GROUPS")[0].operands == (
        "USER(IZUUSER),ADMIN(IZUADMIN),SECADMIN(IZUSECAD)"
    )


def test_quoted_value_spanning_two_physical_lines_folded_together():
    statements = load_statements()
    logging = by_stmt(statements, "LOGGING")[0]
    assert logging.operands == (
        "('*=warning:com.ibm.zoszmf.*=info:com.ibm.zoszmf.environment.ui= finer')"
    )


def test_multi_line_statement_without_trailing_comma_continuation():
    statements = load_statements()
    wlm = by_stmt(statements, "WLM_CLASSES")[0]
    assert wlm.operands == "DEFAULT(IZUGHTTP) LONG_WORK(IZUGWORK)"


def test_repeated_statement_keeps_both_occurrences_in_order():
    statements = load_statements()
    csrf = by_stmt(statements, "CSRF_SWITCH")
    assert [s.operands for s in csrf] == ["(ON)", "(OFF)"]


def test_fully_commented_out_statements_disappear():
    statements = load_statements()
    assert by_stmt(statements, "AUTOSTART_GROUP") == []


def test_plugins_list_spanning_many_continuation_lines():
    statements = load_statements()
    plugins = by_stmt(statements, "PLUGINS")[0]
    assert plugins.operands == (
        "( INCIDENT_LOG, COMMSERVER_CFG, WORKLOAD_MGMT RESOURCE_MON, "
        "CAPACITY_PROV, SOFTWARE_MGMT, SYSPLEX_MGMT, ISPF)"
    )


def test_source_member_set_for_every_statement():
    statements = load_statements()
    assert all(s.source_member == "IZUPRM00" for s in statements)
