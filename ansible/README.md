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
`sysinfo`, `uss_mounts`, `jes2parm`, `vtam`, `tcpip`, `smplist`,
`activity`, `catalog`, `racf`.
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
   `CMD=`/`PROD=`/`MSTRJCL=` keyword values -- the *real* mechanism z/OS
   uses to select the active `IEFSSNxx`/`COMMNDxx`/`IFAPRDxx`/`MSTJCLxx`
   member, as opposed to assuming they share the same suffix by
   convention. `ssn_commnd.yml`/`ifaprd.yml` use those suffixes (when
   found) to fetch just the active member(s) instead of every member
   matching the wildcard filter. If this comes up empty for any reason
   (unreadable `IEASYSxx`, unexpected `D IPLINFO` format, etc.), it falls
   back to the broad wildcard filter automatically -- no separate flag to
   flip.
4. **`discover_mstrjcl_proclibs.yml`** -- fills a real gap in step 1:
   `$D PROCLIB` only reports JES2's own PROCLIB concatenation (used to
   resolve batch job PROCs), not the separate one the master scheduler
   uses to resolve `START`/`S` command PROCs for started tasks, which
   comes from the `IEFPDSI` DD inside the `MSTJCLxx` member (selected by
   the `MSTRJCL=` suffix from step 3). A site can concatenate extra
   proclib datasets straight onto that DD without ever touching JES2's
   own PROCLIB definition -- confirmed as a real site's setup -- so this
   fetches the active `MSTJCLxx` member (from wherever it's found in
   `zos_extract_proclibs`), pulls every `DSN=` out of the `IEFPDSI` DD
   group (the DD itself plus any unnamed concatenated DD statements after
   it), and appends any not already known to `zos_extract_proclibs` before
   `proclib.yml` dumps everything. Skipped entirely if `MSTRJCL=` wasn't
   found in step 3.

Each of these is tagged with exactly the step(s) that need it, not `always`
-- `discover_proclib.yml` is tagged `proclib`; `discover_parmlib.yml` is
tagged `proclib, ssn_commnd, ifaprd` (all three consume the PARMLIB list);
`discover_active_parmlib_suffixes.yml`/`discover_active_members.yml` are
tagged `proclib, ssn_commnd, ifaprd` (`proclib` needs them too now, for the
`MSTRJCL=` suffix `discover_mstrjcl_proclibs.yml` consumes);
`discover_mstrjcl_proclibs.yml` is tagged `proclib` only. So e.g.
`--tags catalog` or `--tags smpe_csi_discovery` alone doesn't also issue
`$D PROCLIB`/`D PARMLIB`/`D IPLINFO`, fetch `IEASYSxx` members, or fetch
`MSTJCLxx` for no reason -- a tagless run still does all of it, same as
before, since Ansible runs every task when no `--tags`/`--skip-tags` is
given regardless of what tags it carries.

### Finding your SMP/E CSI if you don't already know its name

`zos_extract_smpe_csi` (used by `smplist.yml`) has to be set by hand -- unlike
PROCLIB/PARMLIB, there's no system command that enumerates registered CSIs
(SMP/E doesn't register a CSI anywhere central; it's just a VSAM KSDS a site
chooses to use as one). If you don't know its name yet, run:

```
ansible-playbook playbooks/site.yml --tags smpe_csi_discovery --limit lpar1
```

This searches the catalog with `zos_find` (`resource_type: cluster`), the
same module `catalog.yml` uses for its non-VSAM search, and writes matches to
`smpe_csi_candidates.txt` -- a naming-heuristic list, not a verified one.
Confirm a candidate is really usable as an `SMPCSI` (e.g. by pointing
`smplist.yml` at it) before setting `zos_extract_smpe_csi` to it.

`zos_extract_smpe_csi_search_patterns` defaults to `["EDUC.**.CSI"]`
(`roles/zos_extract/defaults/main.yml`) since that's this site's actual
convention -- every CSI lives under the `EDUC` HLQ. Override it in
`hosts.yml` if yours differs. Keep the leading qualifier literal (e.g.
`SMPE.*.CSI`, not `*.CSI` or `**.CSI`): `zos_find`'s own docs say it "does
not support wildcards for high level qualifiers" -- confirmed the hard way,
a real run against a `**.CSI`-only pattern (no shared prefix) silently
returned nothing, no error. A genuinely suffix-only convention with no
shared prefix has no catalog-search primitive on z/OS at all -- the only way
to find those is an unrestricted `LISTCAT ALL` scan of the whole catalog
followed by a client-side filter, which is real overkill once (like here)
there's a literal prefix to anchor on instead.

### zos_job_query is unusable here -- activity/CICS/DB2 all route around it

`activity.yml` (tag `activity`), `cics.yml` (tag `cics`), and `db2.yml`
(tag `db2`) all avoid `ibm.ibm_zos_core`'s `zos_job_query`, which was tried
first and crashed ZOAU's own `jls` utility on a real run:

```
CEE3209S The system detected a fixed-point divide exception
(System Completion Code=0C9) ... at entry point parseSMFRecord
```

Root cause, confirmed by reading `ibm_zos_core`'s own
`module_utils/job.py`: `zos_job_query` unconditionally calls
`jobs.fetch_multiple(..., include_extended=True)` no matter what `job_name`
is passed (its own code comment: "Observation shows the job_name parameter
is not being used, so we will drop that"). `include_extended` is what pulls
in the SMF-derived fields (`program_name`, `cpu_time`, `srb_time`), and
it's specifically SMF-record parsing that's crashing -- so narrowing the
query pattern was never going to help, and there's no module option to
turn `include_extended` off. `zos_job_query` is unusable here for any
job_name/pattern as a result.

**`activity.yml`** doesn't need those SMF-derived fields at all, so it
calls ZOAU's `jls` binary directly (`ansible.builtin.command`, same as this
file's own `ps -ef` call) requesting every *other* field jls exposes --
`owner,name,id,status,ccode,jobclass,serviceclass,priority,asid,creationdate,`
`creationtime,queueposition,jobtype,executiontime,executionseconds,system,`
`subsystem,onode,xnode,membname` -- confirmed against a real run to avoid
the crash entirely (`rc: 0`, hundreds of jobs) while capturing far more than
the original `extrjobs.py` dump did. `active_jobs.txt` is JSON Lines (one
job object per line, jls's own field names) rather than a fixed four-column
format as a result; `inventory/inventory/models.py`'s `ActiveJob` and
`activity_parser.py`'s `parse_active_jobs()` were updated to match.
`extrjobs.py`'s own plain `jobs.fetch_multiple()` call (no
`include_extended`) presumably never hit the crash for the same reason.

**`cics.yml`/`db2.yml`** need `PROCSTEP`, which isn't one of `jls`'s
available fields, so they consume `discover_active_address_spaces.yml`'s
shared `D A,L` (Display Active, Long form) console command instead (tagged
`cics, db2`, so it only runs once if both tags are selected together).
`D A,L` sidesteps ZOAU/`jls` entirely, going straight to MVS, at the cost
of a narrower field set than `jls` provides (job name, step name,
`PROCSTEP`, status -- no job ID or ASID, which these two don't need
anyway). An address space counts as CICS if its `PROCSTEP` is literally
`CICS` (true for every CICS region in a real reply from this site) **or**
its job name matches `zos_extract_cics_job_patterns` (`CTS*`, `ECB2*`,
`MTSEDUC*`); DB2 the same way via `PROCSTEP` `DB2PROC` **or**
`zos_extract_db2_job_patterns` (`DB2*`) -- OR'd together as a fallback in
case some address space doesn't use the expected `PROCSTEP`. Both are
opt-in (skipped unless their respective patterns are configured) and both
are a naming/content heuristic, not authoritative, same as the CSI
candidate list.

### RACF (step 10) is opt-in on purpose

Per `zos-extract/README.md`, `extrracf.py` needs a materially different and
harder-to-get authorization (READ access to a RACF database **copy**), and
its output is explicitly implementation-only / not yet production-validated.
This role won't run it unless you both set `zos_extract_racf_database_dsn` in
`hosts.yml` **and** pass `--tags racf` explicitly:

```
ansible-playbook playbooks/site.yml --tags racf --limit lpar1
```

### USS mounts / JES2 init parameters (not yet validated against a real reply)

`uss_mounts.yml` (`D OMVS,F`) and `discover_jes2_parmlib.yml`/`jes2parm.yml`
(`$D PARMLIB`, JES2's own command -- distinct from `discover_parmlib.yml`'s
plain MVS `D PARMLIB` and from `discover_proclib.yml`'s `$D PROCLIB`) are
both implemented and unit-tested against hand-built fixtures the same way
RACF was, but **neither has been confirmed against a real reply from an
actual system yet** -- unlike `$D PROCLIB`, which this role's own comments
note was confirmed against a real JES2 reply. Specifically:

- `uss_mounts.yml` writes `D OMVS,F`'s raw console reply verbatim (same
  "capture raw, parse off-host" approach as `sysinfo.yml`) rather than
  parsing it in Jinja -- the real regex work lives entirely in
  `inventory/inventory/uss_mounts_parser.py`, whose docstring carries the
  validation caveat.
- `discover_jes2_parmlib.yml` assumes `$D PARMLIB` wraps its reply the
  same `$HASPnnn`-prefixed way `$D PROCLIB` does, but matches any
  `$HASPnnn` message ID generically (`\$HASP\d+`) rather than a specific
  confirmed number, since the exact ID this command replies with isn't
  known here.

Run `ansible-playbook playbooks/site.yml --tags uss_mounts,jes2parm
--limit lpar1` against a real system and check the resulting
`uss_mounts.txt`/`*_jes2parm.txt` against what the parsers assume before
relying on either dimension.

### VTAM/APPN/TCPIP (not yet validated against a real reply)

`vtam.yml` (`D NET,MAJNODES` + `D NET,VTAMOPTS`) and `tcpip.yml`
(`D TCPIP,,NETSTAT,HOME`, plus an opt-in `PROFILE.TCPIP` dataset fetch)
are implemented and unit-tested against hand-built fixtures the same way
USS mounts/JES2 init parameters were, but **none of the three commands
(nor a real `PROFILE.TCPIP` sample) has been confirmed against a real
reply from an actual system** -- IBM's own docs site 403'd on direct
fetch and no secondary source turned up real sample output for any of
them while writing this either. Specifically:

- `vtam.yml` bundles both D-commands' raw console replies into one
  `vtam.txt` via the same `##BLOCKNAME`-sentinel convention `sysinfo.yml`
  uses for `D SYMBOLS`/`D IPLINFO` -- the real parsing lives entirely in
  `inventory/inventory/vtam_parser.py`, whose docstring carries the
  validation caveat. `D NET,MAJNODES` rows are matched by a name token
  followed by a known status value (`ACTIV`/`ACT/S`/`INACT`/`PEND*`)
  rather than fixed columns; `D NET,VTAMOPTS` is captured generically as
  `KEYWORD=VALUE` pairs (same idiom `discover_active_members.yml` uses
  for IEASYSxx), not a narrow `nodetype`/`cpname`-only model -- **APPN
  enablement/role is answered by filtering that generic table for the
  `NODETYPE`/`CPNAME` keywords**, not a dedicated field.
- `D NET,TOPO` (the APPN topology database -- adjacent/known network
  nodes) is deliberately **not** captured this round: its reply shape is
  even less certain than the two commands above, and this was an
  explicit call to not guess at it rather than ship an unreliable parser
  for the one piece with the least documentation to go on. A candidate
  follow-up once a real reply can be checked against it.
- `tcpip.yml`'s `D TCPIP,,NETSTAT,HOME` capture always runs; the
  `PROFILE.TCPIP` fetch only runs if `zos_extract_tcpip_profile_dsn` is
  set (it can name either a sequential dataset or a PDS member, e.g.
  `TCPIP.TCPPARMS(PROFILE1)` -- `zos_fetch`'s own documented behavior
  flattens either shape to just the dataset/member name locally, which
  `zos_extract_tcpip_profile_local_filename` accounts for). Profile
  statements are captured generically (statement name + raw operand
  text) since `PROFILE.TCPIP` syntax is positional
  (`DEVICE`/`LINK`/`HOME`/`PORT` ...), not uniform `KEYWORD=VALUE` like
  `VTAMOPTS`.

Run `ansible-playbook playbooks/site.yml --tags vtam,tcpip --limit
lpar1` (add `-e '{"zos_extract_tcpip_profile_dsn": "YOUR.PROFILE.DSN"}'`
to also exercise the profile fetch) against a real system and check the
resulting `vtam.txt`/`tcpip.txt` against what the parsers assume before
relying on any of these dimensions.

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
requirements.yml           # ibm.ibm_zos_core collection pin, plus
                            # ibm.ibm_zos_cics/ibm.ibm_zos_ims/ibm.ibm_zosmf
                            # for future expansion (all unused today)
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
                             # their SSN=/CMD=/PROD=/MSTRJCL= keywords --
                             # the active IEFSSNxx/COMMNDxx/IFAPRDxx
                             # suffixes, used by ssn_commnd.yml/ifaprd.yml
                             # to fetch just those members instead of
                             # every one matching the broad wildcard
                             # filter, plus the active MSTJCLxx suffix,
                             # used by discover_mstrjcl_proclibs.yml
    discover_mstrjcl_proclibs.yml
                             # fetches the active MSTJCLxx member and
                             # appends any proclib DSN concatenated onto
                             # its IEFPDSI DD to zos_extract_proclibs --
                             # accounts for proclib datasets invisible to
                             # '$D PROCLIB' (see above)
    proclib.yml, ssn_commnd.yml, ifaprd.yml
                             # zos_find + zos_fetch member dumps (see
                             # _member_dump.yml, the shared worker they
                             # each include per PROCLIB/PARMLIB entry)
    lnklst.yml, apf.yml, sysinfo.yml
                             # zos_operator / zos_apf console-command and
                             # APF-list analogs
    uss_mounts.yml            # 'D OMVS,F' captured raw (see above) --
                               # not yet validated against a real reply
    discover_jes2_parmlib.yml # auto-discovers zos_extract_jes2_parmlibs via
                               # JES2's '$D PARMLIB' if it isn't set
                               # explicitly -- message ID not confirmed,
                               # see the task file's own header comment
    jes2parm.yml               # dumps every member of every JES2 PARMLIB
                                # entry (see _member_dump.yml) -- JES2's
                                # own init deck, not yet validated
    vtam.yml                   # 'D NET,MAJNODES' + 'D NET,VTAMOPTS'
                                # bundled into one vtam.txt (see above) --
                                # not yet validated against a real reply
    tcpip.yml                  # 'D TCPIP,,NETSTAT,HOME' (always) + opt-in
                                # PROFILE.TCPIP fetch, bundled into one
                                # tcpip.txt (see above) -- not yet
                                # validated against a real reply
    activity.yml             # direct `jls -o id,name,status,jobtype,asid`
                              # (not zos_job_query, see above) + `ps -ef`
                              # for the live jobs/processes snapshot
    discover_active_address_spaces.yml
                               # shared 'D A,L' console query + parse for
                               # cics.yml/db2.yml (not zos_job_query, see
                               # above)
    cics.yml, db2.yml          # opt-in PROCSTEP/job-name filters over
                               # discover_active_address_spaces.yml's
                               # output -- not authoritative, see above
    smplist.yml               # zos_mvs_raw (GIMSMP) per SMP/E zone (see
                               # _smplist_zone.yml, the shared per-zone
                               # worker)
    discover_smpe_csis.yml     # opt-in zos_find (cluster) search for CSI
                                # candidates by naming pattern -- not
                                # authoritative, see above
    catalog.yml                # zos_find + zos_stat (non-VSAM) and
                                # zos_mvs_raw/IDCAMS (VSAM) combined
    racf.yml                   # zos_mvs_raw (IRRDBU00), implementation
                                # only -- see above
```
