# 0.7 nm dispersion and directional-grid validation

## Current result

V0/V1/V2 offline closeout is complete. The actual p6 Basix/FFCx reference-cell symbol and flat-layer direct calibration support the Hx numerical-dispersion hypothesis. This does not establish full-grating mesh convergence or complete-DtN accuracy.

The user has authorized one next full-grating candidate, D: p6 condensed direct MUMPS on 200×2×118 = 47,200 hexahedra, with hx=0.25 nm and z intervals 9/100/9. D changes both x and z and must be labeled CROSS_CHANGED_GRID_DIAGNOSTIC. No B=93,600-cell case, C case, or full p7/p8 solve is authorized.

## V0 provenance reconciliation

The 5 nm full600 direct summary reports passed numerical checks (full A6 relative residual 9.59405650939179e-11 and port-volume energy difference -1.552757922240744e-12). Its original outer run summary remains EVIDENCE_INCOMPLETE because the run started at source d0dd7f09 and an authorized docs-only commit changed HEAD to 37a76ecc while it was active. The supplemental V0 record binds all eight docs-only paths and verifies that the src and input tree OIDs did not change. No original manifest or summary was rewritten and no provenance gate was relaxed.

## V1 actual FE symbol

The reference-cell calculation uses the production Basix N1E basis and actual FFCx volume-form quadrature metadata: p6 q15 (8×8×8 = 512 reference points), p7 q17 and p8 q19; the production surface inventory remains q160. The p6 dimensionless symbol error delta=(lambda-kx²)/k0² is:

| hx (nm) | hz (nm) | delta | lambda/kx²−1 | plane-wave mass overlap |
|---:|---:|---:|---:|---:|
| 0.5 | 0.6 | 7.93795478e-6 | 7.94037331e-6 | 0.99999999434 |
| 0.25 | 0.6 | 2.57599732e-9 | 2.57678212e-9 | 0.9999999999999 |
| 0.125 | 0.6 | 6.54204272e-13 | 6.54365451e-13 | 1.0 |
| 0.5 | 10/17 | 7.93795478e-6 | 7.94037331e-6 | 0.99999999434 |
| 0.25 | 10/17 | 2.57602166e-9 | 2.57680655e-9 | 0.9999999999999 |
| 0.125 | 10/17 | 8.52458681e-13 | 8.52651283e-13 | 1.0 |

The hx=.5 to .25 p6 delta decreases by about 3.08×10³. The hx=.125 values are near the observed floating-point floor: longdouble has 63 mantissa bits on this host and the recorded condition-scaled roundoff estimate is about 2.0e-13. The p7 and p8 calculations are bounded reference-cell checks at hx=.5 only. This is not a production-MPC/orientation or real-port verification: those are explicitly NOT_RUN in the V1 record.

## V2 flat-layer direct calibration

All three cases use p6, y=2, the same z mesh, material, incidence, boundary, exact sample coordinates and 540 auto-propagating modes. The finite DtN inventory excludes evanescent orders. The direct worker summaries pass their own numerical gates; the original enclosing run summaries remain unchanged as EVIDENCE_INCOMPLETE.

| Nx | cells | hx (nm) | R | T | A_port | A_volume | energy closure abs | full A6 residual |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 936 | 0.5 | 0.122362042763 | 0.801115353455 | 0.076522603781 | 0.076522603835 | 5.32e-11 | 3.72e-9 |
| 4 | 1872 | 0.25 | 0.113493258322 | 0.810538787016 | 0.075967954662 | 0.075967954603 | 5.88e-11 | 1.18e-9 |
| 8 | 3744 | 0.125 | 0.113490809114 | 0.810541453128 | 0.075967737757 | 0.075967738142 | 3.85e-10 | 4.20e-9 |

For Nx8, the independent flat-interface reference is R=0.113490809318, T=0.810541452554, A=0.075967738128. The corresponding absolute differences are approximately 2.04e-10, 5.75e-10 and 3.71e-10. This is a flat-interface reference, not the grating RCWA result.

Comparisons use raw complex values without a fitted global phase. At the same 320 air-side points (x=16 samples, y=4, z=5) and interface tangential samples, Nx4 versus Nx8 has relative L2 differences:

| Quantity | Relative L2 |
|---|---:|
| E all components / points | 6.50e-5 |
| H all components / points | 7.31e-5 |
| interface tangential E | 6.73e-5 |
| interface tangential H | 7.46e-5 |
| all top outgoing modal amplitudes | 1.95e-4 |
| all bottom outgoing modal amplitudes | 9.65e-5 |

Nx2 versus Nx8 field and modal differences are around 0.20–0.62 relative L2, while Nx4/Nx8 R and T differ by 2.45e-6 and 2.67e-6. These three points show stabilization in this flat case, but are not an asymptotic convergence proof or rigorous error bound. All 540 per-order complex amplitudes and R/T contributions are in flat_modal_orders.csv.

### Matrix, factor and resources

| Nx | condensed matrix shape | PETSc nz_used / nz_allocated | MUMPS lifecycle (s) | sampled tree RSS peak |
|---:|---:|---:|---:|---:|
| 2 | 186,156² | 143,247,686 / 143,413,200 | 45.89 | 14,885,482,496 B |
| 4 | 371,772² | 299,391,182 / 299,541,744 | 154.80 | 30,157,877,248 B |
| 8 | 743,004² | 598,646,088 / 598,791,888 | 643.63 | 65,999,884,288 B |

The JSON retains raw matrix/factor lifecycle facts and MUMPS INFOG/RINFOG. Backend indices and units are not reinterpreted as RSS. Nx8 had a separately authorized 512 GiB small-case hard cap; this is not transferable to the original grating.

All three sampled process-tree VmSwap peaks are zero. Nx2 and Nx8 watchdogs also recorded +2 and +10 global pswpin pages, respectively, with task attribution unresolved; these cannot be called task swap or qualified zero-swap runs. Nx4 recorded zero tree swap and zero global page counters with the newer watchdog state. Its enclosing summary still says EVIDENCE_INCOMPLETE because the old task038 launcher only recognized the older state string. A focused fail-closed compatibility fix and regression test are included; old run summaries are not edited.

## What remains unknown

- The reference-cell symbol does not instantiate production Floquet MPC or actual mesh cell orientations.
- Flat tests do not verify the original rectangular grating, its full 572-mode N0 operator, or evanescent/full-DtN effects.
- Nx4/Nx8 are not a grating z-resolution study.
- Nx8 resource use is small-flat evidence only; it does not predict D capacity.
- The original grating's z accuracy remains unknown. D changes x and z together, so it cannot isolate either direction or establish convergence.
- RCWA comparison authority remains bounded by the previously archived source/provenance limits.

## Files

- flat_calibration.json: identities, V0/V1 evidence, all pairwise field/modal comparisons, R/T/A, matrix/factor facts.
- directional_grid_comparison.csv: three-grid scalar and resource table.
- flat_modal_orders.csv: all 540 modal complex amplitudes, powers and pairwise differences.
- resource_and_scope.json: original classifications and swap-attribution boundary.
- compare_flat_direct_runs.py: deterministic offline extractor; reads only the listed small summaries/configs, outputs and the three hash-bound 33–34 KiB sample archives; it does not read resource streams, full fields, matrices or factors.
