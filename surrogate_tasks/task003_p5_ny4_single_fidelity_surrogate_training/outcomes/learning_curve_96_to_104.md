# Task003 learning curve: 96 to 104 training rows

| training rows | selected CV candidate | R NRMSE | T NRMSE | A NRMSE | aggregate hard Gate |
|---:|---|---:|---:|---:|---|
| 96 | G1 constant GP, feature B, jitter 1e-10 | 0.0369344 | 0.0130048 | 0.0450474 | failed |
| 104 | G2 degree-2 trend + GP residual, feature B, jitter 1e-10 | 0.0296161 | 0.0121282 | 0.0366639 | failed |

The eight new FEM points improved the selected training family and transmission
NRMSE modestly, but the reflection/absorption local error remains above the
unchanged aggregate hard Gate. This is a controlled stop, not a reason to
relax tolerances or unlock validation.
