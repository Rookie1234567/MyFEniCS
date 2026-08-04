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
