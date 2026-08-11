# Task037-extra Review Report V9：H2B 固定单位步长失败后的尺度不变诊断与 PDE 快速恢复

## 0. 审阅身份与最终决定

```text
review                                  = Task037-extra Review Report V9
working_branch                          = codex/20260806-task37-iterative-extra-development
reviewed_handoff                        = docs/task37_extra_development/response_v8.md
reviewed_H2B_source                     = b6b83b338156ab039324aaa8b2705992dd3815ae
H1R3_action_layer                       = ACCEPTED_AND_FROZEN_PASS
H2A_R0_class_discovery                  = ACCEPTED_PASS
H2A_R1_staged_JIT_cache                 = ACCEPTED_PASS
H2A_R2_constrained_factor_store         = ACCEPTED_PASS
H2B_fixed_unit_symmetric_sweep          = ACCEPTED_NUMERIC_FAIL
H2B_factor_store                        = RETAINED_AS_QUALIFIED_RESEARCH_ASSET
H2B_all_preconditioner_capacity         = NOT_YET_REJECTED
new_authorized_stage                    = H2B-S scale-invariant direction oracle
conditional_stage                       = H2B-K normalized additive two-level FGMRES
bounded_fallback                        = H2B-P row-complete restricted patch
H2D_fullspace_matrix_free_DtN           = CONDITIONAL_AFTER_COERCIVE_GLOBAL_PASS
H4_time_harmonic_PDE                    = CONDITIONAL_AFTER_H2B-K_OR_H2B-P_AND_H2D_PASS
full_PDE_memory_hard_target             = process-tree RSS < 2,000,000,000 B
swap                                    = strictly_zero
outer_space                             = uncondensed_fullspace_only
static_condensed_fallback               = forbidden
bounded_codex_autonomy                  = AUTHORIZED
create_new_branch                       = forbidden
pull_request                            = forbidden
merge_to_master                         = permanently_not_planned
ordinary_default_change                 = forbidden
```

本审阅接受 H2B 的原始结论，但将其范围严格限定为：

> **当前 8-color forward + reverse、固定单位步长的 stationary smoother 不稳定，不能继续作为
> 单独的 Richardson/Schwarz 平滑步骤。**

H2B 不能被改写为 PASS。其五类 source 的单位步长 contraction 均达到约
`1e24--1e27`，属于真实的数值失败。

但是，当前证据尚不足以关闭全部 cell-factor 预条件器路线。原因是 H2B 的 Gate 使用：

```math
\rho_{unit}
=
\frac{\lVert r-B_0z\rVert_2}{\lVert r\rVert_2},
\qquad
z=M^{-1}r,
```

并强制步长为 `1`。这适合审查一个可独立迭代的 stationary smoother，却不是判断右预条件
FGMRES 中“方向是否有用”的尺度不变指标。若 `z` 方向正确但整体尺度过大，FGMRES 可以在
外层最小残差过程中选择很小的组合系数；当前逐颜色 residual feedback 则可能把尺度错误在
16 次更新中连续放大。

因此，V9 不允许原样重跑 H2B，也不允许盲目扫描 damping；只授权一个决定性的尺度不变
诊断。该诊断将回答：

```text
现有 202 MB constrained factor store 产生的是“方向有用但尺度错误”的修正，
还是“方向本身错误”的修正？
```

若方向有用，则立即进入低内存 FGMRES；若方向无用，则关闭单 element operator，转向真正的
restricted-global patch operator。两条路线均继续使用未静态凝聚的 full-space。

---

# 1. 最新结果审阅

## 1.1 已通过且应保留的基础设施

| 阶段 | 正式结果 |
|---|---|
| full-space matrix-free volume action | p6/h10、MPI1/MPI2、h5 scaling 全部 PASS |
| H2A-R0 class discovery | `24` topological classes；h-refinement class growth sublinear |
| H2A-R1 JIT staging | cold compile 与 fresh cache-hit 分离成功 |
| H2A-R2 constrained factors | `24` classes、`16` unique numeric factors、`8` exact dedup |
| factorization residual | 最大 `8.540193602788576e-16` |
| representative solve residual | 最大 `4.861914019080286e-11` |
| factor + metadata | `201933812 B` |
| R2 process-tree peak | `717139968 B` |
| global/slab/Schur matrices | 均未形成 |

这些结果说明以下对象是可信且可以继续复用的：

```text
full-space action
Floquet/MPC reduction
class inventory
JIT cache staging
constrained local block construction
exact numeric dedup
factor serialization/loading
factor residual与determinism
```

不得因为 H2B 组合失败而删除这些正结果。

## 1.2 H2B 资源与结构通过

H2B attempt #2 的 online 阶段：

| 项目 | 实测 |
|---|---:|
| rows / constraints | `173802 / 9210` |
| classes / factors | `24 / 16` |
| factor payload | `201933812 B` |
| factor + smoother work | `217953872 B` |
| colors | `8` |
| actions / apply | `16` |
| online process-tree peak | `685731840 B` |
| swap | `0` |
| PoU closure | `0.0` |
| same-color independent rows | disjoint |

所以 H2B 不是内存失败、JIT 失败、factor 失败或 action callback 失败。

## 1.3 H2B 数值失败

| source | unit-step `rho` |
|---|---:|
| gradient-dominated | `4.542906419782354e24` |
| curl-dominated | `2.6341788315209565e24` |
| mixed | `4.361198568985487e24` |
| checkerboard/high-frequency | `7.734935557489985e27` |
| physical-RHS-like | `1.304855993199958e24` |

独立 action 回算与保存 residual 的相对闭合约为 `1.8e-15`。因此巨大数值不是 output
状态错误，而是实际 correction 经 `B0` 作用后的结果。

## 1.4 当前最可能的两类根因

### 根因 A：单位步长与 multiplicative feedback 造成尺度级联

单 factor 的离线 solve gain 约为 `459--876`。当前 smoother 在 8 个颜色上正向一次、反向
一次，每次都用已经更新的 residual 再做局部 inverse。若局部 inverse 的尺度比全局 inverse
偏大，误差会在 16 次 residual update 中级联放大；`1e24` 量级与这种乘法级联相容。

### 根因 B：局部 operator 不是经典 Schwarz 的 restricted global operator

当前 factor 对应单个 element contribution：

```math
\widetilde B_c
=
C_c^H B_c C_c.
```

而经典 overlapping Schwarz 的局部算子应接近：

```math
B_{P}
=
R_P B_0 R_P^T,
```

即在 patch row set 上包含所有相邻 element 对这些 rows 的全局装配贡献。单 element block
可能显著低估全局 row energy，从而产生过大的 inverse correction。

V9 先用尺度不变诊断区分 A 与 B，不直接猜测。

---

# 2. 关键方法学修正：stationary contraction 不等同于右预条件 capacity

对给定 correction `z`，定义：

```math
q=B_0z.
```

允许一个复标量 `omega` 后，最小化：

```math
\min_{\omega\in\mathbb C}
\lVert r-\omega q\rVert_2.
```

其最优值为：

```math
\omega_*
=
\frac{q^Hr}{q^Hq}.
```

尺度不变 contraction 定义为：

```math
\rho_*
=
\frac{\lVert r-\omega_*q\rVert_2}{\lVert r\rVert_2}.
```

并记录方向相关度：

```math
\eta
=
\frac{|q^Hr|}{\lVert q\rVert_2\lVert r\rVert_2}.
```

解释：

- `rho_unit >> 1`、但 `rho_* << 1`：方向有用，主要是尺度错误；
- `rho_* ≈ 1`：方向与 residual 几乎正交，当前局部 operator 没有预条件能力；
- `rho_* > 1` 不应在正确最小二乘计算中出现，若出现即为实现/数值异常；
- `omega_*` 很小不自动判失败，但必须记录其跨 source 和 refinement 的变化。

右预条件 FGMRES 不要求 `I-AM^{-1}` 本身是收缩映射；它要求预条件方向能够形成有效的
最小残差搜索空间。因此 V9 用 `rho_*` 与 global Krylov 结果，而不再单独用固定单位步长
`rho_unit` 决定全部 factor lane 的生死。

---

# 3. H2B-S0：三种组合的尺度不变方向 oracle

## 3.1 固定输入

继续使用冻结的五类 source：

```text
gradient-dominated
curl-dominated
mixed
checkerboard/high-frequency
physical-RHS-like
```

继续使用冻结的：

```text
p6/h10
MPI1
B0 = K_curl + k0^2 M_abs_epsilon
R2 factor store
exact full-space matrix-free action
```

不得重新 factor，不得改变 class、material、p/h、Floquet 或 factor tolerance。

## 3.2 只允许三种组合

### S-A：additive PoU

所有 cell 都使用同一初始 residual：

```math
z_A
=
\sum_c R_c^T W_c\widetilde B_c^{-1}R_cr.
```

全部 cell correction 合并后只做一次 exact `B0` action。不得逐 color 更新 residual。

### S-F：forward-only colored multiplicative

只做 8 colors 的正向 sweep，不做 reverse。

### S-S：当前 symmetric forward/reverse

保留当前 16-action 版本，仅作为对照，不再以 unit-step result 作为进入 PDE 的候选。

禁止新增第四种组合，禁止扫描颜色顺序。

## 3.3 每个 source 必须输出

```text
||r||
||z||
||q||, q=B0*z
rho_unit
omega_star real/imag/abs
rho_star
eta
q/r norm amplification
z/r norm amplification
exact action closure
factor/action/source SHA
wall and process-tree peak
```

还必须保存 additive、forward、symmetric correction/action 的 deterministic SHA。

## 3.4 S0 Gate

一个组合获得进入 Krylov 的资格，必须同时满足：

```text
all values finite and deterministic
exact action closure <= 1e-11 relative to ||q||
0 <= rho_star <= 1 + 1e-12
checkerboard/high-frequency rho_star <= 0.70
mixed rho_star <= 0.85
gradient/curl/physical rho_star <= 0.95
online process-tree peak < 1,000,000,000 B
swap = 0
```

若多个组合通过，选择：

1. action count 最少；
2. worst-source `rho_star` 最小；
3. wall 最小。

因此默认优先级为 additive，再 forward；symmetric 只有在前两者不通过而其自身通过时才保留。

## 3.5 结论分支

### S0-PASS

至少一个组合通过，则进入 H2B-K。

### S0-FAIL

三种组合的 `rho_star` 均未通过，则正式关闭“single-element contribution factor”作为全局
PC 的路线，不允许继续调 damping、PoU、颜色或 sweep；自动进入 H2B-P。

---

# 4. H2B-K：归一化 block PC 与 coercive global FGMRES

仅在 H2B-S0 PASS 后执行。

## 4.1 归一化 PC

对选中的组合计算 `z` 与 `q=B0 z`，然后返回：

```math
\widehat z
=
\omega_* z.
```

由于 `omega_*` 依赖当前 residual，PC 是可变/非线性的；外层必须使用 FGMRES，禁止使用
假设固定线性 PC 的 CG 或普通 stationary Richardson。

必须验证：

```math
\frac{\lVert r-B_0\widehat z\rVert}{\lVert r\rVert}
=
\rho_*
```

达到数值闭合。

## 4.2 时间优化

- additive 只需要一次最终 exact action；
- forward/symmetric 已在 residual update 中得到最终 `r_final`，可由：

```math
q=r-r_{final}
```

获得，不应再增加一遍 action；
- 禁止当前 symmetric 路径每个 PC 固定 16 actions 后再额外 action。

## 4.3 75D full-space wave coarse

在 local normalized PC 通过后，加入固定 75D full-space wave basis：

```math
E=Z^HB_0Z.
```

只保留：

```text
Z
small E
factor(E)
```

`B0*Z` 必须逐列生成后释放，不得长期保存完整 `BZ`。

完整两层 PC 顺序冻结为：

```text
normalized local correction
-> true residual update
-> 75D coarse correction
-> optional one additive post-correction only if memory/time Gate passes
```

第一版禁止 symmetric 16-action post-smoother。

## 4.4 Coercive global solve

```text
operator       = exact matrix-free B0
outer KSP      = right FGMRES
restart        = 20
true tolerance = 1e-8
max iterations = 500
timeout        = 6 h
```

Gate：

```text
20-step true residual <= 0.30
100-step true residual <= 1e-3
full true residual <= 1e-8 within 500 iterations
reported/true residual agree
completed process-tree peak < 1,650,000,000 B
swap = 0
no global matrix/Schur/slab factor
```

若 100 步未到 `1e-3`，但 residual 单调且最后 50 步下降至少 30%，允许继续到 500；否则
判定当前两层 PC 不具备快速 PDE 资格。

---

# 5. H2B-P：row-complete restricted-global patch fallback

仅在 H2B-S0 FAIL，或 H2B-K global coercive solve明确失败时执行。

## 5.1 为什么改变局部 operator

当前 element factor 只包含中心 element contribution。P 路线保持同一 central-cell independent
row set，但局部矩阵改为真正的全局 restriction：

```math
B_P
=
R_PB_0R_P^T.
```

`B_P` 必须包含所有与 patch rows相交的 neighboring elements 对这些 rows 的装配贡献。
它不是扩大到任意大 overlap，也不是 face-pair 的无界搜索。

## 5.2 P0：只做一个代表性 interior class

第一轮只选择一个数量最多、无 Floquet constraint 的 interior class。构造 `B_P` 的允许方法：

1. 从所有 touching cells 的 local tensors 精确累计；或
2. 使用已资格化 matrix-free `B0` 对 patch basis 做 column reconstruction。

若使用 column reconstruction，时间可以长，但每列/每批必须流式，禁止物化 global matrix。

必须比较：

```text
element block vs row-complete patch
factor bytes
condition estimate / pivot growth
solve gain
five-source rho_star
```

P0 Gate：

```text
factorization residual <= 1e-10
solve residual <= 1e-10
all finite/deterministic
checkerboard rho_star <= 0.70
mixed rho_star <= 0.85
other sources rho_star <= 0.95
single-class build peak < 1,500,000,000 B
swap = 0
```

## 5.3 P1：有界 class 扩展

只有 P0 通过才扩展到全部 exact neighborhood classes。要求：

```text
unique numeric factors <= 32
factor + metadata <= 500,000,000 B
no per-cell factor
no slab factor
online predicted live set <= 1,700,000,000 B
```

P1 完成后返回 H2B-K 的 normalized two-level FGMRES Gate。

## 5.4 唯一更大 patch fallback

若 row-complete central-cell patch 的方向接近通过：

```text
worst rho_star <= 0.95
且至少三类 source 达到各自 Gate
```

只允许一次 two-cell face-pair patch。否则关闭 full-space block-factor lane，重新审阅 geometric
multigrid；禁止 edge-star、vertex-star、任意 overlap 或 patch-size 扫描。

---

# 6. H2D 与时谐 PDE 自动推进

H2B-K coercive global solve通过后，Codex可自动继续，无需再次等待审阅。

## 6.1 H2D full-space matrix-free DtN

要求：

```text
80-mode identity不变
explicit dense C/D = 0
MPI1/MPI2 action error <= 1e-11
partition identity <= 1e-12
retained + work <= 150,000,000 B
no MatPython getInfo假数据
```

## 6.2 时谐局部 factor

精确 PDE：

```math
A
=
K_{curl}-k_0^2M_\epsilon+A_{DtN}.
```

局部辅助 operator：

```math
B_\beta
=
K_{curl}-k_0^2M_\epsilon
+i\beta k_0^2M_{|\epsilon|}.
```

只允许：

```text
beta = 1.0
beta = 0.5
```

先用 `beta=1.0`。只有 100/200 步出现明确平台且内存通过，才允许 `beta=0.5`。不得连续扫描。

## 6.3 20/100/200-step screen

```text
right FGMRES
restart = 20
```

Gate：

| iteration | true residual |
|---:|---:|
| 20 | `<=0.60` |
| 100 | `<=0.20` |
| 200 | `<=0.08` |

并且 iteration 150→200 必须继续下降至少 15%。

若未达到绝对 Gate，但 200 步 true residual `<=0.15` 且最后 50 步下降至少 30%，允许一次固定
`16`-vector harmonic Ritz augmentation；禁止更多 vector-count 扫描。

## 6.4 Full PDE

```text
true residual          <= 1e-6
max iterations         = 5000
timeout                = 12 h
completed process RSS  < 2,000,000,000 B
controlled stop        = 1,950,000,000 B
warning                 = 1,750,000,000 B
swap                    = 0
```

收敛后先销毁：

```text
KSP
PC
local factors
wave/Ritz basis
DtN work arrays
```

再进入 field 与 R/T/A。必要时 solve 与 postprocess使用顺序 subprocess，避免内存高水位叠加。

物理 Gate仍要求：

```text
condensed/full true residual authority
R/T/A and volume absorption closure
12/12 significant powers
12/12 significant complex amplitudes
canonical full field
same-machine direct authority comparison
```

---

# 7. 内存预算

当前可复用对象：

| 对象 | 实测/预算 |
|---|---:|
| full-space action worker baseline | 约 `340 MB` process-tree peak |
| R2 factor + metadata | `201.934 MB` |
| existing smoother factor+work | `217.954 MB` |
| 75D full-space basis pure values | 约 `208.6 MB` |
| DtN retained/work | `<=150 MB` |
| FGMRES(20) + PC vectors | `<=180 MB` |
| runtime/allocator reserve | `>=250 MB` |

任何 global coercive/PDE run 前必须生成真实 live-set inventory：

```text
predicted simultaneous live set <= 1,700,000,000 B
```

若超出，依次：

1. 删除 reference/canonical authority objects；
2. 不保留 `BZ/AZ`；
3. factor 与 solve 分阶段；
4. coarse setup 后释放临时 vectors；
5. solve/postprocess 拆 subprocess。

禁止降低 p、增大 h、减少 DtN mode 或放宽 2 GB。

---

# 8. Codex 受控自主权

Codex可在不等待新审阅的情况下：

- 实现 additive/forward/symmetric 三种固定组合；
- 计算 `omega_star`、`rho_star`、`eta`；
- 修复 telemetry、checker、runtime path、MPI、MPC、buffer lifecycle；
- 实现 residual-minimizing scalar normalization；
- 构建/正交化固定 75D full-space wave basis；
- 逐列生成并释放 `BZ/AZ`；
- 实现 row-complete central-cell patch；
- 在允许的两种 local block construction中选择更低内存者；
- 在 Gate满足后自动进入 DtN、PDE screen和full；
- 增加 setup timeout，只要内存与进度 Gate不变。

仍禁止：

- 退回 static condensation；
- 调用 trace Schur、trace slab PC 或 B2/B4 local Krylov；
- 恢复 16 个 slab factors；
- 修改物理、p/h、材料、角度、mode count；
- damping/颜色/patch-size无界扫描；
- global matrix；
- 磁盘反复读取 hot factors；
- 未收敛就输出 official R/T/A；
- 新分支、PR 或 master merge。

---

# 9. Formal campaign 预算

```text
H2B-S0 scale-invariant diagnostic       = 1 formal campaign
H2B-K coercive global solve             = 1 campaign + 1 execution-fix rerun
H2B-P0 representative patch fallback    = 1 campaign
H2B-P1 expanded patch                   = 1 campaign + 1 execution-fix rerun
H2D DtN                                 = 1 formal campaign
H4 beta=1.0 screen                      = 1 campaign
H4 beta=0.5 screen                      = conditional 1 campaign
H4 Ritz-16 augmentation                 = conditional 1 campaign
H4 full                                 = 1 formal + 1 code-fix rerun
```

数值负结果不得以“执行修复”名义重复。

---

# 10. Required outputs

```text
docs/task37_extra_development/outcomes/h2b_scale_invariant_direction.md
docs/task37_extra_development/outcomes/h2b_normalized_global_solve.md
docs/task37_extra_development/outcomes/h2b_row_complete_patch.md
docs/task37_extra_development/outcomes/h2d_fullspace_dtn.md
docs/task37_extra_development/outcomes/h4_fullspace_pde.md
docs/task37_extra_development/response_v9.md
```

只创建实际执行阶段的文件。compact records位于：

```text
benchmarks/cases/101_task37_extra_development/records/
```

heavy raw继续进入 ignored artifacts。旧 H2B failure record、response_v8 和 raw不得覆盖。

---

# 11. 给执行 Codex 的简化指令

```text
继续只在 codex/20260806-task37-iterative-extra-development 工作。
禁止新分支、PR、master merge 和 ordinary default 修改。

完整阅读：

docs/task37_extra_development/response_v8.md
docs/task37_extra_development/review_report_v9.md

以 V9 为最高优先级合同。

当前 H2B 只证明 fixed-unit symmetric stationary sweep失败；
不要删除已通过的 R2 factor store，也不要原样重跑 H2B。

先执行 H2B-S0：

1. additive PoU；
2. forward-only colored；
3. current symmetric对照；

对五类 source计算 q=B0*z、omega_star、rho_star、eta及norm amplification。
不得扫描 damping或颜色。

若任一组合通过 V9 S0 Gate，自动进入 normalized PC + 75D coarse + coercive FGMRES。
若三者均失败，自动进入 row-complete restricted-global central-cell patch。

coercive global solve通过后，自动继续 full-space matrix-free DtN和时谐PDE screen/full。

全过程必须保持：

fine_space = uncondensed_fullspace
condensation = false
static_condensed_operator_used = false
trace_slab_pc_used = false
B2_B4_local_krylov_used = false
completed PDE peak < 2,000,000,000 B
swap = 0

最终统一更新 response_v9.md，并只push当前extra分支。
```
