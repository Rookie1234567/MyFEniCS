# Fisher parameterization and hash schema

## Fisher units

The raw finite differences are physical derivatives:

$$
J_{h,w} = [\partial y/\partial h,\partial y/\partial w],
\qquad [J_{h,w}] = \mathrm{nm}^{-1}.
$$

Task005 scales the parameters as `theta_h=(h-120 nm)/5 nm` and
`theta_w=(w-17 nm)/1 nm`. Therefore the scaled Jacobian used by the Fisher
calculation is `J_theta = J_hw @ diag(5, 1)`, and `F = J_theta.T @ Sigma^-1 @
J_theta`. The stored v1 `covariance_scaled` field is covariance in theta units.

For a full-rank Fisher matrix:

$$
\operatorname{Cov}_{physical} = \operatorname{diag}(5,1)
\operatorname{Cov}_\theta \operatorname{diag}(5,1).
$$

Thus `sigma_theta_h`, `sigma_theta_w` are dimensionless parameter-scale
uncertainties, while `sigma_h_nm` and `sigma_w_nm` are physical nm quantities.
The reported CRLB is only a local DOE metric under provisional diagonal N1/N2;
it is not calibrated metrology uncertainty and is not a Bayesian posterior.

## Hash input schemas

All canonical JSON hashes use UTF-8 `json.dumps(sort_keys=True,
separators=(',',':'), ensure_ascii=False, allow_nan=False)` followed by SHA-256.
Byte/file hashes are SHA-256 over the exact file bytes.

| name | exact input and ordering | meaning |
|---|---|---|
| `train112.training_tuple_sha256` | immutable Task004 tuple package | upstream nominal identity |
| `DISCRETE_ANGLE_DESIGN.point_tuple_sha256` | `[[120.0,17.0,g,a], ...]` in A00–A15 order | full Task005 point tuples |
| `M2 angle_tuple_sha256` | `[[g,a], ...]` in A00–A15 order | raw v1 angle array identity |
| `design_sha256` | bytes of `DISCRETE_ANGLE_DESIGN.json` | design file identity |
| `production_step_lock_sha256` | bytes of `PRODUCTION_STEP_LOCK.json` | selected half-step identity |
| `recommended_triple_hash` | canonical list of ordered IDs `['A05','A07','A09']` in v1 code | historical candidate-ID hash; not a point hash |
| `source_raw_manifest_sha256` | bytes of raw `dataset_manifest.json` | immutable raw package manifest identity |

In particular, the full point-tuple hash and the raw angle-array hash are
intentionally different: the former includes fixed `(h,w)`, while the latter
contains only `(grazing, azimuth)`. No hash is inferred from a field name.

## Frozen identities

- forward solver: `fdf961545f217d620e22800f2704ae9913a6d270`
- raw dataset: `task005_discrete_angle_hw_sensitivity_p5_ny4_v1`
- observable: `task002.fixed-n0-orders.v3`
- source raw `angle_tuple_sha256`: `072ec3da9b7f537dce5d410208eb999773c9fa2c331937711f59a78f412aaea9`
- source raw `design_sha256`: `f1bbe0dbd3a57a4f9a600a0cc6745cdea70eaa33aba5203a22b4a252bb62962d`
- source design schema: `task005.discrete-angle-design.v1`
