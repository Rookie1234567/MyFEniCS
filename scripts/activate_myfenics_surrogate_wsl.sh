#!/usr/bin/env bash
# Source from the repository root after running install_local_wsl_environment.sh.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "This activation entry must be sourced." >&2
  exit 2
fi

_MYFENICS_SURROGATE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "${_MYFENICS_SURROGATE_ROOT}" == /mnt/* ]]; then
  echo "Formal surrogate work must use the WSL Linux filesystem." >&2
  return 2
fi

# Reuse the repository-qualified complex ABI selection and Linux-only PATH.
# shellcheck disable=SC1091
source "${_MYFENICS_SURROGATE_ROOT}/scripts/activate_myfenics_wsl.sh" || return $?

_MYFENICS_SURROGATE_RUNTIME="${_MYFENICS_SURROGATE_ROOT}/benchmarks/artifacts/task000/runtime"
export TMPDIR="${_MYFENICS_SURROGATE_RUNTIME}/tmp"
export TMP="${TMPDIR}"
export TEMP="${TMPDIR}"
export XDG_CACHE_HOME="${_MYFENICS_SURROGATE_RUNTIME}/xdg-cache"
export MPLCONFIGDIR="${_MYFENICS_SURROGATE_RUNTIME}/matplotlib"
export MYFENICS_SURROGATE_LOG_DIR="${_MYFENICS_SURROGATE_RUNTIME}/logs"
export MYFENICS_SURROGATE_ARTIFACT_DIR="${_MYFENICS_SURROGATE_ROOT}/benchmarks/artifacts/task000/runs"

if ! mkdir -p -- \
  "${TMPDIR}" "${XDG_CACHE_HOME}" "${MPLCONFIGDIR}" \
  "${MYFENICS_SURROGATE_LOG_DIR}" "${MYFENICS_SURROGATE_ARTIFACT_DIR}"; then
  echo "Unable to create project-local surrogate runtime directories." >&2
  return 2
fi

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export MYFENICS_MAX_PARALLEL_FORWARD_SOLVES=1
export _MYFENICS_SURROGATE_WSL_QUALIFIED_ACTIVATION=1

if [[ "$(git -C "${_MYFENICS_SURROGATE_ROOT}" branch --show-current 2>/dev/null)" \
      != "codex/only-one-13p5nm-surrogate-inversion" ]]; then
  echo "Unexpected surrogate execution branch." >&2
  return 2
fi
if [[ "$(git -C "${_MYFENICS_SURROGATE_ROOT}" rev-parse \
      --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)" \
      != "origin/codex/only-one-13p5nm-surrogate-inversion" ]]; then
  echo "Unexpected surrogate upstream." >&2
  return 2
fi

hash -r 2>/dev/null || true
