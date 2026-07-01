from pathlib import Path

from inventory import ifaprd_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_products():
    return ifaprd_parser.parse_products(FIXTURES / "sample_ifaprd.txt")


def test_enabled_product_parsed():
    products = load_products()
    eps = next(p for p in products if p.id == "5655-EPS")
    assert eps.name == "EMBEDDED RUNTIME ENABLEMENT FOR ZOS"
    assert eps.version == "*"
    assert eps.release == "*"
    assert eps.mod == "*"
    assert eps.featurename == "*"
    assert eps.state == "ENABLED"
    assert eps.source_member == "IFAPRD00"


def test_disabled_product_with_named_feature_parsed():
    products = load_products()
    zos = next(p for p in products if p.id == "5650-ZOS")
    assert zos.name == "SOME OPTIONAL FEATURE"
    assert zos.version == "2"
    assert zos.release == "5"
    assert zos.mod == "0"
    assert zos.featurename == "OPTFEAT"
    assert zos.state == "DISABLED"


def test_two_products_parsed():
    products = load_products()
    assert len(products) == 2
