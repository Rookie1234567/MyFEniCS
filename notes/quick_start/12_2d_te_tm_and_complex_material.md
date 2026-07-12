# 2D TE、TM 与复材料

## 模型选择

| 选择 | 未知量 | 空间 | 入口 |
|---|---|---|---|
| TM | 面内 `(E_x,E_y)` | Nedelec H(curl) | `2d_tm_*` |
| TE | 标量 `E_z` | Lagrange H1 | `2d_te_port_smoke` |

这两个是二维不变方向下的不同偏振约化，不是同一离散场换一个标签。

## 复折射率

2D CLI 现在接受：

```bash
python src/main.py 2d --formulation port --constraint-backend manual \
  --port-boundary-model dtn --n-substrate 0.999002304859+0.00182649365j \
  --n-grating 0.999002304859+0.00182649365j
```

也可直接选择 `2d_complex_absorption`。代码使用 `epsilon_r=n^2`；在项目的时间约定下，给定材料数据必须与正虚部吸收约定一致。若外部数据库使用相反号，先转换约定，不能机械粘贴。

## 必查输出

| 指标 | 说明 |
|---|---|
| `A_balance=1-R-T` | 从端口功率剩余推得 |
| `A_volume` | `Im(epsilon)|E|^2` 的材料体积分 |
| `absorption_identity_error` | 两种吸收来源之差 |

当前 DtN 自动级次会保留复基座中 `Re(beta^2)>0` 的有耗传播级，并在实际 bottom port 平面计算 T；不要把 `beta` 带虚部误判为倏逝，也不要把端口系数反向去衰减后再算功率。Task28 V2 的 TM smoke 得到 `R=3.6625e-6`、`T=0.88217245`、`A_volume=0.117823885`，闭合误差 `3.33e-15`；这是 dirty-worktree 诊断证据，不替代编号 case 的 clean canonical record。

TE/TM 弱式和符号见 [`../theory/maxwell_strong_weak_and_fem.md`](../theory/maxwell_strong_weak_and_fem.md)，吸收公式见 [`../theory/official_and_diagnostic_rta_methods.md`](../theory/official_and_diagnostic_rta_methods.md)。
