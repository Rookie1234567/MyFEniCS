# Task035b 规则几何压缩结果

## 最终状态

```text
geometry = Task034 fixed rectangular block grating only
status = PARTIAL_WITH_CONTROLLED_NEGATIVES
hybrid_eligible_candidate_count = 0
ordinary_default_changed = false
```

Task035b 证明了 high-p condensation、真实物理减行和内存生命周期优化可以
显著降低 rows、NNZ、factor、peak 和时间；但没有候选同时通过完整 same-error
合同，因此没有声称规则几何压缩成功。

## 主要候选

| candidate | Full3D-equiv DoF | rows | matrix/factor NNZ | peak | build/setup/solve | same-error conclusion |
|---|---:|---:|---:|---:|---:|---|
| global p6/h15 | 84,492 | 24,704 | 19,207,136 / 59,616,320 | 12.000 GiB pair | 396.93 / 21.53 / 0.057 s | scalar/field pass；channels 6/12、8/12 |
| fixed p5-trace/p6-interior h15 | 74,890 | 16,880 | 9,195,812 / 27,916,600 | 5.803 GiB | 61.65 / 6.56 / 0.036 s | scalar/field pass；channels 6/12、7/12 |
| fixed h14 directional-z | 82,315 | 18,500 | 10,104,512 / 31,347,000 | 6.376 GiB | 62.31 / 11.47 / 0.031 s | scalar/field pass；channels 7/12、9/12 |
| fixed h13 directional-z | 89,740 | 20,120 | 11,013,212 / 36,273,200 | 6.411 GiB | 59.86 / 13.34 / 0.033 s | scalar/field pass；channels 10/12、10/12 |
| fixed h15 x-only | 87,195 | 19,680 | 10,728,434 / 33,056,800 | 6.590 GiB | 63.13 / 7.64 / 0.033 s | scalar/field pass；channels 5/12、6/12 |
| h14 R5-slab bisect | 89,740 | 20,120 | 11,013,212 / 36,273,200 | 6.463 GiB | 60.07 / 13.57 / 0.035 s | scalar/field pass；channels 5/12、9/12 |
| global p6/h14 diagnostic | 92,850 | 27,080 | 21,110,096 / 67,325,792 | 12.587 GiB pair | 89.48 / 25.36 / 0.063 s | channels 9/12、12/12；over cap |
| p4-trace p4/p6-interior h10 | 88,994 | 21,824 | 8,184,464 / 42,888,832 | 6.072 GiB | 175.52 / 11.45 / 0.038 s | scalar/vector/orders/fields fail |
| p5-trace p4/p6 N62 h10 | 89,755 | 35,000 | 20,140,928 / 101,062,900 | 9.271 GiB | 344.16 / 37.20 / 0.074 s | non-exact-sequence + accuracy fail |

### global p6/h15

相对 h10 global p6，它达到 `2.057x` DoF、`2.075x` rows、`2.186x`
matrix-NNZ 和 `3.401x` factor-NNZ 压缩。scalar/vector、selected frozen
field probes、true residual 和资源均通过；significant diffraction power
只有 `6/12`、complex amplitude `8/12` 通过。因此正式分类为
`controlled_negative_full_same_error_gate`。

### fixed p5-trace/p6-interior h15

该 exact-sequence physical reduction 落入 65k–75k 优选带，并且不保留
inactive p6 trace rows。相对同网格 global p6，DoF/rows/matrix-NNZ/factor-NNZ
分别压缩 `1.128x/1.464x/2.089x/2.136x`。scalar/vector 和 frozen field
probes 通过，但 diffraction power/amplitude 只有 `6/12`、`7/12`，所以不
进入 Hybrid。

exact preallocation 是独立工程正结果：

| implementation | allocated/unused NNZ | mallocs | build | elapsed | peak |
|---|---:|---:|---:|---:|---:|
| original | 12,694,691 / 3,498,879 | 13,856 | 231.15 s | 269.72 s | 6.105 GiB |
| tensor dedup | 12,694,691 / 3,498,879 | 13,856 | 83.71 s | 121.65 s | 6.001 GiB |
| dedup + exact preallocation | 9,484,580 / 288,768 | 0 | 61.61 s | 95.96 s | 5.803 GiB |

used NNZ、factor NNZ 和物理结果不变，因此优化结论可信，但不能改变 accuracy
分类。

### Review V1 structured-h 与 trace 判别

h15→h14→h13 的 z-direction 序列把通道通过数从 `6/7` 提升到
`7/9`、再到 `10/10`，提供连续但未闭合的 topology/refinement response；
它支持 z-resolution 相关候选原因，不单独证明 phase 机制或唯一因果。
h13 仍失败：

- power：`T(-4,0)_s`、`R(-4,0)_s`；
- amplitude：`R(-5,0)_s`、`R(-4,0)_s`。

x-only 退化到 5/6；y-only global-p5 mechanism control 保持 3/1，但不是
same-space fixed-trace y 排除。q31 与 scaled buffer1 仍为 6/7，只覆盖这
两个已测试 DtN 扰动。只二分最大 R5 slab 虽降低 aggregate error，却退化到
5/9 并新增 `R(-7,0)_s` power failure，因此预先指定的 split lane 关闭；
Review V2 随后只运行两个 adjoint-guided fixed-DoF node 判别点，结果见下表。

global p6/h14 的 9/12 power、12/12 amplitude 是 same-mesh full-trace
measured positive marginal；它不定位 missing-mode subset，也不建立 trace
相对 mesh/DtN 的唯一或次级因果排序。92,850 DoF 超上限 2,850。当前仅有
reference-cell complement/Riesz 和 recovered-dual coefficient proxy。新增
typed caller expansion、Stage4 pre-release hook、owner-aware MatShell 与
row-omission fixture/correctness 能力仍未生成 actual enriched
residual-weighted DWR、物理 row plan 或 selective PDE；因此它不是一个失败
PDE，也不是已闭合的 formal runner。

### Review V2 fixed-DoF node 判别与 lane 关闭

| candidate | topology | DoF / rows | matrix/factor NNZ | peak | power / amplitude | conclusion |
|---|---|---:|---:|---:|---:|---|
| h13 top2 phase redistribution | `(6,2,12)` | 89,740 / 20,120 | 11,013,212 / 36,273,200 | 5.886 GiB | 8/12 / 8/12 | controlled negative |
| h14 exact reverse | `(6,2,11)` | 82,315 / 18,500 | 10,104,512 / 32,338,600 | 5.958 GiB | 7/12 / 8/12 | controlled negative |

两点都通过 scalar/vector、identity、full residual 与资源 Gate，但 significant
channels 比原 h13 `10/12 / 10/12` 更差。h14 record 中的 `9/12 / 11/12`
只是 derived reverse projection forecast；正式结论使用实际 PDE 的
`7/12 / 8/12`。连续两个负信号后，fixed-DoF z-node lane 关闭。

### Review V2 selective-trace capability 与结构性 blocker

`physical_selective_trace_execution_capability_v2.json` 只资格化 typed
expansion、default-off Stage4 callback、owner-aware MatShell action 和
inactive-row omission 的 fixture/correctness contract。其正式边界仍是：

```text
runner_wired = false
actual_residual_weighted_channel_dwr_count = 0
physical_row_plan_count = 0
selective_candidate_count = 0
selective_pde_run_count = 0
```

真正减行的 fixed-trace local-Schur path 使用 reduced
p5-trace/p6-interior element，而现有 generalized-recovery path 要求 standard
full-p6 storage；当前 Stage4 不能在一次运行中同时满足两者。这是必须先解除的
结构性 blocker。不得把 fixture 能力写成新 runner wiring，也不得用 full-p6
矩阵后置零冒充 physical selective trace。

### h10 regionwise candidates

p4 fixed trace 候选在 exact-sequence 审计中有效，且 matrix 是真实减行，
但 normalized R/T/Aclosure 为 `27.704`、volume/interface field error 为
`9.847%/9.778%`，12 个 significant power/amplitude channel 全部失败。

p5-trace N62 虽然 residual 为 `1.57e-12`，其 p4-low space curl nullity
`112` 小于 expected gradient dimension `178`，缺少 66 个 gradient modes。
它被重分类为 `controlled_negative_non_exact_sequence_space`；小 residual
只证明错误离散系统被准确求解。

## 静态凝聚与内存结论

assembly-time exact cell Schur + Floquet slave elimination 使 h10 p6 从
173,882 augmented rows 降为 51,272 active rows，matrix NNZ 从
210,353,120 降为 41,989,040；配合 factor release 和 heap trim，formal
peak 从 35.024 GiB 降为 15.964 GiB。恢复后的 full explicit residual 和
R/T/A 与 global p6 等价。

这回答了“自由度降低后内存为何不降”：仅 post-assembly 降 rows 时，完整
matrix 生命周期与稠密 Schur fill 仍存在；在完整 matrix、inactive rows、
多余 tensor 和 factor 生命周期被真正消除后，内存与时间按正确方向下降。

## Review V2 cold/warm setup 与 direct 内存下限

| case, MPI8 | non-KSP build cold / warm | common solver cold / warm | MUMPS numeric cold / warm | process-tree RSS cold / warm |
|---|---:|---:|---:|---:|
| fixed h15 | 19.242 / 6.141 s | 37.595 / 19.489 s | 5.807 / 6.028 s | 4.602 / 4.453 GiB |
| fixed h13 | 19.410 / 6.696 s | 45.568 / 26.899 s | 13.266 / 12.675 s | 5.030 / 5.016 GiB |

h15 cold non-KSP build 相对 61.61 s Review V2 preoptimization authority 达到
`3.202x`，通过 >=2x 和 25–30 s 目标；两个 warm build 均 <10 s。h13 的
`2.899x` 只是 cold→warm persistent-cache reuse，因为不存在 same-h13
preoptimization cold baseline。上述 setup records 不重新评估 12 通道，也不
提升候选。

h15 同 operator 的 direct rank study 给出：

| MPI | RSS | PSS / USS | common solver | MUMPS symbolic+numeric |
|---:|---:|---:|---:|---:|
| 1 | 1.295 GiB | 1.257 / 1.243 GiB | 76.007 s | 29.969 s |
| 2 | 2.158 GiB | 2.013 / 1.918 GiB | 74.913 s | 19.437 s |
| 4 | 3.100 GiB | 2.723 / 2.612 GiB | 61.849 s | 12.400 s |
| 8 | 4.711 GiB | 3.876 / 3.758 GiB | 53.901 s | 6.527 s |

四点均 residual pass、0 swap。MPI1 是最低实测 direct memory point，但不是
理论/软件/factor-free floor；MPI8 用 `3.64x` RSS 换取 `1.41x` wall-time
改善。MPI4/8 的 50 tasks/rank 仅在 solver release 后的 VTK/TBB postprocess
窗口出现，direct factor peak 在此之前且更高，不能把它归因于隐藏的 MUMPS
solve threads。

## Smoothness、DWR 与 h/p 竞争

252/252 cells 的 physical hierarchical p6/p5 decay 为
`0.16201–0.16783`，p5/p4 projection-defect decay 为
`0.18988–0.19644`。classifier v3 得到
`p-up=102 / p-keep=150 / h-refine=0 / p-down=0`，但因为旧 signal record
缺少新 contract/roundtrip/hash-scope 字段且没有独立 phase-resolution
authority，仍为 `production_qualified=false`。

现有 tetra 顺序代理 `base p5 -> one local-h p5 -> fixed-mesh p6` 显示：

- local-h 的 vector-error log gain/added DoF 更高；
- p-up 的 strict-R log gain/added DoF 更高；
- final p6 为 167,784 DoF，vector control pass 但 strict-R control fail。

该记录不是 same-patch head-to-head cell authority。structured hexa 缺少
hanging-node/transition conformity，tetra selected-p6 又未实现；结合既有
h50/h37.5 预算证据，Task035 继承的 tetra local-h + selected-p6 组合以
`stopped_by_gate_architecture_and_budget` 收口，不重复 Task035 heavy cases。
classifier 的零 `h_refine` 分类不覆盖 Review V1 后来实测的 global
directional-z topology/refinement response；两种证据的 scope 不同。

## Review V2 iterative controlled negatives

三个独立 opt-in MPI8 profiles 均在 200 iterations 后未收敛：

| profile | final/initial residual | full recovered residual | peak | official physics |
|---|---:|---:|---:|---|
| GMRES + Jacobi | 0.861662 | 0.861661 | 3.921 GiB | none |
| FGMRES + ASM-ILU(0) | 0.999661 | 0.999659 | 4.462 GiB | none |
| FGMRES + z-slab ILU(0) + 80-D DtN correction | 0.996265 | 0.996263 | 3.885 GiB | none |

前两者没有 global direct factor；第三者也没有 global MUMPS factor，但包含
local ILU(0) 与 dense coarse LU，因此不称 strictly factorless。三者的较低
RSS 都只是 controlled-negative resource evidence，不是合格 solution memory
floor。当前 assembled iterative lane 只可由 materially different
spectral/auxiliary-space preconditioner 重开；matrix-free 不会自动修复已暴露
的 preconditioner 缺口。

## Hybrid 决定

accuracy best 仍为 fixed h13：89,740 Full3D-equivalent DoF、
`10/12` power + `10/12` complex amplitude。两个 fixed-DoF node follow-up
均退化，formal selective runner 尚未闭合，三个 iterative profile 未收敛；
因此：

```text
selected candidate = null
best measured accuracy = fixed h13, 10/12 power + 10/12 amplitude
hybrid_eligible_candidate_count = 0
Hybrid closure = not_run_by_selected_candidate_gate
M funnel = not_run
0.7 nm PDE = not_run
```

该结论不否定 static condensation、preallocation、DWR 或 classifier 的可复用
工程价值；它只表示本轮没有达到 Task035b 的 production accuracy 合同。
