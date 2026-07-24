# Case095：高阶 local-hp 资源包络

本 case 只研究 Task034 的 fixed rectangular block grating。它不创建、不运行
任何不规则几何；相关原 Task035b G1/G2/Phase F 条目均为
`out_of_scope_by_user / not_run / not_a_completion_gate`。

## 当前目标

- 在同一实际 mesh instance 和同一 mesh/cell-tag/facet-tag hash 上运行
  global p4/p5/p6；
- 保存 H(curl) edge、face-interior、cell-interior DoF 分解；
- 实测 augmented rows、NNZ、average/max row width、MUMPS factor NNZ/fill、
  simultaneous peak memory 和分阶段时间；
- 未启用 condensation 的 global-p records 继续把 trace rows 报告为
  `derived_not_measured`；opt-in exact Schur record 报告实测 active rows；
- ordinary default 保持不变。

## 固定网格身份

当前 structured hexa h10 网格为 `(6, 3, 14)`、252 cells，所有材料面
严格对齐：

- mesh SHA-256:
  `f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857`
- cell-tag SHA-256:
  `42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131`
- facet-tag SHA-256:
  `0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd`

## 已完成 formal records

| record | source SHA | 状态 | simultaneous peak |
|---|---|---|---:|
| `records/global_hexa_p4_p5_h10_mpi8.json` | `2e91d2bf0195056e55be670af226b7716096284c` | `actual_global_r5_pass` | 14.928 GiB |
| `records/global_hexa_p5_p6_h10_mpi8.json` | `c1040a0197d3e113576c9dc1e8d3ae13a5fa66b2` | `actual_global_r5_pass` | 35.024 GiB |
| `records/global_hexa_p5_p6_h10_p6_condensed_mpi8.json` | `0f4b786d618c37e1c572a4f596a9235e53d73161` | `actual_global_r5_pass` | 29.212 GiB |
| `records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json` | `0f8924ac4bacc8a17dc67fb0af2871ea61471c56` | `actual_global_r5_pass` | 15.964 GiB |
| `records/global_hexa_p4_p5_h10_assembly_time_condensed_independent_mpi8.json` | `a5cf24758e31143d25ddb8ae8cb2e731abfffdae` | `actual_global_r5_pass` | 10.590 GiB |
| `records/global_hexa_p5_p6_h10_assembly_time_condensed_independent_mpi8.json` | `e9d35bb77636302e18112bf1ab81fdc40f64efba` | `actual_global_r5_pass` | 20.581 GiB |
| `records/same_mesh_p4_p5_p6_r5_hp_classifier_mpi8.json` | record commit `650fc141` | `same_mesh_hp_classifier_pass` | lightweight |
| `records/regionwise_p4trace_p6interior_h10_mpi8.json` | `eb1742dde4d31c54cf66fc5d2d1d37203f9f7e34` | `actual_regionwise_p_controlled_negative` | 6.072 GiB |

p5/h10 的 101,815 FE DoF 分解为 edge 5,335、face-interior 36,000、
cell-interior 60,480；加 80 个 DtN auxiliary 后实测为 101,895 rows。
理论上消去全部 cell-interior 后为 41,415 rows（2.460x row projection），
但这不是当前矩阵实测值。

p6/h10 的 173,802 FE DoF 分解为 edge 6,402、face-interior 54,000、
cell-interior 113,400；加 80 个 DtN auxiliary 后实测为 173,882 rows。
理论上消去全部 cell-interior 后为 60,482 rows（2.875x row projection），
同样只是 `derived_not_measured`，不能当作已实现的静态凝聚结果。

## MPI8 global-p5/p6 资源对照

| degree | FE DoF | rows | NNZ | avg/max row width | factor NNZ | fill | assembly | factor/setup | solve | total |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| p5 | 101,815 | 101,895 | 79,436,433 | 779.6 / 2,260 | 166,314,925 | 2.094 | 531.6 s | 47.5 s | 0.13 s | 588.7 s |
| p6 | 173,802 | 173,882 | 210,353,120 | 1,209.7 / 3,672 | 386,625,292 | 1.838 | 2,265.9 s | 166.3 s | 0.32 s | 2,526.7 s |

p6 相对 p5 只有 1.706x rows，但有 2.648x matrix NNZ、2.325x factor
NNZ、4.262x assembly time 和 4.292x total time。当前 p6 慢的主因是高阶
cell tensor/积分和全矩阵装配，不是 MUMPS solve。

p6 的 full explicit true residual 为 `2.018e-11`，官方
`R/T/A_volume = 0.000762881475 / 0.602701633983 / 0.396535484542`；
与 COMSOL 直接法收敛中心
`0.000762014 / 0.6027075 / 0.3965305` 的绝对差分别为
`8.67e-7 / 5.87e-6 / 4.98e-6`。因此它作为 Task035b 的可信
global-p6 基线保留，但不把 COMSOL 值当作同离散系统的逐位等价结果。

## MPI8 p6 exact cell-interior condensation

Task035b 已实现 opt-in exact per-cell Schur path。它真正求解 60,482-row
trace + auxiliary 系统，不保留完整 p6 矩阵后把系数设零，也不保存所有 cell
dense factors。恢复后的完整 173,882-row augmented operator 用于 full explicit
true-residual Gate 和 official R/T/A。

| metric | global p6 full | p6 condensed | change |
|---|---:|---:|---:|
| active rows | 173,882 | 60,482 | -65.22% |
| matrix NNZ | 210,353,120 | 52,058,162 | -75.25% |
| factor NNZ | 386,625,292 | 243,270,308 | -37.08% |
| factor fill | 1.838 | 4.673 | +154.25% |
| formal memory authority | 35.024 GiB | 29.212 GiB | -16.59% |
| p6 elapsed | 2,526.7 s | 2,495.3 s | -31.4 s |

condensed p6 的 Schur build 为 84.69 s，其中 final parallel assembly
57.99 s；recovery 为 7.75 s。full p6 base matrix assembly 仍需
2,195.58 s，因此当前原型的主要时间和峰值仍来自完整高阶装配。行数下降没有
转化成同倍率内存下降的直接证据是：Schur fill 从 1.838 上升到 4.673，
factor NNZ 只下降 37.08%，同时 full matrix 在 Schur build 前仍必须存在。

恢复解的 full explicit true residual 为 `1.959e-11`。相对冻结 global-p6
control，`|ΔR|=9.41e-16`、`|ΔT|=4.38e-13`、
`|ΔA_volume|=1.94e-13`；几何、mesh/tag hashes、periodic mapping 和 MPI8
身份相同。该结果资格化的是 exact static condensation，不等价于
cellwise/regionwise local-p 已完成。

## MPI8 physical regionwise-p controlled negative

首个真实 local-p 候选固定 p4 shared edge/face trace，并依据同网格
p4/p5/p6 classifier 在 105 cells 保留 p6 interior、147 cells 使用 p4
interior。active Full3D-equivalent DoF 为 88,994；完整 p6 matrix、
完整 trace matrix 和 inactive p6 rows 均未分配。

| metric | global p6 assembly-time | regionwise candidate |
|---|---:|---:|
| active rows | 51,272 | 21,824 |
| matrix NNZ | 41,989,040 | 8,184,464 |
| factor NNZ | 211,651,232 | 42,888,832 |
| formal peak | 15.964 GiB | 6.072 GiB |
| condensed build | 770.89 s | 175.43 s |
| MUMPS setup | 142.12 s | 11.45 s |
| case elapsed | 967.09 s | 222.34 s |

该成本 lane 是正信号，但候选不是 same-error 压缩。相对 global p6：

- `R00_total` absolute error `2.9281e-4`，超过 p5-p6 band `3.1953e-5`；
- `R_total` absolute error `2.9770e-4`，超过 band `3.2005e-5`；
- `T_total` absolute error `3.8558e-3`，超过 band `2.1768e-4`；
- normalized R/T/Aclosure vector 为 `27.704`，reference radius 为 `1.732`；
- 12 个 significant diffraction channels 的 power/amplitude 全部失败；
- selected volume/interface complex-E errors 为 `9.8467% / 9.7778%`，
  对应 p5-p6 bands 仅为 `0.5183% / 0.5220%`。

full explicit true residual `1.1657e-11`，geometry、tag、periodic 和
orientation 均通过，所以这是明确的算法精度负结果，而不是求解器失败。
`p4 trace + p4/p6 interior` lane 已关闭且不会无理由重跑。

## 复现

必须先使用仓库资格化 activation；正式运行还必须把
`--verified-clean-sha` 替换为当前干净完整 SHA。

```bash
cd /home/Projects/MyFEniCS
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task035_actual_r5 \
  --coarse-degree 4 --enriched-degree 5 \
  --h-nm 10 --mesh-cell-type hexahedron --single-mesh-pair \
  --mpi-size 8 --warning-gib 48 --terminate-gib 96 \
  --timeout-seconds 7200 --verified-clean-sha <FULL_SHA> \
  --record benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p4_p5_h10_mpi8.json
```

p5/p6 复现时把 degree 改为 `5/6`、timeout 改为 `10800`，record 改为
`global_hexa_p5_p6_h10_mpi8.json`。Task035b 后续正式 heavy PDE 与
static-condensation/Hybrid control 均固定为 MPI8；轻量 pure-Python 或最小
MPI2 单元测试不属于正式资源对照。

p6 condensation 复现时另外加入
`--static-condensation-degree 6`，timeout 使用 `14400`，record 使用
`global_hexa_p5_p6_h10_p6_condensed_mpi8.json`。

regionwise-p 负候选复现必须使用记录内绑定的 classifier/control SHA，并加入：

```text
--coarse-degree 5 --enriched-degree 6
--regionwise-p-classifier-record <CLASSIFIER_RECORD>
--regionwise-p-classifier-sha256 <CLASSIFIER_SHA256>
--regionwise-p-control-record <P5_P6_CONTROL_RECORD>
--regionwise-p-control-sha256 <P5_P6_CONTROL_SHA256>
```

原始 mesh、field、长日志和 memory timeline 位于 gitignored
`benchmarks/artifacts/task035/actual_global_r5/`；tracked JSON 通过 SHA-256
绑定这些证据。
