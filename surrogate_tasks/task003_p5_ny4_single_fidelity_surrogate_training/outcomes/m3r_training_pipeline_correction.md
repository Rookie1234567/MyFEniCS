# Task003 M3R training-pipeline correction

This controlled correction used exactly the existing 96 training rows and the
same five deterministic folds. It did not open the 16 frozen-validation rows,
rerun any of the 112 FEM samples, or start active-learning FEM.

Implemented corrections:

- aggregate targets are fitted as `zR=log((R+eps)/(A+eps))` and
  `zT=log((T+eps)/(A+eps))`, with `softmax(zR,zT,0)` reconstruction;
- each exact GP fold uses eight explicit deterministic ARD initializations;
  every fitted kernel, LML, optimizer status, warning, and boundary collision
  is persisted;
- candidates A `(h,w,kx,ky)`, B `(h,w,grazing,azimuth)`, and C
  `(h,w,kx,ky,kz)` are compared using training-only data;
- PCE baselines now use total-degree Legendre/Chebyshev orthogonal bases of
  degree 2/3, not monomial `PolynomialFeatures`;
- power targets use a channel-specific training-frozen `log(P+floor)` floor;
- `training_cv_oof.json` contains per-point truth, prediction, standard
  deviation, error, fold, mask status, and region labels.

The training-only selected candidate is `exact_gp:features=B`. Its aggregate
Gate still fails (R/T/A p95 absolute errors are approximately 0.0135, 0.0155,
and 0.0238), and all 21 primary power channels fail their hard Gate. The GP
aggregate 95% OOF interval coverage is 0.882, so uncertainty is recorded as
eligible for review-only acquisition planning; no 8-point FEM plan was
started or authorized here.

