# M4E model-structure comparison (training-only)

M4E uses the immutable `task004_angle_nominal_p5_ny4_train96_v2` package only.
The purpose of a local model is to fit nearby angle responses without forcing
one correlation length to describe low grazing, cutoff transitions and high
azimuth simultaneously.  A topology expert additionally groups points by the
analytic power-carrying mask; an unseen mask is never silently treated as a
qualified order prediction.

All candidates use the same five deterministic folds, the same composition
latent (`zR`, `zT`) and the same aggregate error metrics.  Uncertainty is
estimated from nested inner-fold residual radii and cross-fitted outer-fold
calibration.  The score is the largest normalized aggregate error ratio; it is
used only for training-CV ranking.

| candidate | score | aggregate Gate | supported-window Gate | uncertainty Gate | composition |
|---|---:|---|---|---|---|
| L1 local RBF, k=24 | 4.4499 | fail | fail | pass | exact |
| L1 local RBF, k=32 | 4.4861 | fail | fail | pass | exact |
| L1 local RBF, k=48 | 4.4837 | fail | fail | pass | exact |
| L2 local Matérn-5/2 GP, k=24 | 4.8127 | fail | pass | pass | exact |
| L2 local Matérn-5/2 GP, k=32 | 4.8041 | fail | pass | pass | exact |
| L2 local Matérn-5/2 GP, k=48 | 5.4264 | fail | fail | pass | exact |
| L3 topology-aware expert, k=32 | 25.4794 | fail | fail | pass | exact |
| L4 Chebyshev degree-2 trend + local residual, k=32 | 4.5014 | fail | fail | pass | exact |

The training-CV ranking selects `L1_local_rbf_k24_s1e-08`.  It is not a
production lock: its aggregate R/T/A errors remain above the frozen Gate.
The best local Matérn variants improve supported-window behavior, but do not
remove the full OOF A/R/T error bottleneck.  L3 is retained as a negative
topology-aware result rather than being promoted by relaxing a Gate.

The immutable Case125 global reference score is 4.9507, so the selected local
candidate is better by the predeclared training-only comparison.  This fact
supports an eligibility proposal; it does not authorize FEM or validation.
