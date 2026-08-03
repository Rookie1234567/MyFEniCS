# M4H selective region report

This report uses only the immutable train112 OOF records. Region labels are
overlapping diagnostics; an accepted count is never treated as a zero error
for rejected points.

| point predictor | risk rule | accepted OOF | low grazing | high azimuth | cutoff near | ordinary interior | boundary | old96 | new16 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| local RBF k24 | S1 M4E2 | 81/112 | 29/43 (0.674) | 10/24 (0.417) | 62/90 (0.689) | 44/55 (0.800) | 23/32 (0.719) | 70/96 (0.729) | 11/16 (0.688) |
| local Matérn k24 | S1 M4E2 | 81/112 | 29/43 (0.674) | 10/24 (0.417) | 62/90 (0.689) | 44/55 (0.800) | 23/32 (0.719) | 70/96 (0.729) | 11/16 (0.688) |
| latent median | S1 M4E2 | 81/112 | 29/43 (0.674) | 10/24 (0.417) | 62/90 (0.689) | 44/55 (0.800) | 23/32 (0.719) | 70/96 (0.729) | 11/16 (0.688) |
| local RBF k24 | S2 std+disagreement | 112/112 | 43/43 (1.000) | 24/24 (1.000) | 90/90 (1.000) | 55/55 (1.000) | 32/32 (1.000) | 96/96 (1.000) | 16/16 (1.000) |
| local Matérn k24 | S2 std+disagreement | 112/112 | 43/43 (1.000) | 24/24 (1.000) | 90/90 (1.000) | 55/55 (1.000) | 32/32 (1.000) | 96/96 (1.000) | 16/16 (1.000) |
| latent median | S2 std+disagreement | 112/112 | 43/43 (1.000) | 24/24 (1.000) | 90/90 (1.000) | 55/55 (1.000) | 32/32 (1.000) | 96/96 (1.000) | 16/16 (1.000) |

For S1, accepted-set accuracy passes for the Matérn and latent-median rows but
cross-fitted coverage is 1.0 for every target, above the frozen upper limit
0.99. The RBF row also misses accepted-set accuracy (`A_balance` NRMSE
0.01481109 and p95 0.01395993). S2 accepts all rows and therefore retains the
known full-domain tail errors; it is not a selective qualification.

The high-azimuth acceptance rate is reported separately rather than hidden in
an ordinary-interior aggregate. Order-resolved outputs remain unqualified.

