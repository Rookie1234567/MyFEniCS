#!/usr/bin/env bash
# Task40 uses the existing qualified shared Python/ABI stack read-only while
# keeping this worktree's source imports and all writable caches private.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Source this script.' >&2
  exit 2
fi

_TASK40_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
_TASK40_SHARED_REPO_ROOT="${TASK40_SHARED_REPO_ROOT:-/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity}"
_TASK40_SHARED_VENV="${TASK40_SHARED_VENV:-${_TASK40_SHARED_REPO_ROOT}/.venv}"
_TASK40_INT64_ROOT="${TASK39EXTRA_INT64_STACK_ROOT:-${_TASK40_SHARED_REPO_ROOT}/tmp/task39extra_v5_abi_restore_20260923/base}"
_TASK40_PORD64_ROOT="${TASK39EXTRA_PORD64_ROOT:-${_TASK40_INT64_ROOT}/prefix/pord64-overlay}"
_TASK40_PETSC="${_TASK40_PORD64_ROOT}/petsc"
_TASK40_DOLFINX="${_TASK40_INT64_ROOT}/prefix/dolfinx"
_TASK40_DOLFINX_PY="${_TASK40_INT64_ROOT}/prefix/dolfinx-python"
_TASK40_MPC="${_TASK40_INT64_ROOT}/prefix/dolfinx_mpc-int64"
_TASK40_MPC_PY="${_TASK40_INT64_ROOT}/prefix/dolfinx_mpc-python"
_TASK40_SCOTCH="${_TASK40_INT64_ROOT}/prefix/scotch-int64"

if [[ "$(uname -s)" != Linux ]] || grep -qi microsoft /proc/sys/kernel/osrelease; then
  echo 'Task40 qualified activation requires native Linux.' >&2
  return 2
fi
if [[ ! -d "${_TASK40_REPO_ROOT}/.git" && ! -f "${_TASK40_REPO_ROOT}/.git" ]]; then
  echo 'Task40 source root is not a Git worktree.' >&2
  return 2
fi
if [[ ! -x "${_TASK40_SHARED_VENV}/bin/python" || ! -f "${_TASK40_SHARED_VENV}/bin/activate" ]]; then
  echo "missing read-only shared interpreter: ${_TASK40_SHARED_VENV}/bin/python" >&2
  return 2
fi
for _TASK40_PATH in \
  "${_TASK40_PETSC}/lib/libpetsc.so.3.19.6" \
  "${_TASK40_PETSC}/lib/petsc4py/lib/petsc.cfg" \
  "${_TASK40_PORD64_ROOT}/lib/libpord.a" \
  "${_TASK40_PORD64_ROOT}/lib/libmumps_common.a" \
  "${_TASK40_DOLFINX}/lib" "${_TASK40_DOLFINX_PY}" \
  "${_TASK40_MPC}/lib" "${_TASK40_MPC_PY}"; do
  if [[ ! -e "${_TASK40_PATH}" ]]; then
    echo "missing qualified shared ABI path: ${_TASK40_PATH}" >&2
    return 2
  fi
done

source "${_TASK40_SHARED_VENV}/bin/activate" || return
export TASK39EXTRA_INT64_STACK_ROOT="${_TASK40_INT64_ROOT}"
export TASK39EXTRA_PORD64_ROOT="${_TASK40_PORD64_ROOT}"
export TASK40_SHARED_VENV_ROOT="${_TASK40_SHARED_VENV}"
export TASK39EXTRA_INT64_ACTIVATION=1
export TASK39EXTRA_PORD64_ACTIVATION=1
export _MYFENICS_NATIVE_QUALIFIED_ACTIVATION=1
export PETSC_DIR="${_TASK40_PETSC}"
export PETSC_ARCH=
unset SLEPC_DIR LD_PRELOAD PYTHONHOME DISPLAY
export PATH="${_TASK40_SHARED_VENV}/bin:/usr/local/bin:/usr/bin:/bin"
export LD_LIBRARY_PATH="${_TASK40_PETSC}/lib:${_TASK40_PORD64_ROOT}/lib:${_TASK40_MPC}/lib:${_TASK40_DOLFINX}/lib:${_TASK40_SCOTCH}/lib"
export PYTHONPATH="${_TASK40_REPO_ROOT}:${_TASK40_PETSC}/lib:${_TASK40_MPC_PY}:${_TASK40_DOLFINX_PY}:${_TASK40_INT64_ROOT}/build-tools"
export CMAKE_PREFIX_PATH="${_TASK40_PORD64_ROOT}:${_TASK40_MPC}:${_TASK40_DOLFINX}:${_TASK40_PETSC}:${_TASK40_SCOTCH}"
unset PKG_CONFIG_PATH
if [[ -n "$(find "${_TASK40_PETSC}/lib/pkgconfig" -maxdepth 1 -type f -name '*.pc' -print -quit 2>/dev/null)" ]]; then
  export PKG_CONFIG_PATH="${_TASK40_PETSC}/lib/pkgconfig"
fi
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export TMPDIR="${_TASK40_REPO_ROOT}/tmp"
export TMP="${TMPDIR}" TEMP="${TMPDIR}"
export XDG_CACHE_HOME="${TMPDIR}/xdg"
export MPLCONFIGDIR="${TMPDIR}/matplotlib"
export PYTHONPYCACHEPREFIX="${TMPDIR}/pycache"
mkdir -p -- "${TMPDIR}" "${XDG_CACHE_HOME}" "${MPLCONFIGDIR}" "${PYTHONPYCACHEPREFIX}" || return
hash -r
