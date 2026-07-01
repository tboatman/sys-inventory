# ansible

Orchestrates step 1 of the pipeline described in the top-level
[`README.md`](../README.md) and [`zos-extract/README.md`](../zos-extract/README.md)
via Ansible, instead of you SSHing into each LPAR by hand and running every
`zos-extract/python/*.py` script and `scp` one at a time. Each of that
pipeline's steps is reimplemented here as a direct
[`ibm.ibm_zos_core`](https://github.com/ansible-collections/ibm_zos_core)
module call (`zos_operator`, `zos_apf`, `zos_job_query`, `zos_find`/
`zos_fetch`, `zos_mvs_raw`, ...) instead of staging and shelling out to the
Python script for that step -- see the header comment in each
`roles/zos_extract/tasks/*.yml` file for exactly which module replaces
which script/ZOAU call, and why. Every step writes its result straight to a
local directory ready for `inventory ingest` (see
[`../inventory/README.md`](../inventory/README.md)) -- there's no separate
"copy the output off-host" step, since these modules return their results
to the control node directly.

## Why native modules instead of running the Python scripts

`zos_common.py`'s own docstring already notes that this project's ZOAU calls
were cross-checked against `ibm_zos_core`'s source, since it wraps the same
`zoautil_py` API this pipeline uses directly -- so `ibm_zos_core` already had
a purpose-built module for nearly everything `zos-extract/python/` does by
hand: `zos_apf` for the APF list, `zos_job_query` for active jobs,
`zos_mvs_raw` for the raw MVS program invocations (GIMSMP/IDCAMS/IRRDBU00),
`zos_find`/`zos_fetch`/`zos_stat` for dataset/member listing and attributes,
and `zos_operator` for the couple of console commands with no more specific
module (`D PROG,LNKLST`, `D SYMBOLS`, `D IPLINFO`). Using those directly
means Ansible manages the DD/dataset allocate-read-back-delete lifecycle
declaratively instead of the hand-rolled `datasets.tmp_name()`+`create()`+
`read()`+`delete()` dance the original scripts needed, and there's no
separate "stage the scripts, then fetch the output back" round trip.

Every task file reconstructs its output in the **exact same text format**
the original script produced (same `##MEMBER`/`##SYMBOLS`/`##NONVSAM`
sentinels, same "one DSN per line" shape, etc.), so
`inventory/inventory/*_parser.py` needs no changes to ingest it.

One step keeps the "nicer structured result" module documented but unused:
`sysinfo.yml` sticks with `zos_operator`'s raw `D SYMBOLS`/`D IPLINFO` text
rather than `zos_gather_facts`'s structured JSON, specifically to stay
byte-for-byte compatible with `sysinfo_parser.py`'s raw-text parsing -- see
that file's header comment.

## Prerequisites

Everything in `zos-extract/README.md`'s "Before you start" section still
applies (OMVS shell, IBM Open Enterprise Python, ZOAU, read authority) --
these modules still shell out to ZOAU/`zoautil_py` on the target under the
hood, they just do it through `ibm_zos_core` instead of
`zos-extract/python/`'s own wrapper code. On top of that:

- Ansible on your control node (wherever you run `ansible-playbook` from --
  your laptop, a CI runner, etc.), plus the collection this directory
  depends on:
  ```
  ansible-galaxy collection install -r requirements.yml
  ```
- SSH access from that control node to each LPAR's OMVS shell as the userid
  that has the READ/console-command authority `zos-extract/README.md`
  describes.

## Setup

```
cp inventory/hosts.yml.example inventory/hosts.yml
```

Edit `inventory/hosts.yml` (gitignored -- it'll hold your real dataset
names and hostnames): add one entry under `zos.hosts` per LPAR, and fill in
`zos_extract_proclibs`/`zos_extract_parmlibs`/`zos_extract_smpe_csi`/`zos_extract_smpe_zones`/`zos_extract_catalog_patterns` for each.
`inventory/group_vars/zos.yml` has the shared ZOAU/Python environment variables from
`zos-extract/README.md`'s "Basic Env requirements" section -- adjust the
paths there if your site installs ZOAU/Python somewhere else. That
environment is applied at the play level (`playbooks/site.yml`) since
`ibm_zos_core`'s modules need it too, not just raw shell commands.

## Running it

```
cd ansible
ansible-playbook playbooks/site.yml
```

This runs every step (except RACF, see below) against every host in the
`zos` group and leaves the results in `output/<lpar-name>/` -- hand that
directory straight to `inventory ingest`:

```
cd ../inventory
inventory ingest ../ansible/output/lpar1/
```

Run a subset with `--tags` (each tag matches one numbered step in
`zos-extract/README.md`):

```
ansible-playbook playbooks/site.yml --tags lnklst,apf
ansible-playbook playbooks/site.yml --limit lpar1 --tags activity
```

Available tags: `proclib`, `ssn_commnd`, `ifaprd`, `lnklst`, `apf`,
`sysinfo`, `smplist`, `activity`, `catalog`, `racf`.
`smplist`/`catalog` only run on hosts where `zos_extract_smpe_csi`/
`zos_extract_catalog_patterns` are actually set, so it's safe to leave them
out of `hosts.yml` for LPARs you don't want those steps on.

### Running it against a system that isn't in `hosts.yml` yet

`playbooks/interactive.yml` prompts for connection details instead of
requiring them in `inventory/hosts.yml` -- useful for a one-off run against
a system you haven't added to inventory, or don't want to:

```
ansible-playbook playbooks/interactive.yml
```

It asks for the hostname/IP, username, password (leave blank to use
key-based auth via your normal `ssh` config/agent instead), and SSH port,
then runs the same role against just that system. Everything else --
which steps run, `zos_extract_proclibs`/`zos_extract_smpe_csi`/
`zos_extract_catalog_patterns`/... -- still comes from
`roles/zos_extract/defaults/main.yml` and `inventory/group_vars/zos.yml`,
same as `playbooks/site.yml`; override those with `-e` as needed, e.g.:

```
ansible-playbook playbooks/interactive.yml \
  -e '{"zos_extract_proclibs": [{"dsn": "SYS1.PROCLIB", "prefix": "00"}]}'
```

`--tags`/`--limit` work the same as with `playbooks/site.yml`. Answering
the password prompt needs `sshpass` installed on your control node, the
same as any Ansible password-based SSH connection -- if you don't have
it, leave the prompt blank and rely on key-based auth instead.

### PROCLIB/PARMLIB and active-member auto-discovery

You don't have to hand-populate `zos_extract_proclibs`/`zos_extract_parmlibs`,
and `ssn_commnd`/`ifaprd` don't have to dump every `IEFSSN*`/`COMMND*`/
`IFAPRD*` member -- this role can work it all out live instead:

1. **`discover_proclib.yml`** -- if `zos_extract_proclibs` isn't set, it
   queries the live PROCLIB concatenation via JES2's `$D PROCLIB` command,
   in search (DD) order. This is JES2-specific -- there's no system-wide
   MVS console command for PROCLIB the way `D PARMLIB` covers PARMLIB, and
   JES3 sites haven't been verified against this parser, so configure
   `zos_extract_proclibs` by hand if your site is JES3 or this doesn't
   find anything. An explicit list in `hosts.yml` always wins over this.
2. **`discover_parmlib.yml`** -- if `zos_extract_parmlibs` isn't set, it
   queries the live PARMLIB concatenation via `D PARMLIB` (a real
   system-wide MVS console command, same idea as the existing LNKLST
   discovery), in search order. An explicit list in `hosts.yml` always
   wins over this too.
3. **`discover_active_parmlib_suffixes.yml`** + **`discover_active_members.yml`**
   -- `D IPLINFO`'s `IEASYM LIST`/`IEASYS LIST` give the active
   `IEASYSxx`/`IEASYMxx` suffix(es); this role then reads the actual
   content of those `IEASYSxx` member(s) and pulls out their `SSN=`/
   `CMD=`/`PROD=` keyword values -- the *real* mechanism z/OS uses to
   select the active `IEFSSNxx`/`COMMNDxx`/`IFAPRDxx` member, as opposed
   to assuming they share the same suffix by convention. `ssn_commnd.yml`/
   `ifaprd.yml` use those suffixes (when found) to fetch just the active
   member(s) instead of every member matching the wildcard filter. If
   this comes up empty for any reason (unreadable `IEASYSxx`, unexpected
   `D IPLINFO` format, etc.), it falls back to the broad wildcard filter
   automatically -- no separate flag to flip.

All of these are unconditional (`always` tagged) so they run regardless of
which step tags you select, since `ssn_commnd`/`ifaprd` need the discovered
suffixes even if you didn't ask for `sysinfo`/PARMLIB steps in the same run.

### Finding your SMP/E CSI if you don't already know its name

`zos_extract_smpe_csi` (used by `smplist.yml`) has to be set by hand -- unlike
PROCLIB/PARMLIB, there's no system command that enumerates registered CSIs
(SMP/E doesn't register a CSI anywhere central; it's just a VSAM KSDS a site
chooses to use as one). If you don't know its name yet, set
`zos_extract_smpe_csi_search_patterns` in `hosts.yml` and run:

```
ansible-playbook playbooks/site.yml --tags smpe_csi_discovery --limit lpar1
```

This searches the catalog (`zos_find`, `resource_type: cluster`) for VSAM
clusters matching those patterns and writes candidates to
`smpe_csi_candidates.txt` -- a naming-heuristic list, not a verified one.
Confirm a candidate is really usable as an `SMPCSI` (e.g. by pointing
`smplist.yml` at it) before setting `zos_extract_smpe_csi` to it.

Keep the patterns prefix-anchored (e.g. `SMPE.*.CSI`), not leading-wildcard
(e.g. `**.CSI`): catalog search is an ordered index (BCS) lookup, so a fixed
prefix lets it do a narrow scan, while a leading wildcard forces it to walk
every catalog entry on the system looking for a match at the end of the
name -- the actual CPU cost driver, not the volume of data stored under any
of those entries.

### RACF (step 10) is opt-in on purpose

Per `zos-extract/README.md`, `extrracf.py` needs a materially different and
harder-to-get authorization (READ access to a RACF database **copy**), and
its output is explicitly implementation-only / not yet production-validated.
This role won't run it unless you both set `zos_extract_racf_database_dsn` in
`hosts.yml` **and** pass `--tags racf` explicitly:

```
ansible-playbook playbooks/site.yml --tags racf --limit lpar1
```

### A performance note on `catalog`

Unlike `zoautil_py`'s `datasets.list_datasets()` (which returns DSORG/RECFM/
LRECL/BLKSIZE/VOLSER for every matching data set in one call), `zos_find`
only returns data set names -- so `catalog.yml` queries each matched
non-VSAM data set individually with `zos_stat` to get those attributes. This
means roughly one extra module call per matched data set, on top of
`zos_find`'s own call. `zos-extract/README.md` already recommends scoping
`zos_extract_catalog_patterns` narrowly rather than to a broad shared HLQ --
that advice matters even more here.

## Layout

```
ansible.cfg
requirements.yml           # ibm.ibm_zos_core collection pin
inventory/hosts.yml.example
inventory/group_vars/zos.yml  # shared ZOAU/Python env + local output path
                               # (must live beside the inventory file --
                               # that's how Ansible auto-loads group_vars)
playbooks/site.yml         # entry point; sets the ZOAU env at the play level
playbooks/interactive.yml  # same, but prompts for connection details for a
                            # one-off system instead of reading hosts.yml
playbooks/roles            # symlink to ../roles -- ansible.cfg's roles_path
                            # setting only applies when a tool's cwd is this
                            # ansible/ directory (so it finds ansible.cfg at
                            # all); this symlink makes the role discoverable
                            # via Ansible's own default playbook-relative
                            # search too, so e.g. an IDE's ansible-lint
                            # integration running from the repo root still
                            # finds roles/zos_extract. Don't delete it.
roles/zos_extract/
  defaults/main.yml        # per-step defaults (member filters, HLQs, ...)
  tasks/
    main.yml               # dispatches to one file per step, by tag
    local_prep.yml          # ensures the local output directory exists
    discover_proclib.yml    # auto-discovers zos_extract_proclibs via
                             # JES2's '$D PROCLIB' if it isn't set explicitly
    discover_parmlib.yml    # auto-discovers zos_extract_parmlibs via
                             # 'D PARMLIB' if it isn't set explicitly
    discover_active_parmlib_suffixes.yml
                             # parses 'D IPLINFO's IEASYM/IEASYS LIST
                             # into the active IEASYSxx/IEASYMxx suffixes
    discover_active_members.yml
                             # reads the active IEASYSxx member(s) (see
                             # _fetch_active_ieasys_member.yml) and pulls
                             # their SSN=/CMD=/PROD= keywords -- the
                             # active IEFSSNxx/COMMNDxx/IFAPRDxx suffixes,
                             # used by ssn_commnd.yml/ifaprd.yml to fetch
                             # just those members instead of every one
                             # matching the broad wildcard filter
    proclib.yml, ssn_commnd.yml, ifaprd.yml
                             # zos_find + zos_fetch member dumps (see
                             # _member_dump.yml, the shared worker they
                             # each include per PROCLIB/PARMLIB entry)
    lnklst.yml, apf.yml, sysinfo.yml
                             # zos_operator / zos_apf console-command and
                             # APF-list analogs
    activity.yml             # zos_job_query + `ps -ef` for the live
                              # jobs/processes snapshot
    smplist.yml               # zos_mvs_raw (GIMSMP) per SMP/E zone (see
                               # _smplist_zone.yml, the shared per-zone
                               # worker)
    discover_smpe_csis.yml     # opt-in catalog search for CSI candidates
                                # by naming pattern (zos_find, cluster) --
                                # not authoritative, see above
    catalog.yml                # zos_find + zos_stat (non-VSAM) and
                                # zos_mvs_raw/IDCAMS (VSAM) combined
    racf.yml                   # zos_mvs_raw (IRRDBU00), implementation
                                # only -- see above
```
