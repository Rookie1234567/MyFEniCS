# Oblique Incidence Validation

## 结论

本轮使用 `theta_from_z = 80 deg`、`phi = 0 deg`，传播方向为 +x 横向分量和 -z 向下分量；s polarization 对应电场沿 y 方向。

| item | value |
| --- | --- |
| lambda0 | 13.5 nm |
| k0 | 0.465421133865155 |
| kx | 0.458350341046137 |
| ky | 0 |
| kz | -0.0808195317433606 |
| kx/k0 | 0.984807753012208 |
| ky/k0 | 0 |
| kz/k0 | -0.17364817766693 |
| Floquet phase x | -0.600741134897984 + -0.799443612046204j |
| Floquet phase y | 1 + 0j |
| polarization | (0, 1, 0) |
| k dot E | 0 |
| DtN mode count | top=40, bottom=40, total=80 |

## 说明

- `phi=0` 时横向波矢完全在 x 方向，因此 `ky=0`。
- s polarization 的电场为 y 方向，满足 `k dot E = 0`。
- 本轮没有观察到阻断运行的 Rayleigh warning；端口模式数为 80，明显低于旧 100 x 100 nm 周期案例中的 708，主要来自周期尺寸变小后传播衍射级减少。
- 入射功率归一化正常，completed direct case 的 official `R+T+A_volume` 均闭合到约 1e-13 或更好。
