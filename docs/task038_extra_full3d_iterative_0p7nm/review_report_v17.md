# Task038-extra Review Report V17：精确 p3 physical coarse-span 与低内存 unrestarted Krylov 机制裁决

## 0. 审阅身份与总裁决

```text
review                                  = Task038-extra Review Report V17
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = d2c0bdbeffdd0b33190a9f95f6d6cc1c2d82616e
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
ordinary_default_change                 = forbidden
standalone_physical_status              = NOT_QUALIFIED
selected_positive_hierarchy             = same_mesh_hcurl_pmg_v1_requalified
same_mesh_physical_pcoarse_v1            = CLOSED_AS_ITERATIVE_REALIZATION
exact_p3_coarse_span                    = NOT_YET_DECIDED
restart20_loss_hypothesis               = NOT_YET_DECIDED
next_subdomain_or_transmission_work      = forbidden before V17 mechanism decision
full_0p7nm_PDE                          = forbidden
primary_objective                       = final correctness under bounded memory
iteration_count_and_wall_time           = secondary
response_required                       = response_v17.md
continuous_authorized_batch             = M0 through M6
mandatory_stop                          = after M6 or any earlier terminal hard stop
```

本 Review 继续服从项目长期目标：

> 在单节点约 2 TiB 物理内存内，以自主 FEniCS/DOLFINx、complex128、Nédélec `H(curl)`、双 Floquet 和 Fourier-DtN，最终求解 0.7 nm 周期单胞内任意非可分三维 Maxwell 散射问题。

V17 不重新研究 Robin、PML、optimized Schwarz、slab、interface Schur、GenEO、BDDC、HX 或新的 LOR 参数。它只回答两个尚未被 V16 区分的机制问题：

1. **如果 p3 physical coarse equation 被真正准确地求解，p3 coarse space 本身能否消除 p6/h10 平台残差？**
2. **当前 `restart=20` 是否反复丢弃了对真实 Maxwell 长尾至关重要的 Krylov 方向？**

这两个问题分别对应：

```text
coarse-space span / coarse-equation solve quality
vs
restart-induced Krylov information loss
```

只有两者都无正信号，才有充分依据重新考虑 wave-aware domain decomposition。不得在本轮提前回到已经研究过的 transmission family。

---

## 1. 对 V16 的最终审阅

### 1.1 必须永久保留的 V16 事实

| 阶段 | 冻结结果 | V17 解释边界 |
|---|---|---|
| Q1.1 | PASS | same-mesh `A3 v` 与 `P63^H A6 P63 v` identity 已通过；不是 full PDE pass |
| Q1.2 | PASS | 小型 p3/h50 physical inner 已达到 `1e-6`；不是 p3/h10 鲁棒性证明 |
| Q2 | `Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL` | 当前 iterative p3 realization 在 10000 步后仍未准确求解，并使 fine residual 变差 |
| W0 | `W0_INTERFACE_RANK_CAPACITY_FAIL` | 只有 preflight 关闭；没有 W1–W4 数值 contraction |
| official physics | `not_run` | 不得由任何 oracle、coarse vector 或 checkpoint correction 冒充 |

V16 Q2 的权威实测必须原样保留：

```text
checkpoint stored residual             = 0.4837947981092168
checkpoint recomputed residual         = 0.48379479479924
checkpoint reproduction relative       = 6.8416957056789795e-9
p3 inner true residual at 10000        = 0.7749555148382701
rho_ref                                 = 2.7001483995603124
rho3                                    = 0.774955514838267
fine residual norm before / after      = 0.6412077991519661 / 1.7313562126657716
parent process-tree peak               = 1,560,625,152 B
worker peak                            = 873,783,296 B
swap                                    = 0 B
```

这些结果已经足够关闭：

```text
positive p3→p1 hierarchy
作为 p3 physical A3 的 production inner inverse
+ fixed restart20 / max_it10000
```

不得通过增加其 inner steps、改变 restart、扫描 shift/smoother 或 p-level 来重开 `same_mesh_physical_pcoarse_v1`。

### 1.2 V16 尚未回答的问题

Q2 中的 `e3` 不是准确的 `A3^{-1} r3`，因为 p3 inner true residual 仍为 `0.775`。因此：

```text
rho_ref = 2.70
```

同时混合了两种可能：

```text
A. p3 coarse space本身不能表示平台误差；
B. p3 coarse space可以表示，但当前positive inner PC根本没有把coarse equation解准。
```

V16 不能仅凭一个未收敛的 inner solve 区分 A 与 B。

同理，V14 的真实 physical outer 使用 `GMRES(20)`，在 checkpoint-500/1000 附近形成 `0.484` 平台，但没有与同一预条件器、同一 checkpoint、同一总 matvec 数的 unrestarted Arnoldi 对照。因此还不能区分：

```text
C. 预条件器缺失全局波传播机制；
D. restart=20周期性丢失了关键近零/非正规方向。
```

V17 用两个一次性 oracle 闭合这些缺口。

---

## 2. Oracle A：精确 p3 physical coarse-span

### 2.1 它解决什么问题

它不开发新的 production solver，也不声称 LU 可以用于 0.7 nm。它只把 p3 coarse equation 当作一把诊断显微镜：

```text
p6 checkpoint residual r6
→ r3 = P63^H r6
→ 准确求解 A3 e3 = r3
→ e6 = P63 e3
→ 检查 r6 - A6 e6
```

若准确 `e3` 能明显压低 p6 residual，说明 coarse span 有效，V16 失败主要来自 p3 physical inverse不够强；若准确 `e3` 仍无收缩，则 p3 coarse space本身无效，应永久关闭 physical p-coarse family。

### 2.2 为什么允许 p3 LU

p3 LU 只用于一次性 authority oracle：

```text
oracle-only
diagnostic-only
not production
not selectable from .dat
not a 0.7 nm scalability claim
factor destroyed immediately after e3 export
```

V17 不允许将 p3 direct factor保留在最终 PC 中，也不允许据此把 Full3D direct/coarse direct重新提升为生产路线。

### 2.3 冻结三阶段生命周期

为了避免 p6 live set 与 p3 factor重叠，必须由同一个 parent watchdog 覆盖三个顺序 child：

```text
A1: p6 residual/restriction producer
    - 从原 checkpoint-1000重建同一A6/b6
    - 计算r6与r3=P63^H r6
    - 保存canonical r6/r3 packet及hash
    - child完全退出

A2: p3 accurate direct oracle
    - 只建立p3 physical equation
    - 允许assembly-time static condensation
    - MUMPS analysis-only先行
    - 通过资源预测后才factor/solve
    - explicit p3 true residual <=1e-10
    - 保存e3 canonical packet
    - 销毁factor/matrix并完全退出

A3: p6 prolongation/contraction checker
    - 重建同一A6和P63
    - e6=P63e3
    - 计算r6_new=r6-A6e6
    - 计算r3_new=P63^H r6_new
```

三个 child 必须绑定同一：

```text
input SHA
physical model SHA
mode manifest SHA
checkpoint manifest/solution SHA
source SHA
canonical key inventories
```

### 2.4 资源合同

该 oracle在当前约16 GB开发机上运行，资源门限仅用于防止系统失稳：

```text
parent process-tree warning = 10,000,000,000 B
parent process-tree hard    = 12,000,000,000 B
swap                        = 0 B
one heavy child at a time   = mandatory
```

必须先完成 p3 MUMPS analysis-only，并报告：

```text
condensed rows / NNZ
analysis estimate
predicted factor memory
predicted peak
available physical memory
```

若 predicted hard upper不能低于12 GB，分类为：

```text
A_ORACLE_BLOCKED_BY_RESOURCE_PREFLIGHT
```

不得启动 factor，也不得把“未运行”写成 span失败。

### 2.5 数值 Gate

Oracle A 的 hard Gate：

```text
checkpoint reproduction relative <=1e-8
p3 direct explicit true residual  <=1e-10
rho3_exact                        <=1e-6
rho_ref_exact                     <=0.70
finite/repeat/input unchanged     = PASS
swap                              = 0
```

辅助分类：

```text
rho_ref_exact <=0.70
    -> EXACT_P3_COARSE_SPAN_PASS

0.70 < rho_ref_exact <0.90
    -> EXACT_P3_COARSE_SPAN_WEAK_SIGNAL
       只记录，不授权生产inner开发；等待Oracle B联合决策

rho_ref_exact >=0.90
或fine residual增大
    -> EXACT_P3_COARSE_SPAN_FAIL
       永久关闭所有same-mesh physical p-coarse变体
```

不得在看到结果后修改 `0.70/0.90`、换 source、换 checkpoint、改 p-level或添加 residual-derived basis。

---

## 3. Oracle B：低内存 unrestarted Krylov 对照

### 3.1 它不是“始终沿同一个方向迭代”

`unrestarted GMRES/FGMRES` 的含义不是一直沿一条固定方向前进。它恰好相反：

```text
每一步都保留一个新的Arnoldi/Krylov方向
而不是每20步把整个搜索子空间清空后重新开始
```

`GMRES(20)` 每个周期只保留20维搜索空间，cycle结束后仅保留当前解；困难的近零、波动或非正规方向可能被反复遗失。unrestarted oracle保留完整400或500维方向，用来判断平台是否主要由 restart造成。

### 3.2 为什么可能对后续有帮助

若 unrestarted 明显优于 `GMRES(20)`，后续不必立刻回到 Schwarz。可研究：

```text
GMRES-DR / thick-restart
harmonic Ritz deflation
disk-backed retained subspace
bounded recycle dimension
```

这些方法只保留少量已经证明重要的全局方向，可以比完整 unrestarted 更低内存。反之，若 unrestarted也停滞，则说明 restart不是主要原因，应停止 Krylov-only优化。

### 3.3 冻结对照

从同一个 checkpoint-1000 开始，固定：

```text
fine operator           = exact split matrix-free A6 + streaming DtN
preconditioner          = existing same_mesh positive pMG
initial solution        = frozen checkpoint-1000
additional iterations   = 500
reference               = GMRES(20) continuation, exactly 500 additional iterations
oracle                   = disk-backed unrestarted right FGMRES, exactly 500 iterations
true residual cadence   = every20 iterations
source/physics/cache     = identical
```

不得改变：

```text
PC
restart20 reference
outer source
checkpoint
physical parameters
quadrature
mode inventory
smoother
```

### 3.4 磁盘与内存合同

所有 Arnoldi basis必须使用 disk-backed storage：

```text
no 500-vector RAM retention
bounded in-memory vector window <=8 full p6 vectors
fsync/checksum at fixed cadence
basis manifest and per-vector SHA
```

一个 p6 complex128 vector 的 derived raw bytes为：

```text
173802 * 16 = 2,780,832 B
```

500步 flexible Arnoldi的 V/Z 两组原始数组上界约为：

```text
2 * 500 * 2,780,832 B = 2,780,832,000 B
```

这是磁盘容量估算，不是RSS。正式 preflight必须检查：

```text
free disk >=10 GB
process-tree hard RSS <2,000,000,000 B
swap=0
```

若现有 disk-backed solver实现无法满足 exact A/PC、right FGMRES、checkpoint identity或显式 true residual合同，则只允许一次通用适配；不得从 Task37-extra整体迁移旧 solver campaign。

### 3.5 数值判定

记录：

```text
r20(k)   = GMRES(20) continuation residual
rUR(k)   = unrestarted residual
k        = 20,40,...,500
```

主要 Gate：

```text
rUR(500) <= 0.1 * r20(500)
```

即同样额外500次迭代，unrestarted至少好一个数量级。

附加正信号：

```text
unrestarted最后200步仍持续下降
Hessenberg finite
orthogonality defect <=1e-8
explicit residual与Arnoldi residual闭合
```

分类：

```text
rUR(500) <=0.1*r20(500)
    -> UNRESTARTED_KRYLOV_STRONG_SIGNAL

0.1*r20(500) < rUR(500) <=0.5*r20(500)
    -> UNRESTARTED_KRYLOV_WEAK_SIGNAL
       只允许离线Ritz/span审计，不授权长PDE

rUR(500) >0.5*r20(500)
    -> UNRESTARTED_KRYLOV_NO_SIGNAL
       关闭Krylov-only lane
```

不得把 unrestarted 500步未达到 `1e-6` 直接称为失败；该 oracle只比较 restart信息损失，不是完整PDE convergence formal。

---

## 4. M0–M6 执行顺序

### M0：冻结证据与实现审计

必须读取并绑定：

```text
response_v16.md
physical_pcoarse_checkpoint_v16.md
physical_pcoarse_q1_qualification_v16.json
physical_pcoarse_checkpoint_v16.json
V14 checkpoint-1000 manifest/solution
current same-mesh transfer/action implementation
existing disk-backed Krylov reusable component
```

输出 docs-only：

```text
outcomes/v17_mechanism_preflight.md
outcomes/records/v17_mechanism_preflight.json
```

### M1：Oracle A capacity / analysis-only

完成三child生命周期、p3 condensed matrix sizing、MUMPS analysis-only和12GB预测。失败则准确记录 resource-blocked，但不阻止M4 Oracle B。

### M2：Oracle A accurate solve

仅在M1通过后执行一次。不得重跑factor、换ordering、换MUMPS参数或提高12GB hard line。

### M3：Oracle A contraction closure

产生：

```text
rho3_exact
rho_ref_exact
fine/coarse residual norms
canonical packet identity
process-tree timeline
```

### M4：Oracle B implementation / fixed reference

适配disk-backed right FGMRES，并先运行500步 `GMRES(20)` continuation reference；两者使用全新artifact root和同一source SHA。

### M5：Oracle B unrestarted formal

运行唯一一次500步disk-backed unrestarted FGMRES，生成逐20步显式残差与Arnoldi/Hessenberg审计。

### M6：联合决策、文档与停止

必须按下表作唯一下一步结论：

| Oracle A | Oracle B | V17 后续决策 |
|---|---|---|
| PASS | STRONG | p3 span有效且restart损失显著；下一任务研究bounded GMRES-DR/thick restart，并另行研究可扩展p3 wave inverse；不回Schwarz |
| PASS | NO/WEAK | p3 span有效，restart非主因；下一任务只研究p3 physical wave inverse，不做global LOR参数扫描 |
| FAIL | STRONG | 关闭physical p-coarse；下一任务研究bounded deflated/recycled Krylov，positive pMG继续作PC |
| FAIL | NO/WEAK | coarse span与restart均无信号；才允许下一review比较wave-aware DD/PML sweeping与其他全局传播架构 |
| RESOURCE_BLOCKED | STRONG | p3 span未判定；优先Krylov lane，不把resource-blocked误写为span fail |
| RESOURCE_BLOCKED | NO/WEAK | 先设计更小的exact span oracle或中间波长pilot；不得直接重跑大LU |

M6 必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/exact_p3_coarse_span_v17.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/unrestarted_krylov_v17.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/v17_joint_decision.md
docs/task038_extra_full3d_iterative_0p7nm/response_v17.md
```

并更新：

```text
outcomes/summary.md
outcomes/test_summary.md
docs/development_progress.md
```

随后提交、推送当前分支并停止等待审阅。

---

## 5. 明确禁止项

本轮禁止：

```text
重跑V16 iterative Q2
增加Q2 inner iterations
改变p3 inner restart/shift/smoother/p-level
把p3 LU提升为production PC
重跑V15 rank32 Floquet correction
从checkpoint residual拟合新的coarse basis
启动Robin/PML/Schwarz/sweep/interface Schur
扫描outer restart
完整fresh physical PDE 20000步
physical recovery或official R/T/A
p6/h5或完整0.7nm PDE
改变ordinary default
merge master
```

若出现 path/cache/import/provenance 的 pre-measurement 工程缺陷，只允许在保留旧证据后窄修一次；真实 numerical、span、2GB/12GB、swap、orthogonality或fixed-cap Gate不得重跑规避。

---

## 6. 对用户问题的直接回答

### 6.1 第一条理解是否正确

是。Oracle A 就是在 p3 层临时使用足够准确的 LU/MUMPS direct solve，把 p3 physical equation真正解准，然后观察该 correction能否消除 p6 checkpoint平台误差。

它回答的是：

```text
p3 coarse space有没有覆盖平台误差
```

而不是证明LU可用于最终0.7 nm生产。

### 6.2 第二条理解需要纠正

不是“一直用同一方向迭代”。unrestarted Krylov 是：

```text
不断产生并保留新的搜索方向
```

而 `restart=20` 是每20步丢弃旧搜索子空间。这个对照能判断当前平台是否有一部分来自重启丢失困难方向。

### 6.3 为什么这两个试验值得做

它们是当前最小、最直接、不会重复既有Schwarz/LOR参数研究的机制裁决：

```text
精确p3 oracle
→ 判定coarse span vs coarse inverse

unrestarted oracle
→ 判定preconditioner缺陷 vs restart信息损失
```

两者结束后，下一架构选择将有真实证据，而不是再次凭直觉回到已失败的子域边界条件路线。
