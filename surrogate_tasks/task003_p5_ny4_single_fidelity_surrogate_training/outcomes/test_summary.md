# Test summary

Run with:

```text
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PYTHONPATH=src .venv-surrogate-cpu/bin/python -m pytest -q tests/test_task003_surrogate.py
```

The test suite covers Case119 hashes/array identities, train-only loading,
analytic propagation masks, domain fail-closed behaviour, deterministic fold
identity, CPU PCE/GP repeatability, and aggregate composition conservation.
The independent Case120 checker also verifies the M0 smoke and sealed-
validation assertions. Final run: **7 passed** (four expected sklearn
lower-bound convergence warnings; no test failure).
