#!/usr/bin/env bash
set +e
status=0
targets=/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v7_preparation_audit/raw/elf_static_targets.txt
printf 'scope=static metadata only; readelf/hash/package query; no ldd, dlopen, native import, or MPI command\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  printf '\n===== %s =====\n' "$path"
  if [[ ! -f "$path" ]]; then printf 'MISSING\n'; status=1; continue; fi
  printf 'realpath='; realpath -e "$path" || status=1
  sha256sum "$path" || status=1
  readelf -nW "$path" 2>&1 | grep -E 'Build ID:' || status=1
  readelf -dW "$path" 2>&1 | grep -E '\((NEEDED|SONAME|RPATH|RUNPATH)\)' || true
  owner_output=$(dpkg-query -S "$path" 2>&1)
  rc=$?
  printf 'owner_exit=%s owner=%s\n' "$rc" "$owner_output"
  if (( rc == 0 )); then
    package=${owner_output%%: *}
    dpkg-query -W -f='package=${binary:Package} version=${Version}\n' "$package" || status=1
  else status=1; fi
done < "$targets"
exit "$status"
