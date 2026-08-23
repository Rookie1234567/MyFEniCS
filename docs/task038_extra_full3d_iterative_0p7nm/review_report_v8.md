# Task038-extra Review Report V8：内存优先的长 Krylov 正确性路线

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V8
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = 7628ab1086604bf8872509bce71ddc504a6bac55
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 87 / behind 0
reviewed_response                       = response_v7.md + response_v7_addendum.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
old_L2_one_apply_result                 = PERMANENT_FAIL_UNDER_OLD_GATE
old_80_iteration_qualification          = PERMANENT_PERFORMANCE_FAIL
additive_LOR_HX_v2                      = CLOSED_AS_PRODUCTION_CANDIDATE
multiplicative_LOR_HX_v1                = REOPENED_ONLY_FOR_MEMORY_FIRST_LONG_KRYLOV
primary_objective                       = final correctness under fixed memory
iteration_count_and_wall_time           = secondary optimization objective
production_restart                      = 20, fixed
production_Krylov                       = right-preconditioned GMRES
continuous_authorized_batch             = M0 through M7 below, conditional on every prior Gate
mandatory_review_stop                   = after M7 or any earlier hard stop
full_0p7nm_PDE                          = forbidden
master_merge                            = forbidden
response_required                       = response_v8.md
```

本 Review 接受用户明确调整后的优先级：当前第一目标不是尽快收敛，而是先证明在固定内存内能够得到最终正确解。迭代次数与耗时可以显著增加；只有在正确性和内存闭合以后，才继续研究更快收敛。

这项优先级调整不会删除或改写旧结果：

- 旧 L2 单次修正 `rho=1.7348663090876784 > 0.45` 仍是原合同下的永久 FAIL；
- multiplicative-v1 的 p2/MPI2 random 在 80 步内未通过，仍是永久性能资格失败；
- additive-v2 的 p2/MPI2 random 在 200 步仍为 `4.380523556760784e-6`，其 small MPI2 qualification 仍正式关闭；
- 本 Review 新建的是一个不同的 `memory-first long-Krylov` 合同，不把旧失败重分类为通过。

---

# 1. 最新试验究竟证明了什么

## 1.1 增加迭代次数确实可能得到收敛

当前证据包含两个层次。

### multiplicative-v1：已经实测最终收敛

同一 p2/h50 random source：

```text
MPI1 first true residual <= 1e-8 at iteration 58
MPI2 first true residual <= 1e-8 at iteration 196
MPI2 final true residual = 5.885599406046585e-9
```

因此，“80 步没有通过”不等于“该方法永远不收敛”。至少在这个小型正定辅助问题上，固定预条件器配合更多 Krylov 迭代已经实测得到正确残差。

### additive-v2：持续下降，但尚未证明最终通过

同一 p2/MPI2 random source：

```text
iteration 80  true residual = 5.890364694544531e-4
iteration 200 true residual = 4.380523556760784e-6
```

它表现出继续下降趋势，因此更长迭代“有可能”达到 `1e-8`；但该 case 没有实际运行到通过，所以不能写成已证明收敛。

## 1.2 最大迭代次数与 restart 必须分开理解

```text
max_it 增加
= 增加时间和总 matvec/PC apply 数
= 在固定 restart 下通常不增加 Krylov 常驻向量数

restart 增加
= 增加同一个 GMRES 周期内保存的 Krylov basis
= 直接增加峰值内存
```

因此，本 Review 允许显著增加 `max_it`，但冻结 p6/h10 的 `restart=20`。不得用 `restart=40/80/200` 绕过低内存目标。

## 1.3 为什么选择 multiplicative-v1，而不是 additive-v2

现有小模型证据中：

| variant | p2 MPI1 random | p2 MPI2 random | 当前判断 |
|---|---:|---:|---|
| multiplicative-v1 | 58 步通过 | 196 步通过 | 更强；保留为 memory-first 候选 |
| additive-v2 | 76 步通过 | 200 步仍未通过 | 没有改善 MPI2；保持关闭 |

multiplicative-v1 不是 Hermitian PC，但本路线使用 GMRES，而不是 CG；GMRES 不要求 PC 为 Hermitian。当前 PC 是固定、线性且 repeat identity 通过，因此不需要 FGMRES 的额外向量存储。

---

# 2. 新的成功层级

从本 Review 起，必须区分三个层级。

| 层级 | 判断内容 | 当前优先级 |
|---|---|---:|
| correctness Gate | 最终 explicit true residual、物理量和 MPI 可复现性 | 最高 |
| resource Gate | complete process-tree peak、retained、swap、生命周期 | 最高 |
| performance Gate | iteration count、wall time、restart robustness | 次级 |

原先的 80 步 Gate 继续作为 performance negative 保留，但不再单独阻止一个在固定内存下最终能够收敛的方法进入后续正确性验证。

最终 p6/h10 成功仍必须同时满足：

```text
final explicit true residual <= 1e-6
complete workflow process-tree peak < 2,000,000,000 B
process-tree swap = 0
release-before-recovery lifecycle closed
E/H, R/T/A, A_volume and 12+12 channels pass existing direct-authority Gates
provenance complete
```

---

# 3. 冻结的长 Krylov 执行合同

## 3.1 唯一 production-mimic Krylov 配置

```text
KSP                         = GMRES
PC side                     = right
restart                     = 20
initial guess               = zero for fresh run; checkpoint solution for authorized resume
reported norm               = unpreconditioned
PC variant                  = multiplicative-v1
PC coefficients/options     = unchanged
outer rtol for positive B   = 1e-8
outer rtol for physical A   = 1e-6
```

禁止：

```text
restart scan
GMRES/FGMRES/LGMRES family scan
omega/shift/scaling scan
GAMG smoother/level/V-cycle scan
new additive-v3 or multiplicative-v2
production alpha scaling
hypre AMS
real-imag 2N production split
global direct coarse solve
```

## 3.2 长运行的残差可信度

为避免数千步累计误差，production-mimic runner 必须按 20 步一个周期执行 restarted GMRES：

```text
solve 20 steps
→ explicit exact true residual
→ residual replacement / restart from current solution
→ append compact history
→ continue next 20-step cycle
```

必须记录：

```text
PETSc reported residual each iteration
explicit true residual at 0,1,2,5,10,20 and every restart boundary
matvec count
PC apply count
wall time
process-tree memory and swap
```

不得把全部 Krylov basis、全量 field history或全部 checkpoint常驻内存。历史必须流式写入 ignored artifact；Git 中只提交 compact history和hash。

## 3.3 checkpoint/resume

长运行允许在每 200 步的 restart boundary 保存一个 hash-bound solution checkpoint：

```text
iteration
source SHA
input/physical SHA
MPI size
solution vector role and canonical identity
explicit true residual
```

只允许从 restart boundary checkpoint 恢复。恢复后必须重新计算 exact true residual并与 checkpoint记录一致。checkpoint用于机器中断恢复，不得作为改变初值、拼接不同算法或跳过失败 Gate 的手段。

---

# 4. M0：MPI2 根因隔离，但不把慢收敛误判为错误

M0 只在 p2/h50 small fixture 上运行，不进入 p6。

## M0-A：exact LOR edge inverse reference

使用小型 assembled `B_L` direct reference，仅作 oracle：

```text
high residual
→ exact high-to-LOR dual transfer
→ exact B_L inverse
→ exact LOR-to-high primal reconstruction
```

验证 MPI1/MPI2：

```text
canonical input identity <= 1e-12
canonical correction identity <= 1e-10
B_h-applied correction identity <= 1e-10
finite / repeat / input unchanged
```

若 exact reference 跨 MPI 不一致，说明 transfer/MPC/owner routing仍有明确实现缺陷；只允许修复该单一缺陷，然后重新运行 M0。不得进入 M1。

## M0-B：exact nodal-solve HX reference

保持 multiplicative-v1 correction顺序，只在 small oracle 中把 scalar PCGAMG V-cycle替换为 exact nodal solve。

比较：

```text
MPI1/MPI2 iteration histories
各 correction component
final canonical correction
```

目的仅为区分：

```text
transfer/topology defect
vs PCGAMG partition sensitivity
vs HX decomposition本身较弱
```

exact solve不得迁入 production。

## M0-C：逐分量 MPI 对照

对同一个 canonical residual分别记录：

```text
edge Jacobi pre
G^H restriction
nodal gradient correction
Pi_x correction
Pi_y correction
Pi_z correction
edge Jacobi post
final PC output
```

要求所有 exact algebraic map在 MPI1/MPI2 下相对差 `<=1e-10`。PCGAMG近似输出允许分区依赖，但必须测量并定位差异从哪一步开始。

M0只要排除 algebraic correctness bug即可继续；即使最终确认 PCGAMG导致迭代数增加，只要 M1 能在固定内存内最终收敛，仍可继续主线。

---

# 5. M1：small fixed-memory long-Krylov qualification

## 5.1 cases

冻结顺序：

```text
p2 MPI1: random, gradient, curl, checkerboard
p2 MPI2: random, gradient, curl, checkerboard
p3 MPI1: random, gradient, curl, checkerboard
p3 MPI2: random, gradient, curl, checkerboard
```

## 5.2 配置

```text
right GMRES
restart = 20
max_it  = 2000
rtol    = 1e-8
multiplicative-v1
```

旧 restart80数据只作历史诊断，不可替代本轮 restart20结果。

## 5.3 correctness Gate

每个 case 必须：

```text
explicit true residual <= 1e-8 by iteration 2000
finite throughout
input unchanged
repeat identity <= 1e-13
no solver breakdown
```

MPI1/MPI2 最终结果必须满足：

```text
final action canonical relative <= 1e-8
final solution canonical relative <= 1e-7
```

迭代数允许明显不同。80/200/500/1000/2000步只报告性能，不作为只要最终收敛就失败的依据。

若任一 case 到 2000 步仍未达到 `1e-8`，则当前 multiplicative LOR-HX family正式关闭，不得增加 restart、换Krylov或产生第三个PC变体。

---

# 6. M2：p6/h10 cold setup与固定内存资格

只有 M1 全部通过后才允许 M2。

## 6.1 case

```text
13.5 nm
p6/h10
MPI1 first
then conditional MPI2
```

## 6.2 setup内容

```text
T2 high-order matrix-free positive/physical action infrastructure
T3 streaming DtN retained infrastructure
p6↔LOR owner-local transfer/maps
LOR edge AIJ
scalar nodal AIJ
one shared PCGAMG hierarchy
multiplicative-v1 work vectors
restart20 GMRES vectors
watchdog/checkpoint writer
```

## 6.3 resource Gate

```text
cold complete setup process-tree peak < 2,000,000,000 B
post-setup retained process-tree       < 1,800,000,000 B
process-tree swap                      = 0
high-order global AIJ                  = false
global transfer matrix                 = false
global direct coarse                   = false
FE-sized numeric allgather             = false
```

达到2GB即受控停止；不得通过warm cache、拆进程、隐藏setup或只报告单rank RSS制造通过。

---

# 7. M3：p6/h10 positive auxiliary最终收敛

只有 M2通过后运行。

```text
operator = positive high-order B_h
KSP      = right GMRES
restart  = 20
max_it   = 3000
rtol     = 1e-8
```

先运行 MPI1 random；通过后运行 gradient/curl/checkerboard，再条件运行 MPI2 random。

成功要求：

```text
final explicit true residual <= 1e-8
complete process-tree peak < 2,000,000,000 B
swap = 0
checkpoint/resume contract pass if resume used
```

这里不再设置80步或200步硬收敛门槛，但必须完整报告：

```text
20 / 100 / 200 / 500 / 1000 / 2000 / 3000
```

的 true residual。若3000步仍未达到1e-8，停止当前family。

---

# 8. M4：p6/h10 exact physical Maxwell MPI1最终求解

只有 M3 MPI1 positive通过后，才允许 exact physical solve。

## 8.1 exact operator

```text
A = T2 matrix-free Maxwell volume action
  + T3 dynamic streaming Fourier-DtN
```

不得用positive B_h residual替代physical A residual。

## 8.2 solver

```text
right GMRES
restart = 20
max_it  = 5000
final explicit true residual target = 1e-6
```

不设置短迭代performance hard Gate。必须记录：

```text
20 / 100 / 200 / 500 / 1000 / 2000 / 3000 / 4000 / 5000
```

true residual以及每个restart cycle的compact history。

## 8.3 resource与生命周期

全过程必须遵循：

```text
solve
→ explicit final true residual
→ save minimal recovery packet
→ destroy KSP/PC/GAMG/Krylov and unnecessary matrices
→ verify RSS release
→ recover E/H and postprocess
```

complete workflow Gate：

```text
process-tree peak < 2,000,000,000 B
swap = 0
no OOM/SIGKILL
```

## 8.4 physics Gate

达到 `true residual <=1e-6` 后，必须运行并对照既有 direct authority：

```text
complex E/H selected observables
R/T/A
A_volume
energy closure
12 bottom + 12 top diffraction channels
canonical field/observable identity
```

所有阈值沿用 Task038-extra 原 T6 authority合同，不得因为迭代较慢而降低物理标准。

若 residual通过但 recovery/postprocess使complete workflow超过2GB，仍为resource FAIL，不得只报告solve阶段通过。

---

# 9. M5：p6/h10 MPI2分布式正确性

只有 M4 MPI1完整 residual、physics和resource全部通过后才运行。

配置与 M4 完全相同：

```text
MPI2
right GMRES
restart20
max_it5000
final true residual <=1e-6
```

允许 MPI2 迭代数显著高于 MPI1，但要求最终：

```text
complete process-tree peak < 2,000,000,000 B
swap = 0
final true residual <=1e-6
E/H and full observable vector pass MPI1/direct comparison
```

如果 MPI1通过而MPI2在5000步内未通过，必须准确分类为：

```text
SERIAL_MEMORY_CORRECTNESS_POSITIVE
DISTRIBUTED_LONG_KRYLOV_ROBUSTNESS_OPEN
```

不能写成通用 distributed production pass。

---

# 10. M6：条件 h10→h5资源缩放测量

只有 M4 MPI1完整通过后才允许进入。M6不以h5最终收敛为目标，而是为2TiB容量模型提供第二个完整PC实测点。

先基于h10实测闭合h5预测。只有：

```text
central predicted peak < 10,000,000,000 B
hard predicted peak    < 12,000,000,000 B
MemAvailable合格
一次只运行一个heavy job
```

才允许 p6/h5：

```text
cold setup
one PC apply
restart20的前20步physical screen
warning=10GB
hard stop=12GB
swap=0
```

若预测达到12GB，M6标记 `not_run_by_capacity_preflight`，不得冒险启动。

M6必须输出：

```text
DoF/rows/topology counts
cold peak
post-setup retained
one-apply workspace
restart20 20-step peak
h10→h5 memory exponent
```

---

# 11. M7：更新0.7 nm / 2 TiB容量审计，不运行0.7 nm PDE

M7在 M4完成后必须执行；若M6未运行，则使用h10实测加保守区间。

更新：

```text
formal 0.7 nm materials and physical identity
external propagating/near-cutoff/evanescent inventory
accuracy-qualified mesh scenarios
matrix-free fine action
LOR topology and sparse operators
PCGAMG hierarchy
restart20 fixed-memory Krylov
checkpoint/recovery reserve
MPI duplication
lifecycle overlap
```

给出：

```text
optimistic
central
conservative
```

三种2TiB process-tree预算，并区分：

```text
measured
derived
predicted
not_run
blocked
```

M7不得运行完整0.7 nm PDE，也不得把p6/h10成功直接写成0.7 nm通过。

---

# 12. 统一停止条件

任一条件触发即保存证据、写 `response_v8.md`、提交推送并停止：

```text
明确的transfer/MPC/owner algebra mismatch无法通过单一修复关闭
M1任一small case在restart20/max_it2000下不收敛
M2 cold setup达到2GB或swap>0
M3 positive p6在3000步内不收敛
M4/M5 physical A在5000步内不达到1e-6
任何阶段出现nonfinite、solver breakdown、OOM或provenance mismatch
complete workflow或recovery超过2GB
```

禁止在停止后自动：

```text
增加restart
增加max_it超过冻结上限
改变PC参数
换Krylov family
恢复additive-v2
产生第三个HX变体
重启已关闭的FC3/sweep/trace-harmonic family
```

---

# 13. 必须创建的结果文件

```text
outcomes/lor_hx_mpi2_root_cause.md
outcomes/lor_hx_memory_first_small.md
outcomes/lor_hx_p6h10_setup.md
outcomes/lor_hx_p6h10_positive_longrun.md
outcomes/lor_hx_p6h10_physical_longrun.md
outcomes/lor_hx_p6h10_mpi2.md
outcomes/lor_hx_h5_scaling.md
outcomes/feasibility_0p7nm_2tib_v2.md
outcomes/summary.md
response_v8.md
```

每个正式run必须绑定：

```text
source SHA
input SHA
physical SHA
MPI/threads/ABI
command
restart/max_it
full explicit true-residual history or compact hash
process-tree RSS/swap
checkpoint hashes
artifact hashes
classification
```

---

# 14. 最终授权范围

本 Review 条件连续授权：

```text
M0 MPI2 root-cause isolation
→ M1 restart20 small long-Krylov correctness
→ M2 p6/h10 setup/resource
→ M3 p6 positive long-run
→ M4 p6 physical MPI1 final solve + official recovery
→ M5 conditional MPI2 final solve
→ M6 conditional h5 resource scaling
→ M7 updated 0.7 nm / 2 TiB audit
→ response_v8.md and stop
```

本轮仍不授权：

```text
full 0.7 nm PDE
ordinary default change
master merge/rebase
whole-branch merge
new solver family outside this Review
```

核心裁决为：

> 当前证据已经证明，在固定预条件器下增加迭代次数能够使至少一个原80步失败的MPI2小案例最终达到正确残差。下一阶段因此从“短迭代性能资格”转为“固定restart、固定内存、长Krylov最终正确性资格”。速度问题保留为后续优化，不再先于正确性和内存闭合。