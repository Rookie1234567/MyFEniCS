# V14：从 Gx560 负结果到原尺寸准入包

这份包只整理已经存在的原尺寸模式清单和资源台账。它没有生成 15,232-cell 有限元网格、矩阵或 PDE 结果。原尺寸模型仍是 0.7 nm 波长、50×25×140 nm 区域，Si/air 与 32,060 个 AUTO 传播模式的身份沿用已保存记录。

## 目前知道什么

| 项目 | 已有数字 | 数据类型与边界 |
|---|---:|---|
| 原尺寸候选网格 | 272×4×14 = 15,232 cells | derived 计数；来自原尺寸台账，不代表已经生成网格 |
| 模式清单 | 32,060 个传播模式 | measured 清单；ordered-key SHA 03c1965c…e95dec，没有 FE 求解 |
| 候选 p6 行数 | full storage 10,228,620；periodic independent 9,948,672；interior 6,854,400；trace 加 actual AUTO ports 3,126,332 | derived 行数；端口模式数为 32,060 |
| 候选稀疏项 | 实际 NNZ 与 CSR indptr 末值未知 | 没有目标矩阵；不能从行数或旧案例 NNZ 外推 int32 安全 |
| 完整目标资源与时间 | 2 TB / 48 h 均未资格化 | q 因子填充、同时存活工作区、target KSP、恢复和输出均未知 |

原尺寸候选把 x 方向分成 78/58/58/78 个子区间，其他轴只是计数用的 4 和 14 个单元。按总长度除以单元数得到的名义均值是 h_x=0.1838 nm、h_y=6.25 nm、h_z=10 nm；这些不是实际每个单元的 h。x 各段平均宽度约为 0.2115、0.1466、0.1466、0.2115 nm。目标轴节点没有生成，所以每个局部单元宽度、边界拟合及极值仍未知。

用真空波数 k0=2π/0.7=8.97598 nm⁻¹ 乘以盒子长度，得到 k0Lx≈448.80、k0Ly≈224.40、k0Lz≈1256.64。按上述名义平均宽度换算的自由空间相位约为 x 各段 1.90/1.32/1.32/1.90 rad、y 56.10 rad、z 89.76 rad。它们只是从尺寸和计数推出的电尺寸诊断，不是有限元精度结论；真实轴和材料相位均未知。尤其 y/z 的候选分辨率没有 h/p 资格，不能因 x 有大量细分就称原尺寸模型已经解析。

## 下一单一电尺寸候选：E1 q1.25（保持 HELD）

为让下一轮只比较一个同波长电尺寸增长点，本包记录了现有 E1 输入和精确轴计划，但不把它变成可直接启动的授权。波长仍为 0.7 nm；输入文件 input/task40extra_0p7nm_engineering/nonseparable_e1_p6_q4_manual_m2_growth.dat，SHA256 5c0aa01d1bb327f1331b69cfe359c6f775961398d316c2f88d3aeaff978af8fd；几何身份 task40extra_nonseparable_0p7nm_e1_q1p25_v1；轴计划 10×4×19，计划 760 cells。mesh plan SHA256 为 b266e571b422d176521f42296739358092dc32d5c9b22a16c9f854d84c659e4e。实际网格、传播模式数和资源测量均为未知；输入中的手动模式边界是 |m|≤10、|n|≤3，不能据此声称实际传播模式计数。

当前 V13 case allowlist 只接通 B0、Gx560 和 Gx784，没有 E1 run identity 的完整 reference-PC 路由。因此此输入虽存在，端到端 launch route 尚未获审查接线。本次不扩充 allowlist、不启动 FE/PDE；E1 保持 HELD，且依赖后续先为 Gx560 physical action identity 门形成可审查闭环。

## 从本轮结果能得出的结论

Gx560 的启动、四个 q 数值因子和完整参考检查消耗了实测时间与内存，但它在进入 Full3D target solve 前被不可放宽的 action-identity 门挡住。因此现有证据不能判断原尺寸的主要成本会是装配、因子填充还是 Krylov 迭代。Gx560 的资源和时间门通过，只能说明这次失败不是内存或时间受控停止。

目标准入必须同时检查 p6 行数、实际矩阵 NNZ 和 CSR indptr，并核算四个 q 因子及它们的 workspace 是否同时存活。现有 int32 行数低于上限并不足以证明最终稀疏索引安全；target NNZ 和 indptr 仍为空。台账中的 74 个外层向量约 3.70 GB、保留场 scratch 约 4.43 GB、一个完整稠密 H 矩阵约 16.45 GB，都是公式导出的 payload，不是同一时刻 RSS，也不含真实填充和全部对象生命周期。

## 下一次审查的入口

当前决定为 NO_GO / NOT_QUALIFIED，表示还没有完成目标级精度、资源和端到端时间资格，不表示数学上不可能。下一次审查需要先给出保持同一解析几何与材料身份的明确目标轴，以及 y/z 可解释的 h/p 选择；随后在正式组装前核验 rows、NNZ、indptr 和有界资源余量。只有 Gx560 的物理 RHS action identity 门另获可审查的数值闭环后，才有依据考虑目标级 PDE。此包不授权新运行，也不声称存在可直接启动的原尺寸 one-command runner。

详细的数字、来源 hash 和 unknown 字段见 [V14 结构化目标桥接记录](v14_engineering_to_target.json)；原始模式与资源清单见 [target ledger](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/target_ledger.json) 和 [resource ledger](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/target_resource_ledger.json)。
