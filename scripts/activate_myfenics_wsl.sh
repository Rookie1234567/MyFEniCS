#!/usr/bin/env bash
# Source from the repository root: source scripts/activate_myfenics_wsl.sh

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "This activation entry must be sourced." >&2
  exit 2
fi

_MYFENICS_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if ! grep -qi microsoft /proc/sys/kernel/osrelease; then
  echo "Task034 qualification requires native WSL2 Linux." >&2
  return 2
fi
if [[ ! -f "${_MYFENICS_REPO_ROOT}/.venv/bin/activate" ]]; then
  echo "Missing ${_MYFENICS_REPO_ROOT}/.venv; create it with:" >&2
  echo "  /usr/bin/python3 -m venv --system-site-packages .venv" >&2
  return 2
fi

# shellcheck disable=SC1091
source "${_MYFENICS_REPO_ROOT}/.venv/bin/activate"
export PETSC_DIR=/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex
export SLEPC_DIR=/usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex
if [[ ! -d "${PETSC_DIR}" || ! -d "${SLEPC_DIR}" ]]; then
  echo "Qualified complex PETSc/SLEPc directories are unavailable." >&2
  return 2
fi
_MYFENICS_MPC_PREFIX="${VIRTUAL_ENV}/dolfinx_mpc-complex"
if [[ ! -f "${_MYFENICS_MPC_PREFIX}/lib/libdolfinx_mpc.so" ]]; then
  echo "Missing project-local complex dolfinx_mpc under ${_MYFENICS_MPC_PREFIX}." >&2
  echo "Run the Task034 environment qualification build procedure first." >&2
  return 2
fi
export CMAKE_PREFIX_PATH="${_MYFENICS_MPC_PREFIX}${CMAKE_PREFIX_PATH:+:${CMAKE_PREFIX_PATH}}"
export LD_LIBRARY_PATH="${_MYFENICS_MPC_PREFIX}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
_MYFENICS_VENV_SITE="${VIRTUAL_ENV}/lib/python3.12/site-packages"
export PYTHONPATH="${_MYFENICS_VENV_SITE}:${PETSC_DIR}/lib/python3/dist-packages:${SLEPC_DIR}/lib/python3/dist-packages:/usr/lib/python3/dist-packages"
export PATH="${VIRTUAL_ENV}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
unset PYTHONHOME
# Windows Codex may pass TMP/TEMP through as Windows-mounted paths. Keep
# Python, OpenMPI, PETSc, and test scratch data on the WSL Linux filesystem.
export TMPDIR=/tmp
export TMP=/tmp
export TEMP=/tmp
if [[ ! -d "${TMPDIR}" || ! -w "${TMPDIR}" ]]; then
  echo "Qualified WSL temporary directory ${TMPDIR} is unavailable." >&2
  return 2
fi
# DOLFINx/FFCx resolves its JIT cache from XDG_CACHE_HOME at import time.
# Windows Codex sessions may inherit a Linux HOME that the managed sandbox can
# read but not write, so all generated compiler/cache files stay under /tmp.
export XDG_CACHE_HOME="${TMPDIR}/myfenics-xdg-cache-${UID}"
export MPLCONFIGDIR="${TMPDIR}/myfenics-matplotlib-${UID}"
if ! mkdir -p -- "${XDG_CACHE_HOME}" "${MPLCONFIGDIR}"; then
  echo "Unable to create qualified WSL cache directories." >&2
  return 2
fi
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export _MYFENICS_WSL_QUALIFIED_ACTIVATION=1
hash -r 2>/dev/null || true
