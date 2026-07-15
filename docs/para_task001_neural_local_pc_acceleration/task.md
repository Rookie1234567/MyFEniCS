# PARA-Task001：Neural Local Preconditioner Acceleration for the Full-3D Maxwell Solver

## 0. 任务身份

```text
task = PARA-Task001
name = Neural Local Preconditioner Acceleration for the Full-3D Maxwell Solver
status = planned / research-only parallel task
execution_branch = ChatGPT/20260715-para-task-neural-local-pc
base_branch = master
remote_repository = Rookie1234567/MyFEniCS
reference_wavelength = 13.5 nm
reference_geometry = current validated full-3D periodic Si block grating
reference_discretization = p2 Nedelec hexahedral FEM
reference_parallelism = MPI4 unless a smaller smoke explicitly says otherwise
ordinary_default_changed = false
production_claim_allowed = false before final review
```

### 0.1 一次性分支治理例外

仓库长期原则规定执行分支通常由 Codex 创建。本分支由用户在 2026-07-15 明确要求并授权 ChatGPT 直接创建，作为并行机器开发入口。这是一次性、任务级例外：

- 不修改 `docs/repository_work_principles.md`；
- 不改变今后默认仍由 Codex 创建执行分支的规则；
- 不允许借此绕过 task / outcomes / review / selective merge 流程；
- 该分支仍属于 research branch，失败 solver code 默认不合并 production。

---

# 1. 为什么启动本任务

当前完整 3D p2 Maxwell 求解器已经具有可信 direct reference、exact DtN condensation、right FGMRES、16 个重叠 physical z-slabs、75D wave-aware coarse correction，以及通过 full explicit true residual 和 official R/T/A Gate 的迭代基线。

但当前两个主要工程基线存在明确折中：

1. Task030 speed-oriented compact profile 保留较快的 assembled fine action，h2 历史结果约为 1873 次迭代、2393.689 s、9.374729 GiB；
2. Task031 memory-first profile 释放 assembled `F`，h2 达到约 7.897675 GiB，但需要 1977 次迭代、11982.581 s，约为 Task030 solve time 的 5.01 倍。

Task031 已证明当前主要时间成本不是一次性释放 `F`，而是大量 outer / inner Krylov 步中重复执行 public MPC form action、装配与通信。继续只压缩 restart、近似共享 factor 或把边界 slab 改成 Jacobi 已经得到负结果。

因此本任务研究：

```text
能否用冻结的神经局部预条件器，
增强或替换 physical-slab 内部的局部修正，
显著减少 outer / inner 的真实 Maxwell action 调用次数，
从而降低 wall time；
同时评估是否可以替代部分 ILU factor storage，进一步降低内存。
```

本任务是现有 full-3D 路线上的并行可行性研究，不替代 Task032–Task035 的 Hybrid FEM–Modal、h/p 自适应和最终迭代主路线。

---

# 2. 开始前必须读取

开发者开始实现前必须读取：

```text
docs/repository_work_principles.md
docs/task_retrospective_standard.md
docs/project_service_requirements_and_forward_model_roadmap.md
docs/project_service_requirements_phase1_scope.md
docs/solver_guide.md
docs/iterative_solver_ports.md
docs/architecture_overview.md

docs/task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/summary.md
docs/task031_compact_physical_slab_memory_optimization/task.md
docs/task031_compact_physical_slab_memory_optimization/outcomes/summary.md
docs/task031_compact_physical_slab_memory_optimization/review_report_v1.md
docs/task031_compact_physical_slab_memory_optimization/response_v1.md
docs/task031_compact_physical_slab_memory_optimization/review_report_v2.md

docs/task032_hybrid_fem_modal_direct_baseline/task.md
notes/reference/code_walkthrough/32_physical_slab_two_level_pc.md
notes/theory/iterative_solver_and_preconditioner.md

src/solvers/physical_slab_two_level.py
src/solvers/condensed_dtn.py
src/solvers/mpc_form_action.py
benchmarks/run_workstation_iterative.py
src/test/test_23_physical_slab_two_level.py
```

完成任务时必须维护：

```text
docs/para_task001_neural_local_pc_acceleration/outcomes/summary.md
docs/development_progress.md
benchmarks/cases/090_neural_local_pc_acceleration/
```

重型矩阵、训练数据、模型 checkpoint、完整残差流和 profiler 输出必须放在：

```text
benchmarks/artifacts/cases/090/
```

并保持 Git ignore。Git 中只提交轻量配置、checksum、compact records、结果表和必要的小型 smoke fixture。

---

# 3. 冻结物理与数值基线

## 3.1 物理问题

第一阶段冻结：

```text
wavelength = 13.5 nm
material = current validated complex Si optical constant
geometry = current validated 50 x 25 x 140 nm periodic cell
Si block = current validated 17 x 25 x 120 nm block
incidence = theta=80 deg, phi=0 deg, S polarization
periodicity = double Floquet in x/y
ports = current 80 auto-propagating auxiliary Fourier-DtN unknowns
finite element = p2 Nedelec hexahedral
MPI = 4 ranks for target runs
```

不得在第一阶段同时改变波长、材料、几何、偏振、端口模态定义、粗空间或 official R/T/A 口径。

## 3.2 两个比较基线

### Baseline-S：速度优先

Task030-derived compact physical-slab profile：

```text
operator = exact condensed operator with assembled fine action retained
outer = right FGMRES90
subdomains = 16 physical z slabs
overlap = 0.125
local = shifted-F ILU0, factor-only storage
smoother = symmetric pre/post path
coarse = fixed 75D wave coarse
```

h2 历史参考：

```text
iterations = 1873
solve_s = 2393.689
peak = 9.374729 GiB historical reviewed reference
full residual = 9.972228e-7
```

### Baseline-M：内存优先

Task031 assembled-F-free public MPC form-action profile：

```text
operator = exact condensed operator, assembled F released during solve
outer = right FGMRES90
subdomains = 16 physical z slabs
overlap = 0.125
local = shifted-F ILU0, factor-only storage
smoother = symmetric pre/post path
coarse = fixed 75D wave coarse
```

h2 reviewed reference：

```text
n_fe = 615108
iterations = 1977
solve_s = 11982.581
external simultaneous worker peak = 7.897675 GiB
full augmented true residual = 9.998454e-7
max R/T/A delta from direct = 6.126e-9
```

NN 候选必须分别与适用的 Baseline-S 和 Baseline-M 比较，不得混用不同 memory sampler 或把不同 action 路径的时间差全部归因于 NN。

---

# 4. 核心研究问题

本任务必须回答以下问题，而不是只报告训练 loss：

1. NN 能否对真实 complex shifted-F slab operator 给出有效局部修正？
2. NN 是否能处理真实 Krylov 过程中出现的局部 RHS，而不仅是白噪声样本？
3. NN 替代或增强局部 ILU 后，outer FGMRES 迭代数是否显著下降？
4. NN 是否能把当前两步 inner smoother 降为一步，从而减少昂贵 true/form action？
5. NN inference、CPU/GPU transfer、batch packing 和 fallback 的成本是否低于节省的计算？
6. 若移除部分或全部 ILU factors，模型权重、激活、局部矩阵和 runtime buffer 的总内存是否真实下降？
7. 候选是否保持 full explicit true residual、official R/T/A 和能量闭合？
8. NN 在 h5、h3、h2 的尺寸变化下是否可复用，还是只能记忆固定 slab？

---

# 5. 方法边界与推荐架构

## 5.1 必须保留的可信框架

第一阶段不得替换：

- exact condensed operator `F-C H^-1 D`；
- outer right FGMRES；
- 75D true-action Galerkin coarse correction；
- physical-slab subdomain index sets、owner assignment、overlap weighting 和 MPI scatter；
- full explicit true residual；
- official modal R/T/A 和 volume absorption；
- current benchmark provenance、memory sampler 和 lifecycle Gate。

NN 只允许作为 local slab solver backend 或 local residual-correction backend。

## 5.2 推荐插入位置

当前局部路径为：

```text
local rhs r_s
-> local shifted-F ILU/KSP solve
-> local correction z_s
-> overlap weighting
-> reverse scatter to global correction
```

新增抽象应类似：

```python
class LocalSlabSolver:
    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None:
        ...
```

至少保留：

```text
IluLocalSlabSolver
JacobiLocalSlabSolver (existing research baseline)
NeuralLocalSlabSolver
IluNeuralCorrectionSlabSolver
```

不得在第一版重写 coarse context 或 outer KSP。

## 5.3 三条候选 lane

### Lane A：NN-only local inverse feasibility

```text
z_s = NN(A_s metadata, r_s)
```

只用于验证 NN 是否能学习真实局部逆动作。不得因为单 slab loss 很低就直接称为全局加速成功。

### Lane B：ILU + NN residual correction（优先）

```text
z0_s = ILU_s(r_s)
q_s  = r_s - A_s z0_s
dz_s = NN(A_s metadata, q_s)
z_s  = z0_s + dz_s
```

该 lane 让 NN 只学习 ILU 未消除的困难误差，优先级高于从零学习完整逆。

### Lane C：NN single-step smoother

若 Lane A/B 在 h5 出现明确正信号，测试：

```text
current two-step inner GMRES smoother
-> one NN-enhanced slab apply
```

目标是减少 inner true-action 数量。该 lane 必须单独记录 operator apply count，不能只看 outer iterations。

---

# 6. 数据生成与训练合同

## 6.1 不保存全局 A/b 训练集

禁止把完整 615108-DoF 全局矩阵和大量全局残差保存为普通训练集。

训练对象是 owner rank 上的局部 shifted-F slab operators。每个 unique slab CSR 只保存一次，并附带：

```text
matrix shape
CSR indptr / indices / complex values
slab ID and z range
DoF global indices or canonical local ordering
overlap/core mask
material/boundary summary
h, p, wavelength, incidence, polarization
exact fingerprint
normalization metadata
source commit / image digest
```

## 6.2 训练样本类型

数据必须混合：

1. `synthetic_error`：生成有结构的局部误差 `e_s`，计算 `r_s=A_s e_s`；
2. `teacher_solve`：对采样 `r_s` 使用可靠局部 LU/高精度 solve 得到标签；
3. `real_krylov_rhs`：从现有 baseline 的真实 `_apply_once()` 采集局部 RHS，再用 teacher solve 生成标签；
4. `ilu_residual`：采集 `q_s=r_s-A_s ILU_s(r_s)`，用于 Lane B。

不得只使用独立白噪声并据此声称能处理真实 FGMRES 残差。

## 6.3 训练方式

第一阶段使用离线训练：

```text
export representative local operators / RHS
-> offline train
-> save frozen checkpoint + checksum
-> solver runtime only inference
```

正式 benchmark 中不得在线反向传播或更新权重。任何在线适应研究必须另开 lane 并显式记录训练时间、显存和预条件器可变性。

## 6.4 输入、输出与 loss

输入：

```text
normalized complex local residual / ILU residual
+ optional local matrix/operator features
+ slab class / geometry metadata
```

输出：

```text
complex local correction z_s or delta z_s
```

基础 loss：

```math
L_corr = ||z_s-e_s||^2 / (||e_s||^2+delta)
```

```math
L_res = ||A_s z_s-r_s||^2 / (||r_s||^2+delta)
```

Lane B 使用：

```math
L_res,corr = ||A_s(z_s^{ILU}+delta z_s)-r_s||^2/(||r_s||^2+delta).
```

最终模型选择不能只依赖 validation loss，必须以局部 action Gate 和全局 FGMRES wall-time / residual Gate 为准。

---

# 7. 模型与硬件约束

## 7.1 先从 h5 开始

执行顺序强制为：

```text
small synthetic unit test
-> h5 single slab
-> h5 all slabs
-> h3 conditional
-> h2 conditional
```

不得直接从 h2 开始训练或完整运行。

## 7.2 4 GB GPU / CPU fallback

第一版必须支持 CPU inference，并可选 GPU inference。若使用 GPU：

- 不得把完整全局 PETSc vector 或 matrix 放入 4 GB GPU；
- 仅 owner rank 的局部 slab 数据按 batch 传输；
- 必须分别计时 batch packing、host-to-device、inference、device-to-host 和 scatter；
- 必须报告 GPU peak allocated / reserved memory；
- 小 batch 或 CPU inference 更快时应如实保留负结果。

## 7.3 模型复杂度

禁止对大型 slab 使用稠密 `Linear(n_s,n_s)` 作为最终候选。教学 smoke 可以使用小稠密层，但真实 h5/h3/h2 候选应优先考虑：

- POD / reduced-coordinate correction；
- sparse or graph message passing；
- structured hexahedral local representation；
- low-rank residual correction；
- shared trunk + slab-specific small adapters。

若第一阶段采用 16 个 slab-specific 模型，只能标记为 engineering upper-bound experiment，不能声称具有参数/网格可扩展性。

---

# 8. Runtime 安全与 fallback

每次 NN local solve 至少检查：

```text
finite output
output norm sanity
local residual ratio rho_s = ||r_s-A_s z_s||/||r_s||
inference exception / missing checkpoint / checksum mismatch
```

支持显式 fallback：

```text
NN invalid or rho_s above threshold
-> current ILU local solve
```

必须记录：

```text
NN apply count
fallback count and slab IDs
local rho distribution
NN/ILU timing
host-device timing
model memory
```

NN-only profile 在没有 fallback 时必须 fail closed，不能返回有限向量就继续宣称成功。

---

# 9. 实施阶段与 Gate

## P0：环境、基线与数据出口

1. 在新机器 clean clone 并 checkout 本分支；
2. 记录 `git status`、HEAD、remote、Docker image/digest、Python/PETSc/DOLFINx/PyTorch 和 CPU/GPU；
3. 运行现有 unit/import smoke；
4. 重现 h5 Baseline-S 或 Baseline-M 的 compact record，不要求先跑 h2；
5. 新增 local slab operator / RHS export，验证导出 CSR action 与 PETSc local Mat action 的相对误差 `<=1e-12`。

P0 未通过不得训练真实 slab 模型。

## P1：单 slab 离线训练

至少选择：

```text
one boundary / air-dominated slab
one interface / grating-containing slab
one interior representative slab
```

若只有一个 slab 进入第一轮，必须说明选择依据。

Local validation Gate：

```text
no NaN/Inf
checkpoint deterministic
median rho_s < 0.5 on real-Krylov validation RHS
p95 rho_s < 0.95
NN apply time recorded against ILU apply
unseen validation split separated by RHS generation seed/run
```

这是 feasibility Gate，不等于全局成功。

## P2：h5 单 slab 替换

只把一个 slab 改为 NN/ILU+NN，其余保持 current ILU。必须比较：

```text
outer iterations
operator apply count
PC / smoother apply count
full true residual
R/T/A and closure
wall time
peak memory
fallback count
```

若 full true residual `>1e-6`、R/T/A delta `>1e-6` 或时间明显恶化且无机制正信号，停止该 lane。

## P3：h5 全 slab

允许：

- shared model；
- small number of expert models；
- slab-specific upper-bound models（必须明确不可扩展身份）。

h5 Engineering Positive Gate：

```text
full augmented true residual <= 1e-6
max official R/T/A delta from direct <= 1e-6
energy closure remains within current benchmark Gate
no hidden online training
solve wall time reduction >= 20% against same-action baseline
peak memory increase <= 10%
```

h5 Strong Gate：

```text
solve wall time reduction >= 2x
and peak memory <= baseline
or peak memory reduction >= 20% with no solve-time regression
```

必须同时报告 outer iteration reduction 与每步成本，防止只降低迭代数却增加总时间。

## P4：h3 conditional

只有 h5 达到 Engineering Positive Gate 才进入 h3。必须重新训练或验证模型尺寸/网格迁移，不得默认 h5 checkpoint 对 h3 通用。

h3 至少通过：

```text
full true residual / RTA Gate
wall time positive against same-action h3 baseline
peak memory within hardware safety limit
no uncontrolled fallback concentration
```

## P5：h2 conditional

只有 h3 full pass 且根据实测给出可信时间、内存和 GPU 预测后才允许 h2。h2 不得因为“模型已训练”绕过现有 memory watchdog、true-residual monitor 或 official R/T/A Gate。

单次 h2 运行前必须给出：

```text
predicted peak memory
predicted solve time
predicted NN/fallback apply counts
checkpoint provenance
stop / warning thresholds
```

---

# 10. 性能诊断要求

每个正式候选必须拆分时间：

```text
fine/condensed operator action
local gather/scatter
ILU local solve
NN batch packing
H2D / D2H
NN inference
local residual check
coarse projection/solve
FGMRES orthogonalization if available
setup / training / checkpoint load
```

至少记录：

```text
outer iterations
outer operator apply count
inner operator apply count
one-level smoother apply count
PC apply count
mean and p95 local solve time
solve wall time / total wall time
simultaneous worker RSS / cgroup peak / GPU peak
training time and offline artifact size
```

NN 价值必须按完整 amortization 场景解释：单次 solve、同一 operator 多 RHS、参数扫描分别计算训练成本摊销，禁止把离线训练成本无条件忽略。

---

# 11. 测试要求

至少新增：

1. complex sparse toy system 的 NN local solver action test；
2. checkpoint missing/corrupt/checksum mismatch fail-closed test；
3. deterministic repeated inference test；
4. complex real/imag packing round-trip test；
5. local residual ratio 与 fallback test；
6. ILU+NN correction 不劣化教师修正的 controlled fixture；
7. owner-computes single-rank / MPI2 smoke；
8. overlap weighting 和 reverse scatter 与现有 ILU path 等价的 adapter test；
9. PC certification：固定冻结模型应报告 determinism；若结构非线性，只允许 FGMRES；
10. h5 integration test 的 full true residual 与 official R/T/A Gate；
11. lifecycle / destroy / repeated apply no leak test；
12. `git diff --check`、现有 full unit suite 和 benchmark checker。

测试不得把随机一次收敛当作稳定性证据；训练和推理随机种子、checkpoint checksum 必须记录。

---

# 12. 禁止事项

本任务不得：

- 改变 ordinary solver default；
- 用 NN 输出直接替代 full true residual；
- 用训练 loss、局部 residual 或 KSP reported residual冒充求解成功；
- 在未通过 h5 Gate 前运行 h2；
- 把大型 CSR、checkpoint、field、HDF5、完整日志提交 Git；
- 把 16 个 slab-specific 网络称为通用神经预条件器；
- 因 NN 正信号删除现有 ILU fallback；
- 把不同 operator action、不同 sampler 或不同硬件的时间/RSS直接混为严格 A/B；
- 整体合并本 research branch；
- 阻塞或改写 Task032 Hybrid FEM–Modal 主路线。

---

# 13. 交付物

代码和轻量文档至少包括：

```text
src/solvers/local_slab_solver.py or equivalent stable abstraction
src/solvers/neural_local_pc.py
benchmarks/neural_pc/export_slab_dataset.py
benchmarks/neural_pc/train_local_pc.py
benchmarks/neural_pc/evaluate_local_pc.py
benchmarks/run_neural_local_pc.py
benchmarks/cases/090_neural_local_pc_acceleration/
config / schema / checksum metadata
unit + MPI smoke tests
```

任务记录至少包括：

```text
docs/para_task001_neural_local_pc_acceleration/outcomes/summary.md
outcomes/changed_files.md
outcomes/experiment_matrix.csv
outcomes/local_action_metrics.csv
outcomes/runtime_breakdown.csv
outcomes/memory_report.md
outcomes/model_and_dataset_provenance.md
outcomes/merge_recommendation.md
review_report_vN.md / response_vN.md
updated docs/development_progress.md
```

---

# 14. 最终分类与合并边界

最终 classification 必须从以下选择：

```text
strong_speed_and_memory_success
speed_success_memory_neutral
memory_success_speed_neutral
engineering_positive_unqualified
local_feasibility_only
numeric_failure
performance_failure
not_feasible_with_current_hardware_or_architecture
```

默认合并边界：

- 可复用且不改变默认的 local solver abstraction、telemetry、dataset schema、tests 和文档可选择性合并；
- NN runtime backend 只有通过 h5/h3 Gate、可维护且无隐式依赖时才可考虑选择性合并；
- checkpoint、训练数据和失败 solver profile 留在 artifacts/research branch；
- 未通过 final ChatGPT review 前不进入 `master`；
- ordinary default 始终保持不变。

---

# 15. 新机器最短启动流程

```powershell
cd <parent-directory>
git clone <MyFEniCS-origin-url> MyFEniCS_neural_pc
cd MyFEniCS_neural_pc
git fetch origin --prune
git checkout ChatGPT/20260715-para-task-neural-local-pc
git pull --ff-only origin ChatGPT/20260715-para-task-neural-local-pc
git status --short
git rev-parse HEAD
git remote -v
```

开发过程中只向该分支提交和 push：

```powershell
git add <intentional-files>
git commit -m "..."
git push origin ChatGPT/20260715-para-task-neural-local-pc
```

不得直接 push `master`。若需要同步主线，只能在记录清楚 base/head 后显式 merge/rebase，并重新运行相关 smoke；不得无记录地覆盖并行分支历史。
