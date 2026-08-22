# Task040：Hybrid side factor 低内存预条件器与受控变量资格化

## 0. 任务身份

```text
task                                   = Task040
task_kind                              = HYBRID_SIDE_FACTOR_REPLACEMENT_CONTROLLED_PC_CAMPAIGN
status                                 = READY_FOR_CODEX_EXECUTION
repository                             = Rookie1234567/MyFEniCS
base_branch                            = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
base_SHA                               = 9dc9ac58e05e5422498dade503046f9ae87d13d9
working_branch                         = codex/20260822-task40-hybrid-side-factor-pc
remote_upstream                        = origin/codex/20260822-task40-hybrid-side-factor-pc
branch_creation_authority              = user explicit instruction on 2026-08-22
Task039_write_or_reclassification      = forbidden
other_branch_write                     = forbidden
master_write_or_merge                  = forbidden
ordinary_default_change                = forbidden
public_input_entry                     = python scripts/run_case.py <one-case.dat>
primary_case                           = 5 nm / 1 deg grazing / phi=0 / S / p6h4 / M480 / MPI8
primary_blocker                        = bottom/top full sparse local side factors
primary_goal                           = replace full side factors by a lower-memory PC while preserving the same Hybrid equation
secondary_goal                         = measure the true memory-residual-time limit of the selected PC
full_0p7nm_PDE                         = forbidden
new_QEP_or_M_study                     = forbidden
dynamic_DtN_redesign                   = forbidden
global_Hybrid_operator_redesign        = forbidden
matrix_free_side_F_redesign            = forbidden in the initial campaign
coarse_space_or_local_spectral_addition = forbidden until a later review explicitly authorizes it
response_required                      = response_v1.md
```

仓库长期规则通常由 Codex 创建执行分支；本任务由用户在本轮明确要求 ChatGPT 从 Task039
最新 HEAD 创建 Task040 分支，因此这是一次有记录的用户级覆盖。除该分支创建动作外，
角色分工保持不变：ChatGPT 负责任务书与 review，Codex 负责实现、测试、正式运行、
`outcomes/` 与 `response_v1.md`。

---

## 1. 本任务解决哪个 0.7 nm blocker

本任务只解决一个 blocker：

> 当前成功的 Hybrid iterative 虽然不做全局 Hybrid MUMPS factor，但仍同时保留 bottom 和
> top 两个完整 sparse side factors；这两个 factor 是 5 nm h4 完整峰值的主导来源，并且
> 随网格细化会超线性增长，不能直接服务未来 0.7 nm。

本任务不同时解决 QEP、内部模态数、external-channel scaling、dynamic DtN、显式 side
矩阵或 global Hybrid operator。原因是必须控制变量：若一次改变多个子系统，即使结果变好或
变坏，也无法判断究竟是哪项修改造成。

本任务的核心问题是：

```text
能否保持同一个 5 nm Hybrid 方程、同一个 M480 模态系统、同一个 DtN、同一个后处理，
只把 A_bottom^-1 和 A_top^-1 中的 full MUMPS side factor替换为低内存迭代预条件器？
```

---

## 2. Task039 继承基线

Task040 从 Task039 最新 HEAD 原样继承全部正、负结果，不修改或重分类历史证据。

### 2.1 完整 workflow authority

| 路径 | 范围 | process-tree RSS peak | 数值/物理状态 | Task040 用途 |
|---|---|---:|---|---|
| Hybrid direct h4 | 完整 workflow | `93.377006531 GiB` | matched reference pass | direct 内存基线 |
| exact-side Hybrid iterative h4 | 完整 workflow | `80.025856018 GiB` | five residual、recovery、R/T/A、E/H、canonical、channels pass | 当前最好 iterative authority |
| exact-side outer solver | 完整 workflow | `1` outer iteration | fixed exact block-LDU | 数值 oracle，不是长期生产 PC |

### 2.2 side factor 的阶段内存

下表是同一完整 exact-side formal 的 stage-aligned process-tree RSS，不是对象字节相加：

| 阶段 | RSS | 解释 |
|---|---:|---|
| `bottom_F_ready` | `23.195 GiB` | 尚未建立 bottom factor |
| `bottom_factor_ready` | `49.313 GiB` | 一个完整 bottom factor 驻留 |
| `bottom_construction_cleanup` | `45.386 GiB` | construction 临时对象释放，factor仍驻留 |
| `top_F_ready` | `51.298 GiB` | bottom factor仍在，top F进入 |
| `top_factor_ready` | `79.464 GiB` | bottom/top 两个完整 factor 同时驻留 |
| `top_woodbury_ready` | `80.025856018 GiB` | 当前完整 workflow 峰值 |
| `modal_schur_ready` | `76.742 GiB` | modal Schur 没有产生新峰值 |
| `outer_ksp_setup_ready` | `76.938 GiB` | Krylov storage不是当前主峰 |

由阶段差分可见，一个 side factor及其 MUMPS/PETSc运行时大约增加 `26–28 GiB` RSS。
这只是 stage attribution，不得把差分冒充精确 factor bytes。

### 2.3 已有低内存负结果

| 候选 | bottom component peak | 主要思想 | 数值结果 |
|---|---:|---|---|
| six-layer `J1` | 约 `22.27 GiB` | 六个层对角 factor | worst residual约 `45`，失败 |
| `F1/FB1/FB2/FB4` | 约 `22.27 GiB` | 简单 forward/backward 与 defect correction | 不收缩并最终发散 |
| two-layer `SN2-J` | 约 `22–27 GiB` | `[0,1]/[2,3]/[4,5]` 三个 supernode factors | finite后 worst bare-F residual约 `17.09`，失败 |
| `J1`-inner-FGMRES | `22.007 GiB` | J1作为完整 side Krylov PC | 16步 residual仍约 `0.997–0.999` |
| raw-load Petrov | 约 `23 GiB` | load-vector coarse basis | rank512仍数值失败 |

这些结果证明：删除 full side factor 后，内存可回到 `20–30 GiB` 级；但已有分区边界和
预条件器没有正确传递短波长 Maxwell 波，因此不能直接用于完整 Hybrid。

---

## 3. 冻结物理、离散与软件身份

整个 Task040 正式 campaign 冻结：

```text
wavelength                       = 5.0 nm
grazing angle                    = 1 deg
azimuth                          = 0 deg
polarization                     = S
geometry/material                = Task039 h4 formal identity unchanged
finite element                   = p6 Nedelec H(curl)
mesh                             = h4 formal mesh identity unchanged
scalar/index                     = complex128 / existing PETSc IntType
Floquet x/y                      = unchanged
Hybrid internal modes            = M480 positive + M480 negative
selected-mode packet             = existing hash-bound Task039 packet
external mode keys/order         = unchanged
static condensation              = unchanged
explicit side F matrices         = unchanged in this campaign
current external DtN/Woodbury    = unchanged
modal traction/projection        = unchanged
modal Schur definition/sign/order = unchanged
global Hybrid MatPython action   = unchanged
recovery/postprocessing/checker  = unchanged
MPI                              = 8 for h4 formal components
threads                          = 1 unless inherited authority states otherwise
```

正式 heavy run 应优先复用已资格化 selected-mode packet，并记录：

```text
qep_calls = 0
consumer_qep_required = false
```

若复用 packet 的 identity、hash、external keys 或 physical model不一致，必须停止；不得静默
重做 QEP 或改 M。

---

## 4. 唯一允许改变的对象

Task040 初始 campaign 只允许改变：

```text
bottom_action / top_action 中用于替代 full side factor 的 preconditioner与inner solver
```

具体而言，当前 exact-side 路径中的：

```text
full side MUMPS factor solve
```

改为：

```text
right-preconditioned inner FGMRES
+
fixed z-partition impedance forward/backward Schwarz PC
```

以下全部保持不变：

```text
side operator RHS
side F action
DtN C/D/H 与现有作用
Hybrid coupling
modal Schur algebra
outer Hybrid equation
recovery和physics
```

---

## 5. 数学路线

### 5.1 第一阶段只解 bare side `F`

先隔离 finite-element side factor问题：

```math
F_s x=b,
\qquad s\in\{bottom,top\}.
```

此阶段不通过 Woodbury，也不改变或重新设计 DtN。目的是回答：

> 新 PC 是否能在不建立 full `F_s` factor 的情况下，稳定加速同一个显式 `F_s` 方程？

### 5.2 固定 z 分区

沿用已经审计过的六层结构，并固定为三个非重叠 two-layer subdomains：

```text
subdomain 0 = layers [0,1]
subdomain 1 = layers [2,3]
subdomain 2 = layers [4,5]
```

初始正式候选不得改变分区数、层组合或 ordering。

### 5.3 与旧 SN2 的关键区别：impedance artificial interface

旧 SN2 只取 principal block，人工截面近似为零延拓，容易把波反射回来。新局部块概念上为：

```math
\widetilde B_j
=
R_j F_s R_j^T
+
T_j^-
+
T_j^+,
```

其中 `T_j^-` 和 `T_j^+` 是人工截面上的固定一阶切向 impedance/Robin 项。
它们只属于 PC，不改变精确 `F_s` 方程。

通俗地说：旧方法在子域边界放置“硬墙”；新方法尝试让离开一个子域的波自然传给下一个
子域，减少人工反射。

Task038-extra 分支中的 first-order impedance facet action和 sweep只能作为只读参考；不得整体
merge/cherry-pick该分支。若选择性适配代码，必须在 Task040 分支重新命名、重新测试并证明：

```text
static-condensed trace identity正确
Nedelec orientation正确
Floquet/MPC phase只施加一次
MPI owner/ghost正确
未引入dynamic DtN、full-space operator或Task038-extra runner
```

### 5.4 固定 forward/backward multiplicative apply

一次 PC apply 固定为：

```text
forward:  subdomain 0 -> 1 -> 2
backward: subdomain 2 -> 1 -> 0
```

传递的是人工截面 Robin/impedance data，而不是旧 F1 的普通零延拓 residual。
不得扫描 sweep count、ordering或 damping。

### 5.5 PC 只作为 inner FGMRES 预条件器

新 PC 不被要求一次 apply 就等于 `F_s^-1`。它的作用是改善谱，使 inner FGMRES逐步求解
bare `F_s`。

固定 checkpoint：

```text
8 -> 16 -> 32 -> conditional 64
```

只有在32步时 true residual仍有限、持续下降、最近8步至少下降0.25 decade，且内存/时间
Gate均通过时，才允许64。不得测试其他budget、restart或tolerance菜单。

### 5.6 bare `F` 通过后才进入完整 side operator

完整 side equation概念上写为：

```math
A_s x=b,
```

其中 `A_s` 是当前代码已经使用的 FEM + external DtN side action。正负号、C/D/H定义和
normalization完全以现有代码与 exact-side authority为准，不从本文符号猜测。

此阶段必须：

```text
直接用FGMRES迭代完整 A_s action
```

禁止把近似 `F_s^-1` 代入“精确 Woodbury恒等式”后冒充 exact side inverse。
当前 DtN implementation保持原样，只作为精确 operator action参与迭代。

---

## 6. 严格控制变量与禁止项

Task040 初始 campaign 禁止：

```text
修改波长、材料、几何、角度、偏振、p/h、M或MPI
重跑 Hybrid direct
重跑 V7 exact-side full formal
重跑 response-packet producer
修改 global Hybrid MatPython action
把显式 side F 改成matrix-free
引入 dynamic/streaming DtN redesign
改变 C/D/H、W/K、external keys或normalization
改变 modal traction/projection/modal Schur
增加 coarse space、Petrov、trace-harmonic或local spectral modes
增加 second-order/rational impedance
扫描 Robin/impedance 参数
扫描 overlap宽度
扫描分区数或supernode组合
扫描 ILU/BLR/drop tolerance/restart
继续 J1/F1/FB8/FB16 或原SN2-J/SGS
使用response packet作为生产 inverse
运行 Full3D heavy
运行0.7 nm PDE
修改 ordinary defaults
写入或合并 master、Task039或其他分支
```

---

## 7. 冻结 RHS 与数值检查

bottom component 使用 Task039 已冻结并可重建的 source family：

```text
modal traction positive
modal traction negative
external DtN coupling
fixed random repeat 0
fixed random repeat 1
physical side RHS（若为零，只作zero-map，不进入relative residual）
```

每个 source必须记录：

```text
input/output finite
zero-map
repeat
linearity
one-apply contraction
inner FGMRES true residual checkpoints
KSP reason
apply count
wall
process-tree RSS
swap
```

定义一次 PC apply 的 contraction：

```math
\rho_b
=
\frac{\lVert b-F_s M_s^{-1}b\rVert_2}{\lVert b\rVert_2}.
```

该值只是预条件器强度诊断，不代替最终 inner true residual。

---

## 8. Gate

### 8.1 实现与代数 Gate

```text
all outputs finite                         = true
zero input maps to zero                    <= 1e-13 relative/absolute contract
repeat relative error                      <= 1e-10
linearity relative error                   <= 1e-10
restriction/prolongation round trip        <= 1e-12
MPI2/MPI4 tiny physical identity           <= 1e-12
forbidden factor inventory                 = full-side 0, global 0
```

局部 three-subdomain factors允许存在；必须报告每个factor rows、NNZ、memory和owner。

### 8.2 单次 PC apply推进 Gate

```text
all mandatory rho                          < 1.0
worst mandatory rho for inner-FGMRES start <= 0.95
modal+/modal-/external rho preferred       <= 0.90
```

若所有 source均收缩但 worst位于 `(0.95,1.0)`，保存为 `STABLE_BUT_TOO_WEAK`，不启动重型
inner FGMRES。不得通过调参数追逐推进。

### 8.3 bare `F` inner FGMRES Gate

在固定budget中，首个同时满足下列条件的budget为 preferred：

```text
all mandatory true residual <= 1e-2
modal+/modal-/external       <= 1e-3
all finite                   = true
swap                         = 0
```

若32步没有持续下降，64不得运行。若64仍未通过，nonoverlap family关闭。

### 8.4 bottom 资源 Gate

当前 exact bottom factor阶段基线：

```text
49.313 GiB process-tree RSS
```

Task040 bottom candidate分级：

| 分类 | bottom construction/process peak |
|---|---:|
| 资源失败 | `>=49.313 GiB` |
| 最低正结果 | `<49.313 GiB` |
| meaningful | `<=35 GiB` |
| strong | `<=30 GiB` |

还必须满足：

```text
post-setup retained state <= 30 GiB
full-side exact factor    = 0
swap                      = 0
```

### 8.5 完整 `A_bottom` Gate

只有 bare `F_bottom` preferred candidate存在时，才用完全相同配置求完整 `A_bottom`：

```text
all mandatory true residual <= 1e-2
modal+/modal-/external       <= 1e-3
no full-side factor
bottom peak                  <49.313 GiB
```

不得为完整 `A_bottom` 重新调整 impedance、partition、budget或ordering。

### 8.6 top 与完整 Hybrid Gate

bottom通过后，top必须使用完全相同的算法配置；允许的差异只来自 top实际矩阵、外边界和
source数值，不得单独调参。

bottom/top均通过后，先运行 both-side setup-only：

```text
full-side bottom/top factors = 0/0
both-side setup peak          <80.025856018 GiB
swap                          = 0
```

通过后才允许一次完整 Hybrid formal。因为 inner side solve可能是可变近似，outer必须使用
FGMRES。完整数值/物理 Gate沿用 Task039 V7 authority：

```text
reported/global/bottom/top/modal true residual <= 5e-9
projection bottom/top/combined                  <= 1e-8
exact traction bottom/top                       <= 1e-8
R/T/A/A_volume delta vs matched direct          <= 1e-6
selected E/H relative L2                        <= 5e-3 / 1e-2
canonical active/full relative L2               <= 1e-5
power-weighted channels                         <= 1e-4
external keys/order                             = exact
normal flux/orders/powers/amplitudes            = inherited Gate pass
all finite/swap                                 = true/0
```

完整 workflow memory分级：

| 分类 | full workflow peak |
|---|---:|
| 不低于当前最好 iterative | `>=80.025856018 GiB` |
| 新最低点 | `<80.025856018 GiB` |
| 至少节省20% vs direct | `<=74.701605225 GiB` |
| 至少节省30% vs direct | `<=65.363904572 GiB` |
| 至少节省40% vs direct | `<=56.026203919 GiB` |
| 至少节省50% vs direct | `<=46.688503266 GiB` |

即使未达到50%，也必须报告真实 Pareto极限，不得把低于direct但未达50%的结果统一写成失败。

---

## 9. 唯一条件 fallback：一层 overlap

只有 nonoverlap candidate满足以下全部条件时，才允许一个 fallback：

```text
所有single-apply rho <1
至少三个mandatory source rho <=0.90
inner FGMRES有稳定下降但到64仍未通过
资源 <=35 GiB
```

唯一允许变化是：

```text
每个人工接口增加一层真实z-layer overlap
```

其他全部冻结：

```text
同一first-order impedance
同一三组core partition
同一forward/backward order
同一FGMRES ladder
无coarse、无local spectral、无dynamic DtN
```

overlap版本只允许一次完整 bottom component。若仍未通过，Task040 初始 PC family关闭，
由下一轮 review决定是否引入 coarse/local spectral；Codex不得自行扩展。

---

## 10. 执行顺序

```text
T40-0  inherited audit，docs-only
T40-1  impedance/artificial-interface algebra与tiny MPI identity
T40-2  bottom bare-F nonoverlap PC construction + one-apply contraction
T40-3  条件 bottom bare-F inner FGMRES 8/16/32/(64)
T40-4  条件 one-layer-overlap fallback，完整bottom一次
T40-5  preferred配置求完整 A_bottom，DtN保持不变
T40-6  同配置 top bare-F + A_top
T40-7  both-side setup-only
T40-8  条件唯一一次 full Hybrid formal
T40-9  outcomes、Pareto、response_v1.md并停止
```

任一前置 Gate失败时，后续阶段标记 `not_run_by_gate`，保存真实负结果后停止，不得自动换新PC。

---

## 11. T40-0 第一提交

Codex第一项提交必须是 docs-only：

```text
docs(task040): audit inherited side-factor baseline
```

创建：

```text
docs/task040_hybrid_side_factor_pc/outcomes/inherited_audit.md
docs/task040_hybrid_side_factor_pc/outcomes/baseline_memory_attribution.md
docs/task040_hybrid_side_factor_pc/outcomes/task038_extra_reference_boundary.md
```

至少记录：

```text
branch/HEAD/upstream/ahead-behind/worktree
base Task039 SHA = 9dc9ac58e05e5422498dade503046f9ae87d13d9
input/resolved/physical/selected-packet hashes
93.377 / 80.026 GiB full baselines
23.195 / 49.313 / 79.464 / 80.026 GiB stage baselines
old J1/F1/FB/SN2/J1-FGMRES negative identities
Task038-extra only-read reference files and explicit non-migration boundary
ABI/MPI/threads/MemAvailable/swap/disk/watchdog
all Task040 forbidden routes
```

第一提交不得修改Python、input、config、schema或benchmark result。

---

## 12. 允许修改与代码组织

允许：

```text
在src/solvers/中新增通用static-condensed side impedance Schwarz模块
对现有Task039 hybrid side action增加显式opt-in research hook
新增focused tests、tiny MPI tests、通用参数化benchmark runner/checker
新增Task040专用.dat，只能表达同一冻结物理与显式research profile
新增Task040 outcomes、compact records和response
```

数值核心不得只写在task-numbered benchmark脚本中。benchmark只负责参数、watchdog、telemetry、
checker和artifact orchestration。

不得整体复制 Task038-extra 文件；选择性参考必须在 `inherited_audit` 中列出来源、依赖、改写
理由和fresh tests。

---

## 13. 时间与资源运行规则

```text
one heavy job at a time
swap = 0
default heavy timeout = 21600 s (6 h)
```

只有已经进入 inner或outer FGMRES，且同时满足：

```text
RSS低于对应exact-factor或full-workflow基线
无NaN/Inf
迭代持续增加
最近90分钟有至少4个true-residual checkpoint
残差持续下降至少0.5 decade，或已接近Gate且趋势明确
外推剩余时间 <=2 h
```

才允许一次延长到总计8小时。setup、factor construction、QEP、direct或尚未开始Krylov的过程
不得自动延长。

每次heavy必须记录：

```text
process-tree RSS/PSS/USS（PSS/USS若工具可用）
swap
max-rank RSS
wall与stage markers
factor inventory
KSP residual history
artifact hashes
termination reason
```

---

## 14. 测试与证据

最少测试顺序：

```text
formula/orientation/unit tests
serial tiny block test
MPI2 tiny physical identity
MPI4 tiny physical identity
focused existing Hybrid regression
bottom h4 component
conditional top/both/full
Ruff/format/compileall
document contract
git diff --check
```

正式 checker必须从raw字段重算：

```text
rho
true residual
repeat/linearity
factor count
memory tiers
full Hybrid physics deltas
```

不能只信任worker写入的status。

tracked evidence只保存轻量compact JSON/Markdown/config/hash；矩阵、factor、fields、timeline和完整
logs留在ignored `results/` 或 `benchmarks/artifacts/`。

---

## 15. 必需交付物

```text
docs/task040_hybrid_side_factor_pc/outcomes/summary.md
docs/task040_hybrid_side_factor_pc/outcomes/inherited_audit.md
docs/task040_hybrid_side_factor_pc/outcomes/baseline_memory_attribution.md
docs/task040_hybrid_side_factor_pc/outcomes/task038_extra_reference_boundary.md
docs/task040_hybrid_side_factor_pc/outcomes/impedance_interface_identity.md
docs/task040_hybrid_side_factor_pc/outcomes/bottom_bare_f_pc.md
docs/task040_hybrid_side_factor_pc/outcomes/bottom_full_side.md
docs/task040_hybrid_side_factor_pc/outcomes/top_full_side.md
docs/task040_hybrid_side_factor_pc/outcomes/both_side_setup.md
docs/task040_hybrid_side_factor_pc/outcomes/full_hybrid_result.md
docs/task040_hybrid_side_factor_pc/outcomes/memory_residual_time_pareto.md
docs/task040_hybrid_side_factor_pc/outcomes/test_summary.md
docs/task040_hybrid_side_factor_pc/response_v1.md
benchmarks/cases/<Task040 case>/records/<compact records>
```

未达到的阶段也必须创建对应 outcome，并明确写 `not_run_by_gate` 与停止原因；不得留空或伪写通过。

`outcomes/summary.md` 必须表格优先，至少包含：

```text
方法/阶段/作用范围
factor inventory
rows/NNZ
single-apply rho
FGMRES checkpoints
bottom/top/full residual
RSS/wall/swap
相对49.313/80.026/93.377 GiB的比较
失败与未运行项
0.7 nm意义和仍存blocker
selective merge分组
```

---

## 16. 停止条件

立即停止并保存证据：

```text
branch/base/worktree/ABI不合格
physical/input/packet/external-key identity不一致
Task039或master出现写入
full-side或global direct factor意外出现
swap >0
达到阶段hard memory line
任何NaN/Inf
impedance action identity失败
all mandatory rho并非全部<1
inner residual停滞或发散
bottom未通过却启动top/both/full
任何ordinary default改变
```

受控资源停止不等于算法数值失败；数值失败也不得写成OOM。所有分类必须区分：

```text
measured
derived
predicted
not_run
failed
controlled_stop
implementation_failure
```

---

## 17. 提交计划

建议按以下阶段提交，不要求每个阶段都产生重型运行：

```text
1. docs(task040): audit inherited side-factor baseline
2. feat(task040): add fixed impedance supernode PC core
3. test(task040): qualify impedance interface and MPI identity
4. bench(task040): record bottom bare-F PC evidence
5. feat/bench(task040): qualify conditional full-side and Hybrid path
6. docs(task040): close side-factor PC outcomes
```

不得 amend、rebase、force-push或删除负结果。完成后推送同一 Task040 分支并停止等待review。

---

## 18. Task040 完成判定

Task040 不以“必须节省50%”作为唯一完成条件。它必须给出以下之一：

### A. 完整正结果

```text
same Hybrid equation
full-side exact factors = 0/0
完整数值与物理Gate通过
workflow RSS <80.025856018 GiB
```

并按20/30/40/50% tier报告实际水平。

### B. side component正结果但完整Hybrid未建立

```text
bottom/top side residual通过
factor内存显著降低
both/full因明确后续blocker未完成
```

必须指出具体blocker和下一最小步骤。

### C. 有界负结果

```text
first-order impedance nonoverlap
+
唯一one-layer-overlap fallback
```

均不能在冻结budget和资源内通过，则关闭该初始PC family，并明确记录：

```text
最低实测内存
最佳rho/FGMRES residual
失败的source family
是否需要coarse/local spectral作为下一独立变量
```

无论A/B/C，Task040都必须回答：

> 在保持其他Hybrid组件不变时，仅替换两个local side factors，内存能够降低到哪里，数值代价是什么，
> 下一步是否必须引入全局/粗空间信息？
