# Hybrid FEM–modal 与直接 3D FEM 对比

## 1. 可比口径

本表复用 Task032 Case080 的 clean tracked records。严格可比对象只有 p2/h5 与 p2/h3：

- 相同 13.5 nm、相同目标光栅、相同 p2、相同拟合网格；
- 直接 3D reference 的 `grid_converged=false`，所以是同离散一致性，不是连续解收敛；
- p3/p4 目标光栅没有同阶直接 3D reference，不参与本表。

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

## 5. 高阶边界

p3/h5/M160 曾有一个 clean-reference-disabled 的诊断运行，残差约 `2.37e-12`，但它没有
同阶 full3D reference，且不是本阶段正式 aggregate。p4 没有目标光栅 Hybrid 全链路记录。
因此这里只将 Hybrid/full3D 对比收口在 p2。
