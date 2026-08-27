# Structured-background reference validation

## 0. Classification

```text
classification = STRUCTURED_BACKGROUND_REFERENCE_ALGEBRA_PREPARED
solver_pass     = no
PDE_pass        = no
open_z_pass     = no
MPI_pass        = no
0p7nm_pass      = no
```

## 1. Files

```text
src/solvers/floquet_background_hcurl.py
src/test/test_319_task040_parallel_background_hcurl.py
src/studies/run_floquet_background_symbol_smoke.py
```

## 2. Isolated lightweight tests

在隔离的 Python/NumPy 环境运行：

```bash
python -m pytest -q src/test/test_319_task040_parallel_background_hcurl.py
```

结果：

```text
6 passed in 0.03 s
```

覆盖：

```text
Bloch-shifted FFT frequency order
transverse/longitudinal projectors
analytic Maxwell symbol inverse vs dense inverse
near-resonance singular guard
fully-periodic FFT operator/inverse round-trip
vector working-set payload estimate
```

## 3. Smoke runner

命令：

```bash
python -m src.studies.run_floquet_background_symbol_smoke
```

结果：

```text
status                 = pass
round_trip_error       = 6.173191687525133e-15
symbol_inverse_error   = 4.236644606489205e-16
shape                  = 6 x 5 x 4 x 3
4-vector payload lower estimate = 23040 B
```

## 4. Evidence boundary

这些结果只验证：

```text
continuous Fourier symbol sign
Bloch FFT ordering
analytic constant-background inverse
pure NumPy implementation consistency
```

没有验证：

```text
DOLFINx Nedelec action
MPC/Floquet owner mapping
open-z boundary
physical Fourier-DtN
x/y distributed FFT
z block solve
static condensation
real 5nm/0.7nm system
```

项目 qualified complex128环境必须重新运行 test319和smoke；随后仍需按
`structured_background_fft_hcurl.md` 的 S1/S2/S3 Gate执行。
