# Task038-extra Review Report V3：关闭二阶 transmission 与 standalone sweep，转向内存封顶的 adaptive two-level coarse/deflation

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V3
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = d2e6b0bb123540d49e21cf6f1ea7984b380a4a94
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 28 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v2.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v2.md
T1_status                               = ACCEPTED_AND_FROZEN_CONTRACT_PASS
T2_status                               = ACCEPTED_AND_FROZEN_ACTION_PASS
T3_status                               = ACCEPTED_AND_FROZEN_DYNAMIC_DTN_PASS
T4_status                               = ACCEPTED_AND_FROZEN_INTERFACE_TOPOLOGY_ACTION_PASS
R0_R1_R2_R3_status                      = ACCEPTED_AND_FROZEN_AUTHORITY_PASS
Candidate_A_standalone                  = ACCEPTED_NUMERICAL_CONTRACTION_FAIL
Candidate_B_current_geometry            = CLOSED_NOT_APPLICABLE
Candidate_C_second_order_transmission   = CLOSED_BY_RESOURCE_AND_PROJECT_PRIORITY
Candidate_C_rerun_or_optimization       = forbidden
transmission_parameter_search           = closed
standalone_two_slab_sweep_family        = CLOSED_BY_BOUNDED_CANDIDATES
T6_S                                    = not_authorized_from_current_R4
T6_F                                    = not_authorized
new_primary_lane                        = adaptive_trace_harmonic_two_level_v1
continuous_authorized_batch             = D0 through D4 below, subject to every Gate
mandatory_review_stop                   = after D4 screen or any earlier hard stop
T7_T8_T9                                = not authorized
full_0p7nm_PDE                          = forbidden
ordinary_default_change                 = forbidden
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
whole_Task37_extra_migration            = forbidden
whole_Task039_migration                 = forbidden
amend_rebase_force_push                 = forbidden
response_required                       = response_v3.md
```

本 Review 接受 `response_v2.md` 的主要事实与分类。T1–T4 和 R0–R3 已产生当前基线下的可复用正证据；Candidate A 的 standalone physical contraction 未达到 Gate；Candidate B 对当前 mixed interior interface 不适用；Candidate C 在得到任何正式 `rho` 之前触发 12 GiB process-tree hard stop。

根据原任务书已经冻结的规则：

```text
若 A/B/C 不能处理规定 residual，停止主 sweep 路线；
process-tree 达到 12 GB，停止受影响 lane。
```

因此，本 Review 不再授权修复、重跑或优化 Candidate C，也不再增加新的 Robin、Padé、二阶、rational、mode-count、overlap 或 slab transmission 候选。Candidate C 的源码和负证据保留为研究档案，不删除、不改写，但不得进入最终 selective-merge production candidate。

这不等于断言二阶 impedance 在数学上永远无效。当前裁决只表示：在本项目的 arbitrary-3D、p6、低内存与有限开发预算约束下，继续投入该实现没有足够的数值或资源依据。

当前 standalone two-slab sweep family 同时缺少：

```text
通过 physical/long-tail contraction 的候选
完整 workflow < 2,000,000,000 B 的候选
可进入 T6-S 的候选
```

所以不能继续把 T6-S 当作“只差一次重跑”。下一步必须引入真正不同的全局误差机制，而不是继续调整 transmission。

---

# 1. 对 Response V2 的审阅

## 1.1 Git、范围和停止行为

| 审阅项 | 结果 | 说明 |
|---|---|---|
| base / merge-base | pass | 均为 `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| reviewed HEAD | pass | `d2e6b0bb123540d49e21cf6f1ea7984b380a4a94` |
| branch relation | pass | 审阅时 `ahead 28 / behind 0` |
| ordinary default | unchanged | `full3d_iterative` 仍为显式 opt-in |
| master | unchanged | 未 merge、未写入 `master` |
| 0.7 nm PDE | correctly not_run | 没有运行或伪造结果 |
| Candidate C stop | accepted | `SIGTERM` controlled stop、swap=0、无 SIGKILL/OOM |
| T6 | correctly not_run | R4 未通过后没有继续 |

Codex 拉取本 Review 后必须重新报告：

```text
branch
HEAD
upstream
ahead/behind
git status --short
canonical worktree identity
Python/MPI/PETSc/DOLFINx/Basix ABI
PETSc ScalarType/IntType
MemAvailable/swap/disk
```

远端 review 无法观察 nonignored untracked 文件。工作树、ABI 或资源身份不合格时不得开始 D0。

## 1.2 接受并冻结的正结果

以下资产继续保留：

| 资产 | 当前身份 | 后续用途 |
|---|---|---|
| T1 `.dat` contract | frozen pass | 保持 one-dat/one-run 与 provenance |
| T2 matrix-free volume action | frozen pass | exact fine action |
| T3 dynamic streaming Fourier-DtN | frozen pass | exact open-boundary action |
| T4 owner-local slab/interface topology | frozen action/topology pass | 只作为数据分区与局部支持基础 |
| R2 current physical-dual oracle | frozen pass | 当前 RHS/component authority |
| R3 current recomputed residual at historical state | frozen pass | 当前兼容的 difficult residual source |

旧 W5 residual row array仍不是 current physical authority；Path A 继续关闭。R3 的：

```text
CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE
```

是后续 difficult source 的唯一正式 long-tail authority。

## 1.3 Candidate A：接受 standalone 数值负结果

Candidate A 的正式结果为：

| source | measured rho | Gate | process-tree peak | 结论 |
|---|---:|---:|---:|---|
| physical RHS MPI1 | `0.8145890334049838` | `<=0.60` | `5,145,784,320 B` | numeric fail |
| gradient MPI1 | `0.8889127715646881` | `<=0.90` | `1,323,728,896 B` | local source pass |

physical source 的失败不是 implementation defect，不能靠修改 inner iteration、restart、Robin 参数或继续重复运行解释掉。

Candidate A 不再是 standalone production PC。其现有固定实现只能在新两级方法中作为**冻结的局部 smoother oracle**使用，条件如下：

```text
transmission unchanged
slab count unchanged
local GMRES restart/max_it unchanged at 8/8
one forward+backward sweep only
no parameter scan
no independent production qualification claim
```

如果新的全局 coarse correction 不产生明确收益，Candidate A 也不再继续。

## 1.4 Candidate B：当前几何下关闭

Candidate B 依赖合格的 interior modal transmission authority。当前人工界面是 mixed Si–Si / Si–air 截面，而 T3 只资格化 exterior top/bottom Fourier-DtN。

因此：

```text
Candidate B = CLOSED_NOT_APPLICABLE_FOR_CURRENT_INTERFACE
```

不得把 exterior Floquet modes 截到零散 mixed facets 后冒充 interior modal oracle。除非未来任务改变人工界面到真实均匀层，并经新 review 授权，否则本任务不再打开 B。

## 1.5 Candidate C：正式关闭

Candidate C 唯一 p6/h10 physical formal attempt 的资源事实为：

```text
process-tree peak RSS = 12,942,209,024 B
hard line             = 12,884,901,888 B
wall                  = 406.7977727999969 s
swap                  = 0 B
return code           = -15
stop reason           = hard_stop_12_gib
rho / closure         = not_run_by_resource_hard_stop
```

当前 evidence 不能判断 C 的 contraction 数值能力，但已经足以决定项目优先级：

```text
CLOSED_BY_RESOURCE_AND_PROJECT_PRIORITY
DO_NOT_RERUN
DO_NOT_OPTIMIZE_JIT_FOR_THIS_CANDIDATE
DO_NOT_MERGE_TO_PRODUCTION
```

禁止通过以下方式恢复 C：

```text
预热 cache 后只报告 warm run
把 JIT/compiler 移出 watchdog 后宣称完整 workflow pass
降低 p/h 或改变物理
减少 Gate source
提高 12 GiB hard stop
重新选择二阶系数
切换更多 Padé/rational 阶数
```

源码、tests、compact record 和 ignored raw 保留，不删除负结果。最终 selective merge manifest必须将 `fullspace_second_order_impedance.py`、Candidate-C runner/checker分支和对应 production exposure列为 `do_not_merge / research archive`，除非未来用户明确建立独立新任务重新研究。

## 1.6 standalone sweep family 的关闭

当前 bounded candidates 的总状态为：

```text
A = physical numeric fail
B = not applicable
C = controlled resource stop and now closed
```

这满足原任务书的 sweep hard-stop精神。正式分类为：

```text
TRANSMISSION_ONLY_TWO_SLAB_SWEEP_FAMILY_CLOSED
```

关闭的是“依靠更换 transmission 就让一次 sweep 通过全部 Gate”的路线，不是关闭所有 Full3D iterative、domain decomposition 或两级方法。

---

# 2. 对“是否还有希望低于 2 GB”的判断

## 2.1 当前 standalone sweep：没有可信的 `<2 GB + 数值通过` 路径

当前没有一个 standalone sweep 同时满足：

```text
physical rho <= 0.60
long-tail rho <= 0.70
complete workflow peak < 2,000,000,000 B
swap = 0
```

Candidate A 的 gradient warm-like peak约为 `1.324 GB`，说明 matrix-free exact action、两个局部 shell和短 GMRES的**在线规模**并非天然远高于2 GB。但同一 A physical cold process-tree peak为 `5.146 GB`，且数值 `rho=0.815` 失败。Candidate C 又达到 `12.942 GB`，没有产生 `rho`。

因此：

> 当前 transmission-only sweep family 没有理由继续投入，也不能据此承诺完整 workflow 会降到2 GB以内。

## 2.2 保留组件下的两级方法仍有狭窄但真实的 online 机会

p6/h10 full-space 向量长度为 `173,802`，一个 complex128 full vector为：

```text
173,802 × 16 B = 2,780,832 B
```

若新的 coarse/deflation 使用 `r` 个 owner-local sharded basis `Z`，并同时保存 `AZ`，纯数值载荷为：

| coarse rank r | `Z + AZ` bytes | MiB |
|---:|---:|---:|
| 16 | `88,986,624 B` | `84.864 MiB` |
| 32 | `177,973,248 B` | `169.729 MiB` |
| 48 | `266,959,872 B` | `254.593 MiB` |
| 64 | `355,946,496 B` | `339.457 MiB` |

把 rank64 的 `Z+AZ` 与 Candidate A warm-like measured peak简单并列，只能得到一个**derived preflight**：

```text
1,323,728,896 + 355,946,496
= 1,679,675,392 B
```

该数值不是 simultaneous measured peak，也未包括 runtime、orthogonalization、manifest、coarse solve和allocator余量。但它表明：

```text
rank <= 64
+ owner-local basis
+ no duplicate FE-sized arrays
+ fixed one-sweep smoother
```

在 online 阶段仍可能落在2 GB附近，而不是已经被算术上排除。

因此本 Review 的判断为：

```text
current standalone sweep complete-workflow <2GB = not credible
new bounded two-level online <2GB              = plausible but narrow
new complete-workflow <2GB                     = not established
```

cold JIT/build peak必须单独测量，不能被 warm cache隐藏。只有 build和online两阶段的最大 process-tree peak都低于2 GB，才能称 complete-workflow resource pass。

---

# 3. 新主线：adaptive trace-harmonic two-level coarse/deflation

## 3.1 它解决什么问题

Candidate A 对 gradient source达到 Gate，但对 physical RHS只达到 `rho≈0.815`。这说明当前固定局部 sweep可以处理一部分局部/平滑误差，却没有充分消除跨区域、全局传播相关的困难方向。

新方法不再修改 transmission，而是增加一个由算子本身决定的自适应全局校正空间：

```text
local/short-range error  → frozen Candidate A one-sweep smoother
long-range/global error  → adaptive trace-harmonic coarse/deflation
```

它改变 PC，不改变：

```text
Maxwell weak form
material
Floquet phase
Fourier-DtN normalization
exact matrix-free fine operator
```

## 3.2 基本形式

设冻结的 Candidate A one-sweep为 `M_A^{-1}`，自适应 coarse basis为：

```math
Z=[z_1,\ldots,z_r],
\qquad
E=Z^H A Z.
```

有界两级 multiplicative correction可写为：

```math
M_{2L}^{-1}r
=
M_A^{-1}r
+
Z E^{-1} Z^H\left(r-A M_A^{-1}r\right).
```

这里的 `Z` 不允许从某一个 residual拟合，也不是旧 fixed 75/390/530D range。候选向量来自 owner-local interface/trace 上的 Maxwell-harmonic generalized eigenproblem，再通过有界 local harmonic extension进入 full-space。

局部辅助问题使用预先冻结的正定能量，而不是直接对 indefinite physical A 做任意特征值搜索。概念形式为：

```math
B_i\phi=\lambda M_{\Gamma,i}\phi,
```

其中：

```text
B_i              = local coercive Maxwell energy
M_Gamma,i        = interface/partition-of-unity trace energy
selected vectors = smallest predeclared eigenpairs under fixed rank ladder
```

该方法的目标是捕获穿过多个局部区域的低能量/难传播方向，而不是继续改善一个局部 Robin公式。

## 3.3 为什么它仍符合 arbitrary-3D

允许沿 z 或一般空间分区构造 owner-local subdomains，但 coarse vectors来自真实材料、真实 interface和真实局部算子，不要求：

```text
内部区域沿 z 均匀
结构可分离
有限个解析内部 Floquet mode精确描述结构
Hybrid/QEP
```

因此它仍属于 arbitrary non-separable Full3D iterative 路线。

## 3.4 收益、代价与适用边界

潜在收益：

```text
补足 standalone local sweep缺失的全局传播方向
coarse rank有明确上限
basis与AZ可owner-local分布
内存近似随 rN 线性增长
不需要global sparse factor
```

代价：

```text
需要局部 generalized eigenproblem
需要 harmonic extension
需要Z/AZ存储或流式作用
coarse E可能病态
rank可能随电尺寸增长
```

本轮只资格化 p6/h10 的 bounded coarse oracle，不得据此宣称0.7 nm production coarse已解决。若 rank64仍不能通过 contraction，当前 two-level coarse family立即关闭，不继续增加到128/256或开放阈值扫描。

---

# 4. 本 Review 授权的连续执行范围

## D0：关闭旧 transmission lane并建立精确内存 preflight

第一提交必须是轻量 closeout/preflight，不运行 heavy PDE：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/transmission_family_closeout.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/adaptive_coarse_preflight.md
```

必须记录：

```text
A/B/C最终分类
Candidate C do-not-rerun/do-not-merge
Candidate A只可作为冻结 smoother
full vector bytes
rank16/32/48/64 Z+AZ bytes
coarse metadata/work预算
build/JIT与online内存口径
```

不得删除 Candidate C代码或负证据；不得把关闭写成数学不可能证明。

D0 的 preflight Gate：

```text
coarse rank ladder          = 16 / 32 / 48 / 64 only
rank64 Z+AZ                 = 355,946,496 B
coarse metadata/work cap    = 64,000,000 B
coarse retained hard cap    = 424,000,000 B
no FE-sized numeric allgather
no replicated full basis per rank
no global sparse factor
```

若仅最小可实现布局已经超过上述硬线，停止本轮，不进入 D1。

## D1：p2/p3 adaptive trace-harmonic oracle

先在 p2/p3 小 fixture实现和验证：

```text
owner-local interface energy operators
fixed coercive local Maxwell auxiliary B_i
interface mass/PoU energy M_Gamma,i
small generalized eigenproblem
local harmonic extension
restriction/prolongation adjoint
MPI1/MPI2 canonical identity
```

允许在 p2/p3 oracle中显式组装小型局部矩阵用于独立比较；production p6路径不得依赖 global AIJ、global Schur或growing factor。

D1 Gate：

| 项目 | Gate |
|---|---:|
| auxiliary Hermitian defect | `<=1e-12` |
| generalized eigen residual | `<=1e-10` |
| extension/restriction adjoint | `<=1e-11` |
| coarse basis finite/repeat | exact deterministic |
| MPI1/MPI2 canonical identity | `<=1e-12` |
| phase application | finalized Floquet MPC once |
| global numeric allgather | `false` |

只允许一次针对明确 indexing/orientation/ownership defect的窄修。第二次仍失败则停止，不进入 D2。

## D2：p6/h10 bounded coarse packet

D2 不运行 outer KSP。按固定 rank ladder：

```text
r = 16 → 32 → 48 → 64
```

构造 owner-local sharded `Z` 与 `AZ`，并形成小型：

```math
E=Z^H A Z.
```

不得从 physical RHS、R3 long-tail residual或任何 checkpoint直接训练/拟合 basis。residual只能用于之后的独立 contraction test。

D2 Gate：

| 项目 | Gate |
|---|---:|
| `Z^H Z` orthogonality defect | `<=1e-10` |
| `AZ` action identity | `<=1e-11` |
| repeat | deterministic |
| cross-MPI canonical identity | `<=1e-12` |
| coarse `E` Hermitian/physical consistency | explicit audited |
| `cond(E)` | `<=1e12` |
| total `Z+AZ` at r64 | `<=355,946,496 B` |
| total coarse retained | `<=424,000,000 B` |
| numeric allgather/global matrix | `false` |
| swap | `0` |

p6/h10 可以用 dense `r×r` QR/LU作为**coarse oracle**，因为 `r<=64`；它不能被描述为0.7 nm production global coarse solver。未来若进入T7/T8，必须重新判断 coarse维数增长和hierarchical/distributed solve。

如果 rank64不能满足 algebra、condition或内存 Gate，停止当前 coarse lane。

## D3：coarse-only 与 two-level contraction

使用同一冻结 source family：

```text
physical RHS
gradient-dominated
curl-dominated
checkerboard/high-frequency
R3 qualified long-tail residual
```

每个 rank先测试 coarse-only correction；只有 coarse-only对 physical或long-tail产生预声明的明确正信号，才允许与冻结 Candidate A one-sweep组合。

明确正信号定义为：

```text
physical rho improvement vs identity >= 20%
or
long-tail rho improvement vs identity >= 20%
```

两级正式 Gate继续使用任务书原值：

| source | required rho |
|---|---:|
| physical RHS | `<=0.60` |
| R3 qualified long-tail | `<=0.70` |
| checkerboard/high-frequency | `<=0.75` |
| gradient | `<=0.90` |
| curl | `<=0.90` |

执行纪律：

```text
rank16 → rank32 → rank48 → rank64
第一个通过全部 source的rank立即停止
不得在通过后继续增加rank
不得超过64
Candidate A参数完全冻结
```

资源必须分成两个权威阶段：

```text
build/JIT/setup stage
online correction/apply stage
```

正式分类：

```text
online process-tree peak < 2,000,000,000 B     = online resource Gate
max(build stage, online stage) < 2,000,000,000 B = complete-workflow resource Gate
swap = 0
```

如果 online超过2 GB，当前 two-level lane直接resource fail；不得靠生命周期口径变化继续。如果 online低于2 GB但build/JIT超过2 GB，只能分类：

```text
ONLINE_SCALABLE_SIGNAL_WITH_BUILD_RESOURCE_DEBT
```

不得称 complete workflow pass，也不得进入 T6-F。

如果 rank64仍不能通过全部 contraction Gate，关闭当前 adaptive coarse family，不再增加basis、阈值或residual-derived directions。

## D4：条件 T6-S screen

只有以下全部满足才允许 D4：

```text
D1 algebra/MPI pass
D2 rank<=64 packet/algebra/memory pass
D3 at least one rank passes all five contraction Gates
D3 online process-tree peak < 2,000,000,000 B
swap=0
current T1–T4 affected regressions pass
```

外层冻结：

```text
right FGMRES
restart = 20
standard in-memory Krylov
adaptive_trace_harmonic_two_level_v1
no parameter scan
```

T6-S Gate：

| checkpoint | full explicit true residual Gate |
|---:|---:|
| 20 | `<=0.40` |
| 100 | `<=0.05` |
| 200 | `<=0.005` |
| 150→200 improvement | `>=20%` |

必须保存 20/100/150/200 的 hash-bound solution/residual compact packets，并由 current exact action显式重算 true residual。

无论 D4通过或失败，本 Review 都要求停止并写 `response_v3.md`。不授权：

```text
final 1e-6 solve
official E/H recovery
R/T/A/A_volume
T7 h-scaling
T8 0.7 nm capacity audit
T9 closeout
```

---

# 5. 本批次明确禁止

| 对象 | Review V3 决定 |
|---|---|
| Candidate C rerun/JIT optimization | permanently closed in this task |
| new second-order/Padé/rational transmission | forbidden |
| Candidate B on mixed interface | closed |
| Candidate A parameter changes | forbidden |
| more slab/overlap/inner-step/restart scan | forbidden |
| standalone sweep production claim | closed |
| fixed 75/390/530D range migration | forbidden |
| residual-derived/recycling-trained basis | forbidden |
| rank greater than 64 | forbidden |
| p4-complement/84-factor campaign | forbidden |
| old W8–W18 PC | closed |
| LOR-HX reopening | closed |
| disk-backed FGMRES | forbidden |
| global AIJ / global Schur | forbidden |
| dense FE-sized interface matrix | forbidden |
| growing local/global factor | forbidden |
| whole Task37-extra/Task039 migration | forbidden |
| T6-F / T7 / T8 / T9 | not authorized |
| full 0.7 nm PDE | forbidden |
| ordinary default/master merge | forbidden |

---

# 6. 全批次硬停止条件

任一条件发生，保存证据、提交轻量结果、写 `response_v3.md` 并停止：

1. branch/base/upstream/worktree/ABI不正确；
2. Candidate C被重新执行或优化；
3. D0最小布局超过 coarse retained hard cap；
4. D1 algebra/orientation/MPI经一次窄修后仍失败；
5. D2需要global matrix、numeric allgather或growing factor；
6. `cond(E)>1e12`且不能由固定正交化实现错误解释；
7. rank64仍不能闭合 algebra或内存；
8. coarse basis需要根据 residual拟合或选择；
9. D3 rank64仍不能通过全部 contraction Gate；
10. D3 online process-tree超过2,000,000,000 B；
11. process-tree达到12 GiB、出现swap、OOM风险或termination失效；
12. 需要增加rank、inner steps、slabs、overlap或开放参数扫描；
13. T6-S任一checkpoint失败或150→200改善小于20%；
14. 工作转向Hybrid、RCWA、z-separable internal modes或0.7 nm full PDE；
15. 必须改变Maxwell弱式、材料、Floquet phase、DtN normalization或Gate才能继续。

硬停止只关闭当前 adaptive two-level candidate，不得写成“Full3D iterative永远不可能”。

---

# 7. 提交计划

继续使用同一分支：

```text
codex/20260820-task38-extra-full3d-iterative-0p7nm
```

推荐提交顺序：

```text
docs(task038-extra): close bounded transmission family and preflight adaptive coarse
feat(dd): add trace-harmonic coarse oracle fixtures
feat(dd): add bounded owner-local adaptive coarse packets
bench(task038-extra): record coarse and two-level contraction
bench(task038-extra): run conditional two-level T6 screen
docs(task038-extra): respond to review v3
```

若前一 Gate失败，不创建后续空提交。禁止 amend、force push、rebase、新分支或无关清理。

---

# 8. outcomes 与 response 要求

至少新增或更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/transmission_family_closeout.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/adaptive_coarse_preflight.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/adaptive_coarse_oracle.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/two_level_contraction.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md
docs/task038_extra_full3d_iterative_0p7nm/response_v3.md
```

若运行 D4，还需：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/full3d_iterative_screen.md
docs/development_model_registry.md update
```

建议 compact records：

```text
records/d0_adaptive_coarse_preflight_v1.json
records/d1_trace_harmonic_p2_mpi1_v1.json
records/d1_trace_harmonic_p2_mpi2_v1.json
records/d1_trace_harmonic_p3_mpi1_v1.json
records/d1_trace_harmonic_p3_mpi2_v1.json
records/d2_coarse_rank_<16|32|48|64>_v1.json
records/d3_two_level_rank_<16|32|48|64>_v1.json
records/d4_t6_screen_v1.json
```

`response_v3.md` 必须回答：

1. branch、base、Review V3 start/final HEAD、ahead/behind和worktree；
2. Candidate C关闭与do-not-merge处理；
3. D0–D4 planned/run/pass/fail/not_run矩阵；
4. exact full-vector与rank ladder内存；
5. local eigenproblem定义、eigen residual与Hermitian defect；
6. harmonic extension、orientation、phase和MPI identity；
7. Z/AZ bytes、coarse rank、E condition与coarse solve身份；
8. coarse-only和two-level对五类source的rho；
9. Candidate A是否仅按冻结smoother使用；
10. build/JIT与online process-tree分别测量的峰值；
11. complete-workflow是否真正低于2 GB；
12. 若运行T6-S，20/100/150/200 true residual、wall、RSS、swap；
13. T6-F、E/H、R/T/A、T7–T9和0.7 nm的not_run边界；
14. measured/derived/predicted/failed/controlled_stop/not_run分类；
15. 下一轮是否值得授权T6-F或应关闭该coarse family。

---

# 9. 下一次 Review 的裁决范围

下一次 Review 将只裁决：

```text
adaptive trace-harmonic basis是否具有独立operator authority
rank<=64是否足以处理physical与long-tail residual
在线two-level memory是否真实低于2 GB
cold build/JIT是否仍阻止complete-workflow qualification
T6-S是否显示足够收敛信号
是否授权T6-F
或是否关闭当前two-level family并重新设计Full3D PC
```

在下一次 review 前不得开始 T6-F、T7、T8、T9 或 master integration。

---

# 10. 最终决定

```text
T1_T2_T3_T4                    = ACCEPTED_AND_FROZEN
R0_R1_R2_R3                    = ACCEPTED_AND_FROZEN
Candidate_A_standalone         = NUMERICAL_FAIL
Candidate_B                    = CLOSED_NOT_APPLICABLE
Candidate_C                    = CLOSED_DO_NOT_RERUN_DO_NOT_MERGE
transmission_only_sweep_family = CLOSED
adaptive_two_level_D0_D1_D2_D3 = AUTHORIZED_AS_ONE_BOUNDED_BATCH
T6_S_D4                        = CONDITIONALLY_AUTHORIZED_AFTER_ALL_D3_GATES
T6_F_T7_T8_T9                  = NOT_AUTHORIZED
MASTER_MERGE                   = FORBIDDEN
```

Codex可以连续推进 D0→D4，正常通过时不需要逐阶段等待审阅；但必须在 D4 screen完成、rank64失败、online超过2 GB或任何更早hard stop后，提交并推送同一分支，写 `response_v3.md`，随后停止等待下一轮审阅。
