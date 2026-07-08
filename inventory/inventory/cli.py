"""CLI entry point: `inventory ingest`, `inventory lineage`, `inventory report`,
`inventory trace`,
`inventory subsystems`, `inventory started-tasks`, `inventory sysinfo`,
`inventory products`, `inventory active`, `inventory processes`,
`inventory catalog`, `inventory vsam`, `inventory racf-users`,
`inventory racf-groups`, `inventory racf-connections`,
`inventory racf-dataset-profiles`, `inventory racf-dataset-access`,
`inventory racf-resource-profiles`, `inventory racf-resource-access`,
`inventory uss-mounts`, `inventory jes2parm`, `inventory vtam-majnodes`,
`inventory vtam-options`, `inventory vtam-topology`,
`inventory tcpip-home`, `inventory tcpip-profile`,
`inventory sms-storgrps`,
`inventory wlm`, `inventory db2-packages`, `inventory db2-plans`,
`inventory wlm-zosmf`, `inventory cics-dfhrpl`, `inventory cics-sit`,
`inventory cics-csd`, `inventory cmci`, `inventory zone-index`, `inventory zones`,
`inventory fmids`, `inventory zone-gaps`, `inventory parmlib`,
`inventory ieasys`, `inventory bpxprm`, `inventory devsup`, `inventory opt`,
`inventory clock`, `inventory autor`, `inventory sched`, `inventory couple`,
`inventory grsrnl`, `inventory grscnf`, `inventory smf`, `inventory ios`, `inventory consol`,
`inventory igdsms`, `inventory izuprm`, `inventory diag`, `inventory iggcat`,
`inventory prog`."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import (
    activity_parser,
    autor_parser,
    bpxprm_parser,
    catalog_parser,
    cics_csdup_parser,
    cics_proc_parser,
    clock_parser,
    cmci_parser,
    consol_parser,
    couple_parser,
    db2_catalog_parser,
    devsup_parser,
    diag_parser,
    grscnf_parser,
    grsrnl_parser,
    ieasys_parser,
    ifaprd_parser,
    igdsms_parser,
    iggcat_parser,
    ios_parser,
    izuprm_parser,
    jcl_parser,
    jes2parm_parser,
    opt_parser,
    parmlib_parser,
    prog_parser,
    racf_parser,
    sched_parser,
    smf_parser,
    smpe_parser,
    sms_parser,
    ssn_parser,
    store,
    sysinfo_parser,
    tcpip_parser,
    uss_mounts_parser,
    vtam_parser,
    wlm_parser,
    wlm_zosmf_parser,
)
from .models import Fmid, RacfSnapshot
from .resolver import dataset_zone, resolve_all

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
    # *parmlib_snapshot*.txt is a 'D PARMLIB' console reply, not a member
    # dump -- excluded here the same way '*wlm*.txt' excludes
    # '*wlm_zosmf*.txt' below, since it'd otherwise also match '*parmlib*.txt'.
    parmlib_snapshot_files = set(input_dir.glob("*parmlib_snapshot*.txt"))
    parmlib_member_dumps = [p for p in input_dir.glob("*parmlib*.txt") if p not in parmlib_snapshot_files]
    for path in sorted(input_dir.glob("*proclib*.txt")) + sorted(parmlib_member_dumps):
        members.extend(jcl_parser.parse_dump(path))

    zone_maps = [smpe_parser.parse_smplist(p) for p in sorted(input_dir.glob("*smplist*.txt"))]
    zones = smpe_parser.merge_zones(*zone_maps) if zone_maps else {}

    zone_index_entries = [e for p in sorted(input_dir.glob("*smpzones*.txt"))
                           for e in smpe_parser.parse_globalzone(p)]

    fmids = [
        Fmid(fmid=fmid, zone=zone.name, status=status)
        for zone in zones.values()
        for fmid, status in zone.fmid_status.items()
    ]

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

    parmlib_datasets = [d for p in sorted(parmlib_snapshot_files)
                        for d in parmlib_parser.parse_parmlib_snapshot(p)]

    ieasys_statements = [s for p in sorted(input_dir.glob("*ieasys_snapshot*.txt"))
                         for s in ieasys_parser.parse_ieasys_snapshot(p)]

    bpxprm_statements = [s for p in sorted(input_dir.glob("*bpxprm_snapshot*.txt"))
                         for s in bpxprm_parser.parse_bpxprm_snapshot(p)]

    devsup_statements = [s for p in sorted(input_dir.glob("*devsup_snapshot*.txt"))
                         for s in devsup_parser.parse_devsup_snapshot(p)]

    opt_statements = [s for p in sorted(input_dir.glob("*opt_snapshot*.txt"))
                      for s in opt_parser.parse_opt_snapshot(p)]

    clock_statements = [s for p in sorted(input_dir.glob("*clock_snapshot*.txt"))
                        for s in clock_parser.parse_clock_snapshot(p)]

    autor_statements = [s for p in sorted(input_dir.glob("*autor_snapshot*.txt"))
                        for s in autor_parser.parse_autor_snapshot(p)]

    sched_statements = [s for p in sorted(input_dir.glob("*sched_snapshot*.txt"))
                        for s in sched_parser.parse_sched_snapshot(p)]

    couple_statements = [s for p in sorted(input_dir.glob("*couple_snapshot*.txt"))
                         for s in couple_parser.parse_couple_snapshot(p)]

    grscnf_statements = [s for p in sorted(input_dir.glob("*grscnf_snapshot*.txt"))
                         for s in grscnf_parser.parse_grscnf_snapshot(p)]

    grsrnl_statements = [s for p in sorted(input_dir.glob("*grsrnl_snapshot*.txt"))
                         for s in grsrnl_parser.parse_grsrnl_snapshot(p)]

    smf_statements = [s for p in sorted(input_dir.glob("*smf_snapshot*.txt"))
                      for s in smf_parser.parse_smf_snapshot(p)]

    ios_statements = [s for p in sorted(input_dir.glob("*ios_snapshot*.txt"))
                      for s in ios_parser.parse_ios_snapshot(p)]

    consol_statements = [s for p in sorted(input_dir.glob("*consol_snapshot*.txt"))
                         for s in consol_parser.parse_consol_snapshot(p)]

    igdsms_statements = [s for p in sorted(input_dir.glob("*igdsms_snapshot*.txt"))
                         for s in igdsms_parser.parse_igdsms_snapshot(p)]

    izuprm_statements = [s for p in sorted(input_dir.glob("*izuprm_snapshot*.txt"))
                         for s in izuprm_parser.parse_izuprm_snapshot(p)]

    diag_statements = [s for p in sorted(input_dir.glob("*diag_snapshot*.txt"))
                       for s in diag_parser.parse_diag_snapshot(p)]

    iggcat_statements = [s for p in sorted(input_dir.glob("*iggcat_snapshot*.txt"))
                         for s in iggcat_parser.parse_iggcat_snapshot(p)]

    prog_statements = [s for p in sorted(input_dir.glob("*prog_snapshot*.txt"))
                       for s in prog_parser.parse_prog_snapshot(p)]

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

    vtam_major_nodes = []
    vtam_start_options = []
    vtam_topology_summary = None
    vtam_files = sorted(input_dir.glob("*vtam*.txt"))
    if len(vtam_files) > 1:
        print(f"inventory: {len(vtam_files)} vtam files found, using {vtam_files[0]} "
              f"for the (single-record) topology summary", file=sys.stderr)
    for path in vtam_files:
        nodes, options, topology = vtam_parser.parse_vtam(path)
        vtam_major_nodes.extend(nodes)
        vtam_start_options.extend(options)
        if vtam_topology_summary is None:
            vtam_topology_summary = topology

    tcpip_home_addresses = []
    tcpip_profile_statements = []
    for path in sorted(input_dir.glob("*tcpip*.txt")):
        addresses, statements = tcpip_parser.parse_tcpip(path)
        tcpip_home_addresses.extend(addresses)
        tcpip_profile_statements.extend(statements)

    # Excludes '*igdsms*' matches -- that's a separate dimension (the
    # active IGDSMSxx PARMLIB member, see below), and '*sms*' would
    # otherwise also match its filename (igdsms_snapshot.txt contains
    # "sms" as a substring) -- same precedent as '*wlm*'/'*wlm_zosmf*'
    # below (doc/TODO.md "9.2").
    sms_storage_groups = []
    for path in sorted(input_dir.glob("*sms*.txt")):
        if "igdsms" in path.name:
            continue
        sms_storage_groups.extend(sms_parser.parse_sms(path))

    # Excludes '*wlm_zosmf*' matches -- that's a separate dimension (see
    # below), and '*wlm*' would otherwise also match its filename.
    wlm_files = sorted(p for p in input_dir.glob("*wlm*.txt") if "zosmf" not in p.name)
    if len(wlm_files) > 1:
        print(f"inventory: {len(wlm_files)} wlm files found, using {wlm_files[0]}",
              file=sys.stderr)
    wlm_policy = wlm_parser.parse_wlm(wlm_files[0]) if wlm_files else None

    db2_packages = []
    db2_plans = []
    for path in sorted(input_dir.glob("*db2_catalog*.txt")):
        packages, plans = db2_catalog_parser.parse_db2_catalog(path)
        db2_packages.extend(packages)
        db2_plans.extend(plans)

    wlm_zosmf_entries = [e for path in sorted(input_dir.glob("*wlm_zosmf*.txt"))
                         for e in wlm_zosmf_parser.parse_wlm_zosmf(path)]

    cics_dfhrpl_entries = []
    cics_sit_overrides = []
    cics_csd_definitions = []
    for path in sorted(input_dir.glob("*cics_deepening*.txt")):
        dfhrpl, sit = cics_proc_parser.parse_cics_proc(path)
        cics_dfhrpl_entries.extend(dfhrpl)
        cics_sit_overrides.extend(sit)
        cics_csd_definitions.extend(cics_csdup_parser.parse_cics_csdup(path))
    # Resolve each DFHRPL dataset to its owning SMP/E zone/APF status the
    # same way STEPLIB/JOBLIB/LNKLST hops already are in resolve_all()
    # above, via the same public helper (see resolver.dataset_zone()).
    for entry in cics_dfhrpl_entries:
        entry.zone = dataset_zone(entry.dsn, zones)
        entry.apf_authorized = None if apf is None else entry.dsn in apf

    cmci_resources = [r for path in sorted(input_dir.glob("*cics_cmci*.txt"))
                       for r in cmci_parser.parse_cmci(path)]

    conn = store.connect(Path(args.db))
    store.save_lineage(conn, lineage)
    store.save_subsystems(conn, subsystems)
    store.save_started_tasks(conn, started_tasks)
    store.save_system_info(conn, system_info)
    store.save_products(conn, products)
    store.save_parmlib_datasets(conn, parmlib_datasets)
    store.save_ieasys_statements(conn, ieasys_statements)
    store.save_bpxprm_statements(conn, bpxprm_statements)
    store.save_devsup_statements(conn, devsup_statements)
    store.save_opt_statements(conn, opt_statements)
    store.save_clock_statements(conn, clock_statements)
    store.save_autor_statements(conn, autor_statements)
    store.save_sched_statements(conn, sched_statements)
    store.save_couple_statements(conn, couple_statements)
    store.save_grscnf_statements(conn, grscnf_statements)
    store.save_grsrnl_statements(conn, grsrnl_statements)
    store.save_smf_statements(conn, smf_statements)
    store.save_ios_statements(conn, ios_statements)
    store.save_consol_statements(conn, consol_statements)
    store.save_igdsms_statements(conn, igdsms_statements)
    store.save_izuprm_statements(conn, izuprm_statements)
    store.save_diag_statements(conn, diag_statements)
    store.save_iggcat_statements(conn, iggcat_statements)
    store.save_prog_statements(conn, prog_statements)
    store.save_active_jobs(conn, active_jobs)
    store.save_processes(conn, processes)
    store.save_catalog_datasets(conn, catalog_datasets)
    store.save_vsam_clusters(conn, vsam_clusters)
    store.save_racf_snapshot(conn, racf_snapshot)
    store.save_uss_mounts(conn, uss_mounts)
    store.save_jes2_init_statements(conn, jes2_init_statements)
    store.save_vtam_major_nodes(conn, vtam_major_nodes)
    store.save_vtam_start_options(conn, vtam_start_options)
    store.save_vtam_topology_summary(conn, vtam_topology_summary)
    store.save_tcpip_home_addresses(conn, tcpip_home_addresses)
    store.save_tcpip_profile_statements(conn, tcpip_profile_statements)
    store.save_sms_storage_groups(conn, sms_storage_groups)
    store.save_wlm_policy(conn, wlm_policy)
    store.save_db2_packages(conn, db2_packages)
    store.save_db2_plans(conn, db2_plans)
    store.save_wlm_zosmf_entries(conn, wlm_zosmf_entries)
    store.save_cics_dfhrpl_entries(conn, cics_dfhrpl_entries)
    store.save_cics_sit_overrides(conn, cics_sit_overrides)
    store.save_cics_csd_definitions(conn, cics_csd_definitions)
    store.save_cmci_resources(conn, cmci_resources)
    store.save_zone_index(conn, zone_index_entries)
    store.save_zones(conn, list(zones.values()))
    store.save_fmids(conn, fmids)
    conn.close()

    total_steps = sum(len(v) for v in lineage.values())
    print(f"inventory: ingested {len(members)} members, {len(zones)} zones, "
          f"{total_steps} resolved steps, {len(subsystems)} subsystems, "
          f"{len(started_tasks)} started tasks, {len(products)} products, "
          f"{len(parmlib_datasets)} PARMLIB concatenation datasets, "
          f"{len(ieasys_statements)} active IEASYSxx statements, "
          f"{len(bpxprm_statements)} active BPXPRMxx statements, "
          f"{len(devsup_statements)} active DEVSUPxx statements, "
          f"{len(opt_statements)} active IEAOPTxx statements, "
          f"{len(clock_statements)} active CLOCKxx statements, "
          f"{len(autor_statements)} active AUTORxx statements, "
          f"{len(sched_statements)} active SCHEDxx statements, "
          f"{len(couple_statements)} active COUPLExx statements, "
          f"{len(grscnf_statements)} active GRSCNFxx statements, "
          f"{len(grsrnl_statements)} active GRSRNLxx statements, "
          f"{len(smf_statements)} active SMFPRMxx statements, "
          f"{len(ios_statements)} active IECIOSxx statements, "
          f"{len(consol_statements)} active CONSOLxx statements, "
          f"{len(igdsms_statements)} active IGDSMSxx statements, "
          f"{len(izuprm_statements)} active IZUPRMxx statements, "
          f"{len(diag_statements)} active DIAGxx statements, "
          f"{len(iggcat_statements)} active IGGCATxx statements, "
          f"{len(prog_statements)} active PROGxx statements, "
          f"{len(active_jobs)} active jobs, {len(processes)} processes, "
          f"{len(catalog_datasets)} cataloged datasets, "
          f"{len(vsam_clusters)} VSAM clusters, "
          f"{len(racf_snapshot.users)} RACF users, "
          f"{len(racf_snapshot.groups)} RACF groups, "
          f"{len(uss_mounts)} USS mounts, "
          f"{len(jes2_init_statements)} JES2 init statements, "
          f"{len(vtam_major_nodes)} VTAM major nodes, "
          f"{len(vtam_start_options)} VTAM start options, "
          f"{len(tcpip_home_addresses)} TCPIP home addresses, "
          f"{len(tcpip_profile_statements)} TCPIP profile statements, "
          f"{len(sms_storage_groups)} SMS storage groups, "
          f"{len(db2_packages)} DB2 packages, "
          f"{len(db2_plans)} DB2 plans, "
          f"{len(wlm_zosmf_entries)} WLM z/OSMF entries, "
          f"{len(cics_dfhrpl_entries)} CICS DFHRPL entries, "
          f"{len(cics_sit_overrides)} CICS SIT overrides, "
          f"{len(cics_csd_definitions)} CICS CSD definitions, "
          f"{len(cmci_resources)} CICS CMCI resources, "
          f"{len(zone_index_entries)} SMP/E zone index entries, "
          f"{len(fmids)} FMIDs -> {args.db}")
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
        csi = row["csi"] or "?"
        dataset = row["dataset"] or "?"
        apf = _apf_str(row["apf_authorized"])
        print(f"  step {row['step_name']}: PGM={pgm} dataset={dataset} zone={zone} "
              f"FMID={fmid} CSI={csi} [{apf}]  [{row['resolution']}]")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_lineage(conn)
    conn.close()

    fieldnames = ["member", "step_name", "pgm", "dataset", "zone", "fmid", "csi", "resolution", "apf_authorized"]
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


def cmd_trace(args: argparse.Namespace) -> int:
    """Full traceability for one name: is it a defined auto-start task, is
    it running right now, and (reusing `lineage_for_member` -- `StartedTask.
    task_name` is the PROC member name per real MVS `START
    procname[.identifier]` syntax) what's its resolved execution path,
    down to the SMP/E zone/FMID/holding CSI for each step. See doc/TODO.md
    ("8b") for why this exists: the started-task and lineage sides were
    never joined anywhere before this."""
    name = args.name.upper()
    conn = store.connect(Path(args.db))
    started = [r for r in store.all_started_tasks(conn) if r["task_name"].upper() == name]
    active = [r for r in store.all_active_jobs(conn) if r["name"].upper() == name]
    lineage_rows = store.lineage_for_member(conn, name)
    conn.close()

    print(f"TRACE: {name}")

    if started:
        for row in started:
            ident = f".{row['identifier']}" if row["identifier"] else ""
            print(f"  defined as auto-start: S {row['task_name']}{ident}  [{row['source_member']}]")
    else:
        print("  no COMMNDxx auto-start command found for this name")

    if active:
        for row in active:
            print(f"  currently active: {row['job_id']}  TYPE={row['job_type'] or '?'} "
                  f"ASID={row['asid'] or '?'} OWNER={row['owner'] or '?'} SYSTEM={row['system'] or '?'}")
    else:
        print("  not currently active (or no active_jobs.txt ingested)")

    if lineage_rows:
        print("  execution path:")
        for row in lineage_rows:
            pgm = row["pgm"] or "(no PGM)"
            zone = row["zone"] or "?"
            fmid = row["fmid"] or "?"
            csi = row["csi"] or "?"
            dataset = row["dataset"] or "?"
            apf = _apf_str(row["apf_authorized"])
            print(f"    step {row['step_name']}: PGM={pgm} dataset={dataset} zone={zone} "
                  f"FMID={fmid} CSI={csi} [{apf}]  [{row['resolution']}]")
    else:
        print(f"  no PROCLIB/PARMLIB member named {name} was ingested -- cannot resolve an execution path")

    return 0 if (started or active or lineage_rows) else 1


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


def cmd_parmlib(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_parmlib_datasets(conn)
    conn.close()

    for row in rows:
        flags = row["flags"] or "?"
        volume = row["volume"] or "?"
        print(f"{row['entry']}  FLAGS={flags} VOLUME={volume} {row['dsn']}")
    return 0


def cmd_ieasys(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_ieasys_statements(conn)
    conn.close()

    for row in rows:
        value = row["value"] if row["value"] is not None else ""
        print(f"{row['keyword']}={value}  [{row['source_member']}]")
    return 0


def cmd_bpxprm(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_bpxprm_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_devsup(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_devsup_statements(conn)
    conn.close()

    for row in rows:
        value = row["value"] if row["value"] is not None else ""
        print(f"{row['keyword']}={value}  [{row['source_member']}]")
    return 0


def cmd_opt(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_opt_statements(conn)
    conn.close()

    for row in rows:
        value = row["value"] if row["value"] is not None else ""
        print(f"{row['keyword']}={value}  [{row['source_member']}]")
    return 0


def cmd_clock(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_clock_statements(conn)
    conn.close()

    for row in rows:
        value = row["value"] if row["value"] is not None else ""
        print(f"{row['keyword']}={value}  [{row['source_member']}]")
    return 0


def cmd_autor(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_autor_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_sched(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_sched_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_couple(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_couple_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_grscnf(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_grscnf_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_grsrnl(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_grsrnl_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_smf(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_smf_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_ios(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_ios_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_consol(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_consol_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_igdsms(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_igdsms_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_izuprm(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_izuprm_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_diag(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_diag_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
    return 0


def cmd_iggcat(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_iggcat_statements(conn)
    conn.close()

    for row in rows:
        value = row["value"] if row["value"] is not None else ""
        print(f"{row['keyword']}={value}  [{row['source_member']}]")
    return 0


def cmd_prog(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_prog_statements(conn)
    conn.close()

    for row in rows:
        print(f"{row['stmt']} {row['operands']}  [{row['source_member']}]")
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


def cmd_vtam_majnodes(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_vtam_major_nodes(conn)
    conn.close()

    for row in rows:
        print(f"{row['name']}  STATUS={row['status'] or '?'}")
    return 0


def cmd_vtam_options(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_vtam_start_options(conn)
    conn.close()

    for row in rows:
        print(f"{row['keyword']}={row['value']}")
    return 0


def cmd_vtam_topology(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    row = store.get_vtam_topology_summary(conn)
    conn.close()

    if row is None:
        print("inventory: no VTAM topology summary ingested", file=sys.stderr)
        return 1

    print(f"LAST CHECKPOINT: {row['last_checkpoint'] or '?'}")
    print(f"ADJ={row['adj'] if row['adj'] is not None else '?'} "
          f"NN={row['nn'] if row['nn'] is not None else '?'} "
          f"EN={row['en'] if row['en'] is not None else '?'} "
          f"SERVED EN={row['served_en'] if row['served_en'] is not None else '?'} "
          f"CDSERVR={row['cdservr'] if row['cdservr'] is not None else '?'} "
          f"ICN={row['icn'] if row['icn'] is not None else '?'} "
          f"BN={row['bn'] if row['bn'] is not None else '?'}")
    print(f"INITDB CHECKPOINT DATASET: {row['initdb_checkpoint_dataset'] or '?'}")
    print(f"LAST GARBAGE COLLECTION: {row['last_garbage_collection'] or '?'}")
    return 0


def cmd_tcpip_home(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_tcpip_home_addresses(conn)
    conn.close()

    for row in rows:
        marker = "  (PRIMARY)" if row["is_primary"] else ""
        print(f"{row['link_name']}  {row['ip_address']}{marker}")
    return 0


def cmd_tcpip_profile(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_tcpip_profile_statements(conn)
    conn.close()

    for row in rows:
        source = f"  [{row['source_dsn']}]" if row["source_dsn"] else ""
        print(f"{row['stmt']} {row['operands']}{source}")
    return 0


def cmd_sms_storgrps(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_sms_storage_groups(conn)
    conn.close()

    for row in rows:
        volumes = ",".join(json.loads(row["volumes_json"]))
        group_type = row["group_type"] or "?"
        print(f"{row['name']}  TYPE={group_type}  STATUS={row['status'] or '?'}  VOLUMES={volumes or '?'}")
    return 0


def cmd_wlm(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    row = store.get_wlm_policy(conn)
    conn.close()

    if row is None:
        print("inventory: no WLM policy ingested", file=sys.stderr)
        return 1

    print(f"POLICY: {row['policy_name'] or '?'}")
    print(f"MODE: {row['mode'] or '?'}")
    return 0


def cmd_db2_packages(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_db2_packages(conn)
    conn.close()

    for row in rows:
        creator = row["creator"] or "?"
        bind_timestamp = row["bind_timestamp"] or "?"
        print(f"{row['name']}  CREATOR={creator} BINDTIME={bind_timestamp}  [{row['ssid']}]")
    return 0


def cmd_db2_plans(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_db2_plans(conn)
    conn.close()

    for row in rows:
        creator = row["creator"] or "?"
        bind_timestamp = row["bind_timestamp"] or "?"
        print(f"{row['name']}  CREATOR={creator} BINDTIME={bind_timestamp}  [{row['ssid']}]")
    return 0


def cmd_wlm_zosmf(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_wlm_zosmf_entries(conn)
    conn.close()

    for row in rows:
        print(f"{row['name']}  {row['raw_json']}")
    return 0


def cmd_cics_dfhrpl(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_cics_dfhrpl_entries(conn)
    conn.close()

    for row in rows:
        zone = row["zone"] or "?"
        apf = _apf_str(row["apf_authorized"])
        print(f"{row['dsn']}  ZONE={zone} [{apf}]  [{row['proc']}]")
    return 0


def cmd_cics_sit(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_cics_sit_overrides(conn)
    conn.close()

    for row in rows:
        print(f"{row['keyword']}={row['value']}  [{row['proc']}]")
    return 0


def cmd_cics_csd(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_cics_csd_definitions(conn)
    conn.close()

    for row in rows:
        group = row["grp"] or "?"
        print(f"{row['def_type']} {row['name']}  GROUP={group}  [{row['csd_dsn']}]")
    return 0


def cmd_cmci(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    rows = store.all_cmci_resources(conn)
    conn.close()

    for row in rows:
        print(f"{row['resource_type']} {row['name']}  [{row['context']}]  {row['attributes_json']}")
    return 0


def cmd_zone_index(args: argparse.Namespace) -> int:
    """SMP/E's own authoritative zone census per CSI (LIST GLOBALZONE's
    ZONEINDEX), if any *smpzones*.txt files were ingested -- see
    `inventory zone-gaps` for the cross-reference against the zones
    actually captured via *smplist*.txt's LIST DDDEF/MOD/SYSMOD."""
    conn = store.connect(Path(args.db))
    rows = store.all_zone_index(conn)
    conn.close()

    for row in rows:
        csi_note = "" if row["csi"] == row["source_csi"] else f"  (cross-referenced from {row['source_csi']})"
        print(f"{row['zone_name']}  TYPE={row['zone_type']} CSI={row['csi']}{csi_note}")
    return 0


def cmd_zones(args: argparse.Namespace) -> int:
    """Every SMP/E zone actually captured via *smplist*.txt (LIST DDDEF/MOD/
    SYSMOD), independent of lineage -- a full SMP/E zone inventory, not just
    the zones a PROCLIB step happens to resolve into."""
    conn = store.connect(Path(args.db))
    rows = store.all_zones(conn)
    conn.close()

    for row in rows:
        dddefs = json.loads(row["dddefs_json"])
        csi_note = f" CSI={row['csi']}" if row["csi"] else ""
        print(f"{row['name']}{csi_note}  {len(dddefs)} DDDEFs")
    return 0


def cmd_fmids(args: argparse.Namespace) -> int:
    """Every FMID captured across all ingested SMP/E zones."""
    conn = store.connect(Path(args.db))
    rows = store.all_fmids(conn)
    conn.close()

    for row in rows:
        status = f" ({row['status']})" if row["status"] else ""
        print(f"{row['fmid']}  zone={row['zone']}{status}")
    return 0


def cmd_zone_gaps(args: argparse.Namespace) -> int:
    """Cross-reference zone_index (SMP/E's own LIST GLOBALZONE census, if
    *smpzones*.txt was ingested) against the zones actually captured via
    *smplist*.txt, per doc/TODO.md's '8f' plan -- flags a zone SMP/E itself
    says exists that was never captured, rather than requiring a one-off
    by-hand comparison."""
    conn = store.connect(Path(args.db))
    zone_index_rows = store.all_zone_index(conn)
    captured_names = {row["name"] for row in store.all_zones(conn)}
    conn.close()

    gaps = [row for row in zone_index_rows if row["zone_name"] not in captured_names]
    if not gaps:
        print("inventory: no zone gaps found (every LIST GLOBALZONE zone was also captured via *smplist*.txt)")
        return 0
    for row in gaps:
        print(f"MISSING: {row['zone_name']}  TYPE={row['zone_type']} CSI={row['csi']} (from {row['source_csi']})")
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

    p_trace = sub.add_parser("trace", help="full traceability for one name: auto-start definition, live status, and resolved execution path down to SMP/E zone/FMID/CSI")
    p_trace.add_argument("name", help="started task name / PROCLIB member name")
    p_trace.set_defaults(func=cmd_trace)

    p_subsystems = sub.add_parser("subsystems", help="list defined subsystems (IEFSSNxx)")
    p_subsystems.set_defaults(func=cmd_subsystems)

    p_started = sub.add_parser("started-tasks", help="list auto-start started tasks (COMMNDxx)")
    p_started.set_defaults(func=cmd_started_tasks)

    p_sysinfo = sub.add_parser("sysinfo", help="show captured LPAR/sysplex identity")
    p_sysinfo.set_defaults(func=cmd_sysinfo)

    p_products = sub.add_parser("products", help="list product enablement status (IFAPRDxx)")
    p_products.set_defaults(func=cmd_products)

    p_parmlib = sub.add_parser("parmlib", help="list the live PARMLIB concatenation in search order (D PARMLIB, explicit capture)")
    p_parmlib.set_defaults(func=cmd_parmlib)

    p_ieasys = sub.add_parser("ieasys", help="list active IEASYSxx KEYWORD=value statements -- the actual system parameters active at IPL")
    p_ieasys.set_defaults(func=cmd_ieasys)

    p_bpxprm = sub.add_parser("bpxprm", help="list active BPXPRMxx statements -- z/OS UNIX System Services (OMVS) configuration (not yet production-validated)")
    p_bpxprm.set_defaults(func=cmd_bpxprm)

    p_devsup = sub.add_parser("devsup", help="list active DEVSUPxx KEYWORD=value statements -- device support definitions (not yet production-validated)")
    p_devsup.set_defaults(func=cmd_devsup)

    p_opt = sub.add_parser("opt", help="list active IEAOPTxx KEYWORD=value statements -- system tuning/options parameters (not yet production-validated)")
    p_opt.set_defaults(func=cmd_opt)

    p_clock = sub.add_parser("clock", help="list active CLOCKxx KEYWORD value statements -- TOD clock/timezone parameters (not yet production-validated)")
    p_clock.set_defaults(func=cmd_clock)

    p_autor = sub.add_parser("autor", help="list active AUTORxx statements -- WTOR auto-reply policy (not yet production-validated)")
    p_autor.set_defaults(func=cmd_autor)

    p_sched = sub.add_parser("sched", help="list active SCHEDxx PPT (Program Properties Table) statements (not yet production-validated)")
    p_sched.set_defaults(func=cmd_sched)

    p_couple = sub.add_parser("couple", help="list active COUPLExx statements -- XCF/sysplex couple dataset definitions (not yet production-validated)")
    p_couple.set_defaults(func=cmd_couple)

    p_grscnf = sub.add_parser("grscnf", help="list active GRSCNFxx GRSDEF statements -- Global Resource Serialization configuration parameters, CONFIRMED against a real member")
    p_grscnf.set_defaults(func=cmd_grscnf)

    p_grsrnl = sub.add_parser("grsrnl", help="list active GRSRNLxx RNLDEF statements -- global resource serialization resource name lists, CONFIRMED against a real (partial) member")
    p_grsrnl.set_defaults(func=cmd_grsrnl)

    p_smf = sub.add_parser("smf", help="list active SMFPRMxx statements -- SMF recording configuration (not yet production-validated)")
    p_smf.set_defaults(func=cmd_smf)

    p_ios = sub.add_parser("ios", help="list active IECIOSxx statements -- I/O related parameters (not yet production-validated)")
    p_ios.set_defaults(func=cmd_ios)

    p_consol = sub.add_parser("consol", help="list active CONSOLxx statements -- MCS/EMCS console definitions")
    p_consol.set_defaults(func=cmd_consol)

    p_igdsms = sub.add_parser("igdsms", help="list active IGDSMSxx SMS statements -- SMS base configuration (distinct from sms-storgrps, the live D SMS,STORGRP snapshot)")
    p_igdsms.set_defaults(func=cmd_igdsms)

    p_izuprm = sub.add_parser("izuprm", help="list active IZUPRMxx statements -- z/OSMF configuration")
    p_izuprm.set_defaults(func=cmd_izuprm)

    p_diag = sub.add_parser("diag", help="list active DIAGxx statements -- diagnostic function defaults")
    p_diag.set_defaults(func=cmd_diag)

    p_iggcat = sub.add_parser("iggcat", help="list active IGGCATxx KEYWORD(value) statements -- catalog system parameters, CONFIRMED against a real member")
    p_iggcat.set_defaults(func=cmd_iggcat)

    p_prog = sub.add_parser("prog", help="list active PROGxx APF/LNKLST/LPA/EXIT/SCHED statements, CONFIRMED against a real member")
    p_prog.set_defaults(func=cmd_prog)

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

    p_uss_mounts = sub.add_parser("uss-mounts", help="list mounted USS filesystems (confirmed against a real reply)")
    p_uss_mounts.set_defaults(func=cmd_uss_mounts)

    p_jes2parm = sub.add_parser("jes2parm", help="list JES2's own initialization statements (confirmed against a real init deck)")
    p_jes2parm.set_defaults(func=cmd_jes2parm)

    p_vtam_majnodes = sub.add_parser("vtam-majnodes", help="list VTAM major nodes and their status (confirmed against a real reply)")
    p_vtam_majnodes.set_defaults(func=cmd_vtam_majnodes)

    p_vtam_options = sub.add_parser("vtam-options", help="list VTAM start options incl. NODETYPE/CPNAME (APPN enablement/role) (confirmed against a real reply)")
    p_vtam_options.set_defaults(func=cmd_vtam_options)

    p_vtam_topology = sub.add_parser("vtam-topology", help="show the APPN topology database summary (D NET,TOPO) -- confirmed against a real reply")
    p_vtam_topology.set_defaults(func=cmd_vtam_topology)

    p_tcpip_home = sub.add_parser("tcpip-home", help="list TCP/IP stack home addresses (confirmed against a real reply)")
    p_tcpip_home.set_defaults(func=cmd_tcpip_home)

    p_tcpip_profile = sub.add_parser("tcpip-profile", help="list PROFILE.TCPIP configuration statements, if configured (confirmed against a real member)")
    p_tcpip_profile.set_defaults(func=cmd_tcpip_profile)

    p_sms_storgrps = sub.add_parser("sms-storgrps", help="list SMS storage groups, type, per-system status, and volumes (confirmed against a real reply)")
    p_sms_storgrps.set_defaults(func=cmd_sms_storgrps)

    p_wlm = sub.add_parser("wlm", help="show the active WLM policy name/mode (confirmed against a real reply)")
    p_wlm.set_defaults(func=cmd_wlm)

    p_db2_packages = sub.add_parser("db2-packages", help="list installed DB2 packages (confirmed against a real DSNTEP2 report)")
    p_db2_packages.set_defaults(func=cmd_db2_packages)

    p_db2_plans = sub.add_parser("db2-plans", help="list installed DB2 plans (confirmed against a real DSNTEP2 report)")
    p_db2_plans.set_defaults(func=cmd_db2_plans)

    p_wlm_zosmf = sub.add_parser("wlm-zosmf", help="list WLM entries fetched via z/OSMF's REST API (most speculative dimension, not yet production-validated)")
    p_wlm_zosmf.set_defaults(func=cmd_wlm_zosmf)

    p_cics_dfhrpl = sub.add_parser("cics-dfhrpl", help="list deepened CICS DFHRPL load-library entries, zone/APF-resolved (opt-in, not yet production-validated)")
    p_cics_dfhrpl.set_defaults(func=cmd_cics_dfhrpl)

    p_cics_sit = sub.add_parser("cics-sit", help="list deepened CICS SIT (System Initialization Table) overrides (opt-in, not yet production-validated)")
    p_cics_sit.set_defaults(func=cmd_cics_sit)

    p_cics_csd = sub.add_parser("cics-csd", help="list deepened CICS resource definitions from a DFHCSDUP LIST report (opt-in, most speculative dimension alongside wlm-zosmf, not yet production-validated)")
    p_cics_csd.set_defaults(func=cmd_cics_csd)

    p_cmci = sub.add_parser("cmci", help="list CICS resources fetched via CMCI (opt-in, for CMCI-enabled regions only, not yet production-validated)")
    p_cmci.set_defaults(func=cmd_cmci)

    p_zone_index = sub.add_parser("zone-index", help="list SMP/E's own authoritative zone census per CSI (LIST GLOBALZONE), if ingested -- not yet production-validated")
    p_zone_index.set_defaults(func=cmd_zone_index)

    p_zones = sub.add_parser("zones", help="list every SMP/E zone actually captured via *smplist*.txt")
    p_zones.set_defaults(func=cmd_zones)

    p_fmids = sub.add_parser("fmids", help="list every FMID captured across all ingested SMP/E zones")
    p_fmids.set_defaults(func=cmd_fmids)

    p_zone_gaps = sub.add_parser("zone-gaps", help="cross-reference LIST GLOBALZONE's zone census against zones actually captured via *smplist*.txt")
    p_zone_gaps.set_defaults(func=cmd_zone_gaps)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
