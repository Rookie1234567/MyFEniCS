#!/usr/bin/env bash
# Source this explicit opt-in entry for the task-local PORD64 PETSc stack.
# The ordinary activate_task39extra_int64.sh entry remains the default int64
# stack; this entry only selects the separately rebuilt PORD/PETSc prefix.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Source this script.' >&2
  exit 2
fi

_TASK39EXTRA_PORD64_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
_TASK39EXTRA_PORD64_ROOT="${TASK39EXTRA_PORD64_ROOT:-/tmp/task39extra-pord64}"
_TASK39EXTRA_PORD64_PETSC="${_TASK39EXTRA_PORD64_ROOT}/petsc"

# Reuse the already qualified task-local DOLFINx/MPC/Python environment, then
# replace only the PETSc/PORD runtime and petsc4py metadata paths below.
source "${_TASK39EXTRA_PORD64_REPO_ROOT}/scripts/activate_task39extra_int64.sh" || return
for _TASK39EXTRA_PORD64_PATH in \
    "${_TASK39EXTRA_PORD64_PETSC}/lib/libpetsc.so.3.19.6" \
    "${_TASK39EXTRA_PORD64_PETSC}/lib/petsc4py/lib/petsc.cfg" \
    "${_TASK39EXTRA_PORD64_ROOT}/lib/libpord.a" \
    "${_TASK39EXTRA_PORD64_ROOT}/lib/libmumps_common.a"; do
  if [[ ! -e "${_TASK39EXTRA_PORD64_PATH}" ]]; then
    echo "missing task-local PORD64 stack path: ${_TASK39EXTRA_PORD64_PATH}" >&2
    return 2
  fi
done

export TASK39EXTRA_PORD64_ACTIVATION=1
export TASK39EXTRA_PORD64_ROOT="${_TASK39EXTRA_PORD64_ROOT}"
export PETSC_DIR="${_TASK39EXTRA_PORD64_PETSC}"
export PETSC_ARCH=
unset SLEPC_DIR
unset LD_PRELOAD
export LD_LIBRARY_PATH="${_TASK39EXTRA_PORD64_PETSC}/lib:${_TASK39EXTRA_PORD64_ROOT}/lib:${_TASK39EXTRA_MPC}/lib:${_TASK39EXTRA_DOLFINX}/lib:${_TASK39EXTRA_SCOTCH}/lib"
export PYTHONPATH="${_TASK39EXTRA_PORD64_PETSC}/lib:${_TASK39EXTRA_MPC_PY}:${_TASK39EXTRA_DOLFINX_PY}:${_TASK39EXTRA_PORD64_REPO_ROOT}:${_TASK39EXTRA_INT64_ROOT}/build-tools"
export CMAKE_PREFIX_PATH="${_TASK39EXTRA_PORD64_PETSC}:${_TASK39EXTRA_MPC}:${_TASK39EXTRA_DOLFINX}:${_TASK39EXTRA_SCOTCH}"
unset PKG_CONFIG_PATH
if [[ -n "$(find "${_TASK39EXTRA_PORD64_PETSC}/lib/pkgconfig" -maxdepth 1 -type f -name '*.pc' -print -quit 2>/dev/null)" ]]; then
  export PKG_CONFIG_PATH="${_TASK39EXTRA_PORD64_PETSC}/lib/pkgconfig"
fi
hash -r
