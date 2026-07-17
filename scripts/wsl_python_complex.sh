#!/usr/bin/env bash
set -euo pipefail

for candidate in \
  /usr/lib/petscdir/petsc-complex \
  /usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex
do
  if [ -d "$candidate" ]; then
    export PETSC_DIR="$candidate"
    break
  fi
done

for candidate in \
  /usr/lib/slepcdir/slepc-complex \
  /usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex
do
  if [ -d "$candidate" ]; then
    export SLEPC_DIR="$candidate"
    break
  fi
done

if [ -z "${PETSC_DIR:-}" ]; then
  echo "complex PETSc was not found; install python3-dolfinx-complex first" >&2
  exit 2
fi

project_root="/mnt/c/Users/Administrator/Desktop/MyProject"
mpc_prefix="/home/fenics/opt/dolfinx-mpc-0.10.1-complex-petsc3.19-v2"
if [ ! -d "${mpc_prefix}/python/dolfinx_mpc" ]; then
  echo "complex dolfinx_mpc extension was not found under ${mpc_prefix}" >&2
  exit 2
fi
export PYTHONPATH="${mpc_prefix}/python:${PETSC_DIR}/lib/python3/dist-packages:/usr/lib/python3/dist-packages:${project_root}${PYTHONPATH:+:${PYTHONPATH}}"
export LD_LIBRARY_PATH="${mpc_prefix}/lib:${PETSC_DIR}/lib${SLEPC_DIR:+:${SLEPC_DIR}/lib}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export PYTHONUNBUFFERED=1

exec /usr/bin/python3 "$@"
