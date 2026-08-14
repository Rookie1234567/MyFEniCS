# Review V1 E7：M960 canonical trace 数值审计

## 1. 目的与边界

canonical trace 是把独立 lifting 得到的界面迹映射到一组稳定的模态坐标。普通
forward error 只看结果差了多少；本阶段同时报告 backward error，用矩阵自身的规模
衡量“当前误差是否符合浮点线性代数的可解释范围”。它只改变 Review V1 的
`M960` research-only 判断，不改变 M120/M240/M480 或 ordinary direct 的 fixed
`1e-12` Gate，也不读取外部 family raw 文件作为在线运行依赖。

审计顺序是：四档真实 capture 先独立保存矩阵，再由离线 family checker 重新加载和
重算；随后唯一一次正式 M960 direct run 在当前 `G/R/M` 位置记录在线数值。审计通过
不等于 Hybrid 模型已通过 Full3D 或网格收敛。

## 2. 身份与证据

| 项目 | 值 |
| --- | --- |
| Review family compact record | [task039_e7_m960_trace_family_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_trace_family_v1.json) |
| family raw record SHA / bytes | `5fd8351050fb4849b87084de9465b218745805ecda7e4a83109bcd7a472aaedd` / `2372242` |
| family compact file SHA / bytes | `9530ab4259db2f8a8ccda7b69edcac50e4fa9fce06f56b2ec9c1d3a6d2a0cae0` / `10600` |
| capture source SHA | `34bca037870cc4d7d132dcfbec71981a867213b8` |
| physical model SHA | `db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a` |
| 每档 MPI / external inventory | `MPI8` / `604` exact keys |
| online M960 result | [task039_e7_m960_direct_result_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_direct_result_v1.json) |
| online source commit | `d66c3a64176897a90fc1ea04298c6b804bafa8aa` |

四档 capture 的 input/resolved SHA 各自不同，但 physical SHA、source capture SHA、MPI
和 604-key identity 一致；每档 JSON/NPZ 的完整 hash 仍保留在 compact family record
及其原始 ignored evidence 中。

## 3. 四档 family Gate

下表是每侧审计的最坏 scalar；`representation`、`raw forward`、`eta`、repeat eta
均由每侧独立矩阵重算。`eta limit` 是
`100 * eps_machine * matrix_dimension`，不是把 fixed `1e-12` 改成更宽的固定值。

| M | bottom/top condition | 最坏 raw forward | 最坏 representation | 最坏 eta / limit | sign/order、repeat、finite | individual |
| ---: | ---: | ---: | ---: | ---: | --- | --- |
| 120 | 4349.66 / 4323.96 | 2.220e-15 | 1.048e-15 | 8.764e-16 / 2.665e-12 | pass / pass / pass | pass |
| 240 | 17231.37 / 17130.23 | 1.888e-13 | 1.288e-15 | 6.309e-14 / 5.329e-12 | pass / pass / pass | pass |
| 480 | 69451.71 / 69069.19 | 2.183e-12 | 3.702e-15 | 4.227e-13 / 1.066e-11 | pass / pass / pass | pass |
| 960 | 986240.60 / 2089283.87 | 1.592e-11 | 1.484e-14 | 2.837e-12 / 2.132e-11 | pass / pass / pass | pass |

family 结论为：

```text
family_pass = true
historical_sign_order_exact = true
historical_repeat_gate = true
all_matrices_finite = true
raw_artifact_exact = true
repeat_matrix_difference_exact = true
classification = M960_TRACE_AUTHORITY_NUMERICAL_AUDIT_PASS
```

这组证据没有手填 M120/M240/M480 的“通过”标志；每档两侧的列键、重复装配、有限
性和数值量均从对应 JSON/NPZ 重新核对。M960 的最坏列是 bottom index 934、top
index 935；完整列键与原始 near-degenerate 证据在 family raw artifact 中保留。

## 4. 正式 M960 direct online Gate

正式运行目录为
`results/task039_5nm_hybrid_direct_m960/task039_5nm_hybrid_direct_p6h10_m960_mpi8__hybrid_direct__mpi8__M960/20260813T214509.450065Z`。
它使用同一 p6/h10、5 nm、S、10°、M960、MPI8、604 keys 和 exact traction 合同；
在线 policy 只在 M960 且 family attestation 通过时启用。

| Gate / 量 | bottom | top | limit / 结论 |
| --- | ---: | ---: | --- |
| raw forward | 1.087993e-11 | 9.599898e-12 | hard guard `1e-9`，pass |
| representation | 8.946793e-15 | 8.999275e-15 | `1e-12`，pass |
| backward eta | 1.914663e-12 | 1.701156e-12 | `2.131628e-11`，pass |
| surface Gram condition | 987468.013 | 2094742.667 | measured |

其中在线 backward error 使用同一公式：

```math
\eta_{raw} = \frac{\lVert R-GM\rVert_\infty}{\lVert R\rVert_\infty + \lVert G\rVert_\infty\lVert M\rVert_\infty + \mathrm{tiny}}.
```

正式 own authority 如下：

| 项目 | measured 值 | Gate |
| --- | ---: | --- |
| true relative residual | `1.6797118438e-11` | `<=1e-9`, pass |
| interface projection | `5.7894084979e-13` | `<=1e-8`, pass |
| exact traction bottom/top | `3.8353122558e-12 / 1.6724358568e-11` | `<=1e-8`, pass |
| closure | `1.1485794891e-6` | `<=1e-5`, pass |
| R/T/A_balance/A_volume | `0.9094973679165264 / 0.0008705857370964508 / 0.0896320463463772 / 0.08963319492586634` | finite |
| external keys | `604`, bottom/top `300/304` | exact unique, pass |
| numerical wall | `5332.772663516924 s` | measured |
| process-tree RSS/PSS/USS | `71502.582 / 69746.089 / 69465.102 MiB` | measured independent peaks |
| swap | `0 MiB` | pass |

`official_record=false` 与 `mode_count_converged=false` 的原因是 M convergence / model
validation 仍未建立，不是 M960 own solve、traction 或在线 trace Gate 失败。正式结果
的 sampled traction-density proxy 仍为 false；它不覆盖 exact variational traction。

## 5. M convergence 与 Full3D 边界

| 比较 | 结果 | 解释 |
| --- | --- | --- |
| M480 vs M960 | adjacent totals、33 significant power/amplitude、selected E/H 均通过 | 说明 M960 与既有 M480 direct observable 接近 |
| M960 vs Full3D h10 | H z=10 `0.0616688409`、z=60 `0.0599587361` 失败 | Full3D H diagnostic 仍是负结果 |
| M960 vs Full3D h6 | 差异大；604 keys exact | h6 是 best available discrete，不是已建立 reference |

h6 与 h10 的 physical SHA 差异来自 mesh 进入 physical identity；E5 已证明
`physics_except_mesh_exact=true`。因此该差异不是物理合同漂移的证据，也不能把 h6
称为 continuum/refined authority。相关比较见 [M960 vs M480/h10/h6 records](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_direct_vs_m480_h10_v1.json)
和 [h6 comparison](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_direct_vs_h6_v1.json)。

## 6. 结论与停止边界

E7 family audit 和唯一 M960 direct rerun 均完成；这不是把 fixed forward Gate 简单
放宽，而是以四档真实 repeat/sign-order 证据和在线 backward stability 条件作窄的
M960 research-only qualification。M120/M240/M480 ordinary fixed Gate、exact traction
实现和后续 direct solve 语义没有被本阶段文档改写。

Review V1 §7.3 要求完成 M960 direct 后停止，因此 E8/E9 均为
`not_run_by_review_v1_7p3_stop_after_m960_direct`。这不是 Hybrid iterative 的成功或
失败；首轮 Hybrid iterative 从未运行的事实仍保留。Full3D 网格未收敛、T4 iterative
负结果、T9 0.7 nm component-only 限制也全部保留。

## 7. 证据入口

- [E5 grid convergence](full3d_direct_grid_convergence_v2.md)
- [E6 H diagnostic](m480_h_field_diagnostic.md)
- [resource ledger](resource_ledger.md)
- [test summary](test_summary.md)
- [E7/E10 compact evidence](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_direct_result_v1.json)
