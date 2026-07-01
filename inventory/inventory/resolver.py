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
) -> list[LineageStep]:
    """Build the full lineage for one top-level ProcMember, following nested
    PROC calls and resolving each PGM= back to a Dataset/Zone/FMID."""
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

        if dataset is None:
            resolution = "no STEPLIB/JOBLIB and no LNKLST data available"
        elif zone_name is None:
            resolution = f"dataset {dataset} not matched to any SMP/E zone DDDEF"
        elif fmid is None:
            resolution = f"module {step.pgm} not found in zone {zone_name}'s FILE list"
        else:
            status = zones[zone_name].fmid_status.get(fmid, "")
            resolution = f"resolved via {how}" + (f" ({status})" if status else "")

        lineage.append(
            LineageStep(
                member=member.name,
                step_name=step.step_name,
                pgm=step.pgm,
                dataset=dataset,
                zone=zone_name,
                fmid=fmid,
                resolution=resolution,
            )
        )

    return lineage


def resolve_all(
    members: list[ProcMember], zones: dict[str, Zone], lnklst: list[str]
) -> dict[str, list[LineageStep]]:
    by_name = {m.name: m for m in members}
    return {m.name: resolve_member(m, by_name, zones, lnklst) for m in members}
