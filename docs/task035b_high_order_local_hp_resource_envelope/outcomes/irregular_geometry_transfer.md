# Task035b 不规则几何移交状态

## 权威状态

```text
status = out_of_scope_by_user
PDE = not_run
completion_gate = not_a_completion_gate
ordinary_default_changed = false
```

`task_scope_addendum_v1.md` 将原任务书 G1、G2 与 Phase F 的不规则几何研究
从 Task035b 范围中移除。Task035b 只研究 Task034 fixed rectangular block
grating，不创建、不运行、也不推断以下几何的数值结果：

- sloped sidewall、rounded corner、curved profile；
- local notch、defect、roughness、sharp perturbation；
- 任意人为发明的不规则结构。

本文没有 geometry、mesh、PDE、DoF、残差、R/T/A 或资源结果。classifier
中的 unit-cube smooth/interface/corner/high-frequency 测试全部是
`synthetic_method_fixture=true / target_physics_evidence=false`，只验证方法
的 fail-closed 行为，不是未来真实不规则结构的替代证据。

0.7 nm 资源敏感性中的 `f_H=0.40` 只保留为
`conservative unknown-future-geometry planning envelope`。它不授权不规则
几何 PDE，也不能证明 classifier 或 local-p 对未知结构可迁移。

