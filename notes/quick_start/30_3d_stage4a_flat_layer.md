# 3D Stage 4A 平层 DtN

```bash
python src/main.py --preset 3d_stage4a_flat_layer_direct
```

该 preset 使用 10 nm x 10 nm 周期截面、空气 5 nm、基座 5 nm、波长 13.5 nm 和 h=2 nm。平界面横向尺寸不会改变解析 Fresnel 系数，但会改变离散 DoF 和归一化端口面积，因此小尺寸适合诊断。

Stage 4A 首次把双 Floquet、分层 total-field 背景、上下 Fourier-DtN、复基座和 3D RTA 放在同一系统中。它没有几何光栅。

## 必查恒等式

| 项 | 目的 |
|---|---|
| 数值 DtN R/T 对解析 Fresnel R/T | 端口方向、归一化和背景场 |
| `A_balance=1-R-T` 对 `A_volume` | 吸收实现与端口功率闭合 |
| auxiliary 幅值对边界 trace | 增广耦合符号 |
| 网格 h=2/1.9/更细 | 排除单一网格偶然一致 |

如果出现“全反射”，先核查端口法向、纵向波数根号分支、底端口 admittance、基座复折射率符号和入射/反射幅值定义，不要先调求解器。

理论见 [`../theory/dtn_modal_ports_and_condensation.md`](../theory/dtn_modal_ports_and_condensation.md) 与 [`../theory/official_and_diagnostic_rta_methods.md`](../theory/official_and_diagnostic_rta_methods.md)。
