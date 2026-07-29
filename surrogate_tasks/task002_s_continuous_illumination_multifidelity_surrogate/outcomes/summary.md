# Task002 M0--M2 结果总览

## 当前结论

Task002 状态为 `controlled_stop_at_M2`，不是完成。M1 的 S-only schema、连续角转换、
order/cutoff audit、campaign resume/dedup、canonical dataset/hash checker 已完成。四个角度
corner 的 LF/HF center anchors 共 8 个 run 全部通过；49 点 LF pilot 的首个新增点
`0.5°/15°/S` 未通过 energy Gate，因此按任务书立即停止。没有开始四维 bulk、surrogate
training、DOE、P surrogate、Hybrid-P 或正式反演。

## 身份与范围

| 项目 | 值 | 状态/证据 |
|---|---|---|
| implementation baseline | `a27b07946319e31719c4cf9b1cd16b5d0a4735b9` | M1 initial clean commit |
| formal M2 dataset source | `f6613e4329ba3d52f122cffb8952df93cd83a30d` | exact-traction Task002 gate clean SHA |
| polarization / wavelength | S only / 13.5 nm | P fail closed |
| geometry domain | h=115--125 nm, w=16--18 nm | not bulk-sampled |
| angle domain | grazing=0.5--10°, azimuth=0--90° | M2 incomplete |
| LF / HF | Hybrid p4/p6 h10 M120 MPI2 | fixed |
| observable schema | `task001.fixed-n0-orders.v2` | unchanged and order-window complete |

## M1 实现

| 组件 | 作用 | 结果 |
|---|---|---|
| Task002 parameter schema | 对 S/13.5 nm/四维域 fail closed；0°返回结构化 limit | pass |
| angle features | degree 输入转换为 theta/phi 与 normalized kx/ky | pass |
| analytic order audit | 在 49 点角网格搜索 m=-12..12 | propagating union=-7..0，固定窗口完整 |
| design tables | 冻结 49 LF、9 fixed HF 和 seed | pass，hash-bound |
| campaign | 单样本、clean SHA、watchdog、resume/dedup | pass |
| dataset/checker | arrays、mask、split、hash、混源拒绝 | synthetic pass |

M2 首次尝试暴露旧 sampled-H proxy 仍是 hard Gate；`0.5°/0°/S` 的 exact variational
traction dual、assembled E、能量和 residual 都通过。Task002 独立 gate 因而改为使用 exact
assembled traction，把 sampled interpolation 原值保留为 diagnostic；Task001/Task035c 历史
Gate 未改。按 source 规则建立新 SHA 并重跑全部 anchors。

## M2 统一结果

以下均为 center geometry、baseline `f6613e4...` 的 measured 数据；R/T/A 无量纲，RSS 为
process-tree peak。

| fidelity | grazing/azimuth (deg) | status | residual | max assembled E | max exact H dual | energy closure | R / T / A | wall s | RSS GB |
|---|---|---|---:|---:|---:|---:|---|---:|---:|
| LF | 0.5/0 | measured_pass | `4.22e-11` | `1.29e-6` | `8.39e-12` | `3.45e-7` | .859005 / .000834 / .140161 | 53.2 | 1.069 |
| LF | 0.5/90 | measured_pass | `9.21e-12` | `2.18e-5` | `6.77e-12` | `-6.88e-9` | .861286 / .000824 / .137889 | 47.2 | 1.160 |
| LF | 10/0 | measured_pass | `2.87e-12` | `1.24e-6` | `2.68e-12` | `1.51e-7` | .001882 / .596620 / .401498 | 53.3 | 1.070 |
| LF | 10/90 | measured_pass | `1.20e-12` | `1.81e-5` | `1.61e-12` | `7.84e-9` | .001853 / .602506 / .395641 | 46.2 | 1.082 |
| HF | 0.5/0 | measured_pass | `4.99e-11` | `1.85e-7` | `1.82e-11` | `7.68e-10` | .621706 / .006224 / .372070 | 514.9 | 4.780 |
| HF | 0.5/90 | measured_pass | `5.00e-11` | `1.09e-5` | `3.73e-11` | `-1.48e-9` | .625420 / .006239 / .368341 | 225.5 | 3.457 |
| HF | 10/0 | measured_pass | `2.89e-12` | `1.55e-7` | `2.39e-12` | `1.56e-10` | .000763 / .602702 / .396535 | 233.5 | 3.387 |
| HF | 10/90 | measured_pass | `3.95e-12` | `9.72e-6` | `3.34e-12` | `-1.38e-10` | .000747 / .608659 / .390594 | 225.5 | 3.640 |
| LF | 0.5/15 | failed_numerical_gate | `2.07e-11` | `1.24e-3` | `3.05e-11` | `-2.606e-5` | .818563 / .001415 / .180022 | 46.2 | 1.067 |

九个 run 全部 zero swap 且 watchdog cleanup 完成。失败点只有 energy closure 未通过；
`|beta|/k0=0.0087265<0.02`，属于预先标记的 near-cutoff 区，但固定 LF M120 尚无可靠
disposition，不能进入 dataset。

## 阶段与后续决策

| 阶段 | 状态 | 决策 |
|---|---|---|
| M0 | pass | WSL complex ABI/资源/Git 合格 |
| M1 | pass | production core isolated；ordinary default unchanged |
| M2 anchors | 8/8 pass | 保留 hash-bound evidence |
| M2 LF pilot | 5/49 unique angles evaluated，1 fail | controlled stop |
| M2 HF pilot | 4/9 fixed points复用 anchors | 不继续 |
| M3--M10 | not_run | 未解锁 |

后续若继续，必须先由 Review 给出独立 disposition，解释/修复 near-cutoff conical S 的 M120
energy closure；不得放宽 `1e-5`、删除失败点或直接分区后宣称全域通过。

## Selective merge

| 分组 | 内容 | 建议 |
|---|---|---|
| reusable forward-data | Task002 schema/design/dataset/campaign | 可审阅，数值核心不变 |
| runner gate routing | Task002 exact assembled traction gate | 需结合 F1/Review V3 审阅 |
| checker/Case112 | M1 contract + M2 compact negative evidence | 可保留 |
| research evidence | near-cutoff `0.5°/15°/S` failure | 必须保留，不提升 production |
| do-not-merge/promote | bulk、surrogate、DOE、P、inversion | 未运行 |
