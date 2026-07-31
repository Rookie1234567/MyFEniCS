# Model selection status

`MODEL_SELECTION_LOCK.json` was deliberately not created. Training CV selected
`exact_gp:features=B` as the lowest recorded candidate score, but the lock is
only valid after the aggregate and primary-power hard Gates pass and must
precede any read of the 16 validation targets. This run therefore has no
selected production model and makes no claim of surrogate qualification.
