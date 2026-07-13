#!/bin/sh

# Read-only capability probe for the Task029 direct-solver thread audit.
# Run inside the same image used by the benchmark artifacts.

set -u

section() {
    printf '\n===== %s =====\n' "$1"
}

section "PETSc and petsc4py"
/dolfinx-env/bin/python - <<'PY'
import petsc4py
from petsc4py import PETSc

print("petsc_version_info=", PETSc.Sys.getVersionInfo())
print("petsc4py_config=", petsc4py.get_config())
print("petsc_python_module=", PETSc.__file__)
PY

PETSC_DIR=$(/dolfinx-env/bin/python -c 'import petsc4py; print(petsc4py.get_config()["PETSC_DIR"])')
PETSC_ARCH=$(/dolfinx-env/bin/python -c 'from pathlib import Path; from petsc4py import PETSc; print(Path(PETSc.__file__).parent.name)')
ACTIVE_PETSC="$PETSC_DIR/$PETSC_ARCH"
printf 'active_petsc_arch=%s\n' "$PETSC_ARCH"

section "PETSc configure/build variables"
find "$ACTIVE_PETSC" -type f \( -name petscvariables -o -name petscconf.h \) \
    -print 2>/dev/null | while IFS= read -r path; do
        printf '%s\n' "--- $path"
        grep -E 'CONFIGURE_OPTIONS|PETSC_WITH_EXTERNAL_LIB|BLASLAPACK|MUMPS|OPENMP|OPENBLAS|MKL' "$path" 2>/dev/null || true
    done

section "PETSc dynamic linkage"
find "$ACTIVE_PETSC/lib" -type f -name 'libpetsc*.so*' -print 2>/dev/null | while IFS= read -r path; do
    printf '%s\n' "--- $path"
    ldd "$path" 2>/dev/null || true
done

section "MUMPS libraries, version hints, and linkage"
find "$ACTIVE_PETSC" -type f \
    \( -name 'lib*zmumps*.a' -o -name 'lib*mumps_common*.a' -o -name 'zmumps_c.h' \) \
    -print 2>/dev/null | while IFS= read -r path; do
        grep -H -E 'MUMPS_VERSION|MUMPS_VERSION_MAX|Version [0-9]+\.[0-9]+' "$path" 2>/dev/null || true
    done

section "Registered numerical runtimes"
ldconfig -p 2>/dev/null | grep -Ei 'openblas|blas|lapack|gomp|libomp|iomp|mkl|mumps' || true
printf 'system_openblas_target=%s\n' "$(readlink -f /lib/x86_64-linux-gnu/libopenblas.so.0)"
dpkg-query -W 'libopenblas*' 2>/dev/null || true

section "System OpenBLAS API and thread control"
OPENBLAS_NUM_THREADS=4 /dolfinx-env/bin/python - <<'PY'
import ctypes
import ctypes.util

path = ctypes.util.find_library("openblas")
library = ctypes.CDLL(path)
library.openblas_get_config.restype = ctypes.c_char_p
library.openblas_get_corename.restype = ctypes.c_char_p
library.openblas_get_parallel.restype = ctypes.c_int
library.openblas_get_num_threads.restype = ctypes.c_int
library.openblas_set_num_threads.argtypes = [ctypes.c_int]
print("library=", path)
print("config=", library.openblas_get_config().decode())
print("core=", library.openblas_get_corename().decode())
print("parallel_mode=", library.openblas_get_parallel())
print("threads_from_environment=", library.openblas_get_num_threads())
library.openblas_set_num_threads(2)
print("threads_after_runtime_set=", library.openblas_get_num_threads())
PY

section "NumPy BLAS control-only cross-check"
/dolfinx-env/bin/python - <<'PY'
import numpy

numpy.show_config()
try:
    from threadpoolctl import threadpool_info
except ImportError as exc:
    print("threadpoolctl_unavailable=", repr(exc))
else:
    print("threadpool_info=", threadpool_info())
PY

section "CPU visibility and affinity"
printf 'nproc=%s\n' "$(nproc)"
lscpu 2>/dev/null | grep -E '^(CPU\(s\)|On-line CPU|Thread|Core|Socket|NUMA|Model name)' || true
grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/self/status || true

section "Thread environment defaults"
env | grep -E '^(OMP|OPENBLAS|MKL|NUMEXPR|VECLIB|BLIS)_' || true

section "OpenBLAS runtime control probe"
OPENBLAS_VERBOSE=2 OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=1 \
    /dolfinx-env/bin/python - <<'PY'
import numpy as np

matrix = np.ones((768, 768))
print("matmul_check=", float((matrix @ matrix)[0, 0]))
PY
