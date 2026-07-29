# M2A 低掠射失败分析

## 结论

`LF4 = Hybrid p4/h10/M120/MPI2` 不能作为 `grazing=0.5--10°`、
`azimuth=0--90°` 的统一 low fidelity。正式 `1e-5` 能量 Gate 未改变；规定的 13 点
LF diagnostic stencil 中只有 4 点通过，9 点失败。失败形成中间方位角带，并非 incident
`m=0` 掠入射本身或真正的非零衍射级 Rayleigh crossing。

本轮所有新 PDE 绑定 clean baseline
`a0b9ae0e457b74876eb39346885d53e940ab1584`，MPI2、每 rank 一线程、zero swap，watchdog
均完成清理。Case112 原始 9 个样本没有改写；0.5° 下 azimuth=0°/15°/90° 的 LF stencil
记录复用旧证据，其中 15° 另按 p/M matrix 要求做了相同数值配置的诊断复算。

## 独立 Full3D reference

中心诊断点 `h=120 nm, w=17 nm, grazing=0.5°, azimuth=15°, S` 的独立 Full3D
static-condensed p4/h10 结果为：

| R | T | A balance | A volume | energy closure |
|---:|---:|---:|---:|---:|
| 0.8186083122 | 0.0014147086 | 0.1799769792 | 0.1799769792 | `4.92e-13` |

同点 Hybrid p4/M120 为 `R=0.8185631316`、`T=0.0014147769`、
`A_balance=0.1800220914`、`A_volume=0.1799960301`。因此 p4 的外端口响应与独立
Full3D 接近（`delta R=-4.52e-5`），但 Hybrid 自身 `A_balance-A_volume=2.606e-5`，仍然
越过原 Gate，不能重命名为 pass。

## p/M matrix

| p / M | R | A balance | energy closure | max assembled E | Gate |
|---|---:|---:|---:|---:|---|
| p4 / 80 | 0.818563073 | 0.180022152 | `-2.620e-5` | `1.242e-3` | fail energy |
| p4 / 120 | 0.818563132 | 0.180022091 | `-2.606e-5` | `1.240e-3` | fail energy |
| p4 / 160 | 0.818563134 | 0.180022089 | `-2.607e-5` | `1.240e-3` | fail energy |
| p4 / 240 | 0.818562935 | 0.180022291 | `-2.666e-5` | `1.240e-3` | fail energy |
| p5 / 120 | 0.631653305 | 0.362442761 | `-2.739e-6` | `6.620e-5` | pass |
| p6 / 120 | 0.621509085 | 0.372250707 | `7.668e-7` | `9.942e-5` | pass |

p4 的 M80--M240 响应和能量误差已收敛到同一失败值，故增加 M 不是修复。p5/p6 的能量
账本内部闭合，但它们跳到与 p4/Full3D 相差约 `delta R=-0.187/-0.197` 的另一响应分支；
这不是可信的 p-convergence。HF 在 30°/45°/60° 仍稳定于 `R≈0.621`，进一步确认该
分支差异。45° HF 还独立失败了 biorthogonality identity `1e-6` Gate。

## volume/Poynting ledger

所有量按各 run 记录的 incident normal power 归一；原始 code-unit 分项完整保存在
Case113 `energy_ledger.json`。

| source | local bottom | local top | middle volume | middle Poynting loss | A volume | closure |
|---|---:|---:|---:|---:|---:|---:|
| Hybrid p4/M120 | 0.008133717 | 0.324672167 | 0.648907707 | 0.648909888 | 0.179996030 | `-2.606e-5` |
| Hybrid p6/M120 | 0.035403861 | 0.539912084 | 1.454975118 | 1.454975119 | 0.372251474 | `7.668e-7` |

Full3D p4 volume ledger 为 grating `A=0.179035732`、substrate `A=0.000941247`，总计
`A=0.179976979`，与 Full3D port balance 在 `4.92e-13` 内一致。Hybrid p4 中间体积分与
两界面 Poynting loss 只差 `-2.181e-6` code units；总闭合失败不能归因于 M 截断，也不能
用放宽阈值处理。

## diagnostic stencil

0.5° grazing 方位扫描的能量误差为：0° `3.45e-7`、5° `-1.57e-6`、10°
`-7.73e-6`、15° `-2.61e-5`、20° `-5.85e-5`、30° `-1.83e-4`、45°
`-3.30e-4`、60° `-1.76e-4`、75° `-2.41e-5`、90° `-6.88e-9`。失败随 conical
中间方位角增强，而在两个对称端点消失。azimuth=15° 的 grazing 0.5°/0.75°/1°/2°
分别为 `-2.61e-5/-3.76e-5/-4.77e-5/-5.87e-5`，均失败。

LF 的 30° 点另失败 biorthogonality Gate；其余 LF 失败均至少包含原能量 Gate。所有
residual、exact assembled traction 继续按原阈值检查，没有删除失败状态。

## cutoff v2

中心点 incident/specular `m=0` 的 `|beta|/k0=0.0087265355=sin(0.5°)`；这只是入射波
法向波数。排除 `(m,n)=(0,0)` 后，最近非入射级为 bottom `m=-7,n=0`，
`|beta|/k0=0.2777146`。13 个 stencil 点的局部 11x11 角邻域均未出现 lossless top-port
非零级传播状态翻转，`rayleigh_crossing_in_local_angle_neighborhood=false`。

因此 V1 的旧 `near_cutoff` 标签确实混淆了 incident m0 grazing 与非零衍射级 Rayleigh
crossing。M2A 证据不支持以 Rayleigh crossing 解释失败；最强关联是低掠射下的 conical/
中间方位角 Hybrid 表示与 p 阶分支不一致。

## disposition

- LF4 全角域统一 low fidelity：**不合格**。
- p6/HF 与独立 p4 Full3D 的分支一致性：**未建立**。
- M2 Gate：**仍未通过**。
- 49 点正式 campaign、四维 bulk、surrogate、angle DOE、反演：**继续禁止**。

机器可读证据位于 `benchmarks/cases/113_task002_m2a_low_grazing_diagnostics/records/`。

