# WSL workstation environment qualification

## Final decision

| Scope | Status | Evidence |
|---|---|---|
| WSL2 Ubuntu identity | PASS | Ubuntu 24.04.4 LTS; WSL2 kernel `6.18.33.2-microsoft-standard-WSL2` |
| Linux filesystem | PASS | Repository at `/home/Projects/MyFEniCS` on WSL ext4 |
| GitHub access | PASS | SSH authentication and fetch from `Rookie1234567/MyFEniCS` |
| Repository baseline | PASS | `master` and `origin/master` at `4c1b78bdac955608d8a4043b3d0f678ce8bf2343` |
| Complex PETSc | PASS | `PETSc.ScalarType == numpy.complex128` |
| MPI1 / MPI2 / MPI4 | PASS | All ranks used the same Linux Python and complex package paths |
| SLEPc / MUMPS / DOLFINx | PASS | Lightweight complex capability tests completed |
| MyFEniCS code execution | PASS | 19 lightweight tests and one Stage1 3D PDE smoke passed |
| Task034 | NOT_RUN | Environment qualification only; no Task034 branch or computation |
| Heavy benchmarks | NOT_RUN | Explicitly outside bootstrap scope |

The workstation is qualified for WSL-native MyFEniCS code execution through
the project-local complex environment described below. The environment itself
is intentionally Git-ignored and is not part of this report-only change.

## Execution identity

- Qualification date: `2026-07-18`
- Linux user: `fenics`
- Hostname: `DESKTOP-O598DT1`
- Distribution: Ubuntu 24.04.4 LTS (Noble Numbat)
- Kernel: `Linux 6.18.33.2-microsoft-standard-WSL2`
- Bash: `/usr/bin/bash`, GNU bash 5.2.21
- Repository: `/home/Projects/MyFEniCS`
- Filesystem: ext4 mounted from `/dev/sdd`
- Git remote: `git@github.com:Rookie1234567/MyFEniCS.git`

The shell prompt `fenics@DESKTOP-O598DT1` means Linux `user@hostname`; it is
not a filesystem path.

## Qualified environment

Activate from a WSL Bash shell:

```bash
cd /home/Projects/MyFEniCS
source .venv/bin/activate-myfenics
```

The qualified interpreter is:

```text
/home/Projects/MyFEniCS/.venv/bin/python
```

| Component | Status | Version / identity |
|---|---|---|
| Python | PASS | 3.12.3 |
| pip | PASS | 24.0 |
| NumPy | PASS | 1.26.4 |
| SciPy | PASS | 1.11.4 |
| mpi4py | PASS | 3.1.5 |
| PETSc / petsc4py | PASS | 3.19.6, complex |
| SLEPc / slepc4py | PASS | 3.19.2, complex |
| DOLFINx | PASS | 0.10.0.post2, complex |
| Basix | PASS | 0.10.0 |
| UFL | PASS | 2025.2.1 |
| Gmsh | PASS | 4.12.1 |
| Open MPI | PASS | OpenRTE 4.1.6 |
| MUMPS | PASS | PETSc factor solver selection and complex solve |

Complex Python packages were loaded from:

- petsc4py:
  `/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex/lib/python3/dist-packages`
- slepc4py:
  `/usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex/lib/python3/dist-packages`
- DOLFINx:
  `/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex/lib/python3/dist-packages`

The activation entrypoint replaces the mixed WSL login PATH with:

```text
/home/Projects/MyFEniCS/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

No `/mnt/c`, `/mnt/d`, WindowsApps, Windows Python, Windows Git, or Windows MPI
path remains in the activated project shell.

## PETSc scalar gate

| Field | Result |
|---|---|
| `PETSc.ScalarType` | `<class 'numpy.complex128'>` |
| Scalar dtype | `complex128` |
| `PETSc.IntType` | `<class 'numpy.int32'>` |
| Integer dtype | `int32` |
| Gate | PASS |

Reproduction:

```bash
python -c "from petsc4py import PETSc; print(PETSc.ScalarType)"
```

Expected:

```text
<class 'numpy.complex128'>
```

## MPI qualification

| Run | Status | Evidence |
|---|---|---|
| MPI1 | PASS | rank 0 of 1 |
| MPI2 | PASS | ranks 0–1 of 2 |
| MPI4 | PASS | ranks 0–3 of 4 |

Every rank used:

- Python: `/home/Projects/MyFEniCS/.venv/bin/python`
- mpi4py: `/usr/lib/python3/dist-packages/mpi4py/__init__.py`
- petsc4py: complex PETSc 3.19 path
- DOLFINx: complex PETSc 3.19 path
- PETSc scalar dtype: `complex128`

No MPI ABI mismatch or Windows path was observed.

## Lightweight native capability tests

| Capability | Status | Evidence |
|---|---|---|
| SLEPc PEP lifecycle | PASS | `SLEPc.PEP` created and destroyed |
| Complex MUMPS solve | PASS | Complex 1x1 LU solve; absolute error `2.29e-16` |
| DOLFINx serial | PASS | Tiny mesh/function space stored `1+2j` |
| DOLFINx MPI2 | PASS | 8 global cells, 9 owned DoFs, complex storage |
| Static compilation | PASS | `src` and `benchmarks` compiled |

These tests were in-memory or used small WSL temporary directories. They did
not write project result artifacts.

## MyFEniCS code validation

The following reviewed lightweight test files were run:

- `src/test/test_00_units_and_conventions.py`
- `src/test/test_01_plane_wave_tools.py`
- `src/test/test_02_pml_tensor.py`
- `src/test/test_03_fresnel_coefficients.py`
- `src/test/test_24_repository_work_principles.py`

Result:

```text
19 passed in 1.45s
```

The opt-in coarse Stage1 3D PDE smoke was then run:

```text
src/test/test_04_airbox_dirichlet_pde.py
1 passed in 5.87s
```

This test uses `mesh_target_size=300` and exercises a real project
mesh/assembly/solve path. Its small temporary output was removed after the
test.

The README 2D and 3D runner entrypoints also parsed `--help` successfully:

```bash
python -m src.runners.run_cases --help
python -m src.runners.run_3d_cases --help
```

## Remediation performed

Initial inspection found that Ubuntu had both real and complex PETSc/SLEPc
variants installed, while system alternatives selected real PETSc. It also
found no unversioned `python` command and a WSL login PATH containing Windows
entries.

Remediation:

1. Installed Ubuntu `python3.12-venv`, `python3-pip-whl`, and
   `python3-setuptools-whl`.
2. No existing Ubuntu package was upgraded.
3. Created Git-ignored `/home/Projects/MyFEniCS/.venv`.
4. Added an ignored `activate-myfenics` entrypoint providing `python`, `pip`,
   complex PETSc/SLEPc/DOLFINx, and a Linux-only PATH.
5. Kept system-wide PETSc/SLEPc alternatives unchanged to avoid affecting
   other local projects.
6. Re-ran all bootstrap gates and the reviewed project tests successfully.

No tracked project source or existing documentation was modified during
environment remediation.

## Remaining warnings

1. Bare `/usr/bin/python3` outside the project environment still follows the
   system real-PETSc alternatives and is not qualified for MyFEniCS.
2. The WSL login PATH contains Windows entries before project activation.
3. A passphrase-protected GitHub key requires a live `ssh-agent` for future
   fetch, pull, and push operations.
4. Heavy simulations still require the resource gates defined by their task
   documents; environment qualification is not authorization to run them.

## Explicitly not run

- Task034 research work
- Task034 execution branch
- Docker
- Heavy/full3D reference benchmarks
- p3/h5, p3/h3, p4/h5, or other large solves
- Any Git push during the qualification phase

## Proposed `AGENTS.md` WSL rules

This proposal was not written to an `AGENTS.md` file:

```markdown
# MyFEniCS WSL execution rules

- Run all project commands in WSL2 Ubuntu.
- Keep the repository on the WSL Linux filesystem under `/home/...`.
- Never execute project work from `/mnt/c`, `/mnt/d`, or another
  Windows-mounted directory.
- Do not use Windows Python, Git, MPI, PowerShell, CMD, or WindowsApps
  executables for project operations.
- Activate the qualified MyFEniCS complex environment before project work.
- Python, mpi4py/Open MPI, PETSc/petsc4py, SLEPc/slepc4py, DOLFINx, and native
  solver libraries must come from one coherent WSL environment.
- Require `numpy.dtype(PETSc.ScalarType) == numpy.dtype(numpy.complex128)`.
- At the start of every task, verify WSL identity, repository path,
  filesystem type, executable paths, module paths, and PETSc scalar type.
- Fail closed on any identity, path, scalar-type, MPI ABI, residual, or
  resource-gate failure.
- Use Docker only when the current task explicitly requires it.
- Do not run heavy benchmarks or large solves without the task's explicit
  CPU, RAM, storage, runtime, and artifact gates.
- Label every conclusion PASS, FAIL, NOT_RUN, or WARNING; never report an
  unexecuted check as passed.
```

## Integrity statement

At the end of qualification:

- `master == origin/master == 4c1b78bdac955608d8a4043b3d0f678ce8bf2343`
- tracked worktree was clean
- no project source file was changed
- no Task034 branch was created
- no project commit was created
- no push was performed
- no heavy computation was run

This report is being published separately for review.
