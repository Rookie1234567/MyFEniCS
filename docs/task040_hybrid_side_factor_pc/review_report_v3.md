# Task040 Review Report V3：联合接口 coarse correction 与可扩展 side inverse 决策树

## 0. 审阅身份与正式裁决

```text
review                                      = Task040 Review Report V3
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review          = 01bf31fe06931e66b2f4c2ceaa86f206b15a1571
reviewed_response                           = response_v3.md
reviewed_producer_record                    = task040_v2_interface_schur_packet_producer_v1.json
reviewed_consumer_record                    = task040_v2_projected_transmission_consumer_v1.json
review_status                               = PASS_WITH_QUALIFICATIONS
packet_producer                             = PASS_DIAGNOSTIC_ORACLE
canonical_cross_process_remap               = PASS
projected_groupwise_sweep                   = CONTROLLED_NUMERICAL_NEGATIVE
scalar_transmission                         = CLOSED
same_span_analytic_groupwise_route          = NOT_AUTHORIZED_AS_NEXT_STEP
primary_blocker                             = missing_coupled_long_range_interface_correction
next_primary_action                         = COUPLED_LOWER_UPPER_PROJECTED_INTERFACE_SOLVE
same_branch_continuation                    = required
new_branch                                  = forbidden
master_or_Task039_write                     = forbidden
ordinary_default_change                     = forbidden
merge_approval                              = NO
physical_case                               = 5 nm / 1 deg grazing / phi=0 / S / p6h4 / M480 / MPI8
QEP_M_physical_DtN_global_Hybrid_change     = forbidden
full_0p7nm_PDE                              = forbidden
response_required                           = response_v4.md
```

本轮审阅始终围绕 Task040 的唯一主线：

> 用稳定、低内存、可扩展的 iterative side inverse 替代 bottom/top 两个完整 exact MUMPS
> side factors，并且所得架构在 0.7 nm 更密网格下不能重新退化成增长型大 factor。

正式裁决如下：

1. V2-A1 producer 已在 `28.706955 GiB` 内生成完整、hash-bound、owner-row 分布的
   interface-Schur packet；其 exact oracle factor 生命周期 `3 -> 0`，该基础设施通过；
2. V2-B2 fresh consumer 已在 `32.453453 GiB` 内完成 packet remap、projected action、
   one-apply 和 FGMRES screen；其资源与实现身份通过；
3. 五个非零 source 在 16 步后的 true residual 仍为 `0.99365–0.99647`，所以当前
   “三个 group 分别修正后再按 `0 -> 1 -> 2 -> 2 -> 1 -> 0` sweep”是真实数值负结果；
4. 当前负结果不能继续归因于内存、packet、canonical owner remap、local exact solve或简单
   scalar幅值问题；主要未决问题是：lower/upper两个人工截面是否必须作为一个耦合系统同时求解；
5. 下一阶段不增加 mode count、不调 beta、不改 sign、不改 QEP、physical DtN 或 Hybrid 方程；
   只改变现有接口信息的**组合方式**：由三个独立 projected local inverse + sweep，改为一个
   lower/upper 联合 reduced interface solve；
6. 联合 full-span `296 + 480 = 776` 系统只允许作为 mechanism oracle。Task040 的最终
   0.7 nm-oriented 候选必须进一步满足 bounded coarse rank、无 full-cross-section factor、
   bounded patch size 和近线性 PC resident memory；
7. 只有联合接口机制与 bounded-rank coarse 均通过，才允许继续替换三个横跨整个 x/y 截面的
   exact group factors。不得把更弱的 bounded patch solve接到已经失败的 groupwise sweep上。

---

## 1. 已审阅事实

### 1.1 完整 workflow 基线

| 路线 | 范围 | process-tree RSS peak | 数值/物理状态 | 当前用途 |
|---|---|---:|---|---|
| Hybrid direct h4 | full workflow | `93.377006531 GiB` | matched authority pass | direct reference |
| exact-side Hybrid iterative h4 | full workflow | `80.025856018 GiB` | residual、recovery、R/T/A、E/H、canonical、channels pass | 当前最好完整 iterative authority |
| V2-A1 packet producer | bottom interface oracle component | `28.706954956 GiB` | packet/identity/lifecycle pass | diagnostic only |
| V2-B2 projected consumer | bottom bare-F component | `32.453453064 GiB` | resource/identity pass，numerical fail | current negative candidate |

producer/consumer 是相互独立的组件进程；它们的峰值不能相加，也不能冒充完整 workflow
saving tier。当前完整 workflow 最好结果仍为 `80.025856018 GiB`。

### 1.2 V2-B2 数值负结果

| source | one-apply `rho*` | direction correlation | FGMRES `r16` |
|---|---:|---:|---:|
| modal traction positive | `0.9991091943` | `0.0421997381` | `0.9936534709` |
| modal traction negative | `0.9992000839` | `0.0399899035` | `0.9964222028` |
| external DtN coupling | `0.9992621061` | `0.0384088973` | `0.9939467694` |
| fixed random repeat 0 | `0.9990697662` | `0.0431231059` | `0.9963350357` |
| fixed random repeat 1 | `0.9990604726` | `0.0433378831` | `0.9964721804` |

这些数据说明 projected correction 不是单纯缩放不合适，而是没有生成足够有用的全局 Krylov
方向。32 步没有授权是正确的；不得继续增加当前 groupwise route 的迭代预算。

证据入口：

- [response_v3.md](response_v3.md)
- [projected consumer outcome](outcomes/projected_transmission_consumer.md)
- [producer outcome](outcomes/interface_schur_packet_producer.md)
- [consumer compact record](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v2_projected_transmission_consumer_v1.json)
- [producer compact record](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v2_interface_schur_packet_producer_v1.json)

---

## 2. 当前负结果为什么指向“联合接口系统”

### 2.1 三分区的真实接口结构

bottom side 仍使用冻结分区：

```text
group0 = layers [0,1]
group1 = layers [2,3]
group2 = layers [4,5]
```

两个内部人工截面分别记为：

```text
Gamma_L = group0 / group1 interface
Gamma_U = group1 / group2 interface
```

消去各 group interior 后，真实接口 Schur operator 不是两个互不相关的局部量，而具有
四个 block：

```math
S_\Gamma
=
\begin{bmatrix}
S_0 + S_{1,LL} & S_{1,LU} \\
S_{1,UL} & S_2 + S_{1,UU}
\end{bmatrix}.
```

其中：

```text
S_0                 = group0 对 lower interface 的贡献
S_2                 = group2 对 upper interface 的贡献
S_1,LL / S_1,UU     = middle group 的同接口贡献
S_1,LU / S_1,UL     = middle group 跨 lower/upper interface 的长程耦合
```

V2 producer 已记录 middle-cross probes；当前 consumer则把 projected correction嵌入三个
独立 group inverse，再依赖 sweep逐步传播。该结构没有一次性求解 lower/upper 两个截面的耦合
系数，因此无法判断失败来自 mode span不足，还是来自 sweep没有正确处理 `S_{1,LU}` 和
`S_{1,UL}`。

### 2.2 下一候选的 reduced system

冻结 lower `296` 个 Fourier/Floquet方向与 upper `480` 个 QEP方向，构造：

```text
Z_Gamma = blockdiag(Z_L, Z_U)
Y_Gamma = blockdiag(Y_L, Y_U)
coarse dimension = 296 + 480 = 776
```

联合 Petrov reduced operator 为：

```math
E_\Gamma
=
Y_\Gamma^H S_\Gamma Z_\Gamma.
```

其 block 结构必须显式包含：

```math
E_\Gamma
=
\begin{bmatrix}
Y_L^H(S_0+S_{1,LL})Z_L & Y_L^H S_{1,LU} Z_U \\
Y_U^H S_{1,UL} Z_L & Y_U^H(S_2+S_{1,UU})Z_U
\end{bmatrix}.
```

给定经过局部消元后的接口 residual `g_Gamma`，一次联合 correction 为：

```math
E_\Gamma c = Y_\Gamma^H g_\Gamma,
```

```math
\lambda_\Gamma = Z_\Gamma c,
```

随后用相同 group operator完成 interior harmonic back-substitution。

实现可以采用等价的 balanced two-level形式，但必须在 tiny fixture和正式 sampled oracle中证明
与上述 Schur algebra一致；不得只把三个已有 local inverse包进另一个循环后称为 coupled solve。

---

## 3. 与最终 0.7 nm 主线的关系

### 3.1 为什么这不是旁支

当前 full-side exact factor很强，是因为它隐式编码了跨整个 side 的远距离耦合。J1、SN2、
scalar impedance和当前 projected sweep都只保留局部或逐段信息，因此短波长下几乎不收敛。
联合接口 coarse correction要解决的正是 exact factor中最难替代的长程部分：

```text
local bounded solver       -> 处理局部高频误差
coupled interface coarse   -> 处理跨截面、跨group、长距离传播误差
FGMRES                     -> 组合二者并修正剩余误差
```

这是替代 exact side factor所需的两级结构，不是另一个独立物理模型。

### 3.2 full-rank 776 只属于 mechanism oracle

`776 x 776 complex128` 小矩阵本身只约 `9.2 MiB`，在5 nm组件内不是内存瓶颈；但 mode数会随
0.7 nm和更密横截面增加，因此不能把“5 nm full 776 direct coarse solve通过”直接写成
0.7 nm scalable pass。

Task040 的最终可扩展候选还必须满足：

```text
full-side exact factor                 = 0
full-cross-section exact group factor  = 0
global Hybrid direct factor            = 0
global direct coarse factor            = 0, except bounded fixed-rank small solve
FE-sized numeric allgather             = false
per-rank replicated full basis         = false
max_local_rows                         <= 1024
bounded coarse rank                    <= 512
PC resident memory growth target       = O(N)
```

因此必须区分：

```text
COUPLED_INTERFACE_MECHANISM_PASS_ONLY
BOUNDED_COARSE_PASS
SCALABLE_SIDE_INVERSE_CANDIDATE
FULL_HYBRID_LOWER_MEMORY_PASS
```

---

## 4. 冻结项与允许修改

本轮继续冻结：

```text
5 nm / 1 deg grazing / phi=0 / S
p6/h4 / M480 / MPI8 / threads1
material / geometry / Floquet
selected-mode packet、mode keys、beta branches和normalization
static condensation和explicit bare F operator
physical external DtN / C-D-H-W-K
modal traction / projection / modal Schur
global Hybrid MatPython action
recovery / R-T-A / E-H / canonical / channel checker
```

只允许修改：

```text
现有人工接口数据如何组合成side preconditioner
conditional bounded-rank selection
mechanism通过后的bounded local group solve
```

禁止：

```text
重跑或改变QEP
改变M480或扫描mode count
调scalar beta、sign、damping或sweep count
增加普通ILU/BLR参数菜单
修改physical DtN
dynamic DtN redesign
修改global Hybrid operator
重跑Hybrid direct或exact-side authority
完整0.7 nm PDE
```

---

## 5. Implementation bug 自主修复权限

Codex可自行最小修复并继续：

```text
syntax/import/type/path/package invocation
packet field、schema、hash、canonical key和owner remap接线
PETSc Vec/Mat ownership、scatter、workspace alias
block ordering、lower/upper slice、small-matrix shape接线
对象destroy顺序和明确内存泄漏
checker、watchdog、telemetry和artifact registry
由独立tiny/exact oracle证明的orientation、transpose或phase-once bug
```

要求：保留失败root，标为`implementation_failure`；先用unit/tiny/MPI测试复现；最小修复；
增加回归测试；绑定新source SHA后重跑同一阶段。下列变化不是bug fix，必须按Gate停止：

```text
更改mode span或basis family
调参数追逐残差
改变分区或增加overlap
增加新coarse family
放宽残差、内存、rank或local-row上限
```

---

# 6. 连续执行顺序

```text
V3-0  inherited audit
V3-1  packet-only coupled-algebra audit与failure decomposition
V3-2  full-span coupled-interface mechanism oracle
V3-3  bounded-rank coupled coarse audit
V3-4  coupled coarse的packet-independent生产重构
V3-5  bounded local patch Level B
V3-6  bottom full side / top / both / full Hybrid
V3-7  conditional h3 scalability probe
V3-8  evidence、Pareto、response_v4.md
```

正常通过或可修复implementation bug后，Codex自动继续；只有本Review定义的真实数值、资源、
可扩展性或信息完整性Gate才停止等待审阅。

---

## 7. V3-0：继承审计

第一提交：

```text
docs(task040): audit review v3 coupled interface campaign
```

创建或更新：

```text
outcomes/review_v3_inherited_audit.md
outcomes/coupled_interface_algebra.md
outcomes/coupled_interface_consumer.md
outcomes/bounded_coupled_coarse.md
outcomes/production_side_inverse.md
```

至少绑定：

```text
branch / HEAD / upstream / worktree
review_report_v3 identity
response_v3、producer/consumer compact hashes
packet manifest SHA256
input / physical / selected-mode / probe / spool hashes
93.377 / 80.026 / 28.707 / 32.453 GiB baselines
V2-B residual table和classification
所有冻结项和禁止项
```

V3-0只允许docs，不运行heavy。

---

## 8. V3-1：packet-only coupled algebra与失败分解

本阶段优先使用已有packet，不组装PDE、不构造factor、不运行QEP。

### 8.1 必须核对的small-matrix inventory

独立列出每个group的：

```text
Gram = Y^H Z
projected_scalar = Y^H S_scalar Z
projected_exact = Y^H S_exact Z
shape / rank / singular values / condition / SHA256
```

必须证明：

```text
group0 span = 296
group1 span = 776，column/row顺序严格为lower296后upper480
group2 span = 480
```

随后从group1矩阵显式切出：

```text
LL / LU / UL / UU
```

并报告四个block的Frobenius norm、相对norm、rank和hash。`LU/UL`不得被默认为零。

### 8.2 联合矩阵组装

按冻结ordering构造：

```math
E_{joint}
=
E_1
+
\operatorname{blockdiag}(E_0,E_2).
```

这里的`E0/E1/E2`必须使用同一种left/right dual和coefficient convention。若Gram不是单位阵，
不得使用normal equations；允许complex SVD、rank-revealing QR或直接Petrov solve。

### 8.3 独立tiny fixture

建立一个complex、non-Hermitian、三分区block-tridiagonal tiny system，独立比较：

```text
直接消去interiors得到的full interface Schur
按E1 + blockdiag(E0,E2)组装的joint Schur
joint reduced solve后的full residual
错误省略LU/UL cross block的负对照
```

误差目标：

```text
matrix/action relative error <= 1e-12
solution/full residual       <= 1e-12
```

### 8.4 packet failure decomposition

分别汇总：

```text
physical trace probes
modal-combination probes
complement probes
middle lower-to-upper probes
middle upper-to-lower probes
```

报告每类的：

```text
scalar-exact error
projected-exact error
in-span projection error
complement orthogonality
cross-interface energy ratio
```

### 8.5 V3-1 Gate

通过条件：

```text
packet identity/hashes pass
joint matrix finite
full expected rank或有明确数值rank
condition <= 1e12
cross-block ordering identity pass
tiny fixture pass
现有packet足以构造joint operator
```

如果已有packet只缺少一个可从同一producer内存结果直接序列化的small matrix，允许一次最小
packet-schema增强和一次producer重跑；不得改变probe、basis、mode span或Schur公式。

若必须重新求解新的物理问题才能补齐信息，则停止并分类：

```text
COUPLED_PACKET_INFORMATION_INCOMPLETE
```

---

## 9. V3-2：full-span coupled-interface mechanism oracle

### 9.1 目的

只回答：

> 在相同三分区、相同296/480 span和相同local exact group solve下，一次性求解两个接口的
> 776维耦合系统，能否让bare-F side equation进入可用FGMRES范围？

这一步用来区分：

```text
V2失败主要来自groupwise sweep
还是当前interface mode span本身不足
```

### 9.2 构造合同

fresh MPI8 consumer只读取已有packet，不构造exact interface Schur oracle。允许三个
cross-section exact group factors继续作为mechanism oracle，但必须：

```text
simultaneous factor max = 3
full-side factor         = 0
global direct factor     = 0
QEP calls                = 0
PDE solve                = not_run
```

一次PC apply必须执行等价于：

```text
1. local/group pre-correction
2. 计算未消除的lower/upper interface residual
3. 用Y_Gamma投影为776维RHS
4. 解E_joint c = rhs
5. 用Z_Gamma合成两个接口correction
6. 对三个group做一致的harmonic/interior back-substitution
7. 返回full side correction
```

不得退化成三个independent local projected inverses后再sweep。

### 9.3 full-rank reduced solve

允许：

```text
rank = 776
complex128
SVD / QR / dense LU as mechanism oracle
```

禁止normal equations。必须报告：

```text
E_joint rank / singular values / condition
LL/LU/UL/UU norms
solve repeat error
one-apply linearity
coarse residual
full bare-F true residual
```

### 9.4 FGMRES screen

冻结五个非零source和physical zero-map，运行：

```text
checkpoints = 0 / 4 / 8 / 16
conditional 32
conditional 64
```

32只在16步后全部finite且最近8步至少下降`0.25 decade`时授权；64只在32步最坏residual
`<=0.1`且最近16步继续单调下降时授权。禁止其他budget。

### 9.5 数值Gate

首个checkpoint同时满足：

```text
all mandatory true residual <= 1e-2
modal+ / modal- / external  <= 1e-3
```

则分类：

```text
COUPLED_INTERFACE_FULL_SPAN_PASS
```

若tiny/packet/in-span action identity通过，但64步仍不通过，分类：

```text
COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL
```

此时不得继续analytic same-span、bounded patch或更多Krylov；当前296/480 span或harmonic lift
不足，Task040在本Review停止等待下一轮。

### 9.6 资源Gate

```text
peak process-tree RSS < 45 GiB
swap = 0
exact-interface oracle factor = 0
full-side/global factor = 0/0
three group factors only
cleanup = 3 -> 0
```

`776 x 776` reduced factor必须单独记账，不得混入group factor count。

---

## 10. V3-3：bounded-rank coupled coarse audit

只有V3-2 full-span通过后才运行。

### 10.1 目标

full 776证明机制，不证明0.7 nm可扩展。必须从同一joint operator中形成嵌套、可重构的
bounded-rank coarse family：

```text
rank 64
rank 128
rank 256
rank 512
```

不允许其他rank菜单。basis选择必须使用complex biorthogonal SVD、RRQR或等价稳定方法，并
绑定mode-key/linear-combination coefficients；不得按列号随意截断。

### 10.2 Gate

每个rank运行相同one-apply和FGMRES `4/8/16/条件32/64`。选择首个满足V3-2数值Gate的最小
rank，并记录：

```text
rank
basis identity/hash
E condition
one-apply rho/rho*/correlation
FGMRES checkpoints
RSS / wall
```

若rank512仍不通过但full776通过，分类：

```text
FULL_SPAN_MECHANISM_PASS_BUT_BOUNDED_COARSE_NOT_ESTABLISHED
```

停止，不进入Level B；不得把776 full rank称为0.7 nm scalable candidate。

若某一rank `<=512`通过，分类：

```text
BOUNDED_COUPLED_COARSE_PASS
```

并进入V3-4。

---

## 11. V3-4：packet-independent生产重构

现有exact-interface packet只能作为oracle。正式side-PC candidate不得要求运行exact packet
producer。

Codex必须使用冻结的：

```text
lower Fourier/Floquet modes
upper M480 QEP modes
V3-3 selected linear-combination coefficients
explicit bare-F action
```

在fresh进程中重建同一bounded coarse basis和coarse matrix。允许使用bounded local iterative
harmonic extension；禁止读取exact U/V owner-row values作为生产输入。

必须证明：

```text
selected mode-key/coeff identity exact
oracle-vs-production basis subspace angle
oracle-vs-production E action error
one-apply/FGMRES Gate
exact packet producer not required
exact-interface oracle factor = 0
```

目标误差：

```text
subspace principal-angle sine max <= 1e-8
coarse action relative error        <= 1e-8
```

若生产重构无法达到数值Gate，分类：

```text
EXACT_ORACLE_DEPENDENCE_NOT_REMOVED
```

停止；不得把packet-dependent fixed-case结果提升为可扩展side inverse。

---

## 12. V3-5：bounded local patch Level B

只有V3-4通过后才运行。保持coupled coarse basis和所有物理身份不变，唯一变化是删除三个
cross-section exact group factors，改为：

```text
local FGMRES
+
bounded overlapping patch PC
+
V3-4 bounded coupled coarse correction
```

可扩展性硬合同：

```text
full-cross-section exact factor = 0
full-side exact factor          = 0
max_local_rows                  <= 1024
factor class count              = bounded and reported
one factor owner                = deterministic
full basis per-rank replica     = false
FE-sized numeric allgather      = false
```

bottom bare-F资源：

```text
construction peak <= 35 GiB
strong target     <= 30 GiB
post-setup retain <= 30 GiB
swap              = 0
```

数值Gate沿用V3-2。若local PC用完固定`8/16/32/条件64`仍不通过，分类：

```text
BOUNDED_LOCAL_SOLVER_INSUFFICIENT
```

---

## 13. V3-6：bottom full side、top、both与完整Hybrid

### 13.1 bottom full side

bare-F通过后，保持physical DtN实现完全不变，直接对完整：

```math
A_s = F_s - C_s H_s^{-1} D_s
```

运行side FGMRES；不得把approximate `F^-1`强行代入精确Woodbury恒等式。

Gate：

```text
all mandatory side residual <= 1e-2
modal+ / modal- / external  <= 1e-3
full-side exact factor       = 0
```

### 13.2 top

bottom通过后，同一配置运行top；不得为top单独调rank、patch、budget或coarse。

### 13.3 both-side setup

```text
bottom full-side factor = 0
top full-side factor    = 0
global direct factor    = 0
swap                    = 0
```

### 13.4 唯一完整Hybrid formal

outer solver使用FGMRES。必须通过：

```text
reported/global/bottom/top/modal true residual <= 5e-9
recovery
R/T/A/A_volume
energy closure
selected E/H
canonical vectors
normal flux
diffraction orders/powers/amplitudes
```

完整内存分级：

| 分类 | full workflow peak |
|---|---:|
| 未刷新当前 iterative | `>=80.025856018 GiB` |
| 新最低点 | `<80.025856018 GiB` |
| 至少节省20% vs direct | `<=74.701605225 GiB` |
| 至少节省30% vs direct | `<=65.363904572 GiB` |
| 至少节省40% vs direct | `<=56.026203919 GiB` |
| 至少节省50% vs direct | `<=46.688503266 GiB` |

heavy run默认6小时；只有已进入outer solve、峰值低于80.026 GiB且true residual持续下降时，
才允许一次延长至总计8小时。

---

## 14. V3-7：条件h3扩展性probe

只有完整h4 scalable candidate通过后，才允许一次5 nm p6/h3 bottom-only probe。保持所有
rank、patch、coarse和Krylov配置不变。

必须报告：

```text
N_h4 / N_h3
PC retained bytes
local factor total bytes
coarse basis bytes
Krylov bytes
process-tree peak
max_local_rows
factor class cap
```

PC内存指数：

```math
p_{mem}
=
\frac{\log(B_{PC,h3}/B_{PC,h4})}
     {\log(N_{h3}/N_{h4})}.
```

战略Gate：

```text
p_mem <= 1.30
max_local_rows unchanged
bounded coarse rank unchanged
factor class cap不出现随global N无界增长
```

h3只提供0.7 nm架构扩展性证据，不是0.7 nm PDE或空间收敛资格。

---

## 15. 测试与独立证据

至少需要：

```text
tiny coupled Schur fixture
cross-block omission negative control
serial/MPI2/MPI4 packet joint assembly
canonical lower/upper ordering tests
complex left/right dual tests
bounded-rank nesting/reconstruction tests
watchdog/checker tamper tests
Ruff / format / compileall / git diff --check
check_benchmarks --no-write
```

checker必须从raw contractions、FGMRES history、factor inventory、packet hashes和watchdog
samples独立重算；不得相信worker自报status。

当前仓库已有Case104 whitelist文档合同缺口，Codex应在V3-0记录并按仓库规则判断是否属于可
自主修复的测试登记bug；不得将其与数值结果混写。

---

## 16. 真正停止条件

Codex只在以下情况停止等待审阅：

```text
COUPLED_PACKET_INFORMATION_INCOMPLETE
COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL
FULL_SPAN_MECHANISM_PASS_BUT_BOUNDED_COARSE_NOT_ESTABLISHED
EXACT_ORACLE_DEPENDENCE_NOT_REMOVED
BOUNDED_LOCAL_SOLVER_INSUFFICIENT
bottom/top/full-side真实数值Gate失败
resource hard stop或swap>0
max_local_rows > 1024
完整Hybrid residual/physics失败
h3 scalability Gate失败
或全部授权阶段完成
```

不得因为普通implementation bug、路径、checker、owner remap、telemetry或对象生命周期接线
问题提前停止；这些应按§5最小修复后继续。

---

## 17. Response V4 必答问题

`response_v4.md` 必须逐项回答：

1. V2失败究竟来自groupwise sweep，还是296/480 interface span本身不足？
2. `E_joint` 的LL/LU/UL/UU block norm、rank、condition是什么？
3. full776 coupled-interface oracle是否通过？首次通过的FGMRES checkpoint是什么？
4. 最小通过coarse rank是64/128/256/512中的哪一个？若均失败，实际极限是什么？
5. 正式candidate是否完全不依赖exact-interface packet producer？
6. bounded local patch的`max_local_rows`、factor inventory、RSS和residual是什么？
7. bottom/top/full side是否均在full-side factor=0下通过？
8. 完整Hybrid峰值、时间、五项residual和全部physics结果是什么？
9. h3 scaling是否支持0.7 nm更密网格下的近线性PC内存？
10. 哪些代码/测试可选择性复用，哪些只能保留为research-only负结果？

---

## 18. 合并边界

本Review不批准merge。即使V3出现正结果，Codex也只提交并推送Task40分支，等待最终审阅。

默认分类：

```text
research-only:
    exact interface oracle
    full776 mechanism solve
    historical scalar/projected negative routes

potential reusable after qualification:
    canonical packet/remap
    coupled reduced-matrix assembly
    bounded-rank distributed coarse carrier
    watchdog/checker/lifecycle utilities

production candidate only after full formal:
    packet-independent bounded coupled coarse
    bounded local patch side inverse
```

未经最终review和用户授权，不得合并`master`。
