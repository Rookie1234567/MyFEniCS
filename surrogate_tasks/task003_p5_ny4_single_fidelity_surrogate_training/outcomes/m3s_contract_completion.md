# Task003 M3S contract completion

M3S was completed using training targets only. Frozen-validation target values
were not opened, and the aggregate hard Gate was not changed.

## Frozen contracts

- `FEATURE_CONTRACT_v2.json` freezes feature **B**:
  `[height_scaled, width_scaled, grazing_scaled, azimuth_scaled]`.
- A and C remain comparison-only candidates; production transforms cannot
  silently fall back to A.
- `POWER_MASK_AUTHORITY.json` records separate top/air and bottom/complex-
  substrate runtime-mode authorities. Dispersion propagation and finite
  positive Poynting power are separate identities; inactive powers remain
  null. The 96-row training power mask matches exactly.
- P1 independent `log(P+floor)` is retained as diagnostic. P2 predicts each
  side total from the composition latent and reconstructs masked active-channel
  fractions, giving nonnegative fractions that sum to one per side and exact
  side ledgers (OOF max ledger error below `3e-16`).
- Channel outputs retain all 21 observable channels and are labelled
  primary/secondary/structural-null from training-only maxima and activity;
  structural null means analytic inactivity and is never a zero target.

## Finite model comparison

The only M3S candidates were G1 constant-mean Matérn-5/2 ARD exact GP and G2
degree-2 Legendre trend plus Matérn-5/2 ARD residual GP, each at jitter
`1e-10`, `1e-8`, and `1e-6`, on the same five training folds. Every fit stores
kernel, LML, boundary collisions, warnings, and optimizer state. The selected
candidate is selected from training CV; no model lock was created.

Training OOF uncertainty stores raw and multiplicatively calibrated coverage,
standardized residual quantiles, and region breakdowns. Calibration is an
acquisition-ranking aid only, not a qualified physical uncertainty statement.

## Gate result

The 96-row M3S run remained a hard-gate failure, so the deterministic
Round-1 plan was generated and checked before FEM. After eight new Ny4 p5
points, the 104-row training-only run also remains a hard-gate failure. The
workflow therefore stops for Review V2; no frozen-validation scoring, model
lock, Round 2/3, DOE, or inversion was started.
