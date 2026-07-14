# REVIEW REPORT V1：Task031 compact physical-slab 内存优先结构优化

## 0. 审查身份

```text
review = Task031 review_report_v1
branch = codex/20260714-task31-compact-pc-memory-optimization
base = Task030 merged master 545165b3d29396dcc3a8d5b029089175eafa3c4a
clean implementation commit = 45a0fc6e19535cb8f14fbfb186f099019612fec2
review_status = changes_required_before_selective_merge
numerical_result = pass
memory_result = strong_memory_success
performance_result = negative / slow_but_memory_efficient
ordinary_default_change = forbidden
additional_h2_rerun = not_required
master_merge = blocked by documentation and branch-sync hardening only
```

Task031 的正式 h5/h3/h2 结果、三类真残差、80 个模态、official R/T/A、能量闭合和 clean-source provenance 可以接受。最终 h2 外部同时 worker RSS 为 `7.897674560546875 GiB`，达到任务书 `<=8.0 GiB` 的 strong memory Gate；但 solve time 为 `11982.581 s`，约为 Task030 的 `5.01x`，只能定位为显式 opt-in 的 memory-first profile，不能替代 ordinary 或 Task030 speed-oriented profile。

本轮不要求重新运行 h5/h3/h2。合并前需要完成：

1. 与当前 master 同步并保护项目级规划文档；
2. 建立完整的迭代求解器端口文档；
3. 收紧 matrix-free、内存对比和 profile 身份措辞；
4. 按本文档给出的边界选择性合并。

---

# 1. 关于“释放 assembled F 导致变慢”的准确解释

## 1.1 直接原因

变慢的直接原因不是执行 `blocks.release_f()` 或销毁 `F` 的动作本身。销毁矩阵只发生一次，时间成本不是主项。

Task030 外层 fine action 使用 PETSc assembled sparse matrix：

```text
x -> F.mult(x)
```

Task031 为了让 solve 阶段不再常驻 assembled `F`，改为 public DOLFINx/DOLFINx-MPC form action：

```text
active vector
-> MPC Function
-> slave backsubstitution
-> ufl.action(a, u)
-> dolfinx_mpc.assemble_vector(...)
-> restore MPC slave unit rows
```

这个路径每次外层 operator apply 都需要执行 Function 写入、ghost/MPC 处理、有限元 form action、vector assembly 和通信。它避免了完整 `F` 的存储，但比已组装 CSR/AIJ 的 `MatMult` 显著更贵。

因此正确表述是：

```text
释放 assembled F = 内存收益的必要生命周期动作
public MPC form action = 主要求解时间成本
```

不能写成“destroy F 本身使求解变慢”。

## 1.2 数据支持

Task030 h2：

```text
iterations = 1873
solve = 2393.689 s
约 1.278 s / outer iteration
```

Task031 h2：

```text
iterations = 1977
solve = 11982.581 s
约 6.061 s / outer iteration
```

迭代数只增加约 `5.55%`，而每步平均成本增加约 `4.74x`，总 solve time 增加约 `5.01x`。所以主要瓶颈是 matrix-free form action 的每次 apply 成本，而不是迭代数。

h5 200-step A/B 也支持这一判断：assembled action 为 `18.478 s`，matrix-free form action 为 `58.837 s`，约 `3.18x`。

## 1.3 “matrix-free”术语边界

当前实现可以称为：

```text
assembled-F-free public MPC form-action path
```

或者：

```text
public form-action matrix-free fine operator
```

但文档必须说明它不是已经完成缓存优化的低层 element-kernel matrix-free 实现。它仍在每次 apply 中调用 `assemble_vector(ufl.action(...))`，因此性能与未来可缓存/批量的 element action 不同。

---

# 2. 接受的正式结果

## 2.1 h5/h3/h2

| mesh | FE DoF | iterations | full true residual | simultaneous worker peak | solve time |
|---|---:|---:|---:|---:|---:|
| h5 | 44,698 | 1,157 | `9.959903e-7` | 1.619598 GiB | 350.851 s |
| h3 | 198,438 | 1,994 | `9.973853e-7` | 3.474346 GiB | 2311.581 s |
| h2 | 615,108 | 1,977 | `9.998454e-7` | 7.897675 GiB | 11982.581 s |

三套正式运行均满足：

```text
KSP reason > 0
reported residual <= 1e-6
condensed true residual <= 1e-6
full augmented true residual <= 1e-6
same 80 modal unknowns
no swap
clean-source provenance
```

## 2.2 物理输出

h2：

```text
R = 0.0013429341864810204
T = 0.5992132355694105
A = 0.3994438359264334
energy closure = 5.68232483288966e-9
max R/T/A delta vs direct = 6.12516271036867e-9
```

结果与 direct reference 一致，没有因 matrix-free action、overlap 减少或 compact lifecycle 改变物理定义。

## 2.3 matrix-free action correctness

```text
h5 action error = 9.718e-16
h3 action error = 9.460e-16
h2 action error = 9.248e-16
```

MPC slave unit rows 已修复并有测试覆盖。`require_f/release_f`、重复释放和 no-double-destroy lifecycle 有对应测试，solve ledger 证明正式 Task031 profile 在外层 solve 中不保留 assembled `F`。

---

# 3. 内存结果的接受边界

## 3.1 接受绝对峰值

Task031 h2 的权威值是外部采样器在同一时刻汇总四个 live worker RSS：

```text
7.897674560546875 GiB
```

同时记录：

```text
cgroup current peak = 7.424026 GiB
legacy internal peak = 8.176441 GiB
swap in/out = 0
```

因此“约 8 GiB 可完成 frozen h2 target”可以接受。

## 3.2 相对降幅需保守表述

Task030 的 `9.374729 GiB` 与 Task031 external simultaneous worker peak 并非完全同一采样实现。Task031 报告已经承认这一点。

合并后的项目文档不应只写：

```text
Task031 精确降低 15.756%
```

建议写成：

```text
Task031 h2 external simultaneous peak = 7.898 GiB；
相对 Task030 历史口径的观察降幅约 15.8%；
使用 Task031 legacy internal peak 对照时约下降 12.8%；
因此保守结论为 h2 从约 9.4 GiB 压缩到约 8.0–8.2 GiB。
```

绝对 Task031 peak 是主要结论，百分比是辅助对照。

## 3.3 残差余量

h2 full residual `9.998454e-7` 非常接近 `1e-6` Gate，但 reported/condensed/full 三者一致，KSP reason、R/T/A 和能量闭合均通过，所以本次接受。

必须保留限定：该结果仅资格化 frozen target、MPI4、当前 partition、当前 RHS 和当前 PETSc/DOLFINx image。不能推导其他角度、偏振、材料、网格或几何必然收敛。

---

# 4. 各候选的审查结论

## 4.1 接受

### public MPC form action

接受为通用研究/工程基础设施。它正确消除了 solve 中 assembled `F` 常驻，并可在未来局部 3D block 和 hybrid 方法中复用。

### condensed operator external fine action 与生命周期

接受：

```text
external fine action
require_f()
release_f()
no-double-destroy
compact lifecycle
```

### overlap 0.125

接受为 Task031 profile 的显式参数。16 slabs 下 factor nnz 从 7,046,752 降到 5,666,368，h2 从 95,617,608 降到 80,743,816。其收敛较弱，不得修改 ordinary default。

### external simultaneous memory sampler

接受并推荐作为后续 memory authority。必须继续同时输出 worker RSS、process tree、cgroup、swap 和 stage，不得恢复“各 rank 不同时刻历史峰值直接求和”为唯一结论。

### PC certification

接受。非 FGMRES outer KSP 必须先通过固定线性和确定性 Gate，fail closed 是正确行为。

### compact lifecycle

接受。它对批量运行和 RTA 前释放有效；但 current RSS 下降不能单独包装成 solve-peak 下降。

## 4.2 保留接口但当前不可使用

### ordinary GMRES outer port

CLI 接口存在：

```text
--ksp-type gmres
```

但是当前 adaptive local GMRES PC 的线性误差为 `2.374308e-2`，不满足普通 GMRES 的固定线性 PC 条件。runner 会执行 certification 并 fail closed。

因此当前状态必须标为：

```text
port_implemented_but_incompatible_with_current_adaptive_pc
```

不能标为 supported solver。

### TFQMR 与 BCGS outer ports

CLI 接口存在：

```text
--ksp-type tfqmr
--ksp-type bcgs
```

runner 对非 FGMRES 路线使用 left PC，并要求 PC certification。当前 adaptive PC 会在线性 Gate 处失败；它们也没有 target-qualified full solve。

状态应为：

```text
interface_exposed_not_target_qualified
```

不能因为 argparse 中存在 choices 就称为可用生产求解器。

### Richardson local smoother port

接口存在：

```text
--smoother-ksp-type richardson
```

固定 Richardson PC 线性误差约 `3.6e-15`，但 h5 200 步 residual 为 `0.7703`，数值上失败。

状态：

```text
linear_research_port_numeric_negative
```

## 4.3 明确拒绝提升

- FGMRES restart50：内存仅约 -1.9%，更慢且残差更差；
- 20 slabs + overlap0.125：factor、残差、RSS 和时间均不如 16 slabs；
- selective boundary Jacobi：残差恶化到约 `0.0118`，无 RSS 收益；
- factor dedup：16/16 fingerprints 全部唯一，不存在 exact duplicate；
- approximate factor sharing：任务明确禁止；
- fixed Richardson + ordinary GMRES：线性但失去有效平滑；
- Task031 profile 作为 ordinary default；
- 任意参数、mesh-independent 或数学保证收敛的宣传。

---

# 5. P0：必须建立迭代求解器端口文档

现有 `solver_guide.md` 已包含部分结果，但仍缺少统一、面向使用者的“端口—合法性—资格化”视图。

Codex 必须创建或补充一份明确文档，推荐：

```text
docs/iterative_solver_ports.md
```

并从以下文件链接：

```text
docs/README.md
docs/solver_guide.md
docs/capability_matrix.md
notes/quick_start/40_3d_workstation_iterative.md
```

## 5.1 文档必须列出的入口

### canonical workstation iterative

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  --config benchmarks/configs/workstation_p2.json \
  --h-nm <5|3|2> \
  --record <record.json>
```

身份：

```text
Task27 canonical workstation profile
FGMRES100
assembled F retained
speed-oriented relative to Task31
```

### Task30 compact profile

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

身份：

```text
experimental opt-in
约 9.4 GiB h2 historical result
速度明显优于 Task31
```

### Task31 memory-first profile

推荐通过 wrapper：

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

h2 必须继续受 `--unlock-h2`、预测 Gate、9.5 GiB warning 和 11 GiB termination 保护。

身份：

```text
experimental memory-first opt-in
约 7.9 GiB h2
约 5.01x Task030 solve time
```

## 5.2 outer KSP port matrix

文档至少必须包含：

| CLI | 接口状态 | 当前 adaptive PC 合法性 | target qualification |
|---|---|---|---|
| `--ksp-type fgmres` | implemented | legal for variable/nonlinear PC | Task27/30/31 verified |
| `--ksp-type gmres` | implemented | illegal unless certification passes；当前 adaptive PC fails | not qualified |
| `--ksp-type tfqmr` | implemented | certification required；当前 adaptive PC fails | not qualified |
| `--ksp-type bcgs` | implemented | certification required；当前 adaptive PC fails | not qualified |

必须明确：

```text
argparse port exists != solver is currently usable
```

## 5.3 local smoother port matrix

| CLI | 状态 | 证据 |
|---|---|---|
| `--smoother-ksp-type gmres` | current verified adaptive smoother | 与 FGMRES outer 配对 |
| `--smoother-ksp-type richardson` | research-only negative | 线性通过但 residual 0.7703 |
| `--selective-diagonal-boundary-slabs` | research-only negative | boundary Jacobi 无内存收益且残差恶化 |

## 5.4 infrastructure flags

文档必须区分以下参数不是独立 Krylov 求解器：

```text
--matrix-free-fine
--compact-lifecycle
--certify-pc
--subdomain-local-shift
--factor-only-storage
--post-smooth
```

它们是 operator/PC/lifecycle 组件开关，需要与一个合法 outer KSP 组合。

## 5.5 用户选择规则

文档必须给出：

```text
reference / small problem -> direct MUMPS
normal qualified iterative -> Task27 canonical
memory约9.4 GiB且速度优先 -> Task30 compact experimental
memory约8 GiB硬限制且可接受数小时 -> Task31 memory-first experimental
角度/波长/材料/几何/MPI/element变化 -> 先重新 qualification
```

同时说明目前这些迭代入口仍主要是 benchmark/experimental CLI，不是已经冻结的通用 service API。未来 Task032–Task034 应在公共 solver abstraction 中复用底层组件，而不是复制 benchmark runner。

---

# 6. P0：分支同步与项目规划文档保护

Task031 分支从 `545165b3...` 创建。当前 master 已新增项目级规划和第一阶段冻结范围，包括：

```text
docs/project_service_requirements_and_forward_model_roadmap.md
docs/project_service_requirements_phase1_scope.md
```

Task031 分支当前相对 master 已 diverged，不能整体覆盖式合并。

Codex 在 response_v1 前必须：

1. 获取当前 master；
2. rebase 或 merge master 到 Task031 branch；
3. 解决 `docs/README.md`、`development_progress.md`、capability/solver 文档冲突；
4. 保留当前统一范围：`13.5 nm + fixed Si + 1–10° + S/P`；
5. 重新运行 documentation contracts、benchmark checker、JSON/CSV parse、diff check；
6. 不因同步文档而重跑 h5/h3/h2；
7. 若同步过程中修改任何核心 solver 代码，则需要重新评估是否触发小规模 action/测试，而不是默认沿用旧 provenance。

---

# 7. 选择性合并建议

## 7.1 建议合并

### 通用 solver infrastructure

- `src/solvers/mpc_form_action.py`；
- `condensed_dtn.py` 的 external fine action、`require_f/release_f` 和 safe lifecycle；
- public matrix/action equivalence helpers；
- no-double-destroy 和 unit-row correctness tests；
- PC linearity/determinism certification；
- object ledger 和 true-residual monitoring；
- external simultaneous RSS/cgroup/swap/stage sampler；
- clean-source attestation 和 watchdog；
- compact lifecycle 的安全释放逻辑。

### 显式 experimental profile

可保留 Task031 profile，但必须：

```text
explicit opt-in
ordinary default unchanged
frozen-target qualification only
performance warning visible
```

### Benchmark 和文档

- Case070 config/expected/records/checker；
- lightweight h5/h3/h2 records；
- Task031 outcomes；
- solver guide/capability/quick-start 更新；
- 新的 iterative solver ports 文档；
- Task031 contracts 和回归测试。

### physical-slab 扩展

可合并 generalized overlap、fixed/selective research knobs 和 diagnostics，但失败配置不得通过普通 API 宣称 supported，默认值必须保持不变。

## 7.2 不得合并或不得提升

- heavy artifacts、raw fields、matrix/cache、逐步日志；
- Task031 profile 替换 ordinary/canonical default；
- fixed Richardson 作为成功 solver；
- boundary Jacobi selective profile；
- restart50 profile；
- 20-slab profile；
- factor dedup/sharing claim；
- approximate factor sharing 代码；
- TFQMR/BCGS/ordinary GMRES 的 target-supported 声明；
- 通用参数鲁棒或 mesh-independent 声明；
- 把 Task31 的 performance-negative 路线作为高吞吐反演默认。

---

# 8. 测试与 provenance 审查

接受：

```text
full unit = 172 passed, 10 skipped
MPI1/2/4 targeted = 19 passed per rank
benchmark checker = 258/258
JSON/CSV parse = pass
diff check = pass
formal runs = clean SHA 45a0fc6e...
```

clean implementation commit 之后的两次提交主要是 Case070、records、checker 和文档收口，没有改变正式 run 使用的核心 solver implementation。现有 provenance 可以保留。

Codex response_v1 完成 master 同步和端口文档后，只需重跑轻量测试与 contracts，不要求重跑正式 h2。

---

# 9. 最终状态与 response 要求

## 当前分类

```text
Task031 numerical correctness = pass
Task031 absolute memory result = pass
Task031 strong memory Gate = pass
Task031 performance = negative
Task031 ordinary default = no
Task031 selective merge = recommended after hardening
Task031 master merge now = blocked
```

## Codex 必须创建

```text
docs/task031_compact_physical_slab_memory_optimization/response_v1.md
```

response_v1 至少回答：

1. 如何将 Task031 分支同步到当前 master，并保护项目级规划文档；
2. 新增/更新了哪些迭代求解器端口文档；
3. outer KSP、local smoother、profile 和 infrastructure flags 的状态表；
4. 哪些接口只是存在、哪些通过当前 target qualification、哪些被 certification 阻塞；
5. matrix-free 术语和性能代价如何修正；
6. Task031/Task030 内存百分比口径如何限定；
7. 哪些文件建议选择性合并，哪些明确不合并；
8. 最终轻量测试、benchmark checker、文档合同和 clean-tree 状态。

完成这些加固后，Task031 可以进入最终审查，不需要追加 h2 计算。
