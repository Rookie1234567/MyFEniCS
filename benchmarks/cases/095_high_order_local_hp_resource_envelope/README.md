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
| `records/regionwise_p5trace_p4low_p6high_n62_h10_mpi8.json` | `6c113cbd6c3dfadd7399ec2d198f0d36bed7533d` | `actual_regionwise_p_controlled_negative` | 9.271 GiB |
| `records/same_mesh_hexa_p4_p5_goal_dwr_h10_mpi8.json` | `56310afa46465ae2e0316c957cf00fd385fa0997` | `target_goal_weighted_two_level_pass` | 15.485 GiB |
| `records/same_mesh_p4_p5_p6_multigoal_hp_classifier_v2.json` | `ac31b6b62cee0185214f2f44a985024393535ea0` | `multigoal_hp_screening_pass` | lightweight |
| `records/regionwise_p_exact_sequence_structural_audit.json` | `e418e96f05cba144b64e6a25e3b445838c9cfaf9` | `regionwise_space_structural_audit_complete` | lightweight |
| `records/global_hexa_p5_p6_h15_assembly_time_condensed_independent_mpi8.json` | `5d75c5ed8ae0dd4382eccf0c47e22fce01391184` | same-error controlled negative | 12.000 GiB pair |
| `records/global_hexa_p6_h15_vs_h10_same_error_audit.json` | `2f334425e20454f04d0edb5d9442708e7e38ea1e` | `controlled_negative_full_same_error_gate` | audit |
| `records/fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json` | `7f61d554b0441d7b224c096aba402d3b3ac2baa6` | `actual_fixed_trace_controlled_negative` | 5.803 GiB |
| `records/global_hexa_p5_p6_h10_projection_signals_mpi8.json` | `65bf6fb034d6717e190a5d1ab4a2025fb1c4ff3b` | 252-cell projection signals | 19.977 GiB pair |
| `records/actual_sequential_h_vs_p_competition_mpi8.json` | generator `659c2a20c6ef56798098470cdeef4d7e45d50b4c` | sequential proxy pass with limitations | derived |
| `records/same_mesh_p4_p5_p6_multigoal_hp_classifier_v3.json` | `5f353e53b519016239374331207d13041b36676e` | v3 pass with limitations | lightweight |

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

第二个候选提高到 p5 shared trace，但为保持 `<=90k`，190 cells 只能保留
p4 interior，按 `eta_p5p6` 排名前 62 cells 保留 p6 interior。

| metric | p5-trace N62 |
|---|---:|
| Full3D-equivalent active DoF / solved rows | 89,755 / 35,000 |
| matrix / factor NNZ | 20,140,928 / 101,062,900 |
| average / max row width | 575.46 / 965 |
| factor fill | 5.018 |
| formal peak / swap | 9.271 GiB / 0 |
| condensed build / MUMPS setup / solve | 344.16 / 37.20 / 0.074 s |
| true residual | `1.5721e-12` |

该候选 `R00/R/T/Aclosure =
0.94396245/0.96089508/0.01608446/0.02302046`，normalized multi-goal
error 为 `30187.729`，volume/interface complex-E errors 为
`101.720%/101.039%`；全部 strict Gate 失败。它是预算内 high-interior
最多的候选，因此不再运行同一非 exact-sequence 空间的更弱 N18。

后续 local polynomial de Rham 审计改变了对该负结果的解释：

- `p4 trace + p4/p6 interior` 的 low/high curl nullity 为 `124/222`，
  与 mixed scalar companion 的 expected gradient dimensions 完全一致；
  它仍是有效的独立精度负结果，p4 trace 子路线保持关闭；
- `p5 trace + p4 interior` 的 low-space expected gradient dimension 为
  `178`，实测 curl nullity 只有 `112`，缺失 66 个 gradient modes；
- `p5 trace + p6 interior` high space 为 `276/276`，问题仅在低空间。

因此 N62 保留为 `controlled_negative_non_exact_sequence_space` 证据；
小线性残差只证明该错误离散系统被准确求解，不能资格化其 Maxwell 空间。
此前“两个独立精度负信号关闭全部 fixed-mesh lane”的依据不成立。lane 只对
新的 exact-sequence-conforming、物理减行 trace/local-p 构造重新开放，
不重跑 p5-trace/p4-interior。

## MPI8 same-mesh multi-goal DWR

同一 252-cell hexa h10 网格上的 p4/p5 pair 已完成三个独立 Hermitian
adjoint：`R00_total`、`R_total`、`T_total`。p4/p5 full explicit true
residual 分别为 `5.273e-12 / 2.038e-11`，三目标 direct-adjoint 与
finite-difference 相对误差均在 `2.4e-10` 以内；DWR absolute effectivity
均与 1 的差小于 `1.7e-11`。

| indicator, theta=0.5 | marked cells | captured fraction | 与 R5 的 Jaccard |
|---|---:|---:|---:|
| strict `DWR_R00` | 84 | 0.5055 | 0.6897 |
| strict `DWR_R` | 84 | 0.5059 | 0.6897 |
| `DWR_T` | 78 | 0.5160 | 0.8077 |
| relative `R/T` multi-goal | 81 | 0.5091 | 0.7778 |
| tolerance-normalized `R/T` multi-goal | 78 | 0.5126 | 0.8077 |
| R5 correction energy | 63 | 0.5115 | — |

tolerance normalization 绑定 Case093 structured p4/h7.5 相对 p4/h5 的独立
`R/T/A_volume` error authority。normalized DWR 的 78 cells 包含全部 63 个
R5 marked cells；因此它比只优化 `R_total` 更适合作为下一步 one-cycle
local-h 的研究 marker，但 marker 仍只是 classifier 输入，不等价于已完成
网格变异。

该 pair 总时长 877.03 s，simultaneous process-tree peak 15.485 GiB，
0 swap。p5 阶段 645.13 s 中 base matrix assembly 为 553.89 s，
MUMPS setup/solve 为 78.61/0.17 s，再次确认当前高阶时间瓶颈是 assembly，
不是直接法回代。

## multi-goal hp screening v2

classifier v2 在同一 canonical cell ID 上合并 `eta_p4p5`、`eta_p5p6`、
strict `DWR_R00/R/T`、tolerance-normalized `R/T`、R5 以及实际
material/interface/corner tags。原始 strict-R00 与 normalized-R/T 并集为
99 cells；周期审计发现 3 个 x-periodic mates 未同时进入原始 Dörfler 集合，
因此显式加入 `[213, 227, 241]`，形成 102-cell periodic-closed screening
set。闭合后 126 个 x/y periodic mate groups 的 action 全部一致。

所有 102 个 goal-important cells 的 `eta_p5p6/eta_p4p5` 都远小于 0.5，
所以 measured screening 给出：

| action | cells |
|---|---:|
| `p_down_candidate` | 0 |
| `p_keep_candidate` | 150 |
| `p_up_candidate` | 102 |
| `h_refine_candidate` | 0 |
| `undetermined` | 0 |

界面/corner prior 没有覆盖该 measured p-decay 结论。此记录明确保持
`production_qualified=false`：target-cell hierarchical coefficient decay、
local projection defect 和 actual local-h-vs-p cost competition 尚未取得。
因此它是 screening 正结果和 hexa local-h 的零信号，不是最终 local-hp
decision authority，也不能据此把未运行的 local-h 写成通过。

## Projection signals 与 classifier v3

最新 MPI8 p5/p6 authority 在 252/252 cells 上保存 physical hierarchical
decay、coefficient diagnostic 和 p4/p5 projection defect：

| signal | min | median | max |
|---|---:|---:|---:|
| physical p6/p5 hierarchical decay | 0.16201 | 0.16289 | 0.16783 |
| coefficient decay，diagnostic only | 0.14644 | 0.14723 | 0.15164 |
| p4 projection defect | 0.03436 | 0.03448 | 0.03848 |
| p5 projection defect | 0.00655 | 0.00657 | 0.00755 |
| p5/p4 defect decay | 0.18988 | 0.19086 | 0.19644 |

v3 对 periodic transitive components 先聚合 worst signal/goal OR，再决策，
结果为 `p-up=102 / p-keep=150 / h-refine=0 / p-down=0`。它还通过
smooth/interface/corner/high-frequency synthetic fixtures 和 MPI2
rank-local-invalid collective fail-fast。旧 signal record 不含后来新增的
N1E/Piola、p5 round-trip 与 explicit hash-scope 字段，target phase-resolution
和 same-patch h-vs-p authority 也缺失，因此仍为
`production_qualified=false`。

## h15 资源候选与最终 Gate

| candidate | DoF / rows | matrix/factor NNZ | peak | same-error |
|---|---:|---:|---:|---|
| global p6/h15 | 84,492 / 24,704 | 19,207,136 / 59,616,320 | 12.000 GiB pair | channels 6/12 power、8/12 amplitude；negative |
| fixed p5-trace/p6-interior h15 | 74,890 / 16,880 | 9,195,812 / 27,916,600 | 5.803 GiB | channels 6/12 power、7/12 amplitude；negative |

两者 scalar/vector、selected fields、full residual 和资源均通过，但完整
same-error Gate 不允许忽略 significant channels，因此没有进入 Hybrid。
fixed h15 的 tensor dedup + exact preallocation 将 PETSc mallocs 降至 0、
build 降至 61.61 s，证明工程优化有效，但不改变 accuracy 分类。

## Review V1：显著通道参考、伴随与根因假设判别

`records/significant_channel_reference_v1.json` 已在不重跑既有 heavy
authority 的前提下冻结 12 通道 reference v1。它保存逐通道 power、复振幅、
magnitude、unwrapped phase、绝对/相对 spread、source SHA、mesh hash 与
qualification；12/12 均有可审计 numerical band。该 reference 是
best-available same-code convergence authority，不是 continuum truth，也没有
改变 Review V1 冻结的 12 通道 acceptance Gate。

`records/fixed_p5trace_p6interior_h15_channel_adjoints_verification_v2_mpi8.json`
实际完成 16 个独立 Hermitian adjoint，覆盖 6 个失败功率目标及 5 个失败复振幅
目标的 real/imag：

- 16/16 direct-adjoint verification 通过；
- 最大 direct-adjoint 相对误差 `2.514e-11`；
- 最大 finite-difference 相对误差 `5.575e-7`；
- 最大 adjoint residual `4.207e-13`；
- adjoint 总时间 `10.334 s`，诊断运行峰值 `7.190 GiB`。

当前 entity localization 是 recovered-dual coefficient sensitivity proxy，
不是 enriched residual-weighted DWR。它没有提供 physical Piola/Riesz、
missing-trace complement Schur solve 或 true active numbering，因而不能单独
选择 p6 trace modes。

DtN/port 根因假设判别保留了三类独立证据：

| record | 判别结果 |
|---|---|
| `records/fixed_p5trace_p6interior_h15_dtn_q31_mpi8.json` | 更高 trace quadrature 无通道恢复，controlled negative |
| `records/fixed_trace_h15_evanescent_buffer1_preflight_controlled_stop.json` | 未缩放 evanescent 坐标在 PDE 前安全停止 |
| `records/fixed_p5trace_p6interior_h15_dtn_evanescent_buffer1_scaled_mpi8.json` | 安全缩放后仍为 6/12 power、7/12 amplitude，controlled negative |
| `records/manufactured_rayleigh_port_authority_v1.json` | manufactured amplitude/phase/normalization algebra 通过 |
| `records/dtn_port_phase_authority_v1.json` | phase convention 与 reference-plane 变换审计通过 |

已测试的 q31 与 bounded buffer 没有支持其作为 material recovery 机制；
这不排除小贡献或其他 DtN/port 离散效应。manufactured authority 支持当前
port convention，但不能数学上排除所有共同的 port 误差。

## Review V1：方向性 structured-h 恢复

所有 formal PDE 均为 MPI8，且实际 topology、geometry/tag/orientation/Floquet
identity 与完整 true residual 均通过：

| candidate | topology | DoF / rows | matrix/factor NNZ | peak | 12通道 power / amplitude | 分类 |
|---|---|---:|---:|---:|---:|---|
| fixed h15 seed | `(6,2,10)` | 74,890 / 16,880 | 9,195,812 / 27,916,600 | 5.803 GiB | 6/12 / 7/12 | controlled negative |
| z-only h14 | `(6,2,11)` | 82,315 / 18,500 | 10,104,512 / 31,347,000 | 6.376 GiB | 7/12 / 9/12 | positive signal, not candidate |
| z-only h13 | `(6,2,12)` | 89,740 / 20,120 | 11,013,212 / 36,273,200 | 6.411 GiB | 10/12 / 10/12 | best measured, still negative |
| x-only h15 | `(7,2,10)` | 87,195 / 19,680 | 10,728,434 / 33,056,800 | 6.590 GiB | 5/12 / 6/12 | controlled negative |
| y-only global-p5 control | `(6,3,10)` | 72,995 / 25,280 | 14,433,128 / 70,293,600 | 8.868 GiB pair | 3/12 / 1/12 | control negative |
| global p6/h14 discriminator | `(6,2,11)` | 92,850 / 27,080 | 21,110,096 / 67,325,792 | 12.587 GiB pair | 9/12 / 12/12 | over DoF cap and power negative |
| h14 R5-slab bisect | `(6,2,12)` | 89,740 / 20,120 | 11,013,212 / 36,273,200 | 6.463 GiB | 5/12 / 9/12 | controlled negative |

z-only h13 是当前最强测得候选，但仍失败 `T(-4,0)`、`R(-4,0)` power
以及 `r(-5,0)`、`r(-4,0)` complex-amplitude Gate，不能接入 Hybrid。
R5-slab 只二分一个最大 proxy slab 后反而使 `R(-7,0)` power 回退；该点已按
预注册停止条件关闭指定 R5-slab split lane，不能继续盲扫该 split。其他
node distributions 未被证明无效且未运行。x-only 是 same-space negative
control；y-only 是 global-p5 mechanism control，不是 same-space fixed-trace
y 排除。方向性证据支持 z-resolution 为当前最强预算内恢复杠杆，但没有证明
z、mesh 或 numerical phase 是唯一根因。

`records/channel_response_matrix_directionality_v1.json` 与
`records/channel_phase_dispersion_diagnostic_v1.json` 进一步显示：h13 剩余
三项失败的 power response 近似 rank 2、complex response rank 3。现有线性
response 诊断不支持预期单一 scalar mesh knob 闭合全部通道；它不是实际组合
PDE，也不证明所有其他 topology 无效。这是停止大规模盲扫的判别依据。

## Review V1：选择性 trace 与迭代路径的 fail-closed 边界

`records/missing_p6_trace_complement_preflight_v2.json` 证明 reference-cell
p5/p6 missing trace complement 为 132 维：每条 edge 1 mode、每个 face
20 modes；reference-entity Riesz 与 orientation-closed block algebra 通过。
`records/inverse_trace_interior_budget_exchange_preflight.json` 则证明用降低
cell-interior order 换取完整 p6 trace 的 p6-trace/p5-interior 与
p6-trace/p4-interior 空间均不满足冻结的 local exact-sequence prerequisite，
因此两条预算交换在 PDE 前关闭。

`records/physical_trace_lane_capability_gate.json` 的
`pass=true` 只表示 SHA-bound capability audit 有效。其正式状态是
`capability_stop_not_run`，candidate/PDE count 均为 0；physical Piola/Riesz、
missing-mode Floquet phase pullback、complement Schur solve、actual enriched
residual-weighted DWR、selected exact-sequence closure 和 true active global
numbering尚未闭合。因此 Lane B 是 `not_currently_executable`，不是被数值
证伪，也没有授权从 coefficient proxy 选择 mode subset。

`records/condensed_trace_iterative_capability_gate.json` 同样是
`capability_stop_not_run`。它冻结了未来唯一低成本 screen 的合同：
MPI8、GMRES restart 30、最多 200 iteration、unpreconditioned residual norm、
至少 3 decades residual reduction、最终显式 reduced-system residual
`<=1e-3`、peak `<=5.2 GiB`、无 factor、无 swap。当前 public path 仍是 direct
provenance，且缺少 dedicated iterative hook、residual history 和 factor-free
inventory，所以没有伪造迭代实测值。`24 byte/factor-NNZ +
8 byte/row-pointer` 只是一项 planning proxy；不同阶段 peak 的差也不是
factor-memory upper bound。

## Lane B 与 Hybrid stop

Task035 tetra h50 的顺序代理
`base p5 -> one local-h p5 -> fixed-mesh p6` 显示 vector-cost 偏向 h、
strict-R-cost 偏向 p，最终 p6 为 167,784 DoF 且 strict-R control 失败。
它不是 same-patch cell-decision authority。

structured hexa 缺少 conforming hanging-node/transition implementation，
tetra selected-p6 physical reduction 未实现；classifier v3 没有 target
same-patch h-refine signal，但该 scope 不覆盖后续 directional-z
topology/refinement response。Review V1 后，方向性 Lane A 已以 h13 与
R5-slab stop 完成预先指定的预算内最少判别点；选择性 trace Lane B 停在
上述真实 capability gap。
不存在 Hybrid-eligible candidate，故 Hybrid closure、M funnel、external
DtN funnel 和 0.7 nm resource model v3 均为
`not_run_by_selected_candidate_gate`。

## 不应无理由重复的 heavy authorities

以下 MPI8 PDE 已有 source/artifact/hash-bound 证据；除非对应数值核心、输入
identity 或 review Gate 改变，不应重跑：

- global p4/p5/p6 h10 与 assembly-time condensation controls；
- global p6/h15 与 fixed p5-trace/p6-interior h15；
- h15 的 16-goal adjoint verification v2；
- DtN q31、unsafe buffer preflight、scaled buffer-1；
- z-only h14、z-only h13、x-only h15、y-only control；
- global p5/p6 h14 discriminator；
- h14 R5-slab bisect；
- Task034 p4/h5、structured p4/h7.5 及 Task035 tetra heavy references。

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

Review V1 的两个 capability audit 都是 serial、pure-postprocess，不启动 PDE。
已冻结 record 的无写入复核使用对应 targeted tests：

```bash
python -m pytest -q \
  src/test/test_132_task035b_physical_trace_lane_capability_gate.py \
  src/test/test_133_task035b_condensed_iterative_capability_gate.py
```

正式 tracked evidence 只能写入 Case095 `records/`，且生成器使用 exclusive
create。若未来补齐 physical trace 或 iterative capability，必须先提交干净
源码，再以新的 source SHA 和新的 record 文件名运行；不得覆盖现有
controlled-stop records。

原始 mesh、field、长日志和 memory timeline 位于 gitignored
`benchmarks/artifacts/task035/actual_global_r5/`；tracked JSON 通过 SHA-256
绑定这些证据。
