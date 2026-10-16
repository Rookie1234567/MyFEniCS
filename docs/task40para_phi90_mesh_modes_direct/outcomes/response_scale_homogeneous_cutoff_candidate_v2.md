# Scale-homogeneous cutoff candidate v2 — review only

## Narrow correction

The opt-in candidate keeps the production relative_tol=1e-13, owned/global maximum, MPC support, conjugation, and sparse ordering at both component filtering and projection/coupling merge filtering. Only the Task40 saved-field capture wrapper installs the relative-only helpers; it saves and invokes the original V4 capture callable exactly once, then restores every patched helper in finally. The historical V4 default-floor route remains unchanged.

Candidate, V4, untruncated, and saved auxiliary values are compared in consistent boundary-amplitude units: saved_total_auxiliary_projection * P is compared with each N/H * P. Raw projection, converted total boundary value, incident projection, and outgoing boundary amplitude remain separately named. Coupling is still a non-conjugated algebraic dot, not physical power.

## Validation scope

The focused no-mesh test runs the real candidate wrapper around a fake original capture, the real production vector/merge helpers, the real candidate accounting structure, JSON-safe readback, and frozen-V4 attachment. It verifies a single original-capture call, helper restoration, the renamed coupling record key, and a non-unit test phase P=4e-29. It does not build a mesh, carrier, global matrix, factor, or solve.

The V2 contract explicitly records that src/solvers/dtn_port_3d.py differs from the historical Y2 source for this candidate and that all legacy callers retain the old default floor. The V1 artifacts remain preserved. The V2 package is review-only; no fresh or worker run has been performed.
