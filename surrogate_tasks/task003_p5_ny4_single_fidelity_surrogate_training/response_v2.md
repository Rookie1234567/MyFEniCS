# Task003 response v2 — controlled M3R correction

## Scope respected

The correction used the same 96 training samples and the same five-fold
training-only split. Frozen validation stayed sealed, all 112 existing FEM
samples remained immutable, and no active-learning FEM was run.

## Corrections

Aggregate fitting now uses the true two-dimensional log-ratio latent
`zR=log((R+eps)/(A+eps))`, `zT=log((T+eps)/(A+eps))`, with
`softmax(zR,zT,0)` reconstruction. Candidates A/B/C were compared. The
selected candidate by training CV is `exact_gp:features=B`.

The exact GP uses eight deterministic optimization starts for every fold and
channel. Fitted kernels, LML, boundary collisions, optimizer status, and all
ConvergenceWarnings are retained. PCE baselines use true Legendre/Chebyshev
orthogonal total-degree bases. Power channels use a training-frozen
`log(P+floor)` transform. Per-point OOF predictions, standard deviations,
errors, folds, mask status, and cutoff/region labels are saved.

## Result and stop

The corrected selected model still fails the hard aggregate Gate and all 21
primary power-channel Gates. OOF aggregate 95% interval coverage is 0.882;
this is marked eligible for review-only acquisition planning, not as an FEM
authorization. `MODEL_SELECTION_LOCK.json` was not created and frozen
validation was not read. No 8-point plan was executed, no FEM was rerun, and
no angle DOE or inversion was started.

Evidence: `outcomes/training_cv.json`,
`outcomes/training_cv_oof.json`, and
`outcomes/m3r_training_pipeline_correction.md`.

