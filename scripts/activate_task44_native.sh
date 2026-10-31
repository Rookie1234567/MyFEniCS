#!/usr/bin/env bash
# Source from the Task44 worktree. Reuse the qualified host ABI read-only while
# binding Python imports and JIT caches to this checkout.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    printf '%s\n' 'Source this file; do not execute it.' >&2
    exit 2
fi

_task44_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd -P)"
_task44_abi_venv="${MYFENICS_NATIVE_ABI_VENV:-/home/fenics/Projects/MyFEniCS/.venv}"
if [[ ! -f "${_task44_abi_venv}/bin/activate" || ! -x "${_task44_abi_venv}/bin/python" ]]; then
    printf 'Task44 ABI venv is unavailable: %s\n' "${_task44_abi_venv}" >&2
    return 2
fi
if [[ ! -d "${_task44_abi_venv}/dolfinx_mpc-complex/lib" ]]; then
    printf 'Task44 complex dolfinx_mpc library is unavailable: %s\n' "${_task44_abi_venv}/dolfinx_mpc-complex/lib" >&2
    return 2
fi

source "${_task44_abi_venv}/bin/activate"
unset PYTHONHOME LD_PRELOAD
export TMPDIR=/tmp
export TMP=/tmp
export TEMP=/tmp
if [[ ! -d /tmp || ! -w /tmp ]]; then
    printf '%s\n' 'Task44 native activation requires writable /tmp' >&2
    return 2
fi
_task44_cache_root="${MYFENICS_TASK44_CACHE_ROOT:-/tmp/myfenics-task44-native-cache-${UID}}"
export XDG_CACHE_HOME="${_task44_cache_root}/xdg"
export MPLCONFIGDIR="${_task44_cache_root}/matplotlib"
if ! mkdir -p "${XDG_CACHE_HOME}" "${MPLCONFIGDIR}"; then
    printf '%s\n' 'Task44 native activation cannot create its isolated cache directories' >&2
    return 2
fi

export PETSC_DIR=/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex
export SLEPC_DIR=/usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex
export DOLFINX_MPC_DIR="${_task44_abi_venv}/dolfinx_mpc-complex"
export PYTHONPATH="${_task44_root}:${PETSC_DIR}/lib/python3/dist-packages:${SLEPC_DIR}/lib/python3/dist-packages:/usr/lib/python3/dist-packages"
export LD_LIBRARY_PATH="${DOLFINX_MPC_DIR}/lib:${PETSC_DIR}/lib:${SLEPC_DIR}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export CMAKE_PREFIX_PATH="${DOLFINX_MPC_DIR}${CMAKE_PREFIX_PATH:+:${CMAKE_PREFIX_PATH}}"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export BLIS_NUM_THREADS=1
# Task44 is qualified for one MPI rank. Keep the Linux hwloc backend while
# avoiding x86 discovery's temporary rebinding across host CPUs; use Open MPI's
# OB1 layer and let the MPI rank inherit systemd's selected CPU affinity.
export HWLOC_COMPONENTS=-x86
export OMPI_MCA_pml=ob1
export OMPI_MCA_hwloc_base_binding_policy=none
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION
export MYFENICS_NATIVE_COMPLEX_ENV=1
export MYFENICS_TASK44_ROOT="${_task44_root}"
unset _task44_root _task44_abi_venv _task44_cache_root
