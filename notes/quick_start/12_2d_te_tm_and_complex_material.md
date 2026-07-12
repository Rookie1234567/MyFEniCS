# 2D TE/TM 与复折射率吸收教程

## 1. 功能与物理图景

TM 路径求解面内矢量 `E=(Ex,Ey)`，使用 N1curl；TE 路径求解标量 `Ez`，使用 Lagrange。两者是不同偏振的降维方程，不能在非等价条件下直接比较场分量，但都可用复折射率描述吸收。

## 2. 当前能力状态

| 能力 | 状态 |
|---|---|
| complex `n` CLI | 支持 `1.45`、`a+bj`、`a+bi` |
| TM auxiliary DtN lossy power | canonical Case003 |
| TE scalar DtN lossy power | canonical Case003；当前为 trace/explicit modal path |
| probe | diagnostic_only |
| arbitrary material database convention | 用户必须核对符号 |

## 3. 运行前提

项目时间约定为 `exp(-i omega t)`，输入是折射率 `n`，内部计算 `epsilon_r=n^2`。本项目当前采用正 `Im(epsilon_r)` 表示吸收；若外部数据库给出相反约定，先转换。

## 4. PyCharm presets

```python
ACTIVE_PYCHARM_PRESET = "2d_complex_absorption"  # TM canonical geometry
ACTIVE_PYCHARM_PRESET = "2d_te_port_smoke"       # TE 路径 smoke
```

Case003 的 TE canonical 参数由 case config/run 脚本冻结，不等同于 Robin `2d_te_port_smoke`。

## 5. `main.py` 修改位置

TM 有损 preset 是：

```python
replace(
    _TM_DTN_AUX_2D,
    n_substrate=0.999002304859 + 0.00182649365j,
    n_grating=0.999002304859 + 0.00182649365j,
)
```

TE 通过 `polarization_type="TE"` 进入 `solve_te_maxwell`，不是把 TM 矢量的某个分量设为零。

## 6. 完整 Case003 参数块

| 量 | TM | TE |
|---|---:|---:|
| period | 100 nm | 10 nm |
| air/substrate | 100/50 nm | 5/5 nm |
| degree | 2 | 1 |
| h | 3 nm quad | 2 nm triangle |
| angle | 0° | 15° |
| DtN | auxiliary, auto orders | scalar trace, order 0 |
| lossy `n` | `0.999002304859+0.00182649365j` | 同左 |

完整机器可读值见 Case003 `config.json`。

## 7. 参数含义和合法值

| 参数 | 含义 | 注意 |
|---|---|---|
| `n_air/substrate/grating` | 复折射率 | 不是 epsilon |
| `polarization_type` | `TM`/`TE` | 选择不同 FE 空间和方程 |
| `port_use_diffraction_orders` | 自动传播阶 | TM 大周期可产生多个阶 |
| `air_height/substrate_thickness` | port plane 距离 | 有损传播会改变实际平面振幅 |
| `port_rayleigh_tolerance` | cutoff 邻域 | 不应用 `Im(beta)==0` 判传播 |

## 8. Qualification 边界

Case003 证明两个冻结案例的 residual、非负 R/T/A、`A_balance≈A_volume` 与能量闭合；不证明所有角度、材料、period 或 near-Rayleigh 情况。

## 9. CLI 等价命令

```text
python src/main.py --preset 2d_complex_absorption
SOURCE_COMMIT=<sha> sh benchmarks/cases/003_2d_te_tm_complex_absorption/run.sh
```

CLI 复数示例：

```text
--n-substrate 0.999002304859+0.00182649365j
--n-grating 0.999002304859+0.00182649365i
```

## 10. 真实调用链

```text
TM: run_cases::main -> solve_port_maxwell::run_port_case
    -> compute_dtn_auxiliary_power_metrics
TE: run_cases::main -> solve_te_maxwell::run_te_port_case
    -> compute_te_dtn_port_power_metrics
Both -> power_metrics::_volume_absorption_metrics
```

## 11. 输出与关键字段

Case003 records 位于：

```text
benchmarks/cases/003_2d_te_tm_complex_absorption/records/
├── tm_complex_absorption.json
└── te_complex_absorption.json
```

重点读 `physical_model`、`solver.linear_true_residual`、`official_rta`、`diagnostic_probe`、RSS 和 artifact provenance。

## 12. 当前 canonical 结果

| 案例 | DoF | residual | R | T | A_volume | closure |
|---|---:|---:|---:|---:|---:|---:|
| TM | 14,452 + 30 aux | 3.323e-14 | 3.663e-6 | 0.88217245 | 0.11782389 | -3.33e-15 |
| TE | 56 | 1.486e-15 | 8.746e-5 | 0.99034578 | 0.00956676 | 5.83e-16 |

TM auxiliary-vs-trace 最大差为 `1.22e-15`。

## 13. 成功 Gate

```text
linear residual <= 1e-10
R,T,A_volume >= 0
abs(1-R-T-A_volume) <= 1e-8
abs(A_balance-A_volume) <= 1e-8
TM auxiliary-vs-trace <= 1e-8
probe identity = diagnostic_only
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| T 被算成 0、A_balance 接近 1 | complex beta 被误判为 evanescent |
| 撤销有限层吸收 | 功率用了 reference-plane amplitude 而非 port-plane coefficient |
| `A_volume<0` | 材料符号约定或标签错误 |
| TM/TE 场值差很大 | 两个偏振本来不等价 |
| probe 不闭合 | 采样诊断误差；不能覆盖 official |

## 15. 改成自己的材料

先固定几何和网格，只替换 `n`，检查 `epsilon=n^2` 的虚部符号。随后分别做 port 距离和网格收敛，确保 A_balance 与 A_volume 不依赖人为截断位置。

## 16. 链接

- RTA 理论：[`../theory/official_and_diagnostic_rta_methods.md`](../theory/official_and_diagnostic_rta_methods.md)
- 2D 代码：[`../reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md`](../reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md)
- Case003：[`../../benchmarks/cases/003_2d_te_tm_complex_absorption/README.md`](../../benchmarks/cases/003_2d_te_tm_complex_absorption/README.md)
