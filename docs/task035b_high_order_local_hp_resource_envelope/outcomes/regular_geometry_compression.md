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
其他 node distributions 未被证明无效且未运行。

global p6/h14 的 9/12 power、12/12 amplitude 是 same-mesh full-trace
measured positive marginal；它不定位 missing-mode subset，也不建立 trace
相对 mesh/DtN 的唯一或次级因果排序。92,850 DoF 超上限 2,850。当前仅有
reference-cell complement/Riesz 和 recovered-dual coefficient proxy，没有
physical Piola/Riesz、missing-mode Floquet orbit、actual enriched
residual/DWR 或真实 active numbering。因此 selective trace 记为
`capability_stop_not_run`，不是一个失败 PDE。

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

## Hybrid 决定

所有预算内恢复候选都未通过完整 same-error Gate；global p6/h14 又超预算，
因此：

```text
selected candidate = null
Hybrid closure = not_run_by_selected_candidate_gate
M funnel = not_run
0.7 nm PDE = not_run
```

该结论不否定 static condensation、preallocation、DWR 或 classifier 的可复用
工程价值；它只表示本轮没有达到 Task035b 的 production accuracy 合同。
