# Task040 Review Report V6：exact-authority 救援、全接口波传播预条件器与 0.7 nm 可扩展架构

## 0. 审阅身份与正式裁决

```text
review                                      = Task040 Review Report V6
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review          = 00ac78e1e1960f45cad5dae65f244fe32e096cd9
reviewed_response                           = response_v6.md
reviewed_outcomes                           = summary.md + route_signal_ledger.md
review_status                               = CONTINUE_WITH_RESCUE_AND_ARCHITECTURE_PIVOT
V5_2_fresh_bare_F_authority                 = RESOURCE_TIME_WINDOW_BLOCKED_NOT_NUMERICAL_FAIL
V5_Route_C                                  = VALID_CONTROLLED_NO_SIGNAL
V5_Route_A_B                                = NOT_RUN
Task040_closed                              = false
Task040_primary_goal                        = replace bottom/top exact side factors
strategic_goal                              = credible path toward 0.7 nm within about 2 TB
old_776_response_family                     = DIAGNOSTIC_RESCUE_ONLY
new_primary_family                          = FULL_INTERFACE_WAVE_TRANSMISSION
new_general_fallback                        = ADAPTIVE_IMPEDANCE_SCHWARZ
final_local_service                         = BOUNDED_PATCH_OR_MATRIX_FREE_HCURL
execution_mode                              = ACCELERATED_ROUTE_SWITCHING
minimal_test_policy                         = FOCUSED_RISK_BASED
conditional_factor_only_rescue              = authorized_once
full_interface_exact_oracle                 = authorized_once
full_spectrum_sweep_oracle                  = authorized
moving_PML_sweep_fallback                   = authorized_once
adaptive_spectral_Schwarz_pilot             = authorized_conditionally
conditional_full_Hybrid                     = authorized_after_side_gates
full_target_0p7nm_PDE                       = forbidden_in_Task040
reduced_0p7nm_capacity_and_architecture      = mandatory
same_branch_continuation                    = required
new_execution_branch                        = forbidden
master_or_Task039_write                     = forbidden
ordinary_default_change                     = forbidden
merge_approval                              = NO
response_required                           = response_v7.md
```

本 Review 接受 V5 的真实负结果，但**不关闭 Task040，也不放弃 0.7 nm**。

V5 只否定了下面这一条具体路线：

```text
three full-cross-section groups
+ first-order scalar impedance
+ current 776-dimensional interface family
+ long right-FGMRES / harmonic-Ritz sampling
```

它没有否定：

```text
完整15120-row接口Schur求解
全频谱Floquet/DtN传输
moving-PML或source-transfer sweep
adaptive Maxwell-harmonic spectral coarse
bounded 3D patch Schwarz
matrix-free H(curl) multilevel local solve
```

因此，本 Review 的核心变化不是继续增加 Route C 的迭代数，而是把算法从
“固定小接口子空间”转向“完整接口上的波传播近似”，并把最终局部求解从横跨整个
`x/y` 截面的 factor 转向 bounded patch 或 matrix-free multilevel。

---

## 1. V5 结果的正式解释

### 1.1 fresh bare-`F` authority 未完成，不是数值失败

V5-2 已完成：

```text
五个 current-layout RHS
canonical active-row layout
Gamma_L / Gamma_U canonical layout
one-cell source factor lifecycle 1 -> 0
```

但完整 bottom bare-`F` factor 只到：

```text
v5_bare_f_factor_setup_begin
```

在授权的 `21600 s` 窗口内没有出现：

```text
factor-ready
exact-output packet
F_b x* - b true residual
```

资源事实为：

```text
peak process-tree RSS = 45432283136 B = about 42.31 GiB
swap                  = 0
55/58/64 GiB lines    = not exceeded
```

所以它的准确分类仍是：

```text
FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED
```

不是：

```text
bare-F numerical fail
MUMPS memory hard stop
operator identity fail
```

### 1.2 Route C 是真实 no-signal

V5 Route C 对两个规定 RHS 的结果为：

| source | r64 | r128 | 64→128趋势 |
|---|---:|---:|---|
| `external_dtn_coupling` | `0.8906247440` | `0.9116861469` | 变差 |
| `fixed_random_repeat_0` | `1.0368916759` | `1.0585987179` | 变差 |

同时：

```text
shared_slow_directions.count = 0
stable_components            = []
conditional 256              = not authorized
```

这证明继续同一 PC 到 `256/512/1000` 没有可信依据。

### 1.3 Route A/B 尚未被检验

由于没有 current bare-`F` exact output，V5 没有执行：

```text
exact trace representability
current Petrov vs metric-best projection
exact/Petrov/best group lift
mass-dual Route A
R1/R2/R3 exact-response Route B
```

因此不能把 Route A/B 写成数值失败。V6 允许完成这一项剩余救援，但它不再阻塞新的
full-interface 主线。

### 1.4 测试不是进度瓶颈

V5 consolidated focused tests 为：

```text
94 passed, 2 skipped in 11.31 s
```

文档合同为：

```text
26 passed in 1.35 s
```

时间主要消耗在重型 factor construction 和 Route C solve。V6 继续使用最小风险测试，
不通过增加或删除无关 pytest 来伪装数值进展。

---

## 2. 为什么 0.7 nm 不能沿用当前 80 GiB 架构

### 2.1 用户提出的缩放判断是正确警报

若为了保持每波长分辨率而令三维网格尺度满足：

```text
h proportional to lambda
```

则体自由度近似：

```math
N(\lambda)\propto \lambda^{-3}.
```

因此：

```text
5 nm -> 1 nm    : N multiplier ≈ 5^3 = 125
5 nm -> 0.7 nm  : N multiplier ≈ (5/0.7)^3 ≈ 364.43
```

即使错误地假设内存只随 `N` 线性增长：

```text
80 GiB * 125    ≈ 10 TiB
80 GiB * 364.43 ≈ 28.5 TiB
```

完整 sparse direct factor 通常比线性增长更差。因此：

> 约 2 TB 物理内存不能通过“继续保存两个完整 side factors”解决 0.7 nm。

### 2.2 80 GiB 不是不可降低的物理下限

Task39 的 `80.025856 GiB` 包含：

```text
bottom exact side factor
top exact side factor
explicit side operators
DtN/Hybrid objects
PETSc/MUMPS runtime overlap
```

它是当前成功实现的峰值，不是 Maxwell 方程的最低信息量。

0.7 nm 路线必须同时降低：

```text
asymptotic growth
bytes per DoF
global replication
lifecycle overlap
```

### 2.3 0.7 nm 可行架构必须满足

```text
volume operator             = matrix-free or streamed
side/global direct factor   = 0
full-cross-section factor   = 0 in final candidate
physical DtN W matrix       = 0; FFT/streaming action
local factor size           = bounded independent of global N
coarse information          = distributed and multilevel
Krylov storage              = bounded restart
full basis replication      = false
FE-sized numeric allgather  = false
swap                        = 0
```

仅把 80 GiB 降到 20–30 GiB 仍不够；若保持显式 `F` 和同样 bytes/DoF，乘以约 364 仍超过
2 TB。因此 V6 将区分：

```text
5NM_MECHANISM_PASS
5NM_FACTOR_FREE_SIDE_PASS
0P7NM_ARCHITECTURE_CANDIDATE
```

只有最后一类要求 matrix-free volume action 和 streaming physical DtN。

---

## 3. 当前 776 维路线为什么不是 0.7 nm 主架构

当前两个人工接口合计有：

```text
Gamma_L rows = 7560
Gamma_U rows = 7560
joint rows   = 15120
```

V3/V5 只保留：

```text
296 lower Fourier/Floquet directions
480 upper QEP modal directions
joint selected span = 776
```

V3 已证明 reduced `776 x 776` 小系统内部可以解到约 `1e-14`，但完整 side residual 仍弱。
V5 Route C 又证明，在相同 group/impedance family 下增加迭代并没有产生稳定共享方向。

旧 Task39 response-packet compression 还显示：训练列可被低秩空间很好拟合，但即使有效 rank
接近 `478`，某些冻结 holdout direction 的 projection error 仍接近 `0.97`。这说明固定闭集
response basis 容易过拟合 source family。

更重要的是，0.7 nm 的横向传播/近截止/evanescent channel 数会增长。一个固定、每 rank
复制、dense-factorized 的 `rank<=512` 全局 coarse 不能自动保持物理完整性。

V6 因此作如下合同修正：

```text
旧 response-coarse 路线：最终总rank仍 <=512
新 full-interface 路线：不使用固定全局rank
```

新路线允许分布式 spectral channels 随物理接口分辨率增长，但必须：

```text
owner-row distributed
FFT/streamed action
no dense global basis
no replicated full trace
no dense global factor
storage O(N_Gamma) or O(N_Gamma log N_Gamma)
```

这不是放宽内存纪律，而是从“复制一个固定 dense coarse”换成“分布式施加完整接口物理”。

---

## 4. 新主架构：完整接口上的波传播近似

### 4.1 它解决什么问题

当前 PC 对它认识的 776 个方向可以做准确 reduced solve，但可能丢失大量真实接口场。
新路线不再先压缩接口，而是直接保留完整接口 trace，并用近似 DtN 或 PML 表示波从一个
subdomain 传播到相邻 subdomain 的方式。

### 4.2 它改变计算流程的哪一步

旧流程：

```text
full interface residual
-> Y^H projection to 776 coefficients
-> solve 776 x 776
-> Z synthesis
-> group lift
```

新流程：

```text
full owner-row interface residual
-> full-spectrum Floquet transform or local PML transmission
-> forward/backward wave sweep
-> full owner-row interface correction
-> group/local solve
```

### 4.3 完整接口 Schur 形式

将 bottom bare `F_b` 的未知量分为 group interiors `I` 和两个接口 `Gamma`：

```math
F_b=
\begin{bmatrix}
F_{II} & F_{I\Gamma}\\
F_{\Gamma I} & F_{\Gamma\Gamma}
\end{bmatrix}.
```

完整接口 Schur operator 为：

```math
S_{\Gamma}
=F_{\Gamma\Gamma}
-F_{\Gamma I}F_{II}^{-1}F_{I\Gamma}.
```

V3 求的是：

```math
Y^H S_{\Gamma} Z.
```

V6 首先建立的是 `S_Gamma` 的完整 matrix-free action，不再经过 `Y/Z` 截断。

### 4.4 为什么可能有效

高频波动问题的主要困难不是局部高频误差本身，而是远距离传播、反射、近截止和
subdomain 间相位传递。近似 DtN transmission 或 moving-PML sweep 直接近似 block LU 中的
波传播项；adaptive Maxwell-harmonic coarse 再处理 heterogeneity 和全局慢误差。

### 4.5 代价和适用边界

- Fourier-DtN sweep 最适合人工接口附近存在可定义 background/layered symbol 的区域；
- moving-PML sweep 对非可分离材料更通用，但 local setup 更贵；
- adaptive spectral Schwarz 适用于 arbitrary 3D，但实现和 coarse selection 更复杂；
- full-cross-section exact group factors只允许作为 h4 mechanism oracle，不能进入最终候选。

### 4.6 文献与仓库证据定位

V6 的方法选择由以下公开研究和仓库历史共同支持：

```text
Bonazzoli et al., arXiv:1711.03789
    high-frequency Maxwell + absorption + two-level overlapping Schwarz

Li and Hu, arXiv:2501.18305
    impedance local problems + adaptive local Maxwell-harmonic coarse

Nicholls, Perez-Arancibia and Turc, arXiv:1809.05634
    quasiperiodic layered media + approximate DtN + double sweep
    该文是Helmholtz类比，不是本项目Maxwell通过证明

Fu, arXiv:2608.22903
    fully matrix-free factor-free three-grid Maxwell architecture
    这是最新研究信号，不作为本项目数值authority
```

仓库内部证据：

- Task030 已证明 matrix-free/low-memory H(curl) 基础设施和 factor-only local lifecycle 可行；
- Task039 证明旧 16-slab + 75D coarse 在 5 nm 4000 步仍停在 `0.155`，需要新的波传播层；
- Task021–Task025 证明 FE-response / DtN Schur 的物理定位有价值，但 local `A_FE^{-1}` 质量
  决定是否能扩展；
- Task040 证明固定 776 接口 family 不够。

---

## 5. 冻结项、允许修改与新覆盖

### 5.1 继续冻结的正式物理身份

```text
wavelength                         = 5.0 nm
grazing angle                      = 1 deg
azimuth                            = 0 deg
polarization                       = S
finite element                     = p6 Nedelec H(curl)
mesh                               = h4 formal identity
complex scalar                     = complex128
Floquet x/y                        = unchanged
Hybrid internal modes              = M480 positive + M480 negative
selected-mode packet               = inherited hash-bound packet
physical external DtN              = unchanged as exact operator
static condensation                = unchanged
global Hybrid operator             = unchanged
recovery/physics/checker            = unchanged
formal MPI / threads               = 8 / 1
```

### 5.2 继续禁止

```text
修改5 nm formal geometry/material/source
改变M480或重跑QEP
修改physical DtN sign/normalization/external keys
修改global Hybrid equation
重跑Hybrid direct authority
ordinary ILU/BLR/drop/restart菜单扫描
继续Route C到256/512/1000
把旧raw global row当current physical identity
把exact output packet变成production runtime dependency
未经Gate直接运行full target 0.7 nm PDE
修改ordinary defaults
写入或合并master、Task039或其他分支
```

### 5.3 本 Review 的狭窄覆盖

允许：

```text
一次factor-only current bare-F authority救援
完整15120-row interface Schur MatShell
完整trace Floquet/Fourier transform
PC-only full-spectrum DtN transmission
PC-only moving-PML/source-transfer sweep
adaptive local Maxwell-harmonic spectral coarse
bounded 3D patch factors
matrix-free factor-free H(curl) local multilevel
```

Task040 原 `coarse total rank<=512` 只继续约束旧 dense response-coarse 路线。新 distributed
full-interface spectral action不受该 rank 定义约束，但受更严格的 no-replication、no-dense-
factor 和 memory-growth Gate 约束。

---

# 6. 加速执行总决策树

```text
V6-0  factor-stage forensic + inherited audit

V6-1  conditional one factor-only bare-F authority rescue
       success -> exact authority available
       blocked -> do not stop Task040; continue V6-2

V6-2  full 15120-row exact interface Schur action and identity

V6-3  full-spectrum Floquet-DtN double-sweep oracle
       positive -> follow this route to productionization
       no signal -> V6-5 moving-PML sweep

V6-4  whenever exact authority becomes available:
       exact/Petrov/best/lift + Route A/B remaining rescue
       old family no holdout signal -> retire old family only

V6-5  one moving-PML/source-transfer double-sweep oracle
       positive -> follow this route to productionization
       no signal -> V6-6 adaptive spectral Schwarz

V6-6  adaptive impedance Schwarz + Maxwell-harmonic coarse pilot
       positive -> productionization
       no signal -> stop Task040 side-specific campaign and produce
                    mandatory Full3D architecture handoff for next task

V6-7  replace all full-cross-section group factors:
       bounded 3D patches first
       matrix-free three-grid local service if needed

V6-8  bottom bare F -> bottom A_side -> same-config top
       -> both-side setup -> one full Hybrid formal -> conditional h3

V6-9  0.7 nm / 2 TB capacity ledger and Full3D handoff

V6-final response_v7.md
```

Codex 不需要在 V6-0、factor forensic、full-interface algebra、Route A/B 小诊断或正常
positive signal 后等待审阅。只在本 Review 的真正 stop Gate、完整成功或全部新 families
无信号后停止。

---

## 7. V6-0：factor-stage forensic，不先盲目延长时间

### 7.1 比较对象

必须比较：

```text
Task039 V10 response producer
    source dbc5e9bfdf9ad0520881caa168c7a27316d50f10
    setup wall about 2971 s
    total wall about 4390 s

Task040 V5-2 fresh bare-F producer
    source fd7bea41d7d7b7869dd3ade4407129b00900ef7d
    authorized wall 21600 s
    no factor-ready
```

### 7.2 必须回答

```text
1. v5_bare_f_factor_setup_begin发生在总wall的第几秒
2. factor stage实际持续多久
3. 两次matrix rows / NNZ / Mat type / block size
4. ownership ranges与MPI layout
5. MUMPS ordering / ICNTL / CNTL / PETSc options
6. symbolic analysis与numeric factorization的阶段标记
7. OOC / BLR / memory relaxation是否不同
8. one-cell source generation与RHS packet耗时占比
9. MUMPS INFOG/RINFOG是否能提供进度
10. bare-F operator是否与旧 factor-bearing path属于同一矩阵语义
```

### 7.3 决策

```text
FORENSIC_CLEAR_REPAIR_OR_PREFACTOR_OVERHEAD
    存在明确配置回归，或factor前阶段消耗了主要wall
    -> 允许V6-1

FORENSIC_TRUE_FACTOR_STALL
    factor本身已持续接近整个窗口，且无配置回归
    -> 跳过V6-1，直接V6-2

FORENSIC_IDENTITY_MISMATCH
    不是同一bare-F/operator identity
    -> 不拿旧timing作等价基线；仍可V6-1一次，但必须记录差异
```

V6-0 只做 source/raw/marker 审计和必要的 tiny option readback，不运行 heavy。

---

## 8. V6-1：一次 factor-only current bare-`F` authority 救援

### 8.1 目的

这一步只为取得 current bare-`F` 的五个 exact solutions。它不是 production solver，
也不改变 Task040 最终 factor-free 要求。

### 8.2 复用 V5 已完成工作

优先复用 V5-2 已写出的：

```text
five current-layout RHS packets
canonical active layout
Gamma_L / Gamma_U layouts
source/operator/hash identity
```

只有所有 manifest、shard、canonical key 和 current reconstruction round-trip 通过时才复用。
不得重新运行 one-cell source factor，只为重新得到相同 RHS。

如果 current ownership 变化，必须从 canonical keys 重构；raw row remap 仍禁止。

### 8.3 固定运行

```text
side                       = bottom only
operator                   = current explicit bare F_b
factor                     = one MUMPS exact factor
factor_only_storage        = true
RHS                        = frozen five
physical DtN / Woodbury    = not used in solve
QEP                        = 0
three-group factors        = 0
full Hybrid                = not run
recovery/physics           = not run
```

### 8.4 资源与时间

```text
minimum MemAvailable before launch = 128 GiB
preferred peak                     = 60 GiB
warning peak                       = 70 GiB
absolute hard stop                 = 80 GiB
swap                               = 0
factor-stage wall cap              = 14400 s
total producer wall cap            = 18000 s
```

这是用户授权的一次诊断 heavy run。不得扫描 ordering、BLR 或 MUMPS 参数；V6-0 只允许修复
一个已证明的配置回归。

### 8.5 Gate

```text
FRESH_BARE_F_AUTHORITY_PASS
    five full explicit true residual <=1e-9
    repeat <=1e-12
    canonical packet round-trip pass
    factor lifecycle 1 -> 0
    producer exits before consumer
    swap=0 and peak<80 GiB

FRESH_BARE_F_AUTHORITY_FACTOR_STALL
    factor-stage cap耗尽且未factor-ready
    -> factor rescue永久结束，但Task040继续V6-2

FRESH_BARE_F_AUTHORITY_NUMERICAL_FAIL
    factor-ready但任一exact residual>1e-9
    -> 停止受影响的authority路线，保存operator/factor证据；V6-2仍可作为独立算法路线
```

除 implementation failure 外，不授权第二次 factor-only heavy rerun。

---

## 9. V6-2：完整 15120-row interface Schur action

### 9.1 目的

这一步不压缩接口，直接回答：

> 在三个 group interior solve 正确时，完整接口问题是否可以被稳定施加和求解？

它既是 exact-authority 的第二条来源，也是新 sweeping 路线的 operator foundation。

### 9.2 固定 algebra

使用：

```text
group0 = layers [0,1]
group1 = layers [2,3]
group2 = layers [4,5]
Gamma_L rows = 7560
Gamma_U rows = 7560
joint full interface = 15120
```

早期允许三个 group exact factors，只作为：

```text
FULL_INTERFACE_MECHANISM_ORACLE
```

禁止构造：

```text
full-side factor
dense 15120 x 15120 Schur
global numeric allgather
full interface replica per rank
```

`S_Gamma` 必须是 PETSc MatShell/MatPython distributed action。

### 9.3 identity Gate

至少验证：

```text
zero-map                                <=1e-13
repeat                                  <=1e-11
linearity                               <=1e-11
restriction/prolongation round-trip     <=1e-11
Schur action vs full-F elimination      <=1e-10 on 3 deterministic vectors
full trace owner coverage               = exact
Gamma_L/Gamma_U ordering                = canonical
factor lifecycle                        = 3 -> 0
```

### 9.4 exact solution资格

先对：

```text
external_dtn_coupling
fixed_random_repeat_0
```

运行 interface FGMRES。checkpoint：

```text
16 / 32 / 64 / 128
conditional 256
conditional authority continuation to 512
```

条件 `256`：

```text
r128 <=0.8
or 64->128下降>=0.10 decade
```

条件 `512` 只用于 exact authority：

```text
r256 <=1e-2
持续单调下降
peak<45 GiB
swap=0
wall仍在单次授权窗口内
```

若两源 full bare-`F` residual 均达到 `<=1e-9`，再运行其余三个 RHS 并写 exact packets。

这一步不得把 512 步写成 production capacity；它只是 exact interface oracle。

---

## 10. V6-3：完整频谱 Floquet-DtN double sweep

### 10.1 通俗解释

它不再猜“哪 776 个接口方向最重要”，而是把接口上的全部离散波分量都保留下来。
每个 Floquet harmonic 都有自己的传播常数和 TE/TM impedance；传播波、近截止波和
衰减波都参与 transmission。

### 10.2 完整 trace transform

当前 structured periodic hexa interface 上，transform 必须覆盖：

```text
periodic x/y cell indices
all local high-order tangential trace channels
orientation/sign channels
Floquet phase
```

实现优先级：

```text
1. block FFT over periodic cell indices for each local trace channel
2. 若布局暂不能FFT，使用bounded-batch streamed full spectral action
```

正式 scalable candidate 禁止：

```text
explicit dense Z/Y
all modes x all trace rows dense matrix
FE-sized allgather
```

transform Gate：

```text
forward/inverse round-trip        <=1e-10
mass/Parseval identity            <=1e-10
Floquet phase-once                pass
MPI2 and one final MPI4 identity  pass
all resolvable discrete harmonics included
propagating + evanescent included
```

### 10.3 transmission symbol

对每个 transverse harmonic：

```math
\beta_{mn}
=
\sqrt{(k_0 n_{bg})^2-\lVert k_t+G_{mn}\rVert^2},
```

使用现有 outgoing branch 规则，构造 TE/TM tangential impedance。它只用于 PC，不修改
physical DtN。

人工接口 background identity 必须从 current material/geometry 明确冻结。若接口穿过明显
heterogeneous material，记录 heterogeneity indicator；这会决定是否进入 V6-5 moving-PML，
但不得静默把材料平均化当作 exact physics。

### 10.4 sweep

固定为：

```text
forward  group0 -> group1 -> group2
backward group2 -> group1 -> group0
```

使用 full interface residual，不经过 776 projection。早期 group interior 仍使用 exact oracle。

### 10.5 信号 Gate

运行五个冻结 RHS：

```text
one-apply
FGMRES 8 / 16 / 32 / 64
conditional 128
```

分类：

```text
FULL_SPECTRUM_SWEEP_STRONG_SIGNAL
    all five r64 <=0.1
    and modal+/modal-/external <=1e-2

FULL_SPECTRUM_SWEEP_WEAK_POSITIVE
    all five finite and improve vs V3-2 by >=4x at r64
    or modal+/modal-/external r64 <=0.5
    and holdout sources do not worsen

FULL_SPECTRUM_SWEEP_NO_SIGNAL
    external and random0 r64 >0.8
    and 32->64下降<0.10 decade
    or any mandatory source becomes nonfinite/strongly unstable
```

`STRONG` 或 `WEAK_POSITIVE` 后沿该路线继续到 V6-7，不停下审阅。

`NO_SIGNAL` 后不扫描 impedance 常数、mode cutoff 或 sweep count，直接进入 V6-5。

---

## 11. V6-4：完成旧 Route A/B 的剩余救援

只要 V6-1 或 V6-2 产生合格 exact bare-`F` solutions，就执行本阶段；它与新 full-interface
主线并行，不阻塞 V6-3/V6-5。

### 11.1 exact/Petrov/best/lift

对五个 exact solutions 比较：

```text
exact trace t*
current Petrov trace tP
metric-best trace tB
exact/Petrov/best full 3D lift
```

exact-trace lift Gate：

```text
solution relative error <=1e-8
bare-F true residual    <=1e-9
```

### 11.2 Route A

只有 best 好、Petrov 差时运行：

```text
one fixed mass-dual
one fixed local-pre/interface/local-post composition
```

没有至少 `2x` 的五源一致改善就结束 Route A；不扫描更多 dual/post/sweep。

### 11.3 Route B

只有 current span 内容不足时运行：

```text
training = modal_traction_positive, external_dtn_coupling, fixed_random_repeat_0
holdout  = modal_traction_negative, fixed_random_repeat_1
R1 / R2 / R3 only
```

继续条件：

```text
training median r16 improve >=30%
holdout both improve >=20%
all finite
```

R3 无 training/holdout 一致信号时：

```text
OLD_776_RESPONSE_FAMILY_RETIRED
```

这只关闭旧 family，不关闭 full-interface / PML / adaptive Schwarz。

即使 Route B 通过，它也只作为 5 nm accelerator；若运行时依赖 fixed dense global basis，
不得升级为 0.7 nm 主架构。

---

## 12. V6-5：moving-PML / source-transfer double sweep fallback

### 12.1 触发条件

```text
FULL_SPECTRUM_SWEEP_NO_SIGNAL
or artificial-interface heterogeneity indicator is high
```

### 12.2 它解决什么问题

Fourier-DtN symbol假设接口附近有可定义的 background 波传播。若人工接口切过非可分离材料，
一个 homogeneous symbol可能太粗。moving-PML 在每个 local group 边界增加一个只属于 PC 的
吸收 collar，用局部 PDE 近似相邻无限域，不依赖全局 Fourier 可分离性。

### 12.3 固定配置

只允许一个配置，不扫描：

```text
collar thickness  = two existing z element layers where available, otherwise one
profile           = quadratic absorption
one-pass target   = exp(-6) amplitude attenuation
sweep             = one forward + one backward
exact outer F     = unchanged
```

早期 local extended-group solve 可用 exact factor作为 mechanism oracle。PML/collar 不进入
physical equation、recovery 或 official fields。

### 12.4 Gate

使用与 V6-3 相同的五源、checkpoint和 signal Gate。

```text
PML_SWEEP_STRONG_OR_WEAK_POSITIVE
    -> V6-7 productionization

PML_SWEEP_NO_SIGNAL
    -> V6-6 adaptive spectral Schwarz
```

不得继续扫描 PML thickness、attenuation、sweep count 或 ordering。

---

## 13. V6-6：adaptive impedance Schwarz + Maxwell-harmonic coarse

### 13.1 定位

这是面向 arbitrary 3D 的通用 fallback，不要求内部区域可分离。它把域分成重叠的三维局部
subdomains，local boundary 使用 impedance，coarse space 从每个 local Maxwell-harmonic
space 的困难 eigenmodes 自适应构造。

### 13.2 结构

```text
outer FGMRES on exact bare F
+ overlapping 3D brick local impedance solves
+ PC-only mild absorption shift
+ partition-of-unity weighting
+ adaptive local Maxwell-harmonic spectral coarse
```

初始 shift 复用当前 Task39/Task40 dimensionless `0.1` identity，不扫描。

local spectral selection必须复现 `arXiv:2501.18305` 的 dimensionless generalized eigenproblem
和论文中的一种固定 tolerance。若论文没有唯一推荐值，只允许使用其数值实验中的最保守
单值；不得在 formal h4 上扫 tolerance。

### 13.3 coarse 不是固定 global rank

允许：

```text
local selected mode count varies by subdomain
total mode count grows with subdomain count
owner-distributed basis
multilevel/iterative coarse application
```

禁止：

```text
all basis replicated on every rank
dense global coarse matrix factor
global allgather of FE-sized vectors
```

必须报告：

```text
modes per subdomain distribution
total coarse DoF
coarse bytes
coarse apply communication
principal local eigenvalue gap
```

### 13.4 economical fallback

若 local generalized eigenproblems 本身触发资源 Gate，只允许论文定义的 economical variant，
不允许自行增加第三种 coarse family。

### 13.5 h4 pilot Gate

先用 current bottom bare `F`、两个代表 RHS：

```text
external_dtn_coupling
fixed_random_repeat_0
```

checkpoint：

```text
16 / 32 / 64 / 128
```

正信号：

```text
both r64 <=0.5
or both improve >=4x vs Route C r64
and 32->64下降>=0.15 decade
```

有正信号后运行五源并自动进入 V6-7。

无信号：

```text
ADAPTIVE_SPECTRAL_SCHWARZ_NO_SIGNAL_AT_H4
```

此时 Task040 side-specific families 才允许停止，并必须提交下一 Full3D 任务的 architecture
handoff；这不是放弃 0.7 nm，而是从 Hybrid side 研究转入通用 Full3D 实现。

---

## 14. V6-7：删除 full-cross-section factors

任何 V6-3/V6-5/V6-6 正信号都必须继续到本阶段。机制 oracle 不能作为最终成功。

### 14.1 第一层：bounded 3D patch local service

```text
patch core                      = owned condensed cell/trace neighborhood
overlap                         = one shared-entity layer
max factorized local rows       <=1024
factor ownership               = one deterministic owner per exact class
factor class reuse             = enabled
partition of unity             = owner-consistent
```

允许 local exact factors，但单 factor 尺寸不随 global `N` 增长。

### 14.2 第二层：matrix-free three-grid local service

若 bounded patch local solver在 128 步内仍太弱，或 patch factor bytes常数过大，允许唯一
factor-free fallback：

```text
unshifted fine local operator       = matrix-free
intermediate correction             = fixed-work unshifted Krylov
auxiliary 2h/4h cycle               = complex shifted
smoother                            = bounded Jacobi/Chebyshev or bounded patch
coarse solve                        = iterative; no direct factor
transfer                            = Task030 validated H(curl) infrastructure
```

该实现应借鉴 fully matrix-free three-grid思想，但必须在本仓库独立验证；外部论文结果不能
替代本项目 Gate。

不得直接复用 Task030 已失败的 `792D p1 coarse` 作为唯一 coarse。新 local service必须与
V6 的 full-interface wave transmission 或 adaptive spectral coarse组合。

### 14.3 final bottom contract

```text
full-side exact factor              = 0
full-cross-section factor           = 0
global direct factor                = 0
global dense coarse factor          = 0
max factorized local rows           <=1024
full basis per-rank replication     = false
FE-sized numeric allgather          = false
explicit full-interface basis       = false
swap                                = 0
construction peak                  <=35 GiB
strong target                      <=30 GiB
post-setup retained                <=30 GiB
```

数值容量：

```text
preferred <=64 iterations
research  <=256 iterations
all five true residual <=1e-2
modal+/modal-/external <=1e-3
```

超过 256 步不能称为 production-capable side inverse。

---

## 15. V6-8：bottom、top 与完整 Hybrid

bottom bare `F` 通过后，连续执行：

```text
bottom full A_side with physical DtN unchanged
same-config top bare F and A_side
both-side setup-only
one full Hybrid formal
```

top 禁止单独调 transmission、PML、patch、spectral tolerance、restart 或 iteration budget。

完整 Hybrid 继续使用 Task39 authority Gate：

```text
reported/global/bottom/top/modal true residual <=5e-9
projection/traction identities pass
recovery pass
R/T/A/A_volume matched
selected E/H matched
canonical active/full vectors matched
normal flux and diffraction channels matched
bottom/top full-side exact factor = 0/0
global direct factor = 0
swap = 0
```

完整峰值与：

```text
93.377006531 GiB direct
80.025856018 GiB exact-side iterative
```

比较。`<80.025856018 GiB` 为新完整低点；但 5 nm 新低点本身不等于 0.7 nm 可行。

---

## 16. conditional h3 与 0.7 nm-oriented Gate

### 16.1 h3 scaling

完整 h4 candidate通过后，允许一次同参数 `p6/h3` bottom probe：

```text
no top
no full Hybrid
no QEP
same transmission family
same spectral selection rule
same patch cap
same Krylov restart
```

报告：

```text
active rows N
matrix-free/operator bytes
PC retained bytes
interface transform bytes
local factor/multilevel bytes
coarse bytes
Krylov bytes
construction transient
process-tree peak
iterations
```

### 16.2 内存指数

```math
p_{mem}
=
\frac{\log(B_{PC,h3}/B_{PC,h4})}
     {\log(N_{h3}/N_{h4})}.
```

目标：

```text
p_mem <=1.30
no new full replication
no new direct factor
patch cap unchanged
```

### 16.3 0.7 nm architecture classification

`0P7NM_ARCHITECTURE_CANDIDATE` 还必须满足：

```text
bare F exact action has a matrix-free implementation path
physical DtN uses FFT/streaming; explicit W=0
all transverse spectral data owner-distributed
no fixed global dense rank assumption
local/coarse storage O(N) or O(N log N)
restart and live vectors bounded
high-envelope predicted process-tree peak <=1.5 TiB
swap=0 and one-heavy-case policy
```

`1.5 TiB` 是 2 TB 工作站的 planning ceiling，不是允许程序占满物理内存；其余内存保留给
OS、filesystem cache、MPI/runtime和安全余量。

### 16.4 预测必须使用真实 mesh，而不是只乘 125

`response_v7.md` 必须同时报告：

```text
naive uniform h proportional to lambda envelope
accuracy-qualified p/h/hp mesh estimate
local refinement estimate
measured h4/h3 bytes per DoF
measured iteration growth
external channel inventory growth
```

任何 0.7 nm 结论必须区分：

```text
measured
derived
predicted
not_run
```

Task040 不运行 full target 0.7 nm PDE，但必须给出下一任务可直接执行的 reduced pilot和
目标规模 preflight合同。

---

## 17. 最小测试政策

### 17.1 默认测试

| 变更 | 最小测试 |
|---|---|
| docs/JSON | parse、Markdown/table/math、`git diff --check` |
| full-interface algebra helper | focused serial |
| owner/scatter/FFT | serial + MPI2 |
| Floquet/orientation/round-trip | serial + MPI2；formal前一次MPI4 |
| PETSc MatShell/lifecycle | one component test |
| local spectral eigenproblem | tiny deterministic algebra test |
| formal run前 | touched Ruff、compileall touched modules、focused suite |
| closeout | one consolidated focused suite + repo/doc contracts |

默认不运行：

```text
full repository pytest
每commit重复MPI4
无关Task039 heavy tests
无关benchmark全量写入
```

### 17.2 implementation bug

Codex可自行修复并继续：

```text
path/schema/hash/marker
PETSc ownership/scatter/workspace
FFT channel order/orientation/Floquet phase-once
MatShell transpose/conjugation
factor/object lifecycle
watchdog/telemetry/checker wiring
```

要求：保留失败 root、一个 focused regression、最小修复、新 SHA 重跑同阶段。

---

## 18. heavy-run 预算与停止纪律

本 Review 预授权：

```text
one conditional factor-only authority rescue
one full-interface Schur/spectral-sweep formal sequence
one moving-PML fallback sequence if needed
one adaptive spectral Schwarz h4 pilot if needed
one selected full Hybrid formal after all side gates
one h3 scaling probe after full h4 success
```

implementation failure 的同阶段最小修复重跑不算新算法 attempt。

一次只运行一个 heavy process tree；formal 前必须：

```text
clean tracked source
exact source SHA
complex128 ABI
MPI8 / threads1
MemAvailable and disk pass
swap=0
watchdog active
```

---

## 19. 真正 stop Gate 与自动继续权限

### 19.1 必须停止等待审阅

```text
factor rescue出现bare-F numerical inconsistency
full-interface Schur action identity无法建立
full-spectrum sweep和moving-PML均no-signal
adaptive spectral Schwarz h4也no-signal
selected positive route无法删除full-cross-section factors
matrix-free/local service违反memory或rows Gate
same-config top出现无法解释的数值失败
full Hybrid residual/physics/resource Gate失败
h3显示明显超线性增长或迭代失控
```

### 19.2 不需要停止

```text
factor rescue再次time blocked但full-interface route仍可继续
旧Route A/B无信号
full-spectrum route有weak/strong signal
moving-PML route有weak/strong signal
adaptive spectral Schwarz有正信号
普通focused test修复
outcomes文档阶段完成
```

### 19.3 有正信号就做到底

任一新 family 达到 positive signal 后，Codex自动完成：

```text
five-source qualification
remove full-cross-section factors
bottom bare F
bottom A_side
top
both-side
full Hybrid
h3 scaling
0.7 nm capacity ledger
```

除真正 Gate 外，不得在“完成一个小实验”“还没跑全仓测试”或“刚写完一个 outcome”时停下。

---

## 20. Evidence 与 response_v7

至少新增或更新：

```text
outcomes/v6_factor_forensics.md
outcomes/v6_factor_only_authority.md
outcomes/full_interface_schur_identity.md
outcomes/full_spectrum_floquet_sweep.md
outcomes/old_776_rescue.md
outcomes/moving_pml_sweep.md
outcomes/adaptive_spectral_schwarz.md
outcomes/factor_free_local_service.md
outcomes/bottom_full_side.md
outcomes/top_full_side.md
outcomes/both_side_setup.md
outcomes/full_hybrid_result.md
outcomes/h_refinement_scaling.md
outcomes/0p7nm_side_pc_capacity.md
outcomes/full3d_0p7nm_architecture_handoff.md
outcomes/route_signal_ledger.md
outcomes/memory_residual_time_pareto.md
outcomes/test_summary.md
outcomes/summary.md
response_v7.md
```

`route_signal_ledger.md` 必须分别登记：

```text
factor rescue
old A/B rescue
full-spectrum sweep
moving-PML sweep
adaptive spectral Schwarz
factor-free local service
```

每条记录：

```text
entry condition
exact configuration
actual checkpoints
training/holdout if applicable
memory/wall
signal classification
switch/continue reason
0.7 nm scaling implication
```

`full3d_0p7nm_architecture_handoff.md` 必须说明哪些 Task040 primitive 可迁移到 arbitrary 3D
Full3D，哪些只属于 Hybrid side acceleration。该 handoff 不得把 Hybrid pass冒充 arbitrary 3D pass。

`response_v7.md` 至少包括：

```text
branch / exact HEAD / upstream / worktree
all commits after Review V6
focused tests and deliberately not-run tests
factor forensic and conditional rescue result
full-interface action identity
all route signals and switches
selected route or all-new-routes-negative conclusion
bottom/top/full Hybrid if reached
h3 if reached
0.7 nm / 2 TB measured-derived-predicted ledger
Full3D handoff
selective merge groups
remaining blockers
```

---

## 21. 提交节奏

建议按真正阶段提交：

```text
docs(task040): audit v6 factor and scaling baseline
feat(task040): add full-interface Schur action
feat(task040): add full-spectrum Floquet sweep
bench(task040): qualify full-interface wave transmission
feat(task040): add moving-PML or adaptive Schwarz fallback
feat(task040): replace cross-section factors with scalable local service
bench(task040): qualify factor-free side and full Hybrid
docs(task040): close review v6 and 0.7nm handoff
```

可以根据实际路线省略未发生的 fallback 提交。不得把所有数值核心、heavy evidence和文档混成
一个不可审阅提交，也不得每个小 bug 单独停下来等待审阅。

---

## 22. Merge 与最终边界

```text
merge approval = NO
```

本 Review 只授权当前 Task040 分支继续研究。以下默认 research-only：

```text
factor-only authority producer
three full-cross-section group oracle
old 776 response family
moving-PML mechanism oracle
failed route artifacts
```

只有通过 factor-free side、完整 Hybrid、h3 scaling和下一轮 ChatGPT review 的通用组件，才可
进入 selective merge 候选。

最终裁决：

```text
Task040 closed                                      = no
V5 Route C family continued                        = no
remaining exact-authority rescue                   = yes, once
full-interface Schur route                         = primary
full-spectrum Floquet-DtN sweep                    = primary wave route
moving-PML sweep                                   = first fallback
adaptive Maxwell-harmonic Schwarz                  = general fallback
bounded/matrix-free local service                  = mandatory before success
full target 0.7nm PDE in Task040                    = no
0.7nm architecture and 2TB capacity accounting     = mandatory
arbitrary-3D Full3D handoff                        = mandatory
master merge                                       = not approved
```
