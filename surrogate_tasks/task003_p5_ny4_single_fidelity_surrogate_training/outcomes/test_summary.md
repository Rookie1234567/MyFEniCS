# Test summary

Run with:

```text
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PYTHONPATH=src .venv-surrogate-cpu/bin/python -m pytest -q tests/test_task003_surrogate.py
```

The test suite covers Case119 hashes/array identities, train-only loading,
analytic propagation masks, domain fail-closed behaviour, deterministic fold
identity, CPU PCE/GP repeatability, and aggregate composition conservation.
The independent Case120 checker covers the original M0/M3S evidence; the
Case122 checker additionally verifies the 112+16 exact-design package, both
eight-point append sets, fixed validation tuples, Round-2 campaign statuses,
and all rebuilt hashes without loading target arrays. Final implementation
tests remain **9 passed**; expected sklearn convergence warnings are surfaced
and recorded, with no test failure.
