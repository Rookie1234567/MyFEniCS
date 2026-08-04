# Task005 Response V2：M5R derived-only final-lock correction

## 结论

M5R 已完成，且严格使用现有 Task005 数据；本轮没有运行任何 FEM。原始
`task005_discrete_angle_hw_sensitivity_p5_ny4_v1` package、Task004 train112、
Task005 V1 lock 和所有 93 个 FEM 证据均保持不变。Case134 独立 checker
通过，V2 lock 已建立为 `review_ready`，现停止等待 Review V2。

## 不可变身份

```text
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
raw_dataset_id = task005_discrete_angle_hw_sensitivity_p5_ny4_v1
derived_dataset_id = task005_discrete_angle_hw_sensitivity_p5_ny4_derived_contract_v1
model = Full3D static uniform N1curl p5/h10/Ny4, mesh (6,4,14)
MUMPS ICNTL(14) = 40; MPI2; thread1
observable = task002.fixed-n0-orders.v3
new FEM in M5R = 0
```

Raw manifest SHA remains `e3a1b92b5311ec1fb6f5c5fb52d64f2a99f0b22122e57358305e36914229ca20`.
The historical V1 lock SHA remains
`4509404694c9182a9eeaa1da6efc6f3f9e2f5de63e4eaa025d375936861f4ad7`.

## M2 ranking-stability audit

The audit independently reads the existing 1–4 angle Fisher tables. The robust
reference remains the M0/M1 N1/N2 worst-case ranking. M2/N1 and M2/N2 are shown
separately because the extended contract includes weak channels.

| count | robust best | M2/N1 best | M2/N2 best | M2 worst-case best |
|---:|---|---|---|---|
| 1 | A05 | A05 | A05 | A05 |
| 2 | A05+A07 | A05+A09 | A05+A07 | A05+A07 |
| 3 | A05+A07+A09 | A05+A09+A11 | A05+A07+A09 | A05+A07+A09 |
| 4 | A05+A06+A07+A09 | A05+A07+A08+A09 | A05+A06+A07+A09 | A05+A06+A07+A09 |

The M2-only diagnostic contains 28 weak-channel observations across 13 angles.
Their nominal powers span `1.27707e-5`–`8.18441e-4`; the corresponding sigma
ranges are `1.00000e-4`–`1.00334e-4` under N1 and `5.00000e-4`–`5.00268e-4`
under N2. These channels are near the absolute floor and remain diagnostic.

On the common full-rank sets, robust-vs-M2 worst-case top-10 overlap is 10/10
for sizes 1–4; top-20 overlap is 13/13, 20/20, 20/20 and 20/20. Spearman
correlations are respectively 1.000000, 0.999681, 0.999902 and 0.999940.
The isolated N1 changes are retained as a warning, but cannot override the
robust M0/M1 lock.

## Illumination-count tradeoff

The primary score is robust M0/M1/N1/N2 worst-case minimum eigenvalue. The
adjacent-count ratios are:

| comparison | fewer / more score | ratio | 5% tie? |
|---|---:|---:|---|
| 1 vs 2 | 12.882983 / 23.781704 | 0.541718 | no |
| 2 vs 3 | 23.781704 / 34.768648 | 0.683999 | no |
| 3 vs 4 | 34.768648 / 45.149335 | 0.770081 | no |

Therefore the information-global-best set is the four-angle set
`A05+A06+A07+A09`. The operational three-angle set remains
`A05+A07+A09`: it is the best robust triple and the only set with the prescribed
G1–G3 nonlinear recovery evidence. It is a validated cost-information
compromise, not the global information optimum and not a formal inversion design.

## Derived sensitivity supplement

The companion package is at:

```text
benchmarks/artifacts/cases/132_task005_sensitivity_dataset/derived_contract_v1/
```

It contains `perturbed_inputs.npy`, M0 `Dh/Dw` and noise arrays, ragged-safe M1
and M2 derivative/noise NPZ files with offsets, channel contracts/tiers and
source record IDs. The manifest binds every file to the raw v1 file hashes and
states `source_raw_package_modified=false`, `generated_without_fem=true` and
`new_fem_count=0`.

## Task001 baseline interpretation

The historical A14+A15 pair `(10°,0°)+(10°,90°)` is retained. Under M0 it is
full rank but strongly correlated; under M1 the robust threshold leaves one
active channel per angle and gives a worst-case N2 condition number of about
`5.65e5`. M2 weak channels improve that diagnostic number to about `129.6`, but
the pair remains far below the new robust candidates.

This difference is explained by changed observable contracts, explicit
non-redundant aggregate/order treatment, robust-channel thresholding and the
absolute N1/N2 noise floors. It is not a claim that Task001 was false or that
the historical pair was renamed.

The physical/scaled Fisher units and every tuple/hash input schema are defined
in `FISHER_PARAMETERIZATION_AND_HASH_SCHEMA.md`; in particular,
`covariance_scaled` is covariance in `theta=(dh/5,dw/1)` units, while the
reported `sigma_h_nm` and `sigma_w_nm` are physical nm quantities.

## Final lock and checker

`DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json` has status `review_ready` and
records the raw package hashes, derived supplement hash, M2 audit, count
tradeoff, baseline addendum, Fisher semantics, M4 recovery evidence and the
explicit scope boundary:

```text
formal_inversion = false
Task006_authorized = false
Task004 blind24 = false
new FEM = 0
```

Case134 independently passed all checks: raw v1 package unchanged, V1 lock
preserved, M2 rankings and overlaps rebuilt, 5% rule rebuilt, supplement arrays
rebuilt, V2 lock identities verified, and no FEM/validation/inversion accessed.

## Tests and stop state

See `outcomes/test_summary_v2.md`. Task004 remains
`closed_controlled_negative`; no Task006, formal surrogate or Bayesian inversion
was started. The current branch is pushed only after final review of the clean
working tree, then execution stops for ChatGPT review.
