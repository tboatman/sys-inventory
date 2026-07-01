"""CLI entry point: `inventory ingest`, `inventory lineage`, `inventory report`."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import jcl_parser, smpe_parser, store
from .resolver import resolve_all

DEFAULT_DB = Path("inventory.db")


def _read_lnklst(input_dir: Path) -> list[str]:
    lnklst_file = input_dir / "lnklst.txt"
    if not lnklst_file.exists():
        return []
    return [line.strip() for line in lnklst_file.read_text().splitlines() if line.strip()]


def cmd_ingest(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"inventory: {input_dir} is not a directory", file=sys.stderr)
        return 1

    members = []
    for path in sorted(input_dir.glob("*proclib*.txt")) + sorted(input_dir.glob("*parmlib*.txt")):
        members.extend(jcl_parser.parse_dump(path))

    zone_maps = [smpe_parser.parse_smplist(p) for p in sorted(input_dir.glob("*smplist*.txt"))]
    zones = smpe_parser.merge_zones(*zone_maps) if zone_maps else {}

    lnklst = _read_lnklst(input_dir)

    lineage = resolve_all(members, zones, lnklst)

    conn = store.connect(Path(args.db))
    store.save_lineage(conn, lineage)
    conn.close()

    total_steps = sum(len(v) for v in lineage.values())
    print(f"inventory: ingested {len(members)} members, {len(zones)} zones, "
          f"{total_steps} resolved steps -> {args.db}")
    return 0


def cmd_lineage(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.lineage_for_member(conn, args.member)
    conn.close()

    if not rows:
        print(f"inventory: no lineage found for member {args.member}", file=sys.stderr)
        return 1

    print(f"{args.member}")
    for row in rows:
        pgm = row["pgm"] or "(no PGM)"
        zone = row["zone"] or "?"
        fmid = row["fmid"] or "?"
        dataset = row["dataset"] or "?"
        print(f"  step {row['step_name']}: PGM={pgm} dataset={dataset} zone={zone} "
              f"FMID={fmid}  [{row['resolution']}]")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_lineage(conn)
    conn.close()

    fieldnames = ["member", "step_name", "pgm", "dataset", "zone", "fmid", "resolution"]
    out = sys.stdout if args.output == "-" else open(args.output, "w", newline="")
    try:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in fieldnames})
    finally:
        if out is not sys.stdout:
            out.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="inventory")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite inventory database path")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="parse extracted PROCLIB/PARMLIB + SMP/E dumps and resolve lineage")
    p_ingest.add_argument("input_dir", help="directory containing the downloaded zos-extract output")
    p_ingest.set_defaults(func=cmd_ingest)

    p_lineage = sub.add_parser("lineage", help="show the resolved execution path for one member")
    p_lineage.add_argument("member", help="PROCLIB/PARMLIB member name")
    p_lineage.set_defaults(func=cmd_lineage)

    p_report = sub.add_parser("report", help="dump the full resolved inventory as CSV")
    p_report.add_argument("--output", default="-", help="output file, or '-' for stdout")
    p_report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
