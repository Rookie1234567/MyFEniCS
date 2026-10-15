# Response: 0.7 nm dispersion and directional-mesh validation

## Result so far

The actual p6 reference-cell symbol and the flat-layer Nx2/Nx4/Nx8 direct cases both support the Hx numerical-dispersion hypothesis. The conclusion is limited: the original grating has not yet been tested on a refined-x or coarsened-z grid, and full evanescent DtN authority remains unverified.

V1 used the actual Basix N1E basis and FFCx-derived production volume quadrature rules. With p6 and hz=0.6 nm, delta=(lambda−kx²)/k0² decreased from 7.94e-6 at hx=0.5 nm to 2.58e-9 at hx=0.25 nm. The hx=0.125 nm value, 6.54e-13, is close to the measured floating-point floor and is not evidence for an arbitrarily high convergence rate. p7/p8 were bounded reference-cell checks only.

In the flat calibration, R/T/A moved from 0.1223620/0.8011154/0.0765226 at Nx2 to 0.1134933/0.8105388/0.0759680 at Nx4, then to 0.1134908/0.8105415/0.0759677 at Nx8. At common coordinates, Nx4/Nx8 relative field-sample differences were 6.50e-5 for E and 7.31e-5 for H; all 540 auto-propagating output amplitudes were also compared as raw complex values without phase fitting. This is a flat-layer calibration, not the grating.

## Original-grating follow-up now authorized

The user has authorized exactly one candidate D full-grating run: p6 direct condensed MUMPS, 200×2×118=47,200 hex cells, hx=0.25 nm and z sections 9/100/9. It retains the original 0.7 nm Si material, 1° S incidence, periods and geometry, 572 N0 modes with all m=-142…0 top/bottom s/p channels, parent metadata and q160, and the p6 recovery/output checks.

D changes x and z at once. Any result is a CROSS_CHANGED_GRID_DIAGNOSTIC; it cannot independently prove x-only improvement, z accuracy, or convergence. The old 46,800-cell run and the new 47,200-cell candidate must use separate mesh/DOF/MPC/matrix/factor identities. No FE arrays or factors are reused.

The D hard tree-RSS limit remains 1.8e12 B. Capacity review must use measured trace/port/CSR structure and same-matrix symbolic facts; cell-count scaling alone is not an admission argument. Symbolic estimates are diagnostic, not a memory upper bound. The current 65.9999 GB flat Nx8 peak and its special 512 GiB cap do not transfer to D. B=93,600 cells, C, and full p7/p8 runs are not authorized.

## Qualification limits

The flat cases used a finite auto-propagating port set and do not establish full-DtN accuracy. The V1 symbol is a canonical reference-cell result and did not instantiate production MPC or actual grating cell orientations. The full600 direct numerical summary passed its own A6 and energy checks, but its enclosing run summary remains EVIDENCE_INCOMPLETE because a docs-only HEAD change occurred during the run; the supplemental V0 record verifies the source and input trees were unchanged and leaves the original summary intact.

Nx4 has zero sampled task-tree VmSwap and zero global page counters in its watchdog report, but its old outer classification remains EVIDENCE_INCOMPLETE because the launcher recognized only the old watchdog status string. The narrow future classifier fix is tested. Nx2 and Nx8 had nonzero global page-in deltas that cannot be attributed to those tasks; they are not labeled zero-swap-qualified.

The archived RCWA comparison remains authority-limited by its existing provenance boundary. This response does not claim a complete DtN/RCWA match, grating convergence, z accuracy, or a resource guarantee for D. D's measured R/T/A, modal amplitudes, restored fields and RSS will be added after its single authorized run terminates.

## Evidence index

- [Offline V0/V1/V2 summary](outcomes/dispersion_directional_validation_20261015/summary.md)
- [Flat calibration and pairwise complex comparison](outcomes/dispersion_directional_validation_20261015/flat_calibration.json)
- [All per-order flat R/T and complex amplitudes](outcomes/dispersion_directional_validation_20261015/flat_modal_orders.csv)
- [Resource and classification boundary](outcomes/dispersion_directional_validation_20261015/resource_and_scope.json)
- [V0 docs-only source reconciliation](outcomes/dispersion_directional_validation_20261015/v0_source_identity_reconciliation.json)
- [V1 actual Basix/FFCx symbol record](outcomes/dispersion_directional_validation_20261015/v1_actual_n1e_ey_dispersion_symbol.json)
