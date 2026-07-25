# Task035b Review V2：最终通道精度、内存下限与高阶 Setup 重构续研

## 1. 审阅身份与正式结论

```text
review_status = TASK035B_ACCURACY_MEMORY_SETUP_CONTINUATION_AUTHORIZED
execution_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
reviewed_numerical_head = aa87534158bc84be7362d14e55ad56e7286a5e2a
reviewed_delivery = response_v2 current remote state
geometry_scope = Task034 fixed rectangular block grating only
current_best_in_budget_candidate = fixed_p5trace_p6interior_h13_directional_z
current_best_candidate_dof = 89740
current_best_candidate_active_rows = 20120
current_best_candidate_significant_power = 10_of_12
current_best_candidate_significant_amplitude = 10_of_12
same_error_target = not_met
hybrid_eligible_candidate_count = 0
current_peak_memory_is_theoretical_minimum = false
current_setup_path_is_final = false
accuracy_continuation = authorized
setup_rearchitecture = authorized
memory_floor_research = authorized
factor_free_condensed_iterative = authorized_as_opt_in_research
hybrid_after_full_candidate = conditionally_automatic
additional_review_between_candidate_and_hybrid = not_required
ordinary_default_changed = false
master_merge = not_authorized
irregular_geometry = out_of_scope_by_user
```

本轮不接受“已经达到 Task035b 最终目标”的表述。最强预算内候选已把原始
`6/12 power + 7/12 amplitude` 推进到 `10/12 + 10/12`，并将剩余误差集中到
`T(-4,0)`、`R(-4,0)` 和 `R(-5,0)` 三个通道，但仍未达到强制的
`12/12 + 12/12`。因此：

```text
channel recovery = strong positive signal, incomplete
same-error compression <= 90k = not proven
Hybrid continuation = not unlocked yet
0.7 nm / 2 TiB feasibility = unknown
```

同时，本 Review 不接受把 `5.8–6.4 GiB` 解释为“八九万 DoF 的最低内存”。
该峰值是八个 MPI Python/PETSc/DOLFINx 进程、局部高阶张量、静态凝聚、全局
稀疏矩阵、MUMPS analysis/LU、恢复缓存和后处理对象共同形成的 process-tree
峰值。LU 是其中一项，但不是全部，也没有证据表明现有对象生命周期、MPI rank
数和组装方式已经达到最低。

Task035b 因此继续在同一分支完成三个相互关联的目标：

```text
A. 最后三个显著衍射通道的定向恢复；
B. 将高阶 condensed setup 从“可用的临时优化”推进到可复用的正式快速路径；
C. 建立真实内存下限，并尝试 direct 再优化与 factor-free iterative。
```

A 获得完整通过候选后，不等待新的中间 Review，直接完成 Full3D–Hybrid closure、
M/DtN funnel 与资源模型 v3。B、C 可与 A 并行推进，但不得污染正式数值证据。

---

## 2. Response V2 的准确验收

### 2.1 已完成并接受的结果

以下结果接受为正式研究证据：

1. `significant_channel_reference_v1` 已冻结，12/12 通道均有明确参考状态；
2. 16 个失败通道独立 Hermitian adjoint 全部验证通过；
3. port/DtN 的已测试符号、相位、投影和 manufactured Rayleigh authority 通过；
4. z 方向分辨率是当前最强实测恢复方向；
5. x-only、q31、scaled evanescent-buffer1 均为有效受控负结果；
6. assembly-time exact static condensation、Floquet slave 物理消元、tensor dedup、
   exact preallocation、factor release 和 heap trim 均为工程正结果；
7. 全仓 `845 passed, 31 skipped`，Task035b scoped Ruff、compileall、JSON、链接和
   diff Gate 通过。

### 2.2 当前最强预算内候选

```text
candidate = fixed p5 trace + p6 cell interior, directional-z h13
axis plan = (6, 2, 12)
Full3D-equivalent DoF = 89,740
active matrix rows = 20,120
matrix NNZ = 11,013,212
factor NNZ = 36,273,200
factor fill = 3.294
peak = 6.41059 GiB
build = 59.855 s
MUMPS setup/factorization = 13.342 s
backsolve = 0.0334 s
true residual = 5.81e-12
significant power = 10/12
significant complex amplitude = 10/12
```

剩余失败：

```text
power:
    T(-4,0)
    R(-4,0)

complex amplitude:
    r(-4,0)
    r(-5,0)
```

失败集合并集只有：

```text
T(-4,0), R(-4,0), R(-5,0)
```

这说明研究问题已经从“整体 hp 如何压缩”缩小为“如何在 90k 预算内恢复三个
弱而相位敏感的通道”。但因为 h13 只剩 260 DoF headroom，继续增加完整 z 层、
完整 p6 trace 或大范围局部加阶都不可能满足预算。

### 2.3 为什么还不能进入 Hybrid

原合同要求：

```text
DoF <= 90,000
+
12/12 significant powers
+
12/12 significant complex amplitudes
+
R00/R/T/Aclosure/fields/residual 全部通过
```

当前候选仍未满足通道 Gate。继续接入 Hybrid 会把 Full3D 空间误差、Hybrid
接口误差、M 截断和 DtN 截断混在一起，使根因不可辨识。因此当前停止 Hybrid
是正确的，不应通过放宽通道 Gate 或只看总 R/T 来绕过。

---

## 3. 为什么八九万 DoF 仍需要 5–6 GiB

### 3.1 这里的 DoF 与实际求解行数不是同一个量

`74,890` 或 `89,740` 是 Full3D-equivalent FE DoF，用于与未凝聚高阶空间比较。
静态凝聚和 Floquet slave 消元之后，真正送入全局求解器的是：

```text
h15: 16,880 rows
h13: 20,120 rows
```

因此不能用：

```text
5.8 GiB / 74,890
```

简单解释成“每个有限元自由度需要约 80 KiB”。峰值内存属于完整 MPI 进程树，
而不是只属于 global trace matrix。

### 3.2 当前峰值至少包含哪些部分

以 h15 authority 为例：

```text
process start MPI tree RSS ≈ 3.02 GiB
fixed-trace solve-stage peak ≈ 5.94 GiB
formal process-tree peak ≈ 5.803 GiB
matrix estimate ≈ 0.21 GiB
MUMPS factor-storage planning proxy ≈ 0.624 GiB
```

剩余部分包括但不限于：

- 8 个 Python/MPI/PETSc/DOLFINx 进程及动态库；
- mesh、geometry、tags、function space、MPC/Floquet maps；
- Basix/FFCx quadrature、basis、orientation 和 Piola 数据；
- 每类高阶单元局部 `A_tt/A_ti/A_ii`、局部 LU 与 Schur 张量；
- PETSc matrix、preallocation、communication buffers；
- MUMPS symbolic/numeric workspace 与 factors；
- full-field recovery、port projections、field probes 和输出缓存；
- glibc/PETSc/MUMPS allocator 保留但尚未归还的 heap；
- 每个 rank 的重复或半重复数据。

因此 LU 不可能单独解释全部 5.8 GiB。现有规划代理只把 factor payload估为约
0.624 GiB；即使将该代理全部删除，也不能把峰值机械地写成 5.18 GiB 的正式
iterative 预测，因为不同阶段峰值并不同时发生，allocator 与其他工作区也会改变。

### 3.3 当前 5.8 GiB 不是最低值

现有证据只能说明：

```text
5.803 GiB = 当前 MPI8 direct condensed 实现的实测峰值
```

不能说明：

```text
5.803 GiB = 数学下限
5.803 GiB = 当前软件栈下限
5.803 GiB = factor-free 下限
```

至少存在以下未测空间：

1. MPI1/2/4/8 下 replicated runtime 与 communication 的变化；
2. PSS/private/shared 页面，而不是只看 process-tree RSS sum；
3. 进一步流式释放 local tensors、Schur scratch 与 recovery cache；
4. 不保留完整恢复场、只流式计算正式 observables/probes；
5. MUMPS ordering、symbolic factorization 和 sparsity pattern 重用；
6. 不形成 LU 的 assembled iterative；
7. 不形成 global matrix 的 matrix-free condensed operator。

因此本 Review 要求先建立“对象与阶段可归因的内存下限”，再讨论最低内存。

### 3.4 本轮采用的内存研究目标

以下是研究目标，不是预先宣称可达到的结果：

```text
current direct h15 authority:
    5.803 GiB

near-term optimized direct target:
    <= 4.5 GiB preferred
    <= 5.0 GiB minimum useful signal

factor-free assembled condensed target:
    <= 4.0–4.5 GiB research target

matrix-free/streamed condensed target:
    <= 3.0–3.5 GiB stretch target
```

任何目标都必须由 process-tree RSS、cgroup、PSS、object ledger 和 no-swap 实测支持。
若实测证明 MPI/Python runtime 本身构成更高下限，应如实更新目标，不得伪造压缩。

---

## 4. 为什么当前不是 MUMPS 最耗时

### 4.1 旧结论与当前结论并不矛盾

Task029 对未凝聚的约 198k-row 系统证明：

```text
primary peak = KSPSetUp 中 MUMPS analysis + numeric LU
KSPSolve/back-substitution = negligible
```

这个结论对当时的 full assembled direct system 是正确的。

Task035b 现在已经通过 static condensation 和 Floquet elimination，把全局系统降到
16k–20k rows。瓶颈随算法改变发生了迁移：

```text
旧路径：大稀疏 LU 主导
当前路径：高阶局部张量/Schur 构造与全局装配主导
```

### 4.2 当前实际时间分解

h15 fixed-trace authority：

```text
mesh build                         ≈ 2.24 s
function-space setup               ≈ 16.30 s
Floquet total                      ≈ 1.12 s
condensed matrix build             ≈ 61.61 s
MUMPS setup/analysis/factorization  ≈ 6.56 s
MUMPS backsolve                    ≈ 0.036 s
postprocess                        ≈ 2.32 s
```

h13：

```text
condensed build   ≈ 59.86 s
MUMPS setup       ≈ 13.34 s
backsolve         ≈ 0.033 s
```

因此用户的直觉“解回代应该很快”是正确的，但“当前 MUMPS 一定是最长阶段”已经不
成立。MUMPS 的 analysis/factorization 仍比 backsolve 昂贵，但当前最大的单项是
高阶 condensed matrix build。

### 4.3 之前的稳妥临时方案是什么

当前稳定路径采用了：

```text
tensor dedup
+
批量复用
+
exact PETSc preallocation
```

它把 h15 fixed-trace build 从：

```text
231.15 s -> 83.71 s -> 61.61 s
```

同时将：

```text
PETSc mallocs: 13,856 -> 0
unused NNZ: 3,498,879 -> 288,768
peak: 6.105 -> 5.803 GiB
```

这是可信的工程优化，但仍是“单次进程内去重和预分配”，没有从根本上解决：

- 每次运行重新建立高阶局部张量；
- Python/per-cell 路径与多次小块插入；
- identical material/geometry class 的局部 `A_ii` 分解与 Schur 重算；
- 同一 topology 的 sparsity、periodic map 和 symbolic factorization 重建；
- cold/warm cache 未分层；
- 多参数/多 RHS 工作流缺少正式 offline/online 拆分。

本 Review 因此授权彻底重构 setup 路径，而不是继续只调一个 PETSc 参数。

---

# 续研任务 A：完成 12/12 通道恢复

## A0. 保持 reference 与 Gate 不变

必须继续绑定：

```text
significant_channel_reference_v1
12 significant powers
12 significant complex amplitudes
strict R00/R/T/Aclosure
selected fields/interfaces
full explicit true residual
```

不得为了得到候选而删除 `R/T(-4,0)` 或 `R(-5,0)`，也不得修改已冻结的
same-code acceptance band。

## A1. 主起点改为 h14，而不是继续全局 h13

h13 只有 260 DoF headroom，无法进行有意义的 trace 恢复。h14：

```text
fixed p5-trace/p6-interior h14
DoF = 82,315
headroom to 90k = 7,685
power/amplitude = 7/12 + 9/12
```

同网格 full p6 trace：

```text
DoF = 92,850
power/amplitude = 9/12 + 12/12
```

说明 trace enrichment 有实测正作用，但完整 trace 超预算 2,850 DoF。下一步应在
h14 上实现合法、物理减行、periodic-closed 的 selective p6 trace，而不是在 h13
继续增加完整层。

## A2. 补齐 physical selective p6 trace 能力

必须完成以下能力，才能选择任何 trace subset：

1. physical-cell covariant-Piola missing-trace basis；
2. physical tangential Riesz 与 cross-entity Gram；
3. edge/face orientation 与 Basix transform；
4. x/y periodic transitive orbit 和 Floquet phase pullback；
5. missing-trace enriched residual；
6. complement Schur action/inverse；
7. 每个失败通道的 residual-weighted enriched DWR；
8. exact-sequence-compatible active space；
9. active global numbering，inactive rows 不进入矩阵；
10. matrix/NNZ/factor/peak 的真实增量。

禁止：

```text
完整 p6 trace matrix + 将未选模式置零
```

## A3. channel-aware trace 子空间选择

对剩余重点通道：

```text
T(-4,0)
R(-4,0)
R(-5,0)
```

建立：

- channel × trace-orbit sensitivity matrix；
- power 与 Re/Im amplitude 独立目标；
- reference-band normalization；
- SVD、rank-revealing QR 和 DWR-weighted mode ranking；
- periodic orbit 作为最小选择单元；
- 每个 orbit 的 DoF、rows、NNZ 和边际误差收益。

同时保留全部12通道审计，防止修复弱通道时破坏已经通过的通道。

## A4. 固定 DoF 的 z-node/phase-aware topology 优化

h13 的均匀方向性 z 增量是正信号，而预设 R5 slab bisection 为负结果。这并不证明
所有非均匀 z 节点分布都失败。

允许在**不增加 cell count 和 DoF**的前提下，移动少量内部 z 平面：

- 材料界面 `z=0` 与 `z=120` 固定；
- top/bottom domain boundaries 固定；
- 周期与材料标签不变；
- Jacobian、aspect ratio 和 phase-resolution Gate 通过；
- 使用失败通道 adjoint/response 指导，而不是盲扫；
- 每次只修改1–2个平面；
- 必须运行 unchanged-topology control。

该路线的目标是在 h14 或 h13 DoF不变时恢复 `(-4,0)` 和 `(-5,0)` 的相位/功率。

## A5. 候选竞争顺序

同时最多：

```text
Lane A1: h14 + selective p6 trace
Lane A2: fixed-DoF z-node optimization
Control: unchanged h14 or h13
```

只有单lane出现正信号后，才运行最小组合：

```text
h14 selective trace
+
最多一次 fixed-DoF z-node adjustment
```

不进行大规模模式数、节点和网格组合盲扫。

## A6. 精度成功 Gate

候选必须同时满足：

```text
Full3D-equivalent DoF <= 90,000
full explicit true residual <= 1e-9
R00/R/T/Aclosure pass
normalized vector pass
12/12 significant powers pass
12/12 significant complex amplitudes pass
selected volume/interface fields pass
geometry/tag/Floquet/orientation pass
exact sequence pass
MPI8, no swap, clean SHA
```

达到后自动继续 Hybrid，不等待新的中间审阅。

---

# 续研任务 B：彻底解决高阶 Setup 过慢

## B0. 先统一时间术语

所有正式记录必须分开：

```text
cold import/JIT
mesh build
function-space/Basix setup
periodic/Floquet map
local tensor generation
local Aii factorization
local Schur formation
sparsity/preallocation
bulk global insertion/finalization
DtN assembly
KSP symbolic analysis
KSP numeric factorization
backsolve
recovery
postprocess
```

不得再用含混的 `setup` 同时表示“有限元准备”和“MUMPS factorization”。

## B1. 冷启动与热启动双基线

对 h15 seed 和 h13 best candidate 分别测量：

1. clean-cache cold run；
2. same-process second assembly；
3. new-process persistent-cache warm run；
4. same-topology/new RHS；
5. same-topology/new material/frequency的正确失效行为。

缓存不得跨不兼容 geometry、material、wavelength、degree、orientation 或 source SHA
静默复用。

## B2. 正式 offline/online cache

建立 gitignored、SHA-bound 的持久缓存，至少覆盖：

- Basix entity transforms、quadrature 和 basis tabulation；
- canonical affine geometry classes；
- material/geometry-class local tensors；
- local `A_ii` LU/solve representation；
- local Schur class；
- periodic trace map 与 active numbering；
- exact sparsity graph 和 row-wise preallocation；
- DtN mode identities、trace basis和projection structure；
- MUMPS symbolic ordering metadata，在合法时重用。

每个缓存必须记录：

```text
schema
physical-config hash
mesh hash
element/basis hash
source SHA
build environment
numerical checksum
validation result
```

## B3. 消除 Python per-cell 组装瓶颈

优先比较：

1. tensor-class batched dense linear algebra；
2. 同类单元只构造一次 Schur stencil；
3. 直接生成分布式 CSR/COO，而不是大量 `MatSetValues` 小块插入；
4. rank-local bulk insertion；
5. 预先建立 local-to-global expansion map；
6. C++/Numba/Cython 或 PETSc/DOLFINx compiled kernel，只在profile证明Python循环主导后采用；
7. 不保留所有单元 dense scratch，采用 class cache + streaming。

必须先profile，不得仅凭代码行数猜测瓶颈。

## B4. 重用 sparsity 与 symbolic factorization

对于同一 topology 和 active space：

- 重用 PETSc matrix nonzero structure；
- `MatZeroEntries` 后只更新数值；
- 审计 MUMPS ordering/symbolic analysis reuse；
- 多 RHS、adjoint和反演参数点只做必要的 numeric更新；
- 区分 topology变化、material变化、frequency变化和仅 RHS变化。

当前 condensed trace graph 与Task029的full matrix不同，可以做一次小规模 ordering/symbolic
reuse bake-off；不得重复已经证明在旧图上无效的大范围MUMPS参数扫描。

## B5. Setup 性能目标

以下作为工程目标：

```text
h15 current condensed build = 61.61 s
h13 current condensed build = 59.86 s

minimum useful result:
    cold build reduction >= 2x

preferred:
    cold build <= 25–30 s
    persistent-cache warm build <= 10 s

stretch:
    same-topology/new-RHS incremental setup <= 2 s
```

必须保持物理值、true residual、matrix NNZ和active rows一致；不得通过跳过必要
计算或复用错误缓存达到目标。

---

# 续研任务 C：建立内存下限并继续节约

## C0. 精确内存归因

在现有process-tree sampler之外增加：

- 每rank `/proc/<pid>/smaps_rollup`；
- RSS、PSS、USS/private-clean/private-dirty/shared；
- cgroup current/peak；
- PETSc matrix/object bytes；
- MUMPS symbolic/numeric阶段；
- local tensor/cache bytes；
- Python heap与native heap分开；
- allocator `malloc_info` 或等价摘要；
- object create/destroy lifecycle；
- post-destroy + `malloc_trim` 后的实际下降。

目标是形成：

```text
runtime floor
mesh/space
local tensors
matrix
MUMPS workspace/factor
recovery/postprocess
allocator retention
```

的可加但不误称同时峰值的ledger。

## C1. MPI rank数重新资格化

当前16k–20k-row condensed系统可能不适合MPI8作为最低内存配置。对冻结h15
candidate运行：

```text
MPI1
MPI2
MPI4
MPI8
```

每个点保持：

-相同物理、矩阵和真残差；
-线程环境显式记录；
-CPU affinity记录；
-process-tree RSS、PSS和cgroup；
-build、MUMPS setup、solve与总时间；
-factor NNZ和ordering。

正式MPI8仍作为并行身份Gate，但若MPI2/4在单工作站上明显更低内存、更快，可新增
显式opt-in workstation profile。不得直接把Task029旧full-matrix比例搬到当前condensed图。

另外，历史sampler在solve阶段曾观察到大量线程。虽然activation已设置
`OMP/OPENBLAS/MKL/NUMEXPR=1`，仍必须审计实际线程名称、来源与CPU使用，排除MPI、
BLAS、MUMPS或运行时隐式线程造成的内存与调度开销。

## C2. Direct路径继续优化

在不改变数值空间的前提下：

- 继续保持solver/factor在postprocess前释放；
- recovery按cell/patch流式进行，只保留正式probes和port quantities；
- field output为显式opt-in，不作为普通候选峰值的必需共存对象；
-审计MUMPS ordering对当前condensed图的factor fill；
-同图重用symbolic analysis与ordering；
-释放local Schur scratch、preallocation临时数组和unused caches；
-避免rank间复制全局channel/trace数据。

## C3. 专用factor-free condensed iterative profile

当前 capability stop 的原因是：

```text
PETSc build lacks HYPRE
public profile is direct-only
no dedicated iterative provenance
no residual-history contract
no factor-free inventory
```

本轮授权实现一个**独立opt-in profile**，不得用raw PETSc覆盖冒充正式结果。至少支持：

```text
GMRES or FGMRES
explicit reduced trace matrix initially
factor_nnz = 0
residual history
terminal explicit reduced residual
full recovered-field residual
failure semantics distinct from DirectSolveFailure
```

预条件路线按成本依次尝试：

1. Jacobi/block-Jacobi baseline；
2. ASM/RAS + local ILU/LU；
3. edge/face/DtN block fieldsplit；
4. p5-trace或低阶trace辅助空间；
5. PETSc GAMG/其他当前环境可用组件的受控试验；
6. 只有前述路线不足时，评估新增HYPRE/AMS资格化环境，不静默替换现有环境。

首个正式screen：

```text
MPI = 8 and best workstation rank count
restart = 30
max iterations = 200
unpreconditioned residual reduction >= 3 decades
terminal explicit reduced residual <= 1e-3
full recovered true residual reported
factor matrix absent
no swap
```

若只达到诊断性收敛，保留负结果并继续设计预条件器；不得把低精度KSP结果写成
official R/T/channel结果。

## C4. matrix-free condensed trace研究

assembled matrix在当前规模只占峰值一部分，但未来0.7 nm必须避免global fine matrix。
在assembled iterative稳定后，研究：

```text
local Schur action on demand
+
periodic trace expansion
+
DtN matrix-free action
```

要求：

-不存global matrix；
- local class tensors可流式/缓存；
- MatShell action与assembled matrix action一致；
- serial/MPI identity；
- preconditioner拥有独立低存储表示；
- memory与setup实测，而非只做复杂度说明。

---

# 续研任务 D：通过后继续 Hybrid 与资源模型

当任一 Full3D candidate通过A6全部Gate时，Codex无需等待新的Review，直接：

1. Full3D–Hybrid same-degree closure；
2. M80/M120/M160，必要时M240；
3. external DtN propagating/evanescent/order funnel；
4. 12个显著通道power/amplitude闭合；
5. selected fields/interfaces与full residual；
6. local FE rows、total rows、QEP DoF、M、内存和时间；
7. 更新0.7 nm / 2 TiB resource model v3。

资源模型必须分别报告：

```text
measured
derived
predicted
unknown
```

不得把component sum写成simultaneous peak，也不得仅凭本Task的local FE优化宣称
0.7 nm production feasible。

---

## 5. 连续执行规则

Task035b继续采用连续自主研究，不逐小阶段等待Review。

```text
accuracy lane有正信号 -> 继续到完整候选
setup优化有正信号 -> 继续到cold/warm正式记录
memory lane有正信号 -> 继续到direct/iterative对照
完整候选通过 -> 自动进入Hybrid
```

单个cache方案、ordering、preconditioner、trace subset或z-node候选失败，不停止整个
Task；保存受控负结果后切换。

只有以下情况停止请求用户：

-需要密码、凭据或系统级安装授权；
-ABI/source/reference/evidence身份异常；
-内存、swap、磁盘或进程安全风险；
-所有合理accuracy/setup/memory路线耗尽；
-准备修改ordinary default；
-准备merge master；
-Hybrid后确认必须新开独立modal-core或生产迭代任务。

---

## 6. 下一份Response要求

完成上述连续批次后新增：

```text
docs/task035b_high_order_local_hp_resource_envelope/response_v3.md
```

至少报告：

1. 是否得到 `<=90k`、12/12+12/12候选；
2. selective trace与z-node候选的完整通道表；
3. exact-sequence、periodic orbit和active-row证据；
4. cold/warm setup分解与加速倍率；
5. setup中Python、tensor、Schur、PETSc insertion、DtN和MUMPS各自占比；
6. MPI1/2/4/8内存/时间/PSS对照；
7. direct优化后的最低实测峰值；
8. factor-free iterative是否运行、迭代历史、残差、峰值和失败语义；
9. matrix-free capability状态；
10. 若候选通过，Hybrid、M/DtN与resource model v3；
11. 所有controlled negative与not-run原因；
12. full repository regression、Ruff、compileall、JSON、diff-check和工作树状态。

未经最终Review与用户明确授权，不得合并master。
