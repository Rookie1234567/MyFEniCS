#!/usr/bin/env bash
# Source this entry in the native Linux worktree.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Source this script.' >&2
  exit 2
fi
_MYFENICS_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "$(uname -s)" != Linux ]] || grep -qi microsoft /proc/sys/kernel/osrelease; then
  echo 'This entry requires native Linux.' >&2
  return 2
fi
source "${_MYFENICS_REPO_ROOT}/.venv/bin/activate" || return
export PETSC_DIR=/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex
export SLEPC_DIR=/usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex
export LD_LIBRARY_PATH="${VIRTUAL_ENV}/dolfinx_mpc-complex/lib:${PETSC_DIR}/lib:${SLEPC_DIR}/lib"
export PYTHONPATH="${PETSC_DIR}/lib/python3/dist-packages:${SLEPC_DIR}/lib/python3/dist-packages:/usr/lib/python3/dist-packages"
export PATH="${VIRTUAL_ENV}/bin:/usr/local/bin:/usr/bin:/bin"
unset PYTHONHOME DISPLAY _MYFENICS_WSL_QUALIFIED_ACTIVATION
export TMPDIR="${_MYFENICS_REPO_ROOT}/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="${TMPDIR}/xdg" MPLCONFIGDIR="${TMPDIR}/matplotlib"
export PYTHONPYCACHEPREFIX="${TMPDIR}/pycache"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$MPLCONFIGDIR" "$PYTHONPYCACHEPREFIX" || return
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
export _MYFENICS_NATIVE_QUALIFIED_ACTIVATION=1
hash -r
