# Task003 response V4

Required M3T and the conditionally authorized Round-2 active-learning run are
complete. The stale stage authority was replaced with a post-Round-2 status.
An independent exact-design checker passed for the deterministic 112-training
+16-frozen-validation package: original 96 rows are unchanged, both sets of
eight active-learning tuples match their design files, all hashes rebuild, and
the frozen-validation tuple table is unchanged.

The original 96 reference folds were frozen and a 96/104/112 learning curve
was computed for the same G1 constant-GP and G2 degree-2 Legendre-trend plus
Matérn-5/2 residual-GP contracts. Round-1 prospective diagnostics and P2
side-total/masked-fraction power records remain training-only. The Round-2
plan satisfied the domain-wide diversity constraints and all exactly eight
Ny4 p5 Full3D cases measured pass with zero numerical failures, zero resource
controlled stops, and clean compact records.

The 112-row training-only CV still fails the frozen aggregate hard Gate. The
selected training-CV candidate is
`G1_constant_gp:features=B:jitter=1e-08`; no MODEL_SELECTION_LOCK was created.
The 16 frozen-validation targets were not accessed, and no Round-3 FEM,
validation scoring, angle DOE, or inversion was started. Work stops here for
Review V3.
