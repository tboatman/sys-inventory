"""CLI entry point: `inventory ingest`, `inventory lineage`, `inventory report`,
`inventory subsystems`, `inventory started-tasks`, `inventory sysinfo`,
`inventory products`, `inventory active`, `inventory processes`,
`inventory catalog`, `inventory vsam`, `inventory racf-users`,
`inventory racf-groups`, `inventory racf-connections`,
`inventory racf-dataset-profiles`, `inventory racf-dataset-access`,
`inventory racf-resource-profiles`, `inventory racf-resource-access`,
`inventory uss-mounts`, `inventory jes2parm`."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import (
    activity_parser,
    catalog_parser,
    ifaprd_parser,
    jcl_parser,
    jes2parm_parser,
    racf_parser,
    smpe_parser,
    ssn_parser,
    store,
    sysinfo_parser,
    uss_mounts_parser,
)
from .models import RacfSnapshot
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

    racf_file = input_dir / "racf.txt"
    racf_snapshot = racf_parser.parse_racf(racf_file) if racf_file.exists() else RacfSnapshot()

    uss_mounts = [m for path in sorted(input_dir.glob("*uss_mounts*.txt"))
                  for m in uss_mounts_parser.parse_uss_mounts(path)]

    jes2_init_statements = [s for path in sorted(input_dir.glob("*jes2parm*.txt"))
                             for s in jes2parm_parser.parse_dump(path)]

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
    store.save_racf_snapshot(conn, racf_snapshot)
    store.save_uss_mounts(conn, uss_mounts)
    store.save_jes2_init_statements(conn, jes2_init_statements)
    conn.close()

    total_steps = sum(len(v) for v in lineage.values())
    print(f"inventory: ingested {len(members)} members, {len(zones)} zones, "
          f"{total_steps} resolved steps, {len(subsystems)} subsystems, "
          f"{len(started_tasks)} started tasks, {len(products)} products, "
          f"{len(active_jobs)} active jobs, {len(processes)} processes, "
          f"{len(catalog_datasets)} cataloged datasets, "
          f"{len(vsam_clusters)} VSAM clusters, "
          f"{len(racf_snapshot.users)} RACF users, "
          f"{len(racf_snapshot.groups)} RACF groups, "
          f"{len(uss_mounts)} USS mounts, "
          f"{len(jes2_init_statements)} JES2 init statements -> {args.db}")
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
        owner = row["owner"] or "?"
        job_class = row["job_class"] or "?"
        svc_class = row["svc_class"] or "?"
        system = row["system"] or "?"
        print(f"{row['job_id']} {row['name']}  TYPE={job_type} ASID={asid} OWNER={owner} "
              f"JOBCLASS={job_class} SVCCLASS={svc_class} SYSTEM={system}")
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


def _bool_str(value) -> str:
    if value is None:
        return "?"
    return "YES" if value else "NO"


def cmd_racf_users(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_racf_users(conn)
    conn.close()

    for row in rows:
        name = row["name"] or "?"
        owner = row["owner"] or "?"
        default_group = row["default_group"] or "?"
        print(f"{row['userid']}  NAME={name} OWNER={owner} DFLTGRP={default_group} "
              f"SPECIAL={_bool_str(row['special'])} OPERATIONS={_bool_str(row['operations'])} "
              f"AUDITOR={_bool_str(row['auditor'])} REVOKED={_bool_str(row['revoked'])} "
              f"RESTRICTED={_bool_str(row['restricted'])}")
    return 0


def cmd_racf_groups(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_racf_groups(conn)
    conn.close()

    for row in rows:
        superior = row["superior_group"] or "?"
        owner = row["owner"] or "?"
        uacc = row["universal_access"] or "?"
        print(f"{row['name']}  SUPGROUP={superior} OWNER={owner} UACC={uacc}")
    return 0


def cmd_racf_connections(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_racf_group_connections(conn)
    conn.close()

    for row in rows:
        uacc = row["group_universal_access"] or "?"
        print(f"{row['userid']} in {row['grp']}  UACC={uacc} "
              f"GRP-SPECIAL={_bool_str(row['group_special'])} "
              f"GRP-OPERATIONS={_bool_str(row['group_operations'])} "
              f"GRP-AUDITOR={_bool_str(row['group_auditor'])} "
              f"REVOKED={_bool_str(row['revoked_in_group'])}")
    return 0


def cmd_racf_dataset_profiles(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_racf_dataset_profiles(conn)
    conn.close()

    for row in rows:
        volume = row["volume"] or "?"
        owner = row["owner"] or "?"
        uacc = row["universal_access"] or "?"
        audit_level = row["audit_level"] or "?"
        print(f"{row['profile']}  VOLUME={volume} GENERIC={_bool_str(row['generic'])} "
              f"OWNER={owner} UACC={uacc} AUDIT={audit_level}")
    return 0


def cmd_racf_dataset_access(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_racf_dataset_access(conn)
    conn.close()

    for row in rows:
        access = row["access"] or "?"
        print(f"{row['profile']}  {row['auth_id']}={access}")
    return 0


def cmd_racf_resource_profiles(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_racf_general_resource_profiles(conn)
    conn.close()

    for row in rows:
        owner = row["owner"] or "?"
        uacc = row["universal_access"] or "?"
        audit_level = row["audit_level"] or "?"
        print(f"{row['class_name']}/{row['profile']}  OWNER={owner} UACC={uacc} AUDIT={audit_level}")
    return 0


def cmd_racf_resource_access(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_racf_general_resource_access(conn)
    conn.close()

    for row in rows:
        access = row["access"] or "?"
        print(f"{row['class_name']}/{row['profile']}  {row['auth_id']}={access}")
    return 0


def cmd_uss_mounts(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_uss_mounts(conn)
    conn.close()

    for row in rows:
        name = row["name"] or "?"
        fs_type = row["fs_type"] or "?"
        device = row["device"] or "?"
        status = row["status"] or "?"
        mode = row["mode"] or "?"
        print(f"{row['path']}  NAME={name} TYPE={fs_type} DEVICE={device} "
              f"STATUS={status} MODE={mode}")
    return 0


def cmd_jes2parm(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_jes2_init_statements(conn)
    conn.close()

    for row in rows:
        subscript = f"({row['subscript']})" if row["subscript"] else ""
        params = ",".join(f"{k}={v}" for k, v in json.loads(row["params_json"]).items())
        print(f"{row['stmt']}{subscript}  {params}  [{row['source_member']}]")
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

    p_racf_users = sub.add_parser("racf-users", help="list RACF users (implementation only, not yet production-validated)")
    p_racf_users.set_defaults(func=cmd_racf_users)

    p_racf_groups = sub.add_parser("racf-groups", help="list RACF groups (implementation only, not yet production-validated)")
    p_racf_groups.set_defaults(func=cmd_racf_groups)

    p_racf_connections = sub.add_parser("racf-connections", help="list RACF user-to-group connections (implementation only, not yet production-validated)")
    p_racf_connections.set_defaults(func=cmd_racf_connections)

    p_racf_ds_profiles = sub.add_parser("racf-dataset-profiles", help="list RACF DATASET-class profiles (implementation only, not yet production-validated)")
    p_racf_ds_profiles.set_defaults(func=cmd_racf_dataset_profiles)

    p_racf_ds_access = sub.add_parser("racf-dataset-access", help="list RACF DATASET-class access lists (implementation only, not yet production-validated)")
    p_racf_ds_access.set_defaults(func=cmd_racf_dataset_access)

    p_racf_gr_profiles = sub.add_parser("racf-resource-profiles", help="list RACF general-resource profiles, curated classes only (implementation only, not yet production-validated)")
    p_racf_gr_profiles.set_defaults(func=cmd_racf_resource_profiles)

    p_racf_gr_access = sub.add_parser("racf-resource-access", help="list RACF general-resource access lists, curated classes only (implementation only, not yet production-validated)")
    p_racf_gr_access.set_defaults(func=cmd_racf_resource_access)

    p_uss_mounts = sub.add_parser("uss-mounts", help="list mounted USS filesystems (not yet production-validated)")
    p_uss_mounts.set_defaults(func=cmd_uss_mounts)

    p_jes2parm = sub.add_parser("jes2parm", help="list JES2's own initialization statements (not yet production-validated)")
    p_jes2parm.set_defaults(func=cmd_jes2parm)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
