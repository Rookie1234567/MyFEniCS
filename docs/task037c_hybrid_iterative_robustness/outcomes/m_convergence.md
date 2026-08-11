# Task037c M 收敛与统一 M 决策

## 冻结选择规则

任务书要求三个 phi 共享一个 M：先看每个 phi 的 M120-vs-M160，再看 M120/M160 各自与
Full3D 的比较；不得按方位角分别选 M，也不得自动进入 M200。

```math
M_{\mathrm{robust}}=
\begin{cases}
120, & \text{三个方位角的 M120 比较全部通过},\\
160, & \text{否则三个方位角的 M160--Full3D 比较全部通过},\\
\text{not established}, & \text{否则。}
\end{cases}
```

## 结果

| phi | M120 vs M160 | M120 vs Full3D | M160 vs Full3D | 解释 |
|---:|---|---|---|---|
| 0° | pass | pass | pass | 12/12显著通道；总量与 field Gate通过 |
| -5° | pass | fail | fail | 11个低功率显著通道超 `1e-4` relative |
| +5° | pass | fail | fail | 镜像通道同类失败，最大约`2.402e-3` |

`M120-vs-M160` 的非零 phi 最大通道 relative delta 约 `7.03e-7`（-5°）和 `7.37e-7`
（+5°），远低于 `1e-4`。因此 M160 已表现出与 M120 基本相同的 direct solution；把
失败解释为“只需加 M”没有证据支持。

selection carrier：

| 字段 | 值 |
|---|---|
| path | [`m_robust_selection_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/m_robust_selection_6555663.json>) |
| SHA256 | `2d7861cc44023fd27c4a082b14ae8bbdec1f040e6b890ccfee2ce6a489e83de6` |
| `m120_pass` / `m160_pass` | `false / false` |
| selected | `null` / `not_established` |
| classification | `HYBRID_MODEL_ROBUSTNESS_NOT_ESTABLISHED_BY_M160` |

## 负结果边界

Full3D/direct 比较中总 R/T/A/A_volume、energy closure、coordinates、interface E/H 和
middle E/H 均通过；失败值是显著 order power 的 relative delta，absolute 差只有约
`9e-12`--`7.4e-11`。比较器使用的 `max(power)>=1e-8` 与 relative `<=1e-4` 是冻结合同，
本轮不修改。

因此结论是“当前 fixed Hybrid 模型在 1°、±5° 对低功率 external channels 的鲁棒性尚未
建立”，不是“更高 M 必然解决”。后续若重新开启任务，需要新的审阅和新的 numerical evidence；
本轮不得 M200、调 PC、增 max_it 或改 tolerance。

## 允许的 diagnostic 与正式阶段

因为对应 direct 自身有效但 Full3D 比较未过，任务书允许每个非零 phi 一次 M160
solver-vs-direct diagnostic。两次 diagnostic 都在 linear Gate失败，不能作为 M 选择、Full3D
比较或 three-way pass 的输入。正式 R4、R5、R6 保持 `not_run_by_gate`。

## Final f2d7719 / 2dbf898 closeout

上段的 `not_run_by_gate` 只描述原 `6555663`、scalar traction、max_it=1600 冻结阶段；
它不覆盖后续用户明确授权的 research extension。该扩展使用
`full3d_one_cell_exact_schur`、固定 two-pass side correction、M120、restart90、
zero initial 与 max_it=4500，并保持 ordinary defaults 不变。

| phi | direct M120 self | direct M120-vs-M160 | direct M120-vs-Full3D | iterative M120 own / pairwise | 结论 |
|---:|---|---|---|---|---|
| 0° | pass | pass | pass | pass / pass | final pass |
| -5° | pass | pass | pass | pass / pass | final pass |
| +5° | pass | pass | pass | pass / pass | final pass |

三角度的 M120/M160/Full3D 九份 comparison 全部通过，故该授权扩展的共同
`M_robust=120`；这不是对上段历史 `M_robust=not_established` 的追溯改写。
MPI8 与 MPI1 的 iterative identity comparison 也均通过，镜像只做 power-only，复振幅为
`not_run_without_phase_map`。完整输入路径、SHA256 和误差字段见
[MPI8 compact record](../../../benchmarks/cases/102_hybrid_iterative_robustness/records/task037c_mpi8_three_way_qualification_v1.json)
与 [MPI1 compact record](../../../benchmarks/cases/102_hybrid_iterative_robustness/records/task037c_mpi1_identity_and_resource_v1.json)。

该 M 选择只适用于限定分类
`TASK037C_S_POL_1DEG_AZIMUTH_ROBUSTNESS_PASS_UNDER_USER_AUTHORIZED_RESEARCH_EXTENSION`，
不得写成 `production-qualified`，也不得据此尝试 M200 或修改冻结 PC/阈值。
