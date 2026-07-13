# REVIEW REPORT V1：Task029 直接法内存诊断验收、线程并行条件验证与阶段文档收口

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260713-task29-stage4-direct-memory-forensics
base = master@2f9e56d2edddb801780504f681b2ff295d993e02
scope = Task029 code + Benchmark050 + outcomes + documentation
```

本轮重点复核：

```text
- h=5/h=3 MPI4 direct baseline；
- simultaneous RSS / cgroup / swap / historical peak 的统计口径；
- KSPSetUp、KSPSolve、RTA、field output 的阶段归因；
- base/augmented matrix 生命周期；
- MPI1/2/4 rank-count 诊断；
- MUMPS OOC、BLR、ordering 与 SuperLU_DIST 筛选；
- h=2 内存预测与 G1–G10 启动决策；
- auto_propagating 全传播衍射级是否保持；
- telemetry、异常清理、solver-package 选择与 Benchmark050；
- Task029 是否形成新的 production direct profile；
- 项目总览文档是否足以清楚表达 Task029 的方法、结果和最终决策。
```

---

# 2. 审查结论

```text
review_status = changes_required

task29_classification = diagnostic_success
engineering_success = no
strong_engineering_success = no
h2_workstation_success = not_attempted_by_gate

baseline_memory_forensics = pass
stage_attribution = pass
memory_metric_semantics = pass
matrix_factor_inventory = pass_with_qualification
numeric_reference_protection = pass
auto_propagating_modal_identity = pass
rank_count_diagnostic = pass
h2_guard_decision = pass
ooc_screen = pass_as_diagnostic
blr_screen = rejected_correctly
superlu_dist_screen = rejected_correctly
ordering_screen = rejected_correctly
ordinary_default = pass

telemetry_infrastructure_merge = recommended_after_response
failure_cleanup_merge = recommended_after_response
solver_package_selection_fix_merge = recommended_after_response
release_base_opt_in_merge = recommended_with_diagnostic_identity
new_low_memory_direct_profile = none

threaded_direct_capability = not_yet_verified
project_level_documentation = partial_fail
master_merge = not_yet
```

准确结论是：

> Task029 已经成功定位当前直接法的内存主瓶颈，并建立了可信的内存遥测、矩阵/factor inventory、候选筛选与 h=2 安全决策。它没有找到达到 h=3 至少 20% 降内存门槛的新 direct profile，因此不能把 MPI2、OOC、BLR、SuperLU_DIST 或新 ordering 提升为推荐路径。合并前还需要完成一次严格受控的“少 MPI rank + 多线程”能力验证，并重写项目级进度文档，使 Task029 的方法、对比、结论和决策对新读者清楚可见。

本报告不要求运行 h=2，不允许修改普通 direct 默认，也不要求在 Task029 中实现新的迭代预条件器或多重网格。

---

# PART I：已接受的 Task029 结果

## 3. h=5 / h=3 baseline 通过

当前 baseline 使用冻结的 Task28 target：

```text
period = 50 x 25 nm
block = 17 x 25 x 120 nm
cell height = 140 nm
lambda = 13.5 nm
theta = 80 deg
phi = 0 deg
polarization = s
material = complex Si
p = 2 Nedelec
boundary = double Floquet + auxiliary Fourier-DtN
order policy = auto_propagating
MPI baseline = 4 ranks
threads per rank = 1
```

正式 baseline：

| 指标 | h=5 MPI4 | h=3 MPI4 |
|---|---:|---:|
| FE DoF | 44,698 | 198,438 |
| auxiliary DoF | 80 | 80 |
| augmented rows | 44,778 | 198,518 |
| top / bottom modes | 40 / 40 | 40 / 40 |
| propagating modes | 80 | 80 |
| full true residual | `5.225e-12` | `1.382e-11` |
| max Task28 R/T/A delta | `0` | `1.865e-14` |
| simultaneous worker RSS | 2,328.145 MiB | 8,651.098 MiB |
| cgroup current peak | 1,729.035 MiB | 8,353.727 MiB |
| swap in / out | 0 / 0 | 0 / 0 |

接受这些结果作为 Task029 的统一内存口径 baseline。

## 4. 主瓶颈归因通过

h=3 的阶段数据表明：

```text
before KSPSetUp -> during KSPSetUp peak:
  worker RSS increase ≈ 6,472.43 MB
  cgroup increase ≈ 6,474.57 MB

KSP solve retained increment ≈ 6.98 MB
official RTA increment < 1 MB
field output increment ≈ 129.06 MB worker RSS
```

因此通过以下结论：

```text
primary bottleneck = MUMPS analysis + numeric LU factorization in KSPSetUp
secondary overhead = A_base / A_aug coexistence
not primary = KSPSolve
not primary = official RTA
not primary = field output
not primary = auxiliary modal DoF count
```

h=3 的 `A_base/A_aug` 共存增量约为 729 MB worker RSS / 755 MB cgroup，只占总峰值约 8%–9%。这解释了为什么提前释放 base objects 只能产生约 5% 的全局峰值收益。

## 5. Factor fill 结论通过，但保持口径限定

h=3：

```text
augmented nnz = 21,317,860
factor nnz = 266,127,836
factor / augmented nnz ratio ≈ 12.48
```

统一 nnz-storage estimator 给出：

```text
augmented estimated storage ≈ 489 MB
factor estimated storage ≈ 6,093 MB
```

接受“LU fill 是主内存量级”的结论，但必须继续保留以下限定：

```text
- PETSc raw factor memory/fill fields returned zero；
- 6,093 MB 是统一 nnz estimator，不是 MUMPS allocator 实测；
- INFOG/RINFOG 只按原始 index 保存，未猜测语义；
- worker RSS 与 cgroup charged memory 均需报告。
```

## 6. H1–H7 调查结论

### H1：提前释放 base matrix/vector

```text
h5 reduction = 4.767%
h3 reduction = 5.462%
numeric Gate = pass
```

接受为：

```text
low-risk lifecycle control
explicit opt-in
not a qualified low-memory profile
ordinary default remains false
```

### H2：A_aug 预分配

当前记录：

```text
nnz_allocated == nnz_used
nnz_unneeded = 0
mallocs = 0
```

接受“不在没有 allocator 证据时重写预分配”的决定。

### H3：临时对象与异常清理

接受：

```text
DirectSolveFailure.cleanup() idempotent cleanup
OOC success/failure cleanup semantics
required true residual and RTA objects retained
ordinary unconstrained diagnostic matrix remains disabled
```

### H4：直接装配 augmented matrix

当前公共 DOLFINx/dolfinx_mpc API 不提供安全地把 constrained FE block 直接装进外部 leading block 的路径，预计收益上限也只有约 5%–9%。接受：

```text
not implemented
no private API hack
no speculative master merge
```

### H5：solver package 与 rank 数量

接受 rank-count 诊断，但不接受新的默认 profile。

h=5、同为 MUMPS、每 rank 1 thread：

| 配置 | worker RSS | 相对 MPI4 | Stage4 time |
|---|---:|---:|---:|
| MPI1 x 1 thread | 1,230.305 MB | -47.16% | 25.969 s |
| MPI2 x 1 thread | 1,697.980 MB | -27.07% | 19.286 s |
| MPI4 x 1 thread | 2,328.145 MB | baseline | 14.800 s |

h=3 MPI2：

```text
worker RSS = 7,343.137 MB
reduction vs MPI4 = 15.119%
cgroup reduction = 15.362%
true residual = 1.334e-11
max R/T/A delta = 5.473e-14
swap = 0
```

接受：

```text
MPI2 = best diagnostic in-core point
MPI2 != engineering-success profile
MPI2 != ordinary default replacement
```

### H6：OOC、BLR、ordering

接受以下处理：

```text
OOC:
  h5 worker reduction = 13.744%
  scratch peak = 559,715,776 bytes
  Stage4 time ratio = 1.539
  numeric Gate = pass
  disposition = diagnostic fallback only

BLR 1e-5:
  true residual = 4.704e-3
  max R/T/A delta = 1.073e-3
  RSS increased
  disposition = reject

MUMPS ICNTL(7)=3:
  factor nnz increased
  RSS increased 4.09%
  disposition = reject
```

### SuperLU_DIST

```text
h5 RSS increased = 14.462%
Stage4 time increased ≈ 16%
numeric Gate = pass
```

接受 solver-package 选择逻辑修复，但拒绝 SuperLU_DIST 作为本 target 的低内存候选。

### H7：factor 与 postprocess 生命周期

当前 global peak 已发生在 KSPSetUp；field output 的第二峰值远低于该主峰。接受暂不为 global-peak 目标重构 factor/postprocess 生命周期。

---

# 7. h=2 不运行决定通过

选定 diagnostic candidate：

```text
MUMPS MPI2
one thread per rank
```

两种预测：

```text
DoF power-law prediction = 22.214 GiB
factor-nnz/fill prediction = 22.330 GiB
engineering sensitivity range = 18.882–27.913 GiB
safe limit = 13.5 GiB
```

失败 Gate：

```text
G3: h3 reduction 15.119% < 20%
G5: predicted upper bound 27.913 GiB > 13.5 GiB
G7: available memory ≈ 12.83 GiB < predicted lower bound
G9: watchdog not activated because earlier hard Gates already blocked launch
```

通过以下决定：

```text
h2_launch_decision = not_run
Task28 h2 record untouched
no h2 process created
no swap/thrashing experiment
```

这属于正确工程决策，不属于求解失败。

---

# PART II：关于“MPI1 + 4 threads”的准确判断

## 8. 不能先假定等价

用户提出的问题是：

```text
MPI1 x 4 threads
是否可以接近
MPI4 x 1 thread
的速度，
同时接近 MPI1 x 1 thread 的内存？
```

当前 Task29 **没有回答这个问题**，因为正式 rank-count 运行明确把：

```text
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
```

固定为每 rank 单线程。

理论上，少 MPI rank 可以减少进程级复制；线程共享同一地址空间，因此 factor 和大部分 solver 数据不会按线程完整复制。但这不意味着：

```text
1 rank x 4 threads == 4 ranks x 1 thread speed
```

是否能加速取决于：

```text
- 当前 MUMPS 是否以 hybrid/OpenMP 方式构建；
- linked BLAS 是否是可控的 threaded BLAS；
- KSPSetUp 中哪些 dense frontal kernels 能进入多线程；
- analysis、ordering、front scheduling、MPI-free serial sections 的比例；
- memory bandwidth 和 thread affinity；
- 是否发生 nested threading 或 oversubscription。
```

即使线程有效，也通常只能加速 factorization 的部分工作；分析、串行调度和其他阶段不会自动获得四倍加速。线程也会使用各自 stack/work buffer，因此内存会高于 MPI1 x 1 thread，但通常应明显低于多 MPI process 的复制量。

当前 h=5 数据给出需要跨越的门槛：

```text
MPI1 x 1 MUMPS time = 25.969 s
MPI4 x 1 MUMPS time = 14.800 s
required speedup to match MPI4 ≈ 1.75x
```

因此，只有实测才能判断该方向是否值得扩展。

---

# PART III：P0 补充工作

## 9. P0-A：线程能力审计

Codex 必须先确认当前镜像是否具备真实线程能力，不得只设置环境变量后假设线程生效。

至少记录：

```text
- PETSc configure/build information；
- MUMPS version/build information（可获得范围内）；
- linked BLAS/LAPACK provider；
- OpenBLAS/MKL/OpenMP runtime libraries；
- OMP_DISPLAY_ENV 或等价 thread runtime evidence；
- OMP_NUM_THREADS / OPENBLAS_NUM_THREADS / MKL_NUM_THREADS；
- CPU affinity / visible cores；
- KSPSetUp 期间实际 CPU utilization / thread count；
- 是否存在 nested thread oversubscription。
```

不得将 NumPy 自己的 BLAS 线程等同于 MUMPS factorization 线程。

### 9.1 停止条件 T0

若满足任一条件：

```text
- 当前 MUMPS/BLAS 构建不支持可控多线程；
- MPI1 x 4 设置后 KSPSetUp 仍只使用约 1 个核心；
- 线程数量无法可靠固定和记录；
- 出现不可控 nested threading；
```

则输出：

```text
threaded_direct_capability = unavailable_in_current_image
```

停止该方向，不重建复杂镜像，不运行 h=3，不把线程写成下一步推荐方案。

## 10. P0-B：固定四核预算的 h=5 screening

只有 P0-A 证明线程确实生效，才运行以下同机、同物理、完整 direct solve：

```text
A: MPI4 x 1 thread  （现有 baseline，可复用）
B: MPI2 x 2 threads
C: MPI1 x 4 threads
D: MPI1 x 1 thread  （现有 reference，可复用）
```

建议补充：

```text
MPI1 x 2 threads
```

用于判断线程 scaling 曲线。

必须保持：

```text
same target config
same auto_propagating 80 modes
same MUMPS package
same ordering/options
same full true residual
same official R/T/A
same machine/cgroup
same total core budget for A/B/C
no swap
```

每个运行记录：

```text
mpi_ranks
threads_per_rank
total_threads
actual thread evidence
KSPSetUp time
KSPSolve time
Stage4 time
max simultaneous worker RSS
cgroup peak
factor nnz
true residual
R/T/A delta
swap
```

## 11. 线程方向的决策 Gate

### T1：线程实际生效

```text
MPI1 x 4 的 KSPSetUp 平均 CPU usage 明显超过 1 核，
或其他底层证据证明 factorization 使用多线程。
```

### T2：内存保持接近单 rank

建议判断：

```text
MPI1 x 4 RSS <= 1.20 x MPI1 x 1 RSS
```

线程 buffer 允许有增长，但不应接近 MPI4 的进程复制水平。

### T3：速度具有实际价值

强正信号：

```text
MPI1 x 4 Stage4 time <= 1.25 x MPI4 x 1 Stage4 time
```

即 h=5 目标约：

```text
<= 18.5 s
```

且内存满足 T2。

可继续调查的中等信号：

```text
MPI1 x 4 Stage4 time <= 1.50 x MPI4 x 1 Stage4 time
```

即约：

```text
<= 22.2 s
```

同时相对 MPI1 x 1 有明确加速且内存接近单 rank。

负信号：

```text
- time > 1.50 x MPI4 baseline；
- 或 speedup vs MPI1 x 1 < 1.25x；
- 或 memory > 1.20 x MPI1 x 1；
- 或 thread evidence 不可信。
```

### T4：h=3 条件运行

仅在 h=5 达到强正信号时，才运行：

```text
MPI1 x 4 threads, h=3
MPI2 x 2 threads, h=3（若 h5 有竞争力）
```

h=3 只用于确认：

```text
- 内存收益能否保持；
- KSPSetUp speedup 是否保持；
- 数值和 modal identity 是否通过；
- 是否产生 swap。
```

无论线程结果如何：

```text
h=2 remains not_run
```

本轮不得重新解锁 h=2。

## 12. 线程方向最终身份

可能结论只能是以下一种：

```text
threaded_direct_unavailable:
  当前镜像没有有效线程能力；停止。

threaded_direct_negative:
  线程生效但速度/内存组合无价值；停止。

threaded_direct_diagnostic_positive:
  h5 有收益但未达到强 Gate；记录，后置。

threaded_direct_workstation_candidate:
  h5/h3 均满足数值 Gate，且接近 MPI4 速度、接近 MPI1 内存；
  仍保持显式 opt-in，等待下一轮审查，不直接改 ordinary default。
```

---

# PART IV：项目文档必须重写

## 13. 当前问题

Task029 的 `outcomes/summary.md` 和表格证据比较完整，但项目级文档仍不足以让新读者理解：

```text
- 为什么启动 Task029；
- 直接法内存暴涨在哪个阶段；
- 用了哪些遥测方法；
- h5/h3 baseline 是什么；
- H1–H7 分别验证了什么；
- 每个候选降低多少内存、是否改变结果；
- 为什么没有运行 h=2；
- 什么代码建议合并、什么 profile 被拒绝；
- 下一步为何转向 multilevel iterative / adaptive mesh；
- 少 rank + 多线程是否有实测结论。
```

Codex 必须在 `response_v1.md` 中同步更新以下文档。

## 14. P0-C：重写 `docs/development_progress.md`

Task029 部分不得只写一句“完成内存诊断”。必须形成独立、清晰的阶段章节，至少包括以下结构。

### 14.1 问题与目标

说明：

```text
- Task28 direct h2 约 18–20.5 GB，16 GB 机器会 swap；
- COMSOL 另一台机器、四面体、零级端口，只作内存量级参考；
- Task029 目标是区分 LU fill 与项目代码开销；
- 保留 FEniCS 全部 auto_propagating 传播级；
- h5/h3 先验证，h2 条件解锁。
```

### 14.2 使用的方法

必须写清：

```text
- 0.25 s 外部 sampler；
- simultaneous worker RSS；
- process-tree RSS；
- cgroup current/peak；
- swap in/out；
- stage marker；
- matrix/factor nnz inventory；
- clean-source provenance；
- full residual + official per-order R/T/A Gate；
- h=2 两种外推与 watchdog Gate。
```

### 14.3 Baseline 与内存归因

至少放入 h5/h3 表格，并明确：

```text
peak stage = KSPSetUp / MUMPS factorization
h3 factor/augmented nnz ≈ 12.48
base/aug coexistence only 8%–9% of peak
KSPSolve/RTA/output are not primary peak
```

### 14.4 候选结果对比

至少给出：

| 候选 | h5 降幅 | h3 降幅 | 数值 | 最终决定 |
|---|---:|---:|---|---|
| release base | 4.77% | 5.46% | pass | 保留为 opt-in lifecycle control |
| MUMPS MPI2 | 28.89% | 15.12% | pass | 诊断点，不是新 profile |
| MUMPS OOC | 13.74% h5 | 未进 h3 | pass | fallback，不提升 |
| BLR 1e-5 | -3.43% | 未进 h3 | fail | 拒绝 |
| SuperLU_DIST | -14.46% | 未进 h3 | pass | 内存更差，拒绝 |
| ICNTL(7)=3 | -4.09% | 未进 h3 | pass | 拒绝 |

其中负号必须解释为内存增加，不得产生歧义。

### 14.5 h=2 决策

明确写：

```text
prediction = 18.882–27.913 GiB
safe limit = 13.5 GiB
failed Gates = G3/G5/G7/G9
h2 = not_run
recommended machine = >=48 GB, preferably 64 GB
```

### 14.6 最终结论

必须区分：

```text
diagnostic success = yes
engineering success = no
new direct profile = no
ordinary default changed = no
merge telemetry/infrastructure = recommended after review
merge performance candidates = no
```

### 14.7 下一步

更新为：

```text
1. 本轮先完成 conditional threaded-MUMPS h5 screen；
2. 若无强正信号，停止 direct 微调；
3. 后续重点转向真正的 H(curl) multilevel / GMG-like iterative route；
4. 再推进 boundary-fitted graded / adaptive mesh；
5. direct 继续作为 reference solver，而不是千万 DoF production 主线。
```

## 15. P0-D：更新其他项目级文档

至少同步：

```text
docs/README.md
docs/capability_matrix.md
docs/solver_guide.md
docs/benchmark.md
benchmarks/README.md
benchmarks/cases/050_stage4_direct_memory_forensics/README.md
notes/reference/code_walkthrough/30_direct_solver_profiles.md
```

### `docs/capability_matrix.md`

必须写：

```text
Task29 telemetry = stable/merge candidate
Task29 optimized direct profile = none
MPI2 = diagnostic only
OOC = explicit fallback
BLR = failed numeric Gate
SuperLU_DIST = valid backend but negative memory result
threaded MUMPS = pending conditional validation / final status after response
```

### `docs/solver_guide.md`

必须增加 direct 选择表：

```text
default MPI4 MUMPS = Task28 reference baseline
MPI2 MUMPS = lower-memory diagnostic, not default
MPI1 MUMPS = lowest rank-replication memory but slower under 1 thread
OOC = disk-for-RAM fallback, not qualified low-memory profile
BLR = approximate and failed current tolerance
SuperLU_DIST = available but worse on target
release-base = opt-in lifecycle control, only ~5% h3 benefit
threaded MPI1/MPI2 = only if response experiment proves value
```

### `docs/benchmark.md` / Case050

必须展示最终结果和明确状态，不只链接 outcomes。

### `docs/README.md`

添加：

```text
review_report_v1.md
response_v1.md（完成后）
Task029 current status
```

---

# PART V：代码与合并边界

## 16. 建议保留的代码

在 P0 工作完成并通过复审后，建议保留：

```text
- benchmarks/run_direct_memory_forensics.py telemetry infrastructure；
- simultaneous RSS / cgroup / swap / OOC sampler；
- matrix/factor inventory；
- clean-source provenance；
- Benchmark050 contracts and lightweight records；
- DirectSolveFailure.cleanup()；
- explicit distributed factor-package selection correctness fix；
- OOC scratch/I/O/cleanup telemetry；
- direct_release_base_after_augmentation opt-in option；
- h2 gate and prediction helpers；
- associated tests and docs。
```

## 17. 不得提升的路径

```text
- MPI2 as ordinary default；
- MPI1 as ordinary default；
- OOC as qualified low-memory profile；
- BLR 1e-5；
- SuperLU_DIST for this target；
- ICNTL(7)=3；
- direct augmented assembly private-API rewrite；
- any h=2 new run；
- any reduction of diffraction modal set。
```

线程方向即使强正信号，也只能作为新的显式 workstation candidate，不能在本轮静默替换 Task28 direct default。

---

# PART VI：测试与回应要求

## 18. Response V1 文件

Codex 应在同一分支提交：

```text
docs/task029_stage4_direct_memory_forensics/response_v1.md
```

逐项回应：

```text
P0-A thread capability audit
P0-B fixed-four-core h5 screening / stop decision
P0-C development_progress rewrite
P0-D project documentation synchronization
```

若 h5 线程强正信号成立，再增加：

```text
P0-E conditional h3 threaded confirmation
```

## 19. 最低验证

```text
ruff changed Python
compileall benchmarks src
Task29 focused tests
full unit discovery
Task29/documentation contracts
benchmark checker --no-write
JSON/CSV parse
git diff --check
tracked source clean
```

线程运行还必须验证：

```text
true residual <= 1e-8
R/T/A delta <= 1e-8
same 80 propagating modes
same n_aux
no swap
actual thread evidence recorded
```

不要求重跑原 h5/h3 MPI4 baseline；已有 clean-source records 可复用。

---

# 20. 最终决策

当前状态：

```text
Task029 diagnostic objective = ACCEPTED
Task029 engineering memory objective = NOT MET
Task029 h2 direct objective = CORRECTLY NOT ATTEMPTED
Task029 infrastructure merge = PROVISIONALLY RECOMMENDED
Task029 performance profile merge = NOT RECOMMENDED
Task029 master merge = WAIT FOR RESPONSE V1 AND FINAL REVIEW
```

下一轮最终审查应回答：

```text
1. 当前镜像中的少-rank多线程是否真的有效？
2. MPI1 x 4 是否接近 MPI4 x 1 的速度并保持接近 MPI1 的内存？
3. 项目级文档是否已经清楚表达 Task029 全过程？
4. telemetry / cleanup / package-selection / lifecycle infrastructure 是否可安全进入 master？
```

若线程方向无效或收益不足，应明确停止 direct 微调，并将后续研发资源转入 H(curl) multilevel iterative 与 graded/adaptive mesh。
