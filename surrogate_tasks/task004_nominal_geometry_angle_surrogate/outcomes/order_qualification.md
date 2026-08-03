# Level B order-resolved qualification

Level B predicts the fixed reflection/transmission order array and its
outgoing S/P powers.  The analytic mask is authoritative: inactive channels
remain `power=null`/`mask=false`, and an unseen topology is `unsupported`.
The OOF aggregate prediction and fold-local channel-fraction models are kept
separate, so the test-fold power truth is never used to construct its own
prediction.

The independent power ledger passed:

```text
mask agreement                 = 100%
maximum sidewise ledger error  = 2.220446049250313e-16
```

The primary-channel accuracy Gate did not pass.  Representative primary
channels include reflection `m=0,S` (order index 7), with p95 absolute error
`0.0230207` and max error `0.10852`, and transmission `m=0,S` with p95
`0.0196077` and max `0.34159`.  Reflection `m=-1,S` and transmission
`m=-1,S` also have normalized errors above the `NRMSE≤0.03` criterion.  The
full per-channel values, active counts, tiers and uncertainty summaries are in
`ANGLE_ORDER_QUALIFICATION_CONTRACT.json`; no weak channel was omitted.

Consequently Level B is `not_qualified`.  This does not invalidate the exact
aggregate composition or the power ledger; it means that correct total R/T
does not yet imply correct allocation among individual diffraction orders.
The order contract is separate from Level A and no order model lock was
created.  The 7 rare unseen candidate-pool mask signatures remain
response-blind design evidence and will be fail-closed if queried.
