# Frozen validation status

The 16 frozen-validation tuples and targets remain sealed. No validation
array was opened, used for feature statistics, transforms, model comparison,
kernel fitting, or error reporting. The explicit unlock path remains
`MODEL_SELECTION_LOCK.json` plus `--unlock-frozen-validation`; it was not
available in this controlled-stop run.

