# Training-only M3R CV

The five folds are deterministic, hash-bound, maximin-ordered folds over the
same 96 training rows (`seed=20260731`). The corrected comparison evaluates
feature candidates A/B/C, the true aggregate log-ratio latent, Legendre and
Chebyshev degree-2/3 bases, and a Matérn-5/2 ARD exact GP with eight explicit
optimization starts per fold.

Training CV selected `exact_gp:features=B` by the recorded CV score, not by a
hard-coded family choice. Its hard Gate failed for all three aggregate
quantities and for all 21 training-defined primary order-power channels under
the required thresholds. Per-fold kernel/LML/warning/boundary records are in
`outcomes/training_cv.json`; point-level OOF records and region breakdowns are
in `outcomes/training_cv_oof.json`. No tolerance, Gate, or frozen split was
changed. Sparse exact-corner and cutoff anchors are retained and reported.

Because the hard Gate failed, active-learning FEM remains at 0/24 points. The
OOF interval coverage is 0.882 and is marked eligible for review-only
acquisition planning; no candidate plan was executed or submitted as an FEM
run.
