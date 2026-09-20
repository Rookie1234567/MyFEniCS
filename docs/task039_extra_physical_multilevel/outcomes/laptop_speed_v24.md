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
| input_original.dat SHA | `2ba2508861e02c2f1a9dbda433702c977eb0371cdb986350245e3caf15eb6928` |
| physical model SHA | `d8c5abb837adda92ea86e257cff9e2ff01ccf466879b08a2cde9a071e1d1d036` |
| resolved config SHA | `3e4a072525a5f853a12ee78b2f2b120f8478ba008c1fa4a623c5dd2ce97c4587`，14647 bytes |
| RHS storage | archive `9c6d9f1251437db65f74f534586f038ceb9027d99b88866922b13da5e0e05f9f`；array bytes `b85dde2599428906be4ffd2f2200438f3011e57358d20a541679b3ab50687824` |
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
| `MEMORY_NONINCREASE` | observed below prior reference | 正式连续 watchdog process-tree RSS/PSS=`7339319296/7307023360 B`，相对旧参考 RSS 少 `48287744 B`；这是单核路线对照，不是多核内存中性证明 |
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
| true KSP monotonic / old V23 KSP | `3716.1522563079925 / 4737.310983555995 s`；两场均126步，`29.493271875460258 / 37.59770621869837 s/step` |
| solver elapsed | `4064.2847061239304 s`；不作为 KSP 时间 |
| factor symbolic / numeric | `0.5657629839988658 / 216.7832953909965 s`；full setup 精确边界 `unknown` |
| p4 logical / physical MatSolve | `254 / 255` |
| p4 reduce / solve / recover / total | `72.99329236106132 / 87.17264209411223 / 69.50814429990714 / 230.02264079889574 s` |
| native A4 / native A6 apply count | `255 / 283` |
| native A4 / native A6 cumulative total | `426.09123840702523 / 1637.1402389939758 s` |
| owner primal / adjoint | `255 / 258` calls；`74.13890026698937 / 65.49211706320057 s` |
| process-tree RSS / PSS peak | `7339319296 / 7307023360 B` |
| swap peak | `0 B` |
| watchdog resource samples | `16998`；resources SHA `0b220a16d4cb096ea6a00a808e1a76b547bee42867b5152044f04e1e5e6a4e79` |
| watchdog summary | `COMPLETED`；summary SHA `4a73bd0c392416486c7a6b03afab9b7190eb37722a0ad543341b67e5fb820fb6`；descendants cleared；global swap delta 0 |
| worker snapshot | `1142` samples，SHA `185cc5d39631385c9373073185b3c2552cf76672bba6161c30cdfce49eddc63a`；只作非权威旁证 |

正式 watchdog 中曾观测到 `vanished_pids=[373722]`，但该样本同时保持状态/PSS 可读、unreadable 为空，且终态 leader=0、后代清空；这是采样时正常退出竞态，不作为失败门槛。global swap 只按 watchdog summary 的 delta 判定，不把系统累计计数的起点值当作新门槛。

## PC 边界、离线 checker 与 FE 回归

PC 记录绑定 `127` 个 boundary、`254` 个 logical call、`255` 个实际 factor solve；每个 boundary 有两次 `BAL_H` coarse call，`inner_ksp=false`、`max_it=2048`、`restart=32`、soft/hard PC 时间为 `25/30 s`。本轮 formal PC 的 `time_policy=observe_only`，未启用时间终止；这两个值只作记录和边界核对。保存的抽样闭合按 `closure_norm / operation_scale` 重算，最大 `4.309333201200774e-11`，限值 `1e-8`。A4 的 raw JSON 为 `254` 个 raw 加 `1` 个 `correction_1`，最终 rho 始终以原始 raw `g` 为分母。

独立离线 checker 从 raw fields 重算显式 residual、A4 rho、身份、PC 约束、channel/field/功率和旧 B 同离散回归；结果 `passed=true`，audit SHA 为 `58ca321b21a01ac60a57beaf1699c9f76f17f0b92a8f2af7a565fbc96c0b32ef`，checker 脚本 SHA 为 `c4205d929f4add3f4ca0dd58ca6f736cb749e7ff941786ecf00856f30cbaaebf`。旧 V23 只作为同离散回归输入，不覆盖其历史 `58/59` 负结果。

保存场上的同离散 FE 指标后处理为工程证据，不是新 PDE：L2 相对差 `1.8744734231920724e-14`，scaled-curl 相对差 `1.351616670038343e-13`，均由 artifact 的 absolute/reference 重新计算且低于 `1e-4`。成功 wrapper 使用 `LEGACY_STATIC_MEMORY_ENVELOPE + time_policy=enforce`，不是正式物理 watchdog 策略。首次 wrapper 以 `TIMEBASE_INCONSISTENCY` 受控停止（49.30150357799721 s，RSS `1280192512 B`，swap0，清场），该负记录保留，不能改判为数值失败。

正式服务为 `inactive/dead`，systemd result `success`，exec status `0`；watchdog 为 `COMPLETED`，后代清场为 true。没有 OOM kill、残留 formal MPI/worker 或 swap 活动。

## 证据入口

- 正式 summary：[physical_dual_condensed_laptop_speed_v24_summary.json](../../../results/euv_grazing1_phi0/task39extra_v24_laptop_speed_original_h7p5__full3d_iterative__mpi1__Mna/20260920T111003.508765Z/physical_dual_condensed_laptop_speed_v24_summary.json)
- official output：[z3_output.json](../../../results/euv_grazing1_phi0/task39extra_v24_laptop_speed_original_h7p5__full3d_iterative__mpi1__Mna/20260920T111003.508765Z/official_output/z3_output.json)
- watchdog：[summary.json](../../../results/euv_grazing1_phi0/task39extra_v24_laptop_speed_original_h7p5__full3d_iterative__mpi1__Mna/20260920T111003.508765Z/watchdog/summary.json)
- independent offline audit：[v24_independent_offline_audit_v2.json](../../../results/euv_grazing1_phi0/task39extra_v24_laptop_speed_original_h7p5__full3d_iterative__mpi1__Mna/20260920T111003.508765Z/v24_independent_offline_audit_v2.json)
- same-discrete FE metric artifact：[v24_same_discrete_fe_metrics.json](../../../results/euv_grazing1_phi0/task39extra_v24_laptop_speed_original_h7p5__full3d_iterative__mpi1__Mna/20260920T111003.508765Z/engineering/v24_same_discrete_fe_metrics.json)
- 机器可读 compact：[laptop_speed_v24_compact.json](records/laptop_speed_v24_compact.json)
- A4 repair：[laptop_speed_v24_a4_repair.json](records/laptop_speed_v24_a4_repair.json)
- route/components：[laptop_speed_v24_components.json](records/laptop_speed_v24_components.json)
- checker/decision：[laptop_speed_v24_checker.json](records/laptop_speed_v24_checker.json)、[laptop_speed_v24_decision.json](records/laptop_speed_v24_decision.json)

大型 field、matrix、factor、event 和 resource 原始文件保留在 ignored run root，不进入 Git。V23 的 `58/59`、旧 authority limitation 和历史负结果均保持原分类。
