# REVIEW REPORT V2：Task029 最终验收、合并边界与后续研发路线

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260713-task29-stage4-direct-memory-forensics
reviewed_head = a48faf9c73a01bd90db35d2697d6136acfcc982e
base = master@2f9e56d2edddb801780504f681b2ff295d993e02
review_chain = review_report_v1 + review_report_v1_p0c_addendum -> response_v1 -> review_report_v2
```

本轮复核范围：

```text
- Review V1 的 P0-A / P0-B 线程能力审计；
- 固定四核预算下 MPI4x1、MPI2x2、MPI1x4、MPI1x1 的 h=5 full solve；
- threaded h3 的条件停止决定；
- Task029 outcomes 与 Benchmark050 新记录；
- development_progress 的结构化重写；
- Task retrospective 长期标准、工作原则和文档合同；
- telemetry、异常清理、solver package 选择、OOC 与生命周期代码；
- 哪些内容可以进入 master，哪些性能身份不得提升；
- Task029 之后的研发优先级。
```

---

# 2. 最终审查结论

```text
review_status = pass_with_minor_documentation_closeout

task29_classification = diagnostic_success
engineering_success = no
strong_engineering_success = no
h2_workstation_success = not_attempted_by_gate

baseline_memory_forensics = pass
stage_attribution = pass
matrix_factor_inventory = pass_with_measurement_qualification
rank_count_diagnostic = pass
threaded_direct_audit = pass_as_negative_capability_result
threaded_direct_capability = unavailable_in_current_image
h2_guard_decision = pass
auto_propagating_modal_identity = pass
numeric_reference_protection = pass
ordinary_default = pass

telemetry_infrastructure = pass
failure_cleanup = pass
solver_package_selection_fix = pass
release_base_lifecycle_option = pass_as_explicit_diagnostic_option
benchmark050 = pass_as_diagnostic_benchmark
retrospective_standard = pass
project_level_documentation = pass

new_low_memory_direct_profile = none
further_direct_micro_optimization_in_current_task = stop
heavy_rerun_required = no
master_merge = yes_after_response_v2_final_status_sync_and_user_approval
```

准确结论是：

> Task029 已完成其诊断目标。当前 Stage4 直接法的全局峰值主要由 `KSPSetUp` 中 MUMPS analysis 与 numeric LU factorization 产生，而不是 DtN 辅助变量、`A_base/A_aug` 共存、KSPSolve、official R/T/A 或场输出。低风险生命周期优化只能降低约 5%，减少 MPI rank 在 h=3 只能降低 15.119%，OOC、BLR、SuperLU_DIST 和新 ordering 均未形成合格路径；当前镜像中的 MPI1×4 也没有实际多核 factorization。继续在 Task029 内微调直接法的预期收益已经不足，应停止扩展。

Task029 没有形成新的推荐 direct profile，也没有改变 ordinary default；但它形成的内存遥测、Benchmark、异常清理、solver 选择正确性、生命周期控制、安全 Gate 和长期文档规范具有明确的主线价值。

---

# PART I：最终接受的技术结论

## 3. 直接法主内存瓶颈

h=3 MPI4 baseline：

```text
FE DoF = 198,438
auxiliary DoF = 80
augmented rows = 198,518
augmented nnz = 21,317,860
factor nnz = 266,127,836
factor / augmented nnz ratio ~= 12.48
max simultaneous worker RSS = 8,651.098 MiB
max cgroup current ~= 8,353.727 MiB
full true residual = 1.382e-11
```

阶段归因：

```text
before KSPSetUp -> factorization peak:
  worker RSS increase ~= 6,472 MB
  cgroup increase ~= 6,475 MB

KSPSolve retained increase ~= 7 MB
official RTA increase < 1 MB
field output increase ~= 129 MB
A_base / A_aug coexistence increase ~= 729–755 MB
```

最终判断：

```text
primary = LU analysis/factor fill
secondary = base/augmented coexistence
not primary = solve/back-substitution
not primary = RTA/postprocess
not primary = 80 auxiliary diffraction modes
```

## 4. 候选结果与最终处置

| 路线 | h=5 内存变化 | h=3 内存变化 | 数值 Gate | 最终身份 |
|---|---:|---:|---|---|
| release `A_base/b_base` | `-4.767%` | `-5.462%` | pass | 保留为显式生命周期控制；不是低内存 profile |
| MUMPS MPI2 | `-28.893%` | `-15.119%` | pass | 最佳诊断点；未达工程 Gate |
| MUMPS OOC | `-13.744%` | not_run | pass | 磁盘换 RAM fallback；不提升 |
| MUMPS BLR `1e-5` | `+3.427%` | not_run | fail | 拒绝；真残差和 R/T/A 不合格 |
| SuperLU_DIST | `+14.462%` | not_run | pass | 当前 target 内存更差，拒绝 |
| MUMPS `ICNTL(7)=3` | `+4.093%` | not_run | pass | factor nnz 和峰值增加，拒绝 |

表中正号表示内存增加，负号表示内存下降。

## 5. 少 rank + 多线程最终结论

Review V1 后，Codex 对当前镜像进行了只读构建审计和固定四核 h=5 full-solve 矩阵。

活动环境：

```text
PETSc = 3.24.0
MUMPS = 5.8.1
system BLAS = OpenBLAS 0.3.26 pthread
CPU affinity = cores 0-3
source commit = 48958571f62590418bf4281f09ad22b1419eb880
```

固定四核结果：

| 配置 | Stage4 time | 内存特征 | KSPSetUp CPU 证据 | 结论 |
|---|---:|---|---|---|
| MPI4 x 1 | `18.311 s` | 多进程最高 | 多 rank 并行 | baseline |
| MPI2 x 2 | `20.687 s` | 介于 MPI4 与 MPI1 | 主要仍依靠 MPI | 可作诊断，不是新 profile |
| MPI1 x 4 | `48.273 s` | 接近 MPI1 x 1 | mean/peak `0.999 / 1.054` cores | 线程未用于 MUMPS 主 factorization |
| MPI1 x 1 | `50.891 s` | 单 rank 最低 | 约 1 core | reference |

MPI1×4 相对 MPI1×1 只有约 `1.054x` speedup，并未接近 MPI4×1。虽然进程中创建了额外 pthread，但 MUMPS `KSPSetUp` 的有效 CPU 使用仍约为一个核心。

最终身份：

```text
threaded_direct_capability = unavailable_in_current_image
T1 actual-factorization-threading = fail
T3 useful-speedup = fail
threaded h3 = not_run by T4
```

因此：

```text
- 不继续重建镜像追逐 hybrid MUMPS；
- 不把 MPI1x4 或 MPI2x2 提升为 workstation profile；
- 不再在 Task029 中投入少-rank多线程优化；
- 若未来更换为明确支持 hybrid factorization 的 HPC 软件栈，可重新建立独立任务验证，但不能沿用本次资格。
```

## 6. h=2 安全决策继续有效

```text
central predictions = 22.214 / 22.330 GiB
sensitivity range = 18.882–27.913 GiB
safe limit = 13.5 GiB
h2_launch_decision = not_run
```

Review V1 后没有出现任何足以改变该判断的新 h=3 低内存 profile；线程方向又在 h=5 被否定。因此不需要重新计算 h=2，也不需要重新拟合 h=2。

---

# PART II：Master 合并边界

## 7. 可以合并到 master 的内容

### 7.1 内存遥测与 Benchmark 基础设施

```text
benchmarks/run_direct_memory_forensics.py
benchmarks/cases/050_stage4_direct_memory_forensics/*
benchmarks/check_benchmarks.py 的 Case050 contract
simultaneous worker RSS / process-tree RSS / cgroup / swap sampler
stage marker 与 KSPSetUp/KSP solve/postprocess checkpoint
matrix/factor nnz inventory
raw MUMPS INFOG/RINFOG 按 index 保存
clean-source provenance
h2 launch Gate 与 prediction helpers
CPU/thread/affinity diagnostic fields
```

理由：这些组件不改变普通求解物理和默认 profile，可以复用于后续 direct、iterative 和大规模内存审计。

### 7.2 低风险正确性与生命周期修复

```text
DirectSolveFailure.cleanup() 幂等 PETSc 对象清理
OOC 成功/失败 scratch 清理与保留规则
显式 distributed factor package 不被 fallback MUMPS 静默覆盖
serial-only factor package 在 MPI 路径被拒绝
direct_release_base_after_augmentation 显式 opt-in
```

其中 `direct_release_base_after_augmentation` 的身份必须保持：

```text
diagnostic lifecycle option
not ordinary default
not qualified low-memory profile
observed h3 gain ~= 5.46%
```

### 7.3 线程能力负结果基础设施

```text
scripts/audit_direct_thread_capability.sh
--threads-per-rank
--cpu-affinity
CPU time / core-equivalent / process-thread telemetry
h5_threaded_direct_audit.json
threaded h3 not-run decision
```

这些可以合并，原因是它们记录并保护“当前镜像线程无效”的负结果；但只能作为诊断工具，不能作为普通运行推荐入口。

### 7.4 文档与长期治理

```text
docs/task029_stage4_direct_memory_forensics/*
docs/development_progress.md 的完整 Task029 章节
docs/task_retrospective_standard.md
README / docs README 工作原则更新
docs/repository_work_principles.md 长期回顾条款
capability matrix / solver guide / benchmark docs / code walkthrough
Task retrospective 与 documentation contract tests
COMSOL reference 与 comparability boundary
```

这些应当全部进入 master，作为项目知识和后续 Task 的强制流程。

## 8. 不得提升或写成 production 能力的内容

以下内容可以作为负结果、配置入口或记录存在于 master，但**不得被提升为默认/推荐/qualified profile**：

```text
MPI2 MUMPS direct
MPI1 MUMPS direct
MPI2 x 2 threaded direct
MPI1 x 4 threaded direct
MUMPS OOC
MUMPS BLR 1e-5
SuperLU_DIST for this target
MUMPS ICNTL(7)=3
release-base as a standalone low-memory solution
```

必须继续保持：

```text
ordinary direct default = Task28 behavior
ordinary iterative default = unchanged
all alternative direct profiles = explicit opt-in / diagnostic / fallback
```

## 9. 不允许进入 master 的重型或未实现内容

```text
benchmarks/artifacts/cases/050/* heavy timelines
raw PETSc/MUMPS logs
mesh / field / VTU / XDMF / HDF5
factor / OOC scratch files
private-API direct augmented assembly prototype（未实现）
任何 h=2 新 record（不存在）
任何减少 auto_propagating diffraction modes 的版本
```

## 10. 合并形式

从代码边界看，当前 Task029 branch 可以作为一个整体 PR 合并，因为：

```text
- rejected routes were not made ordinary defaults；
- experimental options remain explicit；
- negative results are represented by records/docs rather than hidden production selection；
- canonical Task28 records were not overwritten；
- heavy artifacts remain ignored。
```

建议使用普通 PR merge 或 merge commit，保留 Task029 的诊断、review 和 response 历史。

---

# PART III：Response V2 的最终文档同步

## 11. Codex 只需完成轻量 closeout

Codex 应继续在同一分支提交：

```text
docs/task029_stage4_direct_memory_forensics/response_v2.md
```

禁止新增 direct solver 实验、h=2、threaded h3、新 ordering、BLR tolerance sweep 或新软件镜像。

## 12. 最终状态同步

Codex 应将以下文件从“等待 final review”更新为“V2 技术通过、等待用户合并许可”：

```text
README.md
docs/README.md
docs/development_progress.md
docs/capability_matrix.md
docs/solver_guide.md
docs/benchmark.md
benchmarks/README.md
benchmarks/cases/050_stage4_direct_memory_forensics/README.md
docs/task029_stage4_direct_memory_forensics/outcomes/summary.md
docs/task029_stage4_direct_memory_forensics/outcomes/merge_recommendation.md
docs/task029_stage4_direct_memory_forensics/outcomes/next_decision.md
```

必须统一写明：

```text
Task029 final classification = diagnostic_success
engineering_success = no
new optimized direct profile = none
threaded_direct_capability = unavailable_in_current_image
h2 = not_run
ordinary default = unchanged
technical review = pass
master merge = approved after explicit user permission
```

## 13. 文档索引

`docs/README.md` 必须加入：

```text
review_report_v2.md
response_v2.md
```

并将 Task029 状态改为：

```text
final closeout pending user merge approval
```

## 14. 最终轻量验证

在 `response_v2.md` 提交前运行并记录：

```text
ruff changed Python
python -m compileall benchmarks src
Task29 focused tests
repository principles tests
Task retrospective/documentation contract tests
benchmark checker --no-write
JSON/CSV parse
git diff --check
tracked source clean
```

不要求重新运行任何 h=5/h=3/h=2 物理案例。线程与 direct records 已来自 clean source，后续仅文档状态修改。

---

# PART IV：下一阶段建议

## 15. 停止继续微调直接法

Task029 已经排除了当前最直接的低风险方向：

```text
- base/augmented duplicate only ~=5% benefit；
- current preallocation has no allocator waste signal；
- MPI2 h3 only 15.119%；
- OOC only moderate RAM shift with disk cost；
- BLR/ordering/SuperLU negative；
- current threaded MUMPS effectively single-core；
- direct augmented rewrite is high risk with <=5–9% expected benefit。
```

因此下一阶段不应继续：

```text
MUMPS parameter sweep
BLR tolerance sweep
rank/thread combinations
h2 direct retry
new direct package search in the current image
```

Direct solver 后续定位保持：

```text
reference solver
small/medium validation
coarse solve
local subdomain solve
diagnostic fallback
```

## 16. 推荐 Task030：H(curl) 几何多层基础设施与预条件器可行性

建议名称：

```text
Task030: Nested H(curl) geometric hierarchy,
transfer-operator validation, and multilevel preconditioner feasibility
```

中文：

```text
Task030：H(curl) 嵌套几何层次、传递算子验证与多层预条件器可行性
```

### 16.1 为什么是这个方向

```text
1. 未来目标是 1–2 TB 工作站上的千万级 DoF，direct LU 不具备合理扩展性；
2. Task27 的 physical-slab + fixed coarse 已能求解，但 615k DoF 仍约 13 GB；
3. Task029 证明 direct 的主要成本是不可避免的 fill，而非可轻易清理的框架副本；
4. COMSOL 的成功路径是 Krylov + 完整 GMG 层次，而不是裸 Krylov 或单个 ILU；
5. 当前 boundary-fitted structured hexahedral target 天然适合建立嵌套几何层次；
6. 后续 graded/adaptive mesh 也需要可靠的层次、传递和粗空间基础。
```

### 16.2 Task030 第一阶段目标

Task030 不应立即追求百万 DoF production，而应先验证多层基础设施：

```text
- h=5/h=3 的嵌套 hexahedral mesh hierarchy；
- p2 H(curl) fine space 与 p1/粗网格 H(curl) space；
- edge/face DoF orientation-correct prolongation/restriction；
- double Floquet phase-compatible transfer；
- material/interface-aware hierarchy；
- transfer of vectors and operator action；
- Galerkin coarse operator or rediscretized coarse operator equivalence；
- complex inner-product and Hermitian semantics；
- matrix-free fine action；
- exact condensation 与 80 个 DtN auxiliary modes 保持不变。
```

### 16.3 Gate 顺序

```text
Stage A: nested mesh and DoF maps only
Stage B: prolongation/restriction algebraic tests
Stage C: two-level preconditioner on small h5
Stage D: smoother screening on h5
Stage E: h3 confirmation
Stage F: only after memory/iteration positive signal consider h2
```

数值保护：

```text
full true residual
Task28/Task27 R/T/A reference
same auto_propagating mode set
same Floquet constraints
same physical target
```

### 16.4 候选 smoother 方向

优先研究适合 H(curl) 层次的方法，而不是重新堆叠全局 ILU：

```text
edge/vertex/element patch block smoothers
additive or multiplicative Schwarz patches
Vanka-like local field blocks
Chebyshev/Jacobi on shifted/coercive operator
p2 -> p1 auxiliary correction
coarse MUMPS only on sufficiently small system
```

之前失败的 AMS/HX 结果不能直接当作本任务结论，因为它们针对的矩阵形式、real split、coarse construction 和问题阶段不同；但 Task030 必须阅读这些负结果，避免原样重复。

## 17. Task031：周期匹配分级/自适应网格

多层基础设施有正信号后，再进入：

```text
boundary-fitted graded mesh
periodic-face synchronized refinement
interface/edge/corner local refinement
R/T/A and near-field error indicators
uniform h2 vs graded mesh comparison
adaptive loop and physical convergence qualification
```

这样安排的原因是：

> 自适应网格负责降低达到目标物理精度所需的 DoF；多层预条件器负责降低每个 DoF 的求解内存和时间。未来千万级模型两者都需要，不能只依赖其中一个。

---

# 18. 最终决策摘要

```text
Task029 diagnostic objective = ACCEPTED
Task029 direct engineering objective = NOT MET
Task029 threaded-direct hypothesis = REJECTED FOR CURRENT IMAGE
Task029 h2 run = CORRECTLY NOT RUN
Task029 infrastructure/docs = APPROVED FOR MASTER
Task029 performance candidates = NOT APPROVED AS DEFAULT OR QUALIFIED PROFILE
Task029 branch merge = APPROVED AFTER RESPONSE V2 STATUS SYNC AND USER PERMISSION
next research direction = H(curl) geometric multilevel infrastructure
```
