# Task035b Response V1

## 1. 身份与状态

```text
execution_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
task035b_start_head = c29ce474a96bc50019968eef9c8330d4a9ef6f53
stacked_task035_review_v6 = 81c714b236e9c362df8783382f1d40a5cd888cd5
implementation_and_record_head = 6af98f1e0a51a37798b924c40141d31ac6103643
final_status = PARTIAL_WITH_CONTROLLED_NEGATIVES
ordinary_default_changed = false
master_merge = not_authorized
```

最终文档提交和远程 HEAD 由交付消息给出；本文件不通过自引用猜测尚未创建的
commit SHA。

## 2. 范围回应

| requirement | disposition |
|---|---|
| fixed rectangular block only | 完成；全部 formal PDE 为 G0 |
| irregular G1/G2/Phase F | `out_of_scope_by_user / not_run / not_a_completion_gate` |
| same-mesh p4/p5/p6 | MPI8 pass |
| edge/face/cell DoF inventory | pass |
| rows/NNZ/row width/factor/fill/peak/time | measured |
| exact static condensation | pass，opt-in research path |
| physical local/regionwise p | implemented；两个 MPI8 accuracy negatives |
| strict R00/R/T/Aclosure + vector | measured |
| significant orders/amplitudes + fields | measured；最终候选 channel fail |
| DWR_R00/R/T + normalized multi-goal | pass |
| eta p4p5/p5p6 + projection/smoothness | 252-cell actual signals saved |
| h/p classifier | v3 research-qualified，production false |
| one local-h then fixed-mesh p+1 | inherited actual tetra sequence audited |
| `<=90k` / preferred 65k–75k | resource-only candidates exist；no full same-error success |
| Hybrid / M funnel | stopped by selected-candidate Gate |
| 0.7 nm / 2 TiB | planning sensitivity only；production peak/feasibility unknown |

## 3. 主要实现

### 3.1 High-p resource path

- assembly-time exact cell Schur，不再先装配 full p6 matrix；
- physical Floquet slave elimination，不保留 embedded identity rows；
- full-vector recovery + matrix-free full explicit residual；
- solver/factor release 与 rank-wise `malloc_trim`；
- cell tensor dedup、批量复用和 exact sparse preallocation；
- measured entity DoF、active rows、NNZ、row width、MUMPS factor/fill、
  simultaneous process-tree peak 和分阶段时间。

### 3.2 Local/regionwise H(curl)

- p4 trace + p4/p6 interior 的 physically reduced path；
- p5 trace + p4-low/p6-high 的研究 path；
- local tensor de Rham rank audit；
- fail-closed exact-sequence preflight；
- wrong-control、postprocess failure 和 non-exact sequence evidence 全部保留。

### 3.3 DWR 与 classifier

- independent Hermitian adjoints for `R00_total`、`R_total`、`T_total`；
- tolerance-normalized R/T multi-goal，strict R00 保持独立；
- periodic transitive aggregation；
- physical hierarchical shell、projection defect、R5、DWR 和 material/interface
  prior 融合；
- smooth/interface/corner/high-frequency synthetic fixtures；
- MPI collective fail-fast 与 partition-stable snapshot audit。

## 4. 关键结果

| candidate | DoF / rows | matrix/factor NNZ | peak | accuracy | status |
|---|---:|---:|---:|---|---|
| h10 global p6 control | 173,802 / 51,272 | 41,989,040 / 202,441,352 | pair 19.977 GiB | accepted discrete baseline | pass |
| global p6/h15 | 84,492 / 24,704 | 19,207,136 / 59,616,320 | 12.000 GiB pair | scalar/vector/field pass；channels 6/12、8/12 | controlled negative |
| fixed p5-trace/p6-interior h15 | 74,890 / 16,880 | 9,195,812 / 27,916,600 | 5.803 GiB | scalar/vector/field pass；channels 6/12、7/12 | controlled negative |
| p4-trace regionwise h10 | 88,994 / 21,824 | 8,184,464 / 42,888,832 | 6.072 GiB | complete accuracy fail | valid exact-sequence negative |
| p5-trace N62 h10 | 89,755 / 35,000 | 20,140,928 / 101,062,900 | 9.271 GiB | accuracy fail + missing 66 gradient modes | non-exact-sequence negative |

fixed h15 exact preallocation 将 mallocs 从 13,856 降为 0、unused NNZ 从
3,498,879 降为 288,768、build 从 231.15 s 降为 61.61 s、peak 从
6.105 GiB 降为 5.803 GiB；used NNZ、factor 和物理结果不变。

classifier v3 得到 `p-up=102 / p-keep=150 / h-refine=0 / p-down=0`。
target signal 全部解析，但缺少 same-patch h-vs-p、independent phase-resolution
及 latest element-contract record，所以 `production_qualified=false`。

## 5. 研究决定

1. p4 fixed trace lane 因合格 accuracy negative 关闭。
2. p5-trace/p4-interior 因 non-exact-sequence preflight 永久禁止重复。
3. h15 global/fixed trace 因 significant channel Gate 失败，不接入 Hybrid。
4. structured hexa local-h 与 tetra selected-p6 当前架构不相交；结合预算与
   classifier 零 h-refine 信号，Lane B 为
   `stopped_by_gate_architecture_and_budget`。
5. Hybrid、M funnel、0.7 nm PDE 均未运行；没有把 resource-only DoF 写成
   same-error success。

## 6. 测试与证据

当前已完成：

- focused serial：`100 passed, 7 skipped`；
- MPI2：两 rank 各 `17 passed`；
- Task034/035 regression：`173 passed, 3 skipped`；
- final full repository：`680 passed, 28 skipped`；
- formal same-error runner 已修复为完整 `--untracked-files=all` source audit；
- Task035b scoped Ruff、compileall、945 个 tracked JSON parse 通过；
- full Ruff 仅剩 15 条 inherited findings，均位于本 Task 未修改文件；
- 42-row all-candidate JSON/CSV identity 与 path audit；
- `git diff --check`。

full repository pytest、Ruff、compileall 和最终 JSON/status Gate 见
[`outcomes/test_summary.md`](outcomes/test_summary.md)，交付前填入最终结果。

完整证据入口：

- [`outcomes/summary.md`](outcomes/summary.md)
- [`outcomes/reference_and_resource_target.md`](outcomes/reference_and_resource_target.md)
- [`outcomes/high_p_memory_anatomy.md`](outcomes/high_p_memory_anatomy.md)
- [`outcomes/local_hp_capability.md`](outcomes/local_hp_capability.md)
- [`outcomes/regular_geometry_compression.md`](outcomes/regular_geometry_compression.md)
- [`outcomes/resource_projection_0p7nm.md`](outcomes/resource_projection_0p7nm.md)
- [`outcomes/all_candidates.json`](outcomes/all_candidates.json)
- [`outcomes/negative_results.md`](outcomes/negative_results.md)
- [`../../benchmarks/cases/095_high_order_local_hp_resource_envelope/README.md`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/README.md)

## 7. Selective-merge proposal

当前只提交 Task035b 执行分支供 review；未请求合并 master。

| group | review disposition |
|---|---|
| production numerical/core | exact condensation、Floquet slave elimination、resource audit、same-error primitives；需独立代码 review 与 final acceptance |
| reusable runner/watchdog | Task035 formal runner extensions、same-error/checker、resource/provenance；候选 |
| checker/tests | Task035b 113–117、classifier/collective regressions；候选 |
| compact evidence/docs | Case095 records、outcomes、response；应保留 |
| research-only | regionwise variable-p candidates、classifier v3 policy、heap-trim/preallocation opt-ins；不得成为 ordinary default |
| do-not-promote | non-exact p5-trace/p4-interior、formal failures、accuracy-negative layouts |

所有 merge 决定等待新的 review 和用户明确授权；不得 whole-branch 自动合并。
