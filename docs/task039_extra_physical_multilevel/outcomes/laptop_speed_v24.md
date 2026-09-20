# V24 original p6/h7.5 laptop-speed formal outcome

## 结论先行

V24 在同一 `990-cell` original p6/h7.5 模型上完成了唯一一次正式 B。它通过了离散求解、显式真实残差、释放后残差、场/功率/守恒和资源清场检查，分类为：

`DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`

这里的“authority limited”很具体：没有匹配的独立 h7.5 参考场，因此本结果是当前离散模型的最佳可用正式结果，不是连续收敛或网格收敛证明。

本轮的工程改动把 p6 与 p4 之间反复搬运的局部数据按真实映射分组并复用有界工作区；p4 返回质量保留了同一 factor 的有界修正。它减少了重复准备和数据搬运，但没有改变物理方程、有限元空间、p4 数学算子或默认旧 profile。

## 身份与方法

| 项目 | V24 事实 |
|---|---|
| profile / stage | `physical_p6_trace_p4_condensed_laptop_speed_v24` / `Z3_ORIGINAL_H7P5` |
| source SHA | `b480178314efdf434c5f7405f2ab356ff9137c17` |
| 输入 SHA | `2ba2508861e02c2f1a9dbda433702c977eb0371cdb986350245e3caf15eb6928` |
| physical model SHA | `d8c5abb837adda92ea86e257cff9e2ff01ccf466879b08a2cde9a071e1d1d036` |
| resolved config SHA | `3e4a072525a5f853a12ee78b2f2b120f8478ba008c1fa4a623c5dd2ce97c4587`，14647 bytes |
| mesh / modes | `[9,5,22]`，990 cells，80 DtN modes |
| MPI / threads | MPI1；OMP、OpenBLAS、MKL、NumExpr 和 MUMPS 均为 1 |
| outer solver | FGMRES32，max2048，retained zero start，80-mode port included |

“单元凝聚”是先在每个有限元单元内部解掉局部未知量，只把共享 trace 与端口未知量交给外层迭代，最后恢复完整场。V24 的 owner-route 优化只改变局部数据如何复用和归并；它不减少单元、模式、积分点或物理检查。

正式路线冻结为 `optimized_owner_apply=true`、`fixed_serial_owner_route=true`、native A6 authority、旧 native FFCx power10 H6 setup；packed A6/packed power10 只保留为研究组件证据，没有进入正式 authority。

## 七个独立结论维度

| 维度 | 判定 | 证据与边界 |
|---|---|---|
| `A4_RETURN_QUALITY` | PASS，bounded repair | P1 前缀 PC2 native A4 从 `2.887066115526587e-10` 经同 factor 额外一次 MatSolve 降到 `9.827559370577234e-13`；根因仍分类为 `CAUSE_UNRESOLVED_BOUNDED_REPAIR_QUALIFIED` |
| `DISCRETE_SOLVE` | PASS | 126 iterations；独立显式相对残差 `9.283164961979326e-7`，门槛 `1e-6`；释放后相同 |
| `PHYSICS_CONSISTENCY` | PASS | field/power/channel/identity/energy/modal closure 等正式检查均为 true |
| `AUTHORITY_LIMITED` | PASS with limitation | `NOT_ATTEMPTED_REFERENCE_UNAVAILABLE`；不宣称 continuum convergence |
| `SPEEDUP` | MEASURED | 完整 workflow `4579.015917060999 s`（76.32 min），V23 baseline `5581.178597819002 s`（93.02 min），端到端比值 `1.218859837771` |
| `MEMORY_NONINCREASE` | observed below prior reference | RSS `7336173568 B`，比旧参考 `7387607040 B` 少 `51433472 B`；这是单核路线对照，不是多核内存中性证明 |
| `MULTICORE_ADOPTION` | NOT ADOPTED | 没有运行或通过 2/4-thread memory-neutral 资格试验；正式结果保持 MPI1/单线程 |

## 数值与物理结果

### 求解与释放后检查

| 指标 | 实测值 |
|---|---:|
| retained global size | 199340 |
| FGMRES iterations / MatVec / PC apply | 126 / 129 / 126 |
| KSP solve count | 1 |
| explicit residual（final） | `9.283164961979326e-7` |
| explicit residual（post-release） | `9.283164961979326e-7` |
| internal / native identity / port identity | `9.92421810145759e-18` / `1.4300763730437366e-11` / `3.912391739010179e-16` |
| Schur port identity | `5.862988874019337e-29` |

### 官方端口功率

官方 R/T/A 来自 DtN 端口模态振幅；同一输出包中的 Fourier E/H probe 只是 diagnostic，不能替代官方端口结果。

| 量 | official 值 |
|---|---:|
| `R_total` | `0.36509755370062585` |
| `T_total` | `0.013016803347759889` |
| `A_balance` | `0.6218856429516143` |
| `A_volume` | `0.6218856421339044` |
| `R_plus_T` | `0.37811435704838575` |
| `R00_p / R00_s / R00_total` | `3.441729252877729e-25 / 0.3650608628870489 / 0.3650608628870489` |
| `A_grating / A_substrate` | `0.6135111751743488 / 0.008374466959555545` |
| propagating / total modes | `78 / 80` |
| Rayleigh warnings | `0` |
| `A_port - A_volume` | `8.177098997919074e-10` |

诊断 Fourier E/H probe 的 `R/T/A = 0.36509307874412855 / 0.000028057916947023017 / 0.6348788633389244`，来源标记为 `diagnostic_eh_fourier_probe`，仅用于诊断，不纳入 official R/T/A。

## 成本、生命周期与资源

| 分项 | 实测值 |
|---|---:|
| full workflow | `4579.015917060999 s` |
| watchdog monotonic | `4578.8921036949905 s` |
| solver elapsed | `4064.2847061239304 s` |
| p4 logical / physical MatSolve | `254 / 255` |
| p4 reduce / solve / recover / total | `72.99329236106132 / 87.17264209411223 / 69.50814429990714 / 230.02264079889574 s` |
| native A4 / native A6 apply count | `255 / 283` |
| native A4 / native A6 cumulative total | `426.09123840702523 / 1637.1402389939758 s` |
| owner primal / adjoint | `255 / 258` calls；`74.13890026698937 / 65.49211706320057 s` |
| process-tree RSS / PSS peak | `7336173568 / 7303877632 B` |
| swap peak | `0 B` |
| resource samples | `1141` |

正式服务为 `inactive/dead`，systemd result `success`，exec status `0`；watchdog 为 `COMPLETED`，后代清场为 true。没有 OOM kill、残留 formal MPI/worker 或 swap 活动。

## 证据入口

- 正式 summary：[physical_dual_condensed_laptop_speed_v24_summary.json](../../../results/euv_grazing1_phi0/task39extra_v24_laptop_speed_original_h7p5__full3d_iterative__mpi1__Mna/20260920T111003.508765Z/physical_dual_condensed_laptop_speed_v24_summary.json)
- official output：[z3_output.json](../../../results/euv_grazing1_phi0/task39extra_v24_laptop_speed_original_h7p5__full3d_iterative__mpi1__Mna/20260920T111003.508765Z/official_output/z3_output.json)
- watchdog：[summary.json](../../../results/euv_grazing1_phi0/task39extra_v24_laptop_speed_original_h7p5__full3d_iterative__mpi1__Mna/20260920T111003.508765Z/watchdog/summary.json)
- 机器可读 compact：[laptop_speed_v24_compact.json](records/laptop_speed_v24_compact.json)
- A4 repair：[laptop_speed_v24_a4_repair.json](records/laptop_speed_v24_a4_repair.json)
- route/components：[laptop_speed_v24_components.json](records/laptop_speed_v24_components.json)
- checker/decision：[laptop_speed_v24_checker.json](records/laptop_speed_v24_checker.json)、[laptop_speed_v24_decision.json](records/laptop_speed_v24_decision.json)

大型 field、matrix、factor、event 和 resource 原始文件保留在 ignored run root，不进入 Git。V23 的 `58/59`、旧 authority limitation 和历史负结果均保持原分类。
