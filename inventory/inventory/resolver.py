"""Join the JCL side (ProcMember/JclStep) with the SMP/E side (Zone) to
build the full lineage chain for every PROCLIB/PARMLIB member:

    ProcMember -> JclStep -> PGM -> Dataset -> Zone -> FMID

Resolution order for "what dataset does this PGM= live in":
  1. explicit STEPLIB DD on the step
  2. explicit JOBLIB DD on the step
  3. LNKLST search order (first dataset in the list that any zone claims)
"""
from __future__ import annotations

from .jcl_parser import inline_nested_procs
from .models import LineageStep, ProcMember, Zone


def _dataset_to_zone(dsn: str, zones: dict[str, Zone]) -> str | None:
    for zone in zones.values():
        if dsn in zone.dddefs.values():
            return zone.name
    return None


def dataset_zone(dsn: str, zones: dict[str, Zone]) -> str | None:
    """Public wrapper for _dataset_to_zone -- lets other domains (e.g.
    CicsDfhrplEntry) resolve a dataset to its owning SMP/E zone the same
    way STEPLIB/JOBLIB/LNKLST hops already do here, without duplicating
    the DDDEF-match logic in a new module."""
    return _dataset_to_zone(dsn, zones)


def _fmid_for_module(pgm: str, zone_name: str | None, zones: dict[str, Zone]) -> str | None:
    if zone_name is None:
        return None
    zone = zones.get(zone_name)
    if zone is None:
        return None
    return zone.module_fmid.get(pgm)


def resolve_member(
    member: ProcMember,
    all_members: dict[str, ProcMember],
    zones: dict[str, Zone],
    lnklst: list[str],
    apf: set[str] | None = None,
) -> list[LineageStep]:
    """Build the full lineage for one top-level ProcMember, following nested
    PROC calls and resolving each PGM= back to a Dataset/Zone/FMID.

    `apf`, if given, is the set of APF-authorized dataset names (from
    apf.txt); each resolved hop's `apf_authorized` is True/False when `apf`
    is provided and the hop has a dataset, else None (unknown)."""
    flat_steps = inline_nested_procs(member, all_members)
    lineage: list[LineageStep] = []

    for step in flat_steps:
        if not step.pgm:
            lineage.append(
                LineageStep(
                    member=member.name,
                    step_name=step.step_name,
                    pgm="",
                    dataset=None,
                    zone=None,
                    fmid=None,
                    resolution=f"unresolved PROC reference: {step.proc}",
                    apf_authorized=None,
                )
            )
            continue

        dataset = None
        how = ""
        if step.steplib:
            dataset, how = step.steplib, "STEPLIB"
        elif step.joblib:
            dataset, how = step.joblib, "JOBLIB"
        else:
            for candidate in lnklst:
                if _dataset_to_zone(candidate, zones) is not None:
                    dataset, how = candidate, "LNKLST"
                    break
            if dataset is None and lnklst:
                # no LNKLST entry matched a known DDDEF; still record the
                # first LNKLST candidate so the gap is visible in reports
                dataset, how = lnklst[0], "LNKLST (unverified)"

        zone_name = _dataset_to_zone(dataset, zones) if dataset else None
        fmid = _fmid_for_module(step.pgm, zone_name, zones)
        csi = (zones[zone_name].csi or None) if zone_name else None

        if dataset is None:
            resolution = "no STEPLIB/JOBLIB and no LNKLST data available"
        elif zone_name is None:
            resolution = f"dataset {dataset} not matched to any SMP/E zone DDDEF"
        elif fmid is None:
            resolution = f"module {step.pgm} not found in zone {zone_name}'s FILE list"
        else:
            status = zones[zone_name].fmid_status.get(fmid, "")
            resolution = f"resolved via {how}" + (f" ({status})" if status else "")

        apf_authorized = None if dataset is None or apf is None else dataset in apf

        lineage.append(
            LineageStep(
                member=member.name,
                step_name=step.step_name,
                pgm=step.pgm,
                dataset=dataset,
                zone=zone_name,
                fmid=fmid,
                resolution=resolution,
                apf_authorized=apf_authorized,
                csi=csi,
            )
        )

    return lineage


def resolve_all(
    members: list[ProcMember],
    zones: dict[str, Zone],
    lnklst: list[str],
    apf: set[str] | None = None,
) -> dict[str, list[LineageStep]]:
    """Resolve every member's lineage. When the same member name is ingested
    from more than one PROCLIB/PARMLIB concatenation entry, the one from the
    lowest-sorting `library` (the NN-prefix convention documented in
    doc/zos-extract.md -- lower number searched first) wins, matching real
    PROCLIB/PARMLIB search order -- not whichever instance happened to be
    read last."""
    by_name: dict[str, ProcMember] = {}
    for m in sorted(members, key=lambda m: m.library):
        by_name.setdefault(m.name, m)
    return {name: resolve_member(m, by_name, zones, lnklst, apf) for name, m in by_name.items()}
