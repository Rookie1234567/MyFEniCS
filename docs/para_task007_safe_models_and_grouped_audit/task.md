# PARA-Task007：Safer Learned Local Inverses and Graph-Certified Grouped Borrowed Audit

## 0. 任务身份

```text
task = PARA-Task007
name = Safer Learned Local Inverses and Graph-Certified Grouped Borrowed Audit
status = planned / research-only continuation
execution_branch = ChatGPT/20260715-para-task-neural-local-pc
predecessor = PARA-Task006
predecessor_review = docs/para_task006_zero_copy_audit_architecture/review_report_v1.md
remote_repository = Rookie1234567/MyFEniCS
reference_wavelength = 13.5 nm
reference_geometry = current validated full-3D periodic Si block grating
reference_discretization = p2 Nedelec hexahedral FEM
reference_parallelism = MPI4 for formal h5 shadow
ordinary_default_changed = false
production_claim_allowed = false
new_full16_model_training_allowed = false
bounded_R4_offline_retraining_allowed = true
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

分支中新增或修改 Task007 相关代码、测试、benchmark 和文档。不得：

- 创建、切换、移动、重命名或删除分支；
- merge、rebase、cherry-pick、reset 或同步其他分支；
- pull、push、提交或合并到 `master`；
- 开 PR；
- 因当前分支与其他分支存在差异而主动改变分支历史；
- 修改 ordinary solver default；
- 自动恢复 Task005 的 16-model P3；
- 自动运行 h3/h2；
- 将本任务解释为 production merge preparation。

若当前分支缺少其他路线的新基础设施，应在 outcomes 中记录限制，不得擅自同步。

---

# 1. 为什么启动本任务

PARA-Task006 得到一个明确的正结果和一个明确的负结果。

## 1.1 已成功解决的问题

`BorrowedLocalExactAuditor` 已证明：

```text
16/16 local submatrix actions可由已有 shifted-F/global action精确重建；
max action relative error = 6.030e-16；
max local rho difference = 3.558e-16；
private persistent local CSR = 0 bytes；
每 rank work vectors约0.753–0.762 MiB。
```

因此 Task005 的 `40.458 MiB/owner private exact-audit CSR` 技术债已经从原则上消除。

## 1.2 尚未解决的问题

Task006 的 reduced residual + procedural CountSketch proxy 在 Q0 上失败：

```text
best non-harmful acceptance = 43.37%
best two-seed acceptance = 42.96%
worst slab false reject = 81.89%
```

同时，冻结的 Task005 `A_D0_R64` 本身在 Q0 上已有：

```text
58 / 1024 harmful outputs
slab 0 = 2
slab 5 = 31
slab 9 = 23
slab 15 = 2
```

因此当前问题不是单一的“proxy 不够好”，而是两个相互作用的问题：

```text
A. 模型本身在 per-sample 尾部上不够安全；
B. 逐 slab borrowed exact audit虽然准确，但单次collective约6.207 ms，
   无法简单地对16个slab每次串行全审计。
```

本任务同时研究：

```text
Lane A：降低模型 harmful fraction，特别是 slab 5/9；
Lane B：通过真实离散耦合图认证，把多个 slab 打包到更少的 borrowed MatMult 中审计。
```

两条路线必须在冻结 R4 shadow 中汇合。任一失败，都不得恢复 Task005 P3。

---

# 2. 必须读取

执行前必须完整读取：

```text
docs/repository_work_principles.md
docs/task_retrospective_standard.md
docs/solver_guide.md
docs/iterative_solver_ports.md
docs/architecture_overview.md
notes/reference/code_walkthrough/32_physical_slab_two_level_pc.md

docs/para_task004_full_16_slab_exact_oracle/task.md
docs/para_task004_full_16_slab_exact_oracle/review_report_v1.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/summary.md

docs/para_task005_comprehensive_all_slab_learned_pc/task.md
docs/para_task005_comprehensive_all_slab_learned_pc/review_report_v1.md
docs/para_task005_comprehensive_all_slab_learned_pc/response_v1.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/summary.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/data_and_teacher_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/model_ablation.csv
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/local_quality_by_slab.csv

docs/para_task006_zero_copy_audit_architecture/task.md
docs/para_task006_zero_copy_audit_architecture/review_report_v1.md
docs/para_task006_zero_copy_audit_architecture/outcomes/summary.md
docs/para_task006_zero_copy_audit_architecture/outcomes/borrowed_action_equivalence.md
docs/para_task006_zero_copy_audit_architecture/outcomes/proxy_qualification.csv

docs/para_task006_zero_copy_audit_architecture/outcomes/memory_report.md

src/solvers/borrowed_local_audit.py
src/solvers/low_storage_audit_proxy.py
src/solvers/local_slab_solver.py
src/solvers/physical_slab_two_level.py
src/solvers/batched_reduced_smoother.py
benchmarks/neural_pc/screen_task005_linear.py
benchmarks/neural_pc/screen_task005_nonlinear.py
benchmarks/neural_pc/calibrate_task006_proxy.py
```

完成任务时必须维护：

```text
docs/para_task007_safe_models_and_grouped_audit/outcomes/summary.md
docs/para_task007_safe_models_and_grouped_audit/outcomes/changed_files.md
docs/para_task007_safe_models_and_grouped_audit/outcomes/experiment_matrix.csv
docs/para_task007_safe_models_and_grouped_audit/outcomes/data_split_report.md
docs/para_task007_safe_models_and_grouped_audit/outcomes/model_safety_by_slab.csv
docs/para_task007_safe_models_and_grouped_audit/outcomes/model_ablation.csv
docs/para_task007_safe_models_and_grouped_audit/outcomes/coupling_graph_report.md
docs/para_task007_safe_models_and_grouped_audit/outcomes/grouped_audit_equivalence.csv
docs/para_task007_safe_models_and_grouped_audit/outcomes/grouped_audit_runtime.csv
docs/para_task007_safe_models_and_grouped_audit/outcomes/failure_injection_matrix.csv
docs/para_task007_safe_models_and_grouped_audit/outcomes/live_shadow_report.md
docs/para_task007_safe_models_and_grouped_audit/outcomes/memory_report.md
docs/para_task007_safe_models_and_grouped_audit/outcomes/provenance.md
docs/para_task007_safe_models_and_grouped_audit/outcomes/validation.md
docs/para_task007_safe_models_and_grouped_audit/outcomes/decision.md
docs/development_progress.md
benchmarks/cases/096_safe_models_grouped_audit/
```

重型 artifacts 必须放在：

```text
benchmarks/artifacts/cases/096/
```

并保持 Git ignored。不得提交：

- raw captures；
- LU factors；
- local/global sparse matrices；
- large checkpoints；
- full profiler traces；
- PETSc timelines；
- raw fields/HDF5/XDMF/VTU；
- full MPI logs。

---

# 3. 冻结物理与求解框架

第一阶段固定：

```text
wavelength = 13.5 nm
material = current validated complex Si
geometry = current 50 x 25 x 140 nm periodic cell
Si block = 17 x 25 x 120 nm
incidence = theta 80 deg, phi 0 deg
primary polarization = S
finite element = p2 Nedelec hexahedral
mesh = h5
periodicity = double Floquet
ports = 80 Fourier-DtN auxiliary unknowns
operator = exact condensed F-C H^-1D
outer = right FGMRES90, rtol 1e-6
physical slabs = 16, overlap 0.25
coarse = fixed 75D true-action Galerkin
smoother = current two-step + post-smooth
formal live shadow = MPI4, one thread per rank
R4 = {0,5,9,15}
```

不得改变：

- 波长、材料、几何、主角度；
- slab 数、overlap、weights 与 owner assignment policy；
- two-step smoother；
- post-smooth；
- 75D coarse；
- right FGMRES90；
- official R/T/A；
- ordinary default。

Task004 的 one-step 仍是负证据，不得在本任务重新包装。

---

# 4. 本任务的研究问题

本任务必须回答：

1. 能否通过 tail-aware/non-degradation 训练，把 R4 模型的 harmful 输出从 `58/1024` 降到冻结 Gate？
2. slab 5/9 是否需要比 slab 0/15 更高的 rank、不同损失或不同 precision？
3. 固定线性映射下，weighted low-rank inverse、CVaR/top-k residual 与 scalar damping 谁最有效？
4. nonlinear residual model 是否在安全尾部上真正优于 linear model，而不只是平均 rho？
5. 新模型能否在未用于训练/选择的 same-operator RHS 上保持安全？
6. 模型与 basis 的存储能否在 grouped-audit metadata 加入后仍满足 33.670 MiB/owner，或至少 50.505 MiB speed-first guard？
7. 真实 global shifted operator 的 slab cross-coupling graph 是什么？
8. 哪些 slabs 可以在一次 global MatMult 中安全 grouped audit？
9. grouped borrowed action 是否与 serial borrowed action和CSR action达到 `<=1e-12` 等价？
10. grouped audit能把完整 R4/16-slab audit sweep从多少 collective MatMult降到多少？
11. grouped every-call exact audit是否可满足最终 owner path预算？
12. 若every-call不满足，周期 grouped audit的摊销是否可行？
13. 模型安全性与 grouped audit联合后，R4 live shadow是否保持 full residual/RTA、零私有CSR和内存预算？
14. Task005 P3是否可在后续独立任务中恢复？

---

# 5. 数据身份与不可重复使用规则

## 5.1 Task005 数据重新标记

```text
T1/T2 = training source
V = Task006 calibration source，已被消费
H = Task005 candidate screening source，已被消费
```

V/H 均不得再称为 untouched final holdout。

## 5.2 Task007 数据集合

必须至少建立：

```text
M0 = T1/T2，训练基础
M1 = V，历史 calibration/replay only
M2 = H，历史 screening/replay only
M3 = fresh same-operator S capture，模型选择/验证
M4 = same-operator P capture，仅当16 operator fingerprints完全一致
M5 = fixed complex S/P combination，模型选择后锁定测试
M6 = untouched final same-operator RHS，在模型和阈值全部冻结后生成
```

M3–M6 必须来自 clean solver records，并保存：

```text
source commit SHA
branch
clean status
physical RHS identity
operator fingerprint by slab
sample SHA-256
sampling schedule
outer iteration / pre-post phase / restart window if available
rhs norm
```

若当前 capture 无法可靠记录 outer/phase metadata，必须明确写入限制，不得声称已完成分层覆盖。

## 5.3 Operator fingerprint Gate

P、S/P combination 或任何新 RHS 只有在：

```text
all 16 local operator fingerprints exact match
same global condensed operator identity
```

时才允许作为 same-operator 测试。任一不一致，标记 `not_same_operator` 并停止该 lane。

## 5.4 数据隔离

- M3 可用于候选选择；
- M4 可用于条件选择，但使用后必须记录为 consumed；
- M5 为 locked test，不得调参；
- M6 为最终 untouched test，不得在最终模型冻结前读取；
- 不得从 M5/M6 harmful samples回流训练；
- 不得多轮反复 hard-example mining。

允许最多一次、每 slab不超过256个样本的预先声明 hard-tail augmentation，并且只能来自 M3。

---

# 6. Lane A：更安全的 Learned Local Inverse

Lane A 只允许在 R4 `{0,5,9,15}` 上进行有界离线训练。不得训练其余12个slabs。

## 6.1 目标

对每个 slab `s`：

```math
z_s^{learned}=N_s(r_s),
\qquad
\rho_s=\frac{\|A_s z_s^{learned}-r_s\|}{\|r_s\|}.
```

不仅优化平均 rho，还要直接控制：

```text
harmful fraction
p95 / p99
worst sample
top-k residual
relative non-degradation vs ILU
```

Harmful ground truth继续定义为：

```text
NaN/Inf
rho_learned >= 1.0
rho_learned > 1.05 * rho_ILU
abnormal norm
wrong operator/checkpoint/slab identity
```

## 6.2 冻结候选池

候选池必须在训练前写入 Case096 config，建议不超过12个配置。至少包括：

### A0：历史基线

```text
rank64 D0 ordinary least-squares low-rank inverse
```

只作对照，不重新包装为新结果。

### A1：Weighted low-rank linear inverse

对高 residual / historically harmful 样本加权：

```math
\min_W \sum_i w_i\|Wc_i-d_i^*\|^2+\lambda\|W\|_F^2.
```

允许最多3轮 deterministic iterative reweighting；权重规则必须在运行前冻结。

### A2：Tail/CVaR linear objective

目标至少比较：

```text
mean residual
mean + top-10% residual
CVaR 95%
max-smoothed / log-sum-exp tail
```

不得只根据最终最好结果事后选择损失定义。

### A3：Non-degradation hinge

允许使用 exact local action离线计算：

```math
L_{nd}=\operatorname{mean}\left[\max(0,\rho_{learned}-\gamma\rho_{ILU})^2\right],
```

其中 `gamma` 预冻结，例如：

```text
1.00 / 1.02 / 1.05
```

不得在正式 runtime依赖 ILU。

### A4：Heterogeneous rank policy

冻结比较：

```text
slab 0/15: rank32 or rank64
slab 5/9: rank64 or rank96
```

必须同时报告 complex128、资格化 complex64 basis/map 的质量与存储。

### A5：Offline scalar damping / trust coefficient

允许：

```text
z = alpha_s * N_s(r)
```

其中 `alpha_s` 必须是训练前定义的常数或仅依赖输入 norm bucket 的冻结查表；不得调用 ILU或exact action在线调节。

### A6：Linear base + small nonlinear residual（条件）

只有线性候选仍无法通过安全 Gate时，允许：

```text
z = z_linear + V_s f_s(U_s^H r_s)
```

最多2个预冻结容量点、每个3 seeds。不得扩大成无限NN搜索。

## 6.3 训练与选择规则

- 每个候选至少固定3 seeds；
- model family与rank选择先基于 M3；
- 若使用M4参与选择，必须在M5/M6中保持完全锁定；
- 最终每 slab候选在 global/light shadow 前冻结；
- 不得根据 live solver结果重新挑模型；
- 不得只报告最佳 seed；
- 必须报告 median/min/max seed。

## 6.4 Lane A Safety Gate

### Calibration/selection Gate

M3 上每个 slab至少：

```text
all finite
median rho <= median ILU
p95 rho <= 0.90 * p95 ILU
harmful fraction <= 0.5%
no sample rho >= 2.0
```

### Locked Gate

M5 与 M6 上：

```text
harmful count = 0 for each slab
rho >= 1.0 count = 0
rho > 1.05*rho_ILU count = 0
all finite
p95 rho <= p95 ILU
```

若在M5/M6发现 harmful，不允许回流训练；该候选直接失败。

### Tail Target

重点 slab 5/9：

```text
p99 rho <= 0.95
worst rho < 1.0
median ratio <= 0.80 preferred
```

边界 slab 0/15：

```text
median ratio <= 0.60 preferred
worst rho < 1.0
```

## 6.5 Runtime Gate

R4 owner-batch model-only：

```text
mean <= 7.2 ms
p95 <= 9.0 ms
no per-call checkpoint load
persistent buffers
no large per-call allocation
```

最终 grouped-audit联合预算见第10节。

## 6.6 Storage Gate

必须报告：

```text
input/output bases
reduced maps / MLP
normalization metadata
persistent CPU/GPU buffers
checkpoint metadata
```

目标：

```text
R4 model storage <= 28 MiB / owner preferred
model + grouped auditor persistent state <= 33.670 MiB / owner preferred
speed-first maximum <= 50.505 MiB / owner
```

---

# 7. Lane B：Graph-Certified Grouped Borrowed Exact Audit

## 7.1 为什么需要真实耦合图

若把多个 slab corrections 同时 lift：

```math
x=\sum_{j\in G}R_j^T z_j,
```

则对 slab `i`：

```math
R_i A x=A_{ii}z_i+\sum_{j\ne i}A_{ij}z_j.
```

只有当组内所有交叉块：

```math
A_{ij}=R_i A R_j^T=0
```

时，单次 MatMult 的 restriction才等于每个 slab独立 local action。

因此不得根据：

```text
slab距离
two-color名字
owner分配
几何直觉
```

直接假定可以 grouped audit。

## 7.2 Coupling graph定义

建立无向图：

```text
vertex = slab id
edge(i,j) exists if A[I_i,I_j] or A[I_j,I_i] has structural/numerical coupling
```

必须记录两种证据：

### Structural certificate

在 qualification 阶段允许从合法常驻/临时 assembled shifted operator提取：

```text
cross block shape
structural nnz
max abs entry
Frobenius norm
operator fingerprint
```

提取完成后不得持久保存 cross blocks或完整CSR。

### Action certificate

对每个候选无边 pair/group，使用：

```text
deterministic random corrections
real learned outputs
scale/phase variants
sparse/high-frequency probes
```

验证交叉影响：

```math
\frac{\|R_i A R_j^T z_j\|}{\|A_{jj}z_j\|+\epsilon}\le 10^{-13}
```

或绝对机器精度阈值。Structural certificate与action certificate任一不一致，按有边处理。

## 7.3 Group构造

必须由图算法在运行前冻结：

```text
graph coloring
maximum independent sets
owner-aware coloring（仅作性能优化，不得破坏正确性）
```

至少报告：

```text
edge list
adjacency hash
color count
groups by color
max group size
owner composition
```

不得运行后根据时间重新手工分组。

## 7.4 Grouped auditor接口

建议新增：

```python
class GroupedBorrowedLocalExactAuditor:
    def audit_group(self, slab_ids, rhs_by_slab, correction_by_slab): ...
    def audit_all_colors(self, ...): ...
    def destroy(self): ...
```

必须：

- 复用现有 global action/operator；
- 复用 union scatter/layout；
- 使用 persistent PETSc work vectors；
- private persistent local CSR = 0；
- 不复制 assembled global matrix；
- 所有rank以相同group顺序参加collective；
- group identity、graph hash和operator fingerprint fail closed；
- destroy后不可调用。

## 7.5 Grouped Equivalence Gate

对所有16 slabs与所有冻结 groups：

```text
grouped vs serial borrowed action relative error <= 1e-12
grouped vs CSR qualification reference <= 1e-12
grouped rho vs serial rho absolute difference <= 1e-12
all finite
```

至少使用每 slab 8 个 probes，并覆盖：

```text
real RHS/model output
random complex
scale/phase
single-coordinate sparse
boundary/interior localized
high-frequency alternating
```

## 7.6 Graph-negative结果也必须保留

若真实图为完全图或颜色数过高，导致 grouped audit无实质减少：

```text
grouping_not_useful_by_operator_graph
```

应作为有效负结果停止Lane B，不得用近似忽略交叉耦合。

---

# 8. Grouped Audit Runtime Lanes

## 8.1 Serial reference

记录：

```text
single slab borrowed audit mean/p95/max
R4 full serial sweep
16-slab full serial sweep
collective MatMult count
```

## 8.2 Color-grouped full exact sweep

记录：

```text
color count
MatMult count per full sweep
R4 grouped sweep mean/p95/max
16-slab grouped sweep mean/p95/max
scatter/action/restrict/MPI wait breakdown
```

## 8.3 Every-call exact audit feasibility

若：

```text
model owner-batch + grouped exact audit all enabled slabs
<= 11.514 ms / owner one-level apply mean
and p95 <= 1.25 * 11.514 ms
```

则可以形成：

```text
every_call_grouped_exact_feasible
```

这是最强安全路线，不需要低存储proxy决定是否接受当前输出。

## 8.4 Periodic grouped audit feasibility

若every-call不满足，比较：

```text
K = 2 / 4 / 8 / 16 one-level applies
```

但 periodic lane 只能用于：

```text
research shadow
diagnostic fallback
```

不能单独解锁true no-hidden-ILU replacement，除非 Lane A 在所有 locked/final corpus上零 harmful，且后续独立review明确接受该研究安全合同。

必须报告：

```text
amortized grouped audit time
maximum slab audit interval
fault detection latency
model+audit projected owner path
```

---

# 9. Failure Injection 与身份检查

即使 Lane A 模型通过 locked Gate，grouped auditor必须检测或fail closed：

```text
NaN / Inf
wrong slab routing
wrong group/graph hash
stale operator fingerprint
stale checkpoint
scale 0.25/0.5/1.5/2/4
phase pi/8/pi/4/pi/2/pi
single-coordinate spike
basis-orthogonal noise
high-frequency noise
one-owner corruption
one-slab corruption
late-iteration corruption
```

对 every-call grouped exact audit：

```text
所有exact-harmful输出必须在使用前检测
false accept = 0 on frozen injection corpus
```

对 periodic lane：

```text
记录实际检测延迟
不得声称pre-use detection
不得包装成strict every-call safety
```

---

# 10. Lane A + Lane B 联合 Gate

## 10.1 Strong联合路线

只有同时满足：

```text
Lane A M5/M6 each slab harmful count = 0
Lane A runtime/storage pass
Lane B grouped equivalence pass
every-call grouped exact owner path <= 11.514 ms mean
private persistent CSR = 0
```

才分类为：

```text
safe_model_and_every_call_grouped_audit_qualified
```

该结果仍只允许后续独立任务恢复Task005 P3，不在本任务直接训练16模型。

## 10.2 Conditional联合路线

若：

```text
Lane A locked/final zero harmful
Lane B grouped equivalence pass
periodic grouped audit budget pass
every-call budget fail
```

分类为：

```text
safe_model_periodic_grouped_audit_shadow_only
```

它只允许后续任务做all-slab shadow/diagnostic fallback设计，不直接允许true no-hidden-ILU。

## 10.3 不可恢复条件

以下任一发生，Task005 P3继续锁定：

```text
M5/M6任一 harmful output
grouped action error > 1e-12
operator graph无法形成有效group
model+audit storage > 50.505 MiB/owner
private persistent CSR > 0
R4 live shadow numeric/RTA fail
```

---

# 11. R4 Live Shadow

只有 Lane A locked Gate 与 Lane B equivalence Gate通过后运行。

配置：

```text
R4 learned outputs computed
ILU remains final writeback
current two-step smoother retained
75D coarse retained
right FGMRES90 retained
private CSR = 0
grouped exact audit every call if strong lane
or periodic grouped audit if conditional lane
```

必须记录：

```text
reported/condensed/full residual
R/T/A and closure
learned rho vs ILU rho by slab
harmful count
model time
grouped audit time
MPI wait
operator action count
external simultaneous worker RSS
swap
ordinary ILU writeback equivalence
```

Numeric Gate：

```text
KSP reason > 0
reported/condensed/full residual <= 1e-6
max R/T/A delta <= 1e-6
closure pass
all finite
ILU writeback unchanged
```

Memory Gate：

```text
private persistent CSR = 0
external peak <= 1.10 * paired baseline
no swap
```

本 shadow不构成learned acceleration或factor-removal结果。

---

# 12. 执行阶段

## P0：Provenance、数据与基线

1. 记录branch/HEAD/remote/dirty；
2. 不执行任何分支操作；
3. 完成Task006 Review回应；
4. 建立M3–M6数据身份计划；
5. clean h5/MPI4 baseline；
6. full tests/diff/artifact ignore。

P0失败不得继续。

## P1A：Fresh same-operator corpora

1. 采集M3 fresh S；
2. 验证P/combination fingerprints；
3. 条件采集M4/M5；
4. 模型冻结后生成M6；
5. leakage/duplicate/metadata审计。

## P1B：Coupling graph census

1. 提取16-slab cross-block structural census；
2. 构造保守耦合图；
3. action certificate；
4. 冻结graph hash/coloring/groups；
5. 不持久保存cross blocks。

## P2A：Safe model bounded screen

1. 冻结候选池<=12；
2. A0–A5；
3. 每候选3 seeds；
4. M3选择；
5. storage/runtime screen；
6. 冻结finalists。

P2A Gate：R4 M3 safety与预算pass。

## P2B：Grouped auditor implementation

1. grouped lift/action/restrict；
2. graph identity fail closed；
3. persistent buffers；
4. destroy/lifecycle；
5. serial/grouped/CSR等价。

P2B Gate：16/16等价 `<=1e-12`、private CSR=0。

## P3A：Locked/final model qualification

1. 运行M5；
2. 生成并运行M6；
3. 不再调参；
4. harmful必须逐slab为0。

P3A失败：Lane A停止。

## P3B：Grouped runtime qualification

1. serial reference；
2. R4 grouped sweep；
3. 16-slab grouped sweep；
4. every-call预算；
5. periodic K预算；
6. MPI wait与storage。

## P4：Failure injection

对冻结model+grouped auditor执行第9节矩阵。记录pre-use/periodic detection语义。

## P5：R4 live shadow

仅在P3A/P3B通过后运行。完成numeric/RTA/memory/runtime evidence。

## P6：Final decision与review package

整理outcomes，选择第16节classification，等待ChatGPT review。不得自动恢复Task005 P3。

---

# 13. 测试要求

至少新增或更新：

1. M3–M6 split identity与leakage；
2. P/S/combination operator fingerprint equivalence；
3. consumed V/H不能作为untouched final；
4. weighted low-rank deterministic fit；
5. CVaR/top-k objective；
6. non-degradation hinge；
7. heterogeneous rank routing；
8. complex64/complex128 agreement；
9. scalar damping identity；
10. three-seed reporting contract；
11. locked/final no-retuning contract；
12. harmful exact-ground-truth definition；
13. slab5/9 tail metrics；
14. cross-block structural census；
15. conservative graph edge construction；
16. graph hash/checkpoint；
17. graph coloring deterministic；
18. group cross-coupling action probe；
19. grouped vs serial borrowed action；
20. grouped vs CSR qualification reference；
21. grouped rho equivalence；
22. wrong group identity fail closed；
23. all-rank same group order；
24. grouped persistent allocation；
25. grouped destroy idempotence；
26. private CSR zero ledger；
27. serial/grouped runtime counters；
28. every-call budget calculation；
29. periodic schedule accounting；
30. failure injection numeric/scale/phase；
31. wrong slab/model/operator detection；
32. pre-use vs periodic detection semantics；
33. R4 shadow ILU writeback equivalence；
34. full h5 residual/RTA integration；
35. external memory/swap sampler；
36. MPI2/MPI4 grouped auditor；
37. no RSS growth repeated apply；
38. complete existing test suite；
39. Ruff/compileall；
40. `git diff --check`；
41. heavy artifact ignore audit。

随机过程必须固定seed；性能测试必须记录warm-up、synchronization、thread和affinity。

---

# 14. 禁止事项

本任务不得：

- 进行任何分支管理或master操作；
- 修改ordinary default；
- 训练其余12个slab模型；
- 恢复Task005 full16 P3；
- 使用ILU output/residual作为teacher；
- 在线训练；
- 根据M5/M6或live shadow重新调模型；
- 根据运行时间事后改coupling graph/group；
- 凭几何距离假设cross-coupling为0；
- 忽略非零cross blocks制造grouping；
- 将periodic detection表述为pre-use safety；
- 用R4 shadow声称learned factor removal或global acceleration；
- 用平均rho掩盖harmful tail；
- 只报告最佳seed；
- 把V/H重新称为untouched holdout；
- 提交大型dataset/checkpoint/raw logs；
- 自动运行h3/h2；
- 宣称parameter-general、mesh-independent、production-ready或universal neural PC。

---

# 15. 建议代码职责

文件名可调整，但职责必须清晰：

```text
src/solvers/safe_learned_local_inverse.py
src/solvers/grouped_borrowed_local_audit.py
src/solvers/slab_coupling_graph.py
src/solvers/borrowed_local_audit.py
src/solvers/physical_slab_two_level.py

benchmarks/neural_pc/capture_task007_rhs.py
benchmarks/neural_pc/train_task007_safe_models.py
benchmarks/neural_pc/qualify_task007_models.py
benchmarks/neural_pc/build_slab_coupling_graph.py
benchmarks/neural_pc/qualify_grouped_borrowed_audit.py
benchmarks/neural_pc/benchmark_grouped_audit_runtime.py
benchmarks/run_task007_r4_shadow.py

benchmarks/cases/096_safe_models_grouped_audit/

src/test/test_49_safe_learned_models.py
src/test/test_50_slab_coupling_graph.py
src/test/test_51_grouped_borrowed_audit.py
src/test/test_52_para_task007_contract.py
```

不得把capture、training、graph census、grouped audit、shadow全部堆在一个脚本中。

---

# 16. 最终分类

最终classification必须从以下选择：

```text
safe_model_and_every_call_grouped_audit_qualified
safe_model_periodic_grouped_audit_shadow_only
safe_model_qualified_grouped_audit_runtime_failure
safe_model_safety_failure
grouped_audit_qualified_model_failure
grouped_audit_equivalence_failure
grouping_not_useful_by_operator_graph
grouped_audit_runtime_budget_failure
combined_storage_budget_failure
r4_live_shadow_numeric_failure
r4_live_shadow_memory_failure
infrastructure_incomplete
```

可以同时记录secondary findings，但不得自造含义重叠的成功名称。

---

# 17. 任务完成标准

本任务不能以“新模型loss更低”或“grouped auditor写完”结束。至少必须明确回答：

1. M3–M6各自是什么身份，哪些已被消费？
2. 新模型在每个R4 slab上的median/p95/p99/worst/harmful是多少？
3. slab 5/9的 harmful是否降为0？
4. 线性weighted/CVaR/hinge与nonlinear residual谁有效？
5. 三个seed是否得到一致结论？
6. 模型storage与owner-batch runtime是多少？
7. 16-slab cross-coupling graph是什么？
8. 实际颜色数和group是什么？
9. grouped action与serial/CSR误差是多少？
10. R4/16 full sweep各需要多少MatMult和时间？
11. every-call exact grouped audit是否满足11.514 ms预算？
12. periodic lane的摊销与检测语义是什么？
13. failure injection是否全部按声明语义检测？
14. R4 live shadow是否numeric/RTA/memory通过？
15. private persistent CSR是否仍为0？
16. Task005 P3是否可在下一独立任务中恢复，恢复到哪一阶段？

只有完成上述问题并等待ChatGPT审阅，Task007才算结束。
