# Case120 — Task003 local CPU surrogate training

This case records the local WSL2 CPU training-only qualification attempt for
the immutable Case119 p5/Ny4 compact dataset.  It contains no FEM outputs and
does not unlock the 16 frozen-validation targets.

The training CV hard Gate was evaluated with deterministic degree-2/3 PCE and
Matérn-5/2 ARD exact-GP candidates.  The Gate failed, so no
`MODEL_SELECTION_LOCK.json`, validation read, active-learning FEM run, angle
DOE, or inversion was started.  See the linked Task003 outcomes for the exact
metrics and stop boundary.

