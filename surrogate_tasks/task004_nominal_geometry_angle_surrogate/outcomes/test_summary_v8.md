# Case130 / Required M4I test summary

| check | result | evidence |
|---|---|---|
| immutable train112 arrays, manifest and file hashes | pass | Case130 checker |
| frozen five-fold coverage and fold hashes | pass | Case130 checker |
| predictor-specific source thresholds | pass | `SELECTIVE_THRESHOLD_CORRECTION.json` |
| no fallback threshold can pass | pass | M4I comparison + Case130 checker |
| highest-acceptance passing quantile | pass | threshold candidate grids + Case130 checker |
| unified OOF final normalization/threshold | pass | threshold correction JSON |
| held-out response excluded from acceptance/calibration | pass | M4I OOF + Case130 checker |
| accepted-source targetwise conformal interval | pass | `SELECTIVE_CONDITIONAL_CONFORMAL.json` |
| coverage lower bound and interval-sharpness | pass | comparison/conformal JSON |
| response-blind candidate4096 / blind24 hashes | pass | `SELECTIVE_ACCEPTANCE_DOMAIN_V2.json` + checker |
| lock absence and blind-FEM absence on negative | pass | Case130 checker |
| M4I qualification | controlled negative | both Q1/Q2 fail point accuracy |

Commands:

```text
source .venv-surrogate-cpu/bin/activate && TMPDIR=/tmp python -m pytest -q tests/test_task004_m4i.py
source .venv-surrogate-cpu/bin/activate && python -m py_compile \
  src/surrogate/angle/m4i.py \
  benchmarks/cases/130_task004_selective_interval_correction/checker.py
source .venv-surrogate-cpu/bin/activate && TMPDIR=/tmp python \
  benchmarks/cases/130_task004_selective_interval_correction/checker.py
```

Results: `3 passed`; `py_compile` passed; Case130 returned `status=pass` and
`qualification_status=controlled_negative`. No FEM process was launched.

