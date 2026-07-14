# REVIEW REPORT V2：Task031 最终验收与合并结论

## 0. 最终状态

```text
review = Task031 review_report_v2
branch = codex/20260714-task31-compact-pc-memory-optimization
review_status = PASS
numerical_result = PASS
memory_result = strong_memory_success
performance_result = slow_but_memory_efficient
ordinary_default_changed = false
formal_h5_h3_h2_rerun = not_required
merge_to_master = APPROVED
Task032_after_merge = APPROVED
```

Task031 Review V1 的阻塞项已经关闭。正式 h5/h3/h2 数值证据继续绑定 clean implementation SHA：

```text
45a0fc6e19535cb8f14fbfb186f099019612fec2
```

本轮 master 同步、文档加固和 wrapper CLI 一致性修正没有修改正式 Task031 profile 的核心 solver 数值路径，因此不要求重新运行 h5/h3/h2。

---

# 1. Review V1 关闭情况

## 1.1 master 同步与项目规划保护：关闭

Task031 分支已经合并当前 master，并保留：

- `docs/project_service_requirements_and_forward_model_roadmap.md`；
- `docs/project_service_requirements_phase1_scope.md`；
- Task031 结果、Case070 和审阅记录；
- `docs/README.md` 中的项目规划与迭代端口入口。

当前分支相对 master 为纯 ahead，不再 behind；项目规划范围与 Task031 已验证单点范围已明确区分。

## 1.2 迭代求解器端口文档：关闭

新增：

```text
docs/iterative_solver_ports.md
```

该文档清楚区分：

```text
argparse interface exists
!= algorithm is legal with current PC
!= frozen target is qualified
```

并记录：

- Task27 canonical workstation profile；
- Task30 compact experimental profile；
- Task31 assembled-F-free memory-first profile；
- FGMRES / GMRES / TFQMR / BCGS outer ports；
- adaptive GMRES / fixed Richardson local smoother ports；
- profile 与单个 infrastructure flag 的区别；
- 参数域外重新 qualification 流程；
- 内存与速度选择规则。

## 1.3 matrix-free 术语和性能因果：关闭

项目文档已统一使用：

```text
assembled-F-free public MPC form-action path
```

并明确：

```text
release_f() = 一次性的内存生命周期动作
public MPC form action = 每次 outer apply 的主要时间成本
```

不再错误表述为“销毁 assembled F 本身导致求解变慢”。

## 1.4 内存口径：关闭

最终主结论保持为：

```text
h2 external simultaneous worker peak = 7.897675 GiB
h2 cgroup current peak = 7.424026 GiB
h2 legacy internal peak = 8.176441 GiB
swap in/out = 0
```

相对 Task030 历史 9.374729 GiB 的约 15.8% 只作为辅助观察；保守工程表述为约 9.4 GiB 压缩至约 8.0–8.2 GiB。

## 1.5 wrapper certification 默认：关闭

Task31 sampler wrapper 对 FGMRES 默认不再错误强制 fixed-PC certification。底层 worker 仍对所有非 FGMRES outer KSP 自动执行线性/确定性认证并 fail closed。

因此：

```text
FGMRES + adaptive PC = legal
GMRES/TFQMR/BCGS + current adaptive PC = blocked
```

---

# 2. 接受的正式结果

| mesh | FE DoF | iterations | full true residual | simultaneous worker peak | solve time |
|---|---:|---:|---:|---:|---:|
| h5 | 44,698 | 1,157 | `9.959903e-7` | 1.619598 GiB | 350.851 s |
| h3 | 198,438 | 1,994 | `9.973853e-7` | 3.474346 GiB | 2311.581 s |
| h2 | 615,108 | 1,977 | `9.998454e-7` | 7.897675 GiB | 11982.581 s |

h2 official output：

```text
R = 0.0013429341864810204
T = 0.5992132355694105
A = 0.3994438359264334
energy closure = 5.68232483288966e-9
max R/T/A delta vs direct = 6.12516271036867e-9
```

三类残差、80 modal unknowns、official R/T/A、能量闭合、clean-source provenance 和无 swap 均通过。

Task031 的最终分类保持：

```text
strong_memory_success_slow_but_memory_efficient
```

该 profile 是内存硬约束下的显式选择，不是高吞吐默认配置。

---

# 3. 合并批准范围

以下内容批准进入 master：

## 3.1 通用基础设施

- public MPC form action 及 action equivalence；
- condensed external fine action；
- `require_f()` / `release_f()`；
- safe/no-double-destroy lifecycle；
- PC linearity/determinism certification；
- true-residual monitoring；
- object ledger；
- external simultaneous RSS/cgroup/swap/stage sampler；
- clean-source attestation 和 memory watchdog；
- compact lifecycle。

## 3.2 显式 Task31 profile

批准保留：

```text
Task30 compact architecture
+ 16 slabs
+ overlap 0.125
+ matrix-free-fine
+ compact-lifecycle
+ right FGMRES90
```

身份必须保持：

```text
experimental memory-first opt-in
frozen-target qualified evidence only
ordinary default unchanged
```

## 3.3 证据、测试与文档

- Case070；
- lightweight h5/h3/h2 records；
- benchmark checker；
- Task031 outcomes；
- `docs/iterative_solver_ports.md`；
- solver guide / capability matrix / quick start / theory / walkthrough；
- project service requirements and phase-1 scope；
- Task031 contract tests。

---

# 4. 不得提升的内容

以下内容可以保留为明确 research/negative evidence，但不得成为普通推荐 profile：

- FGMRES restart50；
- 20 slabs + overlap0.125；
- selective boundary Jacobi；
- fixed Richardson smoother；
- factor dedup/sharing；
- approximate factor sharing；
- GMRES/TFQMR/BCGS target-supported 声明；
- Task31 替换 ordinary/canonical default；
- 任意参数鲁棒、mesh-independent 或数学无条件收敛宣传。

heavy artifacts、raw fields、matrices/cache 和完整 timeline 继续留在 ignored artifact 目录，不进入 Git。

---

# 5. 最终轻量验证

接受 `response_v1.md` 中的验证记录：

```text
documentation + Task031 focused contracts = 21 passed
full unit = 175 passed, 10 skipped
benchmark checker = 258/258 passed (--no-write)
Task31 JSON/CSV parse = 14 JSON + 4 CSV passed
wrapper --help = pass
Ruff = pass
compileall = pass
diff check = pass
tracked tree = pass
```

正式 h5/h3/h2 不需要重跑。

---

# 6. 合并方式与下一步

Task031 分支已经包含当前 master，且相对 master 为 pure ahead。当前审阅范围内的 tracked diff 已完成身份隔离、文档说明和测试加固，因此允许将该分支合并到 master。

建议使用显式 merge commit，保留 Task031 的实施、审阅和回应历史。合并后：

1. 在 master 上运行轻量 documentation/contracts/checker；
2. 记录最终 merge SHA；
3. 从干净 master 创建 Task032 执行分支；
4. Task032 严格读取项目服务需求和第一阶段冻结范围；
5. Task032 仍固定 13.5 nm、当前 Si、规则结构，先建立 hybrid FEM–Modal direct baseline。

```text
Task031 disposition = ACCEPTED
merge recommendation = APPROVED
Task032 start = APPROVED AFTER CLEAN MASTER MERGE
```
