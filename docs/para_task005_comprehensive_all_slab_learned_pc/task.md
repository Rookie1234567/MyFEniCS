# PARA-Task005：Comprehensive All-Slab Learned Local Inverse Capability and Engineering Qualification

## 0. 任务身份

```text
task = PARA-Task005
name = Comprehensive All-Slab Learned Local Inverse Capability and Engineering Qualification
status = planned / research-only continuation
execution_branch = ChatGPT/20260715-para-task-neural-local-pc
predecessor = PARA-Task004
predecessor_review = docs/para_task004_full_16_slab_exact_oracle/review_report_v1.md
remote_repository = Rookie1234567/MyFEniCS
reference_wavelength = 13.5 nm
reference_geometry = current validated full-3D periodic Si block grating
reference_discretization = p2 Nedelec hexahedral FEM
reference_parallelism = MPI4 for formal h5 A/B
ordinary_default_changed = false
production_claim_allowed = false before final review
model_training_allowed = offline only
online_training_allowed = false
h3_allowed = false
h2_allowed = false
branch_management = prohibited by explicit user instruction
master_operations = prohibited by explicit user instruction
```

### 0.1 分支操作禁令

本任务只允许在现有：

```text
ChatGPT/20260715-para-task-neural-local-pc
```

分支中新增或修改 Task005 相关代码、测试、benchmark 和文档。不得：

- 创建、切换、移动、重命名或删除分支；
- merge、rebase、cherry-pick、reset 或同步其他分支；
- pull、push、提交或合并到 `master`；
- 开 PR；
- 因当前分支与其他分支存在差异而主动改变分支历史；
- 将本任务解释为 production merge preparation；
- 修改 ordinary solver default；
- 自动运行 h3/h2。

若当前分支缺少其他路线的新基础设施，应在 outcomes 中记录限制，不得擅自同步。

---

# 1. 为什么启动本任务

PARA-Task004 已完成真正的 no-hidden-ILU exact-local-inverse oracle：

```text
same-run shifted-F ILU baseline:
iterations = 861
solve = 89.190 s
condensed operator applies = 2,603
one-level applies = 5,166
external worker peak = 1.607 GiB

G16 exact local inverse + current two-step smoother:
iterations = 566
iteration reduction = 34.2625%
condensed operator applies = 1,712
action reduction = 34.23%
one-level applies = 3,396
solve = 174.429 s
external worker peak = 3.275 GiB
```

G16 exact profile满足：

```text
exact backend count = 16
ILU factor constructed count = 0
stored ILU factor nnz = 0
ILU apply count = 0
hidden fallback count = 0
```

这证明：

```text
全部 16 个 local inverses 同时增强时，
当前 16-slab Schwarz + 75D coarse + right FGMRES90 架构
存在约 34% 的 outer iteration / operator-action 理论收益。
```

Task004 同时证明：

```text
G16 one-step smoother 在 1200 步仍未达到 1e-6，
operator actions 反而增加约 39%。
```

因此 Task005 不再问“local inverse是否有全局价值”，而要彻底回答：

```text
能否在严格 runtime、memory、robustness 和 no-hidden-ILU 约束下，
让全部 16 个 learned local inverses 保留足够的 exact-oracle 谱收益，
并真正实现至少 20% 的 h5 global solve wall-time acceleration？
```

本任务不是一次单模型训练，也不能以 training loss、单 slab rho 或一次 noisy solve 结束。它必须形成从 teacher、模型能力、runtime、MPI、factor removal、重复 A/B 到同算子多 RHS 复用的完整证据链。

---

# 2. “彻底证明 NN PC 能力”在本任务中的含义

本任务将能力拆成六个独立问题。

## 2.1 局部逼近能力

对每个 slab `s=0,...,15`：

```math
A_s z_s^* = r_s,
```

模型只接收 raw local residual：

```text
r_s -> z_s^learned ≈ A_s^{-1} r_s
```

必须在 independent real-Krylov holdout 上证明 learned local residual 优于当前 slab ILU，而不是只在训练集上拟合 teacher correction。

## 2.2 全 slab 协同能力

Task004 表明少量 slab replacement 不能代表 G16。Task005 必须同时激活 16 个 learned backends，验证其是否保留 exact G16 的整体谱收益。

## 2.3 工程运行能力

模型必须在以下 Task004 预算内运行：

```text
end-to-end independent slab budget <= 2.878 ms/slab call
end-to-end owner batch budget <= 11.514 ms/four-slab owner batch
memory-neutral storage <= 33.670 MiB/owner rank
```

预算包括模型、basis、persistent buffer、必要的 operator/audit storage 和设备 staging，不得只报告纯 neural kernel 时间。

## 2.4 真替代能力

最终 qualification profile 必须：

```text
16 learned backends active
16 ILU factors not constructed
ILU apply count = 0
hidden fallback count = 0
current two-step smoother retained
```

诊断性 shadow/fallback 可以先运行，但不能用于 factor-removal、memory saving 或正式 learned replacement 声明。

## 2.5 稳健性与复用能力

必须完成：

- independent train/validation/holdout；
- 至少三轮 clean paired baseline/candidate A/B；
- 同一 operator 下不同 RHS 的复用验证；
- 不同训练 seed 的 finalist 稳定性；
- failure injection 与 fail-closed 测试。

## 2.6 模型组织能力

先验证：

```text
16 independent slab-specific models
```

这是 fixed-operator engineering upper bound。只有其 full Gate 通过，才允许比较：

```text
3 physical expert classes
shared trunk + slab-specific adapters
```

不得直接用 shared model 的失败否定 learned local inverse 路线。

---

# 3. 开始前必须读取与维护

## 3.1 必须完整读取

```text
docs/repository_work_principles.md
docs/task_retrospective_standard.md
docs/solver_guide.md
docs/iterative_solver_ports.md
docs/architecture_overview.md
notes/theory/iterative_solver_and_preconditioner.md
notes/reference/physical_slab_two_level_pc.md

docs/para_task001_neural_local_pc_acceleration/task.md
docs/para_task001_neural_local_pc_acceleration/outcomes/summary.md
docs/para_task001_neural_local_pc_acceleration/review_report_v1.md

docs/para_task002_batched_neural_smoother_acceleration/task.md
docs/para_task002_batched_neural_smoother_acceleration/outcomes/summary.md
docs/para_task002_batched_neural_smoother_acceleration/review_report_v1.md

docs/para_task003_lu_teacher_nn_only_local_inverse/task.md
docs/para_task003_lu_teacher_nn_only_local_inverse/outcomes/summary.md
docs/para_task003_lu_teacher_nn_only_local_inverse/review_report_v1.md

docs/para_task004_full_16_slab_exact_oracle/task.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/summary.md
docs/para_task004_full_16_slab_exact_oracle/review_report_v1.md

benchmarks/cases/090_neural_local_pc_acceleration/README.md
benchmarks/cases/091_batched_neural_smoother_acceleration/README.md
benchmarks/cases/092_lu_teacher_nn_only_local_inverse/README.md
benchmarks/cases/093_full_16_slab_exact_oracle/README.md

src/solvers/local_slab_solver.py
src/solvers/neural_local_pc.py
src/solvers/batched_reduced_smoother.py
src/solvers/lu_teacher_local_solver.py
src/solvers/physical_slab_two_level.py
benchmarks/neural_pc/data_contract.py
benchmarks/neural_pc/petsc_capture.py
benchmarks/neural_pc/build_lu_teacher_dataset.py
benchmarks/neural_pc/benchmark_all_slab_exact_oracle.py
benchmarks/run_workstation_iterative.py
benchmarks/run_task031_memory_forensics.py
```

若上述 notes 路径在当前分支名称不同，应搜索并记录实际文件，不得同步其他分支。

## 3.2 必须维护的交付物

```text
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/summary.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/changed_files.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/experiment_matrix.csv
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/data_and_teacher_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/local_quality_by_slab.csv
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/model_ablation.csv
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/runtime_backend_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/owner_batch_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/shadow_safety_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/global_ab.csv
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/robustness_matrix.csv
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/memory_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/amortization_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/model_and_dataset_provenance.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/decision.md
docs/development_progress.md
benchmarks/cases/094_comprehensive_all_slab_learned_pc/
```

## 3.3 Heavy artifacts

重型 artifacts 必须放在：

```text
benchmarks/artifacts/cases/094/
```

并保持 Git ignored。不得提交：

- raw local CSR matrices；
- LU factors；
- raw RHS/teacher target arrays；
- large checkpoints；
- full optimizer states；
- profiler traces；
- raw MPI stdout/stderr；
- full field/HDF5/XDMF/VTU；
- complete Krylov histories。

Git 中只提交轻量配置、manifest、SHA-256、CSV/JSON 摘要、测试 fixture 和文档。

---

# 4. 冻结物理与全局求解器

## 4.1 Primary h5 target

第一阶段固定：

```text
wavelength = 13.5 nm
material = current validated complex Si optical constant
periodic cell = 50 x 25 x 140 nm
Si block = 17 x 25 x 120 nm
incidence = theta=80 deg, phi=0 deg, S polarization
periodicity = double Floquet in x/y
ports = current 80 Fourier-DtN auxiliary unknowns
finite element = p2 Nedelec hexahedral
mesh = h5
FE DoF = 44,698
formal MPI = 4 ranks
OMP/BLAS threads = 1
```

不得同时改变：

- 波长、材料、几何、角度或主验证偏振；
- DtN mode 定义；
- exact condensed operator action；
- 16-slab partition、overlap 0.25、weights 和 owner assignment；
- fixed 75D true-action Galerkin coarse；
- right FGMRES90、rtol `1e-6`；
- post-smooth；
- official R/T/A 与 volume absorption；
- memory sampler 与 monitor stride。

## 4.2 Two-step smoother 必须保留

正式 learned profile保持：

```text
smoother_iterations = 2
post_smooth = current frozen setting
```

Task004 G16 one-step 是完整负结果，不得在 Task005 作为默认候选重新包装。

## 4.3 Same-run references

Task004 历史数字只用于 sanity：

```text
ILU baseline iterations = 861
ILU baseline solve = 89.190 s
G16 exact iterations = 566
G16 exact action reduction = 34.23%
```

Task005 正式性能声明必须在 clean finalist implementation HEAD 上重新成对运行 baseline 与 candidate。不得直接用 Task004 wall time替代 Task005 baseline。

---

# 5. 核心研究问题

本任务至少必须回答：

1. 16 个 raw-RHS LU-teacher datasets 能否以可控资源生成并保持严格独立？
2. 固定 local operator 下，learned linear inverse 与 nonlinear NN 谁更准确、谁更快？
3. real-Krylov-only 数据与 real+structured-synthetic 数据谁更稳健？
4. 16 个 slabs 中最难学习的是哪些，困难是否与 size、boundary、material fraction 或 residual distribution相关？
5. 每个 slab 独立 inference 能否满足 2.878 ms end-to-end 预算？
6. owner-local 4-slab batch 能否满足 11.514 ms 预算并减少 Python/GPU 调度？
7. CPU BLAS、PyTorch CPU、single-process GPU 中哪条 runtime最优？
8. all-slab shadow 是否显示 harmful local outputs、out-of-distribution residual 或 slab concentration？
9. diagnostic ILU fallback fraction 是否足够低，能否进入 no-hidden-ILU？
10. 16-model true factor-removal profile 是否保持 full residual 与 R/T/A？
11. learned profile 能保留 exact oracle 的多少 iteration benefit？
12. 是否真正获得至少 20% solve wall-time reduction？
13. model+basis+buffers 是否满足 memory-neutral 或预先冻结的 speed-first memory guard？
14. 三轮 paired A/B 是否重复得到相同结论？
15. S-trained models 对同 operator 的 P-polarized/unseen RHS 是否可复用？
16. 16 independent 成功后，3 experts 或 shared trunk 能否压缩存储而不丢失全局收益？
17. teacher+training/setup 成本在 1、10、100、1000 次 RHS solve 下如何摊销？
18. 最终应继续 fixed-operator learned PC、进入跨参数 operator learning，还是转向 coarse/deflation/global modes？

---

# 6. 数据与 Teacher 合同

## 6.1 Raw capture 独立性

必须从独立 clean baseline runs 采集全部 16 slabs 的 raw local RHS。建议最低规模：

```text
T1 train capture: 512 samples/slab
T2 train capture: 512 samples/slab
V validation capture: 256 samples/slab
H holdout capture: 256 samples/slab
```

即主数据至少：

```text
1,024 train + 256 validation + 256 holdout per slab
16 slabs
```

采集必须覆盖：

- early / middle / late outer iterations；
- FGMRES restart 前后；
- residual norm 不同数量级；
- pre-smooth 与 post-smooth 调用；
- 每个 owner rank 的全部 local slabs。

不得只取连续前若干样本。必须按 apply index、outer iteration window 和 residual norm 分层抽样，并在 manifest 中保存规则。

每个 raw sample 只允许包含：

```text
rhs
slab_id
apply_index
outer_iteration / phase metadata if available
norm metadata
source run identity
```

不得包含：

```text
ILU output
ILU residual
current PC correction
Task001/002 correction
teacher target from another split
```

## 6.2 Teacher labels

对每个 slab：

```text
build/fetch one fixed A_s
-> sparse LU factorize once
-> solve all RHS in bounded batches
-> verify teacher residuals
-> save targets + manifest + checksum
-> destroy factor
-> move to next slab
```

不得同时常驻 16 个 teacher LU factors。

Teacher Gate：

```text
all finite
median rho_teacher <= 1e-11
p95 rho_teacher <= 1e-10
max rho_teacher <= 1e-9
operator fingerprint exact match
factor destroyed after dataset generation
swap in/out = 0
```

每个 slab 必须记录：

- shape / matrix nnz；
- fingerprint；
- ordering / pivot；
- factorization time；
- L/U nnz 与 fill ratio；
- explicit factor storage；
- per-RHS solve mean/p95/max；
- RSS before/after/destroy；
- dataset bytes；
- teacher residual统计。

## 6.3 Data recipe ablation

在 representative slabs 上至少比较：

```text
D0 = real Krylov only
D1 = real Krylov + structured synthetic exact pairs
```

structured synthetic pair可由：

```text
choose physically structured error e_s
r_s = A_s e_s
label = e_s
```

产生，不需要 LU solve，但必须使用真实 `A_s` action。结构至少覆盖：

- smooth low-frequency combinations；
- interface-localized modes；
- boundary/overlap-localized modes；
- high-frequency/randomized components；
- POD combinations from real residual/error coordinates；
- multiple amplitude scales。

D1 只有在 independent real-Krylov validation 上改善最差 slab，才允许成为 full 16 recipe。不得用 synthetic validation 代替 real holdout。

## 6.4 Hard-example augmentation

允许最多一次受控 hard-example round：

```text
shadow run identifies harmful/OOD residuals
-> save bounded raw RHS only
-> exact teacher offline
-> retrain once
```

每个 slab新增样本上限建议为 256。不得无限循环“跑失败 -> 加数据 -> 重训”直到出现正结果。

## 6.5 Leakage 与 provenance

Train/validation/holdout 必须来自不同 solver records或明确不重叠的时间段，并记录：

```text
source commit SHA
branch
clean/dirty status
operator fingerprint
sample SHA-256
split seed
sampling rule
teacher manifest SHA-256
```

任何 exact duplicate RHS、近重复 sample 或 split overlap 必须检测并报告。

---

# 7. 模型研究 Lanes

## 7.1 Representative screening slabs

模型 family 与 data recipe 第一轮只在预先冻结的代表集合筛选：

```text
R4 = {0, 5, 9, 15}
```

理由：覆盖上下边界、内部、光栅/界面附近与不同 size class。若实际物理 metadata 表明该集合不能覆盖关键 operator class，执行者必须在训练前提交轻量 rationale 并冻结替代集合；不得根据模型结果事后改选。

## 7.2 Lane A：Learned linear / low-rank inverse（强制基线）

固定 `A_s` 下，目标映射本质线性。必须测试：

```text
c = U_s^H r_s
d = W_s c
z = V_s d
```

候选 rank 至少包括：

```text
32, 64, 96, 128
```

允许：

- POD/SVD basis；
- ridge regression；
- reduced Galerkin inverse；
- low-rank plus diagonal scaling；
- complex128 或资格化 complex64 runtime；
- BLAS batched action。

要求：

```text
linearity error <= 1e-11
determinism error <= 1e-13
batch vs independent <= 1e-12
no Python loop over DoFs
persistent model/buffers
```

## 7.3 Lane B：Independent nonlinear NN

每个 slab 可训练独立 reduced-coordinate NN：

```text
r_s -> slab encoder -> reduced coordinates
-> small MLP/residual network
-> slab decoder -> z_s
```

representative screen 至少比较：

- reduced rank `32/64/96`；
- hidden width `64/128`；
- depth `2/3`；
- activation至少一种平滑 activation 与一种 ReLU-like activation；
- direct map 与 residual/skip map；
- correction loss + equation residual loss。

建议 loss：

```math
L_corr = ||z_learned-z_teacher||^2/(||z_teacher||^2+delta)
```

```math
L_res = ||A_s z_learned-r_s||^2/(||r_s||^2+delta)
```

可以加入 norm/phase regularization，但不得只优化 training MSE。

正式 runtime必须冻结权重，不得在线更新。

## 7.4 Lane C：Linear base + nonlinear reduced residual（条件）

只有 Lane B 明确优于 Lane A但运行成本接近预算时，允许测试：

```text
z = z_linear + V_s N_s(U_s^H r_s)
```

不得重新引入 ILU。该 lane 的目标是用很小 nonlinear residual补足 linear inverse的困难模态。

## 7.5 Lane D：Structured sparse/message-passing model（严格条件）

只有 representative slabs 中：

```text
Lane A/B/C 均无法达到 local quality Gate，
但 exact oracle仍显示该 slab class对 G16必要，
且资源预算允许
```

时，才允许做一个有界 structured model prototype。不得无限扩展 GNN 架构搜索。该 lane 最多一个预先记录的 architecture、两个容量点，并必须使用 local graph/sparsity，不得输入完整 global vector。

## 7.6 Candidate 数量控制

Representative screen 全部候选配置建议不超过 16 组。每个配置至少固定 seed并记录；finalist至少使用 3 个 training seeds重复。

不得通过无限超参数搜索或只报告最佳 seed制造正结果。

---

# 8. 16-Model Upper-Bound Profiles

## 8.1 Uniform-16 profile

使用统一 family、rank、hidden policy 和 data recipe训练 16 个模型，仅允许输入/输出 basis与 slab大小不同。

目的：获得可解释、可维护的统一 policy。

## 8.2 Heterogeneous-best-16 profile

每个 slab从相同、预先冻结的候选 family pool中选择满足 local/runtime/storage Gate的最佳模型：

```text
model_s = best validated admissible candidate for slab s
```

选择评分必须在运行 global solve 前冻结，例如：

```text
primary = holdout local residual
secondary = end-to-end runtime
tertiary = storage
```

不得根据 global solve结果重新挑选 slab模型。

该 profile 是 fixed-operator learned-PC 能力上限，不是通用模型。

## 8.3 Independent profile 成功前禁止压缩

只有 Uniform-16 或 Heterogeneous-best-16 至少一个通过 true factor-removal full Gate，才允许进入 expert/shared模型。

---

# 9. Local Quality 与 Runtime Gate

## 9.1 Local residual定义

```math
rho_s(z)=||A_s z-r_s||/||r_s||.
```

对同一 holdout RHS必须比较：

```text
rho_teacher
rho_ILU
rho_learned
correction relative error to teacher
```

## 9.2 Per-slab admissibility Gate

每个 slab均必须：

```text
all outputs finite
determinism pass
operator/checkpoint fingerprint pass
holdout contains independent real-Krylov RHS
median rho_learned <= median rho_ILU
p95 rho_learned <= 1.05 * p95 rho_ILU
p95 absolute rho_learned < 0.95
no catastrophic sample rho >= 2.0
```

任一 slab不满足时，不能进入 all-slab active candidate。

## 9.3 Target local Gate

全 16 candidate建议达到：

```text
at least 14/16 slabs:
median rho_learned <= 0.75 * median rho_ILU
p95 rho_learned <= 0.85 * p95 rho_ILU

all 16 slabs:
median ratio <= 0.90
p95 ratio <= 1.05
```

Strong local target：

```text
geometric mean median-rho ratio <= 0.50
max slab median-rho ratio <= 0.75
```

## 9.4 Model-only runtime headroom

为 end-to-end 预算留出 gather/scatter、packing和audit空间，模型纯 inference建议先满足：

```text
independent inference <= 1.8 ms/slab mean
owner-batch inference <= 7.2 ms/four-slab batch mean
```

这不是最终成功条件，最终条件仍为：

```text
end-to-end learned local path <= 2.878 ms/slab
or <= 11.514 ms/owner batch
```

同时报告 median/p95/max，不得只报告最佳 GPU kernel。

## 9.5 Storage Gate

Primary memory-neutral target：

```text
model + bases + persistent buffers + required audit/operator storage
<= 33.670 MiB per owner rank
<= 134.678 MiB global
```

允许一个预先冻结的 speed-first exploratory guard：

```text
learned persistent storage <= 1.50 * removed ILU estimate
external worker peak <= 1.10 * same-run baseline
```

但只有 memory-neutral profile可以声称“替代 ILU 且不增加预条件器存储”。

---

# 10. Runtime Backend 与 Owner Batching

## 10.1 必须比较的 runtime

至少比较：

```text
NumPy/SciPy/BLAS CPU
PyTorch CPU
PyTorch CUDA single-process persistent runtime
```

若某环境无法安全与 complex PETSc共存，应记录限制；不得每次迭代启动 subprocess或通过文件交换调用 GPU。

## 10.2 Owner-local batch

MPI4 下每个 owner通常负责 4 个 slabs。应实现：

```text
collect four local RHS on owner
-> slab-specific encoders
-> batched/shared or bucketed reduced action
-> slab-specific decoders
-> four corrections
```

允许 slab尺寸不同，可采用：

- reduced-coordinate bucketing；
- fixed-rank padding + mask；
- grouped GEMM；
- per-slab basis + packed reduced trunk；
- persistent device/host buffers。

不得把完整 global PETSc vector送入 GPU。

## 10.3 必须拆分的时间

```text
gather/scatter
RHS extraction
normalization
batch packing
H2D
encoder
linear map / MLP
decoder
D2H
synchronization
local operator audit
proxy audit
MPI wait
coarse/outer non-local time
```

每项至少记录 count、mean、median、p95、max。

## 10.4 Allocation 与稳定性

正式 runtime要求：

- model/checkpoint只加载一次；
- persistent staging buffers；
- no per-call large allocation；
- repeated apply无RSS持续增长；
- GPU peak allocated/reserved可审计；
- destroy后device/host对象不可继续调用。

---

# 11. Safety、Shadow 与 Audit

## 11.1 Shadow mode

第一阶段 all-slab shadow：

```text
compute learned output for all 16 slabs
compute exact local residual rho_learned every call
compute ILU output/rho for comparison
write back ILU only
```

必须记录：

- learned vs ILU rho by slab；
- accepted/harmful/OOD count；
- output norm distribution；
- runtime budget；
- rank wait；
- residual phase/iteration分布；
- worst examples。

Shadow 期间保留 ILU只是诊断，不构成 factor-removal结果。

## 11.2 Harmful candidate定义

至少将以下标为 harmful：

```text
NaN/Inf
abnormal norm
rho_learned >= 1.0
rho_learned > 1.05 * rho_ILU
checkpoint/fingerprint mismatch
proxy/exact disagreement
```

进入 active fallback前要求：

```text
harmful fraction <= 0.1%
no slab harmful fraction > 0.5%
no systematic late-iteration degradation
```

更理想目标为 0 harmful。

## 11.3 Exact audit 与 periodic audit

Shadow必须每次做 exact local operator audit。

只有满足：

```text
zero false accept on validation/shadow
injected failure detected
proxy false-accept = 0
periodic audit catches injected drift
```

后，active qualification才允许使用 periodic audit，例如每 `K=16/32` 次 exact audit，其余使用严格 proxy。

Final global reported/condensed/full residual永远不能抽样。

## 11.4 Fail closed

True no-hidden-ILU profile中没有 ILU fallback。以下任一发生必须中止 candidate并写 failure record：

- corrupt/missing checkpoint；
- operator fingerprint mismatch；
- NaN/Inf；
- audit failure；
- norm/OOD threshold violation；
- GPU/device error；
- MPI rank exception；
- global residual异常增长；
- memory/swap stop condition。

不得偷偷构造 ILU factor继续运行后声称 learned replacement成功。

---

# 12. Global Integration Profiles

## 12.1 P-shadow：All-slab shadow

```text
16 learned outputs computed
ILU writes back
full global solve remains baseline action
```

目的：验证在线分布、安全、runtime和MPI，而不是加速。

## 12.2 P-fallback：All-slab active with diagnostic ILU fallback

```text
learned output active when local Gate passes
ILU fallback available for diagnostics
```

必须报告 fallback fraction与slab concentration。该 profile不能用于：

- memory saving；
- true factor removal；
- final learned-PC acceleration qualification。

进入 true replacement建议：

```text
fallback fraction <= 0.1%
no slab fallback fraction > 0.5%
full residual/RTA pass
```

## 12.3 P-replace：True 16-slab no-hidden-ILU learned replacement

```text
16 learned backend plans resolved before factorization
requires_ilu_factor = false for all 16
allows_fallback = false
ILU factor count = 0
ILU apply count = 0
hidden fallback = 0
two-step smoother retained
post-smooth retained
75D coarse retained
```

这是本任务唯一可用于正式 factor-removal、memory和global acceleration声明的 profile。

---

# 13. Global Numeric、Spectral 与 Engineering Gate

## 13.1 Numeric Gate

每个正式 candidate必须：

```text
KSP converged reason > 0
reported relative residual <= 1e-6
condensed true residual <= 1e-6
full augmented true residual <= 1e-6
max official R/T/A delta from same-run baseline <= 1e-6
energy closure pass
all outputs finite
no online training
```

## 13.2 Oracle benefit retention

定义：

```math
retention =
(iter_baseline - iter_learned)
/
(iter_baseline - iter_exact).
```

Task004参考为：

```text
iter_baseline = 861
iter_exact = 566
```

建议分类：

```text
retention >= 0.80 = strong spectral retention
retention >= 0.60 = positive spectral retention
0.30 <= retention < 0.60 = weak/review required
retention < 0.30 = insufficient
```

Task005正式数据使用同轮 baseline；若不重新运行 exact oracle，可使用Task004 exact iteration只作参考，并明确sampler/commit差异。优先在finalist HEAD重跑至少一次 G16 exact或做action-equivalence校验。

## 13.3 Primary Engineering Positive Gate

相对三轮同配置 paired baseline的中位数：

```text
outer iteration reduction >= 20%
solve wall-time reduction >= 20%
full numeric Gate pass
true no-hidden-ILU pass
external worker peak <= 1.10 * baseline
no swap
```

以 Task004数字sanity：

```text
iterations approximately <= 688
solve approximately <= 71.35 s
```

正式阈值必须按Task005 same-run baseline计算。

## 13.4 Balanced Success Gate

```text
iteration reduction >= 20%
solve reduction >= 20%
retention >= 0.60
persistent learned storage <= removed ILU storage
external peak <= 1.05 * baseline
```

## 13.5 Strong Success Gate

```text
iteration reduction >= 30%
solve reduction >= 25%
retention >= 0.80
external peak <= baseline
three paired runs all numeric pass
worst candidate solve <= 0.85 * paired baseline
```

## 13.6 Spectral-only结果

若：

```text
iteration reduction >= 20%
但 solve reduction < 20%
```

分类为 spectral success / engineering runtime failure。必须保留，不得包装成加速成功。

---

# 14. Repeated Paired A/B 与统计合同

Finalist必须从clean implementation HEAD运行至少三组paired A/B：

```text
B1 -> C1
B2 -> C2
B3 -> C3
```

每组必须同机器、MPI4、threads、sampler、monitor、physical config和operator action。

至少报告：

- 每组iterations、solve、total、peak；
- median、min、max；
- candidate/baseline ratio；
- full residual/RTA；
- model runtime与MPI wait；
- warm-up与GPU sync方法。

不允许从多次运行中只选择最有利的一组。

---

# 15. Same-Operator Multi-RHS Robustness

## 15.1 为什么只测试同 operator RHS

Task005不研究跨角度/波长 operator泛化。参数改变导致 local operator fingerprint变化时，fixed models必须fail closed。

但同一角度、波长、几何和材料下，不同入射偏振/线性组合主要改变 RHS，可用于验证模型复用。

## 15.2 Robustness RHS

Primary S-polarization profile通过后，条件测试：

```text
R0 = original S RHS
R1 = P-polarization RHS at same theta/phi/wavelength
R2 = complex linear combination alpha*S + beta*P
R3 = amplitude-scaled RHS
```

运行前必须证明：

```text
global condensed operator action equivalent
all 16 local operator fingerprints identical
```

若不一致，立即停止该reuse lane，不得绕过fingerprint。

## 15.3 两种训练身份

比较：

```text
S-only trained models -> unseen P/combination
mixed-RHS trained models -> held-out combination
```

该阶段主要验证same-operator RHS coverage和训练成本摊销，不自动代表跨参数泛化。

Robustness Gate建议：

```text
all numeric Gate pass
iteration reduction on each RHS >= 15%
solve time no worse than baseline
no new harmful slab concentration
```

Primary S full Gate仍是Task005主成功条件。

---

# 16. Expert 与 Shared Model Compression（条件）

只有16 independent profile通过Engineering Positive Gate后进入。

## 16.1 Three-expert lane

按运行前冻结的physical/operator metadata分类，例如：

```text
boundary / near-boundary
interface/grating-dominant
regular interior
```

实际映射必须由z位置、material fraction、size class和operator statistics在训练前冻结，不得按global结果事后分组。

每类允许：

- shared reduced trunk；
- slab-specific input/output basis；
- small slab adapters。

## 16.2 Shared trunk + slab adapters

```text
r_s -> U_s^H r_s
-> shared trunk conditioned on slab metadata
-> adapter_s
-> V_s output
```

metadata可以包括：

- slab ID/position；
- size class；
- material fraction；
- diagonal/row norm statistics；
- reduced operator features。

不得输入完整dense `A_s` 或 global vector。

## 16.3 Compression Gate

相对16-independent finalist：

```text
storage reduction >= 30%
end-to-end runtime no worse by >10%
iteration count no worse by >10%
full numeric Gate pass
```

若shared/expert失败，不影响independent upper-bound结论。

---

# 17. Training、Setup 与 Amortization

必须记录：

```text
raw capture wall time
teacher factorization/solve wall time
preprocessing/SVD time
GPU/CPU training time
hyperparameter screening time
checkpoint save/load time
runtime setup time
per-solve wall time
```

计算：

```text
total effective time(N RHS)
= data/teacher/training/setup + N * learned_solve
```

并与：

```text
N * baseline_solve
```

比较，给出break-even RHS count。

至少报告：

```text
N = 1, 10, 100, 1000
```

不得无条件忽略teacher和training成本。对于逆问题/参数扫描，若operator改变需要重训，必须单独说明，不能使用same-operator amortization替代。

---

# 18. 实施阶段与 Gate

## P0：环境、clean baseline与合同冻结

1. 记录branch、HEAD、remote、dirty status；
2. 明确不执行分支操作；
3. 记录WSL/Python/PETSc/DOLFINx/MPC/NumPy/SciPy/PyTorch/CUDA；
4. 固定MPI4、threads、GPU device、CPU affinity；
5. 从clean implementation HEAD运行h5 ILU baseline；
6. full residual/RTA/memory pass；
7. 运行Task004 no-hidden infrastructure tests；
8. 建立Case094 config/expected。

P0失败不得继续。

## P1：16-slab raw capture与LU teacher

1. 完成T1/T2/V/H独立captures；
2. 检查16 fingerprints；
3. 分层抽样与leakage audit；
4. 逐slab one-factor/many-RHS teacher；
5. teacher resource/accuracy pass；
6. heavy artifacts ignored。

P1 Gate：全部16 teacher datasets通过。

## P2：Representative model/data/backend screen

在R4上比较：

```text
D0 vs D1
Lane A vs Lane B
conditional Lane C/D
CPU vs GPU
independent vs owner-like batch
```

冻结：

- candidate family pool；
- selection score；
- runtime backend；
- normalization；
- audit policy；
- max one hard-example round。

若没有任何candidate同时满足local admissibility和runtime/storage可行性，停止full16训练并记录。

## P3：Train/select 16 independent models

1. 对16slabs训练Uniform-16与Heterogeneous-best候选；
2. 每个finalist至少3 seeds；
3. independent holdout local quality；
4. storage/runtime census；
5. checkpoint/fingerprint/determinism tests；
6. 冻结global candidates。

P3 Gate：16/16 admissible；至少一个full candidate满足target local/runtime/storage screen。

## P4：All-slab shadow

1. 16 learned outputs在线计算；
2. every-call exact local audit；
3. ILU写回；
4. 记录harmful/OOD、runtime、MPI wait；
5. 必要时唯一一次hard-example augmentation并重跑shadow。

P4 Gate：安全与projected speed仍可行。

## P5：Diagnostic active with ILU fallback

1. learned active；
2. ILU fallback仅作诊断；
3. full residual/RTA；
4. fallback by slab/phase；
5. no performance/memory success claim。

P5 Gate：fallback极低且无集中、numeric pass。

## P6：True no-hidden-ILU factor removal

1. 16 learned plans在factorization前解析；
2. ILU factors完全不构造；
3. hidden fallback=0；
4. two-step/post-smooth/75D coarse保持；
5. full numeric/performance/memory evidence。

P6是第一次正式learned replacement qualification。

## P7：Three paired clean A/B

从finalist clean HEAD完成三组paired baseline/candidate，按第14节统计。

P7决定Primary Engineering classification。

## P8：Same-operator multi-RHS robustness

仅在Primary S profile通过numeric且至少有positive spectral signal后运行。完成P/linear-combination/amplitude profiles及fingerprint Gate。

## P9：Expert/shared compression

仅在independent profile通过Engineering Positive Gate后运行。否则not_run_by_gate。

## P10：Amortization、final decision与review package

整理全部outcomes，回答第5节研究问题，提交轻量records并等待ChatGPT review。不得自动启动h3/h2或下一任务。

---

# 19. 测试要求

至少新增或更新：

1. 16-slab raw-only capture contract；
2. split leakage/duplicate detection；
3. 16 operator fingerprint stability；
4. teacher one-factor/many-RHS/destroy；
5. linear model linearity/determinism/batch；
6. nonlinear model deterministic inference；
7. complex pack/unpack round trip；
8. checkpoint SHA/fingerprint/corruption fail closed；
9. owner-batch equals independent action；
10. CPU/GPU action agreement within frozen precision；
11. normalization scale invariance；
12. local residual audit identity；
13. proxy/periodic audit injected failure；
14. OOD/norm failure abort；
15. shadow writes back ILU exactly；
16. diagnostic fallback counting；
17. no-hidden-ILU 16-backend setup；
18. ILU factor/apply/fallback all zero in true profile；
19. repeated apply/destroy no leak；
20. MPI2/MPI4 owner diagnostics gather；
21. model storage ledger；
22. GPU buffer lifecycle；
23. full h5 numeric/RTA integration；
24. same-operator P/S fingerprint equivalence test；
25. expert/shared adapter shape and routing；
26. Case094 benchmark contract checker；
27. complete existing test suite；
28. Ruff/compileall；
29. `git diff --check`；
30. heavy artifact ignore audit。

随机过程必须固定seed；性能测试必须记录warm-up、synchronization、thread和affinity。

---

# 20. 禁止事项

本任务不得：

- 进行任何分支管理或master操作；
- 改变ordinary default；
- 使用ILU output/residual作为teacher；
- 正式solve中在线训练；
- 每次迭代通过subprocess/file exchange调用模型；
- 未通过16/16 local Gate就运行all-slab active；
- 使用shared model跳过16-independent upper-bound；
- 使用one-step smoother作为默认candidate；
- 用training loss代替local residual；
- 用local rho代替full true residual/RTA；
- 用shadow/fallback profile声称factor removal或memory saving；
- 在true profile隐藏ILU fallback；
- 只报告最佳seed或最佳单次A/B；
- 用microkernel时间代替end-to-end local path；
- 把exact-LU oracle wall time/memory称为NN结果；
- 未证明operator fingerprint一致就跨角度/波长复用模型；
- 在Task005自动运行h3/h2；
- 提交大型dataset/checkpoint/raw logs；
- 宣称mesh-independent、parameter-general、production-ready或universal neural PC。

---

# 21. 建议代码职责

文件名可以调整，但职责必须清楚。建议：

```text
src/solvers/learned_local_inverse.py
src/solvers/learned_owner_batch.py
src/solvers/local_slab_solver.py
src/solvers/physical_slab_two_level.py

benchmarks/neural_pc/capture_all_slab_rhs.py
benchmarks/neural_pc/build_all_slab_lu_teacher.py
benchmarks/neural_pc/fit_linear_local_inverse.py
benchmarks/neural_pc/train_independent_local_inverse.py
benchmarks/neural_pc/evaluate_all_slab_models.py
benchmarks/neural_pc/benchmark_learned_runtime.py
benchmarks/neural_pc/build_expert_shared_models.py
benchmarks/run_all_slab_learned_pc.py

benchmarks/cases/094_comprehensive_all_slab_learned_pc/

src/test/test_41_all_slab_teacher_contract.py
src/test/test_42_learned_local_inverse_models.py
src/test/test_43_owner_batched_learned_pc.py
src/test/test_44_no_hidden_ilu_learned_profile.py
src/test/test_45_para_task005_contract.py
```

不得把capture、teacher、training、runtime、global benchmark全部堆在一个脚本中。

---

# 22. 最终分类

最终classification必须从以下选择：

```text
learned_pc_strong_engineering_success
learned_pc_balanced_engineering_success
learned_pc_speed_success_memory_tradeoff
learned_pc_spectral_success_runtime_failure
learned_pc_local_success_global_failure
learned_pc_numeric_failure
learned_pc_runtime_budget_failure
learned_pc_memory_budget_failure
learned_pc_data_or_teacher_failure
learned_pc_infrastructure_incomplete
independent_success_shared_compression_failure
shared_or_expert_compression_success
same_operator_multi_rhs_success
not_feasible_with_current_learned_runtime
```

可以同时给出primary classification与secondary findings，但不得自造含义重叠的名称。

---

# 23. 最短执行顺序

```text
P0 clean baseline
-> P1 all-slab raw capture + sequential LU teacher
-> P2 representative data/model/runtime ablation
-> P3 train/select 16 independent models
-> P4 all-slab shadow
-> optional one hard-example augmentation
-> P5 diagnostic active with fallback
-> P6 true no-hidden-ILU factor removal
-> P7 three paired A/B
-> conditional P8 same-operator multi-RHS
-> conditional P9 expert/shared compression
-> P10 amortization + final review package
```

不得跳步。

---

# 24. 任务完成标准

本任务不能以“16个模型训练完成”“loss下降”或“一次solve收敛”结束。至少必须明确回答：

1. 每个slab的teacher资源与精度是多少？
2. 每个slab的ILU、linear、nonlinear local residual median/p95/worst是多少？
3. 哪些slab最难学习，为什么？
4. real-only与real+synthetic哪个更好？
5. nonlinear NN是否真正优于linear inverse？
6. independent与owner-batch runtime分别是多少？
7. CPU与GPU哪个满足end-to-end预算？
8. model、basis、CSR、audit、buffer各占多少内存？
9. shadow是否发现harmful/OOD outputs？
10. fallback profile的fallback fraction与集中位置？
11. true profile是否16个ILU factor全部不存在？
12. full residual、R/T/A、closure是否通过？
13. learned iterations与oracle benefit retention是多少？
14. 三轮paired A/B的median/worst speedup是多少？
15. 是否达到至少20% iteration和20% wall-time reduction？
16. external peak与persistent storage是否满足Gate？
17. P/组合RHS是否可复用同一模型？
18. expert/shared压缩是否保持性能？
19. teacher+training的break-even RHS count是多少？
20. 下一步应进入h3/h2、跨参数operator learning，还是停止local learned inverse？

只有证据完整并经最终ChatGPT review，Task005才允许关闭。