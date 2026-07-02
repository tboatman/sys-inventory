from pathlib import Path

from inventory import vtam_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_vtam():
    return vtam_parser.parse_vtam(FIXTURES / "sample_vtam.txt")


def test_major_nodes_parsed():
    nodes, _, _ = load_vtam()
    by_name = {n.name: n.status for n in nodes}
    assert by_name == {"VTAMLST": "ACT/S", "NCPMAJ": "ACTIV", "APPLMAJ": "INACT"}


def test_banner_and_header_lines_not_treated_as_major_nodes():
    nodes, _, _ = load_vtam()
    assert len(nodes) == 3


def test_ist1454i_summary_line_not_treated_as_a_major_node():
    # Confirmed against a real 'D NET,MAJNODES' reply: the real summary
    # line is "IST1454I n RESOURCE(S) DISPLAYED", not the originally
    # guessed "IST075I NAME STATUS" header -- covered implicitly by the
    # exact-3-nodes count above, asserted explicitly here too.
    nodes, _, _ = load_vtam()
    assert "3" not in {n.name for n in nodes}


def test_start_options_parsed_generically():
    # Confirmed against a real 'D NET,VTAMOPTS' reply: two KEYWORD=VALUE
    # pairs per line is the common case, not one per line as originally
    # guessed.
    _, options, _ = load_vtam()
    by_keyword = {o.keyword: o.value for o in options}
    assert by_keyword == {
        "ALSREQ": "NO",
        "API64R": "YES",
        "AIMON": "(EQDIO,IQDIO,ISM,QDIO,ROCE)",
        "NODETYPE": "NN",
        "CPNAME": "NN01",
        "NETID": "USIBMSC",
        "SSCPID": "1",
        "HPRPST": "LOW",
    }


def test_appn_enablement_visible_via_nodetype_keyword():
    _, options, _ = load_vtam()
    nodetype = next(o for o in options if o.keyword == "NODETYPE")
    assert nodetype.value == "NN"


def test_parenthesized_value_captured_as_one_token():
    _, options, _ = load_vtam()
    aimon = next(o for o in options if o.keyword == "AIMON")
    assert aimon.value == "(EQDIO,IQDIO,ISM,QDIO,ROCE)"


def test_two_token_value_is_truncated_to_first_token_known_limitation():
    # Confirmed, documented limitation (see vtam_parser.py's module
    # docstring): a value like "LOW          480S" only captures "LOW" --
    # doesn't affect NODETYPE/CPNAME or the vast majority of keywords.
    _, options, _ = load_vtam()
    hprpst = next(o for o in options if o.keyword == "HPRPST")
    assert hprpst.value == "LOW"


def test_topology_summary_parsed():
    _, _, topology = load_vtam()
    assert topology is not None
    assert topology.last_checkpoint == "NONE"
    assert (topology.adj, topology.nn, topology.en, topology.served_en,
            topology.cdservr, topology.icn, topology.bn) == (1, 2, 0, 0, 0, 0, 0)


def test_topology_checkpoint_dataset_and_garbage_collection_parsed():
    _, _, topology = load_vtam()
    assert topology.initdb_checkpoint_dataset == "NONE"
    assert topology.last_garbage_collection == "01/01/26 00:00:00"


def test_topology_absent_returns_none(tmp_path):
    dump = tmp_path / "vtam.txt"
    dump.write_text("##MAJNODES\n##VTAMOPTS\n")
    _, _, topology = vtam_parser.parse_vtam(dump)
    assert topology is None
