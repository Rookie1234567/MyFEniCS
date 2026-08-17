# Task039 Review Report V4：p6/h4 生命周期资格、三方法资源对比与 QEP/M 降峰研究

## 0. 审阅决定

```text
review                                  = Task039 Review Report V4
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = e24217b04b51cbbd5e84a9d2166cfebea76ac813
extension_status                        = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
physical_case                           = 5 nm / 1° grazing / phi=0° / S
spatial_discretization                  = p6/h4
M                                       = 480 fixed for all formal Hybrid runs
M_above_480                             = forbidden
formal_MPI                              = 8 only
Full3D_direct_h4_lifecycle              = authorized_once
Hybrid_direct_h4_M480_lifecycle         = authorized_once after readiness
Hybrid_iterative_h4_M480_exact_side     = authorized once after Hybrid direct own pass
Hybrid_iterative_ordinary_ILU0          = forbidden
strict_per_channel_repair               = deferred
production_PC_sweep                     = forbidden
neural_or_learned_factor                = frozen
full_0p7nm_PDE                          = forbidden
QEP_low_M_and_memory_study              = component/offline only in this Review
concurrent_heavy_jobs                   = forbidden
```

本 Review 的首要目标是：在同一 5 nm、1°、p6/h4、M480、MPI8 条件下，完整获得

```text
Full3D direct
Hybrid direct
Hybrid iterative exact-side
```

三条可比较结果，并回答：

1. Full3D direct 能否通过求解后立即释放 MUMPS/global solver 对象，完成此前被内存终止的恢复与后处理；
2. Hybrid direct 能否移植已验证的 QEP、interface、coupling 和 solve/recovery 生命周期管理，显著降低全过程峰值；
3. exact-side Hybrid iterative 在 h4 下能否继续正确求解，并相对 Hybrid direct 和 Full3D direct 保持明确内存优势；
4. QEP/selected modes 是否正在成为 Hybrid 的主导成本，以及未来波长继续降低时，如何避免 `M↑` 使 Hybrid 优势消失。

本 Review 不重新打开普通 ILU(0) PC。V3 已证明：exact monolithic operator、block-LDU、modal Schur 与 recovery 接线正确，而普通 side ILU 在 5 nm 下不够强。V4 的正式 iterative 候选只使用已通过固定案例资格的 exact-side 显式 opt-in 路径。

历史 10°、h10/h7.5/h6/h5、普通 ILU0 negative、h5 exact-side positive 和 h4 controlled-stop 记录必须全部原样保留。

---

# 1. 冻结物理与数值身份

所有正式 h4 运行共享：

```text
wavelength                       = 5.0 nm
n_grating                        = 0.99396854453 + 0.00435380777i
n_substrate                      = 0.99396854453 + 0.00435380777i
n_air                            = 1 + 0i
period_x / period_y              = 50 / 25 nm
grating width x / y / height     = 17 / 25 / 120 nm
z_min / z_max                    = -10 / 130 nm
Hybrid interfaces                = 10 / 110 nm
grazing angle                    = 1°
internal theta                   = 89°
azimuth                          = 0°
polarization                     = S
Nedelec degree                   = p6
mesh target                      = h4 nm
mesh family                      = boundary-fitted hexahedron
vertical boundary                = DtN port
external mode policy             = auto_propagating
MPI                              = 8
```

external key set必须由每次正式输入的正式枚举器生成，并在同一物理模型的三种方法之间精确一致。既有 h4 partial Full3D run 报告约 600 auxiliary keys；V4 不允许把该数字硬编码为事实，必须由 resolved input 和正式 run manifest重新绑定。

Hybrid正式运行固定：

```text
requested_modes_per_direction    = 480
positive/negative modal unknowns = 480 + 480 = 960
propagation model                = full3d_uniform_cg
traction model                   = full3d_one_cell_exact_schur
```

禁止通过增加 M、改变接口位置、改变 mode filter、截断 external keys 或改变材料来获得正结果。

---

# 2. 为什么 h4 与生命周期管理值得继续

既有 h4 Full3D direct 已经完成线性求解：

```text
true residual        ≈ 3.57e-10
R                    ≈ 0.73318348
T                    ≈ 0.00022244
A_balance            ≈ 0.26659408
```

但在 `solver_objects_retained_for_postprocess` 后，process-tree RSS 达到约 209.07 GiB，略高于 224000000000 bytes（约 208.616 GiB）的绝对终止线，因此未形成 A_volume、closure、selected E/H、canonical 和最终完整 authority。

这说明当前最优先的 Full3D 修复不是改变方程或求解器，而是：

```text
solve完成
→ 保存最小solution/recovery authority
→ 完成true-residual与必要线性审计
→ 立即destroy MUMPS KSP/PC/factor与不再需要的global matrices
→ 确认RSS下降
→ 再进入field recovery与postprocess
```

对 Hybrid，V3 已测得：旧 Hybrid direct 在 selected biorthogonal bases 完成时已经占最终峰值约 96%，而 exact-side 生命周期路径把全过程峰值从约 85.02 GiB 降至约 49.82 GiB。因此 h4 比较必须同时采用生命周期管理，否则比较的是“旧对象重叠方式”，而不是三种方法的合理工程实现。

---

# 3. V4 执行顺序

```text
V4-0  inherited audit、h4 identity与历史证据冻结
V4-1  通用solve/recovery生命周期合同与focused tests
V4-2  Full3D h4 lifecycle preflight和一次正式completion run
V4-3  Full3D h4完整authority、2D Q8趋势与资源收口
V4-4  生成一次共享的h4/M480 selected-mode packet
V4-5  Hybrid direct h4/M480 lifecycle preflight和一次正式run
V4-6  Hybrid direct vs Full3D same-grid integrated comparison
V4-7  Hybrid iterative exact-side h4/M480一次正式run
V4-8  三方法数值、内存与时间比较
V4-9  QEP/M低内存与低M component-only研究
V4-10 response_v5.md与停止审阅
```

所有重型作业严格串行。每阶段完成后及时 commit 并 push 到同一 Task39 分支。

---

# 4. V4-0：继承审计

创建：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/review_v4_inherited_audit.md
```

至少记录：

- local/remote HEAD、upstream、ahead/behind、clean status；
- 2D Q8 reference；
- 1° Full3D h5/h4.5完整记录和 h4 controlled-stop记录；
- 1° Hybrid direct h5 M480记录；
- exact-side Hybrid iterative h5 qualification记录；
- 当前h4输入、external inventory预期与动态枚举合同；
- selected memory、MemAvailable、swap和disk；
- M480固定、M>480禁止；
- ordinary defaults和master不变。

第一项 V4 提交必须为 docs-only。

---

# 5. V4-1：通用生命周期合同

## 5.1 原则

生命周期优化不得改变：

```text
assembled equation
matrix coefficients
RHS
solver tolerances
MUMPS ordering与数值精度
Hybrid M与mode keys
physical outputs
```

只允许改变：

```text
对象何时被checkpoint
对象何时destroy/release
solve与postprocess是否在不同进程中执行
相同数据是否从hash-bound packet重载
```

## 5.2 两级实现

优先使用低时间开销的 **Level A：同进程显式释放**：

1. 保存解向量与最小恢复包；
2. 完成必须依赖矩阵/factor的true residual与repeat审计；
3. collective destroy KSP/PC/factor、无用Mat/Vec与临时cache；
4. 调用已接受的 PETSc/SLEPc garbage cleanup、Python GC 与 allocator trim（若平台支持）；
5. 记录before/after RSS/PSS/USS；
6. 进入恢复和后处理。

只有 Level A 无法把 RSS 降到安全恢复线时，才启用 **Level B：两进程拆分**：

```text
process A: assembly + factor + solve + hash-bound solution/recovery packet → exit
process B: load packet + recovery + postprocess
```

Level B 不得重新组装或重新求解同一个全局线性系统。进程退出的目的只是让操作系统确定释放 PETSc/SLEPc/MUMPS/allocator高水位。

## 5.3 时间边界

生命周期优化新增的：

```text
checkpoint write
packet read
collective destroy
garbage cleanup
```

必须独立计时。目标：

```text
lifecycle overhead <= 10% of original method total wall
strong target      <= 5%
```

若两进程拆分需要重新计算 QEP、重新factor或重新求解，则不属于本 Review 授权路径。

---

# 6. V4-2/V4-3：Full3D direct p6/h4 完整资格

## 6.1 输入与单次运行

新建或修订一个正式 `.dat`，方法仍为 Full3D direct/MUMPS/MPI8，只新增明确的 lifecycle policy。不得使用 OOC、BLR、降低精度或替代求解器。

正式资源合同：

```text
warning RSS                   = 170 GiB
critical checkpoint           = 195 GiB
absolute terminate            = 224000000000 bytes
any swap                      = immediate termination
poll interval                 <= 0.25 s
no concurrent heavy process   = required
MemAvailable before launch    >= 210 GiB
```

先执行一次 setup/recovery contract preflight，不运行第二次完整factor。完成后只允许一次正式 h4 Full3D lifecycle run。

## 6.2 必须保存的解与恢复包

在 factor destroy 前保存：

```text
active condensed solution
RHS和true-residual所需最小向量/hash
static-condensation recovery coefficients或可重建它们的最小packet
mesh/space/Floquet identity
external DtN auxiliary solution与key identity
source/input/resolved/physical SHA
```

不得把完整MUMPS factor或全局matrix复制进packet。

## 6.3 factor销毁顺序

```text
linear solve success
→ true residual
→ external q / port amplitudes必要线性审计
→ solution packet fsync + hash verify
→ destroy KSP/PC/MUMPS factor
→ destroy不再用于recovery的global matrix/preallocation/cache
→ collective cleanup
→ measured RSS checkpoint
→ recovery/postprocess
```

Level A后，进入恢复前的目标是：

```text
RSS <= 190 GiB preferred
RSS <= 200 GiB engineering
RSS < absolute hard required
```

若 Level A 后仍不安全，停止在checkpoint，不丢失解，改用 Level B postprocess进程；不得重新factor。

## 6.4 Full3D h4 own Gate

```text
official result                    = true
true relative residual             <= 1e-9
R/T/A_balance/A_volume             finite
energy closure                     <= 1e-5
external keys                      exact/unique
selected E/H                       complete and finite
canonical active/full              complete
lifecycle packet hashes            pass
factor destroyed before recovery   proven
swap                               = 0
```

成功分类：

```text
TASK039_V4_FULL3D_H4_LIFECYCLE_COMPLETE_PASS
```

另将 h4 完整结果与 2D Q8 reference 比较；其通过与否独立于 Full3D own Gate。

---

# 7. V4-4：共享 h4/M480 selected-mode packet

## 7.1 目的

Hybrid direct 与 exact-side iterative 使用相同物理、网格、M和mode selection。为了避免重复QEP并降低峰值，V4只生成一次 hash-bound selected-mode packet，两个方法均只读消费。

## 7.2 packet 内容

至少包含：

```text
positive/negative beta与branch identity
selected right/left biorthogonal mode data
必要的cross-section mode coefficients
interface traces
canonical mapping与Gram authority
重建和P/T assembly所需最小数据
mode keys/order/sign/group identity
QEP residuals与selection diagnostics
source/input/physical/mesh/M hashes
```

不包含：

```text
EPS/ST/KSP对象
QEP factor/workspace
raw未选candidate vectors
重复的positive/negative/full/trace表示
```

优先使用不压缩或轻量压缩、可 memory-map 的 rank-sharded packet，避免高CPU压缩。packet写入和读取时间必须报告。

## 7.3 QEP进程边界

推荐：

```text
mode-prep process
→ QEP + select M480 + packet write/hash
→ process exits
```

随后 direct 与 iterative 的 solve进程分别读取同一packet。这样全过程峰值按：

```text
max(mode-prep process peak, solver process peak)
```

统计，而不是把两个阶段的对象在同一进程中叠加。

若当前实现不能在本 Review 内安全完成packet拆分，允许使用V3已验证的同进程显式生命周期路径，但必须说明未实现进程隔离。

---

# 8. V4-5/V4-6：Hybrid direct p6/h4 M480

## 8.1 算法身份

```text
method                         = Hybrid direct
M                              = 480 per direction
external modes                 = dynamic exact set
solver                         = global augmented MUMPS direct
MPI                            = 8
ordinary mathematical blocks   = unchanged
```

## 8.2 生命周期顺序

必须移植V3已经实测有效的边界：

1. bottom interface blocks完成ownership transfer后，清理bottom lifting/helper临时量；
2. 再构造top interface blocks；
3. P/T/coupling完成后释放QEP operator、raw candidate、未再使用的full mode对象；
4. augmented matrix完成后只保留matrix、RHS、solution/recovery packet需要的数据；
5. MUMPS solve完成、true residual和必要审计完成后，保存Hybrid solution；
6. destroy global MUMPS factor与不再需要的augmented matrix；
7. 再进行field reconstruction、R/T/A、selected fields和canonical export；
8. 若同进程RSS不能安全下降，使用solve/postprocess两进程拆分，但不得重新QEP、factor或solve。

## 8.3 Hybrid direct own Gate

```text
true residual                       <= 1e-9
interface projection                <= 1e-8
exact traction bottom/top           <= 1e-8
R/T/A/A_volume finite
closure                             <= 1e-5
external keys exact
selected E/H and canonical complete
swap                                = 0
```

## 8.4 Same-grid Full3D integrated comparison

strict逐通道phase/amplitude修复仍 deferred，不作为V4阻断项。Primary integrated Gate：

```text
max |delta R,T,A_balance,A_volume|  <= 1e-5
selected E overall relative L2      <= 5e-3
selected H overall relative L2      <= 1e-2
normal-flux aggregate               <= 1e-4
all-channel power-weighted error    <= 1e-4
external key set                    exact
```

逐通道结果必须完整输出并标记 diagnostic-only，不得隐藏。

若 own Gate通过但 integrated comparison失败，仍允许V4-7以solver-only身份运行 iterative；不得把其称为Hybrid physical qualification。

---

# 9. V4-7：Hybrid iterative exact-side p6/h4 M480

## 9.1 冻结候选

```text
outer operator                  = exact monolithic matrix-free Hybrid
outer solver                    = right FGMRES
restart                         = 90
max_it                          = 4000
initial guess                   = zero
five residual threshold         = 5e-9
block preconditioner            = action-consistent block-LDU
bottom/top side inverse         = exact sparse side factor
external correction             = dynamic DtN Woodbury
nested iterative side KSP       = false
global direct factor            = 0
MPI                             = 8
M                               = 480
```

只允许这一正式候选，不运行ordinary ILU0、ILU1、Candidate E或新的PC sweep。

## 9.2 生命周期

- 复用V4-4 packet，不重复QEP；
- bottom/top side factor顺序构造，避免临时高水位叠加；
- modal Schur构造完成后释放不再需要的P/T和显式临时量；
- outer solution形成并通过residual后，保存solution snapshot；
- recovery前释放side factors、W/K/LU和deferred modal Schur；
- 再执行field recovery与postprocess；
- 若packet进程拆分已实现，报告cold-start和reuse两种时间。

## 9.3 数值 Gate

```text
KSP reason                         > 0
iterations                         <= 4000
reported/global/bottom/top/modal   <= 5e-9
projection                         <= 1e-8
exact traction                     <= 1e-8
recovery own physics               = pass
swap                               = 0
```

与Hybrid direct同方程比较：

```text
R/T/A/A_volume abs delta           <= 1e-6
selected E/H relative L2           <= 5e-3
canonical active/full relative L2  <= 1e-5
external keys                      exact
```

---

# 10. V4-8：三方法公平比较

## 10.1 内存

对三种方法分别报告：

```text
全过程 process-tree RSS/PSS/USS peak
mode-prep peak（Hybrid）
solver-process peak
factor-ready peak
post-factor-destroy RSS
recovery peak
final cleanup RSS
swap
```

Hybrid使用进程拆分时，冷启动全过程峰值定义为各顺序进程峰值的最大值，不得相加。

计算：

```math
S_{H_d/F} = 1-\frac{RSS_{Hybrid\ direct}}{RSS_{Full3D\ direct}},
```

```math
S_{H_i/F} = 1-\frac{RSS_{Hybrid\ iterative}}{RSS_{Full3D\ direct}},
```

```math
S_{H_i/H_d} = 1-\frac{RSS_{Hybrid\ iterative}}{RSS_{Hybrid\ direct}}.
```

资源分类：

```text
positive saving       > 0%
meaningful saving     >= 20%
strong saving         >= 30%
major saving          >= 40%
```

## 10.2 时间

分别报告：

```text
mesh/space
QEP/mode packet preparation
packet write/read
a ssembly/coupling
factor/setup
linear solve
recovery/postprocess
lifecycle cleanup
total cold-start wall
total reuse wall
```

公平比较必须给出两种Hybrid时间：

```text
cold-start = shared mode preparation + method-specific solve/recovery
reuse      = method-specific solve/recovery with existing identical packet
```

不得只报告outer iteration或只报告reuse时间来声称更快。

## 10.3 最终表

| method | numerical/physics status | cold wall | reuse wall | RSS | vs Full3D saving | vs Hybrid direct saving |
|---|---|---:|---:|---:|---:|---:|

---

# 11. V4-9：M增大与QEP内存问题

## 11.1 物理判断

Hybrid 的 `M` 不只是几百个标量未知量。每个模式还携带：

```text
cross-section eigenvector
left/right biorthogonal representation
interface E trace
interface traction/H trace
projection与traction列
propagation data
field-reconstruction data
```

主要存储近似为：

```math
Memory_{modes}
\sim
O(N_{cross}M)+O(N_{interface}M)+O(M^2),
```

QEP eigensolver还需要candidate Krylov basis、shift-invert workspace和未选模式。波长降低时，横截面内传播和弱衰减模式数量通常上升；若仍按完整模式计数扩展，Hybrid优势确实可能逐渐被QEP和mode storage侵蚀。

本 Review 不以降低M为主线，因为h4三方法必须先使用相同、已验证的M480。但授权以下 component/offline 研究，为下一任务选择方向。

## 11.2 Q-A：模式复制审计

首先测清：

```text
每个MPI rank是否完整复制所有selected/raw modes
positive/negative/left/right/full/trace表示各有几份
哪些对象在P/T形成后仍存活
```

输出每类对象的：

```text
shape / dtype / local bytes / global process-tree bytes / ownership / lifetime
```

若selected mode arrays在8个rank完整复制，优先研究 owner-only 或列分布存储；这可能比降低M更稳妥，因为不损失物理信息。

## 11.3 Q-B：±beta配对，只解一个QEP分支

对当前 reciprocal、z-invariant、复介质离散算子做代数审计：

```text
positive beta modes能否通过精确离散变换生成negative beta partner
left/right与traction符号如何映射
lossy complex material下pair residual是否仍满足正式Gate
```

若对M120/240/480均满足：

```text
paired QEP residual             <= existing QEP tolerance
trace/traction reconstruction   <= 1e-10
Hybrid observables              unchanged within 1e-8
```

则下一任务可只求一个QEP分支并生成另一分支，理论上可接近减半QEP求解时间和部分workspace。V4只做审计，不替换正式h4 authority。

## 11.4 Q-C：batched/streaming QEP

研究将一次大candidate solve改为若干谱窗口或批次：

```text
solve a spectral batch
→ immediately select/checkpoint accepted modes
→ destroy EPS/Krylov/raw rejected vectors
→ next batch
```

优先复用同一shift-invert factor或共享operator，避免每批重复大factor。目标：

```text
QEP peak RSS reduction >= 30%
QEP wall increase       <= 20%
selected M480 identity  exact or numerically equivalent
```

只运行小规模或setup-only benchmark，不在V4重新做完整h4三方法PDE。

## 11.5 Q-D：低M不是固定截断，而是物理自适应模式选择

不得武断地把M480改成M240。更合理的低M路径是：

1. 必保留所有传播模式；
2. 必保留满足 `|Im(beta)| L <= eta` 的弱衰减模式；
3. 对其余模式按interface E/H coupling、traction contribution和a posteriori interface residual排序；
4. 从较低子空间开始，按残差驱动增 enrich；
5. 直到 R/T/A、selected fields和interface residual通过。

V4允许用已建立的M480 authority做离线/小系统子空间研究：

```text
M_eff candidates = 240 / 320 / 400
```

但必须从同一M480 basis中构造nested subset或物理筛选，不得重新做三次完整QEP/PDE。比较：

```text
reduced Hybrid residual
R/T/A/A_volume
selected E/H
normal flux
power-weighted channels
```

只有某个 `M_eff` 对h4 authority满足：

```text
R/T/A/A_volume delta          <= 1e-5
selected E/H                  <= 5e-3 / 1e-2
interface residual            <= 1e-8
power-weighted channel error  <= 1e-4
```

才可作为下一任务的候选。该结果是固定case候选，不得直接外推到0.7 nm或复杂结构。

## 11.6 Q-E：长期替代方向

若M必须增长到数千，单纯保存完整本征模最终不可扩展。长期可研究：

```text
matrix-free/rational Krylov propagation operator
contour-integral spectral window extraction
interface-to-interface transfer action而非完整eigenbasis
structured RCWA middle-region operator（仅适合其假设成立的中间区）
```

这些属于后续独立任务，V4不得实现。

## 11.7 V4建议优先级

```text
第一优先：mode ownership/replication + process split
第二优先：±beta one-branch QEP symmetry audit
第三优先：batched/streaming QEP
第四优先：physics-adaptive low-M offline study
长期：matrix-free transfer/propagation operator
```

原因是：前三级可以降低内存而不先牺牲模式完整性；固定低M虽然诱人，但最容易损失短波长下关键传播和导数信息。

---

# 12. Bug修复权限

Codex可自主修复真正的实现问题：

```text
solution/recovery packet缺字段或hash接线
factor destroy后仍有悬挂引用
MPI collective destroy次序
process split launcher/path/ownership
mode packet shape/order/sign
telemetry时钟对齐
incorrect double assembly/recompute
```

要求：

1. 保留原失败证据；
2. 添加最小复现/focused test；
3. 做窄修复；
4. 不改变方程、M、solver tolerance或物理输入；
5. 只重跑受影响正式候选一次；
6. 及时commit并push。

以下不是bug，不得静默调参：

```text
h4内存仍超过hard stop
Hybrid direct不比Full3D省内存
exact-side iterative时间较长
M480与Full3D integrated physics不一致
QEP peak随h/M增长
```

---

# 13. 测试与证据

正式heavy run前至少完成：

```text
solution packet round-trip exactness
factor-destroy-before-recovery unit test
postprocess process consumes packet without solver objects
Full3D old/new h5 equivalence fixture
Hybrid mode packet old/new equivalence fixture
MPI2/MPI4 lifecycle smoke
no duplicate QEP in direct/iterative consumer
telemetry 18-stage ordering and process-tree alignment
```

静态检查：

```text
ruff check
ruff format --check
python -m compileall
git diff --check
```

V4完成后运行focused tests和相关MPI fixtures。完整repository pytest是否执行由最终成本审阅决定；未运行时必须写 `not_run`，不能写pass。

tracked compact records只保存身份、Gate、资源和raw SHA。重型packet、solution、field、timeline保存在ignored results目录。

---

# 14. 最终分类

分别分类，不得强行合并：

```text
TASK039_V4_FULL3D_H4_LIFECYCLE_COMPLETE_PASS
TASK039_V4_HYBRID_DIRECT_H4_OWN_PASS
TASK039_V4_HYBRID_H4_INTEGRATED_PHYSICS_PASS_OR_FAIL
TASK039_V4_HYBRID_ITERATIVE_H4_EXACT_SIDE_PASS_OR_FAIL
TASK039_V4_QEP_MEMORY_DIRECTION_ESTABLISHED_OR_NOT_ESTABLISHED
```

三方法全部形成完整结果且iterative数值通过时，才允许写：

```text
TASK039_V4_H4_THREE_METHOD_RESOURCE_COMPARISON_COMPLETE
```

不得把fixed-case exact-side结果称为普适production PC，也不得把低M component study称为0.7 nm可行性证明。

---

# 15. 最终交付

创建或更新：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v4_full3d_h4_lifecycle.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v4_hybrid_direct_h4_lifecycle.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v4_hybrid_iterative_h4_exact_side.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v4_three_method_comparison.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v4_qep_m_memory_study.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/response_v5.md
```

完成后停止等待审阅，不得自行merge master、运行MPI1、增加M、进入0.7 nm PDE或开启新分支。
