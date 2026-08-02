# Task004 summary

| item | status | evidence |
|---|---|---|
| clean implementation baseline | `7fe366304023c32bf2e8ddcacdb2ada9996d3e7c` | `TASK004_FORWARD_BASELINE.json` |
| angle designs | frozen, response-blind | Case123 design JSONs |
| training angles | 96 designed, 0 measured | `design.md`; training campaign not started |
| blind validation angles | 24 designed, 0 measured | `design.md`; validation sealed |
| clean-SHA anchors | controlled stop at first point | `TASK004_FORWARD_BASELINE.json` |
| angle models / API | implemented, not qualified | `src/surrogate/angle/` |
| Task003 Round3 / validation | not run / not accessed | explicit boundary |

The first new-SHA anchor reached direct LU setup and stopped with MUMPS
`INFOG(1)=-9`, `INFO(2)=919260`; no official observable or formal record was
created. Because the task requires stopping at the first unexplained numerical
failure, no training FEM, blind-validation FEM, model fitting, active learning,
angle maps, or formal DOE was started.
