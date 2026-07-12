# 2D 衍射阶与 R/T/A 方法教程

## 1. 功能与物理图景

周期结构的切向波数为 `alpha_m=kx+2*pi*m/Lx`，纵向波数满足 `beta_m^2=k^2-alpha_m^2`。每个携带实法向功率的阶贡献 `R_m/T_m`，有损体积贡献 `A_volume`。

## 2. 当前能力状态

| 方法 | 身份 |
|---|---|
| TM auxiliary modal amplitude | official/recommended |
| TM/TE boundary trace projection | explicit reference；TE official |
| E/H probe Fourier | diagnostic_only |
| sampled net flux | diagnostic/consistency |
| volume absorption | official |

## 3. 运行前提

采样或端口面必须在横向均匀材料层中。先确认 residual 通过，再解释衍射阶。Rayleigh cutoff 邻域尚未系统资格化。

## 4. PyCharm preset

```python
ACTIVE_PYCHARM_PRESET = "2d_tm_dtn_auxiliary_smoke"
```

有损多阶示例用 `2d_complex_absorption`。

## 5. `main.py` 修改位置

关键字段位于 `Inputs2D`：

```python
port_use_diffraction_orders=True
port_dtn_order_count=2
diffraction_order_count=None
power_probe_num_points=None
```

自动 DtN 阶次与 diagnostic probe 输出阶数不是同一概念。

## 6. 参数块示例

```python
replace(
    _TM_DTN_AUX_2D,
    period_x=100.0,
    lambda0=13.5,
    incident_angle_deg=0.0,
    port_use_diffraction_orders=True,
    port_rayleigh_tolerance=1.0e-6,
    diffraction_order_count=8,
    power_probe_num_points=512,
)
```

## 7. 参数含义

| 参数 | 影响 |
|---|---|
| `period_x` | reciprocal lattice spacing |
| `incident_angle_deg` | fundamental `kx` |
| `n_*` | 各端口 `k` 与 complex beta |
| `port_use_diffraction_orders` | 自动包含明确传播阶 |
| `port_dtn_order_count` | 手动模式的最大阶 |
| `diffraction_order_count` | probe 输出阶范围 |
| `power_probe_num_points` | 诊断 Fourier 采样分辨率 |

## 8. 传播判定与有损修正

有损传播模允许 complex `beta`。代码使用 `Re(beta)>0`、`Re(beta^2)` 和 Rayleigh tolerance 判定，不能要求 `Im(beta)=0`。功率必须使用实际 port plane coefficient：

```math
P_m=L_x\,\frac{\operatorname{Re}Y_m}{2}\,|a_m(y_{port})|^2.
```

相位归一化 amplitude 只用于报告。

## 9. CLI 等价命令

```text
python src/main.py --preset 2d_complex_absorption
python benchmarks/check_benchmarks.py --no-write
```

## 10. 真实调用链

```text
solve_port_maxwell::_candidate_orders_for_side
-> solve_port_maxwell::_is_clearly_propagating
-> power_metrics::_is_propagating
-> power_metrics::_modal_power_on_plane
-> power_metrics::compute_dtn_port_power_metrics
-> power_metrics::compute_dtn_auxiliary_power_metrics
```

## 11. 输出文件

```text
dtn_port_diffraction_orders.json/csv
dtn_auxiliary_diffraction_orders.json/csv
diffraction_orders.json/csv
dtn_port_power_metrics.json
dtn_auxiliary_power_metrics.json
```

`diffraction_orders` 是 probe 诊断；每个 modal record 含 `alpha`、`beta`、admittance、传播标志、boundary amplitude 和 `R_order/T_order`。

## 12. 如何读结果

1. 检查自动选择的 top/bottom order 列表。
2. 检查 cutoff 阶是否被排除。
3. 求和 official `R_order/T_order` 得到 total。
4. 用 A_volume 做 `R+T+A` 闭合。
5. 最后才查看 probe 差异定位采样问题。

## 13. 成功 Gate

```text
所有 official power 非负
evanescent order power = 0
lossy propagating order power > 0 when excited
lossless R+T≈1
lossy R+T+A_volume≈1
auxiliary/trace 一致
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| 高阶突然出现巨大功率 | Rayleigh 邻域或归一化错误 |
| 有损透射阶被删掉 | 使用 `Im(beta)==0` 旧判据 |
| probe 与 modal 不一致 | 采样面、点数或场导数误差 |
| absolute 2D/3D power 直接比较 | 两模块省略公共常数不同，应比较归一化比例 |

## 15. 改成新周期/角度

先打印自动阶次并计算 cutoff 距离；靠近 Rayleigh 点时缩小参数步长并做双侧网格/容差检查。不要只增加 `diffraction_order_count` 就认为 DtN 算子也增加了阶数。

## 16. 链接

- 理论：[`../theory/official_and_diagnostic_rta_methods.md`](../theory/official_and_diagnostic_rta_methods.md)
- DtN：[`../theory/dtn_modal_ports_and_condensation.md`](../theory/dtn_modal_ports_and_condensation.md)
- 代码：[`../reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md`](../reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md)
- Case002/003：[`../../benchmarks/cases/README.md`](../../benchmarks/cases/README.md)
