"""Tests for parmlib_engines.py: the shared flat-keyword and
statement-oriented parsing engines factored out of ieasys_parser.py/
bpxprm_parser.py, so future Category B/C domains (doc/TODO.md "9.1") can
rely on this contract directly instead of each domain's own test file
being the only thing exercising it."""
from __future__ import annotations

from inventory.parmlib_engines import flat_keyword_engine, split_params, statement_engine


def test_flat_keyword_engine_splits_comma_separated_keywords():
    lines = ["SSN=(BN),CMD=(BN),PROD=(BN),", "REAL=(4096,ONLINE),CLPA,"]
    params = flat_keyword_engine(lines)
    assert params["SSN"] == "(BN)"
    assert params["REAL"] == "(4096,ONLINE)"
    assert params["CLPA"] is None  # bare keyword, no '='


def test_flat_keyword_engine_keeps_last_keyword_with_no_trailing_comma():
    params = flat_keyword_engine(["SSN=(BN),CMD=(BN)"])
    assert params["CMD"] == "(BN)"


def test_flat_keyword_engine_strips_comments():
    params = flat_keyword_engine(["SSN=(BN), /* comment */ CMD=(BN),"])
    assert params["SSN"] == "(BN)"
    assert params["CMD"] == "(BN)"


def test_statement_engine_groups_continuation_lines_under_current_statement():
    lines = [
        "ROOT FILESYSTEM('OMVS.ROOT.ZFS')",
        "     TYPE(ZFS) MODE(RDWR)",
        "MAXPROCSYS(3000)",
    ]
    statements = statement_engine(lines, {"ROOT", "MAXPROCSYS"})
    assert statements == [
        ("ROOT", "FILESYSTEM('OMVS.ROOT.ZFS') TYPE(ZFS) MODE(RDWR)"),
        ("MAXPROCSYS", "(3000)"),
    ]


def test_statement_engine_unrecognized_leading_keyword_is_dropped_not_crashed():
    # No prior statement to fold into -- documented limitation, not a bug.
    statements = statement_engine(["UNKNOWNSTMT(1)", "TZ(EST5EDT)"], {"TZ"})
    assert statements == [("TZ", "(EST5EDT)")]


def test_split_params_tracks_paren_depth():
    assert split_params("A=(1,2),B=3") == {"A": "(1,2)", "B": "3"}
