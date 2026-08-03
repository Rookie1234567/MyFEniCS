# Case128 / Task004 M4G test summary

| check | result | evidence |
|---|---|---|
| train112 immutable hash and array identity | pass | Case128 checker |
| frozen 5-fold reference folds, every index once | pass | `TRAIN112_LOCAL_REFERENCE_FOLDS.json` |
| four finite local candidates on complete 112 OOF | completed; all Aggregate A fail | `TRAIN112_LOCAL_MODEL_COMPARISON.json` |
| latent median ensemble | completed; Aggregate A fail | comparison JSON |
| cross-fitted non-negative stack | completed; Aggregate A fail | comparison JSON / fold inner-OOF provenance |
| OOF errors/composition recomputed independently | pass | Case128 checker |
| post-active outlier audit | pass | `POST_ACTIVE_OUTLIER_AUDIT.{json,md}` |
| paired-report final-candidate semantics | pass | paired JSON/MD + Case128 checker |
| safe-domain secondary diagnostic | pass; 4074/4096 structural support | `ANGLE_AGGREGATE_SAFE_DOMAIN_CANDIDATE.json` |
| Aggregate model lock | absent by Gate | v4 contract |
| Order Level B | not qualified | v4 contract |
| new FEM / second active learning / blind responses | not run/accessed | policy boundary |

Targeted checks:

```text
TMPDIR=/tmp PYTHONPATH=. .venv-surrogate-cpu/bin/python benchmarks/cases/128_task004_post_active_local_qualification/checker.py
TMPDIR=/tmp PYTHONPATH=. .venv-surrogate-cpu/bin/python -m pytest -q tests/test_task004_m4e.py
TMPDIR=/tmp PYTHONPATH=. .venv-surrogate-cpu/bin/python -m py_compile \
  src/surrogate/angle/m4g.py src/surrogate/angle/round1.py \
  benchmarks/cases/128_task004_post_active_local_qualification/checker.py
```

The GP optimizer warnings and fitted-kernel provenance remain in the OOF
diagnostics/log; no warning was converted into a silent pass.
