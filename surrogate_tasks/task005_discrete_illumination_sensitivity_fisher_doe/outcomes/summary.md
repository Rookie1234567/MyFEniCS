# Task005 outcomes summary

## Scope and identity

Task005 used fixed 13.5 nm S illumination, nominal `(h,w)=(120,17) nm`, and
Full3D static uniform N1curl p5/h10/Ny4 with mesh `(6,4,14)`, MUMPS
ICNTL(14)=40, MPI2/thread1.  Every new FEM record is bound to forward SHA
`fdf961545f217d620e22800f2704ae9913a6d270`; the implementation commit is
`d24395b377259da129a81384f88d8a4ad74602d2`.

Task004 remains `closed_controlled_negative`.  Its blind24 responses were not
run or accessed.  The Task004 train112 nominal package remains immutable and
was reused at the 16 frozen Task005 angles.

## Gates and measurements

| stage | result | evidence |
|---|---|---|
| M0 design/reuse | pass, 16/16 exact tuples | `DISCRETE_ANGLE_DESIGN.json`, `NOMINAL_REUSE_REPORT.json`, Case131 |
| M1 audit | pass, 40/40 new records | `FINITE_DIFFERENCE_STEP_AUDIT.json`, `PRODUCTION_STEP_LOCK.json` |
| M2 dataset | pass, 44 new + 20 exact M1 reuse | `M2_DATASET_MANIFEST.json`, Case132 |
| Fisher M0/M1/M2 | complete | `FISHER_SINGLE_ANGLE.json`, `FISHER_COMBINATION_RANKING.json` |
| M4 recovery | pass, 9/9 new records and G1–G3 Gate pass | `OFF_CENTRE_RECOVERY.json` |
| final DOE lock | frozen, review pending | `DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json` |

The production derivative steps are `delta_h=1.25 nm` and `delta_w=0.25 nm`.
M0 uses only `[R_total,T_total]`; M1/M2 use non-duplicated fixed-order total
power channels; M3 polarization-resolved values remain diagnostic only.

## Recommended illumination

The robust Fisher recommendation is A05 `(2°,0°)`, A07 `(2°,90°)`, and A09
`(4°,60°)`.  Relative to the Task001 A14+A15 baseline, this set has a much
better local condition number and minimum eigenvalue under both provisional
noise scenarios.  The ranking is not an inversion and does not qualify an
arbitrary-angle surrogate.

## Off-centre recovery

Using the frozen nominal Jacobian and M1/N1 order-total weighting, the selected
triple recovered the three prescribed test geometries with maximum absolute
errors below `0.0361 nm` in height and `0.00121 nm` in width.  These are local
nonlinear checks, not a general structural inversion.

## Explicit non-actions

No P-polarization data, Task004 blind validation, continuous-angle surrogate,
Bayesian inversion, or experimental uncertainty claim was introduced.  Total
new FEM count was 93, below the hard budget of 96.

## M5R derived-only closeout

| item | result | identity / evidence |
|---|---|---|
| M2 ranking stability | pass | `M2_RANK_STABILITY_AUDIT.json`, Case134 |
| M2 weak-channel diagnostic | 28 observations on 13 angles; nominal power `1.27707e-5`–`8.18441e-4` | M2 raw derivatives, N1/N2 absolute floors |
| robust-vs-M2 ranking | worst-case M2 keeps selected single/pair/triple/quad at rank 1; top-10 overlap 10/10 for every size | `M2_RANK_STABILITY_AUDIT.md` |
| illumination count | 1→2 ratio 0.541718, 2→3 ratio 0.683999, 3→4 ratio 0.770081; no adjacent pair is within 5% | `ILLUMINATION_COUNT_TRADEOFF.json` |
| information-global-best | A05+A06+A07+A09 (quad) | local robust Fisher score |
| operational compromise | A05+A07+A09 (triple) | M4 G1–G3 nonlinear recovery evidence |
| derived supplement | pass, source raw package unchanged | `derived_contract_v1/DERIVED_SUPPLEMENT_MANIFEST.json` |
| Task001 interpretation | pass, A14+A15 retained as historical baseline | `TASK001_BASELINE_INTERPRETATION_ADDENDUM.md` |
| V2 lock | `review_ready` | `DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json` |
| Case134 | pass | `benchmarks/cases/134_task005_final_lock_review/records/case134_check.json` |

M5R used only existing arrays, JSON records and Fisher tables. It did not modify
the immutable v1 package, v1 lock, Task004 train112 or blind24 state; no new FEM,
formal surrogate, Task006 or inversion was started.

## Approved metadata closeout

| item | value |
|---|---|
| final status | `approved_closed` |
| M0–M4 implementation SHA | `d24395b377259da129a81384f88d8a4ad74602d2` |
| M5R generator commit SHA | `25327ab792a580fb198f07e59564c84149e952a1` |
| M5R source SHA256 | `0baf314334b67a7668f5ecd663ed1d3c6bb41abd7fe96132ade78f5bbc5f1e42` |
| V2 lock SHA256 | `065dff4bf85722ca43af368e427708d1da78d5fae0178f7967c094b005ff12c3` |
| Task006 authorization | M0–M2 only |

The closeout is metadata-only. V1/V2 locks and all raw/derived data packages are
unchanged. See `TASK005_FINAL_STATUS.json` and `TASK005_APPROVED_CLOSEOUT.md`.
