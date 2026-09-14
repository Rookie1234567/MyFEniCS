#!/usr/bin/env bash
# Source this opt-in entry for the task-local PETSc/DOLFINx/MPC int64 stack.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Source this script.' >&2
  exit 2
fi

_TASK39EXTRA_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
_TASK39EXTRA_INT64_ROOT="${TASK39EXTRA_INT64_STACK_ROOT:-/tmp/task39extra_para_int64_stack}"
_TASK39EXTRA_PETSC="${_TASK39EXTRA_INT64_ROOT}/prefix/petsc"
_TASK39EXTRA_DOLFINX="${_TASK39EXTRA_INT64_ROOT}/prefix/dolfinx"
_TASK39EXTRA_DOLFINX_PY="${_TASK39EXTRA_INT64_ROOT}/prefix/dolfinx-python"
_TASK39EXTRA_MPC="${_TASK39EXTRA_INT64_ROOT}/prefix/dolfinx_mpc-int64"
_TASK39EXTRA_MPC_PY="${_TASK39EXTRA_INT64_ROOT}/prefix/dolfinx_mpc-python"
_TASK39EXTRA_SCOTCH="${_TASK39EXTRA_INT64_ROOT}/prefix/scotch-int64"
for _TASK39EXTRA_PATH in "${_TASK39EXTRA_PETSC}/lib" "${_TASK39EXTRA_DOLFINX}/lib" \
    "${_TASK39EXTRA_MPC}/lib" "${_TASK39EXTRA_MPC_PY}" "${_TASK39EXTRA_DOLFINX_PY}"; do
  if [[ ! -d "${_TASK39EXTRA_PATH}" ]]; then
    echo "missing task-local int64 stack path: ${_TASK39EXTRA_PATH}" >&2
    return 2
  fi
done

# Reuse the native entry's platform and inherited-environment checks, then
# replace its default ABI paths below without carrying old PETSc/SLEPc paths.
source "${_TASK39EXTRA_REPO_ROOT}/scripts/activate_myfenics_linux.sh" || return
export PETSC_DIR="${_TASK39EXTRA_PETSC}"
unset SLEPC_DIR
export TASK39EXTRA_INT64_ACTIVATION=1
export TASK39EXTRA_INT64_STACK_ROOT="${_TASK39EXTRA_INT64_ROOT}"
export _MYFENICS_NATIVE_QUALIFIED_ACTIVATION=1
export LD_LIBRARY_PATH="${_TASK39EXTRA_MPC}/lib:${_TASK39EXTRA_DOLFINX}/lib:${_TASK39EXTRA_PETSC}/lib:${_TASK39EXTRA_SCOTCH}/lib"
export PYTHONPATH="${_TASK39EXTRA_MPC_PY}:${_TASK39EXTRA_DOLFINX_PY}:${_TASK39EXTRA_PETSC}/lib:${_TASK39EXTRA_INT64_ROOT}/build-tools"
export CMAKE_PREFIX_PATH="${_TASK39EXTRA_MPC}:${_TASK39EXTRA_DOLFINX}:${_TASK39EXTRA_PETSC}:${_TASK39EXTRA_SCOTCH}"
export PKG_CONFIG_PATH="${_TASK39EXTRA_PETSC}/lib/pkgconfig"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
export TMPDIR="${_TASK39EXTRA_REPO_ROOT}/tmp"
export XDG_CACHE_HOME="${TMPDIR}/xdg" MPLCONFIGDIR="${TMPDIR}/matplotlib"
export PYTHONPYCACHEPREFIX="${TMPDIR}/pycache"
mkdir -p "${TMPDIR}" "${XDG_CACHE_HOME}" "${MPLCONFIGDIR}" "${PYTHONPYCACHEPREFIX}" || return
hash -r
