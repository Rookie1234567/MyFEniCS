# Task004 M0R/M1R/M2R/M3R summary

| item | status | evidence |
|---|---|---|
| clean numerical baseline | `fdf961545f217d620e22800f2704ae9913a6d270` | `TASK004_FORWARD_BASELINE_v2.json` |
| explicit MUMPS workspace | ICNTL(14)=40, 2/2 fresh passes | `mumps_workspace_ladder.md` |
| five clean-SHA anchors | 5/5 pass | `forward_baseline_v2.md` |
| training canary | 16/16 pass | Case124 batch summary `indices_0000_0015.json` |
| training FEM campaign | 96/96 `measured_pass` | Case124 training campaign manifest |
| training/validation/candidate/anchor designs | frozen; tuples unchanged | `design_rebind.md` |
| Task004 blind validation | sealed, not run | `response_v2.md` |
| ANGLE_MODEL_SELECTION_LOCK | not created | training-only review boundary |
| surrogate training/CV | not run | `response_v2.md` |
| Task003 Round3/frozen validation | not run/not accessed | `response_v2.md` |

All 103 formal forward records (2 ladder + 5 anchors + 96 training) use the
same Full3D static uniform N1curl p5/h10/Ny4 identity, observable-v3 and
source SHA. The independent Case124 checker recomputes design hashes and
re-reads solver records; it reports `status=pass` without launching a solver.

The first training index had one explained preflight retry before PDE execution
because the wrong interpreter was used. The fresh baseline retry is the
measured record; no numerical failure was skipped or overwritten. This does not
unlock blind validation or any surrogate model-selection step.

## M4H selective closure

| item | result | evidence |
|---|---|---|
| selective point predictors | local RBF k24, local Matérn k24, latent median only | `SELECTIVE_MODEL_COMPARISON.json` |
| cross-fitted risk rules | S1 frozen M4E2, S2 std+disagreement | `SELECTIVE_RISK_SIGNAL_CONTRACT.json` |
| accepted OOF | S1 81/112; S2 112/112 | `SELECTIVE_MODEL_COMPARISON.json` |
| candidate pool / blind-design screen | S1 3937/4096 and 22/24; S2 4096/4096 and 24/24 | acceptance-domain JSON |
| selective training-only qualification | controlled negative; no pair passes all Gates | `ANGLE_AGGREGATE_SELECTIVE_QUALIFICATION_CONTRACT.json` |
| structural support vs selective acceptance | separate domains; structural 4074/4096, blind 24/24 | structural/acceptance-domain JSON |
| model lock / blind FEM | not created / not run | Case129 checker |

M4H was training-only and response-blind. S1 Matérn and latent median had
accepted-set accuracy but empirical 95% coverage of 1.0, above the frozen 0.99
upper bound; S2 retained the full-domain tail error. Task004 therefore stops
as a controlled negative and waits for Review V7.

## M4I selective threshold and conditional interval correction

| item | result | evidence |
|---|---|---|
| allowed point predictors | Q1 local Matérn k24; Q2 latent median | `SELECTIVE_MODEL_COMPARISON_V2.json` |
| risk rule | S1 pre-frozen M4E2 ensemble only | `SELECTIVE_THRESHOLD_CORRECTION.json` |
| predictor-specific source thresholds | 5/5 folds qualified for each Q1/Q2; no fallback | threshold correction + Case130 |
| final unified threshold | quantile 0.85; threshold 0.5529775444799786 for both | threshold correction JSON |
| Q1 accepted OOF / pool / blind preacceptance | 92/112; 4013/4096; 22/24 | comparison/acceptance-domain JSON |
| Q2 accepted OOF / pool / blind preacceptance | 91/112; 4013/4096; 22/24 | comparison/acceptance-domain JSON |
| conditional conformal coverage/sharpness | pass for all Q1/Q2 targets | `SELECTIVE_CONDITIONAL_CONFORMAL.json` |
| point-accuracy Gate | fail for both Q1 and Q2 | M4I comparison |
| Case130 evidence checker | pass; qualification remains controlled negative | `case130_check.json` |
| model lock / blind FEM | absent / not run | Case130 checker |

M4I kept the frozen point-accuracy Gate unchanged. Predictor-specific thresholds
and accepted-source conformal intervals qualified the source-selection and
uncertainty contracts, but the resulting cross-fitted accepted sets still
exceeded the fixed point-error limits. Consequently no model lock or blind FEM
was authorized; Task003 validation, second-round active learning, Fisher,
geometry sensitivity and inversion remain untouched. See
`outcomes/m4i_selective_qualification.md` and `response_v8.md`.
