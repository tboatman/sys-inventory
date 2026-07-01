from inventory.blocks import split_named_blocks


def test_splits_multiple_blocks():
    text = "##FIRST\nline1\nline2\n##SECOND\nline3\n"
    blocks = split_named_blocks(text)
    assert blocks == {"FIRST": ["line1", "line2"], "SECOND": ["line3"]}


def test_lines_before_first_sentinel_are_discarded():
    text = "preamble\n##ONLY\ncontent\n"
    blocks = split_named_blocks(text)
    assert blocks == {"ONLY": ["content"]}


def test_no_sentinels_yields_empty_dict():
    assert split_named_blocks("just plain text\nno sentinels\n") == {}
