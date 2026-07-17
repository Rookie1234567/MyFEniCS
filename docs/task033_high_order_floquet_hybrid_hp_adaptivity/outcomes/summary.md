# Task033 阶段性执行摘要

## 1. 身份与范围

| 字段 | 结果 | 说明 |
|---|---|---|
| 阶段分类 | `task033_stage1_phaseA_qep_tracking_closed` | 直接 3D p3/p4 与 QEP Phase A 已闭合 |
| 原 Task033 分类 | `partial_deferred_by_user_scope` | 自适应及其后续阶段延期 |
| 正式源码 | `6613f94b91ebc77eb50e74086475c67df46236f6` | clean worktree、同一 Docker image digest |
| Phase A 源码 | `bb830ba5dd74ced30475402bd6bc6d3c1856c630` | block tracking、Case090 reuse audit 与 selected MPI runs |
| 正式计算 | Case090 144 PDE；QEP MPI1 36 shards；selected p3/p4 h3 MPI2/4 4 shards | 大 campaign 已停止；Phase A 只补最小正向 MPI 身份 |
| ordinary default | unchanged | 新能力保持显式 opt-in |

## 2. 本阶段完成项

| 问题 | 回答 | 证据 |
|---|---|---|
| p3/p4 双 Floquet 直接 3D FEM 是否正确？ | 是。p3/p4 在两个解析夹具、S/P、h5/h2.5、MPI1/2/4 的核心 Gate 全过 | Case090 aggregate |
| 是否保持稀疏、分布式？ | 是。无全边界 allgather，无 dense boundary square | Case090 storage contract |
| p4 是否带来精度收益？ | 在 Case090 的 36 个 p-refinement 对照中均为正收益；代价是更高 DoF、NNZ 与时间 | `high_order_floquet_results.md` |
| p3/p4 QEP 是否资格化？ | 是。p3 直接通过；p4 四维近简并块 principal-angle tracking 通过 | `qep_tracking_diagnostic.md` |
| QEP legacy 全阶 aggregate 是否资格化？ | 否。p1/p2 真实低阶负结果保留；p3/p4 不再被阻塞 | `qep_order_study.md` |
| Hybrid 相比直接 3D FEM 是否一致？ | p2/h5、p2/h3 同阶同网格一致，行数降约 65%–69%，NNZ 降约 59% | `hybrid_vs_full3d_summary.md` |
| p3/p4 Hybrid 是否已与同阶 full3D 对照？ | 否。目标光栅没有 p3/p4 同阶 full3D reference | `negative_results.md` |

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

### 3.2 Hybrid p2 M160 与直接 3D p2

| 网格 | 行数 full3D → Hybrid | 行数降低 | NNZ full3D → Hybrid | NNZ 降低 | 最大 R/T/A 绝对差 |
|---|---:|---:|---:|---:|---:|
| h5 | 44,778 → 14,052 | 68.62% | 4,896,156 → 2,000,624 | 59.14% | `2.07e-6` |
| h3 | 198,518 → 68,796 | 65.35% | 21,317,860 → 8,594,673 | 59.68% | `2.63e-6` |

这证明当前 p2 同阶同网格离散上的代数与物理一致性，不证明连续解已经网格收敛，
也不证明 p3/p4 Hybrid 与 full3D 等价。

## 4. 明确延期

- uniform p/h 20 项完整矩阵；
- p2 graded/adaptive h5、h3；
- p3 equal-accuracy 与 p4 工程收益对照；
- native variable-p 与 hp zoning；
- 四个 interface buffer 与联合代价选择；
- 更新后的 1 TiB 与 0.7 nm 推演；
- 原任务书要求的 21-role formal manifest、final outcome 与 publication descriptor。

这些项目均为 `deferred_by_user_scope`，不是数值失败。

## 5. 正式 campaign 的暂停点

| 阶段 | 暂停时状态 |
|---|---|
| Case090 | MPI1/2/4 各 48、总计 144 PDE 已完成，aggregate 已生成 |
| QEP MPI1 | 36/36 shards 已完成 |
| QEP MPI2/4 | p3/h3、p4/h3 各 MPI2/MPI4 正向运行通过；旧 timeout-negative 保留为合同测试 |
| Hybrid p1/h5 | M80/M120/M160 漏斗已完成，结论为 modal-capacity negative |
| Hybrid p1/h3 | M80、M120 已完成；M160 在 `middle_plane_reconstruction` 阶段被用户范围调整终止 |
| Hybrid p2/p3、adaptive、buffer | 尚未进入 |

`p1/h3/M160` 已完成局部因子、Schur、场恢复与 official RTA，停止时正在中间平面
重建；由于没有生成 solver record、watchdog summary 和 funnel aggregate，它不是有效正式结果。

## 6. 是否需要继续计算

当前用户要求的两项总结不需要补算。若未来要升级结论，最小顺序是：

1. p3 目标光栅：先做资源预测，再生成 p3/h5 同阶 full3D reference，随后做
   p3/h5 的 M80/M120/M160 Hybrid 漏斗与 augmented/minimal anchor；h5 通过后才考虑 h3；
2. p4 目标光栅：只在 p3 闭合且预测 Gate 通过后，考虑 p4/h5 direct + Hybrid；
3. QEP Phase A 已闭合；下一步按审阅报告做 p3/p4 matched-trace 小 fixture，不重跑完整 36 项；
4. adaptive/graded/buffer 不属于当前阶段，除非用户重新开启，不建议继续。

## 7. 证据边界

Case090 与 QEP 原始 watchdog 位于 ignored campaign 目录；仓库跟踪的是其 SHA、关键数值与
阶段描述符。Task032 的六份 p2 Hybrid/full3D 记录仍是可复核的 tracked clean evidence。
