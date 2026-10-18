# D13-Y2 与 Z2 同策略对照

状态：Y2 与 Z2 两场均为 `worker_exit0`，独立 p6 直接求解/残差/能量门通过；本报告只评估同策略有限 R13 算子的 z 方向敏感性。两场都保持 `AUTHORITY_LIMITED` 和 `FULL_DTN_NOT_VERIFIED`。

## 两场身份

| 项 | Y2 | Z2 |
|---|---|---|
| run | `20261016T190312.893443Z` | `20261018T040538.010965Z` |
| source | `73e2fd2c4a36c9698298235148c59aa1551d74d6` | `2aa5558f7c1472df3d3ac6161244e689a959da73` |
| input SHA256 | `7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994` | `32eae0338865ad3784bc9d835b5fb21ca27ea525529e12be0688317b49048309` |
| physical SHA256 | `ac65772c3fda31f22599824023f43e05e62b8292de31652dff226909fc83fa7` | `30d1d0525b5c477cabd1ce3dbd9b20cead50e07113caeefcbad9ec31c3cf5e24` |
| resolved SHA256 | `69d1e4fc40ca9e726ec0b7163217d72fc22b61022ee1a6c92235d05aa0982246` | `c674f9f256b5d24cf60cf8aa9dca8a5d8b842dd23532da68bfd778a09e955084` |
| axes / cells | `[6,24,14]` / 2016 | `[6,24,28]` / 4032 |
| modes | 612, SHA `1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e` | same 612-mode SHA |
| integration / sparse policy | surface q28; volume q15/default; `scale_homogeneous_relative_only_v1`, tolerance `1e-13` | same |

The x/y coordinates and hashes are identical; z alone is bisected. The source SHA differs because the Z2 profile/axis-plan implementation was added. Material values, incidence and mode identities match. This is not a source-SHA-equal comparison.

## Solve checks and global observables

| Quantity | Y2 | Z2 | Absolute difference | Target |
|---|---:|---:|---:|---:|
| condensed residual | `3.0670174445e-12` | `5.4146636871e-12` | — | `<=1e-9`, both pass |
| independent active-rectangle A6 | `3.0741646629e-10` | `2.4319108124e-10` | — | `<=1e-6`, both pass |
| same-factor correction solves | 1 | 1 | — | at most 2, both pass |
| R total | `0.2513556633066366` | `0.2513556504760401` | `1.2830596530e-8` | `<=1e-5`, pass |
| T total | `0.05712882413359571` | `0.05712882339023834` | `7.4335737565e-10` | `<=1e-5`, pass |
| A balance | `0.6915155125597676` | `0.6915155261337216` | `1.3573953961e-8` | `<=1e-5`, pass |
| A volume | `0.69151551258949` | `0.6915155260998864` | `1.3510396468e-8` | `<=1e-5`, pass |
| signed energy closure | `+2.9722224681e-11` | `-3.3835156898e-11` | — | `<=1e-5`, both pass |

Each run used one symbolic factor and one numeric factor on its own matrix, with one correction solve. The run matrices are not reused across meshes. `nz_used` / `nz_allocated` are `361,105,778 / 382,746,384` for Y2 and `697,240,342 / 716,523,408` for Z2.

## Modes and saved fields

The finite R13 inventories have the same ordered 612 keys, propagation branches, beta values and boundary phases. The formal complex-amplitude comparison uses outgoing amplitude at the shared physical boundary reference plane, with no phase fit: relative L2 difference `6.7429537071e-8` (`<=1e-4`, pass); maximum absolute difference `1.8352506969e-8` at bottom `(m=0,n=-4,s)`.

Raw outgoing coefficients and raw auxiliary projection coefficients are retained as diagnostics, not substituted for boundary amplitudes: their relative L2 differences are about `0.999784` because evanescent coefficients carry large exponential scaling. These do not define the boundary-amplitude gate.

| Mode group | Count | Max `|ΔR|` / key | Max `|ΔT|` / key |
|---|---:|---|---|
| All modes | 612 | `1.2844187436e-8`, top `(0,0,s)` | `7.6613842354e-10`, bottom `(0,0,s)` |
| Propagating | 166 | `1.2844187436e-8`, top `(0,0,s)` | `1.5930558452e-11`, bottom `(0,-4,s)` |
| Power carrying | 390 | `1.2844187436e-8`, top `(0,0,s)` | `7.6613842354e-10`, bottom `(0,0,s)` |

The per-propagating-mode `R/T <=1e-6` target passes. The all-mode and power-carrying summaries include lossy nonpropagating bottom modes and are kept separate from that formal propagating-mode gate.

On the identical saved sample coordinates, with no interpolation or phase fit, relative L2 differences are:

| Sample field | Relative L2 difference | `<=1e-4` sample target |
|---|---:|---|
| E | `1.8713666989e-6` | pass |
| H | `2.3670237465e-6` | pass |
| tangential E on sampled interface planes | `2.3887263319e-6` | pass |
| tangential H on sampled interface planes | `9.1225416710e-5` | pass, near the limit |

The Ht samples are horizontal z planes, not canonical grating sidewall traces. Canonical sidewall Et/Ht remains `NOT_MEASURED`; the saved sample norms are not full-domain L2 errors.

The composite E/H sample norms passing does not mean every Cartesian component is equally close. Component-relative diagnostics include `E_z=3.1109e-3`, `H_x=7.3868e-4`, `E_y=8.2612e-5`, and `H_y=9.2572e-5` on these saved sample points. These are diagnostic subcomponents (not separate formal Task40 gates); retain them when interpreting the near-field comparison.

## Resources and interpretation

Y2 elapsed `3610.503968 s`, sampled tree RSS peak `85,740,769,280 B`; Z2 elapsed `10057.095738 s`, sampled tree RSS peak `169,460,588,544 B`. Both task swap peaks are zero and PSS/USS sampling was disabled. Z2's global WSL `pswpin` delta is an unattributed observe-only host counter, not task swap.

The Y2-to-Z2 differences are small for the measured R13 outputs and saved fields, supporting low sensitivity between these two z resolutions on this mesh and sparse policy. This is not a continuum-convergence proof, does not certify the omitted DtN tail, and does not close the canonical sidewall check. Both terminal outputs remain authority-limited.

## Machine-readable record

- [Full comparison JSON](records/d13_y2_z2_same_relative_only_comparison_v1.json), SHA256 `343fbf19ecbb1588b50e7e60b268a016a0ff4e48c85ed50b6808e477d094d495`.
- [All 612 modes CSV](records/d13_y2_z2_same_relative_only_all_612_modes_v1.csv), SHA256 `1bb1a8f27d387d83c33f5382cbf873d7cf93ff94fb10ba4d355a56ce3510e89e`.
- [Reproducible offline comparison script](analysis/compare_d13_same_policy_y2_z2.py), SHA256 `1bb65d07926940ef60df7128f3ea1192ad636b10cb2567fd65d94b6cdba5834f`.

The offline script read the two compact mode/summary JSON sets and the two saved 1.3 MB sample archives once each. It did not read VTU files, resource streams, or large field artifacts, and did not run FE or a factorization.
