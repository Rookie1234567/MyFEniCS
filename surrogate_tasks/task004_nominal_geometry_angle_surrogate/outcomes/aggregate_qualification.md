# Level A aggregate qualification

Level A predicts `(R_total, T_total, A_balance)` from `(grazing_deg,
azimuth_deg)` at fixed `h=120 nm`, `w=17 nm`.  The latent is

```text
zR = log((R + eps)/(A + eps))
zT = log((T + eps)/(A + eps))
```

and a three-way softmax reconstructs non-negative `R`, `T`, `A` with an exact
sum of one.  This avoids fitting three unconstrained quantities that could
violate the power-composition identity.

The CV-selected candidate is `L1_local_rbf_k24_s1e-08`.  Its five-fold OOF
metrics are:

| target | NRMSE | p95 absolute error | maximum absolute error |
|---|---:|---:|---:|
| `R_total` | 0.01877 | 0.02379 | 0.06020 |
| `T_total` | 0.02995 | 0.01521 | 0.11859 |
| `A_balance` | 0.04219 | 0.03665 | 0.13350 |

The required limits are NRMSE≤0.01, p95≤0.01 and max≤0.03.  Therefore the
aggregate result is `not_qualified_but_viable`, not a model lock.  The
composition identity is exact and the cross-fitted uncertainty Gate passes,
but accuracy does not.

The new supported local windows are a hard interpolation diagnostic.  For the
selected model, the high-azimuth window remains the main warning (`A_balance`
p95 0.08148); cutoff-near and low-grazing windows are lower but are still
reported.  The original Case125 whole-region low-grazing/high-azimuth/cutoff
holdouts are preserved unchanged as advisory extrapolation stress evidence,
not relabeled as supported interpolation.

No blind target was opened, no validation response was used, and no
`ANGLE_AGGREGATE_MODEL_SELECTION_LOCK.json` was created.
