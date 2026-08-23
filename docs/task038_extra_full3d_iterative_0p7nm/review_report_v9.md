# Task038-extra Review Report V9：以最终真残差与物理正确性为权威的固定内存长 Krylov 路线

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V9
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = fe72e847208e1da93d88829fc383cdfbf0527015
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 91 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v8.md
reviewed_summary                        = docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v8.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
V8_M0_result                            = ACCEPTED_HARD_STOP_UNDER_V8_CONTRACT
V8_M0_internal_MPI_identity             = remains failed/diagnostic; not reclassified
orientation_placement_fix_9f            = ACCEPTED_RESEARCH_FIX_WITH_SCOPE_LIMIT
additive_LOR_HX_v2                      = CLOSED; do not reactivate
multiplicative_LOR_HX_v1                = AUTHORIZED_FOR_FINAL_RESIDUAL_MEMORY_FIRST_LANE
scalar_MPC_owner_difference             = KNOWN_PARTITION_ROBUSTNESS_DEBT
primary_authority                       = exact A, exact b, explicit true residual, official physics, process-tree memory
PC_internal_MPI_identity                = diagnostic unless it breaks linearity/finite/primal-validity/final correctness
production_Krylov                       = right-preconditioned GMRES
production_restart                      = 20, fixed
residual_replacement_period             = 20 iterations, fixed
continuous_authorized_batch             = P0 through P8 below, conditional on every prior Gate
mandatory_review_stop                   = after P8 or any earlier hard stop
p6_h10_final_physical_solve             = conditionally authorized
p6_h10_official_recovery                = conditionally authorized after final residual pass
p6_h5_scaling                           = conditionally authorized under 12 GB development-machine envelope
0p7nm_2TiB_capacity_audit               = conditionally authorized; no full 0.7 nm PDE
full_0p7nm_PDE                          = forbidden
ordinary_default_change                 = forbidden
master_merge                            = forbidden
response_required                       = response_v9.md
```

本 Review 接受用户明确冻结的优先级：

> 当前第一目标是在固定内存内得到最终正确解；迭代次数与 wall time 暂时是第二优先级。只有正确性、物理和完整资源闭合后，才研究如何减少迭代次数。

因此，本轮不会把“80 步没有通过”或“预条件器内部 MPI1/MPI2 中间向量不完全相同”单独作为最终求解失败。新的权威链为：

```text
exact operator / RHS identity
→ 固定内存长 Krylov
→ explicit true residual
→ release-before-recovery
→ official E/H、R/T/A、A_volume、channels
→ direct authority / MPI observable comparison
```

旧结论全部保留，不能被本 Review 改写：

- 旧 L2 one-apply `rho=1.7348663090876784 > 0.45` 仍是旧合同下的永久 FAIL；
- multiplicative-v1 未通过旧 80-step performance qualification 的事实仍保留；
- additive-v2 的 small MPI2 Krylov qualification 仍正式关闭；
- V8 M0 的 exact-nodal/internal-component MPI pair Gate 仍是旧合同下的 hard stop；
- 本 Review 只建立一个新的、面向最终正确性的 prospective 合同。

---

# 1. 对 Response V8 与 M0 的审阅

## 1.1 接受的事实

V8 M0 使用 p2/h50 positive auxiliary 小案例对 MPI1/MPI2 分区后的 LOR/HX 路径进行了拆分诊断。以下结果接受为正式事实：

| 对象 | MPI1/MPI2 canonical relative | 审阅结论 |
|---|---:|---|
| high source | `1.417734557397384e-15` | exact RHS identity pass |
| high residual / exact high action | `1.6029978812022376e-15` | exact positive operator identity pass |
| high→LOR low input | `1.6864438658655413e-15` | transfer input identity pass |
| exact low-order edge correction | `1.5658061021293675e-15` | edge reference pass |
| exact low-order edge action | `1.7783413648977776e-15` | edge action identity pass |
| exact edge-pre result | `1.2841132186933526e-15` | orientation-aware edge-pre pass |
| exact nodal output | `0.03757191918203578` | internal partition dependence remains |

MPI2 原有的 raw edge orientation placement 已被明确识别并窄幅修复：

```text
negative cell-edge references = 92
minus map factors             = 208
old owner roundtrip           = 0.5849607443002511
orientation-aware roundtrip   = 2.060948712431624e-17
```

该修复接受为 research fix；它不自动提升 ordinary default，也不证明全部 scalar MPC/owner algebra 已闭合。

## 1.2 已知的 scalar MPC / owner debt

V8 M0 仍观察到：

```text
remote relation inconsistency                     = 37
exact gradient RHS MPI relative                   = 0.36157950436833775
owner-consistent diagnostic gradient RHS relative = 2.396070826157907e-15
owner-consistent nodal delta relative             = 0.11660480519091415
fixed-lattice node-matrix action relative          = 0.08847380943557186
```

这证明当前 scalar nodal auxiliary route 会随 MPI partition 改变。它必须持续记录为：

```text
partition-robustness / reproducibility debt
```

但它不再单独阻止最终求解，前提是每个 MPI 配置中的 PC 都满足本 Review 的线性、有限、重复、合法 primal 输出合同，并且最终 exact true residual 与 official physics 通过。

## 1.3 最关键的正结果

M0 使用固定：

```text
right GMRES
restart = 20
每 20 步显式重算 true residual
每 20 步 residual replacement
```

得到：

| path | MPI | iterations | final explicit true residual |
|---|---:|---:|---:|
| production multiplicative-v1 | 1 | 62 | `9.276247638965869e-09` |
| production multiplicative-v1 | 2 | 62 | `9.431179719931108e-09` |
| exact-nodal diagnostic | 1 | 82 | `9.510953881688309e-09` |
| exact-nodal diagnostic | 2 | 84 | `9.713792528761725e-09` |

因此已经实测：

> 固定 `restart=20`、不增加 Krylov basis 常驻规模，只增加 restart cycles 和总迭代数，可以在 MPI1/MPI2 下得到最终 `1e-8` 级 explicit true residual。

这正是本轮 memory-first 主线的依据。

## 1.4 为什么 V8 hard stop 仍然保留

V8 明确把 internal component MPI identity 设为 M0 hard Gate。Codex 发现该 Gate 失败后停止 M1–M7，执行行为正确。

本 Review 不重新解释 V8 为 PASS，而是改变未来资格标准：

```text
V8 authority  = internal exact-nodal/component identity
V9 authority  = exact A/b identity + final residual + official physics + complete memory
```

---

# 2. 最终正确性为何可以不要求 PC 内部逐项 MPI 相同

## 2.1 预条件器允许随 partition 改变

对于右预条件 GMRES，不同 MPI 分区可以使用不同的线性预条件器：

```math
A M_1^{-1} y_1 = b,
\qquad
A M_2^{-1} y_2 = b,
```

并定义：

```math
x_i=M_i^{-1}y_i.
```

只要最终使用同一个 exact operator `A` 和 RHS `b`，并满足：

```math
r_i=b-Ax_i,
```

则最终正确性由 `r_i` 决定，而不是由 `M_1^{-1}` 与 `M_2^{-1}` 的中间向量是否相同决定。

## 2.2 跨 MPI action consistency 的 residual-based bound

若 MPI1/MPI2 的 exact RHS identity error 为 `delta_b`，则：

```math
\frac{\|A x_1-A x_2\|}{\|b\|}
\le
\frac{\|r_1\|}{\|b\|}
+
\frac{\|r_2\|}{\|b\|}
+
\delta_b.
```

本 Review 的 checker 必须使用 measured final residual 动态构造 pair bound：

```text
pair_action_limit = rho_MPI1 + rho_MPI2 + rhs_identity + 1e-11
```

对于 physical solve 的 `1e-6` residual Gate，使用：

```text
pair_action_limit = rho_MPI1 + rho_MPI2 + rhs_identity + 1e-9
```

不得继续使用与最终 residual 精度不一致的固定 `1e-10` solution/action pair Gate。

## 2.3 哪些 PC 内部性质仍是 hard Gate

PC 内部 MPI1/MPI2逐项相同不再是 hard Gate，但每个 MPI 配置自身必须满足：

```text
linearity relative              <= 1e-12
repeat relative                 <= 1e-13
all output finite               = true
input unchanged                 = true
high-space primal constraint    <= 1e-12
slave/master closure complete   = true
phase applied exactly once      = true
no high-order global AIJ        = true
no global direct coarse         = true
no FE-sized numeric allgather   = true
```

若当前 scalar MPC/owner debt导致 PC 非线性、nonfinite、输入被修改、输出不属于合法 high-space primal，仍然必须停止。

---

# 3. 冻结的 Krylov 与生命周期合同

## 3.1 唯一 Krylov 配置

```text
KSP                         = right-preconditioned GMRES
restart                     = 20
initial guess               = zero for first segment/cycle
subsequent cycle guess      = previous solution
norm authority              = explicit unpreconditioned true residual
residual replacement        = every 20 iterations
```

禁止在本轮扫描：

```text
restart 10/30/40/80
FGMRES/GCROT/LGMRES/BiCGStab
omega
shift
PCGAMG type/smoother/levels
V-cycle count
HX correction order
additive-v2 or third variant
```

`max_it` 可以比旧任务显著增加，因为固定 restart 下总迭代数主要增加时间，不要求保存不断增长的 Krylov basis。

## 3.2 固定的迭代上限

| 阶段 | restart | total max_it | 成功权威 |
|---|---:|---:|---|
| p2/p3 small positive | 20 | 2,000 | final explicit residual `<=1e-8` |
| p6/h10 positive | 20 | 5,000 | final explicit residual `<=1e-8` |
| p6/h10 physical MPI1 | 20 | 10,000 | final explicit residual `<=1e-6` |
| p6/h10 physical MPI2 | 20 | 15,000 | final explicit residual `<=1e-6` |

80、100、200、500、1000、2000 等 checkpoint 只用于性能画像，不是 correctness hard Gate。

达到总迭代上限仍未通过时，必须写：

```text
FAILED_AT_FIXED_MEMORY_ITERATION_CAP
```

不得根据下降趋势外推为 PASS。

## 3.3 每个 restart cycle 的操作顺序

每 20 步必须：

```text
完成当前GMRES cycle
→ 销毁本cycle KSP/Krylov basis
→ 用exact A重新计算 r=b-Ax
→ 记录explicit true residual
→ 检查finite、memory、swap和provenance
→ 若未收敛，用当前x开始下一cycle
```

不得让多个 cycle 的 basis 同时存活。

## 3.4 checkpoint / resume

每 200 步或每 10 个 restart cycles 保存一次 solution-only checkpoint：

```text
solution vector / canonical packet
iteration count
explicit true residual
input SHA
physical-model SHA
operator/source SHA
MPI size and ownership identity
checkpoint SHA256
```

恢复时只允许：

```text
读取solution
→ 重新构造exact A和PC
→ 重新计算explicit true residual
→ 从新的restart20 cycle继续
```

禁止保存或恢复 Krylov basis。

checkpoint 不能用于隐藏内存峰值：

- correctness 可以由多个连续 provenance segment 构成；
- complete-workflow `<2 GB` production qualification 仍优先要求一次 uninterrupted authority run；
- 若只完成 segmented run，分类为：

```text
CORRECTNESS_PASS_RESOURCE_SEGMENTED_NOT_FULL_WORKFLOW
```

不得包装成完整生命周期资源 PASS。

---

# 4. 连续授权阶段 P0–P8

```text
P0  authority/checkpoint/lifecycle contract
→ P1 p2/p3 memory-first small qualification
→ P2 p6/h10 cold setup and repeated-apply resource qualification
→ P3 p6/h10 positive long Krylov
→ P4 p6/h10 exact physical Maxwell MPI1 final solve and recovery
→ P5 p6/h10 exact physical Maxwell MPI2 final solve and cross-MPI physics
→ P6 conditional p6/h5 setup/scaling pilot
→ P7 revised 0.7 nm / 2 TiB capacity audit
→ P8 outcomes/response and mandatory review stop
```

正常通过时不需要在 P0–P8 中间逐阶段等待 ChatGPT。任一 hard Gate 触发时：

```text
保存真实结果
提交轻量records/outcomes
写response_v9.md
推送同一分支
停止等待审阅
```

---

# 5. P0：最终残差权威与长运行基础设施

## 5.1 目标

P0 不运行 heavy PDE。它建立新的 prospective checker 和长运行基础设施，避免把旧 V8 internal-PC Gate 静默删除。

## 5.2 必须实现或更新

```text
final-residual authority checker
residual-based MPI pair bound
restart20 cycle ledger
cycle-boundary process-tree RSS/swap ledger
solution-only checkpoint writer/reader
checkpoint provenance manifest
checkpoint roundtrip checker
```

不得删除 V8 M0 checker 或旧 negative records。

## 5.3 checkpoint 小型资格

使用 p2/h50 MPI1：

```text
运行20步
→ 保存checkpoint
→ 销毁solver对象
→ 重建A/PC
→ 恢复solution
→ 比较恢复前后solution
→ 重算true residual
→ 再运行20步
```

Gate：

```text
checkpoint vector roundtrip relative       <= 1e-13
restart-boundary true residual relative    <= 1e-12
next-cycle first explicit residual relative <= 1e-11
input/operator/source SHA                  exact match
```

## 5.4 P0测试

至少包括：

```text
pair bound unit test
checkpoint corruption fail-closed test
wrong source SHA fail-closed test
wrong MPI size fail-closed test
cycle KSP destruction/lifecycle test
no Krylov basis in checkpoint test
```

P0 失败则停止，不进入 P1。

---

# 6. P1：p2/p3 memory-first small qualification

## 6.1 冻结 cases

```text
p2/h50 MPI1/MPI2
p3/h50 MPI1/MPI2

random
gradient
curl
checkerboard
```

共 16 个 formal cases，按确定性顺序执行。

## 6.2 唯一 PC

使用当前 orientation placement fix 后的：

```text
multiplicative LOR-HX v1
```

additive-v2 继续关闭。不得修改：

```text
edge Jacobi omega=2/3
correction order
one shared scalar PCGAMG hierarchy
one V-cycle per nodal correction
G/Pi definitions
B_h/B_L coefficients
```

## 6.3 每案 numerical Gate

```text
final explicit true residual <= 1e-8
iterations                   <= 2,000
finite                       = true
PC linearity                 <= 1e-12
PC repeat                    <= 1e-13
input unchanged              = true
high primal constraint       <= 1e-12
```

旧 one-apply `rho` 继续记录为 diagnostic，不再作为 hard Gate。

## 6.4 MPI pair Gate

同 degree/source 的 MPI1/MPI2 必须满足：

```text
exact source identity <= 1e-12
exact B_h action identity <= 1e-12
both final true residuals <= 1e-8
final action pair relative <= rho1 + rho2 + rhs_identity + 1e-11
```

以下只作 diagnostic：

```text
solution-vector relative
residual-vector-to-residual-vector relative
PC internal gradient/Pi/nodal pair relative
iteration-count ratio
```

## 6.5 资源与时间分类

P1 不以 80 步或 wall time裁决正确性，但必须记录：

```text
iter20/80/200/500/1000/2000 true residual
matvec count
PC apply count
cycle wall
cycle-boundary RSS
swap
checkpoint count
```

若任一案在 2,000 步内不能通过，当前 multiplicative LOR-HX memory-first route 关闭，不进入 P2。

---

# 7. P2：p6/h10 cold setup 与 repeated-apply 资源资格

## 7.1 模型身份

```text
wavelength = 13.5 nm
p          = 6
h          = 10 nm anchor
MPI        = 1 first
complex128
current physical/material/input identity
```

## 7.2 必须同时建立

```text
high-order full-space matrix-free positive action
high-order exact physical action = volume + streaming Fourier-DtN
p-refined lowest-order LOR topology
LOR edge AIJ
scalar nodal AIJ
G/Pi maps
one scalar PCGAMG hierarchy
multiplicative-v1 PC
restart20 long-run shell/checkpoint infrastructure
```

## 7.3 资源 Gate

正式使用 process-tree/cgroup authority：

```text
warning                           = 1,800,000,000 B
hard stop                         = 2,000,000,000 B
cold setup process-tree peak      < 2,000,000,000 B
post-setup retained process-tree  < 1,800,000,000 B
process-tree/cgroup swap delta    = 0 B
worker/rank VmSwap                = 0 B
```

达到 hard line 后必须终止完整进程组；OOM kill不是合格停止。

## 7.4 repeated-apply资格

完成 setup 后，对一个固定 deterministic residual 连续执行 10 次 PC apply：

```text
finite every apply
repeat relative <= 1e-13
input unchanged
PC object count constant
no retained vector/matrix growth
no global high-order AIJ
authorized scalar hierarchy only
```

one-apply contraction不作 Gate。

## 7.5 exact operator fresh identity

在当前 source SHA 下重新证明：

```text
positive B_h action repeat <= 1e-13
physical A action repeat <= 1e-13
physical volume+DtN action matches frozen T2/T3 authority within current comparator
```

P2资源或代数 Gate失败则停止。

---

# 8. P3：p6/h10 positive auxiliary 长 Krylov

## 8.1 cases

只运行两个最有诊断价值的 source：

```text
random
gradient
```

不为 positive preflight 增加更多 source，以便尽快进入 physical authority。

## 8.2 配置

```text
right GMRES
restart=20
max_it=5,000
explicit residual replacement every20
solution checkpoint every200
```

## 8.3 Gate

每案：

```text
final explicit true residual <= 1e-8
process-tree peak < 2,000,000,000 B
swap = 0
no memory growth beyond fixed live-set
```

80、200、500、1000等残差仅作为性能画像。

P3 任一案到 5,000 步仍未通过，则停止；不得增加 restart或修改PC参数。

---

# 9. P4：p6/h10 exact physical Maxwell MPI1 最终正确求解

## 9.1 精确问题

```text
A = matrix-free full-space Maxwell volume action
  + dynamic streaming Fourier-DtN top/bottom action

b = current physical RHS authority
```

不允许用 positive `B_h`、shifted operator或近似 DtN 替代 exact true residual。

## 9.2 配置

```text
MPI        = 1
right GMRES
restart    = 20
max_it     = 10,000
residual replacement every20
checkpoint every200
zero initial solution unless resuming a hash-valid checkpoint
```

## 9.3 成功 Gate

```text
final explicit true residual <= 1e-6
complete solve process-tree peak < 2,000,000,000 B
swap = 0
finite = true
input/operator/provenance closed
```

不得因为下降缓慢而提前停止；只允许以下停止：

```text
final residual pass
fixed total iteration cap reached
2GB hard stop
swap/nonfinite
provenance or checkpoint corruption
external interruption with valid checkpoint
```

## 9.4 release-before-recovery

残差通过后，必须：

```text
保存最小 recovery packet
→ 销毁GMRES KSP/PC/basis
→ 销毁不再需要的LOR/GAMG online workspace
→ 确认process-tree RSS下降
→ recovery/postprocess
```

不得让 Krylov basis、PC hierarchy临时副本和 recovery field同时形成不必要的峰值。

## 9.5 official physics

只在 final residual pass 后恢复并报告：

```text
complex E
complex H
R/T/A
A_volume
12+12 diffraction channels
selected near-field values
energy closure
```

必须使用 Task038-extra 已冻结的 direct authority和 comparator；不得临时放宽物理 tolerance。

完整工作流资源 Gate取以下最大值：

```text
max(cold setup, long solve, release transition, recovery, postprocess)
< 2,000,000,000 B
```

若数值收敛但 recovery使完整工作流超过2GB，分类为：

```text
NUMERICAL_PASS_RESOURCE_FAIL
```

不能称 production pass。

---

# 10. P5：p6/h10 MPI2 最终求解与物理一致性

P4全部通过后才运行 MPI2。

## 10.1 配置

```text
MPI        = 2
right GMRES
restart    = 20
max_it     = 15,000
residual replacement every20
checkpoint every200
```

允许 MPI2迭代次数明显高于 MPI1；迭代数不作最终 correctness Gate。

## 10.2 exact identity Gate

在正式求解前：

```text
physical RHS canonical MPI1/MPI2 relative <= 1e-12
exact A deterministic action MPI1/MPI2 relative <= 1e-12
physical/input/source hashes exact match
```

## 10.3 每个 MPI 运行自身 Gate

```text
final explicit true residual <= 1e-6
process-tree peak < 2,000,000,000 B
swap = 0
```

## 10.4 cross-MPI Gate

```text
final action pair relative
<= rho_MPI1 + rho_MPI2 + rhs_identity + 1e-9
```

此外，MPI1和MPI2必须分别通过同一个 direct-authority physics comparator：

```text
E/H selected values
R/T/A
A_volume
12+12 channels
energy closure
```

最终 solution-vector relative和两个小 residual vectors的相互relative只作diagnostic，不得单独否定已经通过exact residual和physics的解。

如果 MPI2 在15,000步内仍不能达到 `1e-6`，分类为：

```text
MPI2_FIXED_MEMORY_CORRECTNESS_NOT_REACHED
```

并停止后续h5运行。

---

# 11. P6：条件 p6/h5 setup/scaling pilot

P4和P5全部通过后才允许P6。

## 11.1 运行前容量预检

使用p6/h10实测对象字节和peak分解预测p6/h5：

```text
central predicted peak < 10,000,000,000 B
hard predicted peak    < 11,500,000,000 B
MemAvailable和系统余量合格
一次只运行一个heavy job
```

预测达到11.5GB则不运行heavy case，只保留derived audit。

## 11.2 development-machine Gate

```text
warning = 10,000,000,000 B
hard    = 12,000,000,000 B
swap    = 0
```

## 11.3 运行范围

只执行：

```text
cold setup
10次fixed PC apply
20步right-GMRES physical screen
release
```

不要求h5最终收敛，不执行official recovery。

必须得到：

```text
actual topology/rows/NNZ
setup peak
retained peak
per-apply workspace
restart20 vector bytes
h10→h5 measured exponent
```

这些是容量模型数据，不是h5 solver pass。

---

# 12. P7：更新 0.7 nm / 2 TiB 容量审计

不运行完整0.7 nm PDE。

## 12.1 必须使用的输入

```text
正式0.7nm材料与physical hash
actual external channel inventory
propagating/near-cutoff/evanescent counts
accuracy-qualified p/h assumptions
p6/h10 measured full workflow
p6/h5 measured或controlled-not-run结果
LOR topology/matrix/hierarchy实测
restart20 fixed Krylov live set
checkpoint/recovery live set
MPI duplication
lifecycle overlap
```

## 12.2 必须拆分

```text
mesh/space/MPC
matrix-free high-order action
streaming DtN
LOR edge/nodal matrices
G/Pi/maps
PCGAMG hierarchy
restart20 Krylov vectors
checkpoint buffers
solution/recovery packet
E/H recovery/postprocess
MPI ownership/ghost duplication
allocator/JIT reserve
system reserve
```

## 12.3 三情景

```text
optimistic
central
conservative
```

每个数字标记：

```text
measured
derived
predicted
budget
not_run
controlled_stop
```

不得使用：

```text
p6/h10 <2GB × 1000 = 自动2TB可行
```

作为最终结论。external channels、hierarchy growth、MPI duplication和recovery必须单独建模。

---

# 13. P8：outcomes、response 与停止

必须更新或创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_authority_contract.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_hx_p6h10_setup_v2.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_hx_p6h10_positive_longrun_v2.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_hx_p6h10_physical_longrun_v2.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_hx_p6h10_mpi2_v2.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_hx_h5_scaling_v2.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/feasibility_0p7nm_2tib_v3.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
docs/task038_extra_full3d_iterative_0p7nm/response_v9.md
```

未运行项必须明确标记 `not_run_by_gate`，不能保留空表造成歧义。

完成P8后提交、推送同一分支并停止等待ChatGPT审阅。

---

# 14. Hard stop 条件

任一条件触发即保存证据、写response并停止：

```text
exact A/RHS identity失败
PC非线性、nonfinite、input mutation或primal constraint不闭合
checkpoint identity/provenance失败
p2/p3任一案达到2000步仍不收敛
p6 positive达到5000步仍不收敛
p6 physical MPI1达到10000步仍不收敛
p6 physical MPI2达到15000步仍不收敛
process-tree达到对应hard memory line
process-tree/rank swap非零
worker/ABI/source identity不合格
physical comparator失败
recovery/postprocess导致完整workflow超过2GB
```

以下不再单独触发hard stop：

```text
PC内部gradient/Pi/nodal MPI1/MPI2中间向量不同
80步未达到最终残差
wall time很长
MPI2迭代数高于MPI1
两个已经很小的residual vectors彼此relative接近1
```

---

# 15. 禁止事项

本轮禁止：

```text
增加GMRES restart
扫描Krylov方法
恢复additive-v2
产生第三个HX变体
调omega/shift/GAMG/V-cycle
恢复Candidate A/B/C
恢复trace-harmonic/local-spectral/regional-top coarse
形成high-order global AIJ
形成global direct coarse solve
FE-sized numeric allgather
用分段worker重启隐藏RSS增长
在residual通过前输出official physics
运行完整0.7nm PDE
修改ordinary default
merge/rebase master
amend/force push
删除或弱化旧negative
```

---

# 16. Response V9 必须回答

1. branch、HEAD、base、upstream、ahead/behind、worktree、ABI、threads与资源身份；
2. V8 M0 negative、orientation fix和scalar owner debt是否原样保留；
3. P0 checkpoint与pair-bound contract是否通过；
4. p2/p3 16案的最终true residual、iterations、cycle数、matvec/PC count；
5. 每个MPI pair的exact source/action identity与residual-based final action bound；
6. p6/h10完整LOR/GAMG inventory、cold peak、retained和swap；
7. p6 positive longrun的完整cycle-boundary residual history；
8. p6 physical MPI1最终residual、全过程peak、release-before-recovery与official physics；
9. p6 physical MPI2最终residual、全过程peak、action bound与physics comparator；
10. checkpoint/resume是否使用；若使用，是否仅有segmented resource evidence；
11. h5是否运行；若未运行，预测为何触发stop；
12. 更新后的0.7nm optimistic/central/conservative 2TiB审计；
13. 所有failed/not_run/controlled_stop分类；
14. tests、commands、records、raw hashes与provenance；
15. 下一步是性能优化、资源重构、继续正确性开发还是关闭当前family。

---

# 17. 最终技术判断

当前证据已经说明：

```text
exact high-order problem MPI identity      = 正信号
high↔LOR transfer与edge orientation       = 正信号
restart20下MPI1/MPI2最终1e-8收敛          = 正信号
scalar nodal auxiliary内部MPI一致性       = 未闭合
p6/h10 setup与最终physical solve          = 未运行
完整workflow <2GB                         = 未证明
```

本 Review 的核心判断是：

> 对预条件器而言，partition-dependent并不等于最终解错误。只要exact operator与RHS相同，PC在每个MPI配置内保持线性、有限和合法，最终explicit true residual与official physics才是正确性权威。

因此下一步不再继续无限修复scalar MPC中间向量，而是用固定`restart=20`、长`max_it`、residual replacement、checkpoint和严格2GB watchdog，直接验证能否得到p6/h10最终正确物理解。

如果这条路线最终通过，它首先证明的是：

```text
fixed-memory correctness is achievable
```

迭代次数和wall time可能很大；后续任务再研究：

```text
partition-robust scalar auxiliary space
geometric multigrid
better coarse correction
更少迭代次数与更短时间
```

如果在固定迭代上限、2GB或official physics Gate失败，则真实 blocker将被明确定位为：

```text
convergence under fixed memory
resource capacity
或 physical correctness
```

而不再停留在预条件器内部中间量是否跨MPI逐项相同的问题上。
