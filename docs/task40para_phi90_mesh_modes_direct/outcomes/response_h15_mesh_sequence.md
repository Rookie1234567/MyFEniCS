# H15 四场网格序列与 X2/Y2 同策略对照

状态：H15-B/X/Y/Z 四场均已完成，四场各自通过直接求解的凝聚残差、独立 A6 与能量门并自然清场。保存场的有限 R13 对比已完成。该结果不代表 full-DtN、canonical 方柱侧壁或更粗网格已获验证。

## X2 与 Y2

X2 已自然结束并通过其单场原数值门。与同为 relative-only policy 的 Y2 离线比较使用已保存的 612 模态复幅值、R/T、样本场和小型 summary；没有重跑 FE、factor、读取大 VTU 或重扫资源流。比较脚本、JSON 和逐模 CSV 见本目录 `analysis/compare_d13_same_policy_y2_x2.py`、`records/d13_y2_x2_same_policy_comparison_v1.json` 与 `records/d13_y2_x2_same_policy_all_612_modes_v1.csv`。

X2/Y2 的总 R、R00,s、总 T、A_balance、A_volume 差分别为 `-2.4442e-8`、`-2.4439e-8`、`-1.5891e-9`、`+2.6031e-8`、`+2.6037e-8`。612 个物理边界 outgoing 复幅值相对 L2 差为 `5.8143e-8`，最大逐模绝对差 `2.9526e-8`，位于 top `(m=0,n=0,s)`。共同坐标已保存样本场的 E/H/Et/Ht 相对 L2 差依次为 `4.091e-6 / 5.366e-7 / 3.988e-6 / 1.587e-6`。X2 与 Y2 只有 x 轴不同，source SHA 不同；两者仍是相同模式、积分与 relative-only 算子合同下的比较。倏逝模 raw outgoing 系数受指数尺度影响，不能与 boundary phase 缩放后的物理边界幅值混为一谈。此比较只覆盖有限 R13 模态及已保存采样，不证明 full DtN 或 canonical 方柱侧壁迹。

X2 终态 `run_summary.json` 报告 `finished/exit0/descendants_cleared`，elapsed `20980.17355 s`，任务树 peak RSS `308907405312 B`，swap peak `0 B`。runtime 最低 available-memory 没有保存的聚合值，记为 `UNKNOWN_NOT_AGGREGATED`。`2126305861632 B` 是 launch envelope 的启动准入快照，`68719476736 B` 是 host-floor 门槛；二者都不是运行期最小值。既有样本曾约 `1.85 TB`，但不把该单个样本提升为最低值，也不为此重扫 resources。

## H15 四场合同

H15 是候选较粗基准，不预先宣称精度充分。四场顺序运行、每次只一个重计算：

| 场 | 网格 cells | 轴变化 | cells 总数 | 材料段单元数 x/y/z |
|---|---:|---|---:|---|
| H15-B | `[6,4,10]` | 实际 boundary-fitted H15 基准轴 | 240 | `[2,2,2] / [1,2,1] / [1,8,1]` |
| H15-X | `[12,4,10]` | 只将 B 的每个 x 区间二分 | 480 | `[4,4,4] / [1,2,1] / [1,8,1]` |
| H15-Y | `[6,8,10]` | 只将 B 的每个 y 区间二分 | 480 | `[2,2,2] / [2,4,2] / [1,8,1]` |
| H15-Z | `[6,4,20]` | 只将 B 的每个 z 区间二分 | 480 | `[2,2,2] / [1,2,1] / [2,16,2]` |

按柱体实际 x/y 覆盖区间与 z 材料区间的单元中点分类，H15-B 的 air/substrate/grating 标签数为 `184/24/32`；H15-X/Y/Z 均为 `368/48/64`。这些是轴计划上的独立几何计数期望，正式场仍须由 live mesh QA 再核。

四场保持同一 Si 几何、材料、入射、边界、p6 精确局部凝聚直接法、612 个 R13 有限矩形模态、surface q28、volume q15/default、relative-only `1e-13` 稀疏提取、原凝聚/A6/能量门和最多两次同因子校正。每个细化只从 B 的实际坐标逐区间二分，另两轴 SHA 必须逐位相同。四个 `.dat` 的 input/physical/resolved SHA、轴 hash、plan SHA 和细节见 `records/h15_mesh_sequence_contract_v1.json`。正式 setup 仍需检查实际 mesh/tag/mode 身份；静态轴计划不冒充 live mesh QA。

本轮完整场总上限按用户补充为 13：之前已完成 8 场、D13-X2 1 场、H15 B/X/Y/Z 4 场。此补充只解释新方向的总数上限，不覆盖早期文档中的历史预算或更改其历史记录。完成 H15 后，评估 z 粗化仅使用 B 与 Z 的全模式、复 E/H、逐级功率、R/T/A/A_volume 和原数值门；两级接近只说明当前两个离散接近，不证明更粗网格充分。第 14 场未获授权，不自动启动。5 nm 与 0.7 nm 目前只做固定 cell 预算的非均匀网格静态设计，不启动额外 FE，也不把相位缩放的大网格当启动方案。

H15 每场启动前独立执行真实 fresh/host-floor/共享 heavy-lock/邻任务/重复进程/ABI/磁盘准入。保持 parent CPU9、worker CPU24、MPI1、math threads1、NUMA interleave 0-1、PSS/USS off、无固定 RSS cap、swap observe-only；数值预测不能替代实测。不得跨网格复用 FE 向量或 factor。

## H15 实际场与门值

四场的实际 mesh QA 均为 `PASS`；实际 cell 数、材料标签计数、单轴变化和轴 SHA 已写入 B/X/Y/Z JSON。实际标签计数按 air/substrate/grating 顺序分别为 B `184/24/32`、X/Y/Z `368/48/64`。四场均为 612 个相同 R13 模态，mode SHA `1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e`，surface quadrature degree 28，volume q15/default。

| 场 | 实际 cells | R | T | A_balance | A_volume | 凝聚相对残差 | 独立 A6 相对残差 | 校正数 | elapsed | tree peak RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B | 240 | 0.5852627902940796 | 0.020494519842751743 | 0.3942426898631687 | 0.3942426898600285 | 1.5918324e-10 | 9.1661571e-11 | 0 | 1046.877 s | 8,331,128,832 B |
| X | 480 | 0.5852627848047772 | 0.02049451984382492 | 0.39424269535139783 | 0.3942426953513483 | 1.1982759e-10 | 2.0686148e-11 | 0 | 1094.716 s | 16,253,333,504 B |
| Y | 480 | 0.25154338910740764 | 0.057102436170780035 | 0.6913541747218123 | 0.6913541747191441 | 5.0608100e-12 | 4.2857750e-11 | 1 | 1206.266 s | 19,863,633,920 B |
| Z | 480 | 0.5852599783496771 | 0.020494706485963212 | 0.3942453151643597 | 0.3942453151624836 | 2.0845281e-10 | 1.2888734e-10 | 0 | 1060.228 s | 14,838,960,128 B |

All four workflow gates passed with condensed residual `<=1e-9`, independent A6 `<=1e-6`, energy closure `<=1e-5`, and no more than two same-factor corrections. The reported `FULL_DTN_NOT_VERIFIED` status remains. These solver gates establish each run's solve consistency; they do not establish mesh convergence.

## Saved-field and all-mode comparison

The reproducible comparison is [compare_h15_bxyz_final.py](analysis/compare_h15_bxyz_final.py). It reads each run's small manifest/stage/summary records, 612-mode JSON, and saved sample NPZ only. It does not read the VTU files, build a mesh, or rerun FE. The JSON and all-612-mode CSV are [h15_bxyz_saved_output_comparison_v1.json](records/h15_bxyz_saved_output_comparison_v1.json) and [h15_bxyz_all_612_modes_v1.csv](records/h15_bxyz_all_612_modes_v1.csv). The CSV aligns exact `(side,m,n,polarization)` keys and records every mode's boundary-scaled complex outgoing amplitude and per-mode R/T. No phase fitting was used.

Relative complex-amplitude L2 differences below are measured against B and are grouped over the indicated exact modal sets. Raw outgoing coefficients are also retained separately; for Z their all-mode relative difference is 0.931 because evanescent coefficients carry reference-plane exponential scaling, so that number is not a physical boundary-amplitude comparison.

| Comparison | all 612 boundary amplitudes | propagating | power-carrying | evanescent | ΔR | ΔR00,s | ΔT | ΔA_balance | ΔA_volume |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B→X | 4.8221e-9 | 4.7214e-9 | 4.8139e-9 | 8.7636e-9 | -5.4893e-9 | -5.4883e-9 | +1.0732e-12 | +5.4882e-9 | +5.4913e-9 |
| B→Y | 0.45446 | 0.44347 | 0.45440 | 0.86980 | -0.333719 | -0.333719 | +0.0366079 | +0.297111 | +0.297111 |
| B→Z | 1.9860e-5 | 6.7229e-6 | 6.9567e-6 | 1.4089e-4 | -2.8119e-6 | -2.8106e-6 | +1.8664e-7 | +2.6253e-6 | +2.6253e-6 |

The sampled E/H arrays have common stored coordinates (40 x, 64 y, and 5 z locations); values were compared directly without interpolation. E/H relative L2 differences were B→X `2.3385e-6 / 5.0801e-7`, B→Y `0.52298 / 0.52218`, and B→Z `6.7870e-6 / 1.7937e-5`. Saved Et/Ht arrays are horizontal traces at z=10 and 110 nm, not pillar sidewalls: their relative L2 differences were B→X `2.3370e-6 / 2.5044e-6`, B→Y `0.45033 / 0.30138`, and B→Z `6.0331e-6 / 1.5046e-4`. Component-wise relative errors for some small-field components are denominator-sensitive; the JSON also records absolute L2 and maximum absolute differences and their sample locations. Canonical sidewall traces remain `NOT_MEASURED`.

These data show strong sensitivity to the H15 y resolution in the sampled quantities. X refinement barely changes B's results. Z refinement is much closer to B than Y is, but the all-mode evanescent boundary difference and horizontal Ht difference remain measurable. Similar R/T/A or energy closure alone is not a sufficiency proof for a coarser z grid.

### Apply the Task 40 comparison limits

The task comparison limits are absolute `1e-5` for global R/T/A_balance/A_volume, absolute `1e-6` for each propagating-mode R/T, and relative L2 `1e-4` for all-mode boundary complex amplitudes and same-coordinate E/H/interface traces. On these limits, B→X stays within the reported global, all-mode, per-propagating-power, E/H, Et, and Ht comparisons. B→Y fails those output comparisons by large margins. B→Z has global R/T/A_balance/A_volume differences below `1e-5`, all-mode boundary amplitude below `1e-4`, and E/H/Et below `1e-4`; however, the `R00,s` power difference is `2.8105512937e-6` and therefore exceeds the per-propagating-mode `1e-6` limit, and horizontal Ht is `1.50456981e-4`, above the saved-trace `1e-4` limit. Thus B→Z is not an all-output comparison pass. The Ht check is only on horizontal z-plane traces and does not close the canonical sidewall gate.

### H15-Y against the saved D13-Y2/Y3 references

The corrected offline comparison is reproducible with [compare_h15_y_to_d13_y2_y3_relative_only_v2.py](analysis/compare_h15_y_to_d13_y2_y3_relative_only_v2.py); its new JSON and per-mode CSV are [h15_y_vs_d13_y2_y3_same_relative_only_saved_output_comparison_v2.json](records/h15_y_vs_d13_y2_y3_same_relative_only_saved_output_comparison_v2.json) and [h15_y_vs_d13_y2_y3_same_relative_only_all_612_modes_v2.csv](records/h15_y_vs_d13_y2_y3_same_relative_only_all_612_modes_v2.csv). The comparison binds H15-Y to D13-Y2 run `20261016T190312.893443Z` and the corrected same-policy D13-Y3 run `20261016T202834.284773Z` (source `8faf8094e5309e7e7c0f0a094276cbacb31c1a00`, resolved `9bcdc23e93b6901b4147e2bf235c8b6c986d00c7a069a43c2ae7d834d1903224`). Y3's run manifest, summary, and direct-factor evidence hashes are recorded in the new JSON. All three use `scale_homogeneous_relative_only_v1`, 612 modes with SHA `1987a2b3…7e522e`, surface q28, volume q15/default, and identical saved sample coordinates. The saved-output comparison reads small identity/output JSON and the existing sample NPZs; it does not read VTU or resources, build/assemble/factor/solve, interpolate fields, or phase-fit.

The older D13-Y3 run `20261016T122621.622353Z` (source `d742562e706b896cdb78da7fe8ba9c3dfd83f4b0`) used the legacy `absolute_floor_relative_v1` cutoff. It remains in the earlier comparison v1 artifacts and is marked in the corrected JSON as historical only; it is not the Y3 reference in this table. H15-Y and both D13 runs have matching geometry/material/incidence/boundary settings and mode/integration contracts, but H15-Y `[6,8,10]` versus D13-Y2 `[6,24,14]` and D13-Y3 `[6,48,14]` changes y and z discretization together. These cross-family comparisons cannot isolate error to y or z.

| Comparison against H15-Y | cutoff policy | ΔR | ΔR00,s | ΔT | ΔA_balance | ΔA_volume | all-612 boundary amplitude rel-L2 | max propagating ΔR / count over 1e-6 | max propagating ΔT / count over 1e-6 | E / H rel-L2 | horizontal Et / Ht rel-L2 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D13-Y2 `[6,24,14]` | relative-only | -1.8772580e-4 | -1.8772557e-4 | +2.6387963e-5 | +1.6133784e-4 | +1.6133787e-4 | 4.15038e-4 | 1.87726e-4 / 1 (**FAIL**) | 1.931e-9 / 0 (**PASS**) | 2.77372e-4 / 6.03233e-4 | 2.54583e-4 / 3.30877e-4 |
| D13-Y3 `[6,48,14]` | relative-only | -1.8772667e-4 | -1.8772644e-4 | +2.6388059e-5 | +1.6133861e-4 | +1.6133856e-4 | 4.15039e-4 | 1.87726e-4 / 1 (**FAIL**) | 1.931e-9 / 0 (**PASS**) | 2.77372e-4 / 6.03236e-4 | 2.54584e-4 / 3.30880e-4 |

Against the task limits, both same-policy rows fail global R/T/A differences, `R00,s`, all-mode complex amplitude, E/H and horizontal Et/Ht; propagating-mode R fails for the top `(m=0,n=0,s)` order, while all propagating-mode T differences pass. The individual runs passed their own residual/energy solve checks, but that does not pass cross-mesh output gates. These comparisons reinforce that H15-B/Y is not an adequate result for the requested output tolerance. The older cutoff-mismatched Y3 comparison remains preserved as history and does not change the corrected result.

The comparison should guide a fixed-cell-budget design toward more y resolution while retaining z resolution supported by the B/Z evidence and material/port planes. It does not justify reducing z below the tested B level. No new candidate axes have been promoted to a run, and no field beyond the existing 13-run budget is authorized.

For the measured H15 cross section, x needs at least six intervals to retain the frozen material/sidewall breakpoints. At a 480-cell budget, retaining the D13-Y2 z count of 14 would leave at most `floor(480/(6*14)) = 5` y cells, below H15-Y's eight; therefore a 480-cell redistribution cannot both retain z14 and refine y beyond H15-Y without changing x geometry coverage. The existing same-policy D13-Y2 `[6,24,14]` is a 2016-cell best-available reference, but its H15-Y comparison changes y and z together and fails the output limits. A balanced future budget must be specified explicitly; no untested axis allocation is being presented as accurate.

## Static z-coarsening candidate — not run

For a bounded follow-up candidate only, keep B's x and y axes unchanged and retain all z material/port planes `[-10, 0, 120, 130]` nm. A possible coarser z axis is `[-10, 0, 20, 40, 60, 80, 100, 120, 130]` nm: one 10-nm cell in each exterior interval and six 20-nm cells through the grating region. This would be 8 z cells and 192 total cells instead of B's 10 z cells/240 cells, while preserving the material interfaces and port planes. Its largest step is 20 nm (`k0*dz ≈ 9.31 rad` at 13.5 nm); the aspect ratio and high phase advance make it an unverified, deliberately cautious experiment candidate, not a recommendation that accuracy is adequate. It must pass the same mesh/tag, mode, quadrature, solver, and field-comparison checks if ever authorized. No additional field is authorized by the existing 13-field cap, which is already consumed by the prior eight fields, X2, and H15 B/X/Y/Z. This candidate remains `PLAN_ONLY` pending budget coordination.
