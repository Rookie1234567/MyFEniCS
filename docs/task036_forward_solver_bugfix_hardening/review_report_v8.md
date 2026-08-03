# Task036 Review Report V8：以受控失败结项，选择性保留 Hybrid 与前向求解器修复

## 0. 审阅身份

```text
review                         = Task036 Review Report V8 / final closeout and selective-integration authority
reviewed_task_branch           = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_head                  = ff2227cac8a19bd3a4c66279a413f6a34d730098
master_base                    = 007298261681014efbe6508ac91c6c3ae9a6a44a
branch_ahead_of_master         = 71 commits before this document
ordinary_default               = must remain unchanged
master_full_branch_merge       = forbidden
master_selective_integration   = authorized under this report
new_branch_before_merge        = forbidden
Task036_status                 = CLOSED_CONTROLLED_FAILURE_WITH_REUSABLE_POSITIVES
C1b_96RHS_teacher              = authorization revoked / not_run
compressed_direct_Hybrid       = not_demonstrated
exact_FE_trace_chain           = correctness oracle retained
strong_trace                   = research-only capability retained
iterative_solver               = deferred to Task037
```

用户决定停止 Task036 的继续扩展。此前 V7 对 C1b 的一次性授权自本报告起撤销；不得再运行
96-RHS teacher、POD、minimum-residual capacity、跨角度 gauge、actual compressed candidate
或任何新的 Task036 PDE。

本报告不把 Task036 简化为“全部失败”。它区分：

1. **任务主目标失败**：没有得到一个在小掠射角、P 偏振和完整衍射通道下既鲁棒、又显著低内存、
   且可作为 direct Hybrid 生产接口的低维端口；
2. **域分解和接口物理正结果**：strong trace 修复了不可见的切向电场 complement；完整 FE trace
   和 exact Schur chain 证明 Maxwell 域分解、牵引平衡、DtN、恢复和 direct 求解本身可以与
   Full3D 对齐；
3. **通用工程修复正结果**：DtN 投影、trace alias、MUMPS 遥测、对象生命周期、内存 authority、
   DoF/row 语义等修复对后续 Full3D 与 Task037 均有价值；
4. **低秩接口负结果**：M120/M240、strong-trace M120、discrete-Bloch `d_port<=360` 均未满足完整
   production contract；reachable-source/POD 没有运行到 live teacher，不再继续。

因此正式结论是：

```text
Hybrid domain decomposition correctness       = proven
low-rank direct Hybrid production capability  = not demonstrated
Task036 compressed-port research               = closed
Hybrid codebase                                = retained selectively, not deleted
```

---

## 1. 最终结论矩阵

| 项目 | 最终判定 | 后续处置 |
|---|---|---|
| Full3D 小掠射角 / P 物理 | PASS | 保留 reference、投影、DtN 和资源修复 |
| 原始 physical-QEP M120/M240 完整接口 | CONTROLLED NEGATIVE | 不再扩 M；保留 long-range modal core 与历史实现 |
| projection-only Hybrid | CONTROLLED NEGATIVE | 不作为 production；保留失败证据 |
| strong-trace Hybrid | PARTIAL POSITIVE / CONTROLLED NEGATIVE | 保留为 explicit research-only；E 连续通过，但完整通道未闭合 |
| exact FE trace-chain direct | PASS AS RESEARCH ORACLE | 保留最小可复用实现与回归；不得称 scalable solver |
| discrete-Bloch B1 `d<=360` | CONTROLLED NEGATIVE / CLOSED | 不合入容量 runner、mode-pool campaign 或 POD 研究代码 |
| C1 reachable-source POD | INCOMPLETE / CANCELLED | scaffold 与大 runner 不进入 master；C1b not_run |
| 0.7 nm / 2 TiB | NOT SOLVED | 交由 Task037 的 matrix-free iterative 主线重新规划 |
| Task036 整体 | CLOSED CONTROLLED FAILURE | 选择性整合后结束分支开发 |

Task036 的“失败”特指：

> 未能把完整 FE joint-Cauchy 接口压缩为远低于 full trace 的 direct 端口，同时保持完整通道、
> 小掠射角/P 鲁棒性和有意义的整作业内存优势。

不得将它写成“本征模传播公式错误”或“Hybrid 域分解不可行”。现有审计已经证明 M120 selected
space 内的长程传播 action 基本正确；失败发生在将其提升为完整接口空间。

---

## 2. `master` 集成总原则

当前 Task036 分支相对 `master` 累积 71 个提交和大量研究 runner。禁止：

```text
git merge codex/20260730-task36-forward-solver-bugfix-hardening
```

也禁止一次性 cherry-pick 大型阶段提交。Codex 必须从最新 `origin/master` 出发，按下面的
**函数/能力白名单**重建小型选择性提交。

绑定规则：

1. 不创建任何中间 Git 分支；直接在更新后的本地 `master` 上形成有意图的选择性提交；
2. 在所有测试通过前不得推送 `master`；
3. 若一个白名单修复无法与黑名单研究框架分离，优先提取最小 helper；仍无法分离时，记录
   omission，绝不通过整体复制大 runner 解决依赖；
4. ordinary defaults、现有 public presets 和生产 solver 选择不得改变；
5. strong trace、exact trace 和 one-cell oracle 必须标为 `research_only` 或 explicit opt-in；
6. Hybrid-P 不得因 exact oracle 通过而升级为 production-qualified；
7. 所有 heavy/ignored artifacts 留在 Task036 分支对应本地证据目录，不进入 `master`。

---

## 3. 第一组：必须整合的 Full3D / 通用前向求解器修复

这一组与 Task036 低秩路线成败无关，是后续 Task037 和所有高阶 Full3D 的基础。

### 3.1 B01：DtN 直接投影只使用切向场

必须整合：

- `src/solvers/dtn_port_3d.py`
  - `_mode_projection_from_solution` 的 tangential-only numerator/denominator；
  - top incident subtraction 的统一语义；
  - 独立 direct-projection audit 所需最小 helper；
- 对应 `src/test/test_14_stage4_dtn_modes.py` 的 synthetic oblique S/P、非零 `E_z`、lossy bottom、
  top incident subtraction 回归。

可整合现有 watchdog 的最小字段校验，但不得复制 Task036 robustness runner。

### 3.2 B07：y-invariant trace alias 的 pre-solve fail-closed

必须整合 ordinary-default-off 的 opt-in 防护：

- `src/common/config_3d.py` 中明确的 alias-preflight 配置字段；
- `src/geometry/mesh_builder_3d.py` 中 requested/actual axis-count identity；
- `src/solvers/dtn_port_3d.py` 中基于实际 MPC-reduced tangential surface functional 的 overlap；
- `src/solvers/hybrid_local_dtn.py` 的同一调用语义；
- Ny3 controlled rejection 与 Ny4 positive 的小型测试/contract。

不得把 y-invariant 假设设为普通通用 diffraction 默认。

### 3.3 B08：MUMPS factor NNZ int32 overflow 修复

必须整合：

- `src/solvers/common_3d_solve.py` 中 raw/corrected factor NNZ 双字段；
- 仅 `MUMPS && INFOG(9)<0` 时的 negative-million-entry correction；
- `src/adaptivity/high_order_resource_audit.py`、
  `src/adaptivity/high_order_same_error.py` 和
  `benchmarks/run_direct_memory_forensics.py` 的 corrected-count consumer；
- `src/test/test_195_task036_mumps_factor_nnz.py`。

不得覆盖 raw PETSc/MUMPS 遥测；不得把修复解释成 factor 本身变小。

### 3.4 B09：solver 生命周期与 field output 错峰

必须整合通用生命周期修复：

- `src/solvers/common_3d_utils.py`：幂等 destroy/heap-trim 语义；
- `src/solvers/common_3d_case_flow.py`：完成 residual/recovery 后、field output 前释放不再需要的
  solver objects；
- Hybrid direct solver 中对应的安全 release hook，前提是不引入 Task036 runner；
- use-after-destroy、double-destroy、`malloc_trim(0)` 语义测试。

这项修复对 Task037 的整作业内存 Gate 直接有价值。

### 3.5 B10：同步内存 authority 与 MPI identity

必须整合：

- simultaneous process-tree RSS/PSS/USS/swap 与 per-rank historical peak 的明确分离；
- `sum_rank_historical_peaks_mb_upper_bound` 不得再被命名为 total peak；
- MPI identity 使用 canonical physical/topological identity，不使用 partition-sensitive raw bytes；
- `benchmarks/watchdog_process_control.py` 中隔离进程组、TERM→KILL、确认无残留子进程的通用 helper；
- 对应 process-tree negative-path 和 memory-semantics tests。

`watchdog_process_control.py` 是 Task037 重型迭代作业的必需基础，应进入 `master`。

### 3.6 B11：DoF、carrier、trace rows 与 augmented rows 分字段

必须整合：

```text
num_active_exact_sequence_fe_dofs
num_storage_carrier_fe_dofs
num_independent_trace_rows
num_augmented_rows
dof_row_semantics
```

涉及最小文件：

- `src/solvers/dtn_port_3d.py`；
- `src/solvers/common_3d_case_flow.py`；
- `src/solvers/hcurl_assembly_time_condensation.py`；
- 现有 assembly-time/variable-p contract tests。

保持旧字段兼容，但资源报告必须以实际 rows 和明确语义为准。

---

## 4. 第二组：为“保留 Hybrid”必须整合的安全与物理修复

这组不把 Hybrid 升级为生产主线，而是确保已有 Hybrid 代码不丢失 Task036 得到的真实修复。

### 4.1 B02：高阶 reciprocal trace 的通用一致性部分

必须保留：

- lifted target space 的真实 degree/quadrature policy；
- raw relation、canonical representation 和 orientation audit；
- positive/negative trace 的坐标身份一致性；
- 不一致时 fail closed。

不得合入：

- `task036_scalar_stage4_reciprocal_basis` 专用研究 opt-in；
- 为特定 scalar case 构造的解析 reciprocal production 路径；
- Task036 partition campaign 和自动 repair。

即：整合**通用一致性修复和审计**，不整合特定 B1/robustness 研究策略。

### 4.2 B03：sampled traction proxy 与 exact variational conormal dual 分离

必须整合：

- `src/solvers/hybrid_fem_modal_augmented_direct.py` 中 exact FE conormal dual；
- `src/postprocessing/hybrid_field_reconstruction.py` 的正式/诊断字段分离；
- sampled quantity 统一命名为 `traction_density_l2_proxy`，标记 `diagnostic_only`；
- formal Gate 只读取 `traction_hcurl_dual.relative_dual`；
- top/bottom 任一 formal dual 缺失必须 fail closed，不能由 sampled proxy 替代。

这是今后研究磁牵引连续性的基础，必须保留。

### 4.3 B04：propagation / traction / reconstruction beta 身份

必须整合：

- `ModalFieldReconstructor` 显式接收 positive/negative traction beta；
- E 使用 propagation beta，H/traction 使用 selected coupling traction beta；
- static local reassembly 使用 `beta_override=selected_coupling_traction_beta`；
- shape、finite、两侧完整性 fail-closed tests。

这项修复不解决接口空间不完备，但避免 solve/recovery 使用不同离散导数。

### 4.4 B06：near-degenerate blocks 的检测与 fail-closed，排除 bounded repair

必须保留：

- 完整 `||B-I||_inf`、最大 entry、cross-block pair、beta distance 和 group provenance audit；
- `NearDegenerateBlockPartitionSplitError` 或等价 deterministic exception；
- solve 前 fail closed；
- 累积 row-norm 反例测试。

不得整合：

- Task036 特定的一次 joint-left inverse bounded repair；
- 自动寻找/移动 worst groups；
- 任何放宽 `1e-6` Gate 的逻辑。

通用 continuation/joint subspace rotation 留待以后独立任务，不在本次 master 集成中发明。

### 4.5 Hybrid-P disposition

保留明确状态语义：

```text
full3d_physical_solution_exists
hybrid_modal_rank_insufficient
hybrid_interface_closure_failed
diagnostic_projection_bug
hybrid_p_production_qualified
full3d_fallback_is_hybrid_success
```

但仅合入最小 status helper/contract；不合入 Task036 226 点 robustness campaign、动态调度器或
大规模 analyzer。

---

## 5. 第三组：保留为 research-only 的 Hybrid/oracle 能力

用户明确要求先保留 Hybrid。因此以下正结果应进入 `master`，但必须隔离于 ordinary production
path。

### 5.1 Strong-trace Hybrid

保留 `src/solvers/hybrid_strong_trace_direct.py` 的最小可执行实现及其小型 fixture/test，要求：

- explicit opt-in；
- ordinary default 不变；
- 文档状态固定为 `research_only`；
- 明确结论为“完整切向 E continuity pass，但完整 joint-Cauchy/全部通道未资格化”；
- 不导入 Task036 robustness/capacity runner；
- 不声称 Hybrid-P production pass。

若当前文件与研究 runner 耦合，Codex 必须将 solver core 与调度/证据代码拆开后再集成。

### 5.2 Exact FE trace-chain correctness oracle

保留以下最小功能：

- one-cell two-port exact Schur action；
- endpoint active-row identification；
- `endpoint_cauchy_columns()` / `endpoint_cauchy_balance()`；
- full FE trace-chain matrix-free action；
- serial block-tridiagonal Schur recursion；
- 已验证的 MPI block recursion，如其测试在 master 上独立通过；
- compact five-block materialization仅作为 oracle/debug；
- exact trace vs Full3D 的小型/tiny regression。

推荐的函数白名单包括：

```text
EndpointActiveRows
OneCellTwoPortSchurAction
identify_endpoint_active_rows
build_one_cell_two_port_schur_action
endpoint_cauchy_columns
endpoint_cauchy_balance
solve_block_tridiagonal_recursive
solve_block_tridiagonal_recursive_mpi
PairedEndpointSchurAction
FullFeTraceChainAction
```

不得整合：

- R1 mode-pool PEP campaign；
- B1 discrete-Bloch rank selection；
- reachable-source POD；
- transfer-optimal randomized capacity；
- 96-RHS teacher；
- 7679 行综合研究 runner。

若 `src/solvers/one_cell_discrete_bloch.py` 同时混有上述黑名单代码，禁止整个文件原样复制。优先
提取白名单到职责单一的小模块（例如 `one_cell_trace_schur.py`）；若 Codex 选择保留原文件名，
也必须删除/不引入未获批准的 mode-pool/capacity入口，并由 focused tests 证明功能闭合。

### 5.3 Endpoint trace mass / Riesz action

保留 `src/solvers/hybrid_port_metric.py` 中稀疏 endpoint mass 和 Riesz actions：

- 它们可用于 exact Cauchy audit；
- 对 Task037 的接口/coarse-space metric 也可能有价值；
- 必须保持 sparse action，不显式形成 inverse；
- 状态标为 research utility，不自动成为 production preconditioner。

---

## 6. 明确禁止进入 `master` 的内容

以下文件或功能留在 Task036 远程分支作为研究历史，不做 selective merge：

```text
benchmarks/run_task036_robustness_scan.py
benchmarks/analyze_task036_robustness_scan.py
benchmarks/task036_robustness_scan_points.csv
benchmarks/run_task036_r1_port_capacity.py
benchmarks/run_task036_transfer_optimal_port_capacity.py
benchmarks/task036_transfer_capacity.py
benchmarks/run_task036_exact_cauchy_port_audit.py        # 大型研究 runner；只保留小 helper/tests
benchmarks/analyze_task036_exact_cauchy_port_audit.py
```

以及：

- B1 v1–v4/v9 mode-pool、block-prefix、Petrov/capacity plumbing；
- C1a paired POD scaffold 与所有未运行的 C1b/C1c 代码；
- 自动 rank tuner、retry、fallback、campaign、scheduler；
- scalar reciprocal research-only construction 和 bounded near-degenerate repair；
- 226 点 robustness scan 及其综合 analyzer；
- `.codex/environments/environment.toml`；
- `run_demo*.sh` 的删除；这些与 Task036 选择性修复无关，不得顺带改变 master；
- response/reply/review V1–V7 和 round-by-round 大型历史文档的整体复制；远程 Task036 分支本身即为
  完整历史 authority。

禁止因 import 依赖而把黑名单 runner 拉入 `master`。应移动小型通用 helper，而不是复制调用者。

---

## 7. 文档与 compact evidence 的选择性整合

`master` 不需要复制整个 Task036 文档树，但必须保留一个可审计的结项包：

### 必须进入 master

```text
docs/task036_forward_solver_bugfix_hardening/task.md
docs/task036_forward_solver_bugfix_hardening/review_report_v8.md
docs/task036_forward_solver_bugfix_hardening/outcomes/fix_report.md
docs/task036_forward_solver_bugfix_hardening/outcomes/test_summary.md
```

并新增一个短文件：

```text
docs/task036_forward_solver_bugfix_hardening/outcomes/final_summary.md
```

`final_summary.md` 必须包含：

- exact trace-chain correctness pass；
- M120/M240、strong-trace full-channel、B1 `d<=360` controlled negatives；
- C1b cancelled/not_run；
- 选择性合入 commit SHA；
- 未合入文件/功能；
- Task036 分支最终 SHA；
- Task037 分支创建结果（在创建后追加）。

### 可选进入 master

仅在不扩大依赖时保留 compact Case099 fixture/records：

```text
benchmarks/cases/099_strong_trace_hybrid_fixture/
```

其作用是保留 strong-trace/exact-Cauchy 的小型回归，不是 production benchmark。

### 不进入 master

- heavy ignored artifacts；
- 逐轮 response/reply/review 历史；
- robustness matrices；
- capacity/POD 文档；
- 大型 raw logs。

---

## 8. Codex 在 `master` 上的选择性整合步骤

### M0：停止并冻结 Task036

1. 确认无 Task036/MPI/MUMPS/Python 残留进程；
2. Task036 分支工作树必须 clean；
3. 推送包含本 V8 的最终 Task036 branch HEAD；
4. 不运行 C1b，不再修改 Task036 数值算法。

### M1：更新 master，不创建分支

```bash
git fetch origin --prune
git checkout master
git pull --ff-only origin master
```

必须记录起始 `origin/master` SHA。若本地 master 不干净，停止并报告；不得 stash 未知用户工作后
继续。

### M2：按意图形成选择性提交

建议形成以下三个或四个提交，而不是一个巨大 commit：

1. `fix(task036): integrate full3d correctness and telemetry hardening`
   - 第3节全部通用修复与 tests；
2. `fix(task036): retain hybrid interface safety fixes`
   - B02 通用部分、B03、B04、B06 detector-only、Hybrid-P disposition；
3. `feat(task036): retain strong-trace and exact-trace research oracles`
   - 第5节 research-only 功能与 focused tests；
4. `docs(task036): record controlled-negative closeout`
   - V8、fix/test/final summary、capability/progress registry 更新。

禁止 cherry-pick 包含综合 Task036 runner 的提交后再“尽量删除”；应从 master 逐函数/逐 hunk 移植。

### M3：更新能力矩阵

更新：

```text
docs/capability_matrix.md
docs/development_model_registry.md
docs/development_progress.md
```

状态至少包括：

```text
Task036 compressed direct Hybrid       = controlled_negative / closed
strong-trace Hybrid                    = research_only
exact FE trace-chain                   = research_only correctness oracle
M120/M240 complete global port         = not production-qualified
M120 long-range modal core             = retained
Task037 matrix-free iterative          = branch prepared / task not yet defined
```

不得把 Task036 结项写成 0.7 nm 已解决。

---

## 9. Master 集成测试 Gate

### 9.1 静态检查

```text
Ruff lint on all touched Python files
compileall on src/ and touched benchmarks
ruff format --check on newly created/small extracted modules
git diff --check
tracked JSON parse
```

历史大 runner 不进入 master，因此不得以“旧 runner 太大”为理由跳过新模块格式检查。

### 9.2 必须的 targeted tests

至少覆盖：

```text
test_14_stage4_dtn_modes.py
test_33_task032_mode_classification.py
test_39_task032_hybrid_augmented_direct.py
test_53_task033_high_order_hybrid_components.py
test_68_task033_full3d_watchdog.py
test_70_task033_reduced_equal_accuracy.py
test_79_task034_native_full3d_reference.py
test_80_task034_mpi_identity.py
test_115_task035b_assembly_time_condensation.py
test_179_task035b_hybrid_static_condensation.py
test_181_task035c_p6_h10_runner_gates.py
test_195_task036_mumps_factor_nnz.py
test_196_task036_forward_solver_hardening.py
```

并为选择性提取后的功能保留/新增小型 tests：

```text
strong-trace E restriction and fail-closed contract
one-cell exact Schur action
endpoint Cauchy column/balance
block-tridiagonal recursion serial/MPI
total-vs-historical memory semantics
process-group termination negative path
```

不得整体复制 `test_216_task036_transfer_capacity_discrete.py`；只移植与白名单 helper 直接相关的
小型测试。

### 9.3 MPI / PDE smoke

在 qualified `complex128/int32` 环境中至少执行：

1. 一个 p2 Full3D direct projection smoke；
2. 一个 static-condensed Full3D row-semantics/true-residual smoke；
3. Ny3 alias controlled negative（solve 前停止）和 Ny4 positive smoke，若成本允许；
4. strong-trace tiny/fixture smoke；
5. exact trace-chain tiny direct-vs-full algebra oracle。

不要求重跑 Task036 五个 heavy grazing/P anchors，但 master 集成不得只靠 pure NumPy tests。

### 9.4 Full repository test

在 targeted tests 和 MPI smoke 通过后，运行一次无 deselect 的 full repository pytest。

若出现失败：

- 数值/ABI/source failure 必须修复；
- 历史文档/环境 contract failure必须诚实分类并定向关闭；
- 不得把失败测试删除或放宽 Gate 以完成 merge。

### 9.5 推送条件

只有以下全部成立才允许：

```bash
git push origin master
```

- worktree clean；
- ordinary defaults unchanged；
- targeted tests pass；
- MPI smoke pass/controlled negative as intended；
- full suite 完成并有诚实结论；
- `git diff master_base..HEAD` 只包含本 V8 白名单内容；
- no Task036 capacity/POD runner present。

推送后记录最终 `origin/master` SHA 和 ahead/behind=0/0。

---

## 10. Task037 分支准备指令

只有 `master` 选择性整合完成并成功推送后，Codex 才创建新分支。ChatGPT 本轮不创建分支。

冻结分支名：

```text
codex/20260803-task37-matrix-free-iterative-development
```

创建要求：

```bash
git fetch origin --prune
git checkout master
git pull --ff-only origin master
git switch -c codex/20260803-task37-matrix-free-iterative-development
git push -u origin codex/20260803-task37-matrix-free-iterative-development
```

Task037 分支必须：

- 精确从更新后的 `origin/master` 创建；
- 初始 SHA 与 merge 后 master SHA 相同；
- upstream 已设置；
- ahead=0、behind=0；
- worktree clean；
- **不创建 `task.md`，不实现任何 solver，不运行新的 PDE**；
- 只报告 branch、SHA、upstream 和 clean status，然后停止。

Task037 的具体技术任务由用户在分支推送后与 ChatGPT 另行讨论，不得由 Codex提前自行定义。

若 master 集成失败或未推送，禁止创建 Task037 分支。

---

## 11. 最终停止语义

```text
Task036 further numerical development  = forbidden
C1b/C1c                                = cancelled
new direct-port basis                  = forbidden in Task036
master full branch merge               = forbidden
master selective integration           = authorized
Task037 branch creation                = authorized only after master push
Task037 implementation                 = not authorized yet
```

最终结论：

> Task036 应以“低秩 direct Hybrid 主目标未证明、但域分解正确性和多项前向求解器修复成功”结项。
> 不删除 Hybrid，也不把 exact/strong-trace 研究成果丢弃；只将可复用、可测试且不污染 ordinary
> default 的 solver core、oracle 和通用 hardening 选择性整合到 master。B1/C1 压缩端口研究、
> 大型 runner 和未运行路线留在远程 Task036 分支作为完整历史。完成 master 集成后，仅创建并
> 推送 Task037 空分支，等待下一轮任务设计。
