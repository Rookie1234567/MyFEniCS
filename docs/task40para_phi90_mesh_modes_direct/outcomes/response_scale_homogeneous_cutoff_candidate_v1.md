# Scale-homogeneous sparse cutoff candidate — review only

## Scope and call chain

This is a Task40 diagnostic candidate on the existing saved Y2 and Y3 fields. It does not change any solver profile or the legacy sparse cutoff default.

1. `_vec_nonzero_owned_entries(..., scale_homogeneous=True)` filters each x/y surface component on the existing owned/MPC support. It uses the same global `MPI.MAX` magnitude and keeps `abs(value)/global_max > 1e-13`.
2. `_combine_owned_entries(..., scale_homogeneous=True)` keeps the existing coefficient application, stable mergesort, unique-row grouping, `np.add.reduceat` order, and global maximum. Projection still conjugates only after merging; coupling remains non-conjugated.
3. The saved-field wrapper enables those flags only while the V4 capture function assembles these six q28 signed-key functionals. It restores both production helper functions and accounting functions on every return or exception. All normal callers continue through the unchanged default `max(1e-30, relative_tol * global_max)` path.
4. The candidate report is bound beside the frozen V4 default-floor report. Each Y2/Y3 key compares legacy V4, candidate, untruncated component merge, and the independent q28 integrals on the same zero-slave storage and its same-storage MPC-backsubstituted full-primal expansion. The original carrier gate remains `NO_CARRIER_COMPARISON`/failed-open; this report cannot qualify a carrier or FE field.

## Scale and closure handling

Zero component or merged vectors produce an empty rowset. Non-finite values, magnitude overflow, non-finite coefficients, merge overflow, and a nonzero coefficient product that underflows all the way to zero are rejected. A normalized ratio that underflows to zero is below the positive `1e-13` tolerance and is discarded. Representable subnormal nonzero products are kept as represented and flagged as a precision limit; values are never rescaled before being returned.

For projection and coupling, the diagnostic records each stage's dot, `sum(abs(products))` in long-double text form, term count, and closure absolute residual. It uses no `1e-30` closure floor. Closure diagnostics describe only sparse accounting; they are not a physical residual or qualification gate. Coupling remains a non-conjugated algebraic dot, not physical power. Top `(0,0,s)` is compared to the saved total auxiliary projection, with incident and outgoing amplitudes kept separate.

## Validation and execution status

The focused pure suite invokes the actual production helpers and tests complex-rescaling rowset invariance, projection/coupling routes, default-floor compatibility, zero, non-finite input, magnitude and merge overflow, product underflow, and package wiring. It does not build a mesh or run FE. The exact command/result and package hashes are recorded in `d13_saved_field_scale_homogeneous_cutoff_validation_v1.json`.

The package and sidecar are frozen for review only. No fresh admission, worker, FE, carrier, global matrix, factor, or solve was run for this candidate. The original V4/V5 failure and qualification status are preserved.
