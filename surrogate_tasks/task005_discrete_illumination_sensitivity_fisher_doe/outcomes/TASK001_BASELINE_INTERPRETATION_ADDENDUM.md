# Task001 baseline interpretation addendum

This is a derived-only interpretation of the unchanged Task001 pair A14+A15.
It does not relabel either historical result as false and does not add FEM data.

| contract / noise | full rank | min eigenvalue | logdet | condition number |
|---|---:|---:|---:|---:|
| M0_aggregate_RT / N1 | True | 0.88747292488 | 2.75105630323 | 19.881921148 |
| M0_aggregate_RT / N2 | True | 0.0368624941887 | -1.85029656123 | 115.679653578 |
| M1_order_total_robust / N1 | True | 3.00320070599e-05 | -7.58166837239 | 565138.048375 |
| M1_order_total_robust / N2 | True | 7.49727286431e-06 | -10.3571179076 | 565137.608668 |
| M2_order_total_extended / N1 | True | 0.794080510748 | 2.63593619478 | 22.133162351 |
| M2_order_total_extended / N2 | True | 0.0328735163573 | -1.96575093188 | 129.59638717 |

## Interpretation

Task001's A14+A15 pair is retained as the historical 10°/0° + 10°/90° reference. Under Task005 M0 aggregate `[R_total,T_total]`, it remains full rank, but its parameter directions are strongly correlated. Under Task005 M1 robust order-total, the active-channel threshold leaves one channel per angle and the pair is nearly rank deficient: the N2 condition number is about 5.65e5. M2 extended weak channels improve that diagnostic number to about 129.6 under N2, but the pair is still far below the new robust candidates.

The difference from Task001 is a contract change, not a contradiction:

- Task001 and Task005 use different observable/measurement contracts.
- Task005 excludes duplicate aggregate/order information and uses the robust-channel threshold explicitly.
- Task005 adds an absolute noise floor in both provisional N1 and N2.
- M2 weak channels are diagnostic and are not allowed to override the robust M0/M1 choice.

All Fisher values remain local DOE metrics under provisional diagonal noise scenarios, not calibrated experimental uncertainty or a posterior.
