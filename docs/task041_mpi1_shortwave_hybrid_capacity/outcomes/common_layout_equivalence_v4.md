# Task041 V4：共同布局响应等价记录

## 状态

本记录是 V4-A0 的准备性 compact 说明，不是一次计算结果。宿主在启动前仍有受保护的
Full3D heavy 作业，故状态为 `BLOCKED_BY_ACTIVE_HEAVY_JOB`；C1 尚未实现，C1–C3 和
16 项主响应均 `not_run`。

| 维度 | V4 记录 |
|---|---|
| profile / scope | `task041_schur_speed_v2` / `representative_rhs` |
| comparison mode | `common_layout_equivalence`（显式 opt-in，尚未实现） |
| side schedule | `sequential_component` |
| 主响应 | `0/16`；expected `16` |
| 响应配对 | `0/8`；expected `8` |
| layout、P、PH、PC、response 等价 | `not_run` |
| new RSS / speed | `not_measured` |
| runroot / unit | `null`；本轮没有启动，不能填假路径 |

后续 C2/C3 若获准，资源固定为 MPI8、CPU `0–7`、每 rank 一个数学线程和同一严格 RSS
cap；C1 仅预计秒至分钟级，C2/C3 不在本记录中给出新时长预测。旧 R2 wall 仅作历史
排程参考，不冒充 V4 预计或实测。

## 比较合同

两种实现必须在同一侧、同一 layout epoch、同一 owned RHS 下运行。mesh、MPC、凝聚映射、
原始 global action/RHS 和 p4 factor 只准备一次；bottom 完成四项后释放并确认真实
diagnostics 的 p4/KSP 为零，才允许构造 top。这样可以把差异归因于 owner transfer 和
伴随向量实现，而不把两个运行的编号差异误当成 response 差异。

固定 entry 顺序为：

| ordinal | side | audit index → formal column |
|---:|---|---|
| 0 | bottom / positive | 227 → 207 |
| 1 | bottom / positive | 35 → 15 |
| 2 | bottom / negative | 691 → 671 |
| 3 | bottom / negative | 513 → 493 |
| 4 | top / positive | 330 → 310 |
| 5 | top / positive | 32 → 12 |
| 6 | top / negative | 686 → 666 |
| 7 | top / negative | 513 → 493 |

偶数 ordinal 先运行 legacy，奇数 ordinal 先运行 optimized；两者均 zero-start，不使用
KSP recycle 或 warm initial guess。每项记录原始 audit、reason、iteration、explicit
residual、owned range/array hash 和 identity。不得按数值排序、相位拟合、跨运行重排或
引入新 canonicalization。

## Gate 与停止条件

保留原有 action/transfer、duplicate-row、ghost/MPC、P/PH、p4/refinement、BAL_H 和 KSP
检查。阈值为 action/transfer `1e-11`、p4 residual `1e-10`、BAL_H `1e-8`、每响应
explicit residual `1e-2` 且 reason>0；同布局响应的诊断字段为
`threshold_e_x/threshold_e_A=1e-8`，实际值为 `null/null`，
不替代原线性门或凭空建立近似 KSP 的 `1e-11` 硬门。

资源仍由现有 service/supervisor 负责：process-tree RSS cap `53221163008 B`、90% warning、
reserve/cgroup 安全线、job/global swap 与 time-stop 全部保留。出现资源、身份、数值或
生命周期 Gate 时保留负证据并停止，不自动重试；本次启动前 heavy Gate 已足以阻止 C1。

## 历史边界

旧 R2/R2g 的分侧 apply `1680.27495998214 → 1258.8479048048612 s` 和 full-tree RSS
`51975606272 → 51796770816 B` 仍只是历史组件记录。跨 fresh run 的 132300 condensed
rows 缺少稳定物理 row key，所以正式状态仍为 `PAIRING_IDENTITY_UNPROVEN`；旧 S1f
`53331742720 B > 53221163008 B` 的双侧资源受控停止仍是独立 blocker。离线重叠表本轮
不重算，状态为 `historical_partial_overlap_analysis`：只引用已有的六行历史摘录，native
workspace 仍未知，也不构成双侧资格；六行摘要见 [Response V5 的历史内存表](../response_v5.md#31-旧-r2b-构造内存摘录非-v4-测量)。

旧 R2b 已有的六项构造内存摘录也只作历史定位：public/borrowed、bottom release、top
construction、p4 matrix/factor、transfer/H6、allocator/native unknown 分别保存在
compact 中。inventory 是 rank-local known payload；RSS 是约 0.3 s 级全树采样的 marker
前后括号，PSS/USS 才是稀疏诊断；不把各项 delta 相加或称为 V4 数据。旧 R2 baseline/optimized 全树峰的 cap 余量分别为
`1245556736/1424392192 B`（由 cap 减峰值重算）。

本轮最终只执行新 compact 的 `python -m json.tool`（输出丢弃）和 `git diff --check`，
两项均 exit `0`；父侧 `CLOCK_MONOTONIC` wall 为 `0.063355920 s`。记录见
[`v4a0_final_json_diff_check.json`](../../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/v4a0_final_json_diff_check.json)，
并已在唯一 V2 ledger 中一次追加本轮可追溯静态检查成本；账本当前
`11145.708812196894 s`，shared remaining `10454.291187803106 s`，SHA256
`c1c0ef6ab626f3c53b9d252abc43037b341ec73f53cdc93b86fc8626bc338dad`。
