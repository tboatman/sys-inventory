from pathlib import Path

from inventory import vtam_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_vtam():
    return vtam_parser.parse_vtam(FIXTURES / "sample_vtam.txt")


def test_major_nodes_parsed():
    nodes, _ = load_vtam()
    by_name = {n.name: n.status for n in nodes}
    assert by_name == {"VTAMLST": "ACT/S", "NCPMAJ": "ACTIV", "APPLMAJ": "INACT"}


def test_banner_and_header_lines_not_treated_as_major_nodes():
    nodes, _ = load_vtam()
    assert len(nodes) == 3


def test_start_options_parsed_generically():
    _, options = load_vtam()
    by_keyword = {o.keyword: o.value for o in options}
    assert by_keyword == {
        "NODETYPE": "NN",
        "CPNAME": "NN01",
        "NETID": "USIBMSC",
        "SSCPID": "1",
    }


def test_appn_enablement_visible_via_nodetype_keyword():
    _, options = load_vtam()
    nodetype = next(o for o in options if o.keyword == "NODETYPE")
    assert nodetype.value == "NN"
