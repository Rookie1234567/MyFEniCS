# Task035b 参考解与资源目标

## 权威边界

```text
geometry = Task034 fixed rectangular block grating
wavelength = 13.5 nm
incidence = 10 degree grazing
polarization = S
formal_MPI = 8
continuum_reference = false
ordinary_default_changed = false
```

Task035b 的同误差判定以同代码、完整 observable vector 和冻结场探针为准。
COMSOL direct-solver 表提供独立软件的高阶收敛趋势，但其 Lagrange 阶次、网格
尺寸、DoF 和内存口径与 FEniCS Nédélec/MPI process-tree authority 不等价。

## COMSOL direct 高阶趋势

COMSOL 原始 saved-solution 数据给出的代表性高阶点为：

| direct point | DoF | R00 | R | T | Aclosure |
|---|---:|---:|---:|---:|---:|
| p4 hexa h2 | 4,818,792 | 0.000752895 | 0.000762014 | 0.602707488 | 0.396530498 |
| p4 tetra h3 | 4,323,924 | 0.000752897 | 0.000762016 | 0.602707468 | 0.396530516 |
| p5 tetra h6 | 927,150 | 0.000752911 | 0.000762030 | 0.602707265 | 0.396530705 |
| p6 hexa h7.5 | 488,150 | 0.000752896 | 0.000762015 | 0.602707484 | 0.396530501 |
| p6 tetra h7 | 950,924 | 0.000752895 | 0.000762014 | 0.602707512 | 0.396530474 |

由这些不同拓扑和阶次序列派生的趋势中心为
`R00≈0.000752895 / R≈0.000762014 / T≈0.6027075 /
Aclosure≈0.3965305`。这不是 continuum truth。COMSOL p5 hexa 的 R/T
支持趋势，但其 `R+T+A≈0.9998974`，不作为吸收率权威；COMSOL 内存也是
solver-history 结束值，不是独立 process-tree peak。

来源：
`docs/COMSOL_direct_solver_report.md`，SHA-256
`80d32c80f28f0bcc87470881f639bbbfe54b468b7a7da53c31a26b3785cd6ec4`。

## 冻结的 FEniCS global-p 基线

h10 structured hexa 为 `(6,3,14)`、252 cells，mesh/cell-tag/facet-tag
SHA-256 分别为：

```text
f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857
42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131
0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd
```

| baseline | FE DoF | active rows | matrix NNZ | factor NNZ | R00 | R | T | Aclosure | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| p4/h10 | 53,084 | 21,824 | 8,184,464 | 40,151,936 | 0.001872160506 | 0.001882317215 | 0.596619519622 | 0.401498163163 | `2.35e-11` |
| p5/h10 | 101,815 | 35,000 | 20,140,928 | 101,062,900 | 0.000785714089 | 0.000794886060 | 0.602483953885 | 0.396721160055 | `1.25e-11` |
| p6/h10 | 173,802 | 51,272 | 41,989,040 | 202,441,352 | 0.000753761220 | 0.000762881475 | 0.602701633986 | 0.396535484539 | `1.26e-11` |

p6/h10 是 best available global-p discrete reference，不是 continuum
reference。COMSOL p6/h10 的 `173,882 DoF` 与 FEniCS 的
`173,802 FE DoF + 80 DtN rows` 数值相同只是巧合，不表示离散体系等价。

最新 exact-preallocation p5/p6 record 的 build、MUMPS setup、solve 分别为
`24.72/36.48/0.077 s` 与 `102.32/102.54/0.167 s`；完整 projection pair
峰值 `19.977 GiB`。这些时间不能与旧 source 上的未优化记录直接解释为纯
p 阶倍率。

## Significant channel reference v1

Review V1 已将 12 个显著通道的 best-available same-code 参考冻结为：

```text
record = significant_channel_reference_v1.json
record SHA-256 = 83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3
reference center = global structured-hexa p6/h10 MPI8
status = significant_channel_reference_v1_frozen
canonical = false
production_qualified = false
new PDE run = false
```

12 个通道全部为 `n=0`、S polarization，并由
`m=0,-1,-2,-4,-5,-7` 的上下端口各 6 个通道组成。机械聚合得到 11 个
`reference_converged_monotone_p_and_h` 和 1 个
`reference_converged_with_bounded_final_h_confirmation`；没有把它们提升为
continuum truth。COMSOL 只提供 scalar `R00/R/T` 跨软件趋势，不含逐通道
复振幅，因此没有进入 channel band。

reference v1 的 numerical convergence bands 用于描述 p/h spread，但正式
候选 Gate 仍使用预先冻结的 h10 p5→p6 absolute correction。也就是说：

```text
reference v1 frozen != production reference
reference v1 frozen != threshold relaxation
```

## Same-error 合同

正式 scalar bands 来自同一 h10 p5/p6 control：

| Gate | tolerance |
|---|---:|
| strict R00 | `3.1952869e-5` |
| strict R | `3.2004585e-5` |
| T | `2.1768010e-4` |
| Aclosure | `1.8567552e-4` |
| normalized R/T/Aclosure | `<=sqrt(3)` |
| full explicit true residual | `<=1e-9` |

候选还必须逐项通过 significant diffraction power、complex amplitudes、
selected volume/interface field errors、periodic/tag/orientation/geometry
identity 和实测资源 Gate。DoF 或 scalar-only pass 不能补偿其他失败。

## 13.5 nm 资源目标与当前结果

| target | contract | 当前状态 |
|---|---|---|
| minimum | `N_equiv<=90,000` | h15、directional h14/h13、R5-slab 和两个 regionwise 点达到 DoF 门槛，但均未通过完整精度 Gate |
| preferred | `65,000–75,000` | fixed p5-trace/p6-interior h15 为 74,890，但只有 6/12 power、7/12 amplitude |
| stretch | `<=60,000` 且所有 Gate 不放宽 | 未达到 |
| Hybrid selection | 完整 same-error + resource pass | 0 个候选 |

Review V1 恢复序列的统一状态为：

| candidate | Full3D-equivalent DoF / rows | matrix / factor NNZ | peak | significant power / amplitude | decision |
|---|---:|---:|---:|---:|---|
| global p6/h15 | 84,492 / 24,704 | 19,207,136 / 59,616,320 | 12.000 GiB pair | 6/12；8/12 | controlled negative |
| fixed p5-trace/p6-interior h15 | 74,890 / 16,880 | 9,195,812 / 27,916,600 | 5.803 GiB | 6/12；7/12 | controlled negative |
| fixed directional-z h14 | 82,315 / 18,500 | 10,104,512 / 31,347,000 | 6.376 GiB | 7/12；9/12 | positive z signal；仍 negative |
| fixed directional-z h13 | 89,740 / 20,120 | 11,013,212 / 36,273,200 | 6.411 GiB | **10/12；10/12** | 最佳预算内实测点；仍 negative |
| h13 top2 z redistribution | 89,740 / 20,120 | 11,013,212 / 36,273,200 | 5.886 GiB | 8/12；8/12 | bounded controlled negative |
| h14 exact-reverse h13 top2 | 82,315 / 18,500 | 10,104,512 / 32,338,600 | 5.958 GiB | 7/12；8/12 | second bounded negative；z-node lane closed |
| h14 R5-slab bisect | 89,740 / 20,120 | 11,013,212 / 36,273,200 | 6.463 GiB | 5/12；9/12 | count regression；预先指定 R5-slab lane closed |
| global p6/h14 trace discriminator | 92,850 / 27,080 | 21,110,096 / 67,325,792 | 12.587 GiB pair | 9/12；12/12 | 超 cap 2,850；diagnostic only |

这些点均通过 scalar/vector、selected field/interface、full residual 和
geometry/tag/periodic/orientation identity。h13 仍失败
`T(-4,0)`、`R(-4,0)` 功率以及 `r(-5,0)`、`r(-4,0)` 复振幅，因此
“最佳测得”不等于 eligible。global p6/h14 说明完整 trace 对复振幅有正
信号，但超过 90k 且功率仍未全过。physical expansion、periodic/Floquet
orbit、Stage4 row omission 和 owner-aware MatShell 已通过
fixture/correctness qualification，但 actual residual-weighted channel
DWR、formal runner、candidate 和 PDE 数量仍为 0。当前仍没有合法
selected `N_equiv,13.5`。

Review V2 已完成三个 programmatic MPI8 assembled iterative screen：
GMRES/Jacobi、FGMRES/ASM-ILU 与 physical z-slab ILU0 + DtN trace correction
均在 200 iterations 以 `DIVERGED_MAX_IT` 停止，full recovered residual
分别约为 `0.861661`、`0.999659` 和 `0.996263`。三者没有 official
R/T/A/channel 输出；后两者还含 local factor，不能称为 strictly
factorless。其 3.921/4.462/3.885 GiB peak 只属于失败证据，不能降低正式
资源目标。

同一 h15 direct rank study 的 MPI1/2/4/8 process-tree peaks 为
1.295/2.158/3.100/4.711 GiB。MPI1 是当前最低实测 direct 点，不是理论或
factor-free 下限。h15/h13 canonical setup 的 non-KSP cold/warm build 为
19.242/6.141 s 与 19.410/6.696 s；这些 setup/resource authority 不替代
12-channel accuracy authority。

## 0.7 nm 规划映射

仅作敏感性分析：

```text
s^3 = (13.5 / 0.7)^3 = 7173.104956268225
N_local,0.7 = N_equiv,13.5 * s^3 * f_H
```

| N_equiv,13.5 | f_H=.30 | f_H=.35 | f_H=.40 |
|---:|---:|---:|---:|
| 90,000 | 193.674 M | 225.953 M | 258.232 M |
| 75,000 | 161.395 M | 188.294 M | 215.193 M |
| 70,000 | 150.635 M | 175.741 M | 200.847 M |
| 65,000 | 139.876 M | 163.188 M | 186.501 M |

`f_H=0.40` 是未知未来几何的保守规划系数，不授权不规则几何 PDE。由于
selected candidate 为空，上表没有 accuracy credit，也不能证明 2 TiB
production layout 可行。
