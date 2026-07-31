# Round-1 prospective audit

The audit is stored in `ROUND1_FIXED_REFERENCE_AUDIT.json`. It evaluates both
G1 and G2 using only the original 96 training rows before the eight Round-1
points were added, then reports each new point's aggregate error, predicted
uncertainty, standardized error, and leave-one-new-point-out diagnostic. The
audit is training-domain evidence only; `validation_target_accessed=false`.

The fixed-reference comparisons and the 96/104/112 learning curve use the
same original-96 test rows and the same model contracts. They do not unlock
the frozen validation split.
