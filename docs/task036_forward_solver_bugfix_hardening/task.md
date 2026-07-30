# Task036：3D Full3D / Hybrid 前向求解器鲁棒性缺陷修补

## 0. 任务身份

```text
task = Task036
task_kind = BUGFIX_ONLY
status = READY_FOR_CODEX_EXECUTION
working_branch = codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity
new_branch = forbidden
ordinary_default_change = forbidden unless required by a confirmed correctness bug
new_solver_architecture = forbidden
new_package_or_framework = forbidden
surrogate_training = out_of_scope
inversion = out_of_scope
iterative_solver = out_of_scope
hp_adaptivity_research = out_of_scope
```

本任务只修复已经有明确失败证据、代码审阅证据或可重复回归证据的 bug，并补齐必要的鲁棒性检查。不得借 Task036 继续扩建 Task035e 的 campaign、blind controller、evidence schema、receipt、watchdog、h/p controller，也不得开始 Task035f 迭代求解器研究。

本任务不要求“把 Hybrid-P 彻底开发成生产方法”。如果某个问题需要新的模态算法、全新耦合架构或大规模重写，应保留当前失败证据并增加明确的 fail-closed 路由，不得在 Task036 中展开大开发。

---

## 1. 源码与文档基线

### 1.1 当前工作分支

所有修改继续发生在：

```text
codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity
```

编写本任务书时该分支审阅基线为：

```text
cef2793fbc3157f8b0f65a51a395954fe5cb38bb
```

执行前必须重新记录实际 HEAD、upstream 和 clean status。不得创建 Task036 新分支，也不得整体 merge 其他分支。

### 1.2 需要对照的另一台主机工作分支

```text
codex/only-one-13p5nm-surrogate-inversion
```

编写本任务书时该分支审阅基线为：

```text
1a55efb4530da56cb9099ee3c660e250f8c36b6c
```

该分支已经在连续几何、连续照明、S/P 偏振和批量运行中暴露并修复了若干前向求解器 bug。Task036 必须手工、逐文件地移植已确认的最小修复；禁止整体 merge、禁止整体 cherry-pick、禁止把 `src/forward_data`、surrogate campaign、dataset schema 或数据生成框架带入当前分支。

### 1.3 已复制的轮次历史

必须先完整阅读：

```text
docs/task036_forward_solver_bugfix_hardening/
    round_by_round_execution_history.md
```

该文件是从以下来源原样复制：

```text
surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
    outcomes/round_by_round_execution_history.md
```

它区分早期阶段性判断与后续证据支持的当前结论。不得只读取结论段而跳过失败过程。

---

## 2. 强制阅读范围

开始改代码前，Codex 必须阅读 `codex/only-one-13p5nm-surrogate-inversion` 中：

```text
surrogate_tasks/**/*.md
surrogate_tasks/**/*.json
```

其中必须重点阅读全文：

```text
surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/
    failure_robustness_correction_task.md
    outcomes/five_configuration_failure_correction.md

surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
    outcomes/round_by_round_execution_history.md
    outcomes/m2_solver_domain_qualification.md
    outcomes/m4_y_alias_diagnosis.md
    outcomes/hybrid_hardening_or_quarantine.md
    review_report_v7.md
```

同时必须阅读当前 Task035e 分支中与共享求解器相关的代码和测试，至少包括：

```text
src/common/config_3d.py
src/common/modes_3d.py
src/constraints/cross_section_floquet.py
src/constraints/floquet_3d.py
src/coupling/hybrid_internal_modes.py
src/coupling/modal_trace_projection.py
src/modes/cross_section_spaces.py
src/modes/mode_classification.py
src/modes/quadratic_beta_eigenproblem.py
src/postprocessing/hybrid_field_reconstruction.py
src/solvers/common_3d_solve.py
src/solvers/dtn_port_3d.py
src/solvers/hcurl_assembly_time_condensation.py
src/solvers/hybrid_fem_modal_augmented_direct.py
src/solvers/hybrid_local_dtn.py
src/solvers/hybrid_local_static_condensation.py
benchmarks/run_task032_phase6_augmented.py
```

还必须检查所有直接覆盖上述模块的现有测试。

### 2.1 阅读结果的最小交付

编码前先生成：

```text
docs/task036_forward_solver_bugfix_hardening/outcomes/
    bug_port_matrix.md
```

表格至少包含：

```text
bug_id
失败现象
根因证据
surrogate 分支涉及文件/commit
当前 Task035e 是否已包含修复
本轮最小修改
回归测试
是否需要新 PDE
最终状态
```

该表只用于防止漏项，不得发展成新的 schema、数据库或自动 evidence 框架。

---

## 3. 总体修复原则

### 3.1 允许

- 手工移植已验证的最小代码修复；
- 修正公式、坐标、分量、degree、quadrature、beta、归一化和遥测语义；
- 增加小型单元测试、解析测试和少量真实 PDE 回归；
- 为未资格化的 Hybrid 情况增加清晰的 fail-closed 检查；
- 修复明确的 MPI collective、对象生命周期和整数溢出 bug；
- 在现有函数中增加必要的字段或 docstring，使诊断语义不再混淆。

### 3.2 禁止

- 新建 package、solver framework、state machine、campaign 或数据集框架；
- 为了通过测试放宽 residual、energy、trace、leakage 或 biorthogonality Gate；
- 删除 P 偏振、把 P 改成 S、提高掠射角下限或跳过失败角度；
- 将 Hybrid 失败重命名为“物理不可解”；
- 自动把 Hybrid 路由改成 Full3D 后仍写成 Hybrid 成功；
- 整体 cherry-pick surrogate 分支中的混合提交；
- 重新启动 Task035e h/p 研究；
- 开始代理模型、批量数据、角度 DOE、反演或迭代法；
- 为单个测试样本写硬编码几何、角度或 mode index 特判。

### 3.3 规模限制

每个 bug 应优先在现有模块中局部修复。若单个 bug 需要：

```text
超过 3 个核心模块的结构重写
或
新增超过约 500 行非测试代码
或
超过 90 分钟仍无法形成明确最小修复
```

则停止该 bug 的实现，保留复现和根因，增加 fail-closed 检查，并在报告中列为 `DEFERRED_ARCHITECTURE_REQUIRED`。不得因此扩建大框架。

---

## 4. P0：必须修复的已确认 correctness bugs

## B01：DtN 直接模态投影必须严格使用切向场

### 已确认问题

当前 Task035e 分支的：

```text
src/solvers/dtn_port_3d.py::_mode_projection_from_solution(...)
```

使用完整三分量：

```text
inner(E_total, full mode.e_vector)
```

但分母使用：

```text
mode.electric_tangential_norm_sq
```

这在 S 模式中因 `e_z=0` 被掩盖；P 模式具有非零 `e_z` 时会产生假 discrepancy。

### 必须移植的修复

参考 surrogate 分支中的已实现版本：

```text
E_t       = (E_total[0], E_total[1], 0)
reference = (e_x, e_y, 0) * phase
numerator = integral E_t · conj(reference)
denominator = electric_tangential_norm_sq
```

同时移植或等价实现纯 NumPy 的 synthetic tangential projection helper，明确忽略第三分量。

### 必须测试

1. oblique S；
2. oblique P，且 `e_z != 0`；
3. top incident subtraction；
4. bottom lossy P；
5. top/bottom、S/P、`n=0` 与一个非零 n order；
6. 近零通道使用绝对误差，不使用不稳定的相对误差。

验收：

```text
|a_auxiliary - a_direct_tangential| <= 1e-10
```

不得修改官方 auxiliary amplitude 的定义来迎合错误 diagnostic。

---

## B02：高阶 reciprocal trace 的 degree / quadrature / canonical coordinate 一致性

### 已确认问题

在低掠射 `0.5° / 0° / S` 和 P 对照中，正负 reciprocal trace 曾通过两套独立数值坐标路径生成；roundoff 被高阶插值和 entity reduction 放大到 `O(1e-8)`。

### 必须移植的修复

从 surrogate 分支逐文件核对并手工移植：

- lifted modal coefficient 使用真实 polynomial degree；
- 显式记录并使用正确 surface quadrature；
- reciprocal negative trace 共用同一 canonical coordinate identity；
- 保留 raw reciprocal consistency；
- 每个 side/role/mode 保存 entity-supported reduction；
- 不再依赖单个样本的坐标 roundoff 恰好低于阈值。

重点比较：

```text
src/coupling/modal_trace_projection.py
src/coupling/hybrid_internal_modes.py
src/constraints/cross_section_floquet.py
benchmarks/run_task032_phase6_augmented.py
```

不得直接覆盖当前 Task035e 的高阶 Floquet / exact-sequence 修复；必须逐块合并。

### 必须测试

- p1–p6；
- S/P；
- MPI1/2；
- standard 与 static-condensed；
- 正负 reciprocal trace；
- orientation reversal；
- 低掠射 F1 配置。

验收至少满足：

```text
max interior trace residual <= 1e-10
slave residual = 0
raw reciprocal consistency <= 1e-12
```

历史修复达到约 `2.8e-13`，但不得把该单点数值硬编码成普遍阈值。

---

## B03：traction sampled proxy 与 exact variational conormal dual 必须分离

### 已确认问题

历史代码把 sampled strong-traction density L2 proxy 写成类似 exact traction dual 的名称，并可能被 formal Gate 误用。

### 必须移植的修复

参考已验证 commit：

```text
13aba78c8ef4645a96871ceaf72eeb751b8eb401
Use exact variational traction dual diagnostic
```

手工移植其中的最小核心变化：

1. `src/solvers/hybrid_fem_modal_augmented_direct.py`
   - 增加详细 `_fe_traction_equilibrium_diagnostics(...)`；
   - formal residual 使用 exact variational conormal functional dual；
   - 报告 operator、RHS、positive/negative modal traction load norms；
   - 保留兼容的 scalar view，避免无必要破坏调用者。

2. `src/postprocessing/hybrid_field_reconstruction.py`
   - sampled strong traction 改名为 `traction_density_l2_proxy`；
   - 明确它是 diagnostic-only；
   - 增加或移植 assembled interface continuity 中的 exact `traction_hcurl_dual` 语义。

3. `benchmarks/run_task032_phase6_augmented.py`
   - formal H/traction Gate 使用 exact `traction_hcurl_dual.relative_dual`；
   - 不使用 sampled density proxy 作为通过条件。

### 必须测试

- synthetic exact balance；
- 故意扰动 modal traction 后 dual residual 增长；
- sampled proxy 与 exact dual 可不同，但字段和 Gate 不混淆；
- top/bottom；
- standard/static；
- S/P。

---

## B04：propagation beta、traction beta 与 reconstruction beta 不得静默混用

### 已确认问题

Hybrid P 诊断中已发现传播、电磁场恢复和 traction 可能使用不同离散符号。当前代码必须显式区分：

```text
propagation beta
traction beta
reconstruction beta
```

### 修复要求

- E 场传播使用冻结的 propagation beta；
- H/traction 使用冻结的 traction beta；
- 每份结果记录两者来源和数值身份；
- 不允许 continuous QEP beta 与 scalar-CG discrete derivative 在未声明的情况下混用；
- Route A/B 结果若选择相同，应明确记录而不是依赖默认值；
- 不改变已经通过的 S 结果。

本项只修语义和错误混用。不得在 Task036 中重新设计新的 axial modal method。

---

## 5. P0：Hybrid 鲁棒性与 fail-closed 修补

## B05：P 偏振不得被误判为物理失败

### 已知事实

- P 偏振 Full3D direct 在 F2–F5 均存在并通过 residual/energy；
- Hybrid M120 对 P trace rank 严重不足；
- M 增大到接近完整 rank 后，interface E 可改善，但当前 Hybrid-P energy closure 仍未资格化；
- absorption 的体积分与 Poynting loss 已独立闭合，因此 absorption 后处理不是根因。

### Task036 要求

只做以下 bugfix：

1. Hybrid-P 在 modal rank、biorthogonality、interface dual 或 energy 未通过时必须明确 fail closed；
2. 状态必须区分：
   ```text
   full3d_physical_solution_exists
   hybrid_modal_rank_insufficient
   hybrid_interface_closure_failed
   diagnostic_projection_bug
   ```
3. 不得输出 production-qualified Hybrid-P；
4. 不得为了通过而把默认 M 改成 576；
5. 需要 P 时，调用者可以显式选择已验证 Full3D 路由，但不得把路由切换写成 Hybrid 成功。

Task036 不负责把 Hybrid-P 重新开发成生产算法。

---

## B06：near-degenerate mode blocks 不得被错误拆分

### 已确认问题

Hybrid p6 在约 45° 方位出现：

```text
near-coincident beta modes
被分入相邻 blocks
block 内 normalization 通过
block 间 cross-overlap 超过 biorthogonality Gate
```

独立排序后的 mode index 还会随方位强交换，不能作为连续物理 identity。

### 允许的最小修复

优先检查 surrogate 分支 `src/modes/mode_classification.py` 的已有变化。若能局部修复：

- clustering 后检查相邻 blocks 的 beta spread 和 cross-overlap；
- 满足 near-degenerate 判据时合并并联合 biorthogonalize；
- 物理身份使用 overlap/subspace continuation，不使用独立 magnitude-sort index；
- 保存 merged block identity 和 before/after overlap。

### 硬停止

若修复需要重写 QEP eigensolver、全新 continuation framework 或大范围耦合接口，则不在 Task036 实现。此时必须：

- 增加确定性的 `near_degenerate_block_partition_split` 检测；
- 在进入 Hybrid solve 前 fail closed；
- 保持 Hybrid production quarantine；
- 保存一个真实 p6/45° 回归。

禁止通过增大 biorthogonality tolerance 掩盖。

---

## B07：y 向 trace alias 必须在批量运行前被识别

### 已确认问题

在 y 不变几何中，Ny=3 曾在：

```text
2*ky ≈ 3*Gy
```

附近把物理上正交的 `n=0` 与 `n=-3` trace 显著混合。Ny=4 后 overlap 和泄漏降至舍入误差。

这不是 surface quadrature bug，也不是随机求解波动。

### 修复要求

不得只为 Task002 硬编码 `(6,4,14)`。应在现有 config / DtN / runtime topology 路径中加入最小、通用的防护：

1. 运行时实际 axis cell counts 必须来自 config，并进入结果；
2. 计划与实际 `(Nx,Ny,Nz)` 不一致时 fail closed；
3. 对声明 y-invariant、固定 n=0 物理子空间的运行，在正式 bulk 前计算 relevant port trace Gram/overlap 或等价的 alias preflight；
4. 若任一非目标 n order 与 n=0 overlap 超过冻结阈值，给出明确错误和建议 Ny refinement；
5. 不放宽 `n!=0` leakage Gate；
6. Ny3 作为 controlled negative 保留，Ny4 regression 必须通过。

不得在 Task036 中建立新的 dataset/campaign identity 系统。

---

## 6. P1：Task035e 分支中已确认或高风险的共享 bug

## B08：MUMPS factor NNZ 的 int32 overflow

### 已确认问题

p6/h5 曾把真实 factor entries 写成负数：

```text
PETSc MatInfo raw = -2017967296
MUMPS INFOG(9)    = -2277
```

离线解释为：

```text
factor_nnz = 2,277,000,000
```

### 修复要求

在：

```text
src/solvers/common_3d_solve.py::_petsc_factor_inventory
```

增加通用、64-bit-safe 的解释：

- raw PETSc 值原样保留；
- raw MUMPS INFOG 原样保留；
- 若 MUMPS 负值使用“绝对值 × 1,000,000 entries”语义，生成 Python `int` corrected field；
- 不覆盖原始字段；
- factor fill 使用 corrected count；
- 非 MUMPS 不套用该规则；
- 测试覆盖 `>2^31`。

不得重跑 p6/h5。

---

## B09：solver 对象生命周期不得无故叠加到 field output

Task035e 已证明，在不再需要 KSP/MUMPS factor、system matrix、RHS 和 solution 后及时销毁，可释放数 GiB 内存。

### 修复要求

- 检查普通 Full3D static 和 Hybrid 路径是否仍把 factor/system objects 保留到场输出之后；
- 只有在后处理确实不再需要时才提前释放；
- 必须先完成 field recovery、residual 和所有需要 factor 的回代；
- 释放后不得再次访问已销毁对象；
- `malloc_trim(0)` 返回 0 只表示当前无页可归还，不得作为数值失败；
- 记录 release 前后 current RSS，但不得把生命周期优化冒充矩阵结构压缩。

当前 Task035e 已有的逐 cell p6 basis 流式 goal-gradient 和 h-shadow transfer cleanup 不得重写；只做回归确认。

---

## B10：内存 authority 与 MPI 身份语义

### 修复要求

- 不得把各 rank 在不同时间的 historical peak 相加冒充 simultaneous process-tree peak；
- 有外部同步 sampler 时以同一时刻 process-tree RSS/PSS/USS 为 authority；
- 无同步 sampler 时必须明确写 `historical_upper_bound`；
- raw global vector bytes/hash 随 MPI partition 变化，不得作为物理 identity；
- 物理 identity 优先使用分区无关的 topology、phase、constraint count、residual 和 canonical entity hashes。

只修错误标签和判断，不建立新 telemetry framework。

---

## B11：active DoF、storage carrier 与 condensed rows 必须分开

高阶 variable-p 路径中必须分别报告：

```text
active exact-sequence FE DoF
storage-carrier p6 FE DoF
independent trace rows
augmented rows
```

不得把 p6 storage carrier 当作实际 active DoF，也不得用 Full3D-equivalent DoF 代替实际线性系统行数。增加小型 regression，覆盖 p5-trace/p6-interior 和 selective trace。

---

## 7. 明确不在 Task036 修复的事项

以下属于后续架构或性能研究，只登记为 technical debt：

- `_active_trace_values_from_augmented` 的全局 allgather 可扩展性；
- Hybrid replicated `M^2`、all-mode multi-RHS 和 local LU；
- Hybrid-P 新模态架构；
- iterative preconditioner；
- 自动 h/p controller；
- 0.7 nm 大规模整数/内存架构；
- surrogate campaign、resume、dataset、schema 和 active learning。

不得因为发现这些问题而扩大 Task036。

---

## 8. 执行顺序

## M0：只读差异审计

不改代码，完成 `bug_port_matrix.md`：

- 对照两个分支的同名核心文件；
- 找出已存在、缺失和冲突的修复；
- 记录 surrogate commit/file SHA；
- 禁止整体 cherry-pick。

## M1：纯代码/解析修复

优先完成无需 PDE 的：

```text
B01 tangential projection
B03 traction semantic split
B08 factor overflow
B10 telemetry labels
B11 DoF semantics
```

先运行 unit tests、synthetic tests、compileall、Ruff 和 `git diff --check`。

## M2：Full3D port regression

只运行能验证修复的最小点集：

- 一个 oblique S；
- 一个 oblique P with nonzero e_z；
- top/bottom auxiliary-vs-direct；
- 一个 lossy-bottom P；
- standard/static 若两者均受影响。

不得运行角度网格或 bulk campaign。

## M3：高阶 reciprocal trace 与 Hybrid interface regression

复用已有 F1–F5 raw evidence，最多重跑必要的代表点：

- F1 0.5°/0°/S；
- 一个低掠射 P；
- 一个 10° P；
- 一个原通过的 10° S control。

先验证 trace、exact conormal dual 和 beta 语义；Hybrid-P 若仍未资格化必须 fail closed。

## M4：near-degenerate 与 Ny alias

- 一个 p6/45° near-degenerate regression；
- 同一物理点 Ny3 与 Ny4 对照；
- 不运行 80-angle map；
- 不恢复 surrogate bulk。

## M5：共享回归

至少运行：

- existing DtN port tests；
- high-order Floquet p1–p6 targeted tests；
- static condensation tests；
- Hybrid augmented direct targeted tests；
- Task035b/35c/35d 已合并核心 targeted tests；
- Task035e shared-core tests，不运行 blind campaign；
- MPI1/2，必要项 MPI8；
- tracked JSON parse；
- compileall；
- Ruff；
- `git diff --check`。

所有新 PDE 一次只运行一个。通常不应超过约 12 个；若需要更多，先停止并解释为什么现有 evidence 不能完成 bug 验证。

---

## 9. 验收 Gate

### 9.1 投影与 trace

```text
auxiliary-vs-direct tangential amplitude <= 1e-10
F1 max interior trace residual <= 1e-10
slave residual = 0
reciprocal consistency <= 1e-12
```

### 9.2 求解与物理

```text
true relative residual <= 1e-9
abs(R + T + A_volume - 1) <= existing frozen Gate
Floquet mismatch <= existing frozen Gate
zero swap
cleanup complete
```

### 9.3 Hybrid

- S 既有通过点不得退化；
- P Full3D reference 必须继续通过；
- Hybrid-P 未达到 rank/interface/energy Gate 时必须明确 fail closed；
- near-degenerate block 不得通过放宽阈值掩盖；
- 若只增加检测而未修复，状态应为 `DEFERRED_ARCHITECTURE_REQUIRED`。

### 9.4 Ny alias

```text
Ny3 known alias point = deterministic controlled failure/preflight rejection
Ny4 same point n!=0 power <= 1e-7
Ny4 max n!=0 amplitude <= 1e-4
Ny4 trace overlap near roundoff
```

### 9.5 遥测

- `2,277,000,000` factor entries 能正确表示；
- raw overflow 值仍保存；
- historical upper bound 与 simultaneous peak 不混称；
- active/carrier/rows 字段不混称。

---

## 10. 最小交付

只需提交：

```text
docs/task036_forward_solver_bugfix_hardening/
    task.md
    round_by_round_execution_history.md
    outcomes/
        bug_port_matrix.md
        fix_report.md
        test_summary.md
```

以及实际必要的核心源码和测试修改。

`fix_report.md` 对每个 bug 必须给出：

```text
before
root cause
changed files
minimal fix
after
regression scope
remaining limitation
status = FIXED / VERIFIED_PRESENT / FAIL_CLOSED / DEFERRED_ARCHITECTURE_REQUIRED
```

不得新增 Case 目录、campaign、schema、receipt 或大体积 evidence JSON，除非现有测试系统确实要求一个很小的 fixture。

---

## 11. 最终停止条件

满足任一条件即停止该子项：

1. 已通过对应验收 Gate；
2. 已证明当前分支已有等价修复；
3. 需要新的数值架构；
4. 90 分钟内无法形成局部修复；
5. 新修复破坏 ordinary S / Full3D / static-condensed regression；
6. 需要放宽已有 Gate 才能“通过”。

整个 Task036 完成后：

- 提交并推送到当前 Task035e 分支；
- 报告最终 HEAD、修改文件、测试、未解决项和工作树状态；
- 不创建新分支；
- 不 merge master；
- 不开始 Task035f、代理模型、批量数据或反演。
