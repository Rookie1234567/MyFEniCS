#!/usr/bin/env bash
set +e
raw=/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v9_resume_preparation/raw
targets=/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v7_preparation_audit/raw/elf_static_targets.txt
activation=/home/fenics/Projects/NN-Lab-V2/scripts/activate_task40_phi90_pord64.sh
printf 'scope=static direct dependency resolution; no library load, ldd, ompi_info, native import, or activation sourcing\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
printf 'activation_hash='; sha256sum "$activation"
printf 'activation_env_overrides_present=' 
for v in TASK40_SHARED_REPO_ROOT TASK40_SHARED_VENV TASK39EXTRA_INT64_STACK_ROOT TASK39EXTRA_PORD64_ROOT LD_LIBRARY_PATH LD_PRELOAD; do
  if [[ ${!v+x} ]]; then printf '%s=%q ' "$v" "${!v}"; else printf '%s=UNSET ' "$v"; fi
done
printf '\n'
shared=/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity
introot="$shared/tmp/task39extra_v5_abi_restore_20260923/base"
pord="$introot/prefix/pord64-overlay"
lddirs=("$pord/petsc/lib" "$pord/lib" "$introot/prefix/dolfinx_mpc-int64/lib" "$introot/prefix/dolfinx/lib" "$introot/prefix/scotch-int64/lib")
printf '\nACTIVATION_LD_LIBRARY_PATH (resolved from tracked defaults; script not sourced)\n'
for d in "${lddirs[@]}"; do printf '%s exists=%s\n' "$d" "$([[ -d "$d" ]] && echo yes || echo no)"; done

resolve_one() {
  local f=$1 name=$2 rp=$3 rpdirs=$4 cand= source= d expanded p owner pkg
  local -a dirs=()
  if [[ -n "$rp" && -z "$rpdirs" ]]; then dirs+=("$rp"); fi
  for d in "${lddirs[@]}"; do dirs+=("$d"); done
  if [[ -n "$rpdirs" ]]; then
    IFS=: read -r -a _rdirs <<< "$rpdirs"
    for d in "${_rdirs[@]}"; do
      expanded=${d//\$ORIGIN/$(dirname "$f")}
      dirs+=("$expanded")
    done
  fi
  for d in "${dirs[@]}"; do
    if [[ -e "$d/$name" ]]; then cand="$d/$name"; source="path:$d"; break; fi
  done
  if [[ -z "$cand" ]]; then
    cand=$(ldconfig -p 2>/dev/null | awk -v n="$name" '$1==n {print $NF; exit}')
    [[ -n "$cand" ]] && source=ld.so.cache
  fi
  if [[ -z "$cand" ]]; then printf 'UNRESOLVED parent=%s needed=%s\n' "$f" "$name"; return 1; fi
  real=$(realpath -e "$cand" 2>/dev/null)
  if [[ -z "$real" ]]; then printf 'MISSING_CANDIDATE parent=%s needed=%s candidate=%s source=%s\n' "$f" "$name" "$cand" "$source"; return 1; fi
  printf 'EDGE parent=%s needed=%s source=%s candidate=%s realpath=%s\n' "$f" "$name" "$source" "$cand" "$real"
  sha256sum "$real"
  readelf -nW "$real" 2>/dev/null | awk '/Build ID:/ {print "BUILD_ID " $0; exit}'
  readelf -dW "$real" 2>/dev/null | awk '/\((NEEDED|SONAME|RPATH|RUNPATH)\)/ {print "DYNAMIC " $0}'
  owner=$(dpkg-query -S "$real" 2>&1); rc=$?
  printf 'PACKAGE_OWNER exit=%s %s\n' "$rc" "$owner"
  if (( rc == 0 )); then
    pkg=${owner%%: *}
    dpkg-query -W -f='PACKAGE ${binary:Package} ${Version}\n' "$pkg" 2>&1
  fi
}

status=0
printf '\nDIRECT NEEDED EDGES FOR THE 15 FROZEN ELFS\n'
while IFS= read -r f; do
  [[ -n "$f" ]] || continue
  rp=$(readelf -dW "$f" 2>/dev/null | awk -F'[][]' '/\(RPATH\)/ {print $2; exit}')
  rpdirs=$(readelf -dW "$f" 2>/dev/null | awk -F'[][]' '/\(RUNPATH\)/ {print $2; exit}')
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    resolve_one "$f" "$name" "$rp" "$rpdirs" || status=1
  done < <(readelf -dW "$f" 2>/dev/null | awk -F'[][]' '/Shared library: \[/ {print $2}')
done < "$targets"

printf '\nTHREE EXPLICIT BRIDGE OBJECTS AND THEIR DIRECT NEEDED EDGES\n'
for name in libpsm_infinipath.so.1 libmca_common_ofi.so.10 libfabric.so.1; do
  cand=$(ldconfig -p 2>/dev/null | awk -v n="$name" '$1==n {print $NF; exit}')
  if [[ -z "$cand" ]]; then printf 'UNRESOLVED_BRIDGE %s\n' "$name"; status=1; continue; fi
  f=$(realpath -e "$cand" 2>/dev/null)
  if [[ -z "$f" ]]; then printf 'MISSING_BRIDGE %s candidate=%s\n' "$name" "$cand"; status=1; continue; fi
  printf 'BRIDGE %s candidate=%s realpath=%s\n' "$name" "$cand" "$f"
  sha256sum "$f"
  readelf -nW "$f" 2>/dev/null | awk '/Build ID:/ {print "BUILD_ID " $0; exit}'
  readelf -dW "$f" 2>/dev/null | awk '/\((NEEDED|SONAME|RPATH|RUNPATH)\)/ {print "DYNAMIC " $0}'
  owner=$(dpkg-query -S "$f" 2>&1); rc=$?
  printf 'PACKAGE_OWNER exit=%s %s\n' "$rc" "$owner"
  if (( rc == 0 )); then pkg=${owner%%: *}; dpkg-query -W -f='PACKAGE ${binary:Package} ${Version}\n' "$pkg" 2>&1; else status=1; fi
  rp=$(readelf -dW "$f" 2>/dev/null | awk -F'[][]' '/\(RPATH\)/ {print $2; exit}')
  rpdirs=$(readelf -dW "$f" 2>/dev/null | awk -F'[][]' '/\(RUNPATH\)/ {print $2; exit}')
  while IFS= read -r dep; do [[ -n "$dep" ]] || continue; resolve_one "$f" "$dep" "$rp" "$rpdirs" || status=1; done < <(readelf -dW "$f" 2>/dev/null | awk -F'[][]' '/Shared library: \[/ {print $2}')
done
exit "$status"
