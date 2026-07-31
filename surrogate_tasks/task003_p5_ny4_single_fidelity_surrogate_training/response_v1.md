# Task003 response v1

## Result

M0-L through training-only M3 were executed on the current WSL2 host with
single-thread CPU fits. Case119 compact data passed independent hash, shape,
dtype, split, NaN/mask, and sample-identity checks. The exact-GP smoke ran
twice with identical predictions and zero swap growth.

## Gate and stop

The required five-fold training CV hard Gate failed for the aggregate and
primary power channels for both the low-order baselines and the selected
Matérn-5/2 ARD exact-GP candidate. The failure is preserved; no tolerance,
channel, or validation rule was altered. Per Task003, model locking and the
one-time frozen validation cannot begin. Active-learning FEM remains at 0/24
points and requires the next controlled decision.

No Case119 FEM was rerun. No CUDA, P-incident surrogate, angle DOE, or
inversion was started. The branch is ready for review at this boundary.

