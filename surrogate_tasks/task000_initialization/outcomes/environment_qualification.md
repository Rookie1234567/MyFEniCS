# Task000 原生 WSL 环境资格化

## 结论

- 状态：`environment_gate_pass`
- 平台：WSL2 Ubuntu 24.04，仓库位于 Linux filesystem
- Docker：保留但未进入、未调用；本次环境安装和资格化均为 Ubuntu 原生执行
- 最大并行前向求解数：`1`
- 默认线程：OMP/BLAS/MKL/NumExpr 均为 `1`

## 安装身份

| 组件 | 版本或身份 | 实际来源/路径 |
|---|---|---|
| Python | 3.12.3 | `.venv/bin/python` |
| DOLFINx Debian package | `1:0.10.0.post3-2~ppa2~noble7` | FEniCS Ubuntu PPA |
| `dolfinx.__version__` | `0.10.0.post2` | `/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex/lib/python3/dist-packages/dolfinx` |
| PETSc / petsc4py | 3.19 / 3.19.6 | `/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex` |
| SLEPc / slepc4py | 3.19 / 3.19.2 | `/usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex` |
| Basix | 0.10.0 | `/usr/lib/python3/dist-packages/basix` |
| UFL | 2025.2.1 | `/usr/lib/python3/dist-packages/ufl` |
| FFCx | 0.10.1.post0 | `/usr/lib/python3/dist-packages/ffcx` |
| mpi4py | 3.1.5 | `/usr/lib/python3/dist-packages/mpi4py` |
| OpenMPI | 4.1.6 | `/usr/bin/mpiexec`, `/lib/x86_64-linux-gnu/libmpi.so.40` |
| PyVista / VTK | 0.44.1 / 9.1.0 | FEniCS PPA / Ubuntu system packages |
| dolfinx_mpc | 0.10.1, commit `a444aa3006fdf492091443cc8c885c1eec006c2f` | project `.venv` and `.venv/dolfinx_mpc-complex` |
| scikit-build-core | 0.11.1 | project `.venv`; first pinned line used here with PEP 639 license-expression support |
| nanobind | 2.4.0 | project `.venv` |

The Debian package version and Python module's `__version__` string differ by one
packaging post-release suffix; package identity, loaded library ABI, and the fixed
apt version are recorded separately rather than silently normalised.

## ABI preflight

| Gate | Result | Evidence |
|---|---|---|
| project-local interpreter | PASS | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python` |
| complex scalar | PASS | `PETSc.ScalarType = numpy.complex128` |
| PETSc integer width | PASS | 32 bit |
| Linux-only PATH | PASS | `.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`; no `/mnt/*`, Windows Python, or Windows MPI |
| dolfinx_mpc C++ linkage | PASS | project `libdolfinx_mpc.so.0.10`, `libdolfinx_complex.so.0.10`, and `libpetsc_complex.so.3.19`; no real-scalar variants |
| serial MUMPS | PASS | factor solver `mumps`, solution absolute error `0.0` |
| minimal complex FFCx JIT | PASS | 1-cell interval mass form, 2-by-2 matrix, 4 nonzeros |
| MPI2 import/hello | PASS | ranks 0 and 1 reported the same Python, MPI, scalar type, and library signature |
| MPI2 MUMPS microfixture | PASS | 32 rows, maximum absolute error `1.11e-16`, converged reason 4 |
| MPI2 SLEPc PEP microfixture | PASS | TOAR, one eigenpair, root error `1.78e-15`, relative error `2.61e-12` |

The common MPI2 ABI signature was
`6a45ec52adf23eaf672a981659b978266456c4162640b7d2c4002fa4cb633d34`.

## Reproducibility and isolation

- System packages are installed by the explicit `--system` phase; the normal-user
  `--user` phase creates an idempotent `.venv --system-site-packages` environment.
- `dolfinx_mpc` is built from a full fixed source commit into a project-local
  complex prefix with a recorded runtime path.
- Runtime temp, XDG, Matplotlib, log, and artifact directories are below
  `benchmarks/artifacts/task000`; the repository `.gitignore` excludes them.
- Activation verifies the exact execution branch and upstream before use.
- No PDE qualification or formal sample is claimed by this document. These are
  environment microfixtures only.

## Development-probe correction

The first minimal JIT expression used `(1+1j)*u*v*dx` and correctly failed UFL's
complex arity check because the test function was not conjugated. The probe was
corrected to `(1+1j)*inner(u, v)*dx`; compilation and assembly then passed. This
was a defect in the probe expression, not an ABI or solver failure.

## M3 Gate

`PASS`. The native complex environment is qualified for the next Task000 stages.
This does not authorize bulk data generation and does not relax the clean-source
requirement for formal samples.
