# REVIEW REPORT V1：PARA-Task005 全 Slab Learned Local Inverse 阶段验收与 Audit-Storage 阻塞结论

## 0. 最终状态

```text
review = PARA-Task005 review_report_v1
branch = ChatGPT/20260715-para-task-neural-local-pc
review_status = PASS_WITH_MAJOR_QUALIFICATIONS
primary_classification = learned_pc_memory_budget_failure
root_cause = strict_audit_private_operator_storage_architecture
P0_baseline = PASS
P1_raw_capture_and_teacher = PASS_WITH_DISTRIBUTION_QUALIFICATION
P2_representative_local_quality = PASS_AS_SCREENING_SIGNAL_ONLY
P2_linear_low_rank_signal = POSITIVE
P2_nonlinear_advantage_over_linear = NOT_PROVEN
P2_model_only_runtime = POSITIVE
P2_end_to_end_runtime = NOT_TESTED
P2_model_storage_alone = PASS_FOR_HETEROGENEOUS_SMALLEST_ADMISSIBLE
P2_total_required_persistent_storage = FAIL
P3_to_P10 = NOT_RUN_BY_GATE
all_16_model_quality = NOT_TESTED
all_slab_shadow = NOT_RUN
true_no_hidden_ilu_learned_replacement = NOT_RUN
global_learned_pc_numeric_result = NOT_AVAILABLE
global_learned_pc_acceleration = NOT_PROVEN
memory_saving_result = NOT_PROVEN
same_operator_multi_rhs = NOT_RUN
expert_or_shared_compression = NOT_RUN
ordinary_default_changed = false
production_claim_allowed = false
h3_allowed = false
h2_allowed = false
branch_management = prohibited
master_operations = prohibited
```

PARA-Task005 到 P2 为止形成了三项可信的阶段性证据：

1. 16 个 slabs 的 raw-RHS sparse-LU teacher 数据可以在当前机器上顺序生成，teacher residual 达到约 `1e-14`；
2. 在冻结的 R4 代表集合 `{0,5,9,15}` 上，rank-64 线性低秩局部逆和若干 nonlinear reduced-coordinate 模型可以在独立于训练样本的真实 Krylov 样本上达到 per-slab admissibility；
3. 纯模型 owner-like four-slab batch 的 CPU/GPU 时间明显低于 P2 的 model-only 预算。

但当前结果没有进入 16-model 训练、all-slab shadow、active fallback、真正 no-hidden-ILU factor removal 或 global paired A/B。决定性早停来自冻结 Storage Gate：

```text
R4 private exact-audit CSR = 40.458 MiB / owner
smallest admissible heterogeneous linear models = 27.824 MiB / owner
total = 68.282 MiB / owner

memory-neutral limit = 33.670 MiB / owner
speed-first guard = 50.505 MiB / owner
```

因此，当前 primary classification `learned_pc_memory_budget_failure` 可以接受，但必须准确解释为：

```text
model-only storage is not the primary blocker;
the blocker is model + private exact-audit operator storage under the frozen safety contract.
```

不得把本结果表述为：

```text
NN local inverse lacks approximation capability;
NN inference is too slow;
all-slab learned PC has failed globally;
learned PC cannot replace ILU;
neural PC has been fully qualified.
```

---

# 1. 审阅范围

本轮审阅覆盖：

```text
docs/para_task005_comprehensive_all_slab_learned_pc/task.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/*
benchmarks/cases/094_comprehensive_all_slab_learned_pc/*
benchmarks/neural_pc/audit_task005_captures.py
benchmarks/neural_pc/build_all_slab_lu_teacher.py
benchmarks/neural_pc/build_lu_teacher_dataset.py
benchmarks/neural_pc/build_task005_ilu_holdout.py
benchmarks/neural_pc/screen_task005_linear.py
benchmarks/neural_pc/screen_task005_nonlinear.py
benchmarks/neural_pc/benchmark_task005_owner_batch.py
benchmarks/neural_pc/petsc_capture.py
benchmarks/run_workstation_iterative.py
src/solvers/lu_teacher_local_solver.py
src/solvers/physical_slab_two_level.py
src/geometry/mesh_builder_3d.py
src/test/test_15_stage4_hexa_mesh_spacing.py
src/test/test_35_lu_teacher_contract.py
src/test/test_45_para_task005_contract.py
```

冻结物理与求解框架为：

```text
wavelength = 13.5 nm
material = validated complex Si
geometry = 50 x 25 x 140 nm cell with 17 x 25 x 120 nm block
incidence = theta 80 deg, phi 0 deg, S polarization
finite element = p2 Nedelec hexahedral
mesh = h5, 44,698 FE DoF
periodicity = double Floquet
ports = 80 Fourier-DtN auxiliary unknowns
operator = exact condensed F-C H^-1D
outer = right FGMRES90, rtol 1e-6
physical slabs = 16, overlap 0.25
coarse = fixed 75D true-action Galerkin
smoother = current two-step + post-smooth
formal parallelism = MPI4, one thread per rank
```

本审阅不执行任何分支管理、master 操作、合并、PR 或 ordinary-default 决策。

---

# 2. 接受的结果

## 2.1 P0 clean baseline：接受

P0 在 clean source `f4c0600f352dd940b48e7bdd9b9494d5ebe9e4b0` 上得到：

```text
iterations = 852
solve = 97.252974 s
condensed operator applies = 2,584
one-level applies = 5,112
reported residual = 9.99509346e-7
condensed/full residual = 9.99509348e-7
R = 0.089021603824
T = 0.442588273937
A_volume = 0.468390120999
closure = -1.23937705e-9
external simultaneous worker peak = 1.612289 GiB
swap = 0
```

该结果满足 P0 的数值、R/T/A、memory 和 no-swap Gate。其身份仅为初始 sanity baseline；由于没有 finalist global candidate，Task005 没有进入三轮 paired baseline/candidate qualification。

## 2.2 P1 16-slab raw capture 与 sparse-LU teacher：接受

P1 完成：

```text
16/16 operator fingerprints stable
16/16 teacher datasets complete
1024 train + 256 validation + 256 holdout per slab
24,576 total raw RHS/teacher pairs
one factor at a time
maximum 64 RHS per SuperLU batch
all factors destroyed
swap = 0
```

teacher 质量：

```text
worst slab median rho_teacher = 5.905e-15
worst slab p95 rho_teacher = 7.469e-15
global max rho_teacher = 1.050e-14
```

这证明 one-factor/many-RHS teacher 合同可以可靠扩展到 16 slabs。将逐 RHS SuperLU 改为 bounded multi-RHS solve 是合理修正；被停止的慢路径保留为 rejected evidence，也符合研究记录要求。

## 2.3 Split overlap 与 exact/near-duplicate 审计：接受但有限定

审计确认：

```text
apply-index overlap = 0
exact RHS duplicates = 0
near-duplicate pairs at threshold 0.99999999 = 0
raw-only payload = true
ILU/current-PC correction leakage = absent
```

因此不存在直接样本重复或 teacher 泄漏。

但“来自四次 clean run”只能证明 execution provenance 独立，不等于 residual distribution 独立。T1/T2/V/H 使用同一 operator、同一物理 RHS、同一初值、同一确定性求解配置，并且四次运行都为 852 iterations。它们本质上是同一类 Krylov timeline 的错位抽样。该限制不否定 fixed-RHS screening，但禁止将其表述为跨 RHS、跨轨迹或真实泛化证据。

## 2.4 Lane A：线性低秩逆的 R4 局部正信号：接受

R4 `{0,5,9,15}` 上：

```text
rank 32: 2/4 admissible
rank 64: 4/4 admissible
rank 96: 4/4 admissible
rank 128: 4/4 admissible
```

rank-64 D0 的 median-rho ratio：

```text
slab 0 = 0.418
slab 5 = 0.917
slab 9 = 0.865
slab 15 = 0.436
```

p95 ratio：

```text
slab 0 = 0.684
slab 5 = 0.836
slab 9 = 0.777
slab 15 = 0.491
```

该结果支持：

```text
fixed local operator + real-Krylov training distribution
can be approximated by a low-rank linear inverse better than ILU on R4.
```

但需要注意，两个 5,248-DoF interior/interface slabs 的 rank-64 median 改善较弱，尤其 slab 5 仅改善约 8.3%。因此 rank-64 的身份是“通过最低 admissibility”，不是已达到 Task005 的 all-16 target local Gate。

## 2.5 Lane B：nonlinear NN 局部可行，但不优于线性基线

最佳被保留的 nonlinear screen：

```text
B_D0_R64_W128_D3_GELU_SKIP
R4 admissible = 4/4
median ratio = 0.409 / 0.910 / 0.847 / 0.422
p95 ratio = 0.665 / 0.822 / 0.742 / 0.473
```

它与 A_D0_R64 非常接近，没有形成清晰、稳定且足以抵消额外复杂度的质量优势。因此以下决策正确：

```text
Lane C not unlocked
Lane D not unlocked
linear low-rank remains the mandatory first baseline
```

本任务名称包含 neural/learned PC，但当前实际最强科学信号来自 linear low-rank inverse，而不是非线性网络。

## 2.6 D1 structured synthetic：接受为当前 recipe 的负结果

D1 没有改善 independent real-Krylov H：

```text
A D1 rank96 worse than A D0 rank96
B D1 rank64 worse than B D0 rank64
```

因此不将 D1 升级为 full recipe 是正确的。

但当前 synthetic generator 使用归一化数组下标 `coordinate = linspace(0,1,n)` 构造所谓 interface/boundary-localized error，而没有使用真实 Nedelec DoF 几何位置、entity 类型、材料标签、overlap 或 H(curl) 拓扑。故可接受结论只能是：

```text
this index-space synthetic recipe did not help.
```

不得外推为：

```text
physically structured synthetic exact pairs are generally useless.
```

## 2.7 Model-only runtime 与 owner-like batch：接受为 microkernel headroom

R4 four-slab grouped runtime：

```text
linear NumPy CPU mean = 4.097 ms
linear PyTorch CPU mean = 4.932 ms
linear PyTorch CUDA mean = 1.361 ms
nonlinear PyTorch CPU mean = 2.931 ms
nonlinear PyTorch CUDA mean = 1.343 ms
```

batch vs independent 等价性通过：

```text
linear error = 0
nonlinear worst recorded error = 1.298e-7 <= 2e-6
```

该结果证明：

```text
persistent owner-local model-only inference has sufficient raw compute headroom.
```

但这些 timing 不含：

```text
PETSc gather/scatter
RHS extraction
MPI wait
exact or proxy audit
H2D/D2H from actual local buffers
full PC integration
global solve
```

所以不能把它称为 `2.878 ms/slab end-to-end` 或 `11.514 ms/owner-batch end-to-end` 通过。

## 2.8 P2 Storage Gate 失败与早停：按冻结合同接受

最小 admissible heterogeneous storage：

```text
linear models/bases = 27.824 MiB / owner
nonlinear models/bases = 28.234 MiB / owner
private exact-audit CSR = 40.458 MiB / owner

linear total = 68.282 MiB / owner
nonlinear total = 68.692 MiB / owner
```

对比：

```text
memory-neutral = 33.670 MiB / owner
speed-first guard = 50.505 MiB / owner
```

Task005 明确规定 storage 包含 model、bases、persistent buffers 和 required audit/operator storage，也规定如果 P2 没有 candidate 同时满足 local、runtime、storage feasibility，应停止 full-16 training。因此 P3–P9 `not_run_by_gate` 的过程决定符合任务书。

---

# 3. 主要审阅发现

## 3.1 Major：Primary failure 是 audit-storage architecture，不是 model storage

最小 admissible model 本身：

```text
27.824 MiB / owner linear
28.234 MiB / owner nonlinear
```

均低于被移除 ILU 的 memory-neutral 参考：

```text
33.670 MiB / owner
```

真正使候选失败的是每 owner 40.458 MiB 的私有 complex128 CSR，用于 shadow every-call exact local residual audit。因而更准确的根因是：

```text
strict safety audit requires a second persistent representation of A_s,
which defeats the learned replacement storage budget.
```

该发现很有价值，因为它把下一步问题从“继续增大网络”明确转成：

```text
how to certify learned local outputs without retaining private full CSR copies.
```

## 3.2 Major：H holdout 已被用于候选筛选，不能再称为 untouched final holdout

`screen_task005_linear.py` 和 `screen_task005_nonlinear.py` 都：

```text
train on split == train
evaluate every candidate on split == holdout
select/reject candidate using holdout local residual
```

`validation` split 没有进入当前 Lane A/B selection、early stopping 或 model choice。

因此当前 H 的准确身份是：

```text
representative screening evaluation set
```

而不是：

```text
untouched final holdout
```

这不会使 P2 的相对比较失效，但会使报告中的“independent holdout local pass”偏乐观。后续恢复 P3 前必须二选一：

```text
A. use V for architecture/hyperparameter selection and reserve H untouched;
B. rename current H as screening set and generate a new untouched F split.
```

不得在已经观察 H 结果后仍把 H 用作最终无偏资格化数据。

## 3.3 Major：四个 split 是同一确定性 RHS/Krylov 轨迹的错位采样

四次 clean capture 全部为 852 iterations，配置和物理 RHS相同。固定 stride/offset 可以避免 exact duplicate，却不能产生真正独立的求解轨迹。

因此当前 P2 证明的是：

```text
interpolation/generalization across unseen apply indices
within one deterministic fixed-RHS solver distribution.
```

它没有证明：

```text
same-operator unseen RHS robustness
late-stage drift under a learned-active trajectory
cross-polarization reuse
generalization to a changed preconditioned residual distribution
```

尤其 learned model active 后，FGMRES trajectory 会偏离 ILU capture timeline。P4 shadow 原本用于检查这一 distribution shift，但未运行。因此当前 local positive signal仍需在线 shadow 才能完成闭环。

## 3.4 Major：采样合同没有完整实现 outer phase/norm stratification

任务书要求按：

```text
apply index
outer iteration window
residual norm
pre/post-smooth phase
```

分层采样并保存 metadata。

当前 `LocalSlabCapture` 只保存：

```text
rhs
apply_index
```

并通过固定 stride/offset 抽样；没有 outer iteration、pre/post phase 或 residual norm 字段。因此 P1 对“数量、raw-only、fingerprint、重复检测”的 Gate通过，但对“完整 phase/norm coverage contract”只能判定为：

```text
INCOMPLETE_METADATA / NOT DIRECTLY AUDITABLE
```

后续不得仅凭 stride 分布声称已覆盖 early/middle/late、restart 或 pre/post-smooth。

## 3.5 Moderate：R4 local pass 不能外推为 16/16 admissible

Task005 在 Storage Gate 前只训练和评估 R4。其余 12 个 slabs 只有 teacher，没有模型。

因此目前不存在：

```text
Uniform-16 candidate
Heterogeneous-best-16 candidate
16/16 per-slab admissibility
14/16 target local Gate
all-16 storage ledger
all-16 online distribution evidence
```

`local quality positive` 必须始终带上 `R4 representative screening` 限定。

## 3.6 Moderate：nonlinear conclusion 只有单 seed screen

P2 candidate 允许单个固定 seed；finalist才要求三 seeds。由于没有 finalist，流程上合规。

但“nonlinear没有优于linear”当前是 screening conclusion，不是多 seed statistical conclusion。未来若 audit blocker解除并考虑 nonlinear finalist，应至少对最小可行 linear 与 nonlinear候选进行三 seed重复，再决定是否删除 nonlinear lane。

## 3.7 Moderate：Runtime 使用的是 virtual owner-like R4，而非 PETSc/MPI owner integration

R4 `{0,5,9,15}` 恰好包含两个 3,670-DoF slab和两个 5,248-DoF slab，与每个正式 owner 的 size-class composition相似，因此适合作为 model compute envelope。

但它并没有：

```text
接入 DistributedPhysicalSlabSmoother
从 PETSc Vec gather RHS
执行真正 rank-local packing
测量 MPI reverse scatter/wait
在 complex PETSc process 中长期运行 CUDA
```

故其身份必须保持 model-only owner-like batch，不得称为正式 owner runtime。

## 3.8 Moderate：`changed_files.md` 不完整

仓库实际 Task005 变更还包含但当前 `changed_files.md` 未列出的关键文件，例如：

```text
src/geometry/mesh_builder_3d.py
src/test/test_15_stage4_hexa_mesh_spacing.py
benchmarks/neural_pc/petsc_capture.py
benchmarks/run_workstation_iterative.py
benchmarks/run_task031_memory_forensics.py
```

其中 mesh builder新增 explicit research partition policy，capture路径使用：

```text
MYFENICS_CELL_PARTITION_POLICY=contiguous
```

该修改用于提高 capture/operator identity可重复性，并且默认环境变量未设置时不改变普通 create-box policy；但它仍属于 Task005 provenance，应进入 changed-files 和 rationale。

执行者 response_v1 必须补全实际 tracked diff，而不能只列核心 ML scripts。

## 3.9 Moderate：缺少集中验证报告

当前 outcomes 没有像 Task003/004 那样集中记录：

```text
complete src/test result
Task005 targeted test count
MPI test result
Ruff
compileall
git diff --check
heavy artifact ignore audit
```

这不等于这些检查一定没有运行，但审阅不能把未记录的检查判为 PASS。response_v1 应新增 validation/provenance 小节，绑定具体 clean SHA和命令结果。

## 3.10 Minor：分类名称正确，但 secondary finding必须更精确

推荐最终表述：

```text
primary = learned_pc_memory_budget_failure
secondary = R4 fixed-operator local-quality and model-only runtime positive
root cause = private exact-audit operator storage
```

不要只写：

```text
local quality and runtime positive
```

因为它容易被理解成 16-slab 或 end-to-end runtime 已通过。

---

# 4. Task005 当前真正证明了什么

## 4.1 已证明

```text
16-slab raw-RHS LU teacher generation is feasible and accurate.
Low-rank linear inverse can outperform ILU on four representative slabs.
Small nonlinear reduced models are feasible but offer no clear gain over linear.
Persistent CPU/GPU model-only inference has substantial timing headroom.
The smallest admissible model storage alone can fit within removed-ILU storage.
The current every-call exact-audit implementation breaks the total storage budget.
```

## 4.2 尚未证明

```text
16/16 learned models are admissible.
Learned-active residual distributions remain in-domain.
All-slab shadow has zero harmful outputs.
A strict proxy has zero false accept.
Periodic exact audit detects drift.
True learned backend can run without ILU factors/fallback.
Learned profile converges globally.
Learned profile retains >=60% of exact-oracle benefit.
Learned profile accelerates solve by >=20%.
Learned profile is memory-neutral in external RSS.
Same-operator multi-RHS reuse works.
Expert/shared compression works.
NN PC has been comprehensively qualified.
```

因此用户最初提出的“彻底证明 NN PC 能力”尚未完成。Task005 应被视为一次成功的前置筛选与架构阻塞发现，而不是完整 learned-PC qualification。

---

# 5. 对下一步的强制建议

## 5.1 不要立即扩大网络或继续 P3 full-16 training

当前 blocker与网络容量无关。继续训练 12 个 slabs只会生成无法进入 shadow/active 的 checkpoint，并增加 sunk cost。

在恢复 Task005 P3 前，应建立独立的 audit-storage qualification，目标为：

```text
strict safety evidence
without persistent private full local CSR copies.
```

## 5.2 推荐新的 audit architecture lanes

### Lane A：借用已有 local operator storage

研究是否可以在 shadow阶段保留/借用 smoother setup 中已有的 local PETSc submatrix或其他唯一 operator representation，而不是同时保存：

```text
PETSc local matrix
+ portable CSR copy
```

必须报告真实 retained bytes，不能只改变对象名称。

### Lane B：periodic exact audit + strict cheap proxy

允许：

```text
exact audit on first N applies
every K=16/32 applies
restart boundaries
anomaly-triggered applies
deterministic random schedule
```

其余调用使用严格 proxy。进入资格化前必须满足：

```text
zero false accept on V + online shadow
all injected harmful outputs detected
injected slow drift detected within bounded interval
proxy/checkpoint/operator corruption fails closed
```

### Lane C：sketched local residual certificate

可以研究小尺寸 randomized/sketched certificate，例如预计算局部 sketch operator，但必须：

- 将 sketch storage计入预算；
- 明确概率性保证而非伪称 exact；
- 对所有已知 harmful/injected cases零 false accept；
- 仍保留 periodic exact audit；
- final global true residual永远精确计算。

### Lane D：共享或流式 exact-audit workspace

研究是否能按 owner复用单个 audit workspace，或只在 audit时临时 materialize operator，不让四个 full CSR同时常驻。必须同时测量 allocation、wall time、RSS和MPI wait，不能以频繁重建换取不可接受的运行开销。

## 5.3 修复数据资格化合同

恢复模型研究前必须：

1. 使用 V 进行 candidate selection；
2. 保留 H 完全未触碰，或新建独立 F final set；
3. capture记录 outer iteration、pre/post phase、restart window和residual norm；
4. 至少加入一个 same-operator不同 RHS/线性组合的独立 raw trajectory，用于判断固定 operator下的 RHS coverage；
5. synthetic generator改用真实 DoF坐标、entity/material/overlap metadata，而不是数组下标。

## 5.4 Audit blocker解除后的恢复点

满足 audit-storage Gate后，可以从：

```text
P3 train/select 16 independent models
```

恢复，但推荐优先顺序为：

```text
heterogeneous smallest-admissible linear
-> uniform rank64 linear
-> nonlinear only if multi-seed validation shows real advantage
```

理由是当前证据显示 linear和nonlinear质量接近，而linear更确定、更容易审计和部署。

---

# 6. Required response_v1 修正项

执行者应在同一 Task005 目录新增 `response_v1.md`，至少完成：

1. 接受 primary classification与 root-cause限定；
2. 将 H 从“untouched holdout”改为“screening holdout”，或规划新 final split；
3. 明确 V 当前未用于候选选择；
4. 将四次 clean run 描述为 execution-independent but distribution-correlated；
5. 明确采样只使用 stride/offset，尚无 phase/norm metadata；
6. 将 D1 结论限定为 index-space synthetic recipe negative；
7. 补全 `changed_files.md`；
8. 添加完整测试、lint、compile和diff-check证据；
9. 不运行 P3–P10；
10. 若继续，先建立独立 audit-storage task或经用户明确批准修改 Task005 Gate。

这些是文档与下一阶段治理修正，不要求重跑已完成的 P0/P1/P2 heavy evidence。

---

# 7. 最终处置

```text
PARA-Task005 process through P2 = ACCEPTED_WITH_MAJOR_QUALIFICATIONS
P0 baseline = ACCEPTED
P1 teacher/data integrity = ACCEPTED_WITH_DISTRIBUTION_LIMITATION
P2 R4 linear local signal = ACCEPTED
P2 R4 nonlinear signal = ACCEPTED_BUT_NO_ADVANTAGE_OVER_LINEAR
P2 model-only runtime = ACCEPTED_AS_MICROBENCHMARK_ONLY
P2 model storage alone = FEASIBLE
P2 total storage with private exact-audit CSR = FAILED
P3-P10 stop = CORRECT_BY_FROZEN_GATE
all-slab learned-PC capability = NOT YET TESTED
neural acceleration claim = PROHIBITED
memory-saving claim = PROHIBITED
ordinary default = UNCHANGED
h3/h2 = LOCKED
next research priority = audit_storage_architecture
branch/master operations = OUT_OF_SCOPE_AND_PROHIBITED
```

最终科学判断：

```text
Task004 证明了 all-slab local inverse具有全局谱价值；
Task005 P2 证明了 learned approximation和model-only compute具有初步可行性；
当前阻塞不是模型本身，而是严格安全审计所需的重复operator storage。
```

因此 local-inverse learning主路线不应关闭，但也不能继续盲目扩大模型。只有解决 audit-storage blocker并修复数据资格化语义后，才有资格恢复16-model、shadow、factor removal和global A/B。