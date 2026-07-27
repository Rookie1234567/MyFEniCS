#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "${root}"

echo "root=$(git rev-parse --show-toplevel)"
echo "git_dir=$(git rev-parse --absolute-git-dir)"
echo "origin=$(git remote get-url origin)"
echo "branch=$(git branch --show-current)"
echo "upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}')"
echo "head=$(git rev-parse HEAD)"
echo "ahead_behind=$(git rev-list --left-right --count 'HEAD...@{u}')"
echo "status_begin"
git status --short --untracked-files=all
echo "status_end"
echo "venv_python=${root}/.venv/bin/python"
echo "venv_present=$([[ -x .venv/bin/python ]] && echo yes || echo no)"
echo "runtime_root=${root}/benchmarks/artifacts/task000/runtime"
echo "memory_begin"
free -h
echo "memory_end"
echo "swap_begin"
cat /proc/swaps
echo "swap_end"
echo "disk_begin"
df -hT "${root}"
echo "disk_end"

if [[ -x .venv/bin/python ]]; then
  # shellcheck disable=SC1091
  source scripts/activate_myfenics_surrogate_wsl.sh
  python -c 'import json,numpy as np,sys; from petsc4py import PETSc; import dolfinx,dolfinx_mpc; print("abi="+json.dumps({"python":sys.executable,"petsc_scalar":str(np.dtype(PETSc.ScalarType)),"petsc_int_bits":np.dtype(PETSc.IntType).itemsize*8,"dolfinx":dolfinx.__version__,"dolfinx_mpc":dolfinx_mpc.__file__},sort_keys=True))'
else
  echo "abi=unavailable"
fi
