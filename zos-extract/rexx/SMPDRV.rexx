/* REXX */
/*--------------------------------------------------------------------
 * SMPDRV -- Drive standard SMP/E LIST commands (LIST DDDEF/MOD/SYSMOD)
 *           against one CSI/zone, writing the SMPLIST report (that's the
 *           DD SMP/E actually prints LIST command output to -- not
 *           SYSPRINT, not SMPOUT, not SMPRPT) straight to a USS text
 *           file for off-host parsing by inventory/smpe_parser.py. The
 *           zone name itself is picked up from the page-header banner
 *           SMP/E prints on every page after SET BOUNDARY, so no
 *           separate zone-summary command is needed.
 *
 * Companion to zos-extract/python/smplist.py, which just builds the
 * parm string below and invokes this exec via `tsocmd EX ...` -- no
 * JCL submission and no bpxbatch needed.
 *
 * This has to be a REXX exec (not pure Python) because TSO dynamic
 * allocation is scoped to one address space: ALLOC and the program
 * CALL that uses those DDs must run in the same continuous TSO/E
 * environment, and each `tsocmd` invocation from a shell spawns a new
 * one. REXX is what stays in one environment for its whole run.
 *
 * Upload this exec once via your normal text-mode transfer process
 * (the same one you'd use for any other REXX member) so it lands
 * correctly EBCDIC-encoded -- e.g.:
 *   Via FTP: ascii mode, put SMPDRV.rexx 'your.exec.lib(SMPDRV)'
 *   Via Zowe CLI: zowe zos-files upload file-to-data-set SMPDRV.rexx
 *       "your.exec.lib(SMPDRV)"
 *
 * Usage (called by smplist.py, or directly if you prefer):
 *   EX 'your.exec.lib(SMPDRV)' 'CSI(dsn) ZONE(name) OUTFILE(path)
 *       WORKHLQ(hlq) [STEPLIB(dsn)]'
 *
 * Parameters:
 *   CSI(dsn)      - GLOBAL CSI data set name (required)
 *   ZONE(name)    - target zone name to report on (required)
 *   OUTFILE(path) - USS output text file path for the SMPLIST report
 *                   (required)
 *   WORKHLQ(hlq)  - HLQ for temporary SYSUT1-4 sort work data sets and
 *                   the SMPLOG data set SMP/E requires for every
 *                   function; all deleted again once GIMSMP finishes
 *                   (required)
 *   STEPLIB(dsn)  - SMP/E load library containing GIMSMP, if it's not
 *                   in your LNKLST (optional)
 *
 * SMP/E itself only needs READ access to the CSI for LIST commands (no
 * APPLY/ACCEPT/RECEIVE), so this is safe to run broadly.
 *------------------------------------------------------------------*/

parse arg parms

csi     = extract_parm(parms, 'CSI')
zone    = extract_parm(parms, 'ZONE')
outfile = extract_parm(parms, 'OUTFILE')
workhlq = extract_parm(parms, 'WORKHLQ')
steplib = extract_parm(parms, 'STEPLIB')

if csi = '' | zone = '' | outfile = '' | workhlq = '' then do
  say 'SMPDRV: CSI, ZONE, OUTFILE, and WORKHLQ are required.'
  say 'Example: EX SMPDRV ''CSI(MY.GLOBAL.CSI) ZONE(TZONE1)',
      'OUTFILE(/u/me/inventory/tzone1.smplist.txt) WORKHLQ(MYID.SMPLIST)'''
  exit 16
end

smprpt = outfile'.smprpt'
sysprint = outfile'.sysprint'

"ALLOC FI(SMPCSI) DA('"csi"') SHR REUSE"

/* SMP/E control statements are classic card-image input, so SMPCNTL is
   a real temporary MVS data set (RECFM=FB LRECL=80), not a USS PATH --
   PATH allocation's FILEDATA(TEXT)/RECFM interaction proved unreliable. */
cmd = "ALLOC FI(SMPCNTL) DA('"workhlq".SMPCNTL') NEW REUSE",
      "SPACE(1,1) CYL UNIT(SYSDA) RECFM(F B) LRECL(80)"
cmd

/* SMPLIST (not SYSPRINT, not SMPOUT, not SMPRPT) is where SMP/E writes
   the actual LIST command report. */
cmd = "ALLOC FI(SMPLIST) PATH('"outfile"')",
      "PATHOPTS(OWRONLY,OCREAT,OTRUNC) PATHMODE(SIRUSR,SIWUSR,SIRGRP)",
      "FILEDATA(TEXT)"
cmd

cmd = "ALLOC FI(SYSPRINT) PATH('"sysprint"')",
      "PATHOPTS(OWRONLY,OCREAT,OTRUNC) PATHMODE(SIRUSR,SIWUSR,SIRGRP)",
      "FILEDATA(TEXT)"
cmd

cmd = "ALLOC FI(SMPRPT) PATH('"smprpt"')",
      "PATHOPTS(OWRONLY,OCREAT,OTRUNC) PATHMODE(SIRUSR,SIWUSR,SIRGRP)",
      "FILEDATA(TEXT)"
cmd
"ALLOC FI(SYSUT1) DA('"workhlq".SYSUT1') NEW REUSE SPACE(5,5) CYL UNIT(SYSDA)"
"ALLOC FI(SYSUT2) DA('"workhlq".SYSUT2') NEW REUSE SPACE(5,5) CYL UNIT(SYSDA)"
"ALLOC FI(SYSUT3) DA('"workhlq".SYSUT3') NEW REUSE SPACE(5,5) CYL UNIT(SYSDA)"
"ALLOC FI(SYSUT4) DA('"workhlq".SYSUT4') NEW REUSE SPACE(5,5) CYL UNIT(SYSDA)"

cmd = "ALLOC FI(SMPLOG) DA('"workhlq".SMPLOG') NEW REUSE SPACE(5,5) CYL",
      "UNIT(SYSDA) RECFM(V B) LRECL(1632) BLKSIZE(6233)"
cmd

if steplib \= '' then
  "ALLOC FI(STEPLIB) DA('"steplib"') SHR REUSE"

queue '  SET BOUNDARY('zone') .'
queue ' '
queue '  LIST DDDEF .'
queue ' '
queue '  LIST MOD .'
queue ' '
queue '  LIST SYSMOD .'
"EXECIO" queued() "DISKW SMPCNTL (FINIS"

"CALL *(GIMSMP)"
gimsmp_rc = rc

ddlist = 'SMPCSI,SMPCNTL,SMPLIST,SYSPRINT,SMPRPT,SYSUT1,SYSUT2,SYSUT3,SYSUT4,',
         'SMPLOG'
if steplib \= '' then ddlist = ddlist',STEPLIB'
"FREE FI("ddlist")"

"DELETE '"workhlq".SMPCNTL'"
"DELETE '"workhlq".SYSUT1'"
"DELETE '"workhlq".SYSUT2'"
"DELETE '"workhlq".SYSUT3'"
"DELETE '"workhlq".SYSUT4'"
"DELETE '"workhlq".SMPLOG'"

say 'SMPDRV: GIMSMP rc='gimsmp_rc', report for zone' zone 'written to' outfile

exit gimsmp_rc

/*--------------------------------------------------------------------
 * extract_parm: pull KEY(value) out of a blank-delimited parm string
 *------------------------------------------------------------------*/
extract_parm: procedure
  parse arg instr, key
  up_instr = translate(instr)
  up_key   = translate(key)
  p = pos(up_key'(', up_instr)
  if p = 0 then return ''
  rest = substr(instr, p + length(key))
  if left(rest,1) \= '(' then return ''
  rest = substr(rest, 2)
  close = pos(')', rest)
  if close = 0 then return ''
  return strip(substr(rest, 1, close - 1))
