"""CLI entry point: `inventory ingest`, `inventory lineage`, `inventory report`,
`inventory subsystems`, `inventory started-tasks`, `inventory sysinfo`,
`inventory products`, `inventory active`, `inventory processes`,
`inventory catalog`, `inventory vsam`."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import (
    activity_parser,
    catalog_parser,
    ifaprd_parser,
    jcl_parser,
    smpe_parser,
    ssn_parser,
    store,
    sysinfo_parser,
)
from .resolver import resolve_all

DEFAULT_DB = Path("inventory.db")


def _read_lnklst(input_dir: Path) -> list[str]:
    lnklst_file = input_dir / "lnklst.txt"
    if not lnklst_file.exists():
        return []
    return [line.strip() for line in lnklst_file.read_text().splitlines() if line.strip()]


def _read_apf(input_dir: Path) -> set[str] | None:
    apf_file = input_dir / "apf.txt"
    if not apf_file.exists():
        return None
    return {line.strip() for line in apf_file.read_text().splitlines() if line.strip()}


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
    apf = _read_apf(input_dir)

    lineage = resolve_all(members, zones, lnklst, apf)

    subsystems = [s for p in sorted(input_dir.glob("*ssn*.txt")) for s in ssn_parser.parse_subsystems(p)]
    started_tasks = [t for p in sorted(input_dir.glob("*commnd*.txt")) for t in ssn_parser.parse_started_tasks(p)]

    sysinfo_files = sorted(input_dir.glob("*sysinfo*.txt"))
    if len(sysinfo_files) > 1:
        print(f"inventory: {len(sysinfo_files)} sysinfo files found, using {sysinfo_files[0]}",
              file=sys.stderr)
    system_info = sysinfo_parser.parse_sysinfo(sysinfo_files[0]) if sysinfo_files else None

    products = [prod for path in sorted(input_dir.glob("*ifaprd*.txt"))
                for prod in ifaprd_parser.parse_products(path)]

    active_jobs_file = input_dir / "active_jobs.txt"
    active_jobs = activity_parser.parse_active_jobs(active_jobs_file) if active_jobs_file.exists() else []

    processes_file = input_dir / "processes.txt"
    processes = activity_parser.parse_processes(processes_file) if processes_file.exists() else []

    catalog_datasets = []
    vsam_clusters = []
    for path in sorted(input_dir.glob("*catalog*.txt")):
        ds, clusters = catalog_parser.parse_catalog(path)
        catalog_datasets.extend(ds)
        vsam_clusters.extend(clusters)

    conn = store.connect(Path(args.db))
    store.save_lineage(conn, lineage)
    store.save_subsystems(conn, subsystems)
    store.save_started_tasks(conn, started_tasks)
    store.save_system_info(conn, system_info)
    store.save_products(conn, products)
    store.save_active_jobs(conn, active_jobs)
    store.save_processes(conn, processes)
    store.save_catalog_datasets(conn, catalog_datasets)
    store.save_vsam_clusters(conn, vsam_clusters)
    conn.close()

    total_steps = sum(len(v) for v in lineage.values())
    print(f"inventory: ingested {len(members)} members, {len(zones)} zones, "
          f"{total_steps} resolved steps, {len(subsystems)} subsystems, "
          f"{len(started_tasks)} started tasks, {len(products)} products, "
          f"{len(active_jobs)} active jobs, {len(processes)} processes, "
          f"{len(catalog_datasets)} cataloged datasets, "
          f"{len(vsam_clusters)} VSAM clusters -> {args.db}")
    return 0


def _apf_str(apf_authorized) -> str:
    if apf_authorized is None:
        return "APF=?"
    return "APF" if apf_authorized else "non-APF"


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
        apf = _apf_str(row["apf_authorized"])
        print(f"  step {row['step_name']}: PGM={pgm} dataset={dataset} zone={zone} "
              f"FMID={fmid} [{apf}]  [{row['resolution']}]")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_lineage(conn)
    conn.close()

    fieldnames = ["member", "step_name", "pgm", "dataset", "zone", "fmid", "resolution", "apf_authorized"]
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


def cmd_subsystems(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_subsystems(conn)
    conn.close()

    for row in rows:
        initrtn = row["initrtn"] or "?"
        initparm = row["initparm"] or ""
        print(f"{row['name']}: INITRTN={initrtn} INITPARM='{initparm}' [{row['source_member']}]")
    return 0


def cmd_started_tasks(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_started_tasks(conn)
    conn.close()

    for row in rows:
        ident = f".{row['identifier']}" if row["identifier"] else ""
        print(f"S {row['task_name']}{ident}  [{row['source_member']}]")
    return 0


def cmd_sysinfo(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    row = store.get_system_info(conn)
    conn.close()

    if row is None:
        print("inventory: no system info ingested", file=sys.stderr)
        return 1

    print(f"SYSNAME:  {row['sysname'] or '?'}")
    print(f"SYSCLONE: {row['sysclone'] or '?'}")
    print(f"SYSPLEX:  {row['sysplex'] or '?'}")
    print(f"IPL VOLUME: {row['ipl_volume'] or '?'}")
    print(f"IPL PARM MEMBER: {row['ipl_parm_member'] or '?'}")
    print(f"RELEASE: {row['release'] or '?'}")
    print(f"ARCHLVL: {row['archlvl'] or '?'}")
    return 0


def cmd_products(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_products(conn)
    conn.close()

    for row in rows:
        name = row["name"] or "?"
        vrm = f"{row['version'] or '?'}.{row['release'] or '?'}.{row['mod'] or '?'}"
        feature = row["featurename"] or "?"
        state = row["state"] or "?"
        print(f"{row['id']}: {name}  VRM={vrm} FEATURENAME={feature} STATE={state}  "
              f"[{row['source_member']}]")
    return 0


def cmd_active(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_active_jobs(conn)
    conn.close()

    for row in rows:
        job_type = row["job_type"] or "?"
        asid = row["asid"] or "?"
        print(f"{row['job_id']} {row['name']}  TYPE={job_type} ASID={asid}")
    return 0


def cmd_processes(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_processes(conn)
    conn.close()

    for row in rows:
        print(row["command"])
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_catalog_datasets(conn)
    conn.close()

    for row in rows:
        volser = row["volser"] or "?"
        dsorg = row["dsorg"] or "?"
        recfm = row["recfm"] or "?"
        lrecl = row["lrecl"] if row["lrecl"] is not None else "?"
        blksize = row["blksize"] if row["blksize"] is not None else "?"
        print(f"{row['dsn']}  VOLSER={volser} DSORG={dsorg} RECFM={recfm} "
              f"LRECL={lrecl} BLKSIZE={blksize}")
    return 0


def cmd_vsam(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_vsam_clusters(conn)
    conn.close()

    for row in rows:
        cluster_type = row["cluster_type"] or "?"
        volser = row["volser"] or "?"
        key_length = row["key_length"] if row["key_length"] is not None else "?"
        key_offset = row["key_offset"] if row["key_offset"] is not None else "?"
        data = row["data_component"] or "?"
        index = row["index_component"] or "?"
        print(f"{row['name']}  TYPE={cluster_type} VOLSER={volser} "
              f"KEYLEN={key_length} RKP={key_offset} DATA={data} INDEX={index}")
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

    p_subsystems = sub.add_parser("subsystems", help="list defined subsystems (IEFSSNxx)")
    p_subsystems.set_defaults(func=cmd_subsystems)

    p_started = sub.add_parser("started-tasks", help="list auto-start started tasks (COMMNDxx)")
    p_started.set_defaults(func=cmd_started_tasks)

    p_sysinfo = sub.add_parser("sysinfo", help="show captured LPAR/sysplex identity")
    p_sysinfo.set_defaults(func=cmd_sysinfo)

    p_products = sub.add_parser("products", help="list product enablement status (IFAPRDxx)")
    p_products.set_defaults(func=cmd_products)

    p_active = sub.add_parser("active", help="list currently-active jobs/started tasks (live snapshot)")
    p_active.set_defaults(func=cmd_active)

    p_processes = sub.add_parser("processes", help="list currently-running USS processes (live snapshot)")
    p_processes.set_defaults(func=cmd_processes)

    p_catalog = sub.add_parser("catalog", help="list cataloged non-VSAM datasets (HLQ/pattern-scoped)")
    p_catalog.set_defaults(func=cmd_catalog)

    p_vsam = sub.add_parser("vsam", help="list VSAM clusters and their DATA/INDEX components (HLQ/pattern-scoped)")
    p_vsam.set_defaults(func=cmd_vsam)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
