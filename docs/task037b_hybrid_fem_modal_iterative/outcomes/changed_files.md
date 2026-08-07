# Task037b H1 changed files and provenance

## 代码提交链

| SHA | subject | 范围 |
|---|---|---|
| 26e48e2767d200b6ec58b39d117c354afbdba30c | docs(task037b): adopt fenced-math documentation standard | H0 文档公式治理与最小合同 |
| c1173a7d8de81b8bc80e0fca5e3eb28a912dc1d3 | test(task037b): freeze inherited Hybrid iterative baseline | H0 继承测试基线 |
| 3f72ef3eb4f3002246802af30ef7bca6b0080888 | feat(task037b): qualify direct Hybrid H1 authority | H1 explicit opt-in telemetry、pinned reference opening 与 launch wiring |

H1-A 的六个实现/测试文件已包含在第三个提交中。H1 formal 使用的 clean source SHA 是 3f72ef3eb4f3002246802af30ef7bca6b0080888；本 docs-only 结项不改变该 SHA，也不修改 tracked code。

## H1-A 六文件角色

下列六个文件属于 H1-A commit；本 docs-only 结项没有再次修改它们。

| 文件 | 角色 |
|---|---|
| benchmarks/run_task032_phase6_augmented.py | direct Hybrid augmented 求解入口、H1 rows/hash/RTA/recovery telemetry |
| benchmarks/run_task033_memory_watchdog.py | H1 scoped launch、worker wiring、资源 watchdog 与 summary forwarding |
| benchmarks/task035c_p6_h10_gates.py | pinned historical Full3D reference gate |
| src/test/test_181_task035c_p6_h10_runner_gates.py | H1 parser、worker、summary 与 pinned authority 合同 |
| src/test/test_53_task033_high_order_hybrid_components.py | owned-local PETSc Vec 与 modal hash 合同 |
| src/test/test_79_task034_native_full3d_reference.py | 外部绝对 reference/archive path 合同 |

## 边界

| 项目 | 结论 |
|---|---|
| ordinary defaults | unchanged |
| H1 flag | explicit opt-in，仅 task037b-h1-gate |
| master | 未合并 |
| H2-H10 | 未开始 |
| ignored raw artifacts | 不提交 |
| tracked docs | 只保存 hash-bound evidence 引用 |

## 本轮文档文件

本轮只新增以下五份 outcomes 与一份 response_v0；不修改 inherited_baseline_audit.md，不创建 H2-H10 空壳记录，也不修改 solver、runner 或 JSON authority。
