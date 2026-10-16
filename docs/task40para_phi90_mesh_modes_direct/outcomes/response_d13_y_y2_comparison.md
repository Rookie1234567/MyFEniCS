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
