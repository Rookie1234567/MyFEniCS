# 2D 衍射与 RTA 方法选择

## 优先级

| 方法 | 数据来源 | 定位 |
|---|---|---|
| DtN auxiliary amplitude | 线性系统中的端口辅助未知量 | DtN 正式功率 |
| DtN trace projection | FE 边界迹的 Fourier 投影 | 独立交叉检查 |
| plane probe modal | 域内水平线采样后 Fourier 分解 | 诊断、对探针位置敏感 |
| net Poynting flux | E/H 线积分 | 守恒诊断 |
| volume absorption | 损耗材料体积分 | 正式吸收 |

## 读取规则

1. 先看与本次边界模型同源的 official 字段。
2. 再看 trace/probe/Poynting 是否支持相同结论。
3. 对无损材料检查 `R+T`；对有损材料检查 `R+T+A_volume`。
4. Rayleigh 截止附近注明传播级分类容差。
5. 网格、探针位置和 Fourier 采样数变化后重新比较。

## 衍射级

横向波数为 `alpha_m=kx+2*pi*m/Lx`。只有纵向传播常数满足传播判据的级次贡献远场实功率；倏逝级仍影响近场和 DtN 边界算子，但不应被当作远场 R/T。

字段定义、归一化和常见混淆全部集中在 [`../theory/official_and_diagnostic_rta_methods.md`](../theory/official_and_diagnostic_rta_methods.md)。对应实现为 `postprocessing/power_metrics.py`。
