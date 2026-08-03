# Active-learning eligibility (plan only)

`ACTIVE_LEARNING_ELIGIBILITY.json` records eligibility, not execution.  The
selected local candidate improves the immutable Case125 global reference
score (4.4499 versus 4.9507), has cross-fitted uncertainty, and localizes a
high-error region.  The A-error improvement check is false, so the eligibility
is conditional on the uncertainty and localized-error clauses, as required by
Review V3.

```text
eligible_for_one_round_16_fem = true (conditional proposal only)
budget                       = 16
fem_started                  = false
validation_target_accessed   = false
plan_status                  = eligibility_only_no_fem
```

No 16-point FEM design was executed or converted into a dataset.  No second
active-learning round, blind validation, Task003 validation, Fisher ranking,
geometry sensitivity or inversion was started.  If a later review authorizes
M4F, its response-blind plan must respect the seven rare topology signatures,
localized error hotspots, supported holes and the fixed forward SHA.
