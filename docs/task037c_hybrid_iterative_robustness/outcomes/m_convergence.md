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
