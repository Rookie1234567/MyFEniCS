# Full3D–Hybrid 同阶 closure 矩阵

所有正向点均要求 Full3D official result、Hybrid M160 formal/numeric/true-residual、
M funnel、zero swap、五平面 E/H、接口 E/H、A_volume 与衍射阶向量存在，并验证
Hybrid 对应 Full3D record 的 SHA-256 binding。checker 会重算 12 分量向量完整性，
不只信任 `status`。

| 点 | Full3D | Hybrid M160 | 同阶 closure | 说明 |
|---|---|---|---|---|
| p2/h5 | pass | pass | pass | max ΔR/T/A_volume = 2.07e-6；five-plane E/H = 3.20e-4 / 9.61e-4 |
| p2/h3 | pass | pass | pass | max ΔR/T/A_volume = 2.63e-6；five-plane E/H = 9.96e-5 / 7.80e-4 |
| p2/h2 | pass | pass | pass | max ΔR/T/A_volume = 6.01e-7；five-plane E/H = 1.16e-5 / 3.80e-4 |
| p3/h10 | pass | formal negative | not qualified | Hybrid internal H_t Gate 未通过；原始结果保留 |
| p3/h7.5 | pass | pass | pass | max ΔR/T/A_volume = 1.26e-6；five-plane E/H = 1.27e-4 / 3.50e-4 |
| p3/h5 | pass | pass | pass | max ΔR/T/A_volume = 1.21e-7；five-plane E/H = 1.10e-5 / 1.10e-4 |
| p3/h3 | pass | pass | pass | max ΔR/T/A_volume = 6.07e-9；five-plane E/H = 1.06e-6 / 2.36e-5 |
| p4/h10 | pass | pass | pass | max ΔR/T/A_volume = 1.25e-7；five-plane E/H = 3.37e-5 / 1.11e-4 |
| p4/h7.5 | pass | pass | pass | max ΔR/T/A_volume = 2.01e-8；five-plane E/H = 9.89e-6 / 3.80e-5 |
| p4/h5 | pass | pass | pass | max ΔR/T/A_volume = 1.06e-9；five-plane E/H = 2.05e-7 / 1.03e-5 |

衍射阶的 max/RMS power 与 complex-amplitude relative errors 全部原样保存在 Case093
compact record；相对误差较大的粗点未被隐藏。same-degree pass 沿用已声明的 Hybrid
16-gate closure（R/T/A、A_volume、field/interface、algebra/QEP），不另行放宽阈值。
