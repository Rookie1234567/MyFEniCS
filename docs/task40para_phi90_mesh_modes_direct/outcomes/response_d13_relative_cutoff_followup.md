# D13 relative-only Y2 离线收口回应

> 历史快照：本文记录 relative-only Y2 完成时的阶段状态；当时建议的同策略 Y3 已在后续获准并完成，当前对照与累计资源以 [Y2/Y3 同策略 response](response_d13_y2_y3_same_relative_only.md) 和 [outcomes summary](summary.md) 为准。

本回应补充此前 D13 的 Y/Y2/Y3 比较，并记录同一 Y2 网格上将端口稀疏项筛选改为尺度齐次 relative-only 后的完整 direct 场。这里的“尺度齐次”指筛选只按本次投影量相对最大值判断，不再使用固定 `1e-30` 绝对 floor。它修正的是端口稀疏提取的尺度问题，不改变材料、网格、R13 模态、q28 表面积分或 p6 凝聚直接求解。旧 run、旧 raw audit 和原 V4/V5 FAIL 均原样保留。

## 本轮范围和结果

新 Y2 使用 `[6,24,14]`、2016 cells、612 个 R13 模态，input SHA `7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994`、physical SHA `ac65772c3fda31f22599824023f43e05e62b8292de31652dff226909fc83fa7b`，source `73e2fd2c4a36c9698298235148c59aa1551d74d6`。它与旧 Y2 的 input、physical、三轴网格、612-mode SHA、积分规则相同；source、resolved identity 和 cutoff policy 不同。旧 Y2/Y/Y3 的 source 分别为 `74d5aae3dea064e128e53a253fc5aac0f2b1f146`、`9c0fe6a30554aab33a04ff0245b19c03e4f01f28`、`d742562e706b896cdb78da7fe8ba9c3dfd83f4b0`；这三版实际代码都用 `max(1e-30, 1e-13 × global_maximum)`。新场使用 `scale_homogeneous_relative_only_v1`，相对容差仍为 `1e-13`。

| 新 Y2 检查 | 实测值 | 原门槛 / 状态 |
|---|---:|---|
| 凝聚残差 | `3.0670174445033676e-12` | `< 1e-9`，通过 |
| 恢复场 active-rectangle A6 | `3.0741646629478677e-10` | `< 1e-6`，通过 |
| 同因子校正次数 | `1` | 原合同内 |
| R / T / A_volume | `0.2513556633066366 / 0.05712882413359571 / 0.69151551258949` | 有限 R13 模型结果 |
| 能量闭合绝对差 | `2.972233570375238e-11` | 有限端口闭合；非完整 DtN 证明 |

状态为 `COMPLETED_AUTHORITY_LIMITED`，不是 full-DtN 或连续解资格。旧 Y2 的 R/T/A_volume 为 `0.2513557152507698 / 0.05712882739311799 / 0.6915156826412944`；新旧差分别为 `5.19441331614523e-8 / 3.259522277088145e-9 / 1.700518044156496e-7`。

同网格旧→新 Y2 的 612 个 boundary outgoing 复振幅相对 L2 差为 `3.97053469222378e-3`，最大单模差 `1.4869633826261881e-3` 位于 top `(m=+4,n=0,p)`。all-612 和 power-carrying 子集的逐模 R/T 都保存在 CSV；新旧 Y2 最大逐模功率变化为 R `9.332766853775709e-8`、T `1.879194586051902e-8`，两者均未超过 `1e-6`。612 项中 166 个被标为 propagating、390 个为 power-carrying、446 个为 nonpropagating；这些集合并不互斥，有损介质中的倏逝级也可能携带净功率。

新 Y2 的 retained modal alpha 是增广解末尾的 612 个 modal unknown；`recover_aux` 是 P6 全场恢复后重新计算的 total projection。逐模乘同一 boundary phase `P` 后，两者的 612 项差 L2 为 `1.9337032827278037e-15`，相对 alpha 为 `1.739044475e-15`。top `(m=−4/+4,n=0,p)` 的 boundary 幅值为 `4.911763694969092e-7 / 4.911763247569474e-7`；主控另以独立 full-primal 同单位量核得差 `5.122126747848201e-16 / 6.260306451231583e-16`。六个取证 key 最大同单位差为 `6.256774122628426e-15`。native port residual observation 为 `5.211741736308671e-16`。这些是限定 key 的一致性见证，不是所有 612 个端口方程的完整独立残差。

旧场保存的 raw six-key projection audit 仍是 `false`，包括原阈值与原数值；不得用新 boundary 单位结果覆盖它，也不将 legacy 布尔值改写为 PASS。raw modal coefficients受逐模 `P` 的倏逝指数尺度影响，不能直接把巨大的 raw 差当物理边界误差；报告同时保留 raw coefficient、`P` 和 phase-scaled boundary amplitude。

## Y 网格、全模态功率和复场对照

四场使用相同 ordered 612 mode keys、beta、boundary phase、q28 surface 与 q15/default volume rule。场样本是在逐位相同坐标上的已保存 complex E/H，未拟合整体相位、未插值。完整复数振幅与每模 R/T（含 all-612、propagating、power-carrying、nonpropagating 分类）位于[612-mode CSV](records/d13_y_y2_y3_relative_cutoff_all_612_modes_v1.csv)，六组 pairwise 汇总、identity 和 artifact hashes 位于[比较 JSON](records/d13_y_y2_y3_relative_cutoff_comparison_v1.json)。

| 比较 | 改动范围 | 全 612 boundary outgoing 振幅相对 L2 | 最大逐模 R / T 绝对差 | E / H / 水平面 Ht 相对 L2 |
|---|---|---:|---|---|
| Y → Y2 legacy | 只细化 y，同 legacy cutoff | `3.9704e-3` | `1.2371e-6` / `1.3986e-7` | `1.1561e-5 / 3.9563e-5 / 1.8423e-4` |
| Y2 legacy → Y3 legacy | 只细化 y，同 legacy cutoff | `3.9705e-3` | `9.2467e-8` / `1.8888e-8` | `9.8907e-6 / 9.8892e-6 / 1.8411e-4` |
| Y → Y3 legacy | 只细化 y，同 legacy cutoff | `2.5747e-6` | `1.1447e-6` / `1.5875e-7` | `5.9757e-6 / 3.8353e-5 / 6.2069e-6` |
| Y2 legacy → Y2 relative-only | 同网格，cutoff/source 改变 | `3.9705e-3` | `9.3328e-8` / `1.8792e-8` | `9.8868e-6 / 9.8720e-6 / 1.8411e-4` |
| Y → Y2 relative-only | 网格和 cutoff/source 都改变，混合比较 | `2.6009e-6` | `1.1438e-6` / `1.5865e-7` | `5.9855e-6 / 3.8308e-5 / 6.2518e-6` |
| Y3 legacy → Y2 relative-only | 网格和 cutoff/source 都改变，混合比较 | `9.2916e-7` | `8.6082e-10` / `9.6151e-11` | `2.8364e-7 / 5.8524e-7 / 1.2858e-7` |

Y/Y2/Y3 的 legacy 网格比较显示 Y2 的 612 模态边界幅值 outlier；同网格 relative-only 场显著改变这个保存输出，但这不是同 cutoff 的网格收敛比较。跨 source/policy 的混合行只作数值观察，不证明单独网格方向趋势。水平 Ht 数组来自 `z=10/110 nm` 平面，不是方柱侧壁切向 trace；canonical sidewall gate 仍 `NOT_MEASURED`。

## 证据读取与资源总账

最终分析使用四个小 sample NPZ、模态 JSON、direct summary 和新 Y2 retained alpha。写出期间两次分析尝试在产物写入阶段失败，最终导出又读取了样本；因此这四个 NPZ 和小 alpha 在本轮各经历三次读取尝试，本回应不宣称严格只读一次。未读 104 MB VTU、未重扫 `resources.jsonl`，且未读取更大的 recovered-storage coefficient 文件。新 Y2 先前已完成的一次 terminal resource-stream 审计见[终态回执](../../../../tmp/task40_d13_y2_scale_homogeneous_launch_v1/terminal_receipt_20261017.json)。该回执位于 ignored `tmp/`，远端读者可能无法访问；tracked compact 事实见 [Y2/Y3 同策略比较 JSON](records/d13_y2_y3_same_relative_only_comparison_v1.json)。

截至本文快照，七个成功 D13 direct 场的 workflow 墙钟累计 `15,852.480275410926 s`（`4.403466743 h`），这是分场墙钟相加；不是 CPU 时间。最大单场 RSS 是当时的 legacy Y3 `166,464,983,040 B`，RSS 不跨 run 相加。后续 relative-only Y3 已加入总账，最新累计见 [outcomes summary](summary.md)。不包含 setup 失败、offline analysis、saved-field diagnostics 的成本。

## 保留项和下一步

- 原 V4/V5 saved-field max-facet Gate `FAIL/OPEN` 保留；新 Y2 的局部 projection / active-rectangle 残差不改写历史失败。
- `FULL_DTN_NOT_VERIFIED`、`AUTHORITY_LIMITED` 保持；不把有限 R13 端口输出称为完整 DtN 或连续解 qualification。
- canonical pillar sidewall trace 为 `NOT_MEASURED`；水平采样面的 Ht 不能替代它。
- D5/M5、Y4、额外 FE/factor 未运行。
- 当时唯一建议的下一项是已有 `[6,48,14]` Y3 网格上的 relative-only 重算；该项已获后续授权并完成，当前结果见[同策略 Y2/Y3 response](response_d13_y2_y3_same_relative_only.md)。本文件其余数据保留为当时的阶段快照，不自动授权 Y4、D5 或模式扩展。

分析脚本、逐模 CSV 和 provenance-rich JSON 均列于[outcomes summary](summary.md)末尾；本轮无源码改动、无新测试、无新 FE。
