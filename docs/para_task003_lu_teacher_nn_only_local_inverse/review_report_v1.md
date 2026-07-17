# REVIEW REPORT V1：PARA-Task003 LU Teacher 与少量 Slab Exact-Oracle 验收

## 0. 最终状态

```text
review = PARA-Task003 review_report_v1
branch = ChatGPT/20260715-para-task-neural-local-pc
review_status = PASS_WITH_QUALIFICATIONS
teacher_resource_result = PASS
teacher_accuracy_result = PASS
raw_rhs_independence = PASS
single_slab_exact_oracle = NUMERIC_PASS_GLOBAL_SIGNAL_FAIL
three_slab_exact_oracle = NUMERIC_PASS_GLOBAL_SIGNAL_FAIL
learned_linear_inverse = NOT_RUN_BY_GATE
nonlinear_nn_only = NOT_RUN_BY_GATE
factor_removal = NOT_RUN_BY_GATE
memory_saving_result = NOT_PROVEN
final_classification = exact_lu_oracle_global_signal_insufficient
ordinary_default_changed = false
production_claim_allowed = false
all_16_slab_exact_oracle = NOT_TESTED
all_16_slab_learned_pc = NOT_ALLOWED_BEFORE_NEW_ORACLE_TASK
h3_allowed = false
h2_allowed = false
branch_management = prohibited
master_operations = prohibited
```

PARA-Task003 的执行过程、数值证据和停机决定可以验收。任务成功建立了 raw-residual-only 数据合同、高精度 sparse-LU teacher、one-factor/many-RHS 生命周期和 selected-slab exact-LU oracle 端口，并证明这些基础设施在当前 h5、MPI4、complex Maxwell 局部算子上可用。

本任务最重要的结论不是“NN 失败”，因为任务根本没有进入训练阶段。它证明的是：

```text
slab 9 使用 exact local inverse：outer iterations 860 -> 862；
slab 0/9/10 同时使用 exact local inverse：860 -> 840，仅下降 2.33%。
```

因此，在当前 16-slab、two-step smoother、75D coarse 架构下，少量 selected slabs 的独立 local-inverse replacement 缺乏足够的全局杠杆。继续训练近似这些 selected-slab exact inverses 的 learned/NN-only 模型，不能建立可信的全局加速因果链。任务按冻结 Gate 在 P2 停止是正确的。

本结果不能外推为“所有 NN local PC 都无效”。它没有测试：

```text
全部 16 个 slabs 的 exact local inverse；
全部 16 个 slabs 的 ILU factor 真正移除；
one-step exact Schwarz 对 two-step smoother 的替代；
跨多个 slabs 的联合 learned correction；
learned coarse / deflation space；
不同物理参数和多个 RHS 的 operator learning。
```

因此，后续若继续，应先做新的全 16-slab exact-oracle 任务，而不是直接训练 16 个网络。

---

# 1. 审阅范围

本轮审阅覆盖：

```text
docs/para_task003_lu_teacher_nn_only_local_inverse/task.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/summary.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/teacher_resource_report.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/local_quality.csv
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/runtime_breakdown.csv
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/memory_report.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/model_and_dataset_provenance.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/decision.md
benchmarks/cases/092_lu_teacher_nn_only_local_inverse/
benchmarks/neural_pc/build_lu_teacher_dataset.py
src/solvers/lu_teacher_local_solver.py
benchmarks/run_workstation_iterative.py
src/test/test_35_lu_teacher_contract.py
src/test/test_36_exact_lu_oracle_petsc_adapter.py
src/test/test_37_para_task003_contract.py
```

正式冻结框架保持：

```text
13.5 nm complex-Si block grating
p2 Nedelec hexahedral FEM
h5 = 44,698 FE DoF
16 physical z-slabs
right FGMRES90
75D true-action Galerkin coarse correction
exact condensed DtN operator
full explicit true residual
official R/T/A + volume absorption
MPI4
```

本审阅不执行任何分支管理、master 操作、PR 或合并决策。全部结论只约束当前 research branch。

---

# 2. 接受的结果

## 2.1 Raw-residual-only 数据合同：接受

Task003 使用三次独立 baseline/capture run：

| capture | role | samples | saved contents |
|---|---|---:|---|
| A | train | 512 | `rhs` + `apply_index` |
| B | validation | 128 | `rhs` + `apply_index` |
| C | holdout | 64 | `rhs` + `apply_index` |

三份数据的 slab-9 exact operator fingerprint 一致。数据中没有：

```text
ILU output
ILU residual
ILU correction
current PC output
```

因此 Task003 真正实现了：

```text
input = raw local residual r_s
label = sparse-LU solution A_s^{-1} r_s
```

而不是继续学习 ILU 或 ILU-conditioned residual correction。

## 2.2 Sparse-LU teacher 资源可行性：接受

slab 9：

| 指标 | 实测 |
|---|---:|
| operator shape | 5,248 x 5,248 |
| matrix nnz | 526,696 |
| ordering | COLAMD |
| pivot threshold | 1.0 |
| factorization | 2.576 s |
| L+U nnz | 4,099,255 |
| fill ratio | 7.783x |
| explicit factor storage estimate | 82,069,076 B |
| reused RHS | 704 |
| triangular solve mean / p95 / max | 13.263 / 14.500 / 18.528 ms |
| swap in/out | 0 / 0 |
| factor destroy | confirmed |

实现确实采用：

```text
factorize once
-> solve many RHS
-> verify labels
-> destroy factor
```

没有对每个样本重复 factorization，也没有同时常驻多个 slab teacher factors。

结论：

```text
h5 slab-9 sparse-LU teacher 在当前机器上资源可行。
```

该结论不能直接外推到 h3/h2 或 16 个 factors 同时常驻。

## 2.3 Teacher 数值精度：接受

704 个 teacher labels 的局部残差为：

```text
median = 5.940e-15
p95    = 7.503e-15
max    = 9.585e-15
```

远低于任务 Gate：

```text
median <= 1e-11
p95    <= 1e-10
max    <= 1e-9
```

因此 teacher 标签可以视为当前 complex128 路径下的高精度 local inverse reference。

## 2.4 Exact-LU owner backend 与全局数值可信性：接受

selected slab 的 runtime backend 确实调用 `SparseLuTeacherLocalSolver`，其他 slabs 继续调用现有 ILU。MPI2 owner-computes adapter、full test suite、full augmented residual 和 official R/T/A 均通过。

正式 h5 结果：

| run | exact slabs | iterations | full residual | R/T/A closure |
|---|---|---:|---:|---|
| baseline | none | 860 | `9.930033e-7` | pass |
| single oracle | 9 | 862 | `9.890735e-7` | pass |
| conditional oracle | 0, 9, 10 | 840 | `9.974997e-7` | pass |

因此 oracle 的失败是全局收敛信号不足，不是 local LU、Maxwell 解或后处理错误。

---

# 3. 主要审阅结论

## 3.1 Major：单 slab exact inverse 没有全局正信号

slab 9 从 ILU 提升为 exact local inverse 后：

```text
860 -> 862 iterations
```

没有达到任务要求的至少 2% 下降，反而增加两步。

这说明：

```text
slab 9 的 ILU 近似精度不是当前外层 FGMRES 的主要限制因素；
单独训练 slab-9 NN-only inverse 缺乏全局理论上限；
即使 NN 完美复现 exact LU，也不能据此预期显著减少 outer iterations。
```

## 3.2 Major：三个代表 slab exact inverse 仍未达到 Gate

slab 0/9/10 同时使用 exact LU：

```text
860 -> 840 iterations
reduction = 2.33%
```

低于冻结的 5% Gate。

因此当前“先 slab 9，再扩展到 slab 0/10”的少量 slab-specific learned replacement 路线应停止。P3-P7 不运行是正确的，不属于任务遗漏。

## 3.3 Major：Task003 没有证明 NN-only 不可行

Task003 只证明：

```text
少量 selected-slab exact inverse 的全局杠杆不足。
```

它没有证明：

```text
16 个 slabs 全部 exact/learned inverse 无效；
all-slab factor removal 无内存价值；
one-step learned Schwarz 无法替代 two-step smoother；
联合跨-slab网络或 learned coarse 无效。
```

因此最终分类必须保持范围限定：

```text
exact_lu_oracle_global_signal_insufficient
```

不得改写成 `nn_failure`、`neural_pc_not_feasible` 或类似过度结论。

## 3.4 Major：训练前停机是正确的科学决策

若继续训练，实际研究问题会变成：

```text
如何近似一个已经证明缺少全局杠杆的 selected-slab oracle。
```

这会消耗 GPU 时间、checkpoint 存储、shadow/active h5 runs 和调参工作，却无法建立全局加速的因果链。

因此：

```text
learned linear inverse = NOT_RUN_BY_GATE
nonlinear NN-only = NOT_RUN_BY_GATE
factor removal = NOT_RUN_BY_GATE
```

是应当接受的结果。

## 3.5 Moderate：oracle 内存不能解释为 replacement 内存

当前 oracle 为了测量迭代上限：

```text
保留 existing ILU factors
+ 额外构造 selected sparse-LU factors
```

所以峰值相对 baseline 增加：

```text
slab 9 exact LU      = +11.50%
slab 0/9/10 exact LU = +25.57%
```

这些数字不能用于判断真正 factor removal 后的内存，也不能用于推断 NN checkpoint 内存。

下一任务若测试 all-slab exact oracle，必须提供 **no-hidden-ILU profile**，对 exact slabs 不得构造或保留 ILU factor。

## 3.6 Moderate：provenance 足够支持 research-negative Gate，但非 canonical performance

formal records 指向正确 commit/branch，但重型 oracle 运行发生于 Task003 实现尚未提交的 dirty worktree。

因此可用于：

```text
research stop/go decision
oracle iteration upper-bound diagnosis
numerical correctness evidence
```

不可用于：

```text
clean-final-HEAD canonical wall-time qualification
跨机器精确性能宣传
production record
```

由于结论是 iteration Gate 明确失败，不要求为制造更漂亮结果而补跑；若下一任务需要严格 A/B，应从 clean Task004 implementation HEAD 成对运行。

## 3.7 Moderate：文档中的 factorization 时间应统一

`teacher_resource_report.md` 和 `outcomes/summary.md` 使用 2.576 s；Case092 README 一处写为 2.924 s。最终审阅采用更完整资源报告中的：

```text
factorization = 2.576 s
```

执行者后续回应审阅时应统一 Case README，或解释 2.924 s 对应不同计时范围。

## 3.8 Moderate：三 slab local timing 汇集不完整

三-slab root record 没有汇集 non-root slab 10 的 local timing。全局 iteration、operator count、residual 和 R/T/A 完整，因此不影响本次 oracle Gate；但下一任务必须进行 MPI rank-local diagnostics gather，确保 16 个 slabs 的：

```text
factorization time
factor nnz/storage
apply count
apply mean/p95
owner rank
```

全部汇集至 root record。

---

# 4. 对下一步研究方向的判断

## 4.1 为什么下一步应先做全 16-slab exact oracle

当前证据形成了以下逻辑：

```text
1 exact slab  -> no signal
3 exact slabs -> weak 2.33% signal
```

在训练 16 个独立模型或一个共享模型之前，必须回答：

```text
如果全部 16 个 local solves 都达到 exact inverse，
当前 two-level architecture 的 outer iterations / operator actions 最多能改善多少？
```

如果全 16-slab exact inverse 仍只改善很少，则 local-inverse learning 不是值得继续的主方向，应转向 coarse/deflation/global error modes。

如果全 16-slab exact inverse 显著改善，则说明：

```text
少量 slab 杠杆不足，但 all-slab replacement 具有理论上限；
训练 16 个独立模型、专家模型或共享模型才有依据。
```

## 4.2 下一任务必须真正移除 ILU factors

下一任务不能继续使用：

```text
ILU factors + exact LU factors
```

作为正式 all-slab oracle profile。

应新增 backend planning/lifecycle，使 exact-enabled slabs 在 setup 时直接跳过 ILU factorization。全 16 exact profile 必须证明：

```text
selected exact slabs ILU factor count = 0
selected exact slabs ILU apply count = 0
no hidden fallback action
no hidden duplicated factor
```

这既能给出更可信的 oracle 内存，也为未来 NN-only factor removal 建立正确端口。

## 4.3 应同时测试 two-step 与 one-step exact Schwarz

当前 two-step inner smoother 会重复调用局部 backend。未来 NN 更合理的目标可能不是复制 two-step 路径，而是：

```text
one learned/exact local Schwarz action
替代 current two-step smoother
```

因此下一任务建议同时测试：

```text
Lane A: all-16 exact local inverse + current two-step smoother
Lane B: all-16 exact local inverse + one-step smoother
```

必须记录 outer/inner operator action counts，而不能只看 outer iterations。

---

# 5. 接受与保留边界

## 5.1 接受保留

当前 research branch 中可继续使用：

- raw-only local RHS capture；
- slab filter 和 independent capture provenance；
- sparse-LU one-factor/many-RHS teacher；
- teacher residual Gate；
- exact-LU local backend abstraction；
- operator fingerprint/checksum；
- MPI owner-computes adapter tests；
- Case092 与负结果文档；
- full residual、R/T/A、memory telemetry。

## 5.2 不得提升

不得将以下内容称为已验证能力：

- NN-only local inverse；
- selected-slab factor removal；
- local NN memory saving；
- all-slab neural PC；
- universal/shared model；
- h3/h2 neural acceleration；
- production-ready neural preconditioner。

---

# 6. 最终验收决定

```text
PARA-Task003 disposition = ACCEPTED_WITH_QUALIFICATIONS
teacher feasibility = ACCEPTED
teacher accuracy = ACCEPTED
single/three-slab oracle numeric path = ACCEPTED
selected-slab global acceleration signal = FAILED
training stop decision = APPROVED
P3-P7 = CORRECTLY_NOT_RUN
ordinary default = UNCHANGED
master/branch operations = PROHIBITED
next research task = APPROVED_FOR_ALL_16_SLAB_EXACT_ORACLE_ONLY
```

Task003 是一次成功的负结果研究：它在训练前用 exact oracle 排除了当前少量 slab replacement 路线，避免了无依据的 NN 训练和调参。下一步只有在全 16-slab exact oracle 明确显示足够的全局收益后，才允许讨论 16 个 NN、专家模型或共享模型。