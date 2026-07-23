# Task035 当前结果汇总

## 状态

```text
phase_a = accepted
phase_b_algebraic_precursor = pass
phase_b_real_fixture_minimum_gate = pass
phase_c_low_cost_unlocked = true
phase_c_internal_gate = complete_controlled_negative
B3_B4 = pass
phase_d_internal_gate = complete
execution_mode = continuous_autonomous_research
actual_global_two_level_R5 = pass_hexa_control
actual_discrete_DtN_adjoint = pass
actual_goal_weighted_DWR = pass
periodic_tetra_target_pipeline = research_pass
actual_adaptive_cycles = two_consecutive_pass
selected_research_strategy_10deg = p4_p5_R_total_DWR_theta0p7_one_cycle
robust_angle_common_mesh = controlled_negative
multi_angle_lane = active
second_cycle = controlled_negative_cost_dominated
production_estimator_selected = false
production_backend_selected = false
heavy_p4_authorized = true_by_review_v4_measured_evidence_required
```

Review V4 已把 Task035 切换为连续自主研究。首个真实目标 `p2/h10 -> p3/h10`
global two-level R5 已通过 clean-SHA、watchdog、MPI8、true residual、official R/T/A、
逐 owned cell 非负性与全局能量闭合 Gate。该正结果首先资格化 estimator mechanism；
它仍在 accepted hexa control 上，还没有选择 production mesh backend 或完成 adaptive cycle。

## Phase B 证据

| 项目 | 结果 | 证据 |
|---|---|---|
| algebraic precursor | pass；不得称 formal FE qualification | `records/fixture_summary.json` |
| R2 | `resolution_diagnostic_pass`；只记录 `chi=|k|h/p` | `src/validation/task035_hcurl_estimator_fixtures.py` |
| B1 real periodic Nédélec | p1/p2 pass；实际 UFL volume/jump、Floquet trace 与 fault injection | `records/real_fe_mpi1.json` |
| B2 real flat lossy layer | 三个实际 h/p 点 pass；piecewise-complex DG0、field/goal/estimator trend、DtN perturbation | `records/real_fe_mpi1.json` |
| serial/MPI2 identity | pass；scalar metrics differences = `{}` | `records/real_fe_mpi_identity.json` |
| B3 material-interface/corner | pass；actual Nédélec、DG0 tags、interface facets、fault/enrichment/directional metrics | `records/phase_cd_mpi1.json` |
| B4 Hybrid Et/Ht、M/DtN/QEP | pass；复用 accepted target traces、M80/120/160 与 matched-trace QEP | `records/phase_cd_mpi1.json` |
| R4 equilibrated | `formula_defined` | research lane |

## B1/B2 代表数值

| Fixture | 离散点 | field error | R1 indicator | official fixture goal |
|---|---:|---:|---:|---:|
| B1 periodic | p1, 2×2×2 | 6.0837e-2 | 1.5326 | n/a |
| B1 periodic | p2, 2×2×2 | 1.6905e-3 | 1.0031e-1 | n/a |
| B2 lossy layer | p1, 1×1×2 | 1.7331e-1 | 9.4576 | R00 error 5.55e-17 |
| B2 lossy layer | p1, 2×2×4 | 4.5161e-2 | 5.2798 | R00 error 1.39e-16 |
| B2 lossy layer | p2, 2×2×4 | 2.2355e-3 | 5.9303e-1 | R00 error 4.09e-16 |

这些值来自解析/制造场在真实 Nédélec 空间中的离散与 UFL quadrature，不是 PDE solve，
也不是目标 13.5 nm 光栅的正式 R/T/A。

## Review V4：actual global two-level R5

| 项目 | measured result |
|---|---:|
| target | 13.5 nm、10° grazing、S、Task034 fixed geometry |
| pair | Full3D p2/h10 → p3/h10，同一 252-cell hexa control |
| MPI / clean SHA | MPI8 / `307907a1bb5a7a0a08c46ec75881d890fb3d1549` |
| true residual p2 / p3 | `2.304e-13` / `2.765e-12` |
| p2 R/T/A_volume | `0.9976471 / 0.00191059 / 0.000442293` |
| p3 R/T/A_volume | `0.0553985 / 0.4060679 / 0.5385336` |
| correction energy / norm | `1.0943224e7` / `3308.0544` |
| cell sum closure | relative error `5.106e-16` |
| Dörfler theta=0.5 | 99/252 cells；captured `0.501807` |
| marked hash | `4a4545a59164a813e4b08e47a4be94d652c5df0ee342afba988507e24e9c7e7b` |
| estimator time | `4.190 s` |
| watchdog peak / swap | `2.870 GiB` / `0` |

p2 与 p3 的 official observable 差异很大，说明 p2/h10 尚不在可信离散区间；这不是
adaptive 成功，但正是 actual R5 应识别的强 enrichment signal。下一步把这一 estimator
接到周期 tetra target pipeline，完成 orientation/tag/periodic closure，然后执行 p2 marked
cycles 和 cost-matched uniform control。若 tetra 路线通过，再用 p4 或细化解作为独立
local-error reference 测 correlation/effectivity；当前 dimensionful effectivity 只标记为 proxy。

### Periodic tetra target Gate

| 项目 | measured result |
|---|---:|
| pair | boundary-fitted tetra p2/h50 → p3/h50 |
| MPI / clean SHA | MPI2 / `5f38c4469b8c212e283b1e2b5772c3ee017f8448` |
| cells / DoF | 180；p2 `1470`，p3 `4011` |
| true residual p2 / p3 | `9.388e-14` / `9.134e-13` |
| observable delta L2 | `5.5384e-2` |
| cell energy closure | `5.810e-16` |
| Dörfler theta=0.5 | 49/180 cells；captured `0.507945` |
| watchdog peak / swap | `0.569 GiB` / `0` |

该结果是实际 target Maxwell/DtN PDE，不再只是 tetra manufactured refine control；下一 Gate 是
periodic-mate closure 后的 estimator-marked refinement 与连续 cycle observable reduction。

周期 refinement mechanism 现在使用 translated triangular facet 的 incident-cell closure，并在
实际传给 `dolfinx.mesh.refine` 的 edge 集上再次执行 x/y periodic closure。refine 返回的混合局部
orientation 被显式重建为全正 affine determinant；最终 mesh、cell/facet tags、shape-quality quantile
及 periodic face set 均以 canonical coordinate hash 绑定。serial/MPI2 的初始 mesh、closed marking
和 refined mesh hashes 完全一致。该结果资格化 mesh mechanism，不代替真实 adaptive PDE cycle。

### 首次 actual marked cycle 与 Gate 修正

clean SHA `5bfc1a0b40a959f6c2063979feb1341a83007cac` 的 MPI2 h50 cycle 将 49/180 个
R5 cells 扩展为 60 个 periodic-closed cells、180 个 closed edges，得到 1142 个正 orientation
tetra cells；x/y periodic face sets、材料 tags、true residual（最差 `7.989e-12`）和 no-swap
resource Gate 全部通过，process-tree peak 为 `0.951 GiB`。

旧 watchdog 使用同一网格上 moving p2→p3 gap 作为“实际误差”；该 gap 从 `5.538e-2`
增至 `8.894e-1`，因此真实记录按原 Gate 保存为 `formal_not_pass`，没有覆盖。这个量并非固定
reference error：对 Task034 accepted p4/h5 best-available discrete reference
（`convergence_summary.json` SHA-256 `f5bad15f...1111`），p2 error 从 `1.202635` 降至
`1.189884`（1.060%），p3 error 从 `1.147343` 降至 `0.426445`（62.832%）。因此修正后的
formal Gate 使用 hash-bound fixed reference，moving p-gap 只作 enrichment diagnostic；reference
仍明确不是 continuum truth，阈值没有放宽。

第二次 formal attempt 正确通过上述 fixed-reference reduction，但从 1142 cells 继续 refine 到
6560 cells 时，DOLFINx 的 distributed conformity propagation 在两个周期面产生不同的额外 edge
选择；x/y normalized triangle sets 分别出现 6/6 和 8/16 unmatched。所有 determinant 为正、
minimum quality `0.0456`、material tags 和 no-swap Gate 均通过，但 periodic Gate fail-closed，
因此 cycle2 PDE 未启动，原始记录永久保留。

修复后的 research backend 每轮同步 refine 当前 x/y periodic boundary sleeve 的全部 edges，并在每个
rank 的 `COMM_SELF` 上执行相同 deterministic refine，再将 canonical positive-orientation mesh 分发到
工作 communicator。这牺牲分布式 mesh-refine scalability 以换取多层 topology identity；serial/MPI2
两层 fixtures 的 first/second refined mesh hashes 分别为 `65c11dbe...b0ac` 和 `f4c0533e...49fc`。
该 backend 仍须重新跑 actual cycles 和量化 boundary-sleeve overhead，尚未提升为 ordinary default。

### 两轮 actual adaptive success

clean SHA `9ee77e2bd90dafe1623942221ff75793ac38d5cb`、MPI2 的 recovery run 完成两次
estimator-marked refinement，并通过全部 watchdog qualification：

| cycle | cells | p2 / p3 DoF | p2 fixed-ref error | p3 fixed-ref error | R5 marked / captured |
|---:|---:|---:|---:|---:|---:|
| 0 | 180 | 1,470 / 4,011 | 1.202635 | 1.147343 | 49 / 0.507945 |
| 1 | 1,308 | 9,504 / 26,730 | 1.087687 | 0.142113 | 345 / 0.500700 |
| 2 | 8,785 | 60,330 / 172,257 | 0.195353 | 0.007041 | 1,022 / 0.500164 |

p2 reference error 两步分别下降 9.56% 和 82.04%，p3 分别下降 87.61% 和 95.05%。cycle2
p3 official vector为 `(R,T,A_volume)=(0.004574, 0.597043, 0.398383)`；best-available
p4/h5 reference 是 `(0.000766, 0.602678, 0.396556)`。三轮最差 true residual 为
`2.341e-11`，process-tree peak `6.401 GiB`，swap 0，总 wall time `295.96 s`。

periodic sleeve overhead：第一次 initial estimator edges 174，加入全部 periodic boundary 后 244；
第二次 911→1256。该成功证明 actual R5+tetra 路线有强正信号，但 8,785-cell adaptive mesh
与候选 uniform h5 的 10,080 cells（p2/p3 DoF 69,290/197,871）仍需正式 cost-matched 对照。

### True-uniform cost control 与 R5 决策

从相同 180-cell h50 tetra mesh 连续两次全单元 refinement，得到 1,440 和 11,520 cells；
boundary-sleeve added edges 为 0，两层 serial/MPI2 hashes 分别为 `22204e1b...91af`、
`37d4f643...28a8`。clean SHA `e1743b632aeda845e151efaef7bdf2c81e347f36` 的 MPI2
control 全部 qualification 通过，最终对比如下：

| route | cells | p2 / p3 DoF | p2 fixed-ref error | p3 fixed-ref error | peak GiB | wall s |
|---|---:|---:|---:|---:|---:|---:|
| R5 adaptive cycle2 | 8,785 | 60,330 / 172,257 | 0.195353 | 0.007041 | 6.401 | 295.96 |
| uniform level2 | 11,520 | 78,000 / 223,656 | 0.010697 | 0.001227 | 8.473 | 523.44 |

adaptive/control 比值：cells `0.7626`、memory `0.7554`、time `0.5654`；但 p2/p3 error
比值为 `18.263` / `5.738`。这不是资源或 PDE 失败，而是明确的方法级 negative：当前
`R5_actual_global_two_level_correction_energy` 能驱动收敛，却没有在 comparable cost 上击败
uniform refinement，故不得作为 production marking。继续第三轮纯 R5 会放大已证实的低效率，
不再执行；下一主线必须引入 official-goal sensitivity 的 actual DWR/discrete adjoint，再与同一
uniform record 比较。R5 保留为 diagnostic/two-level correction magnitude。

前文 “候选 uniform h5” 只用于运行前 cost probe；本节 11,520-cell 同拓扑全单元 refinement
才是正式 cost-matched uniform authority。

## Actual DtN adjoint 与 R-total DWR

official R/T amplitude 的解析 real-valued gradient、`A^H z=g` discrete adjoint、full true adjoint
residual、midpoint identity 和 actual cell/face localization 均已通过。首次 p2/p3 DWR cycle
显示阶次依赖的 mixed result：

| route | cells | p2 / p3 DoF | p2 error | p3 error | decision |
|---|---:|---:|---:|---:|---|
| DWR theta=0.5 cycle1 | 1,276 | 9,338 / 26,214 | 1.023485 | 0.171653 | p2 比 uniform1 约好 0.16%，p3 差 2.54 倍 |
| uniform level1 | 1,440 | 10,400 / 29,304 | 1.025085 | 0.067615 | p2/p3 authority |

因此 actual DWR mechanism 通过，但 p2/p3 不是 production 选择；随后按 measured signal 转入
p3/p4，而不是扩大低阶重型路线。首次 watchdog parent compaction failure 原样保存在
`actual_dwr_r_adaptive_watchdog_compaction_failure.json`；worker 数值已通过，修复 record mapper
后才进行正式 clean-SHA rerun。

## p3/p4、MPI8 与最终 research strategy

| route | cells | p3 / p4 DoF | p3 error | p4 error | peak GiB | wall s | decision |
|---|---:|---:|---:|---:|---:|---:|---|
| uniform level1 MPI8 | 1,440 | 29,304 / 63,104 | 0.067615 | 0.00597711 | 4.020 | 27.81 | high-order control |
| DWR theta=.5 cycle1 MPI8 | 1,268 | 25,995 / 55,884 | 0.157261 | 0.00460020 | 3.983 | 37.80 | p4 positive；当前选择 |
| DWR theta=.5 cycle2 MPI8 | 7,348 | 145,710 / 315,444 | 0.0205361 | 0.000536345 | 18.831 | 583.87 | cost-dominated negative |
| DWR theta=.3 cycle1 MPI8 | 1,200 | 24,744 / 53,128 | 0.191653 | 0.0105970 | 3.899 | 34.90 | controlled negative |

uniform1 p3/p4 的 MPI2/MPI8 observables、DoF 与 mesh hashes 一致；MPI8 wall `27.81 s`，相对
MPI2 `73.40 s` 加速约 2.64 倍，代价是 process-tree peak 从 2.549 增至 4.020 GiB。p4/uniform1
已经以 63,104 DoF 和 `0.005977` error 胜过 p2/uniform2 的 78,000 DoF、`0.010697` error，
证明此目标上提高 p 比继续低阶全局 h-refine 更有效。

DWR theta=.5 cycle1 又以约 11% 更少 p4 DoF，把 error 比 uniform1 降低约 23%，是实际工程
正信号。第二 cycle 继续把 error 降到 `5.36e-4`，但与复用的 Task034 accepted structured 结果相比：

| accepted/actual route | DoF | observable error vs p4/h5 reference | peak GiB |
|---|---:|---:|---:|
| structured p4/h10 | 53,084 | 约 0.0079 | 5.640 |
| DWR theta=.5 cycle1 | 55,884 | 0.004600 | 3.983 |
| structured p4/h7.5 | 147,844 | 约 0.000328 | 12.724 |
| DWR theta=.5 cycle2 | 315,444 | 0.000536 | 18.831 |

一轮 DWR 在近似相同 DoF 下优于 p4/h10 且内存更低；第二轮则在误差、DoF、内存上被
p4/h7.5 同时支配。因此固定 geometry、S、10° grazing 的当前最优 research algorithm/stop rule 是：

```text
p3/p4 + actual R_total discrete-adjoint DWR
Dorfler theta = 0.5
exactly one periodic-tetra local refinement
stop before cycle 2
MPI8 formal execution
```

### Marked-set repeatability boundary

Dörfler cutoff near-tie expansion policy 已记录 minimal count、tie expansion、cutoff 与 tolerance。
低阶 fixture 继续满足 serial/MPI exact marker hash；三个独立 p3/p4 MPI8 runs 各选 215 cells，
两两 overlap 均为 `214/216=0.9907407`，但 solve-level cell contribution 漂移大于 tie tolerance，
exact hash 不同。每次正式 record 均绑定其实际 hash，高阶复现只宣称 overlap ≥0.99；
`tie_stable` record 名称表示 tie policy v1 evidence，不表示 exact repeat hash。

### p4/p5 minimal-closure hp audit

clean SHA `f3b38cc15359e22ae1548ed40b838f14caefaf3e` 将 tetra high-order Floquet
research capability 从 p4 扩展到 p5；hexa 与 ordinary default 继续 fail-closed 于 p4。serial 与
MPI8 的 Basix layout、S3 face transform、refined-tetra ownership 和 sparse MPC component Gate 均通过。
正式 MPI8 `p4 -> p5`、`R_total` DWR、minimal periodic closure 两周期结果为：

| cycle | cells | p4 / p5 DoF | p4 / p5 fixed-ref error | marked cells |
|---:|---:|---:|---:|---:|
| 0 | 180 | 8,476 / 15,405 | 0.300154 / 0.0220322 | 49 |
| 1 | 972 | 42,336 / 77,980 | 0.254695 / 0.00715450 | 238 |
| 2 | 4,344 | 183,528 / 339,850 | 0.00414856 / 0.000220336 | 563 |

全部 forward/adjoint residual、periodic、orientation、Dörfler、official-result 与 no-swap Gate 通过；
wall time `778.93 s`，process-tree peak `27.768 GiB`，16 GiB warning 触发但 32 GiB termination 未触发。
最终 p5 error 比 p3/p4 两周期的 `0.000536345` 低约 59%，证明 global-p 可以避开第三层
minimal-closure h-refine 的周期拓扑失败并继续提高精度。但第一周期 p5 已同时被当前选择的一周期
p3/p4 DWR 在 error 与 DoF 上支配；最终点相对 structured p4/h7.5 只进一步降低约三分之一误差，
却使用约 2.30 倍 DoF 和 2.18 倍内存。因此该结果分类为
`numerical_positive_cost_limited_hp_audit`，不替代当前一周期 p3/p4 research stop rule。

同一 p4/p5 与 `theta=0.5` 改用已资格化 full periodic boundary sleeve、只做一次 refinement，得到
1,276 cells、p5 `103,330` DoF、fixed-reference error `0.000589604`、峰值 `7.901 GiB`、
worker wall `109.57 s`，全部 Gate 通过。它相对 p3/p4 full-sleeve 两周期的 error 只高约 10%，
却减少约 67% DoF、58% 内存和 81% 时间，形成 `strong_hp_tradeoff_signal`。相对 structured
p4/h7.5，它使用更少 DoF/内存但 error 仍约高 1.8 倍，因此尚未完成 same-error replacement。
下一最小判别点只提高单周期 Dörfler `theta` 至 `0.7`；若能在仍低于 structured 成本时达到或
优于 p4/h7.5 error，则升级为工程 hp success，否则保存为精度/成本 Pareto 点并关闭该局部扫描。

full-sleeve 单周期 record 绑定 clean SHA `96c80e9bea3ea2aa2624926d6791fc7d51268dbe`；
没有重跑 Task034 p4/h5、p4/h7.5、M funnel 或其他 accepted heavy reference。

预先限定的唯一 `theta=0.7` 判别点绑定 clean SHA
`c2898da89b055f0e6a13df3f039c6a0c24942d04`。它得到 1,316 cells、p5 `106,355` DoF、
error `0.000538286`、峰值 `8.080 GiB`、worker wall `109.79 s`，所有 Gate 通过。相对
`theta=0.5` 只增加约 2.9% DoF，error 改善约 8.7%；相对 p3/p4 full-sleeve 两周期则以
约 33.7% DoF、42.9% 内存和 18.8% 时间达到只差约 0.36% 的 error，构成 clear adaptive-control
compression。但它仍比 structured p4/h7.5 error 高约 64%，所以预先声明的 structured same-error
Gate 未通过。该 theta lane 在此停止，不继续扫参；下一步只做独立 p5 uniform-level1 control，
区分收益来自 DWR marking 还是 global p5。

clean SHA `fc54cc698422d9d13477167cab4bc8566c9004b3` 的独立 p4/p5 uniform-level1 MPI8
control 从同一初始网格全量细化到 1,440 cells，得到 p5 `116,120` DoF、error `0.000735191`、
峰值 `8.011 GiB`、swap 0，全部 Gate 通过。与之相比，DWR `theta=0.7` 使用 1,316 cells、
`106,355` DoF，把 error 降至 `0.000538286`：约少 8.4% DoF且误差低 26.8%，峰值内存只高约
0.9%（包含 adjoint）。因此 goal-oriented marking 的收益不只是 global p5，满足 same-degree
tetra adaptive-vs-uniform causal control：

```text
p4_p5_DWR_theta0p7_vs_uniform_tetra = clear_positive
p4_p5_DWR_theta0p7_vs_structured_p4_h7p5 = pareto_tradeoff_not_same_error
```

上述结论只对 Task034 fixed geometry、S、10° grazing 与当前 best-available p4/h5 reference 成立；
没有冒充 continuum convergence，也未覆盖 robust-angle、P incidence、Hybrid common mesh。
所以这是 selected research strategy，而不是 ordinary production default。

### MPI8 common-mesh robust-angle 判别

clean SHA `782d9d1527796a4cae15255c630a02b69ff02f5c` 从上述 `theta=0.7` authority
record 重放 72 个 `R_total` marker，并严格匹配 1,316-cell mesh、cell-tag 和 facet-tag 哈希。
随后在同一个内存 mesh 实例上连续求解 S 入射 1°/5°/10° grazing 的 p4/p5 pair：

| grazing | p4 / p5 DoF | p4 R/T/A_volume | p5 R/T/A_volume | p4→p5 observable gap |
|---:|---:|---|---|---:|
| 1° | 57,828 / 106,355 | 0.729030 / 0.005488 / 0.265482 | 0.426387 / 0.011593 / 0.562020 | 0.423752 |
| 5° | 57,828 / 106,355 | 0.020312 / 0.325020 / 0.654668 | 0.000567 / 0.338232 / 0.661201 | 0.0246384 |
| 10° | 57,828 / 106,355 | 0.004986 / 0.603166 / 0.391848 | 0.000962 / 0.602920 / 0.396117 | 0.00587184 |

六次 forward solve 均为 official result，最大 true residual 小于 `4.68e-11`；公共网格身份和
全部 watchdog Gate 通过。worker wall `198.47 s`，process-tree peak `16.519 GiB`，swap 0；
16 GiB warning 触发但 32 GiB termination 未触发。

该 run 的“公共网格重放与同网格比较”是 positive infrastructure result，但 10°-优化网格在
1° 和 5° 的 p4→p5 gap 明显增大，不能被称为 robust-angle qualification。因此：

```text
common_mesh_replay_MPI8 = pass
theta0p7_10deg_mesh_direct_robust_angle_reuse = controlled_negative
next_lane = multi_angle_marking_or_independent_angle_reference
thresholds_relaxed = false
```

## Phase C 目标 artifact screen

| 目标点 → enriched 点 | R5 effectivity proxy | R5 Pearson/Spearman | R1 Pearson | R1/R5 marked Jaccard | observable error reduction |
|---|---:|---:|---:|---:|---:|
| p2/h5 → p2/h3 | 0.9086 | 0.9903 / 0.9918 | -0.0356 | 0.0998 | 87.46% |
| p2/h3 → p2/h2 | 0.8106 | 0.9981 / 0.9949 | -0.0768 | 0.1358 | 81.55% |
| p3/h10 → p3/h7.5 | 0.9894 | 0.9892 / 0.9836 | -0.0202 | 0.1035 | 94.00% |

所有 marked set 均以 Dörfler `theta=0.5` 的 global sample ID SHA-256 锁定。R5 是 accepted
field-pair difference proxy，不是 formal hierarchical FE solve；R1 是 sample-grid strong residual，
不是 cell-integrated production R1。后者相关性为负，所以不能进入 production marking。Task034
strip/tensor PDE 对照的 observable error 从 `3.577e-6` 恶化到 `2.378e-2`，且不是 Task035
estimator-marked refinement，故 Phase C 受控收口而不选 estimator。

## Phase D backend 决策

| backend | 结果 | 关键证据 |
|---|---|---|
| Task034 strip/tensor | `controlled_negative` | actual PDE；middle E/H 与 A_volume gates fail |
| multi-block conforming hexa | `hexa_backend_blocker` | strip leakage ratio 6.071；无 qualified transition-cell/hanging-node support |
| tetra marked refine control | `control_pass`，research control only | 384→1392 cells；min volume `3.255e-4`；Nédélec proxy error 0.3523→0.2749 |

B3/B4 通过；serial/MPI2 compact identity 通过。首次 MPI2 tetra volume measurement 因错误的
topology-to-geometry indexing 产生伪零体积，失败 record 永久保留；改用
`geometry.dofmap[cell]` 后 targeted serial 与 MPI2 均通过。

## 最终边界

```text
phase_c_internal_gate = complete_controlled_negative
phase_d_internal_gate = complete
actual_global_two_level_R5 = pass_hexa_control
actual_discrete_DtN_adjoint = pass
actual_goal_weighted_DWR = pass
periodic_tetra_target_pipeline = research_pass
actual_adaptive_cycles = two_consecutive_pass
selected_research_strategy_10deg = p4_p5_R_total_DWR_theta0p7_one_cycle
robust_angle_common_mesh = controlled_negative
multi_angle_lane = active
second_cycle = controlled_negative_cost_dominated
production_estimator_selected = false
production_backend_selected = false
ordinary_default_changed = false
```

Review V4 已授权按 measured evidence 连续推进；ordinary default 与 master merge 仍未改变。
