# Task033 阶段性执行摘要

## 2026-07-17 Review V5 Phase D 更新（当前状态）

Review V5 批准的 D0、D1、D2 已完成；数值 campaign 已按停止规则结束。

| 项目 | 当前结论 |
|---|---|
| D0 source/evidence/document convergence | 完成；历史 Phase C 标记 superseded，pure-3D/Hybrid 数值源兼容性通过 |
| p3/h10 direct / Hybrid M120/M160 | 安全完成、零 swap；direct 等精度失败，Hybrid H-interface Gate 也未过 |
| 条件 p3/h7.5 direct | 3.667 GiB、44.487 s、零 swap、true residual `6.449e-12` |
| p3/h7.5 等精度 | 全部 R/T/A、Avol、五平面/接口 E/H 和逐阶误差不劣于 p2/h3 |
| p3/h7.5 Hybrid M120/M160 | 16 项 Gate 全过；M160 2.008 GiB、74.908 s |
| p3/h7.5 对 p2/h3 资源 | FE DoF 2.571x、local-system rows 2.567x、total rows 2.548x、factor-inventory NNZ 3.557x、memory 1.606x、time 1.331x |
| variable-p / hp | 当前 native cellwise variable-p H(curl) 未资格化；fail closed，无 target prototype |
| 原 Task33 | 仍为 partial；h-adaptive、buffer、1 TiB update、21-role formal closure 未完成 |

等精度 reference 是 `p3/h5` 最佳可用离散解，不是连续解，也未证明网格收敛。
详细误差、资源口径和 SHA 见
[`reduced_equal_accuracy_phaseD.md`](reduced_equal_accuracy_phaseD.md)；Task33 全量完成/
延期对账见 [`task33_completion_matrix.md`](task33_completion_matrix.md)。

## 2026-07-17 Phase C1 更新（覆盖下文旧停止点）

用户允许 p3/h5 受控 direct 运行，并规定：若 p3 实际零 swap 且峰值低于
10 GiB，则可进入 p4/h5。执行结果如下：

| 项目 | 结果 |
|---|---|
| p3/h5 full3D direct | `full3d_reference_pass`；7.781 GiB；cgroup swap 0 |
| p3/h5 Hybrid M160 对同阶 direct | 16 项物理/代数 Gate 全过；最大 R/T/A 差 `1.214e-7` |
| 五个 z 截面 | 最大 E/H 相对 L2 为 `1.100e-5 / 1.098e-4` |
| p4 四模态 matched trace | MPI1/MPI4、4×4 Gram、Petrov、块不变量全部通过 |
| p4/h5 direct 装配 | 339,892 行、155,205,040 base NNZ；12.616 GiB 时受控终止 |
| p4 目标求解 | 未启动；full3D 实测 Gate 失败，Hybrid 独立资源上界 42.594 GiB |

因此当前阶段分类更新为
`p3_h5_same_degree_numerical_closure_pass_p4_target_memory_gated`。这表示 p3
数值闭合已经完成，但新证据仍等待独立复审；原 Task33 自适应范围继续延期。

## 1. 身份与范围

| 字段 | 结果 | 说明 |
|---|---|---|
| 阶段分类 | `p3_h5_same_degree_numerical_closure_pass_p4_target_memory_gated` | Phase C1 已取得 p3 同阶 direct；p4 通过组件门禁但目标求解被自身内存 Gate 阻止 |
| 原 Task033 分类 | `partial_deferred_by_user_scope` | 自适应及其后续阶段延期 |
| Stage1 正式源码 | `6613f94b91ebc77eb50e74086475c67df46236f6` | clean worktree、同一 Docker image digest |
| Phase A 源码 | `bb830ba5dd74ced30475402bd6bc6d3c1856c630` | block tracking、Case090 reuse audit 与 selected MPI runs |
| Phase B 实测源码 | `bd7a6023bde7a7c06d456e702af4b7f9f047b3fc` | p2 MPI1、p3/p4 MPI1/MPI4 matching-trace 五条 shard |
| Phase B 聚合源码 | `9ac29db45b387d4590de084710abe2cc38b25ffe` | fail-closed 复算、原始文件 hash 与 compact observed evidence |
| Phase C 数值源码 | `b636444b693a932988b6d5d69f7e44e6a8cddb38` | p3/h5 C0、M80/M120/M160 与 augmented M160，完整 clean source |
| 正式计算 | 原 campaign + p3 full3D 1 次 + p3 Hybrid 闭合 1 次 + p4 四模态 2 shards + p4 装配负校准 1 次 | p4 未进入因子分解；p3/h3 与 adaptive 未启动 |
| ordinary default | unchanged | 新能力保持显式 opt-in |

## 2. 本阶段完成项

| 问题 | 回答 | 证据 |
|---|---|---|
| p3/p4 双 Floquet 直接 3D FEM 是否正确？ | 是。p3/p4 在两个解析夹具、S/P、h5/h2.5、MPI1/2/4 的核心 Gate 全过 | Case090 aggregate |
| 是否保持稀疏、分布式？ | 是。无全边界 allgather，无 dense boundary square | Case090 storage contract |
| p4 是否带来精度收益？ | 在 Case090 的 36 个 p-refinement 对照中均为正收益；代价是更高 DoF、NNZ 与时间 | `high_order_floquet_results.md` |
| p3/p4 QEP 是否资格化？ | 是。p3 直接通过；p4 四维近简并块 principal-angle tracking 通过 | `qep_tracking_diagnostic.md` |
| QEP legacy 全阶 aggregate 是否资格化？ | 否。p1/p2 真实低阶负结果保留；p3/p4 不再被阻塞 | `qep_order_study.md` |
| p3/p4 matching trace 是否资格化？ | 是。p3、p4 的 3D→2D 迹、右重构、左 Petrov、积分加阶与 MPI identity 均通过；p4 独立判定 | `matched_trace_phaseB.md` |
| Hybrid 相比直接 3D FEM 是否一致？ | p2/h5、p2/h3 同阶同网格一致，行数降约 65%–69%，NNZ 降约 59% | `hybrid_vs_full3d_summary.md` |
| p3/h5 Hybrid 是否已闭合 M 漏斗与路径等价？ | 是。M80/M120/M160 漏斗和 augmented/minimal M160 全部通过 | `p3_h5_phaseC.md` |
| p3/p4 Hybrid 是否已与同阶 full3D 对照？ | p3/h5 已同阶闭合；p4 因本机目标装配内存 Gate 失败而没有同阶 target solve | `full3d_closure_summary.json`、`calibration_summary.json` |

## 3. 核心数值

### 3.1 Case090 直接 3D FEM/Floquet

| Gate | 最大观测值 | 限值 | 结果 |
|---|---:|---:|---|
| constraint round trip | `2.9461e-14` | `1e-12` | pass |
| Bloch trace mismatch | `3.1890e-15` | `1e-11` | pass |
| reduced/full action | `3.1269e-16` | `1e-11` | pass |
| full true residual | `6.5985e-12` | `1e-10` | pass |
| MPI result difference | `1.0669e-11` | `1e-10` | pass |

每个 MPI 规模固定 48 项：Fixture A 16、Fixture B 10° 主矩阵 16、Fixture B
1°/5° smoke 16。MPI1/2/4 合计 144，不是 192。

### 3.2 Phase B matching-interface

| shard | 最大 3D→2D 迹误差 | coefficient round-trip | Gram cond | raised trace-mass delta |
|---|---:|---:|---:|---:|
| p2 MPI1 | `5.951e-15` | `2.948e-16` | `30.4995` | `0` |
| p3 MPI1 / MPI4 | `9.566e-15` | `2.828e-16` | `90.7920` | `0` |
| p4 MPI1 / MPI4 | `9.835e-15` | `5.769e-16` | `35.2663` | `0` |

p3/p4 MPI1→MPI4 最大 beta 匹配差分别为 `5.546e-14` 与 `4.267e-14`。
没有 full field/mode gather，也没有 dense interface square。该结论只覆盖小型匹配迹
组件；目标 Hybrid 已在 Phase C 新 SHA 上重新实测，但该组件记录不替代 full3D。

### 3.3 Hybrid p2 M160 与直接 3D p2

| 网格 | 行数 full3D → Hybrid | 行数降低 | NNZ full3D → Hybrid | NNZ 降低 | 最大 R/T/A 绝对差 |
|---|---:|---:|---:|---:|---:|
| h5 | 44,778 → 14,052 | 68.62% | 4,896,156 → 2,000,624 | 59.14% | `2.07e-6` |
| h3 | 198,518 → 68,796 | 65.35% | 21,317,860 → 8,594,673 | 59.68% | `2.63e-6` |

这张 p2 表本身只证明同阶同网格离散上的代数与物理一致性，不证明连续解已经网格
收敛，也不单独证明 p3/p4 Hybrid 与 full3D 等价。p3/h5 已由后续同阶 direct
闭合另行证明；p4 仍没有目标求解对照。

### 3.4 Phase C p3/h5 Hybrid

| 路径 | memory authority | max-rank total | 结果 |
|---|---:|---:|---|
| Schur-minimal M80 | 2.278 GiB | 63.66 s | pass |
| Schur-minimal M120 | 2.492 GiB | 85.10 s | pass |
| Schur-minimal M160 | 2.641 GiB | 106.98 s | pass |
| augmented vs minimal M160 | 4.148 GiB | 114.05 s | pass |

M120→M160 最大 R/T/A 绝对差为 `7.216e-14`，显著逐阶功率/复振幅相对差为
`3.676e-10 / 1.925e-10`。M160 true residual 为 `2.277e-12`，
volume closure error 为 `1.874e-12`，E/H interface Gate 均通过。旧 C0 曾由两个
经验中心 `6.445 / 15.031 GiB` 和保守上界 `18.038 GiB` 给出
`not_run_by_memory_gate`；该预测身份现已被用户授权的受控实测取代，不能继续当作
当前运行状态。

同阶 p3/h5 full3D 随后以 7.781 GiB、零 cgroup swap、true residual
`5.442e-12` 完成。新 SHA 上重跑的 Hybrid M160 为 2.618 GiB，16 项 Gate 全过；
相对 direct 的最大 R/T/A 差为 `1.214e-7`，五平面最大 E/H 相对 L2 为
`1.100e-5 / 1.098e-4`。因此 p3/h5 whole Phase C 当前为数值闭合通过，而非
“保持未通过”。

## 4. 原范围中尚未完成的项目

- uniform p/h 原 20 项完整矩阵：被 Review V5 的减缩矩阵取代，不再机械执行；
- p2 graded/adaptive h5、h3：未运行，等待 D1/D2 summary 新审阅；
- p4 工程收益：当前主机资源 Gate negative，未建立；
- native variable-p target prototype：capability audit fail closed，未实现；
- 四个 interface buffer 与联合代价选择：等待 defect/nonuniform-end geometry；
- 更新后的 1 TiB 与 0.7 nm 推演：等待 measured adaptive compression；
- 原任务书要求的 21-role formal manifest、final outcome 与 publication descriptor。

fixed-p p3 equal-accuracy 不再属于延期项：`p3/h10` 为精度负结果，
`p3/h7.5` 为带资格的工程正结果。variable-p capability audit 也已完成；未完成的是
target prototype。各项是 `removed_by_reduced_scope`、`deferred`、`resource_gated`
或 `capability_gated`，不能统一写成数值失败。

## 5. 正式 campaign 的暂停点

| 阶段 | 暂停时状态 |
|---|---|
| Case090 | MPI1/2/4 各 48、总计 144 PDE 已完成，aggregate 已生成 |
| QEP MPI1 | 36/36 shards 已完成 |
| QEP MPI2/4 | p3/h3、p4/h3 各 MPI2/MPI4 正向运行通过；旧 timeout-negative 保留为合同测试 |
| Hybrid p1/h5 | M80/M120/M160 漏斗已完成，结论为 modal-capacity negative |
| Hybrid p1/h3 | M80、M120 已完成；M160 在 `middle_plane_reconstruction` 阶段被用户范围调整终止 |
| Phase B matched trace | p2 MPI1、p3/p4 MPI1/MPI4 共 5 条已完成并聚合通过 |
| Phase C p3/h5 full3D | 旧 C0 否决已由用户授权实测取代；direct pass，7.781 GiB、零 cgroup swap |
| Phase C p3/h5 Hybrid | M80/M120/M160 与 augmented M160 完成；新 SHA 上 M160 对同阶 direct 的 16 项 Gate 全过 |
| Phase C p4 四模态 | MPI1/MPI4 四模态 QEP→matched-trace 资格化通过 |
| Phase C p4/h5 target | full3D assembly-only 在 12.616 GiB 受控终止；Hybrid 独立上界 42.594 GiB；均未进入目标求解 |
| Phase D p3/h10 | direct + Hybrid M120/M160 完成；等精度 negative，按规则触发 h7.5 |
| Phase D p3/h7.5 | direct + Hybrid M120/M160 完成；equal-accuracy engineering positive with qualification |
| Phase D variable-p | 运行时 capability audit 完成；fail closed，未触发 microfixture |
| p3/h3、adaptive、buffer | 未获当前批准或等待目标几何，未启动 |

`p1/h3/M160` 已完成局部因子、Schur、场恢复与 official RTA，停止时正在中间平面
重建；由于没有生成 solver record、watchdog summary 和 funnel aggregate，它不是有效正式结果。

## 6. 是否需要继续计算

当前没有需要自动补算的项目。p3/h5、p3/h10、p3/h7.5 均不需要重复，M240 没有
数值必要。若未来继续，最小顺序是：

1. 先独立复审 D1 reduced summary 与 D2 capability report；无需重跑；
2. 只有新审阅批准后，才启动最后的 p2 conforming graded-h h5 mechanism，随后
   条件进入 h3 compression；
3. p4/h5 只能在显著更大的内存预算或已资格化低内存算法上继续；当前主机不应
   重做装配或启动 factorization/solve；
4. interface buffer 等待 defect geometry；1 TiB 推演等待 adaptive measured data；
5. p3/h3 不在当前减缩范围内，不由 p3/h7.5 正结果自动解锁。

## 7. 证据边界

Case090 与 QEP 原始 watchdog 位于 ignored campaign 目录；仓库跟踪的是其 SHA、关键数值与
阶段描述符。Phase B 的五条原始 shard 同样位于 ignored 目录，但 tracked
`phaseB_summary.json` 保存每条文件 SHA256、关键实测量和独立重算 Gate。新 p4
四模态记录由 `p4_four_mode_summary.json` 跟踪。旧 Phase C 七个关键文件仍由
`phaseC_summary.json` 保存历史漏斗与 C0 身份；新同阶闭合由
`full3d_closure_summary.json` 保存 p3 direct、Hybrid、五平面和 16 项 Gate，
p4 负校准则由 `calibration_summary.json` 保存。Task032 的六份 p2
Hybrid/full3D 记录仍是可复核的 tracked clean evidence。Phase D1 由
`stage5_equal_accuracy/reduced_equal_accuracy_summary.json` 哈希绑定 p3/h10、
p3/h7.5 direct/Hybrid raw records；D2 由 `variable_p_capability_audit.json`
保存运行时 API 和逐项 semantic requirement。
