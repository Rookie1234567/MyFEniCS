# Hybrid FEM–modal 与直接 3D FEM 对比

## 2026-07-17 新增 p3/h5 同阶比较

此前只有 p2/h5、p2/h3；现在新增同物理模型、同 p3、同 h5 的正式比较：

| 方法 | rows / 主 FE DoF | assembled NNZ | true residual | memory authority | wall time | R | T | A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| full3D p3 direct | 145,943 / 145,863 | 35,566,727 | `5.442e-12` | 7.781 GiB | 103.59 s | 0.001090107012 | 0.600622478293 | 0.398287414695 |
| Hybrid p3 M160 Schur-minimal | local 21,847×2 + modal 320 | local 5,156,503×2 | `2.343e-12` | 2.618 GiB | 111.94 s | 0.001090095685 | 0.600622368221 | 0.398287536094 |

Hybrid 相对 direct 的峰值内存为 `0.336×`，即约降低 66.35%。由于两条路径的
矩阵分块语义不同，不把 local NNZ 与 full3D NNZ 直接相除作为统一稀疏规模比。
Hybrid/full3D 墙钟比为 `1.081×`，即 Hybrid 约慢 8.1%；因此当前尺度只证明
内存收益，没有证明 wall-clock speedup。
物理差异的最大 R/T/A 绝对值为 `1.214e-7`，体吸收差为 `1.214e-7`；
五截面最大 E/H 相对 L2 为 `1.100e-5 / 1.098e-4`。这证明当前 p3/h5
离散的一致性，但 direct reference 仍为 `grid_converged=false`，不升级为连续解
或 h 收敛证明。

p4/h5 未形成 target 解：四模态迹组件通过，但 direct base matrix 已达
155,205,040 NNZ，增广插入后外部权威值 12.616 GiB 并受控终止；Hybrid M160
资源矩阵中心/上界为 37.038/42.594 GiB。因此没有伪造 p4 同阶比较。

## 1. 可比口径

下方历史表复用 Task032 Case080 的 clean tracked records；它只讨论 p2/h5 与 p2/h3：

- 相同 13.5 nm、相同目标光栅、相同 p2、相同拟合网格；
- 直接 3D reference 的 `grid_converged=false`，所以是同离散一致性，不是连续解收敛；
- p3 的新增同阶比较见上节；p4 仍没有同阶 target reference。

`M160` 表示每个传播方向保留 160 个模态；Hybrid 内部 forward/backward 振幅共 320。
外部 Fourier-DtN 的 80 个辅助未知量不属于 M。

## 2. 代数规模与物理结果

| 网格 | 方法 | FE/local DoF | 外部 aux | 内部 `2M` | 总行数 | assembled NNZ | true residual | R | T | A |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| h5 | 直接 3D FEM p2 | 44,698 | 80 | 0 | 44,778 | 4,896,156 | `9.7340e-12` | 0.0890216029 | 0.4425882787 | 0.4683901184 |
| h5 | Hybrid p2 M160 | 6,826×2 | 40×2 | 320 | 14,052 | 2,000,624 | `2.5455e-12` | 0.0890210691 | 0.4425867427 | 0.4683921882 |
| h3 | 直接 3D FEM p2 | 198,438 | 80 | 0 | 198,518 | 21,317,860 | `9.9234e-12` | 0.0046130314 | 0.5836533572 | 0.4117336114 |
| h3 | Hybrid p2 M160 | 34,198×2 | 40×2 | 320 | 68,796 | 8,594,673 | `2.6036e-12` | 0.0046128199 | 0.5836509402 | 0.4117362399 |

| 网格 | full/Hybrid 行数比 | 行数降低 | full/Hybrid NNZ 比 | NNZ 降低 |
|---|---:|---:|---:|---:|
| h5 | 3.187× | 68.62% | 2.447× | 59.14% |
| h3 | 2.886× | 65.35% | 2.480× | 59.68% |

## 3. 同网格物理一致性

| 网格 | ΔR | ΔT | ΔA | 最大 R/T/A 绝对差 | interface E/H | 选定平面 E/H 最大误差 | Hybrid 能量闭合 |
|---|---:|---:|---:|---:|---:|---:|---:|
| h5 | `-5.3383e-7` | `-1.5359e-6` | `+2.0697e-6` | `2.0698e-6` | `2.46e-7 / 7.42e-3` | `3.20e-4 / 9.61e-4` | `1.73e-11` |
| h3 | `-2.1150e-7` | `-2.4170e-6` | `+2.6285e-6` | `2.6285e-6` | `2.50e-8 / 4.82e-4` | `9.96e-5 / 7.80e-4` | `3.27e-12` |

## 4. 时间与内存

| 网格/路径 | 总时间 | 内存说明 |
|---|---:|---|
| h5 直接 3D reference | 21.18 s | 内部 2360.7 MB 是 rank 历史峰值和，不是 simultaneous authority |
| h5 Hybrid augmented | 70.72 s | simultaneous worker RSS 1.8654 GiB |
| h5 Hybrid Schur-minimal | 60.91 s | simultaneous worker RSS 1.6977 GiB |
| h3 直接 3D reference | 79.54 s | 内部 8707.5 MB 是 rank 历史峰值和，不是 simultaneous authority |
| h3 Hybrid augmented | 102.58 s | simultaneous worker RSS 3.8526 GiB |
| h3 Hybrid Schur-minimal | 99.69 s | simultaneous worker RSS 3.2244 GiB |

direct reference 与 Hybrid memory runner 的源码提交、工作负载和遥测口径不同，不能据此计算
严格 speedup 或内存降幅。可靠结论是：Hybrid 明显降低代数行数和 NNZ；当前小规模运行
没有证明墙钟时间优于完整 3D direct。

## 5. 高阶边界与当前状态

Phase C 先在 clean source `b636444...` 完成 p3/h5 Schur-minimal
M80/M120/M160 漏斗与 augmented/minimal M160 锚点。该历史阶段的 C0 预测曾阻止
full3D；此状态现已由后续实测取代，不再是当前结论。

用户随后授权的 p3/h5 full3D 在 `bd828f24...` 上完成；Hybrid M160 在
`95921ab76...` 上绑定同一 reference NPZ 并通过 16 项 Gate。D0 source audit
进一步证明两个提交之间 12 个关键数值内核 blob 完全一致，Phase6 runner 去除
reference registry 后 AST 完全一致。因此当前 p3/h5 离散比较已正式收口，
review v5 分类为 `PASS_WITH_QUALIFICATIONS`。

资格限制仍然是：

- p3/h5 reference 为 `provisional_best_available_discrete_reference`，不是连续解；
- 没有 p3/h3 或 h 收敛证明；
- p3/h5 Hybrid 有 66.35% 峰值内存下降，但没有墙钟加速；
- p4 四模态组件通过，但目标 full3D/Hybrid 求解均被当前主机资源 Gate 阻止。
