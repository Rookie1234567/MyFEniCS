# Task005 M1 finite-difference step audit

Status: **pass**

The audit compares noise-whitened central derivatives from coarse and half steps. N1/N2 are provisional diagonal DOE scenarios, not calibrated experimental covariance.

| contract/parameter | passing audit angles | gate |
|---|---:|---|
| M0_aggregate_RT:h | 5/5 | True |
| M0_aggregate_RT:w | 5/5 | True |
| M1_order_total_robust:h | 5/5 | True |
| M1_order_total_robust:w | 5/5 | True |

Failure reasons:

