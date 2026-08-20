# Task038-extra Review Report V1：接受 T0 并授权 T1–T6 连续开发批次

## 0. 审阅身份与决定

```text
review                                  = Task038-extra Review Report V1
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = 90fdf43dbc4ed1140d4951679e76c4dd37cf1a0e
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 2 / behind 0
reviewed_task                           = docs/task038_extra_full3d_iterative_0p7nm/task.md
reviewed_T0_commit                      = 90fdf43dbc4ed1140d4951679e76c4dd37cf1a0e
T0_status                               = ACCEPTED
review_classification                   = PASS_WITH_AUTHORIZED_CONTINUATION
continuous_authorized_batch             = T1 through T6, subject to all stage and hard-stop Gates
routine_stop_between_T1_and_T5          = not required
mandatory_review_stop                   = after T6 completion, T6 controlled stop, or any earlier hard stop
T7_T8_T9                                = not authorized in this review
full_0p7nm_PDE                          = forbidden
whole_Task37_extra_migration            = forbidden
whole_Task039_migration                 = forbidden
ordinary_default_change                 = forbidden
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
amend_or_force_push                     = forbidden
response_required                       = response_v1.md for this development batch
```

本审阅接受 T0 的三份 docs-only 审计。它们准确区分了当前 `master`、Task37-extra 研究档案、Task039 Hybrid 路线以及 Task038-extra 的 arbitrary-3D Full3D iterative 主线，没有把历史 action-only、Hybrid fixed-case 或 derived 0.7 nm 数字提升为当前生产资格。

为避免每完成一个基础阶段就中断开发，本 Review 不要求 Codex 在 T1、T2、T3、T4 或 T5 正常通过后分别停下来等待审阅。Codex 可以在同一执行分支内按阶段提交并连续推进；但所有 Gate、执行顺序、禁止项和资源停止线仍然有效。正常情况下，本批次应推进到 T6 的 13.5 nm p6/h10 Full3D iterative anchor 完成后，再统一提交 `response_v1.md` 等待下一次审阅。

---

# 1. T0 审阅结果

## 1.1 范围与 Git 身份

| 审阅项 | 结果 | 说明 |
|---|---|---|
| 默认分支 | pass | 仓库默认分支为 `master`，基线 SHA 为 `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| 执行分支 | pass | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| 被审 HEAD | pass | `90fdf43dbc4ed1140d4951679e76c4dd37cf1a0e` |
| 分支关系 | pass | 审阅时相对 `master` 为 `ahead 2 / behind 0`，merge-base 与指定 base 一致 |
| T0 文件范围 | pass | 只新增 `task.md` 与三份 T0 Markdown；无 Python、schema、runner 或 solver 修改 |
| PDE、MPI、benchmark | correctly not_run | T0 明确禁止这些运行，没有将未运行项写成通过 |
| ordinary default | unchanged | 没有改变普通数值方法或公开默认值 |
| master | unchanged | 没有写入或合并 `master` |

`outcomes/inherited_master_audit.md` 中的 `HEAD = 7114a6b...` 是写入三份 T0 文档之前的审计起点；三份文档提交后，远端当前 HEAD 成为 `90fdf43...`。这不是历史冲突，也不要求回写旧快照。后续 `response_v1.md` 必须同时报告本批次的 start HEAD、review commit 后的开始 HEAD 和最终 HEAD，避免把预提交快照误写为当前状态。

远端审阅无法独立观察 Codex 本地 canonical worktree 中的 nonignored untracked 文件，因此 Codex 拉取本 Review 后，仍必须重新报告：

```text
branch
HEAD
upstream
ahead/behind
git status --short
canonical worktree identity
```

工作树不干净时不得开始 T1。

## 1.2 Task37-extra 继承边界

T0 对 Task37-extra 的分类正确：

| 类别 | 接受的结论 |
|---|---|
| 可重构候选 | rank-one full-space action、MPC/Floquet action、matrix-free DtN architecture、canonical-vector utilities |
| 可复用模式 | JIT staging、cache identity、process-tree watchdog、对象生命周期记录 |
| diagnostic only | disk-backed Krylov；本批次默认不迁移 |
| deferred | p4→p6 owner-local transfer；本批次不开展 p/h multilevel lane |
| 明确不迁移 | dense-cell action、W8–W18 PC、84 个 882D factor store、fixed 75/390/530D range、LOR-HX、task-numbered giant runners |

旧分支中 action 与 DtN 的 PASS 只说明旧 source 下的组件资格；W5、W7 和 W18 的负结果只关闭对应 shifted-patch/range/nested family。两类结论都必须保留：不能把组件正结果写成 PDE pass，也不能把旧 PC 负结果扩大为所有 Full3D iterative 方法不可能。

## 1.3 Task039 边界

T0 正确识别 Task039 为独立 Hybrid 路线。其 5 nm direct/iterative、QEP/modal、exact-side、Petrov、W/K/LU 和 0.7 nm component envelope 都不能整体迁移为 arbitrary non-separable Full3D solver。

本批次只允许借鉴以下与 Hybrid 物理候选无关的通用模式：

```text
one-dat/one-run provenance
source/input/physical hash binding
process-tree watchdog and controlled stop
owner-local lifecycle and release ordering
measured/derived/predicted/not_run classification
```

不得迁移 Task039 的 Hybrid equation、M480/M960 profile、QEP packet、side factor、Petrov basis、runner 或固定案例阈值。

## 1.4 T0 最终裁决

```text
T0_ACCEPTED
NO_CORRECTIVE_T0_COMMIT_REQUIRED
CONTINUE_ON_THE_SAME_BRANCH
```

---

# 2. 为什么本轮允许连续推进到 T6

T1–T4 主要建立输入合同、精确 action、动态 DtN 和 owner-local interface topology。它们是后续 PC 的基础设施，本身还不能回答“新的 sweep 是否消除旧长尾”。真正的第一项算法裁决位于 T5：一次 forward+backward sweep 是否能显著压缩 physical RHS、旧 long-tail、checkerboard 和 gradient/curl residual。

若 T5 通过，T6 是第一个能够同时检查以下四件事的完整 anchor：

```text
真实时谐 Maxwell 收敛
完整 explicit true residual
official E/H and R/T/A observables
simultaneous process-tree memory
```

因此，将 T1–T6 作为一个有严格依赖顺序和硬停止条件的连续批次，比每个基础模块单独审阅更有效率。该授权不是无限自主搜索：候选、顺序、修复次数、checkpoint、资源线和停止点均被冻结。

---

# 3. 本 Review 授权的连续执行范围

## 3.1 总体顺序

Codex 必须按以下顺序执行：

```text
T1 dat contract and adapter
→ T2 generic full-space matrix-free volume action
→ T3 dynamic streaming full-space DtN
→ T4 slab/interface topology and transmission oracle
→ T5 bounded forward-backward sweep contraction
→ T6 conditional p6/h10 Full3D iterative anchor
→ response_v1.md and stop
```

不允许为了并行开发而先实现 T5/T6，再回补 T1–T4 evidence。各阶段可以形成独立提交并推送，但正常通过时不必等待 ChatGPT 逐阶段回复。

## 3.2 T1：显式 opt-in `.dat` 合同

授权增加：

```text
method.kind = "full3d_iterative"
solver.linear_solver = "iterative"
solver.preconditioner = "full3d_scalable_v1"
```

第一版公开字段仍应保持最小：

```text
solver.ksp_type
solver.restart
solver.max_iterations
execution.mpi_size
execution.memory_limit_gb
```

slab 数、transmission 细节、near-cutoff tolerance、coarse selector 和 inner parameters 不得作为一批临时研究参数暴露到公共 schema。它们必须由版本化、fail-closed 的 `full3d_scalable_v1` profile 固定，并写入 resolved config/manifest。

T1 必须完成：

- schema、validation、execution-plan 和 adapter identity；
- `--validate-only`、`--dry-run`；
- MPI size、method/solver mismatch、0.7 nm full-PDE attempt、unknown profile 的 fail-closed tests；
- ordinary 2D、staged 3D、Full3D direct、Hybrid direct/iterative regression contract；
- 不运行正式 PDE。

## 3.3 T2：通用 full-space matrix-free volume action

允许从 Task37-extra 逐文件重构：

```text
hcurl_rank_one_form_action.py
hcurl_rank_one_mpc_action.py
必要的最小 canonical-vector utilities
必要的 JIT/cache identity pattern
```

要求：

- 新实现进入通用 `src/` 命名空间，不保留 `task037_extra` 作为生产 API；
- 不复制 task-numbered orchestration、旧 preset 或 giant benchmark runner；
- 不形成 global AIJ、global Schur、slab matrix、factor 或 per-cell dense tensor cache；
- material、orientation、MPC 和 Floquet phase 必须来自当前模型合同；
- current `master` 上 fresh p2/p3、p6/h10、MPI1/MPI2 evidence。

最低 Gate 保持任务书原值：

| T2 项目 | Gate |
|---|---:|
| p2/p3 assembled action relative error | `<=1e-12` |
| p6/h10 reference action relative error | `<=1e-11` |
| MPI1/MPI2 canonical relative error | `<=1e-12` |
| repeat | 12 次 deterministic |
| retained-payload h10→h5 exponent | `<=1.10` |
| swap | `0` |

若第一个实现存在明确的 indexing、ownership、orientation、JIT 或 telemetry defect，允许一次窄修复并重跑同一冻结测试。第二次仍未通过时停止本批次，不进入 T3。

## 3.4 T3：动态、流式 full-space Fourier-DtN

允许以旧 `hcurl_fullspace_dtn.py` 为 architecture reference，但必须在当前分支重构为：

```text
dynamic mode inventory
propagating / near-cutoff / evanescent classification
owner-local sparse carrier
streaming or bounded batches
MPI1/MPI2 identity
no explicit C/D
no FE-sized numeric allgather
```

80-mode 只能作为 13.5 nm authority anchor，不能写入通用实现的固定常数。

最低 Gate：

| T3 项目 | Gate |
|---|---:|
| action vs independent modal sum | `<=1e-11` |
| recovery relative error | `<=1e-11` |
| cross-MPI relative error | `<=1e-12` |
| mode identity and normalization | exact/hash-bound |
| retained and bounded work | 按 mode count 分项报告 |
| swap | `0` |

同样只允许一次针对明确 implementation defect 的窄修复。第二次 formal identity 仍失败时停止，不进入 T4。

## 3.5 T4：owner-local slab/interface topology 与 transmission oracle

T4 只建立 topology、communication 和人工 transmission action，不运行完整 outer KSP。

必须实现并验证：

```text
z-slab partition
owner-local interface trace maps
restriction/prolongation adjoint
forward/backward communication plan
owned/ghost closure
Floquet phase exactly once
homogeneous/nonhomogeneous interface classification
```

允许的 transmission 仍严格限定为：

| 顺序 | 候选 | 使用边界 |
|---:|---|---|
| A | first-order impedance/Robin | 一般非均匀截面的默认低存储候选 |
| B | propagating + near-cutoff Floquet modal transmission | 只用于均匀接口或已通过 identity 的接口 |
| C | bounded rational/second-order 或 local spectral impedance | A/B 有正信号但不满足 Gate 时的唯一 fallback |

不得连续扫描 Robin 系数、Padé 阶数、mode 数、overlap 或 slab 数。每个候选必须使用任务书或实现文档中预先冻结的一组参数。

T4 的 p2/p3 fixture 必须证明：

```text
interface adjoint closure
MPI1/MPI2 ownership identity
phase-once
transmission action identity
no dense interface Schur
```

明确 implementation defect 允许一次窄修；第二次仍不闭合时停止，不进入 T5。

## 3.6 T5：bounded forward-backward sweep contraction

T5 是本批次第一个算法 Gate。必须使用同一 exact action、同一 norm 定义和同一冻结 source family 比较 A→B→C。

固定 source：

```text
physical RHS
gradient-dominated residual
curl-dominated residual
checkerboard/high-frequency residual
Task37-extra long-tail residual
```

long-tail residual 不得由文字或 compact residual 数字代替。允许迁移或转换的只能是一个最小、hash-bound 的残差向量 packet及其 canonical map；不得迁移旧 PC、old runner 或 Krylov history。当前 exact action 必须对该 packet完成 finite、norm、identity、MPI ownership 和 current-source closure 检查。

如果历史 residual raw packet不可取得、canonical map 不可证明，或 current action closure 失败，则 T5 分类为 `BLOCKED_BY_LONG_TAIL_RESIDUAL_AUTHORITY` 并停止。不得静默用 physical RHS 代替 long-tail Gate。

一次 forward+backward sweep 的 Gate：

| source | required contraction `rho` |
|---|---:|
| physical RHS | `<=0.60` |
| Task37-extra long-tail residual | `<=0.70` |
| checkerboard/high-frequency | `<=0.75` |
| gradient-dominated | `<=0.90` |
| curl-dominated | `<=0.90` |

同时要求：

```text
finite and deterministic
true action closure <= 1e-11
process-tree peak < 6 GB diagnostic ceiling
swap = 0
retained data approximately interface/volume linear
```

候选执行顺序为 A→B→C。每个候选只允许一次明确 implementation defect 修复后的 formal rerun。某个候选通过全部 source Gate 后，不再继续实现更复杂候选，只保留已完成候选的比较结果并进入 T6。

若 A/B/C 均不能使 long-tail residual达到 `rho<=0.70`，或通过需要无限增加 local inner steps、mode 数、overlap、coarse rank 或参数扫描，则停止 sweep 主线，不运行 T6。

## 3.7 T6：条件授权的 13.5 nm p6/h10 anchor

T6 只有在以下条件全部满足后才可开始：

```text
T1 contract pass
T2 exact action pass
T3 dynamic DtN pass
T4 topology/transmission identity pass
T5 at least one candidate passes all contraction Gates
preflight confirms swap=0 and process-tree hard stop is active
```

外层固定优先使用：

```text
right FGMRES
restart = 20
```

本 Review 不授权普通 ILU 参数扫描、restart 扫描、inner-iteration 扫描或 disk-backed Krylov 迁移。只有标准 restart-20 live-set 估计本身与任务书 300 MB Krylov 预算发生明确冲突时，必须停止并在 `response_v1.md` 报告，不得自行引入新的 storage architecture。

T6 分为两个连续子阶段。

### T6-S：20/100/200 步 screen

| checkpoint | true residual Gate |
|---:|---:|
| 20 | `<=0.40` |
| 100 | `<=0.05` |
| 200 | `<=0.005` |
| 150→200 improvement | `>=20%` |

在第一个明确失败 checkpoint 即可 controlled stop，不必继续消耗数百或数千步。不得用 KSP 内部 residual 代替 full explicit true residual。

### T6-F：条件完整求解与物理恢复

只有 T6-S 全部通过时，才允许继续到：

```text
final explicit true residual <= 1e-6
reported/true residual agreement
release unnecessary KSP/PC/work objects where possible
official E/H recovery
R/T/A and A_volume
diffraction channels
frozen direct-authority comparison
full-workflow process-tree peak
```

若本机无法生成同 SHA direct authority，可以使用冻结 direct authority，但必须逐项证明：

```text
physical_model_sha256
mesh/discretization identity
external mode/order inventory
observable definitions
selected field sampling identity
```

不能证明时，只能分类为 numerical result，不能分类为 complete physics qualification。

p6/h10 的战略资源 Gate仍为：

```text
completed full-workflow process-tree peak < 2,000,000,000 B
swap = 0
```

若数值 screen 通过，但实际峰值超过 2 GB且仍低于 12 GB、swap=0，允许完成这一次冻结 T6-F 以取得数值和根因证据；最终必须分类为 resource fail/diagnostic，不能称为 0.7 nm-scalable pass。达到 10 GB 时记录 warning；达到 12 GB、出现 swap 或 OOM 风险时立即 controlled stop。OOM kill不接受。

T6 完成、失败或受控停止后，均不得进入 T7。

---

# 4. 本批次明确禁止的迁移和研究

| 对象 | 本 Review 决定 |
|---|---|
| Task37-extra whole branch | forbidden |
| `benchmarks/run_task037_extra_*.py` giant runners | forbidden |
| W8–W18 shifted/range/nested PC | closed / forbidden |
| fixed 75D、390D、530D coarse/range | forbidden as production design |
| 84 个 882D factors 或 p4-complement factor campaign | not authorized |
| p4→p6 full-mesh transfer | deferred beyond this review |
| LOR-HX hierarchy | closed / do not migrate |
| disk-backed FGMRES | not authorized in this batch |
| Task039 Hybrid/QEP/Petrov/exact-side code | forbidden |
| global AIJ、global Schur、dense interface Schur | forbidden |
| growing slab LU/ILU factor store | forbidden |
| full 0.7 nm PDE | forbidden |
| T7 h-scaling | not authorized yet |
| T8 0.7 nm/2 TiB capacity audit | not authorized yet |
| master merge or ordinary default change | forbidden |

---

# 5. 全批次硬停止条件

任一条件发生时，Codex应保存现有证据、提交当前阶段的轻量结果、写 `response_v1.md` 并停止：

1. 当前 branch/base/upstream、canonical worktree 或 ABI identity 不正确；
2. `PETSc.ScalarType` 不是 `complex128`，或 MPI ranks 使用不同 ABI；
3. T2 action identity 经一次窄修后仍失败；
4. T3 DtN identity经一次窄修后仍失败；
5. T4 ownership、adjoint、phase-once或transmission identity经一次窄修后仍失败；
6. long-tail residual packet authority不可取得或无法映射到当前 canonical space；
7. A/B/C 均不能达到 T5 long-tail `rho<=0.70`；
8. 继续需要无界参数扫描、不断增加 coarse rank、inner steps、overlap或mode count；
9. 需要 global matrix、global Schur、dense interface matrix或随 h 增长的大 factor；
10. T6 任一 checkpoint失败，或 150→200 improvement小于20%；
11. process-tree达到12 GB、出现swap、termination失效或OOM风险；
12. 工作开始转向 Hybrid、RCWA、z-separable内部传播或0.7 nm full PDE；
13. ordinary default、Maxwell弱式、Floquet phase、DtN normalization、材料或物理Gate需要被改变才能继续。

硬停止只关闭当前实现 lane，不得扩大写成“Full3D iterative 永远不可能”。`response_v1.md` 必须指出被关闭的具体机制和下一种真正不同的候选架构。

---

# 6. 提交与推送规则

继续使用同一分支：

```text
codex/20260820-task38-extra-full3d-iterative-0p7nm
```

Codex拉取本 Review 后，应按阶段形成可解释提交，推荐顺序：

```text
feat(io): add opt-in full3d iterative dat contract
feat(maxwell): add generic full-space matrix-free Hcurl action
feat(maxwell): add dynamic streaming full-space DtN
feat(dd): add owner-local slab and interface topology
feat(dd): add bounded optimized-Schwarz transmissions and sweep
feat(runner): connect and screen full3d iterative anchor
evidence(task038-extra): record T1-T6 results
docs(task038-extra): respond to review v1 development batch
```

允许根据依赖把 T4 transmission 与 T5 sweep拆为两个提交；不允许把全部阶段压成一个不可审阅的大提交。每个阶段通过后可以普通 push，但无需停下来等待 ChatGPT。禁止 amend、force push、rebase到更新 master、创建新分支或混入无关清理。

活动期间若 `master` 发生无关更新，继续以冻结 base `438caf...` 开发，不得自行 merge/rebase。

---

# 7. 测试与证据要求

## 7.1 每个代码阶段

至少运行：

```text
focused unit tests
MPI1 fixture
MPI2 fixture where applicable
compileall
git diff --check
input validate-only and dry-run
Markdown fenced-math/table checks
compact JSON parse/checker
```

测试必须在该阶段最终代码后重跑。无 GitHub Actions 时只能报告本地测试，不能写 CI pass。

## 7.2 本批次 outcomes

本轮至少创建或更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/matrix_free_action.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/dynamic_dtn.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/sweep_oracle.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/full3d_iterative_anchor.md
docs/task038_extra_full3d_iterative_0p7nm/response_v1.md
```

如果在 T2–T5 提前停止，不适用的后续文件可以不创建，但 `response_v1.md` 必须用表格明确写 `not_run_by_gate`，不能留空或暗示通过。

若运行 T6 正式或受控重型 PDE，必须同步更新：

```text
docs/development_model_registry.md
```

并在 `response_v1.md` 中说明 `docs/development_progress.md` 尚未进入最终 T9 closeout，不能用一句临时状态冒充最终阶段回顾。

## 7.3 T6 provenance

任何 T6 formal attempt必须绑定：

```text
input_original.dat
resolved_config.json
run_manifest.json
input_sha256.txt
physical_model_sha256.txt
source_sha.txt
run_summary.json
Python/MPI/PETSc/DOLFINx/Basix ABI
PETSc ScalarType/IntType
MPI/thread identity
MemAvailable/swap/disk preflight
process-tree watchdog record
true residual checkpoints
artifact hashes
cleanup/termination status
```

重型场、网格、向量、matrix/factor和timeline继续放在 ignored artifact目录，不提交Git。

---

# 8. `response_v1.md` 必须回答的问题

本连续批次完成或提前停止后，`response_v1.md` 至少包括以下表格和结论：

1. branch、base、review-start HEAD、final HEAD、upstream、ahead/behind、worktree；
2. Python/MPI/PETSc/DOLFINx/Basix与complex128 ABI；
3. T1–T6 planned/run/pass/fail/not_run矩阵；
4. 实际从Task37-extra重构的文件、依赖和未迁移项；
5. T2 action identity、repeat、MPI和h10→h5 retained scaling；
6. T3 mode inventory、分类、batch/streaming、identity和bytes；
7. T4 slab/interface ownership、adjoint、phase和transmission identity；
8. T5 A/B/C 对五类 source 的 `rho`、wall、retained bytes、process-tree peak和停止原因；
9. T6 20/100/150/200/final true residual history，或准确的 `not_run_by_gate`；
10. T6 E/H、R/T/A、A_volume、channels、direct comparison和资源结果，或准确未运行边界；
11. measured、derived、predicted、failed、controlled_stop和not_run的区分；
12. changed files、tests、rendered-view检查和证据路径；
13. 是否建议下一轮进入T7/T8，以及该建议消除哪个0.7 nm blocker。

不得只写“所有测试通过”或“效果不好”；负结果必须列出实际值、Gate和具体机制。

---

# 9. 下一次审阅的裁决范围

下一次 ChatGPT review 将重点裁决：

```text
T2/T3是否真正成为当前master上的通用低内存精确算子
T4 interface/transmission是否保持arbitrary-3D边界
T5 sweep是否真实消除旧long-tail residual
T6是否同时满足数值、物理、资源和provenance Gate
是否授权T7 h-scaling
是否授权T8 0.7 nm / 2 TiB capacity audit
哪些代码可进入最终selective merge候选
```

在下一次 review 前，不得开始 T7、T8 或 T9，也不得合并 `master`。

---

# 10. 最终决定

```text
T0 = ACCEPTED
T1_T2_T3_T4_T5 = AUTHORIZED_AS_ONE_CONTINUOUS_BATCH
T6 = CONDITIONALLY_AUTHORIZED_AFTER_ALL_T1_TO_T5_GATES
STOP_AFTER_T6_OR_ANY_EARLIER_HARD_GATE
T7_T8_T9 = NOT_AUTHORIZED
MASTER_MERGE = FORBIDDEN
```

这意味着 Codex现在可以继续推进任务，不需要在每个 T 后等待审阅；但必须在 T6 完成、T6受控停止或任何更早的硬 Gate发生后，提交并推送同一分支，写 `response_v1.md`，然后停止等待下一轮审阅。
