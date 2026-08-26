# V4-1 exact trace representability

## Review V5 当前状态

`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 的 no-signal stop 与
resource-authority gap 未授权本阶段；这不是 exact trace、projection 或 lift 算法失败。

## Review V4 历史状态

`controlled_identity_negative`（controlled identity stop）。V4-1 的独立 raw checker 已验证 metadata/hash 身份，但在构造
system、F、interface mass、Vec、factor、QEP 或 PDE 之前停止；本页不把未运行的 trace、
projection 或 lift 写成数值失败。

## 唯一问题

先用既有 hash-bound exact-side outputs 做诊断，分别回答：

1. `296 + 480` 当前接口 span 是否能表示正确的 lower/upper trace；
2. Petrov dual 是否造成额外投影误差；
3. 给定 trace 后，三分区 harmonic lift/back-substitution 是否仍不能恢复三维 side 解。

历史 exact spool 来自 `A_side = F - C H^{-1} D` 的 ResearchExactSideLuAction/Woodbury
路径；Review 正式残差必须另以当前 bare `F_b` 核验。两种 operator 的 hash、action 和
residual 不得混用。

## 计划计算与 Gate

| 项目 | V4-1 固定合同 | 当前结果 |
|---|---|---|
| authority | 五个冻结 label；先核验 metadata/hash，再检查 canonical source-row binding | metadata/hash identity 已核验；`canonical_source_binding=false`，数值重建 `not_run_by_identity_gate` |
| projection | 当前 Petrov 与 interface-mass metric best 两种投影 | `not_run` |
| lift | exact trace、Petrov trace、best trace 三种同构 group back-sub | `not_run` |
| formal operator | `F_b` action/hash；A-side 仅解释字段 | `not_run` |
| Gate | five solution rel `<=1e-8`、bare-F residual `<=1e-9`、finite/repeat/linearity、factor `3→0`、full-side factor `0`、swap `0`、peak `<45 GiB` | `not_run` |

投影必须避免 normal equations。metric-best 使用稳定 complex QR/SVD；所有 trace 用 canonical
keys，不假设 PETSc global row 顺序稳定。

## 证据边界

若 exact authority 对 `A_side` 成立而对 `F_b` 不成立，分类为
`EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F`，不是通过调阈值或重建 factor 解决的
implementation bug。若 tiny/exact algebra 证明只是 orientation、owner 或 action 接线错误，
才可按 Review V4 §4 做最小修复并绑定新 SHA。

## Review V4 历史收口

这里的 canonical source-row bridge，通俗地说，就是一张把每个存储行重新指回稳定物理自由度
的地图，也就是 source-row 到 canonical physical key 的映射。当前文件的 array hash 和
metadata 自哈希正确；NPY values 确实存在，但 formal 只做 mmap/hash 校验，没有构造 PETSc
Vec，也没有保留 values。冻结 exact spool 缺少这张 source-row 到 canonical physical key 的
映射/bridge；旧 PETSc global row 只能说明“当时存在哪里”，不能说明“数学上代表什么”。当前
旧 MPI8 ownership 与新构造布局不同，因此不能把 raw global row 当作可重建的 operator identity。

| identity check | 实测结果 |
|---|---|
| input SHA256 | `true` |
| physical model SHA256 | `true` |
| frozen branch | `true` |
| freeze source | `true` |
| selected manifest | `true` |
| resolved config | `true` |
| packet manifest | `true` |
| spool catalog | `true` |
| spool producer source（10 label:role，8/8） | `true` |
| exact-output metadata identity（五标签） | `true` |
| `canonical_source_binding`（canonical source binding） | `false`；唯一 identity failure |

缺失项恰为以下 10 项：

`modal_traction_positive:rhs`、`modal_traction_positive:exact_output`、
`modal_traction_negative:rhs`、`modal_traction_negative:exact_output`、
`external_dtn_coupling:rhs`、`external_dtn_coupling:exact_output`、
`fixed_random_repeat_0:rhs`、`fixed_random_repeat_0:exact_output`、
`fixed_random_repeat_1:rhs`、`fixed_random_repeat_1:exact_output`。

| 项目 | 阈值/合同 | 当前实测状态 |
|---|---|---|
| bare-F true residual，五源 | `<=1e-9` | 无数值；`not_run_by_identity_gate` |
| A-side explanatory residual，五源 | 仅解释，不替代 bare-F | 无数值；`not_run_by_identity_gate` |
| exact/Petrov/metric-best trace | Review V4 固定三种对照 | `not_run_by_identity_gate` |
| projection | Petrov 与 metric-best | `not_run_by_identity_gate` |
| lift | 三种 trace 的 group lift | `not_run_by_identity_gate` |

`descriptor_available`、`descriptor_complete`、`bridge_qualified` 和 `pass` 均为 `false`；
array metadata hash 已验证，但 numeric vectors 未构造、values 未保留、raw-row remap 未使用且
被禁止。正式结论与 37/37 checks、105 read files、无 NPY 的 compact record 绑定：
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

## Review V5 当前收口

本页的 exact/Petrov/metric-best 三种解 trace 与三维 lift 没有运行，状态为
`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 只保存了两源在
16/32/64/128 的 residual trace；这不是 exact authority packet，也不是 lift 结果。

V5-2 的 fresh bare-F authority 在授权的 `21600 s` factor-construction 窗口内
`FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED`，没有可供 consumer 使用的 exact output。随后
Route C 的独立重算得到两源 `ROUTE_C_NO_SIGNAL`，且 timeline 的中段 live-unreadable
样本使 resource authority 不完整。因此没有新的 solution error、bare-F residual、
orientation/Floquet lift 或 factor-free exact reconstruction 数值。此前 V4 的
canonical source-row bridge 负结论仍只表示旧 spool 无法安全重构，不与本次 Route C
residual 混用。

| 项目 | V5 实际状态 |
|---|---|
| exact/Petrov/metric-best trace | `not_run_by_route_c_no_signal_and_resource_authority_gate` |
| 三维 group lift / solution error | `not_run_by_route_c_no_signal_and_resource_authority_gate` |
| bare-F 与 A-side residual | 无数值；未运行 |
| V5-2 exact packet | 未生成；`exact_output_vectors_loaded=0` |

[V5 Route C signal ledger](route_signal_ledger.md)；[V5-1 audit](authority_operator_semantics.md)。
