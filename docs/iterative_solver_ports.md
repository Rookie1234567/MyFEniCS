# 迭代求解器端口、合法性与资格化状态

本文统一说明当前 3D Stage4 迭代入口的命令、算法合法性、目标资格化和资源边界。它回答的是“端口是否存在、当前组合是否可用、在哪个目标上验证过”，不是仅列出 argparse 选项。

> `argparse port exists != solver is currently usable`。接口存在不等于算法与当前预条件器相容，也不等于通过 frozen target 的 full true residual、official R/T/A 和内存 Gate。

## 1. 三个正式入口及身份

### 1.1 Task27 canonical workstation iterative

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  --config benchmarks/configs/workstation_p2.json \
  --h-nm <5|3|2> \
  --record <record.json>
```

身份与边界：

```text
profile = Task27 canonical workstation profile
outer = right FGMRES100
fine action = assembled F retained + exact condensed shell action
status = frozen-target qualified
resource preference = normal qualified iterative / speed-oriented relative to Task31
```

JSON 是 canonical 参数源。任何 CLI override 都会进入 qualification deviations；偏离后只能作为新候选，不能继承 Task27 资格。

### 1.2 Task30 compact physical-slab profile

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  --h-nm <5|3|2> \
  --post-smooth \
  --subdomain-local-shift \
  --factor-only-storage \
  --ilu-levels 0 \
  --restart 90 \
  --record <record.json>
```

身份与边界：

```text
profile = compact_physical_slab_low_memory_experimental_opt_in
outer = right FGMRES90
status = experimental opt-in
h2 memory = historical reviewed result about 9.4 GiB
resource preference = speed clearly better than Task31
ordinary default changed = false
```

Task30 的 clean h5/h3 和历史审阅 h2 都通过对应数值 Gate，但 h2 provenance 与 Task31 不同，且迭代目标/参数域外鲁棒性没有资格化，因此不是 production default。

### 1.3 Task31 assembled-F-free memory-first profile

推荐通过外部同时内存采样 wrapper：

```bash
mpiexec -n 4 python -m benchmarks.run_task031_memory_forensics \
  --h-nm <5|3|2> \
  --num-slabs 16 \
  --overlap-layers 0.125 \
  --ksp-type fgmres \
  --smoother-ksp-type gmres \
  --restart 90 \
  --matrix-free-fine \
  --compact-lifecycle \
  --case-label <label> \
  --run-dir <dir> \
  --verified-clean-sha <full-sha>
```

身份与边界：

```text
profile = task031_matrix_free_compact_physical_slab_opt_in
precise operator term = assembled-F-free public MPC form-action path
outer = right FGMRES90
status = experimental memory-first opt-in
h2 external simultaneous worker peak = 7.897675 GiB
h2 legacy internal peak = 8.176441 GiB
h2 solve cost = about 5.01x Task30
ordinary default changed = false
```

正式 h5/h3/h2 运行还显式使用 `--max-it 5000`；h2 默认锁定，只有文档化的 h3 数值、内存、预测、clean-source 与无-swap Gate 通过后才能增加 `--unlock-h2`。9.5 GiB warning 和 11 GiB controlled termination 不得移除。

FGMRES 允许当前 adaptive/variable PC，因此推荐命令不要求固定线性认证。显式 `--certify-pc` 可用于研究固定 PC；任何非 FGMRES outer port 无论是否传该 flag 都必须自动认证并 fail closed。

## 2. Outer KSP 端口矩阵

| CLI | 接口状态 | 当前 adaptive PC 合法性 | frozen target qualification |
|---|---|---|---|
| `--ksp-type fgmres` | implemented | 合法；允许 variable/nonlinear PC | Task27/30/31 verified |
| `--ksp-type gmres` | implemented | 仅固定线性、确定性认证通过才合法；当前误差 `2.374308e-2`，被阻塞 | not qualified |
| `--ksp-type tfqmr` | interface exposed | left PC + certification required；当前 adaptive PC 被阻塞 | not qualified |
| `--ksp-type bcgs` | interface exposed | left PC + certification required；当前 adaptive PC 被阻塞 | not qualified |

当前状态的精确标签：

```text
gmres = port_implemented_but_incompatible_with_current_adaptive_pc
tfqmr = interface_exposed_not_target_qualified
bcgs = interface_exposed_not_target_qualified
```

普通 GMRES 不能仅因 residual monitor 看似下降就绕过认证；TFQMR/BCGS 也不能因 argparse choices 中存在而称为 supported solver。

## 3. Local smoother 端口矩阵

| CLI / 开关 | 状态 | 证据与限制 |
|---|---|---|
| `--smoother-ksp-type gmres` | current verified adaptive smoother | 与 FGMRES outer 配对；其可变性正是普通 GMRES 被阻塞的原因 |
| `--smoother-ksp-type richardson` | research-only negative | 固定 PC 线性误差约 `3.6e-15`，但 h5 200 步 residual `0.7703` |
| `--selective-diagonal-boundary-slabs` | research-only negative | boundary Jacobi residual 约 `0.0118`，且无外部 RSS 收益 |

Richardson 只证明“可以构造线性 PC”，没有证明该 PC 有足够平滑能力。它不得被提升为成功 solver。

```text
richardson = linear_research_port_numeric_negative
selective boundary Jacobi = research_only_numeric_negative
```

## 4. Profile 与组件开关不是一回事

| 参数 | 类型 | 作用 | 是否可独立称为求解器 |
|---|---|---|---|
| `--matrix-free-fine` | operator/storage | 用 public MPC form action 替代 solve 阶段常驻 assembled `F` | 否 |
| `--compact-lifecycle` | lifecycle | 缩短 KSP/PC/factor/work vectors 与 RTA 的对象重叠 | 否 |
| `--certify-pc` | legality diagnostic | 检查固定线性和确定性；非 FGMRES 自动强制执行 | 否 |
| `--subdomain-local-shift` | PC storage | 避免保留完整 shifted-F | 否 |
| `--factor-only-storage` | PC storage/lifecycle | local setup 后只保留可用因子 | 否 |
| `--post-smooth` | PC action | 启用对称 pre/post smoothing | 否 |

这些 flag 必须与合法 outer KSP、完整 profile 和 true-residual Gate 组合。单个 flag 的 action test 或 current RSS 下降不构成求解器资格。

## 5. “matrix-free”术语和时间代价

Task31 的精确实现是：

```text
assembled-F-free public MPC form-action path
```

也可简称“public form-action matrix-free fine operator”，但必须说明它不是已经完成缓存优化的低层 element-kernel matrix-free 实现。每次 outer operator apply 都包含 active vector 写入 MPC Function、slave backsubstitution、`ufl.action(a, u)`、`dolfinx_mpc.assemble_vector(...)`、slave unit-row 恢复和 MPI/ghost 处理。

`blocks.release_f()` 只是一次性的必要生命周期动作，其销毁时间不是主要性能成本。主要成本来自上述 public form action 在每次 outer apply 中重复装配和通信：

| 对照 | Task30 / assembled | Task31 / form action | 解释 |
|---|---:|---:|---|
| h5 200-step screen | 18.478 s | 58.837 s | 每步路径约 3.18x |
| h2 full solve | 1873 steps / 2393.689 s | 1977 steps / 11982.581 s | 迭代数仅 +5.55%，每步约 4.74x，总时间约 5.01x |

因此应写成“释放 assembled `F` 是内存收益所需的生命周期动作；public MPC form action 是主要时间成本”，不得写成“销毁 `F` 本身导致变慢”。

## 6. 内存结果的可比口径

Task31 h2 的主要、可接受结论是绝对外部峰值：

```text
external simultaneous live-worker RSS = 7.897675 GiB
cgroup current peak = 7.424026 GiB
legacy internal peak = 8.176441 GiB
swap in/out = 0
```

Task030 历史值 9.374729 GiB 与 Task31 external sampler 并非完全相同实现。因此：

- 相对 Task030 历史口径的观察降幅约 15.8%，只能作为辅助对照；
- 使用 Task31 legacy internal peak 对照时，观察降幅约 12.8%；
- 保守工程结论是 frozen h2 从约 9.4 GiB 压缩到约 8.0–8.2 GiB；
- `7.897675 GiB` 是 Task31 external simultaneous authority，不能与各 rank 不同时刻 historical peaks 的和混为一谈。

## 7. 用户选择规则

```text
reference / small problem
  -> ordinary direct MUMPS

normal frozen-target qualified iterative
  -> Task27 canonical workstation profile

memory约9.4 GiB且速度优先
  -> Task30 compact experimental opt-in

memory约8 GiB硬限制且可接受数小时
  -> Task31 assembled-F-free memory-first experimental opt-in

角度/波长/材料/几何/MPI/element/RHS改变
  -> 先重新 qualification，不继承既有“收敛保证”
```

当前 iterative qualification 是单点 frozen target：13.5 nm、固定 Si、`theta=80°`（按表面掠入射角记法对应 10°）、`phi=0°`、S polarization、p2 Nédélec、MPI4、当前 partition/RHS/image。项目第一阶段规划覆盖 `13.5 nm + fixed Si + 1–10° grazing + S/P`，但除当前单点外仍需后续 Task032–Task034 逐点资格化，规划范围不等于已验证范围。

## 8. 公共 API 与选择性合并边界

这些入口目前主要是 benchmark/experimental CLI，不是冻结的通用 service API。后续 Task032–Task034 应在公共 solver abstraction 中复用 `mpc_form_action`、condensed external action/lifecycle、PC certification、true-residual monitor 和 external memory sampler，不应复制整个 benchmark runner。

建议选择性合并：通用 action/lifecycle/certification/telemetry 基础设施、Task31 显式 profile、Case070 轻量证据、合同测试与文档。不得提升：fixed Richardson、boundary Jacobi、restart50、20-slab、factor sharing、TFQMR/BCGS/普通 GMRES target-supported 声明、ordinary default 替换、通用参数鲁棒或 mesh-independent 宣传。heavy artifacts、raw fields、matrix/cache 和逐步日志继续留在 ignored artifact 目录。

## 9. 关联证据

- canonical 使用教程：[`../notes/quick_start/40_3d_workstation_iterative.md`](../notes/quick_start/40_3d_workstation_iterative.md)
- 求解器选择：[`solver_guide.md`](solver_guide.md)
- 能力状态：[`capability_matrix.md`](capability_matrix.md)
- Task31 Case：[`../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md`](../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md)
- Task31 结果：[`task031_compact_physical_slab_memory_optimization/outcomes/summary.md`](task031_compact_physical_slab_memory_optimization/outcomes/summary.md)
- PC / Krylov 理论：[`../notes/theory/iterative_solver_and_preconditioner.md`](../notes/theory/iterative_solver_and_preconditioner.md)
