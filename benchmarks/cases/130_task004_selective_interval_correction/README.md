# Case130：M4I selective interval correction

This is a training-only, response-blind checker for Required M4I.  It
recomputes predictor-specific source thresholds, rejects fallback thresholds,
selects the highest-acceptance passing quantile, rebuilds accepted-source
finite-sample conformal radii and checks coverage/sharpness.  It also verifies
candidate-pool/blind-design preacceptance hashes and that no model lock or
blind FEM exists when M4I is a controlled negative.

The checker never imports the M4I fitter and never reads Task003 validation.

