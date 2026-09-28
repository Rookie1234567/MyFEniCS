#!/usr/bin/env bash
# Source with one of: pure (default), fe, ml. No old activation is sourced.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Source scripts/activate_task042.sh [pure|fe|ml].' >&2
  exit 2
fi

_TASK042_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
_TASK042_MODE="${1:-pure}"
if [[ "$(uname -s)" != Linux || "$_TASK042_ROOT" != /home/fenics/Projects/NN-Lab ]]; then
  echo 'Task042 requires its native Linux NN-Lab worktree.' >&2
  return 2
fi
case "$_TASK042_MODE" in
  pure|fe) _TASK042_VENV="$_TASK042_ROOT/.venv" ;;
  ml) _TASK042_VENV="$_TASK042_ROOT/.venv-ml" ;;
  *) echo 'Unknown Task042 environment mode.' >&2; return 2 ;;
esac
if [[ ! -f "$_TASK042_VENV/bin/activate" || -L "$_TASK042_VENV" ]]; then
  echo "Missing independent environment: $_TASK042_VENV" >&2
  return 2
fi
source "$_TASK042_VENV/bin/activate" || return
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH LD_PRELOAD PETSC_DIR PETSC_ARCH SLEPC_DIR
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION _MYFENICS_NATIVE_QUALIFIED_ACTIVATION
unset TASK39EXTRA_INT64_ACTIVATION TASK39EXTRA_PORD64_ACTIVATION
unset PHYSICAL_NATIVE_CAPACITY PHYSICAL_NATIVE_NODE_CAP_BYTES
unset PHYSICAL_WATCHDOG_PARENT_PID PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES PHYSICAL_WATCHDOG_PHASE_PATH
unset PHYSICAL_TIMEBASE_GUARD PHYSICAL_TIMEBASE_POLICY PKG_CONFIG_PATH
export PATH="$_TASK042_VENV/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="$_TASK042_ROOT"
export PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export CUDA_VISIBLE_DEVICES=''
export TASK042_ROOT="$_TASK042_ROOT" TASK042_ENV_MODE="$_TASK042_MODE"
export TASK042_ACTIVATION=1

_TASK042_CACHE="$_TASK042_ROOT/tmp/task042/$_TASK042_MODE"
export TMPDIR="$_TASK042_CACHE/tmp" TMP="$_TASK042_CACHE/tmp" TEMP="$_TASK042_CACHE/tmp"
export XDG_CACHE_HOME="$_TASK042_CACHE/xdg"
export FFCX_CACHE_DIR="$_TASK042_CACHE/xdg/fenics"
export PYTHONPYCACHEPREFIX="$_TASK042_CACHE/pycache"
export MPLCONFIGDIR="$_TASK042_CACHE/matplotlib"
export TORCH_HOME="$_TASK042_CACHE/torch" HF_HOME="$_TASK042_CACHE/huggingface"
export HUGGINGFACE_HUB_CACHE="$_TASK042_CACHE/huggingface/hub"
export TRANSFORMERS_CACHE="$_TASK042_CACHE/huggingface/transformers"
export TRITON_CACHE_DIR="$_TASK042_CACHE/triton" CUDA_CACHE_PATH="$_TASK042_CACHE/cuda"
export NUMBA_CACHE_DIR="$_TASK042_CACHE/numba"
export PIP_CACHE_DIR="$_TASK042_CACHE/pip" UV_CACHE_DIR="$_TASK042_CACHE/uv"
export PIP_NO_INPUT=1 PIP_DISABLE_PIP_VERSION_CHECK=1
export RUFF_CACHE_DIR="$_TASK042_CACHE/ruff"
export TASK042_RESULTS_ROOT="$_TASK042_ROOT/results/task042"
export TASK042_ARTIFACT_ROOT="$_TASK042_ROOT/benchmarks/artifacts/task042"
for _TASK042_PATH in "$TMPDIR" "$XDG_CACHE_HOME" "$FFCX_CACHE_DIR" \
    "$PYTHONPYCACHEPREFIX" "$MPLCONFIGDIR" "$TORCH_HOME" "$HF_HOME" \
    "$HUGGINGFACE_HUB_CACHE" "$TRANSFORMERS_CACHE" "$TRITON_CACHE_DIR" \
    "$CUDA_CACHE_PATH" "$NUMBA_CACHE_DIR" "$PIP_CACHE_DIR" "$UV_CACHE_DIR" "$RUFF_CACHE_DIR" \
    "$TASK042_RESULTS_ROOT" "$TASK042_ARTIFACT_ROOT"; do
  # Reject symlink escape before any writable directory is created.
  _TASK042_RESOLVED="$(realpath -m -- "$_TASK042_PATH")" || return
  if [[ "$_TASK042_RESOLVED" != "$_TASK042_ROOT/"* ]]; then
    echo "Task042 writable path escapes NN-Lab: $_TASK042_PATH" >&2
    return 2
  fi
  mkdir -p -- "$_TASK042_PATH" || return
done

if [[ "$_TASK042_MODE" == fe ]]; then
  # Read-only ABI prefix observed in the live qualified Task39 worker.
  _TASK042_FE_BASE="${TASK042_FE_BASE:-/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/tmp/task39extra_v5_abi_restore_20260923/base}"
  _TASK042_OVERLAY="$_TASK042_FE_BASE/prefix/pord64-overlay"
  for _TASK042_PATH in \
      "$_TASK042_OVERLAY/petsc/lib/libpetsc.so.3.19.6" \
      "$_TASK042_FE_BASE/prefix/dolfinx/lib/libdolfinx.so.0.10.0" \
      "$_TASK042_FE_BASE/prefix/dolfinx_mpc-int64/lib/libdolfinx_mpc.so.0.10.1"; do
    if [[ ! -f "$_TASK042_PATH" ]]; then
      echo "Missing read-only FE dependency: $_TASK042_PATH" >&2
      return 2
    fi
  done
  export PETSC_DIR="$_TASK042_OVERLAY/petsc" PETSC_ARCH=''
  export LD_LIBRARY_PATH="$_TASK042_OVERLAY/petsc/lib:$_TASK042_OVERLAY/lib:$_TASK042_FE_BASE/prefix/dolfinx_mpc-int64/lib:$_TASK042_FE_BASE/prefix/dolfinx/lib:$_TASK042_FE_BASE/prefix/scotch-int64/lib"
  export PYTHONPATH="$_TASK042_ROOT:$PETSC_DIR/lib:$_TASK042_FE_BASE/prefix/dolfinx_mpc-python:$_TASK042_FE_BASE/prefix/dolfinx-python:$_TASK042_FE_BASE/build-tools"
  export _MYFENICS_NATIVE_QUALIFIED_ACTIVATION=1
fi
hash -r
