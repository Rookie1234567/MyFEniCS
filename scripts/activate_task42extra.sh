#!/usr/bin/env bash
# Source with one of: pure (default), fe, ml. No old activation is sourced.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Source scripts/activate_task42extra.sh [pure|fe|ml].' >&2
  exit 2
fi

_TASK42EXTRA_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
_TASK42EXTRA_MODE="${1:-pure}"
if [[ "$(uname -s)" != Linux || "$_TASK42EXTRA_ROOT" != /home/fenics/Projects/NN-Lab-V2 ]]; then
  echo 'Task42extra requires its native Linux NN-Lab-V2 worktree.' >&2
  return 2
fi
case "$_TASK42EXTRA_MODE" in
  pure|fe) _TASK42EXTRA_VENV="$_TASK42EXTRA_ROOT/.venv" ;;
  ml) _TASK42EXTRA_VENV="$_TASK42EXTRA_ROOT/.venv-ml" ;;
  *) echo 'Unknown Task42extra environment mode.' >&2; return 2 ;;
esac
if [[ ! -f "$_TASK42EXTRA_VENV/bin/activate" || -L "$_TASK42EXTRA_VENV" ]]; then
  echo "Missing independent environment: $_TASK42EXTRA_VENV" >&2
  return 2
fi
source "$_TASK42EXTRA_VENV/bin/activate" || return
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH LD_PRELOAD PETSC_DIR PETSC_ARCH SLEPC_DIR
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION _MYFENICS_NATIVE_QUALIFIED_ACTIVATION
unset TASK39EXTRA_INT64_ACTIVATION TASK39EXTRA_PORD64_ACTIVATION
unset PHYSICAL_NATIVE_CAPACITY PHYSICAL_NATIVE_NODE_CAP_BYTES
unset PHYSICAL_WATCHDOG_PARENT_PID PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES PHYSICAL_WATCHDOG_PHASE_PATH
unset PHYSICAL_TIMEBASE_GUARD PHYSICAL_TIMEBASE_POLICY PKG_CONFIG_PATH
export PATH="$_TASK42EXTRA_VENV/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="$_TASK42EXTRA_ROOT"
export PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_THREAD_LIMIT=1 NUMEXPR_MAX_THREADS=1 GOTO_NUM_THREADS=1
export CMAKE_BUILD_PARALLEL_LEVEL=1 MAX_JOBS=1 RAYON_NUM_THREADS=1
export MAKEFLAGS='-j1'
export CUDA_VISIBLE_DEVICES=''
export TASK42EXTRA_ROOT="$_TASK42EXTRA_ROOT" TASK42EXTRA_ENV_MODE="$_TASK42EXTRA_MODE"
export TASK42EXTRA_ACTIVATION=1

_TASK42EXTRA_CACHE="$_TASK42EXTRA_ROOT/tmp/task42extra/$_TASK42EXTRA_MODE"
export TMPDIR="$_TASK42EXTRA_CACHE/tmp" TMP="$_TASK42EXTRA_CACHE/tmp" TEMP="$_TASK42EXTRA_CACHE/tmp"
export XDG_CACHE_HOME="$_TASK42EXTRA_CACHE/xdg"
export XDG_DATA_HOME="$_TASK42EXTRA_CACHE/data"
export XDG_CONFIG_HOME="$_TASK42EXTRA_CACHE/config"
export FFCX_CACHE_DIR="$_TASK42EXTRA_CACHE/xdg/fenics"
export PYTHONPYCACHEPREFIX="$_TASK42EXTRA_CACHE/pycache"
export MPLCONFIGDIR="$_TASK42EXTRA_CACHE/matplotlib"
export MPLBACKEND=Agg VTK_SMP_MAX_THREADS=1
export PYVISTA_USERDATA_PATH="$_TASK42EXTRA_CACHE/pyvista" POOCH_HOME="$_TASK42EXTRA_CACHE/pooch"
export TORCH_HOME="$_TASK42EXTRA_CACHE/torch" HF_HOME="$_TASK42EXTRA_CACHE/huggingface"
export HUGGINGFACE_HUB_CACHE="$_TASK42EXTRA_CACHE/huggingface/hub"
export TRANSFORMERS_CACHE="$_TASK42EXTRA_CACHE/huggingface/transformers"
export TRITON_CACHE_DIR="$_TASK42EXTRA_CACHE/triton" CUDA_CACHE_PATH="$_TASK42EXTRA_CACHE/cuda"
export NUMBA_CACHE_DIR="$_TASK42EXTRA_CACHE/numba"
export PIP_CACHE_DIR="$_TASK42EXTRA_CACHE/pip" UV_CACHE_DIR="$_TASK42EXTRA_CACHE/uv"
export PIP_NO_INPUT=1 PIP_DISABLE_PIP_VERSION_CHECK=1
export RUFF_CACHE_DIR="$_TASK42EXTRA_CACHE/ruff"
export TASK42EXTRA_RESULTS_ROOT="$_TASK42EXTRA_ROOT/results/task42extra"
export TASK42EXTRA_ARTIFACT_ROOT="$_TASK42EXTRA_ROOT/benchmarks/artifacts/task42extra"
for _TASK42EXTRA_PATH in "$TMPDIR" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$FFCX_CACHE_DIR" \
    "$PYVISTA_USERDATA_PATH" "$POOCH_HOME" \
    "$PYTHONPYCACHEPREFIX" "$MPLCONFIGDIR" "$TORCH_HOME" "$HF_HOME" \
    "$HUGGINGFACE_HUB_CACHE" "$TRANSFORMERS_CACHE" "$TRITON_CACHE_DIR" \
    "$CUDA_CACHE_PATH" "$NUMBA_CACHE_DIR" "$PIP_CACHE_DIR" "$UV_CACHE_DIR" "$RUFF_CACHE_DIR" \
    "$TASK42EXTRA_RESULTS_ROOT" "$TASK42EXTRA_ARTIFACT_ROOT"; do
  # Reject symlink escape before any writable directory is created.
  _TASK42EXTRA_RESOLVED="$(realpath -m -- "$_TASK42EXTRA_PATH")" || return
  if [[ "$_TASK42EXTRA_RESOLVED" != "$_TASK42EXTRA_ROOT/"* ]]; then
    echo "Task42extra writable path escapes NN-Lab-V2: $_TASK42EXTRA_PATH" >&2
    return 2
  fi
  mkdir -p -- "$_TASK42EXTRA_PATH" || return
done

if [[ "$_TASK42EXTRA_MODE" == fe ]]; then
  # Read-only ABI prefix observed in the live qualified Task39 worker.
  _TASK42EXTRA_FE_BASE="${TASK42EXTRA_FE_BASE:-/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/tmp/task39extra_v5_abi_restore_20260923/base}"
  _TASK42EXTRA_OVERLAY="$_TASK42EXTRA_FE_BASE/prefix/pord64-overlay"
  for _TASK42EXTRA_PATH in \
      "$_TASK42EXTRA_OVERLAY/petsc/lib/libpetsc.so.3.19.6" \
      "$_TASK42EXTRA_FE_BASE/prefix/dolfinx/lib/libdolfinx.so.0.10.0" \
      "$_TASK42EXTRA_FE_BASE/prefix/dolfinx_mpc-int64/lib/libdolfinx_mpc.so.0.10.1"; do
    if [[ ! -f "$_TASK42EXTRA_PATH" ]]; then
      echo "Missing read-only FE dependency: $_TASK42EXTRA_PATH" >&2
      return 2
    fi
  done
  export PETSC_DIR="$_TASK42EXTRA_OVERLAY/petsc" PETSC_ARCH=''
  export LD_LIBRARY_PATH="$_TASK42EXTRA_OVERLAY/petsc/lib:$_TASK42EXTRA_OVERLAY/lib:$_TASK42EXTRA_FE_BASE/prefix/dolfinx_mpc-int64/lib:$_TASK42EXTRA_FE_BASE/prefix/dolfinx/lib:$_TASK42EXTRA_FE_BASE/prefix/scotch-int64/lib"
  export PYTHONPATH="$_TASK42EXTRA_ROOT:$PETSC_DIR/lib:$_TASK42EXTRA_FE_BASE/prefix/dolfinx_mpc-python:$_TASK42EXTRA_FE_BASE/prefix/dolfinx-python:$_TASK42EXTRA_FE_BASE/build-tools"
  export _MYFENICS_NATIVE_QUALIFIED_ACTIVATION=1
fi
hash -r
