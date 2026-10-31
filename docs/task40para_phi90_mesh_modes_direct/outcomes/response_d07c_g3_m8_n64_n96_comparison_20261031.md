# D07C G3 M8/N64 → N96 saved-output comparison

## Scope and identity

This is an offline comparison of the two completed, independent p6-direct runs on the same D07C G3 mesh. It reads the saved direct summaries, modal-order JSON files, sample metadata, and the two small reference-sample NPZ archives. It does not read either VTU or resource stream and creates no mesh, carrier, matrix, factor, or FE solve.

| | N64 reference | N96 candidate |
|---|---|---|
| Run | `20261030T132407.592584Z` | `20261030T234947.703061Z` |
| Source | `3a0676dd47c7729fa279d74b114aaf2125ec8072` | `d99aa7e1424d29b20d2e39bea6d27aadc9842efa` |
| Input SHA-256 | `70d60efef816b44831e8a22f63c4d587748221a295ad20ea68686472e58b7ef5` | `bb2d9300568d68b1959370a899d85bcad2a94ec0c6dcd46f31eed048327aaba6` |
| Physical model SHA-256 | `8614e125acda5e11c6c00ef4152e944cd3af09a14760e1d4338f4e1bf87b0631` | same |
| Resolved config SHA-256 | `f44208b0825729fc13b2113fe18d1a054305e0e753aa1e35621e706e113474f4` | `49368696418a6e6a52ced944bfb8006aebf869b6ecbb5fa5468cd9baa0d9940f` |
| Mesh | 4,800 cells, axes `[6,100,8]`, tags air/substrate/grating `3280/1200/320` | same; x/y/z axis hashes exactly equal |
| Modes | `m=-8…8, n=-64…1`, 4,488 signed keys | `m=-8…8, n=-96…1`, 6,664 signed keys |
| Integration / cutoff | surface q81; volume q15/default; `scale_homogeneous_relative_only_v1`, `1e-13` | same |

The source and input hashes differ because the finite mode rectangle changed. Both manifests identify the same physical model. The N64 signed keys were verified as a subset of N96; on every common key, beta, kz, boundary phase, medium, direction, propagation state, and power-carrying state match exactly. No FE object or factor was shared between runs.

## Three comparison groups

| Quantity | N64 | N96 | Absolute difference | Limit | Result |
|---|---:|---:|---:|---:|---|
| `R_total` | 0.13879755144146974 | 0.13879755144180536 | 3.3562042034e-13 | 1e-5 | PASS |
| `T_total` | 0.7157083399204539 | 0.7157083399202182 | 2.3570034813e-13 | 1e-5 | PASS |
| `A_balance` | 0.14549410863807632 | 0.14549410863797640 | 9.9920072216e-14 | 1e-5 | PASS |
| `A_volume_total` | 0.14549410858587863 | 0.14549410858572230 | 1.5634715744e-13 | 1e-5 | PASS |
| `R00_s` | 0.056809125802967486 | 0.05680912580269590 | 2.7158830740e-13 | per-channel 1e-6 | PASS |

### Signed-channel powers

N64 contains 4,488 channels (4,360 propagating; 4,426 power-carrying). N96 contains 6,664 (6,536 propagating; 6,602 power-carrying). Its 2,176 additional keys are `m=-8…8, n=-96…-65` on top and bottom, both polarizations; all 2,176 are propagating and power-carrying.

| Compared set | Max `|ΔR|` and key | Max `|ΔT|` and key | 1e-6 result |
|---|---|---|---|
| All 6,664 N96 keys, with explicit mathematical zero extension for N64-missing keys | 2.71588307399e-13 at `(top, m=0, n=0, s)` | 7.29305504876e-13 at `(bottom, m=0, n=0, s)` | PASS |
| 6,602 N96 power-carrying keys, same extension convention | 2.71588307399e-13 at `(top, 0, 0, s)` | 7.29305504876e-13 at `(bottom, 0, 0, s)` | PASS |
| 6,536 N96 propagating keys, reported separately | same R maximum | same T maximum | PASS |
| 2,176 N96-only keys, compared against zero for a truncation diagnostic | 9.84580007880e-15 at `(top, 0, -66, s)` | 1.23865714451e-14 at `(bottom, 0, -66, s)` | diagnostic only |

N64 has no measured amplitudes or powers for its 2,176 missing keys. The full-N96-set numbers above use a mathematical zero extension solely to quantify the effect of the truncation; they do not relabel missing N64 measurements as observed zeros. Common-key comparison is directly measured and gives the same maxima as the all-key result.

The outgoing complex amplitude at each boundary plane, without phase fitting, has reference-norm-relative L2 difference `9.73725240208e-8` across all N96 keys under the same explicit zero-extension convention (limit `1e-4`, PASS). On the 4,488 measured common keys alone the relative L2 difference is `2.08709962018e-12`. The 2,176 added amplitudes have absolute L2 norm `1.25500822700e-7`; their N64 values are absent, so no relative error is assigned to that added-only subset.

### Same-coordinate field samples

All x/y/z and interface coordinate arrays are exactly equal. The saved sample grid has 40 x-points, 64 y-points, and z-planes `10, 30, 60, 90, 110 nm`; E/H are complex samples in the stated V/m and A/m units. Relative L2 uses the N64 sample norm, with no phase fit.

| Saved samples | Relative L2 difference | Limit | Result |
|---|---:|---:|---|
| Complex E, all saved points/components | 8.46181413742e-11 | 1e-4 | PASS |
| Complex H, all saved points/components | 2.17043028917e-11 | 1e-4 | PASS |
| `E_t` on saved horizontal interface planes | 9.42231356673e-11 | diagnostic | — |
| `H_t` on saved horizontal interface planes | 3.43541924540e-11 | diagnostic | — |

`E_t/H_t` are horizontal z-plane interface diagnostics at z=10 and 110 nm. They do not measure the canonical grating sidewall trace; that remains `NOT_MEASURED`.

All three finite N64→N96 comparison groups pass these saved-output thresholds. This is not a full-DtN result: the automatic propagating inventory is 64,120 modes and N96 contains only 6,536 of those, leaving 57,584 propagating modes outside this rectangle. `FULL_DTN_NOT_VERIFIED` remains. The N64 and N96 single-run finite-active-rectangle gates passed; N96 condensed residual was `6.606524227998438e-12`, independent original-A6 active-rectangle residual `3.655082643014393e-9`, and signed port-volume energy closure `-5.2254089943915005e-11`.

N96 elapsed time was 28,992.45 s. Sampled simultaneous process-tree RSS peak was 486,263,476,224 B; sampled task swap peak was zero. There was one host-level `pswpin` page in the observe-only interval with no task attribution. This is an observed resource record for N96, not a capacity guarantee or a scaling estimate from N64.

## Reproduction and evidence

- [Offline comparison script](records/compare_d07c_g3_m8_n64_n96_saved_outputs_v1.py)
- [Machine-readable comparison](records/d07c_g3_m8_n64_n96_saved_output_comparison_v1.json), SHA-256 `03c07e8b829405e90fa582dd5cfdb01c7b35a0b8945778720c41e3ffd74e5a3d`
- Input-file hashes, sample identities, run identities, exact per-mode maxima, and per-plane field differences are in that JSON.
- The script reads only the two direct summaries, the two modal-order JSON files, sample metadata, and the two small reference-sample NPZ files. No VTU or resource stream was read for this comparison.

The comparison script accepts `TASK40_D07C_RESULTS_ROOT` and
`TASK40_D07C_COMPARISON_OUTCOMES` so this evidence can be reproduced from a
separate Task40 worktree without copying run directories. The copied script
was adjusted only for these path overrides; the numerical comparison was not
rerun during G5 preparation.
