# 小尺寸 flat-layer 补充验证

## 背景

用户指出 Stage 4A flat-layer 不需要 `100 nm x 100 nm` 横向周期。平坦界面没有横向结构，横向尺寸只会影响 DtN auto 模态数量和求解规模。因此本补充验证把计算域缩小为：

- `period_x = 10 nm`
- `period_y = 10 nm`
- `air_height = 5 nm`
- `substrate_thickness = 5 nm`
- 总尺寸 `10 nm x 10 nm x 10 nm`

其余物理参数保持不变：`lambda0 = 13.5 nm`，`n_substrate = 0.999002304859 + 0.00182649365j`，normal incidence，s polarization，`stage4_boundary_model = dtn_port`，`stage4_dtn_order_policy = auto_propagating`。

## 运行目的

这组验证用于区分两个问题：

1. 原先大 cell 中 `port` 近似全反射是否来自物理或端口公式。
2. 横向周期过大导致 auto_propagating 选入大量传播级次后，是否放大了粗网格和直接求解问题。

## 网格序列

网格尺寸按 `lambda0/N` 的想法选取，但采用便于输入的近似值：

| run | mesh_target_nm | 约等于 | cells | DoF | DtN aux modes |
|---|---:|---|---:|---:|---:|
| small_cell_h2p7 | 2.7 | `lambda0/5` | 64 | 300 | 4 |
| small_cell_h2 | 2.0 | `lambda0/6.75` | 150 | 636 | 4 |
| small_cell_h1p5 | 1.5 | `lambda0/9` | 392 | 1520 | 4 |
| small_cell_h1 | 1.0 | `lambda0/13.5` | 1000 | 3630 | 4 |

横向周期缩小到 10 nm 后，auto_propagating 只保留零级 x/y 四个端口模态。原 100 nm cell 的同一策略会选出 708 个 auxiliary port modes。

## Port / Volume 收敛

| mesh_nm | R_port | T_port | A_port | A_volume | R_ref | T_ref | A_ref | dR | dT | dA | closure |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.7 | 3.169e-03 | 9.894e-01 | 7.418e-03 | 7.418e-03 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 3.168e-03 | -2.122e-03 | -1.047e-03 | -1.55e-15 |
| 2.0 | 5.938e-04 | 9.915e-01 | 7.938e-03 | 7.938e-03 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 5.927e-04 | -6.610e-05 | -5.266e-04 | -8.55e-15 |
| 1.5 | 1.755e-04 | 9.917e-01 | 8.155e-03 | 8.155e-03 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 1.744e-04 | 1.359e-04 | -3.103e-04 | -1.11e-16 |
| 1.0 | 6.616e-05 | 9.917e-01 | 8.262e-03 | 8.262e-03 | 1.084e-06 | 9.915e-01 | 8.465e-03 | 6.507e-05 | 1.380e-04 | -2.030e-04 | -2.22e-15 |

结论：

- `port` 不再全反射。
- `R_port` 随网格细化持续下降，从 `3.17e-3` 降到 `6.62e-5`。
- `T_port` 在 `h=2.0 nm` 起已经非常接近解析端口面参考。
- `R_port + T_port + A_volume - 1` 始终为机器精度量级，说明 port 与 volume absorption 的能量闭合已经稳定。

## Probe / Net Flux 诊断

| mesh_nm | R_probe | T_probe | A_probe | R_flux | T_flux | A_flux |
|---:|---:|---:|---:|---:|---:|---:|
| 2.7 | 1.598e-03 | 8.111e-01 | 1.873e-01 | 1.867e-01 | 8.090e-01 | 4.354e-03 |
| 2.0 | 6.923e-03 | 9.137e-01 | 7.938e-02 | 9.168e-02 | 9.024e-01 | 5.889e-03 |
| 1.5 | 3.703e-03 | 9.433e-01 | 5.299e-02 | 5.356e-02 | 9.405e-01 | 5.968e-03 |
| 1.0 | 3.750e-03 | 9.622e-01 | 3.407e-02 | 3.491e-02 | 9.595e-01 | 5.543e-03 |

probe/net_flux 明显随网格改善，但仍没有达到 port/volume 的一致程度。analytic-only 测试已经证明 probe/net_flux 公式本身在解析场输入下是正确的，因此当前偏差更像是 FEM 场采样、FE curl 重构和低阶 p1 体场误差，而不是 R/T/A 公式错误。

## 对“全反射”的判断

原 100 nm cell 的 h=10 结果出现近似全反射。小 cell 补充验证显示：

- 只要把横向周期缩小到 10 nm，并用 `h≈lambda0/5` 或更细网格，`port` 全反射就消失。
- auto_propagating 模态数从 708 降到 4，求解不再被大量横向传播级次拖累。
- 端口与体吸收闭合一直保持机器精度。

因此，原先 h=10 大 cell 的全反射不是 flat interface 的物理结果，也不是 `A_volume` 闭合公式本身的问题，而是大横向周期 + 粗 p1 网格 + 多传播端口模态共同造成的数值诊断失败。

## 当前建议

后续 Stage 4A flat-layer 校准应优先使用 small-cell setup：

```text
period_x = period_y = 10 nm
air_height = substrate_thickness = 5 nm
mesh_target_size = 2.0, 1.5, 1.0 nm
```

后续运行命令应保留默认 unique output，不再添加 `--no-unique-output`。这样每个 case 会在本地 `results/3D_*_YYYYMMDD_HHMMSS/` 下保留完整结果；`outcomes/raw_runs/` 只复制轻量 JSON/TXT/CSV 摘要。

在 small-cell 下，`port` 与 `volume_absorption` 已经可以作为主线能量闭合检查。`probe_eh_fourier` 和 `net_flux` 仍建议保留为 diagnostic only，下一轮重点应继续查 FEM 采样和 curl 后处理误差。
