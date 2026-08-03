# Case127 / Task004 M4E2–M4F test summary

| check | result | evidence |
|---|---|---|
| V3 geometry-support and nearest-distance checker | pass | `case127_check.json`（M4E2 pre-FEM immutable record） |
| M4E2 acquisition Spearman/recall audit | pass | `M4E2_ACQUISITION_QUALITY.json` |
| exact 16-point plan, tuple isolation and spacing | pass | `ACTIVE_LEARNING_ROUND1_PLAN_V2.json` + independent checker |
| fixed forward identity / route / ICNTL(14) | pass | `case127_post_fem_check.json` |
| 16-point campaign | 16/16 `measured_pass` | ignored campaign manifest and compact FEM records |
| compact record gates, residual/ledger/watchdog | pass | `case127_post_fem_check.json` |
| train112 exact 96+16 package | pass | `case127_train112_check.json` |
| paired 96→112 curve | pass (computed) | `paired_learning_curve_96_to_112.{json,md}` |
| standard 112 training-only CV | completed; qualification fail | `train112_cv/training_cv.json` |
| validation response access | false | train112 manifest/checker |
| model lock / blind FEM | not created / not run | fail-closed policy |

The two historical preflight retries recorded in the ignored campaign manifest
occurred before a solver process produced a PDE record. The final resume produced
the 16 measured passes; the original manifest history is retained rather than
rewritten.

Targeted checks run after the final artifacts were generated:

```text
TMPDIR=/tmp PYTHONPATH=. .venv-surrogate-cpu/bin/python benchmarks/cases/127_task004_active_learning_round1/post_fem_checker.py
TMPDIR=/tmp PYTHONPATH=. .venv-surrogate-cpu/bin/python benchmarks/cases/127_task004_active_learning_round1/train112_checker.py
TMPDIR=/tmp PYTHONPATH=. .venv-surrogate-cpu/bin/python -m py_compile \
  src/surrogate/angle/round1.py src/surrogate/angle/m4e2.py \
  benchmarks/cases/127_task004_active_learning_round1/checker.py \
  benchmarks/cases/127_task004_active_learning_round1/post_fem_checker.py \
  benchmarks/cases/127_task004_active_learning_round1/train112_checker.py
```

The existing pure-Python M4E regression suite remains the relevant implementation
test; no full repository test or new FEM was triggered by documentation-only
changes.
