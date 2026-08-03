# Case126 test summary

| check | result |
|---|---|
| Case125 train96 package hash rebuild | pass |
| arrays, dtypes and 96-row identity | pass |
| fixed geometry and angle-domain contract | pass |
| aggregate/order contracts independent | pass |
| finite M4E candidate set | pass |
| supported windows v2 and old stress hash | pass |
| active-learning is eligibility-only | pass |
| model lock/blind FEM absence | pass |
| Task003 validation sealed | pass |
| new FEM run | not run by policy |

The independent result is `benchmarks/cases/126_task004_local_topology_angle_surrogate/records/case126_check.json`.
The checker reads the package and JSON artifacts directly and does not import
the M4E fitter or execute FEM.

The implementation module compiles with:

```text
TMPDIR=/tmp .venv-surrogate-cpu/bin/python -m py_compile src/surrogate/angle/m4e.py
```

All exact-GP convergence warnings observed during the finite L2 comparison
were retained in `/tmp/task004_m4e.log` during execution and in the committed
per-point diagnostics/summary metadata; they were not silently converted to
success.
