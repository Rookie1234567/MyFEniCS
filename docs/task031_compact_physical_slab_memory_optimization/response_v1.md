# RESPONSE V1：Task031 Review V1 加固回应

## 0. 回应状态

```text
review = Task031 review_report_v1
branch = codex/20260714-task31-compact-pc-memory-optimization
review_result_accepted = numerical pass + strong absolute memory success
formal_h5_h3_h2_rerun = not required / not performed
ordinary_default_changed = false
response_scope = master sync + port documentation + terminology/provenance hardening
final_status = ready for final review after lightweight checks
```

本轮没有改写 `task.md` 或 `review_report_v1.md`，也没有重跑正式 h5/h3/h2。正式证据继续绑定 clean implementation SHA `45a0fc6e19535cb8f14fbfb186f099019612fec2`。

## 1. 当前 master 同步与项目规划保护

先执行远程刷新并核对 Git 图。Task031 分支虽然已有提交 `62e6809` 复制两份规划文档，但共同基点仍为 `545165b`，没有真正包含当前 `origin/master` 的 4 个规划提交。

随后将 `origin/master` 的 `b7e0d14cab31e5bad0119f4541c76e278378419c` merge 到 Task031 分支，merge commit 为：

```text
4dccbd7 Merge remote-tracking branch 'origin/master' into Task31 branch
```

唯一冲突是 `docs/README.md`。解决方式不是选择一侧覆盖，而是同时保留：

- Task030 已合入、Task031 已完成且等待最终审查的真实状态；
- `project_service_requirements_and_forward_model_roadmap.md`；
- `project_service_requirements_phase1_scope.md`；
- 后续 Task032–Task035 的统一规划范围 `13.5 nm + fixed Si + 1–10° grazing + S/P`；
- ordinary default 不得静默改变、frozen-target qualification 不得扩张为通用保证的治理规则。

Task031 当前正式资格化仍只是 13.5 nm、固定 Si、theta=80°（按表面记法对应 10° grazing）、S polarization、MPI4、当前 partition/RHS/image 的单点。项目规划范围不等于已验证范围。

master 同步没有修改核心 solver 代码，因此不触发正式 h5/h3/h2 重跑。后续仅对 benchmark wrapper 的认证默认做了 CLI 一致性修正，见第 4 节；正式 profile 的数值路径和既有 run provenance 均不改变。

## 2. 新增和同步的迭代求解器文档

新增统一使用者文档：

```text
docs/iterative_solver_ports.md
```

并从以下文件建立链接和同步说明：

- `docs/README.md`；
- `docs/solver_guide.md`；
- `docs/capability_matrix.md`；
- `notes/quick_start/40_3d_workstation_iterative.md`；
- `docs/benchmark.md`；
- Case070 README；
- Task031 outcomes summary / matrix-free validation / merge recommendation；
- iterative theory 与 walkthrough 32/33/50；
- `docs/development_progress.md`。

端口文档给出 Task27 canonical、Task30 compact 和 Task31 memory-first 的可复制命令、身份、资源选择、h2 lock/watchdog、参数域外重新资格化流程以及 benchmark CLI 与未来 service API 的边界。

## 3. Profile、outer KSP 和 local smoother 状态

### 3.1 Profile

| Profile | 状态 | frozen target 证据 | 资源定位 |
|---|---|---|---|
| Task27 canonical workstation | qualified canonical | h5/h3/h2 | normal iterative / 相对 Task31 速度优先 |
| Task30 compact physical-slab | experimental opt-in | clean h5/h3 + reviewed historical h2 | 约 9.4 GiB 历史结果、明显快于 Task31 |
| Task31 assembled-F-free memory-first | experimental opt-in | clean h5/h3/h2 | external 7.898 GiB、legacy internal 8.176 GiB、约 5.01x Task30 solve time |

### 3.2 Outer KSP

| CLI | 接口状态 | 当前 adaptive PC 合法性 | target qualification |
|---|---|---|---|
| `--ksp-type fgmres` | implemented | legal for variable/nonlinear PC | Task27/30/31 verified |
| `--ksp-type gmres` | implemented | certification required；当前 `2.374308e-2` fail | not qualified |
| `--ksp-type tfqmr` | interface exposed | certification required；当前 PC fail | not qualified |
| `--ksp-type bcgs` | interface exposed | certification required；当前 PC fail | not qualified |

精确状态为：

```text
gmres = port_implemented_but_incompatible_with_current_adaptive_pc
tfqmr/bcgs = interface_exposed_not_target_qualified
```

### 3.3 Local smoother

| CLI / flag | 状态 | 证据 |
|---|---|---|
| `--smoother-ksp-type gmres` | current verified adaptive smoother | 与 FGMRES outer 配对 |
| `--smoother-ksp-type richardson` | linear research port / numeric negative | 线性 `3.6e-15`，200-step residual 0.7703 |
| `--selective-diagonal-boundary-slabs` | research-only negative | residual 约 0.0118，且无外部 RSS 收益 |

## 4. Certification 和 wrapper CLI 一致性

报告给出的 Task31 推荐 FGMRES 命令没有 `--no-certify-pc`。原 wrapper 却默认 `certify_pc=True`，会对允许 variable PC 的正式 FGMRES 路线错误强制“固定线性”认证，并因已知 `2.374308e-2` 失败。

本轮把 `run_task031_memory_forensics.py` 的 wrapper 默认改为：

```text
certify_pc = false for FGMRES wrapper default
```

底层 worker 仍保持：

```python
if args.certify_pc or args.ksp_type != "fgmres":
    certify_fixed_linear_preconditioner(...)
```

因此任何 GMRES/TFQMR/BCGS 都会自动 certification 并 fail closed；FGMRES 可合法使用 adaptive PC，只有显式研究固定 PC 时才传 `--certify-pc`。这只修正 wrapper 默认与报告推荐命令的一致性，不改变正式 Task31 run 的数值路径：三份 lightweight record 保存的正式 worker command 都没有传 `--certify-pc`，等效地没有运行固定-PC Gate。

## 5. Infrastructure flags 身份

以下参数都不是独立 Krylov solver：

| flag | 身份 |
|---|---|
| `--matrix-free-fine` | fine operator / storage 组件 |
| `--compact-lifecycle` | 对象生命周期组件 |
| `--certify-pc` | 合法性诊断；非 FGMRES 自动强制 |
| `--subdomain-local-shift` | PC 存储组件 |
| `--factor-only-storage` | local factor 生命周期组件 |
| `--post-smooth` | PC action 组件 |

它们必须与合法 outer KSP 和完整 profile 组合。单个 flag 的 action test、payload estimate 或 current RSS 下降不能构成 solver qualification。

## 6. Matrix-free 术语与性能根因修正

Task031 当前实现统一命名为：

```text
assembled-F-free public MPC form-action path
```

“public form-action matrix-free fine operator”可作为简称，但文档已明确它不是已缓存优化的低层 element-kernel matrix-free。每次 outer apply 仍包含 MPC Function 写入、slave backsubstitution、`ufl.action(a, u)`、`dolfinx_mpc.assemble_vector(...)`、unit-row 恢复和通信。

正确因果关系是：

```text
release_f() = 一次性的必要内存生命周期动作
public MPC form action = 每次 apply 的主要时间成本
```

数据支持：Task030 h2 为 1873 步 / 2393.689 s，约 1.278 s/step；Task031 h2 为 1977 步 / 11982.581 s，约 6.061 s/step。迭代数只增加约 5.55%，每步成本增加约 4.74x，总 solve time 约 5.01x。h5 200-step 也为 18.478→58.837 s（3.18x）。因此文档不再把“destroy `F` 本身”写成变慢原因。

## 7. 内存百分比和绝对值口径

Task031 的权威主结论保持为：

```text
h2 external simultaneous live-worker peak = 7.897675 GiB
h2 cgroup current peak = 7.424026 GiB
h2 legacy internal peak = 8.176441 GiB
swap in/out = 0
```

Task030 历史 9.374729 GiB 与 Task031 external sampler 并非完全相同实现。所有项目级文档已改为：

- 绝对 external 7.898 GiB 是主要结论；
- 相对 Task030 历史值的约 15.8% 只作辅助观察；
- 以 Task31 legacy internal peak 对照约下降 12.8%；
- 保守工程结论为 frozen h2 从约 9.4 GiB 压缩到约 8.0–8.2 GiB；
- current RSS release 下降只证明 lifecycle 生效，不冒充 solve peak。

h2 full residual `9.998454e-7` 接近 Gate，但三残差、KSP reason、official R/T/A、能量闭合和 direct delta 都通过；资格化边界继续限定为当前 frozen target。

## 8. 选择性合并与明确不提升

建议选择性合并：

- `mpc_form_action.py` 和 public action equivalence helpers；
- condensed external fine action、`require_f/release_f`、safe lifecycle；
- PC certification、object ledger、true-residual monitor；
- external simultaneous RSS/cgroup/swap/stage sampler、clean-source/watchdog；
- compact lifecycle；
- generalized overlap/fixed/selective diagnostics，但失败配置只保留 research 身份；
- Task31 显式 opt-in profile、Case070、轻量 records、测试和文档。

明确不合并或不提升：

- heavy artifacts、raw fields、matrix/cache、逐步 timeline；
- Task31 替换 ordinary/canonical default；
- fixed Richardson、boundary Jacobi、restart50、20-slab profile；
- factor dedup/sharing 或 approximate factor sharing；
- GMRES/TFQMR/BCGS target-supported 声明；
- 通用参数鲁棒、mesh-independent 或数学无条件收敛宣传；
- 把 performance-negative Task31 路线作为高吞吐反演默认。

## 9. 最终轻量验证

```text
documentation + Task031 focused contracts = 21 passed
full unit in qualified DOLFINx image = 175 passed, 10 skipped
benchmark checker = 258/258 passed (--no-write)
Task31 JSON/CSV parse = 14 JSON + 4 CSV passed
wrapper --help = pass
Ruff / compileall = pass
diff check = pass
tracked tree after final commit = pass (only pre-existing user-local untracked directories remain)
formal h5/h3/h2 = accepted existing clean evidence; not rerun
```

完成上述轻量验证并回填本节后，本分支进入 Task031 final review；在用户明确许可前不合并 `master`。
