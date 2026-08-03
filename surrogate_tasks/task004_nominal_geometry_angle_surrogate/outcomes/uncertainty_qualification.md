# Nested and cross-fitted uncertainty qualification

For each outer fold, the model is fitted only to its outer-training rows.  A
three-fold inner split of those rows supplies a residual radius; that radius
sets a lower scale for the outer test uncertainty.  Calibration factors are
then computed from other outer folds, never from the fold being scored.  This
prevents using a test residual twice as both calibration and evaluation.

For the selected `L1_local_rbf_k24_s1e-08`, cross-fitted 95% coverage is:

| target | coverage |
|---|---:|
| `R_total` | 0.96875 |
| `T_total` | 0.95833 |
| `A_balance` | 0.94792 |

All three lie in the frozen `[0.90, 0.99]` uncertainty interval.  The
intervals are empirical training-residual intervals, not experimental or
continuum-physics uncertainty.  Their success does not waive the aggregate
accuracy Gate, and they do not authorize blind validation or FEM acquisition.

The local Matérn candidates also retain deterministic eight-start exact-GP
metadata for each query (neighbour indices, nearest distance, fitted kernel,
LML, selected start and warning count).  Convergence warnings are recorded in
the point diagnostics rather than discarded.
