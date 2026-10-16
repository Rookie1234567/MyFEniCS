# D13 Y / Y2 comparison

## Scope and identity

This compares the completed Y and Y2 direct runs from their saved port artifacts and common-coordinate complex field samples. It is an offline comparison; no FE run was repeated. Complex values are compared directly with no global phase fit.

| Case | Run | Source | Input SHA-256 | Physical-model SHA-256 | Mesh | Cells |
|---|---|---|---|---|---|---:|
| Y | `20261016T102453.831934Z` | `9c0fe6a30554aab33a04ff0245b19c03e4f01f28` | `78b595e4b514e4471184f281e2aa3072dd321206acfee5295b0c0151a7f74f10` | `b9f2aac65e9ce3274c2a3322b8094f88f07b3a6eb7b7db98791478f0ffdd5e56` | `[6,12,14]` | 1,008 |
| Y2 | `20261016T112452.011352Z` | `74d5aae3dea064e128e53a253fc5aac0f2b1f146` | `7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994` | `ac65772c3fda31f22599824023f43e05e62b8292de31652dff226909fc83fa7b` | `[6,24,14]` | 2,016 |

The actual x and z axis hashes are identical; only y changes. The 612 ordered FE-port modes and their branch/material identities are identical (SHA-256 `1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e`). Both use the same production surface quadrature degree 28 and volume quadrature degree 15/default. This is a one-axis y-refinement comparison.

## Port powers

| Quantity | Y | Y2 | Absolute change |
|---|---:|---:|---:|
| Total R | 0.25135680708181884 | 0.25135571525076980 | 1.0918310491e-6 |
| Total T | 0.05712866544974556 | 0.05712882739311799 | 1.6194337243e-7 |
| Balance A | 0.6915145274684356 | 0.6915154573561123 | 9.2988767675e-7 |
| Volume A | 0.6915145274693181 | 0.6915156826412944 | 1.1551719763e-6 |
| Grating A | 0.6547002180127166 | 0.6547012824648758 | 1.0644521592e-6 |
| Substrate A | 0.03681430945660150 | 0.03681440017641860 | 9.0719817103e-8 |

The Y2 per-mode comparison retains the power-carrying mask (390 modes), which includes lossy modes even when `propagating=false`. Over those 390 modes, max `|ΔR|` is `1.2371187126e-6` at top `(m,n,s)=(0,0,s)`; max `|ΔT|` is `1.3986289955e-7` at bottom `(0,0,s)`. Across all 612 modes, max `|ΔT|` is the same. The propagating-only subset has 166 modes and max `|ΔT|=1.1805027323e-8`; this narrower subset is reported separately and does not replace the power-carrying result.

## Modal amplitudes and phase convention

Both runs use the same top and bottom reference planes, amplitude convention, and per-mode `boundary_phase` values for all 612 modes. The unphased `outgoing_amplitude` difference is very large (`relative L2=2.6785915e3`) because these stored coefficients use reference-plane scaling with complex-beta exponential factors. It is retained as a raw-coefficient diagnostic and is not the port-power comparison. After applying the common boundary phase, the physical `outgoing_amplitude_at_boundary` difference is `relative L2=3.9704284e-3`, with maximum absolute per-mode change `1.4869147e-3` at top `(m,n,s)=(−4,0,p)` and its symmetric `(+4,0,p)` partner. No phase alignment or amplitude-fit was applied. The auxiliary total-projection coefficient comparison is also retained in the JSON record.

## Saved complex-field samples

The saved sample coordinate arrays are exactly equal between runs: 40 x samples, 64 y samples, and 5 z planes. No interpolation was used. Relative L2 differences without phase fit are:

| Sample | Relative L2 change |
|---|---:|
| Full sampled E | 1.1561064e-5 |
| Full sampled H | 3.9563438e-5 |
| Saved tangential E on interface planes | 1.0795411e-5 |
| Saved tangential H on interface planes | 1.8422566e-4 |

The tangential samples are on horizontal modal-region planes at z=10 and 110 nm, with x/y components. They are not the pillar x/y sidewalls or the z=0/120 nm material interfaces. The canonical H(curl) sidewall trace gate remains **NOT MEASURED**: the existing DG6-node sidewall diagnostic has non-negligible duplicate-cell trace spread and is not a canonical trace comparison.

## Y2 solve and qualification boundary

Y2 finished with exit 0 and no descendants. Its direct summary reports:

- condensed residual `9.5217509104e-12` (gate `1e-9`);
- independent active-rectangle native A6 relative residual `3.0742513619e-10` (gate `1e-6`);
- native condensed identity relative residual `1.5410850886e-10`;
- one same-matrix correction, MUMPS symbolic/numeric calls `1/1`, solve calls `2`;
- `R+T` versus volume absorption closure `2.2528518206e-7` (gate `1e-5`);
- elapsed `2451.68 s`, sampled process-tree RSS peak `81,628,168,192 B`, task swap peak `0 B`, PSS disabled.

The run remains `AUTHORITY_LIMITED` and `FULL_DTN_NOT_VERIFIED`. The field metrics above are sampled-point comparisons, not a full-domain norm. This comparison quantifies the effect of bisecting the Y grid's actual y intervals while holding x, z, modes, and quadrature fixed; it is not a full-DtN or canonical sidewall qualification.

Machine-readable values and artifact bindings are in [d13_y_y2_comparison.json](records/d13_y_y2_comparison.json). The comparison is reproducible with [compare_d13_y_y2.py](analysis/compare_d13_y_y2.py).

## Offline modal-amplitude diagnosis after review

The additional audit reads only the five small `dtn_port_diffraction_orders_3d.json` and `dtn_auxiliary_amplitudes_3d.json` files. For all B/X/Y/Z/Y2 cases, the 612 mode keys/order, branch/material metadata, and the two modal output files match exactly. Across all 612 rows, the saved raw outgoing coefficient equals `auxiliary - incident` on top and `auxiliary` on bottom; `raw * boundary_phase` equals the saved boundary amplitude; the phase equals `exp(i*kz*z_reference)`; and `power_ratio` reconstructs from `modal_power_code_units / incident_power_code_units`. Each check has zero max discrepancy in the serialized values. The incident-power normalization is identical in all five cases (`21.815508046604222`). The source denominator is `area * electric_tangential_norm_sq * |boundary_phase|^2`; the modal `electric_tangential_norm_sq` itself is not serialized, so it is not independently recomputed here.

For top `(m=±4,n=0,p)`, `beta=+i*0.502589190201403 nm^-1`, `z_reference=130 nm`, and `|boundary_phase|=4.2138342045395975e-29` in every case. The raw coefficients therefore have a very large reference-plane scale. The same phase is applied exactly in every run, so it explains the raw magnitude but not the Y/Y2 change in boundary amplitude. The pair's boundary-amplitude L2 norm is about `4.28253e-7` for Y and `1.48670e-3` for Y2; B/X/Z are `4.30191e-7`, `4.97713e-7`, and `4.31983e-7`. Both modes are marked non-propagating and not power-carrying; their reported R/T are zero. They remain in the requested all-612 amplitude comparison.

The Y-to-Y2 difference decomposition below uses Y as the L2 reference and reports each subset's squared contribution to the full 612-mode delta. `Propagating` and `power-carrying` overlap; the latter includes lossy non-propagating modes.

| Amplitude | Group | Count | Reference L2 | Y2 L2 | Delta L2 | Share of all-612 delta squared |
|---|---|---:|---:|---:|---:|---:|
| Boundary | All 612 | 612 | 0.5296409472 | 0.5296440257 | 2.1029015e-3 | 1 |
| Boundary | Propagating | 166 | 0.5013245850 | 0.5013233580 | 9.1457092e-6 | 1.89146e-5 |
| Boundary | Power-carrying | 390 | 0.5296395937 | 0.5296384998 | 9.1536160e-6 | 1.89473e-5 |
| Boundary | Not propagating (stored flag) | 446 | 0.1708601576 | 0.1708733000 | 2.1028816e-3 | 0.99998109 |
| Boundary | Not power-carrying | 222 | 0.0011974034 | 0.0024193913 | 2.1028815e-3 | 0.99998105 |
| Raw outgoing coefficient | All 612 | 612 | 1.8635951e22 | 4.9911021e25 | 4.9918099e25 | 1 |
| Raw outgoing coefficient | Propagating | 166 | 0.5013246257 | 0.5013233988 | 9.2323918e-6 | 3.42068e-62 |
| Raw outgoing coefficient | Power-carrying | 390 | 0.5472130988 | 0.5471318712 | 9.1606351e-3 | 3.36771e-56 |
| Raw outgoing coefficient | Not propagating (stored flag) | 446 | 1.8635951e22 | 4.9911021e25 | 4.9918099e25 | 1.00000000 |
| Raw outgoing coefficient | Not power-carrying | 222 | 1.8635951e22 | 4.9911021e25 | 4.9918099e25 | 1.00000000 |

The top ±4 pair accounts for `99.9918%` of the boundary-amplitude delta squared and `99.9381%` of the raw-coefficient delta squared. This rules out an artifact-level key/order or raw-to-boundary phase-conversion mismatch in the saved outputs. The anomaly is present in the Y2 finite-rectangle evanescent port solution; its numerical cause is still unresolved. The existing fields are sampled away from the top plane and do not validate this evanescent amplitude independently. No physical accuracy or convergence claim follows from this audit.

The bounded diagnostic is reproducible with [diagnose_d13_y_y2_modal_amplitudes.py](analysis/diagnose_d13_y_y2_modal_amplitudes.py); its bound inputs, SHA-256 values, and full subset norms are in [d13_y_y2_modal_amplitude_diagnostic.json](records/d13_y_y2_modal_amplitude_diagnostic.json). It does not close the canonical sidewall trace gate.
