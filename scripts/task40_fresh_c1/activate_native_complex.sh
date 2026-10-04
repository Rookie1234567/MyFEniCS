#!/usr/bin/env bash
# Explicit new-runtime imports-only activation; this does not grant FE/JIT PASS.
set -e
cloud_c1_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cloud_c1_repo="$(cd "$cloud_c1_script_dir/../.." && pwd)"
cloud_c1_prefix="${1:?pass the explicit native independent prefix}"
cloud_c1_manifest="${2:?run-local imports-only ABI receipt required}"
cloud_c1_cache="${3:?run-local JIT cache directory required}"
if [[ ! -x "$cloud_c1_prefix/bin/python" || ! -f "$cloud_c1_manifest" ]]; then
  echo "fresh native prefix or run-local imports-only ABI receipt missing" >&2; return 1
fi
export PATH="$cloud_c1_prefix/bin:$PATH"
unset PYTHONPATH PYTHONHOME LD_PRELOAD LD_LIBRARY_PATH
export UCX_TLS=self
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export XDG_CACHE_HOME="$cloud_c1_cache"
mkdir -p "$XDG_CACHE_HOME"
if ! python - "$cloud_c1_manifest" "$cloud_c1_prefix" <<'PYCODE'
import json,pathlib,sys
from petsc4py import PETSc
from mpi4py import MPI
import numpy as np
p=pathlib.Path(sys.argv[1]);prefix=pathlib.Path(sys.argv[2]).resolve();r=json.loads(p.read_text())
assert r['status']=='IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION'
assert pathlib.Path(sys.prefix).resolve()==prefix==pathlib.Path(r['prefix']).resolve()
assert np.dtype(PETSc.ScalarType)==np.dtype(np.complex128)
assert np.dtype(PETSc.IntType).name==r['PETSc']['int_dtype']=='int32'
assert list(PETSc.Sys.getVersion())==r['PETSc']['version']==[3,25,6]
assert MPI.COMM_WORLD.size==1 and MPI.COMM_WORLD.rank==0
assert MPI.Get_library_version()==r['MPI']['library_version']
PYCODE
then
  return 1
fi
cloud_c1_hash="$(python - "$cloud_c1_manifest" <<'PYHASH'
import hashlib,pathlib,sys
print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PYHASH
)"
export _MYFENICS_CLOUD_QUALIFIED_ACTIVATION=1
export _MYFENICS_CLOUD_ABI_MANIFEST="$cloud_c1_manifest"
export _MYFENICS_CLOUD_ABI_MANIFEST_SHA256="$cloud_c1_hash"
export _MYFENICS_CLOUD_QUALIFICATION_SCOPE=imports_only_C1_FE_JIT_NOT_RUN
unset cloud_c1_script_dir cloud_c1_repo cloud_c1_prefix cloud_c1_manifest cloud_c1_hash cloud_c1_cache
