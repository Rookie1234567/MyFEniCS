# Case129 / Task004 M4H test summary

| check | result | evidence |
|---|---|---|
| immutable train112 arrays and file hashes | pass | Case129 checker |
| frozen five-fold coverage and fold hashes | pass | Case129 checker |
| S1/S2 threshold source excludes held-out fold | pass | `SELECTIVE_OOF.json`, Case129 checker |
| all 3 predictors × 2 risk rules present | pass | `SELECTIVE_MODEL_COMPARISON.json` |
| accepted-set metrics and composition recomputed | pass | Case129 checker |
| response-blind candidate4096 / blind24 screening | pass | acceptance-domain JSON, Case129 checker |
| structural support domain separated from acceptance | pass | structural-domain JSON, Case129 checker |
| selective qualification Gate | controlled negative | no pair passes all Gates |
| model lock / blind FEM / new FEM | not run | required because Gate failed |
| Task003 validation | not accessed | contract and checker guard |

Commands:

```text
source .venv-surrogate-cpu/bin/activate && python -m pytest -q tests/test_task004_m4h.py
source .venv-surrogate-cpu/bin/activate && python -m py_compile \
  src/surrogate/angle/m4h.py \
  benchmarks/cases/129_task004_selective_angle_surrogate/checker.py
source .venv-surrogate-cpu/bin/activate && python \
  benchmarks/cases/129_task004_selective_angle_surrogate/checker.py
```

All three commands pass. The checker status is `pass` for evidence integrity,
while the qualification status is deliberately `controlled_negative`.

