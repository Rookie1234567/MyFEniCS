# Task035b：高阶 local-hp 压缩与 0.7 nm / 2 TiB 资源桥接

## 当前身份

```text
task = Task035b
status = PARTIAL_WITH_CONTROLLED_NEGATIVES
execution_branch = codex/20260726-task35b-high-order-local-hp-resource-envelope
stacked_base = Task035 Review V6 commit 81c714b236e9c362df8783382f1d40a5cd888cd5
geometry_scope = Task034 fixed rectangular block grating only
irregular_geometry_research = out_of_scope_by_user
selective_master_merge = completed_at_1fb144d3ca50208c22b5f0733e140bfac8d9c47c
```

历史 Task035b 从 Task035 已完成的真实 DWR、周期 tetra、自适应循环和
高阶 p4/p5/p6 证据继续。Review V3 已把审查通过的文件级闭包选择性合入
`master`，并从合并后的干净 master 创建当前 20260726 分支；旧 20260723
stacked branch 保留为完整研究档案，没有整体 merge。

当前任务只研究固定规则结构。斜侧壁、圆角、缺口、粗糙度及其他假设性不规则几何全部移出本任务；等未来真实结构明确后再单独立项。资源模型中的保守 Hybrid factor 只作规划敏感性，不授权不规则几何 PDE。

## 核心问题

```text
在可信 global-p5/p6 高阶基线之上，
能否通过真正的 local p 保留/降低、少量局部 h、必要的静态凝聚，
在不降低 R00/R/T/Aclosure 和独立场误差的前提下，
把 13.5 nm Full3D-equivalent DoF 压到 <=90k，优选 65k–75k，
从而把 0.7 nm Hybrid local-3D FE 规模映射到约 150M–250M DoF？
```

## 必读材料

- [`task.md`](task.md)
- [`task_scope_addendum_v1.md`](task_scope_addendum_v1.md)
- [`review_report_v1.md`](review_report_v1.md)
- [`review_report_v2.md`](review_report_v2.md)
- [`review_report_v3.md`](review_report_v3.md)
- [`response_v2.md`](response_v2.md)
- [`response_v3.md`](response_v3.md)
- [`../task035_hcurl_goal_oriented_adaptivity/review_report_v6.md`](../task035_hcurl_goal_oriented_adaptivity/review_report_v6.md)
- [`../task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md`](../task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md)
- [`../task035_hcurl_goal_oriented_adaptivity/response_v5.md`](../task035_hcurl_goal_oriented_adaptivity/response_v5.md)
- [`../COMSOL_direct_solver_report.md`](../COMSOL_direct_solver_report.md)
- Task034 Case093、Hybrid M funnel 和资源模型 v2.1

发生范围冲突时，`task_scope_addendum_v1.md` 优先于原 `task.md`。

## 执行方式

Task035b 继续采用 measured-evidence 驱动的连续自主研究：有正信号就加深，有明确负信号就保留记录并切换路线。阶段名称用于组织，不是逐阶段等待审批的锁。

普通默认、production 声明和 `master` 合并仍需最终审阅和用户确认。

## 当前结论与交付

Review V1 连续批次冻结了 12 通道 reference v1，并完成 16/16 独立
Hermitian channel adjoint、mesh/topology、phase、trace 与 DtN/port
根因假设判别和最小 MPI8 方向性恢复。当前最强预算内点为 fixed
p5-trace/p6-interior h13：
89,740 Full3D-equivalent DoF、20,120 rows、10/12 significant powers、
10/12 complex amplitudes；它仍未达到强制 12/12 + 12/12。

Review V2 完成了两个 fixed-DoF z-node 判别；h13 top2 redistribution 与
h14 exact-reverse 的实际结果分别为 8/12 + 8/12 和 7/12 + 8/12，因此该
lane 已按连续负信号关闭。physical selective-trace 已推进到
fixture/correctness-qualified 的 physical expansion、Stage4 row omission、
pre-release hook 和 owner-aware MatShell，但 actual channel DWR、formal
runner、candidate 与 PDE 数量仍为 0。

setup/resource 主线是正结果：h15/h13 non-KSP cold/warm build 分别降至
19.242/6.141 s 与 19.410/6.696 s。h15 MPI1/2/4/8 direct study 的最低实测
process-tree peak 是 MPI1 的 1.295 GiB，说明旧 5.8–6.4 GiB 不是内存
下限，但该点也不是理论或 factor-free 下限。三种 programmatic assembled
iterative screen 均在 200 iterations 不收敛，作为 controlled negatives
保留，且没有 official R/T/A/channel 输出。

因此当前仍没有 Hybrid-eligible same-error candidate；Hybrid closure、
M funnel、external DtN funnel 和 0.7 nm resource model v3 保持
`not_run_by_selected_candidate_gate`。

Review V3 完成文件级选择性合并后，新分支已实现 local-FE static
condensation + Hybrid。p2/h5 H1-A 的 standard/static 等价和
M120→M160 均为 12/12 power + 12/12 amplitude，但 static Full3D
与 static Hybrid 的同离散闭合只有 3/12 + 2/12；按 strict absolute audit
是 2/12 + 2/12。因此 H1-A 以 controlled negative 收口，H1-B、H1-C、
h13 seed 和 adaptive Hybrid 均按 Review prerequisite 未运行。详见：

- [`outcomes/hybrid_static_condensation_h1.md`](outcomes/hybrid_static_condensation_h1.md)
- [`response_v5.md`](response_v5.md)

- [`outcomes/summary.md`](outcomes/summary.md)
- [`outcomes/regular_geometry_compression.md`](outcomes/regular_geometry_compression.md)
- [`outcomes/local_hp_capability.md`](outcomes/local_hp_capability.md)
- [`outcomes/high_p_memory_anatomy.md`](outcomes/high_p_memory_anatomy.md)
- [`outcomes/resource_projection_0p7nm.md`](outcomes/resource_projection_0p7nm.md)
- [`outcomes/all_candidates.json`](outcomes/all_candidates.json)
- [`outcomes/negative_results.md`](outcomes/negative_results.md)
- [`outcomes/significant_channel_convergence.md`](outcomes/significant_channel_convergence.md)
