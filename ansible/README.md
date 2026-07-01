# ansible

Orchestrates step 1 of the pipeline described in the top-level
[`README.md`](../README.md) and [`zos-extract/README.md`](../zos-extract/README.md)
via Ansible, instead of you SSHing into each LPAR by hand and running every
`zos-extract/python/*.py` script and `scp` one at a time. It doesn't
reimplement any of that logic -- it stages the existing, tested
`zos-extract/python/` scripts onto each target LPAR, runs them with the
[`ibm.ibm_zos_core`](https://github.com/ansible-collections/ibm_zos_core)
collection, and fetches the resulting text files straight into a local
directory that's ready for `inventory ingest` (see
[`../inventory/README.md`](../inventory/README.md)).

## Why `ibm.ibm_zos_core`

`zos_common.py`'s own docstring already notes that this project's ZOAU calls
were cross-checked against `ibm_zos_core`'s source, since it wraps the same
`zoautil_py` API this pipeline uses directly. That collection also ships the
two pieces this directory actually needs:

- the `ibm.ibm_zos_core.zos_ssh` connection plugin, which handles the
  USS/dataset text-encoding details a plain `ssh` connection doesn't, and
- `zos_copy` / `zos_fetch`, for pushing the scripts onto the LPAR and
  pulling the output back off it -- replacing the manual `scp -r` step in
  `zos-extract/README.md`'s "Getting the output off-host" section.

## Prerequisites

Everything in `zos-extract/README.md`'s "Before you start" section still
applies (OMVS shell, IBM Open Enterprise Python, ZOAU, read authority).
On top of that:

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
paths there if your site installs ZOAU/Python somewhere else.

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
`sysinfo`, `smplist`, `activity`, `catalog`, `racf`, `fetch`.
`smplist`/`catalog` only run on hosts where `zos_extract_smpe_csi`/`zos_extract_catalog_patterns`
are actually set, so it's safe to leave them out of `hosts.yml` for LPARs
you don't want those steps on.

### RACF (step 10) is opt-in on purpose

Per `zos-extract/README.md`, `extrracf.py` needs a materially different and
harder-to-get authorization (READ access to a RACF database **copy**), and
its output is explicitly implementation-only / not yet production-validated.
This role won't run it unless you both set `zos_extract_racf_database_dsn` in
`hosts.yml` **and** pass `--tags racf` explicitly:

```
ansible-playbook playbooks/site.yml --tags racf --limit lpar1
```

## Layout

```
ansible.cfg
requirements.yml           # ibm.ibm_zos_core collection pin
inventory/hosts.yml.example
inventory/group_vars/zos.yml  # shared ZOAU/Python env + staging/output paths
                               # (must live beside the inventory file --
                               # that's how Ansible auto-loads group_vars)
playbooks/site.yml         # entry point
roles/zos_extract/
  defaults/main.yml        # per-step defaults (member filters, HLQs, ...)
  tasks/
    main.yml               # dispatches to one file per step, by tag
    stage.yml              # zos_copy's zos-extract/python/ onto the target
    proclib.yml ...        # one task file per zos-extract/README.md step
    fetch.yml              # zos_fetch's *.txt back to output/<host>/
```
