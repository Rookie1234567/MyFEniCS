# Task035b：高阶 local-hp 压缩与 0.7 nm / 2 TiB 资源桥接

## 当前身份

```text
task = Task035b
status = in_progress
execution_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
stacked_base = Task035 Review V6 commit 81c714b236e9c362df8783382f1d40a5cd888cd5
geometry_scope = Task034 fixed rectangular block grating only
irregular_geometry_research = out_of_scope_by_user
master_merge = not_authorized
```

Task035b 从 Task035 已完成的真实 DWR、周期 tetra、自适应循环和高阶 p4/p5/p6 证据继续，不从 `master` 重新移植。Task035 原分支保留为审查基线；Task035b 的代码、records、outcomes 和 response 全部写在本 stacked branch。

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
- [`../task035_hcurl_goal_oriented_adaptivity/review_report_v6.md`](../task035_hcurl_goal_oriented_adaptivity/review_report_v6.md)
- [`../task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md`](../task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md)
- [`../task035_hcurl_goal_oriented_adaptivity/response_v5.md`](../task035_hcurl_goal_oriented_adaptivity/response_v5.md)
- [`../COMSOL_direct_solver_report.md`](../COMSOL_direct_solver_report.md)
- Task034 Case093、Hybrid M funnel 和资源模型 v2.1

发生范围冲突时，`task_scope_addendum_v1.md` 优先于原 `task.md`。

## 执行方式

Task035b 继续采用 measured-evidence 驱动的连续自主研究：有正信号就加深，有明确负信号就保留记录并切换路线。阶段名称用于组织，不是逐阶段等待审批的锁。

普通默认、production 声明和 `master` 合并仍需最终审阅和用户确认。
