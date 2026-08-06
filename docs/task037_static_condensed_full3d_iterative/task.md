# Task037：p6/h10 静态凝聚 Full3D 迭代求解器开发

## 0. 任务身份

```text
task                         = Task037
task_kind                    = SOLVER_DEVELOPMENT
status                       = READY_FOR_CODEX_EXECUTION
base_master_sha              = f8fab5e12a4cc33cd60dc96d40f628caca446b58
working_branch               = codex/20260803-task37-matrix-free-iterative-development
direct_master_write          = forbidden
merge_to_master              = not_authorized
ordinary_default_change      = forbidden
primary_scope                = static-condensed Full3D iterative solver
frozen_physics               = 13.5 nm / 10 deg grazing / phi=0 / S polarization
frozen_discretization        = p6 Nedelec / h10 / Case096 exact configuration
Hybrid_iterative             = out_of_scope; deferred to Task037b
actual_h_or_p_adaptivity     = out_of_scope
0p7nm_PDE                    = out_of_scope
RCWA                         = out_of_scope
new_direct_port_basis        = forbidden
surrogate_or_inversion       = out_of_scope
new_external_dependency      = forbidden
```

Task037 只开发 **静态凝聚 Full3D 的低内存迭代求解器**。必须先在冻结的 p6/h10、
13.5 nm、10° 掠射、S 偏振案例上建立可复核的数值收敛和资源证据，再考虑真正的
matrix-free fine action。

本任务不开发 Hybrid 迭代法。原始 modal Hybrid、strong-trace Hybrid、exact FE trace-chain
及 M120 coarse/deflation 的应用全部留给后续 Task037b。Task037 的 Full3D 迭代基础设施必须
独立可用，不能以 Hybrid 成功为前提。

Task037 也不实际运行 local-h、variable-p、hanging-node 或 hp controller；但所有新增 iterative
core API 必须避免写死 p6、h10、固定行数和连续 row range，使未来 hp 任务可以替换 operator、
subdomain 和 transfer 实现，而不重写外层 FGMRES、残差、R/T/A、遥测和生命周期框架。

---

## 1. 继承基线与 Task036 合入审计

### 1.1 Git 身份

Task037 空分支已经从已推送的 `origin/master` 创建，并在任务书创建前满足：

```text
master SHA                   = f8fab5e12a4cc33cd60dc96d40f628caca446b58
Task037 branch SHA           = f8fab5e12a4cc33cd60dc96d40f628caca446b58
ahead / behind               = 0 / 0
ordinary default             = unchanged
Task037 implementation       = not started before this task.md
```

所有代码、测试、记录和文档只提交并推送到 Task037 分支。不得直接写入或推送 `master`。

### 1.2 Task036 选择性合入的已知状态

Task036 已按 V8 分四个提交选择性整合：

```text
7735a2617d18fe5f869331a90d47ec16632fd8d3
    Full3D correctness / telemetry / lifecycle hardening

a741ad1b5cfb579e2667600bcc6497ec5c4f23d9
    Hybrid interface safety / exact conormal / beta identity / fail-closed

4c9e1b9cedd4b04d65824698202c9fff96f3a0dc
    strong-trace and exact-trace research-only oracles

b615a130d7c34060a3445c352c1f683bbf3aa23f
    controlled-negative closeout documentation
```

最终 handoff 文档提交为：

```text
f8fab5e12a4cc33cd60dc96d40f628caca446b58
```

被 V8 禁止的 B1/C1 mode-pool、capacity、POD 和 96-RHS 大型 runner 没有进入 master；
strong-trace 保持 `research_only` 与显式 opt-in。

需要诚实保留的测试边界是：Task036 选择性整合已经通过 focused tests、MPI recursion、两项
轻量 Full3D PDE smoke、Ruff/compileall/diff-check 和文档/JSON 检查，但当次 combined pytest
在 41 passed 后被用户中断，小时级 full repository pytest 为 `cancelled / not_run`，且 GitHub
没有可用 CI status。Task037 不得把这项未完成检查写成 PASS。

### 1.3 Task037 Stage 0 继承 Gate

开始修改 iterative solver 前，先生成：

```text
docs/task037_static_condensed_full3d_iterative/outcomes/
    inherited_baseline_audit.md
```

至少记录：

- 当前 branch / HEAD / upstream / clean status；
- PETSc scalar/index ABI、DOLFINx/Basix/PETSc/SLEPc 版本；
- Task036 黑名单 capacity/POD runner 未进入当前分支；
- strong-trace/exact-trace 仍为 research-only；
- ordinary default 未改变；
- 下列 focused baseline tests 的原始命令、exit code 和结果；
- full-suite 遗留状态为 `not_completed_before_Task037`，不得伪装成继承 PASS。

编码前最低 focused baseline：

```text
src/test/test_14_stage4_dtn_modes.py
src/test/test_28_direct_memory_telemetry.py
src/test/test_29_hcurl_multilevel.py
src/test/test_30_task031_contract.py
src/test/test_68_task033_full3d_watchdog.py
src/test/test_80_task034_mpi_identity.py
src/test/test_115_task035b_assembly_time_condensation.py
src/test/test_179_task035b_hybrid_static_condensation.py
src/test/test_181_task035c_p6_h10_runner_gates.py
src/test/test_195_task036_mumps_factor_nnz.py
src/test/test_196_task036_forward_solver_hardening.py
```

任何继承 baseline assertion failure 必须先修复或明确停止；不得在已知回归上继续开发。

---

## 2. 冻结物理、离散与直接法权威

### 2.1 物理与网格身份

Task037 所有正式 heavy run 必须精确复用 Case096 p6/h10 Full3D static authority 的配置，
不得只根据“h10”重新猜测轴向/横向 cell counts：

```text
geometry / material / period  = Case096 frozen target
wavelength                    = 13.5 nm
incident theta from normal    = 80 deg
incident grazing              = 10 deg
incident phi                  = 0 deg
polarization                  = S
boundary                      = double Floquet + auxiliary Fourier-DtN
DtN mode/order identity       = Case096 frozen identity
Nedelec degree                = 6
mesh target / topology        = Case096 p6/h10 exact configuration
assembly backend              = assembly_time_static_condensed
scalar                        = complex128
initial authority MPI         = 8
```

不得修改材料、几何、入射、DtN 阶数、quadrature、Floquet phase、static-condensation
approximation space 或 official R/T/A 定义来改善迭代收敛。

### 2.2 历史 direct reference

Case096 的冻结历史权威为：

| 指标 | Full3D static p6/h10 |
|---|---:|
| full FE DoFs | 173,882 |
| active FE trace rows | 51,192 |
| augmented rows | 51,272 |
| matrix NNZ | 41,989,040 |
| MUMPS factor NNZ | 212,343,992 |
| simultaneous peak | 14.722 GiB |
| total wall | 260.74 s |
| significant powers | 12 / 12 pass |
| significant complex amplitudes | 12 / 12 pass |

逐通道验收必须读取：

```text
benchmarks/cases/096_hybrid_channel_memory_closure/
    records/p6_h10_mpi8_six_path_v1.json
```

official complex-amplitude field 固定为：

```text
outgoing_amplitude_at_boundary
```

不得重新选择 reference plane，也不得用总 R/T 接近掩盖弱通道复振幅失败。

### 2.3 当前源码 direct authority

历史 Case096 只提供 acceptance bands，不能替代当前 Task037 源码的直接法权威。Stage F0
必须在当前 clean Task037 SHA 上 **只运行一次** p6/h10 Full3D static direct：

```text
Task037 direct authority v1
```

必须记录：

- exact config/mesh/axis counts；
- active/carrier/trace/augmented rows；
- matrix/factor NNZ 与 corrected-count source；
- true residual；
- R/T/A 与能量闭合；
- 全部 12 个 significant powers 和 boundary complex amplitudes；
- active trace solution vector 与 recovered full FE vector 的 SHA/shape；
- setup/factor/backsolve/recovery/RTA wall；
- external simultaneous process-tree RSS/PSS/USS/swap；
- source SHA、command、image digest 和 clean status。

当前 direct result 必须通过 Case096 冻结通道合同。若不通过，停止 Task037 iterative 开发，
先分类为 inherited/current-source correctness regression；不得用旧 direct vector 继续。

不要求重跑 34 GiB 的 p6 standard-full 路径。

---

## 3. 数学求解对象

静态凝聚先在每个 p6 Nédélec 单元内部消去 cell-interior DoFs，只保留 Floquet 消元后的
独立 edge/face trace rows。加入 auxiliary DtN 后，增广系统写成：

```math
\begin{bmatrix}
F & C\\
D & H
\end{bmatrix}
\begin{bmatrix}
u\\a
\end{bmatrix}
=
\begin{bmatrix}
f\\g
\end{bmatrix}.
```

其中：

- $u$：约 51,192 个 static active FE trace unknowns；
- $a$：约 80 个外部 Fourier-DtN auxiliary unknowns；
- $F$：static-condensed Full3D FE trace operator；
- $H$：小型 auxiliary block；
- $C,D$：FE trace 与外部通道的稀疏耦合。

外层迭代必须求精确 condensed system：

```math
S u = b_c,
\qquad
S = F-CH^{-1}D,
\qquad
b_c=f-CH^{-1}g.
```

收敛后恢复：

```math
a=H^{-1}(g-Du),
```

再使用 assembly-time static-condensation recovery 恢复 p6 cell-interior 场。

Task037 不允许把 $H^{-1}$、DtN mode set 或 interior recovery 改成新的近似来换取收敛；
近似只允许出现在 preconditioner 中，outer operator 必须与 direct authority 同一离散。

---

## 4. 代码架构原则

### 4.1 允许的最小抽象

建议在现有 `src/solvers/` 中提取或新增职责单一的组件，名称可调整，但职责必须分离：

```text
StaticCondensedStage4System
    只负责 p/h-agnostic static-condensed Stage4 operator/RHS/recovery identity

ActiveTraceSupportMap
    physical cells/entities -> constrained active trace rows

StaticTraceSubdomainPartition
    基于物理 cell support 构造 z-slab overlap row sets

StaticCondensedFineAction
    assembled 或 local-Schur matrix-free fine action

StaticCondensedTwoLevelPc
    local slab smoother + coarse correction
```

禁止创建通用 plugin framework、solver registry、campaign engine、自动调参器或新的外部 package。
优先复用：

```text
src/solvers/condensed_dtn.py
src/solvers/physical_slab_two_level.py
src/solvers/mpc_form_action.py
src/solvers/hcurl_assembly_time_condensation.py
src/solvers/stage4_runtime.py
benchmarks/run_workstation_iterative.py
```

但不得在历史 p2 runner 中堆积大量 `if degree == 6` 特判。若 p2 与 p6 static 路径共享核心，
应提取小型 solver component，由历史 runner 和 Task037 thin runner 分别调用。

### 4.2 为未来 hp 保留的强制边界

Task037 正式运行仍只有 p6/h10，但新增 solver core 必须满足：

- 不硬编码 `degree=6`；
- 不硬编码 `h=10`；
- 不硬编码 `51192`、`51272` 或任何 authority row count；
- 不用连续 row ranges 代表物理 slab；
- subdomain rows 必须由 physical owned cells、trace entities 和 `TraceConstraintMap` 推导；
- local tensor/factor cache identity 必须包含 element signature、degree、cell widths、orientation、
  material/frequency/Floquet/constraint identity；
- coarse vectors必须通过明确 prolongation/restriction进入 active trace space，不能直接写 p6
  coefficient indices；
- operator 和 PC API 必须读取实际 active/carrier/trace/augmented row semantics；
- 增加一个 synthetic nonuniform-support test，证明 partition/PC setup 不依赖固定 cell count、
  固定每单元 local dimension或连续 row ordering。

本任务不实现真实 variable-p、hanging-node、nonmatching hexa 或 hp controller。

### 4.3 迭代合法性

外层固定为：

```text
right-preconditioned FGMRES
```

当前 local PC 允许内部固定步数 GMRES、局部 shift 或可变 apply，因此普通 GMRES、TFQMR、BCGS
不得绕过现有线性/确定性认证。若尝试非 FGMRES，必须先通过现有 PC certification，并作为
研究对照，不能替代 FGMRES 主线。

全局 MUMPS/SuperLU factor 禁止出现在 iterative solve 路径中。允许：

- 小型 $H$ block 的精确求解；
- 小型 coarse operator 的精确求解；
- local slab submatrix 的 ILU/局部 factor；
- current-source direct authority 的独立参考运行。

迭代失败时不得自动 fallback 到 global direct 后仍写 iterative success。

---

## 5. 强制阅读范围

编码前必须阅读并在 `inherited_baseline_audit.md` 中概括：

```text
docs/iterative_solver_ports.md
notes/theory/iterative_solver_and_preconditioner.md
benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md
benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md
benchmarks/cases/096_hybrid_channel_memory_closure/README.md

docs/task036_forward_solver_bugfix_hardening/outcomes/final_summary.md
docs/task036_forward_solver_bugfix_hardening/review_report_v8.md

benchmarks/run_workstation_iterative.py
benchmarks/run_task031_memory_forensics.py
benchmarks/task035c_p6_h10_gates.py

src/solvers/stage4_runtime.py
src/solvers/condensed_dtn.py
src/solvers/mpc_form_action.py
src/solvers/physical_slab_two_level.py
src/solvers/hcurl_multilevel.py
src/solvers/hcurl_assembly_time_condensation.py
src/solvers/common_3d_case_flow.py
src/solvers/common_3d_solve.py
src/solvers/dtn_port_3d.py
```

同时阅读所有直接覆盖上述模块的 tests，特别是 Task27–31、Task035b/c 与 Task036 hardening tests。

编码前再生成：

```text
docs/task037_static_condensed_full3d_iterative/outcomes/
    iterative_port_matrix.md
```

表格至少包含：

```text
component
p2 iterative current implementation
p6 static direct current implementation
can_reuse_directly
required adapter/change
risk
unit/MPI/PDE test
future hp impact
```

不得先复制旧 runner 再逆向解释。

---

## 6. 分阶段执行计划

## F0：当前源码 direct authority 与基线冻结

完成第 2.3 节的一次 p6/h10 static direct run，生成：

```text
benchmarks/cases/100_static_condensed_full3d_iterative/
    records/task37_direct_authority_v1.json
```

以及 thin README/config/expected files。Case ID 冻结为：

```text
100_static_condensed_full3d_iterative
```

不得复制 Case096 全部 heavy evidence；只引用其 tracked acceptance record。

### F0 Gate

```text
current direct source clean                    = true
reported/full true residual                    = pass
12/12 powers                                   = pass
12/12 boundary complex amplitudes              = pass
R/T/A and energy closure                       = pass
active/carrier/trace/augmented row identity    = pass
external simultaneous memory readable         = true
swap                                            = 0
```

任何一项失败则停止 iterative heavy work。

---

## F1：p6 static iterative algebra port（assembled fine operator）

第一阶段保留已装配的 p6 static-condensed $F$，只移除 global direct factor。这样先回答
“迭代与 PC 是否能收敛”，不要把 matrix-free kernel 和 PC 收敛两个问题混在一起。

必须实现：

1. 在不调用 global direct factorization 的情况下构造 p6 static-condensed Stage4 system；
2. 提取或等价暴露 $F,C,D,H,f,g$；
3. 使用现有 exact condensed action $F-CH^{-1}D$；
4. 恢复 auxiliary $a$、active trace $u$ 和完整 p6 FE 场；
5. reported、condensed true、full augmented true 三种 residual；
6. iterative 与 direct active trace/full recovered vector 比较；
7. official R/T/A 只在 full residual Gate 通过后运行；
8. 所有 solver/factor/object 生命周期和 external simultaneous memory telemetry。

### F1 algebra tests

至少包括：

- tiny p2 standard/static augmented action equivalence；
- p6/h10 assembled static matrix deterministic action；
- exact $H^{-1}$ condensed action vs full augmented block action；
- auxiliary recovery；
- cell-interior recovery；
- MPI2/4 action identity；
- no-global-factor inventory；
- 未收敛时 official R/T/A 为 not_run。

F1 只建立 operator/RHS/recovery，不允许立即开始开放参数 sweep。

---

## F2：trace-aware physical slab partition

现有 p2 physical-slab path从完整 `V.dofmap.cell_dofs()` 构造 subdomains；p6 static system 的
求解 rows 已经是 Floquet 消元后的 active trace rows，不能直接复用完整 carrier row numbering。

必须构造：

```text
physical owned cells
    -> cell trace original DoFs
    -> TraceConstraintMap expansion
    -> unique static active rows
    -> overlapping z-slab row sets
```

### F2 contract

- 所有 active FE trace rows 至少被一个 slab覆盖；
- 没有 out-of-range rows；
- 周期 master row 可由两侧物理实体贡献，但 global identity唯一；
- overlap 以物理 cell/support 定义，不以 row number 距离定义；
- union、multiplicity、boundary/interior counts 在 MPI 间可复核；
- row support hash 对 MPI partition 不敏感；
- appended DtN auxiliary rows不混入 FE slab factor；
- nonuniform-support synthetic fixture 通过。

生成 compact partition audit，不保存 replicated full adjacency database。

---

## F3：assembled two-level FGMRES 基线

先移植已在 p2 frozen target 验证过的 physical-slab + wave coarse 机制，但不继承其资格化结论。

第一候选参数冻结为：

```text
outer KSP                 = right FGMRES
restart                   = 90
rtol                      = 1e-6
max_it                    = 3000
num physical z slabs      = 16
overlap                   = 0.25 first
local absorption shift    = 0.1
local factor              = ILU(0)
local KSP                 = fixed small-step GMRES
smoothing                 = 2 pre + 2 post
coarse                    = existing 75D Floquet wave basis
storage                   = factor-only where already qualified
```

只允许一个内存候选对照：在 overlap 0.25 已显示有效收敛机制后，再测试 overlap 0.125；
不得同时扫 slabs、overlap、shift、ILU level、restart 和 smoother count。

### F3 漏斗

每个候选依次运行：

```text
20-step smoke
100-step screen
200-step decision screen
full solve only if decision Gate passes
```

20-step Gate：

- 无 NaN/Inf；
- KSP/PC/operator apply 无异常；
- reported 与显式 true residual 同阶且没有虚假收敛；
- residual 未灾难性增长到初始值的 10 倍以上。

100-step Gate：

```text
full/condensed true residual <= 3e-1
and last 40 iterations show net decrease
```

200-step full-solve authorization：

```text
full true residual <= 5e-2
and predicted iterations to 1e-6 <= 3000
and predicted wall <= 7200 s
```

若未通过，不得盲跑 3000 步。

F3 最多允许：

```text
2 candidates × one 200-step screen
1 assembled full solve
```

历史 Jacobi、ordinary ASM/ILU 和 z-slab one-level 200-step negative 不重跑。

---

## F4：低阶 exact-sequence auxiliary coarse（仅在需要时）

若 75D wave coarse 在 F3 不能通过 200-step Gate，或 full solve迭代数/时间明显不可接受，允许
开发唯一一个新的主 coarse family：

```text
p2 H(curl) auxiliary space on the same frozen h10 mesh
```

这不是 hp 自适应，最终物理解仍在 p6/h10 static space中。p2 只用于预条件。

### F4 transfer contract

构造：

```math
P_{2\rightarrow6,\Gamma}:V_{p2}\rightarrow V_{p6,\Gamma}^{active}.
```

要求：

- 使用 H(curl)-一致的 interpolation/projection 与实体 orientation；
- 先映射到 p6 carrier，再提取 trace并应用 p6 `TraceConstraintMap`；
- Floquet phase、edge/face orientation、corner identity 闭合；
- 无零列、无重复列；
- transfer adjoint/action误差 `<=1e-11`；
- p2 coarse operator使用真实 fine action：
  ```math
  A_c=P^HSP;
  ```
- coarse rank/condition 明确；
- MPI2/4 identity；
- 不形成 p6 global direct factor；
- 不把历史失败的 792D p1 coarse 重新命名为成功。

允许组合：

```text
physical slab smoother + 75D wave coarse + p2 auxiliary coarse
```

或在数值上更稳定时合并/正交为一个 coarse basis。必须报告各部分独立增益，不能只展示最终最好值。

若 p2 auxiliary 200-step residual 仍未通过 F3 decision Gate，默认停止 coarse 扩展。
只有当显式诊断证明残差主要位于离散 gradient 子空间时，才允许增加一次 H1 gradient correction；
不得无证据发展完整 HX/AMS framework。

F4 最多允许：

```text
2 short-screen variants
1 full solve
```

---

## F5：static-condensed matrix-free fine action

只有 assembled candidate 已经完成一次数值 full solve并通过全部物理 Gate 后，才进入 F5。
否则不允许用“未来 matrix-free 会改善”掩盖预条件器尚未收敛。

### F5a：local-Schur action oracle

利用 `AssemblyTimeCondensedSystem` 已有：

- cell recovery maps；
- trace constraints；
- condensed tensor/class identity；
- interior solve/recovery metadata；

实现 fine FE action：

```math
y=F_{MF}x
 =\sum_K C_K^H S_K C_K x,
```

其中 $C_K$ 是 local full trace 到 active Floquet trace 的稀疏 expansion，$S_K$ 为单元静态
Schur action。

必须满足：

- 不在每次 apply 调用完整 UFL/FFCx global assembly；
- 不使用 public form-action 每步重复装配作为最终实现；
- 不长期保存每个单元的完整重复稠密方阵；相同 class 应复用；
- owner/ghost/scatter-add 正确；
- complex non-Hermitian action；
- deterministic vectors上：
  ```math
  \|F_{MF}x-F_{assembled}x\|/\|F_{assembled}x\|\le1e-11;
  ```
- serial、MPI2、MPI4 均通过；
- 与 exact DtN condensed shell 组合后 action 仍 `<=1e-11`。

### F5b：assembled-once / released-before-solve profile

第一版 matrix-free profile允许：

1. 先装配 static $F$；
2. 用它建立 local slab factors和必要 coarse data；
3. 资格化 $F_{MF}$；
4. 在 outer KSP 前释放 global assembled $F$；
5. solve 期间 fine action只使用 $F_{MF}$。

该 profile 必须准确命名为：

```text
assembled_setup_then_static_local_schur_matrix_free_solve
```

不得称为“整个作业从未形成 global matrix”。

### F5c：完全不 materialize global F

这是 stretch，不是 Task037 基本完成 Gate。只有 F5b 已通过且整作业峰值仍由 assembled F 与
PC factor共存主导时，才允许研究 sequential local-factor setup / no-global-F builder。
不得因此扩展成新的任务树。

F5 最多运行一个正式 matrix-free full solve。

---

## F6：MPI、资源与最终资格化

正式候选先在开发 MPI 下收敛，再只比较：

```text
MPI4
MPI8
```

不得进行 MPI1/2/16/32 大扫描。

### F6 MPI identity

同一候选在 MPI4/8 必须满足：

- reported、condensed、full residual identity；
- R/T/A 与全部 12 通道在冻结 tolerance 内；
- active trace/recovered field canonical hash/relative error；
- coarse rank、subdomain coverage与 PC action可解释；
- zero swap；
- no partition-sensitive raw-vector hash冒充物理 identity。

### F6 资源 authority

必须使用外部 0.25 s 或更细 simultaneous process-tree sampler，记录：

- worker-tree RSS；
- PSS/USS；
- cgroup current/peak；
- swap；
- setup/operator/PC/KSP/recovery/RTA 分阶段峰值；
- Krylov vector payload；
- local factor NNZ/storage；
- coarse basis/operator storage；
- global assembled F 是否存在/何时释放；
- matrix-free class tensor/cache storage；
- process-group termination结果。

不得求和各 rank 不同时刻的 historical peaks作为正式总峰值。

---

## 7. 数值、通道与资源 Gate

### 7.1 必须同时通过的数值 Gate

```text
KSP converged reason positive
reported relative residual             <= 1e-6
condensed true relative residual       <= 1e-6
full augmented true residual           <= 1e-6
active trace vs direct relative error  <= 1e-5
recovered full FE vs direct            <= 1e-5
12 / 12 significant powers             = pass
12 / 12 boundary complex amplitudes    = pass
R_total / T_total / A_volume            = frozen direct tolerance pass
energy closure                         = frozen direct tolerance pass
swap                                   = 0
official R/T/A only after residual pass
```

如果三残差达到 `1e-6` 但弱通道仍失败，只允许对 **同一已冻结 candidate** 将 rtol 收紧到
`1e-8` 再运行一次；不得同时修改 PC 参数。最终验收以完整通道为准。

### 7.2 内存分级

相对 current-source direct authority约 14.722 GiB：

```text
numerical pass, resource negative       > 10.30 GiB
memory-positive research pass           <= 10.30 GiB  (>=30% reduction)
engineering memory pass                 <= 7.36 GiB   (>=50% reduction)
preferred matrix-free target            <= 5.00 GiB
stretch target                          <= 4.00 GiB
```

不得为了达到内存目标采用不收敛的 Jacobi/弱 PC。

### 7.3 时间分级

以 current-source direct wall 为本轮实测基准：

```text
engineering wall pass                   <= 5 × direct
memory-first qualified-with-cost        <= 10 × direct
hard full-solve wall cap                 = 7200 s
```

低内存但超过 10× direct 只能标为 `numerical_memory_positive_but_throughput_negative`。

### 7.4 最终分类

允许的最终状态：

```text
FULL3D_STATIC_ITERATIVE_ENGINEERING_SUCCESS
    all numerical/channel gates pass
    peak <= 50% direct
    wall <= 5x direct

FULL3D_STATIC_MATRIX_FREE_MEMORY_SUCCESS_WITH_COST
    all numerical/channel gates pass
    peak <= 5 GiB
    wall <= 10x direct

NUMERICAL_SUCCESS_RESOURCE_REVIEW
    all numerical/channel gates pass
    but peak/wall only in review zone

PARTIAL_WITH_CONTROLLED_NEGATIVES
    operator/PC components pass but no full candidate closes all gates

ITERATIVE_MECHANISM_NOT_DEMONSTRATED
    bounded candidate set fails 200-step/full residual gates
```

不得把 action equivalence、低 current RSS、局部 factor构建或 residual monitor下降单独称为 solver success。

---

## 8. 运行预算与停止规则

Task037 禁止开放式自动搜索。重型 p6 运行预算：

```text
current-source direct authority         1
assembled 200-step screens              <= 4 total
assembled full solves                   <= 2 total
matrix-free action qualification        bounded deterministic tests
matrix-free full solve                  <= 1
MPI authority rerun                     one selected candidate on MPI4/8
```

同一个失败 profile不得仅通过微调 restart、shift、overlap、ILU level或slab count重复运行。
每个 candidate必须有预先写入 Git 的参数 identity。

Watchdog：

```text
poll interval                  <= 0.25 s
warning peak                  = 10 GiB
controlled termination peak   = 14 GiB for iterative candidates
swap                           = forbidden
screen wall cap               = 1800 s
full wall cap                 = 7200 s
TERM -> grace -> KILL          = required
residual/progress heartbeat    = required
retry                          = 0 unless a non-numerical infrastructure failure is proven
```

若发生 ABI、source dirty、unreadable sampler、orphan MPI process、NaN、swap 或 hard cap，保存 artifact
并停止；不得自动改代码后继续同一次 campaign。

---

## 9. 测试 Gate

### 9.1 静态检查

每个阶段提交前：

```text
Ruff lint on touched Python files
ruff format --check on new/small extracted modules
compileall on src/ and touched benchmarks
git diff --check
tracked JSON parse
```

### 9.2 Pure / algebra tests

至少覆盖：

- exact condensed block action；
- auxiliary recovery；
- static interior recovery；
- active trace support completeness；
- non-contiguous row ordering；
- synthetic nonuniform support；
- p/h-agnostic API contract；
- slab overlap/multiplicity；
- PC apply finite/deterministic metadata；
- FGMRES/right-PC legality；
- no global factor inventory；
- matrix-free local-Schur action；
- assembled-vs-matrix-free action；
- official R/T/A fail-closed on nonconvergence；
- lifecycle double-destroy/use-after-destroy；
- process-tree termination negative path。

### 9.3 MPI tests

至少包括：

```text
MPI2 static action/recovery
MPI2/4 trace support identity
MPI2/4 coarse transfer/action
MPI2/4 matrix-free action identity
MPI4/8 final candidate identity
```

### 9.4 PDE smoke / authority

- tiny p2 ordinary/static smoke；
- p6/h10 current-source static direct authority；
- p6 20/100/200-step screens；
- 被授权的 assembled full solve；
- 被授权的 matrix-free full solve；
- official 12-channel comparison。

### 9.5 Full repository test

Task036 选择性整合的 full suite 没有跑完。Task037 final response前必须运行一次无 deselect 的
full repository pytest，并使用外部 watchdog。

若超过 3 小时：

```text
full_suite = timed_out / incomplete
```

保存已通过/失败/未运行清单，不能写 PASS，也不能删除或放宽测试。full-suite timeout不自动否决
已经获得的 task-local数值证据，但会阻止 merge-to-master 建议，必须由后续 review决定。

---

## 10. 交付文件

建议新增：

```text
docs/task037_static_condensed_full3d_iterative/
    task.md
    response_v1.md
    outcomes/
        inherited_baseline_audit.md
        iterative_port_matrix.md
        direct_authority.md
        operator_and_recovery_report.md
        trace_partition_report.md
        preconditioner_funnel.md
        matrix_free_report.md
        resource_and_mpi_report.md
        test_summary.md

benchmarks/cases/100_static_condensed_full3d_iterative/
    README.md
    config.json
    expected/gates.json
    records/*.json
```

允许一个 thin task runner，例如：

```text
benchmarks/run_task037_static_full3d_iterative.py
```

核心 operator/PC/recovery 必须位于可复用的 `src/solvers/`，不能只存在于 benchmark runner。
Heavy matrices、fields、timelines、KSP history和raw logs全部留在 gitignored artifacts。

不得新建新的 evidence database、receipt framework、scheduler或通用 campaign package。

---

## 11. 建议提交结构

建议按可审阅能力提交：

```text
docs(task037): freeze baseline and iterative port matrix

feat(task037): expose static-condensed Full3D iterative algebra

feat(task037): add trace-aware physical slab partition

feat(task037): qualify assembled two-level p6 iterative candidate

feat(task037): add low-order auxiliary coarse space        # only if F4 exercised

feat(task037): add static local-Schur matrix-free action   # only after assembled pass

docs(task037): report numerical and resource outcome
```

每个 commit必须可单独测试。禁止一个超大提交同时包含 operator、PC、matrix-free、runner、PDE
结果和全部文档。

---

## 12. 明确禁止范围

Task037 中禁止：

- 修改或开发原始/strong-trace/exact-trace Hybrid solve；
- 将 M120 模态加入 Full3D coarse space；该项留给 Task037b；
- 新的 direct interface compression、POD、discrete-Bloch 或 96-RHS teacher；
- 实际 h/p 自适应、variable-p、hanging-node、local-h campaign；
- 0.7 nm 正式 PDE；
- RCWA/FEM-RCWA；
- surrogate、dataset、DOE 或 inversion；
- 修改 Case096 channel tolerance；
- 减少 DtN modes；
- 改 S 为更容易收敛的物理；
- 改 10° 掠射角；
- 未收敛时输出 official R/T/A；
- global direct fallback冒充 iterative success；
- 自动参数 sweep、retry/fallback 或 24 小时开放运行；
- ordinary default改变；
- 直接提交或合并 master。

---

## 13. Task037 与后续 Task037b 的边界

Task037 的最终可复用产物应是：

```text
static-condensed Full3D operator/RHS/recovery abstraction
trace-aware subdomain partition
FGMRES + two-level PC infrastructure
low-order auxiliary coarse（若需要并通过）
static local-Schur matrix-free fine action（若 assembled candidate先通过）
true-residual / RTA / telemetry / lifecycle authority
```

Task037b 才允许：

- 原始 modal Hybrid block iterative；
- bottom/top static endcap iterative inverse；
- modal block exact solve；
- M120 modal coarse/deflation；
- direct Hybrid vs iterative Hybrid；
- Task036 成功/失败角度的 solver-vs-model分离。

Task037 完成后不得自动创建 Task037b 分支或任务书。

---

## 14. 最终响应要求

完成当前受控阶段后创建：

```text
docs/task037_static_condensed_full3d_iterative/response_v1.md
```

必须包括：

1. branch / source / environment / clean identity；
2. current-source direct authority；
3. assembled operator/recovery正确性；
4. trace support/subdomain contract；
5. 每个预条件器候选的完整20/100/200-step原始结果；
6. 所有 full solve 的三残差、向量差、12通道、R/T/A和energy；
7. assembled与matrix-free action；
8. MPI4/8 identity；
9. simultaneous memory object ledger和wall；
10. 全部测试，包括未完成 full suite；
11. changed files/line counts/commits；
12. 明确最终分类；
13. 未解决问题和 Task037b 建议，但不得开始 Task037b。

无论正负，提交并推送 Task037 分支后停止等待审阅。不得自动合入 master。