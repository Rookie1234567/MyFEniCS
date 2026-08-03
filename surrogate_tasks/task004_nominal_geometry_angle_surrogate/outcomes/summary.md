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
