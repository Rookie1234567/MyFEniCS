# 0.7 nm dispersion and directional-grid validation

## Current result

V0/V1/V2 offline closeout is complete. The actual p6 Basix/FFCx reference-cell symbol and flat-layer direct calibration support the Hx numerical-dispersion hypothesis. This does not establish full-grating mesh convergence or complete-DtN accuracy.

Candidate D has completed once: p6 condensed direct MUMPS on 200×2×118 = 47,200 hexahedra, hx=0.25 nm and z intervals 9/100/9. Its own A6_n0 and energy checks pass, but it changes both x and z and must remain `CROSS_CHANGED_GRID_DIAGNOSTIC`; it is not a one-axis convergence result. No B=93,600-cell case, C case, or full p7/p8 solve was run.

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
- Nx8 resource use is small-flat evidence only; it did not predict D capacity. D's own measured process-tree RSS peak is reported below.
- The original grating's z accuracy remains unknown. D changes x and z together, so it cannot isolate either direction or establish convergence.
- RCWA comparison authority remains bounded by the previously archived source/provenance limits.

## Candidate D: completed full-grating direct solve

The approved candidate used the same 0.7 nm Si material, 1° S-polarized incidence, p6 elements, two y layers, 572 active N0 channels and the full-parent q160 integration rule. The mesh was 200×2×118=47,200 cells: x had 66/68/66 cells at 0.25 nm, while z used 9/100/9 intervals (10/9, 1.2 and 10/9 nm). It changed x and z together. The old A mesh was 100×2×234=46,800 cells (x=0.5 nm, z=17/200/17); source identities also differ, so the A-to-D contrast is diagnostic rather than a controlled single-variable proof.

The direct route eliminates cell-interior unknowns locally, then factors and solves the resulting sparse global matrix with MUMPS. This avoids the p4/BAL_H iteration path for this case; it costs one large direct factorization. The factorization, numeric phase and solve used the same materialized matrix object.

| Result | Old A, p6 direct | Candidate D, p6 direct | RCWA report |
|---|---:|---:|---:|
| R total | 0.08592253473181985 | 0.07028528534177456 | 0.0702787390763 |
| T total | 0.6522079390017288 | 0.6688236885790999 | 0.668830211715 |
| A from port balance | 0.2618695262664513 | 0.2608910260791255 | — |
| A from material-volume integral | 0.26186952633636734 | 0.260891026570664 | 0.260891048523 reported |
| Port-volume energy closure | 6.991607293116431e-11 | 4.915383655657024e-10 | — |
| Original A6_n0 relative residual | 7.427046290347574e-8 | 1.3202759103785678e-7 | — |

D differs from old A by R=-0.0156372493900, T=+0.0166157495774 and A_volume=-0.0009784997657. Against the displayed RCWA report totals, D differs by R=+6.54626543e-6, T=-6.52313555e-6 and A_volume=-2.19523360e-8. The per-order comparison covers all 143 `(m,n)=(m,0)`, m=-142…0, with no phase fitting. Seven orders meet the union significance threshold 1e-8 across the compared records; the remaining 136-order tail sums are in the comparison JSON/CSV. The RCWA record contains powers, not corresponding complex RCWA amplitudes.

At identical exported sample coordinates (40 x 20 x 5 = 4,000 points; air-side z=10/30/60/90/110 nm), raw complex sample differences D-versus-A are relative L2 0.18568 for E, 0.18515 for H, and 0.18515 for exported curl(E); interface tangential E/H are 0.18860/0.23256. No global phase was fitted. These are bounded sample comparisons, not full-domain norms or errors against an exact grating solution.

The condensed matrix was 9,374,972×9,374,972, with 7,553,047,842 stored nonzeros used and 7,611,634,384 allocated. Assembly took 4,829.26 s; the recorded MUMPS symbolic/numeric/solve lifecycle took 39,664.86 s; the worker's reported full elapsed was 52,635.82 s and the enclosing workflow elapsed was 52,726.35 s. The raw indexed INFOG/RINFOG values remain in the run summary and are not reinterpreted as RSS.

The one complete resource audit read only explicit top-level fields from `watchdog/resources.jsonl`: 153,151 records, no malformed lines and no unreadable-status records. Peak simultaneous process-tree RSS was 1,303,868,440,576 B, below the 1,800,000,000,000 B hard limit by 496,131,559,424 B; it exceeded the advisory 1.17e12 B warning level. Sampled process-tree swap stayed zero, but global pswpin/pswpout changed by +27/+72 pages and attribution is unresolved, so this is not a system-wide or dedicated zero-swap qualification. PSS/USS were disabled by contract.

D's worker reports `passed=true`, original A6_n0 residual below its 1e-6 limit, and energy closure below 1e-5. Its final authority remains `AUTHORITY_LIMITED` / `FULL_DTN_NOT_VERIFIED`; omitted channels were not computed. The result supports the practical D-grid output comparison but cannot identify whether the change came from x, z, their interaction, or source differences. See [response](../../response_dispersion_validation_20261015.md), [compact terminal record](../records/v7_candidate_d_terminal_compact_20261016.json), [all-order and sampled-field comparison](candidate_d_comparison.json), and [143-order CSV](candidate_d_orders_143.csv).

## Files

- flat_calibration.json: identities, V0/V1 evidence, all pairwise field/modal comparisons, R/T/A, matrix/factor facts.
- directional_grid_comparison.csv: three-grid scalar and resource table.
- flat_modal_orders.csv: all 540 modal complex amplitudes, powers and pairwise differences.
- resource_and_scope.json: original classifications and swap-attribution boundary.
- compare_flat_direct_runs.py: deterministic offline extractor; reads only the listed small summaries/configs, outputs and the three hash-bound 33–34 KiB sample archives; it does not read resource streams, full fields, matrices or factors.
- candidate_d_comparison.json / candidate_d_orders_143.csv: old A versus D and displayed RCWA power comparison for all 143 orders, plus exact-coordinate complex E/H/curl sample differences without phase fitting.
- candidate_d_terminal_compact_20261016.json: D run identity, direct-factor/matrix facts, numerical scope, one resource-stream audit and output artifact bindings.
- compare_candidate_d_runs.py: deterministic offline extractor for the preceding D comparison, limited to the small order JSON/CSV files and bounded sample NPZ archives.
