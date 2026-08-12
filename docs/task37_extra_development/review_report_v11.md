# Task037-extra Review Report V11：p4 定义的高阶补空间 row-complete patch 与低于 2 GB PDE 恢复路线

## 0. 审阅身份与最终决定

```text
review                                  = Task037-extra Review Report V11
working_branch                          = codex/20260806-task37-iterative-extra-development
reviewed_HEAD                           = 708f2d23a1406abf0b3b27de925c6abcec3cad86
reviewed_handoff                        = docs/task37_extra_development/response_v10.md
reviewed_previous_contract              = docs/task37_extra_development/review_report_v10.md
H1R3_action_layer                       = ACCEPTED_AND_FROZEN_PASS
H2A_R0_R1_R2                            = ACCEPTED_AND_FROZEN_PASS
H2B_fixed_unit_element_sweep            = ACCEPTED_NUMERIC_FAIL
H2B_S0_element_direction                = ACCEPTED_DIRECTION_FAIL
H2B_P0_row_complete_representative      = ACCEPTED_LOCAL_PASS
H2B_P1_full_neighborhood_dense_factors  = CLOSED_BY_CAPACITY
C1_canonical_congruence                 = CLOSED_BY_84_REPRESENTATIVES
M0_p4_to_p6_local_fixture               = ACCEPTED_LOCAL_FEASIBILITY_ONLY
new_authorized_lane                     = M: p4-split high-order-complement row-complete patch
full_PDE_memory_hard_target             = process-tree RSS < 2,000,000,000 B
swap                                    = strictly_zero
outer_space                             = uncondensed_fullspace_only
static_condensed_fallback               = forbidden
bounded_codex_autonomy                  = authorized
create_new_branch                       = forbidden
pull_request                            = forbidden
merge_to_master                         = permanently_not_planned
ordinary_default_change                 = forbidden
```

本审阅接受 V10 的最终负结论：84 个完整 `882 x 882` row-complete neighborhood factor
不能在既定容量合同下继续；严格的 permutation + unit-modulus phase 分类也没有把 84 个
neighborhood 压缩到 32 个代表。不得重新打开 P1/C1、放宽 tolerance 合并，或把容量负结果
包装成 execution-fix 后重跑。

同时，本审阅接受两个决定性正结果：

1. P0 已证明 row-complete patch 是正确的局部算子；对五类 residual，代表性 patch 的
   scale-invariant contraction 达到约 `1e-14`，checkerboard 约 `3e-12`。
2. M0 已证明生产 p4→p6 局部嵌入、orientation、Hermitian adjoint 和 Floquet phase-once
   在单 cell 上可闭合；p6 local dimension 为 `882`，p4 local dimension 为 `300`。

因此下一步不再保存完整 882 维 neighborhood inverse，而是把每个局部空间分成：

```math
V_6 = V_4 \oplus W_{6\setminus4},
```

其中低阶子空间维数为 `300`，高阶补空间维数为：

```math
882-300=582.
```

低阶部分只保存小型 p4 class factors；高阶部分继续使用数值上已通过的 row-complete
neighborhood operator，但只在 582 维补空间中 factor。该方案保留 P0 的正确局部物理，
同时把 84 个 neighborhood factor 的纯数值上界从约 1.046 GB 降到约 455.4 MB。

本路线不是旧 Task30/Task37 的简单 p4 additive correction：

- fine space 始终为未凝聚 full-space；
- p4 不单独承担全部 coarse correction；
- p6 高阶补空间使用 row-complete、而非 single-element operator；
- low/high 两部分采用 residual-minimizing sequential composition；
- 不形成 global matrix、condensed Schur 或 16-slab factor。

---

# 1. 最新证据的准确解释

## 1.1 已关闭的完整 neighborhood-factor 路线

P0 的一个 `882 x 882` factor 约为：

```math
882^2\times16+882\times4
=12,450,312\ \mathrm{B}.
```

84 个独立 factor 的纯 values+pivots 为：

```math
84\times12,450,312
=1,045,826,208\ \mathrm{B}.
```

该数值尚未包括 class/neighborhood metadata、KSP、wave basis、DtN、action、MPI/PETSc
runtime 和工作向量，所以即使数值上可行，也不再具有 `<2 GB` online PDE 的可信路径。

C1 又得到 `84 neighborhoods / 84 candidate representatives`，说明当前严格 metadata 下没有
可证明的 monomial orbit compression。该 capacity stop 是正式负结果，不再继续寻找 dense
learned transform、tolerance clustering 或结果驱动合并。

## 1.2 P0 仍然给出了正确的算法线索

单 element inverse 的 scale-invariant `rho_star` 约为 `0.953--0.975`；row-complete patch
则把五类 source 降到约 `1e-14`，checkerboard 约 `3.16e-12`。这表明失败根因不是 LU、
Floquet、MPC 或 action，而是单 element block 缺少 touching-cell 对 central rows 的装配贡献。

因此下一条局部 smoother 仍必须基于：

```math
B_P=R_PB_0R_P^T,
```

不得退回：

```math
C_c^HB_cC_c
```

作为完整 p6 局部 inverse。

## 1.3 M0 提供了容量修复的入口

M0 的生产局部嵌入为：

```text
I46 shape   = (882, 300)
dtype       = float64
payload     = 2,116,800 B
```

它已经通过局部 structural、orientation、adjoint 和 Floquet phase-once fixture，但尚未通过
full-mesh owner/ghost/MPC 资格。V11 不把 M0 写成全局 transfer PASS，只把它作为后续
p-split 的前置可行性证据。

---

# 2. 新方法：p4-split row-complete complement patch

## 2.1 局部正交分解

对每个实际 constrained central row set，构造 p4→p6 注入：

```math
I_c\in\mathbb C^{882\times300}.
```

使用固定、确定性的 Householder QR：

```math
I_c=Q_{L,c}R_c,
```

并补全：

```math
Q_c=[Q_{L,c},Q_{H,c}],
```

其中：

```math
Q_{L,c}\in\mathbb C^{882\times300},
\qquad
Q_{H,c}\in\mathbb C^{882\times582}.
```

必须验证：

```math
\lVert Q_c^HQ_c-I\rVert_2\le1e-12,
```

```math
\operatorname{rank}(I_c)=300,
```

以及 orientation、Floquet/MPC phase 只作用一次。

禁止通过 source/result 拟合补空间；禁止使用随 residual 改变的 SVD tolerance。rank 判据固定为
`128 * eps(float64) * ||I_c||_2` 或等价、预先冻结的数值合同。

## 2.2 低阶与高阶局部算子

低阶 element-class block：

```math
B_{L,c}=Q_{L,c}^H\widetilde B_cQ_{L,c}
\in\mathbb C^{300\times300}.
```

高阶 row-complete neighborhood block：

```math
B_{H,P}=Q_{H,P}^HB_PQ_{H,P}
\in\mathbb C^{582\times582}.
```

其中 `B_P` 必须是 P0 已资格化语义下的 restricted-global row-complete operator。
`Q_{H,P}` 是 central row set 上真实的 p4 补空间，不得使用未施加实际 orientation/MPC 的
reference-only basis。

## 2.3 内存依据

一个 582 维 complex128 LU values+pivots 上界为：

```math
582^2\times16+582\times4
=5,421,912\ \mathrm{B}.
```

84 个高阶 neighborhood factors：

```math
84\times5,421,912
=455,440,608\ \mathrm{B}
\approx434.34\ \mathrm{MiB}.
```

若低阶部分保留 16 个 300 维 numeric factors：

```math
16\times(300^2\times16+300\times4)
=23,059,200\ \mathrm{B}.
```

两者纯 values+pivots 合计：

```math
478,499,808\ \mathrm{B}
\approx456.33\ \mathrm{MiB}.
```

这些数字是容量上界预测，不是实测 PASS。正式 factor+metadata、transform carrier 和 work
必须分别测量；任何隐藏的 per-neighborhood dense `Q_H` 都可能破坏预算。

## 2.4 变换存储规则

禁止长期保存 84 份完整 `882 x 582` dense `Q_H`。允许：

- 一个或少数 reference Householder carriers；
- orientation/permutation/Floquet 的稀疏或 monomial metadata；
- 每个 neighborhood 的 compact row/incidence/class map；
- apply 时使用 bounded workspace 恢复 `Q_H^Hr` 与 `Q_Hz_H`。

若实际实现必须长期保存 84 份 dense complex `Q_H` 才能作用，则本路线直接容量失败，不能
通过放宽 2 GB Gate 继续。

---

# 3. M1：full-mesh owner-local p4→p6 adapter

## 3.1 固定范围

第一阶段只实现 transfer/adjoint，不构造 patch factor或 KSP：

```text
p6/h10 MPI1 production mesh
p4/h10 同一 mesh/material/Floquet
owner-local p4->p6 apply
Hermitian adjoint p6->p4 apply
no global AIJ transfer
no global matrix
no PDE
```

随后只运行一个 MPI2 identity Gate，不运行 MPI4/MPI8。

## 3.2 必须验证

1. p4 field 注入到 p6 后，与 p6 对同一解析 p4-compatible field 的表示误差 `<=1e-11`；
2. adjoint identity：

```math
|\langle P_{46}x,y\rangle-\langle x,P_{46}^Hy\rangle|
\le1e-12\lVert x\rVert\lVert y\rVert;
```

3. MPI1/MPI2 canonical relative L2 `<=1e-12`；
4. missing/extra/duplicate 均为 0；
5. orientation、edge reverse、face D4 和 Floquet phase-once 全部通过；
6. actual p4/p6 rows、constraints、owned/ghost 和 transfer bytes完整审计；
7. no absolute owner/global row进入可复用 reference transform identity。

## 3.3 资源 Gate

```text
retained transfer + compact carrier <= 128,000,000 B
bounded apply workspace            <= 64,000,000 B
completed MPI1 process-tree peak    < 900,000,000 B
completed MPI2 process-tree peak    < 1,300,000,000 B
swap                                = 0
```

M1 任一 algebra/MPI Gate 失败，立即关闭 M 路线；不得在错误 transfer 上继续 patch factor。

---

# 4. M2：单代表 high-complement patch oracle

## 4.1 固定代表

复用 P0 已资格化的 central representative：

```text
central ordinal = 3
central class   = 3
touching cells = 19
patch rows      = 882
```

必须复用 P0 authority 和同一 `B0` 定义，不重新选择“更容易”的代表。

## 4.2 构造与 Gate

构造 `Q_L/Q_H`、`B_L` 和 `B_H`，验证：

```text
rank(I_c) = 300
rank(Q_H) = 582
Q orthogonality error <= 1e-12
split reconstruction error <= 1e-11
B_H finite and deterministic
B_H factorization residual <= 1e-10
B_H representative solve residual <= 1e-10
```

对与 P0 相同的五类 residual，至少记录：

- p4-low energy fraction；
- high-complement energy fraction；
- `Q_H` correction 的 action closure；
- unit-step 与 scale-invariant `rho_star`；
- correction/solution SHA 与重复确定性。

最低方向 Gate：

```text
checkerboard/high-frequency rho_star <= 0.70
mixed rho_star                        <= 0.90
all other sources rho_star            <= 0.98
```

此处要求的是高阶补空间 correction 对完整 residual 的作用；不能只在 `B_H` 内部 residual 上
报告接近零而回避 full-space action。

## 4.3 资源 Gate

```text
one high factor values+pivots <= 5,500,000 B
all retained transform metadata <= 32,000,000 B
completed process-tree peak < 1,300,000,000 B
swap = 0
```

M2 数值失败时，关闭“p4 补空间 dense patch factor”路线；不得调 QR tolerance、补空间维数或
source。execution/JIT/telemetry defect 可在保留 raw 后做一次窄修。

---

# 5. M3：全 84-neighborhood complement factor store

仅在 M2 全 PASS 后进入。

## 5.1 避免 P0 的重复 tabulation

不得为 84 个 neighborhood 重复执行 p6 bilinear JIT 或逐 touching-cell 重新 tabulate。
必须在 offline staging 中：

1. 从已通过的 JIT cache 生成一次 exact constrained element-class matrices；
2. 按 numeric class 缓存原始 operator matrix，不能只留下 overwritten LU；
3. row-complete patch 通过 class matrix的索引装配构造；
4. 投影到 582 维 complement后 factor；
5. 每次只保留 current patch、current projected patch 和 bounded compare workspace；
6. factor写入 hash-bound store后释放原始 patch。

原始 element-class matrices属于 offline builder 数据，不能与 online KSP 同时常驻。

## 5.2 固定容量 Gate

本阶段不再使用旧的 `factor_count <=32`，而改用由维数下降支持的**字节 Gate**：

```text
neighborhood identity count        = 84
unique high-complement factors     <= 96
high-factor values+pivots          <= 460,000,000 B
low p4-factor values+pivots        <= 30,000,000 B
factor + metadata + carriers       <= 560,000,000 B
predicted online simultaneous set  <= 1,700,000,000 B
offline builder peak               < 1,800,000,000 B
fresh online loader peak           < 1,050,000,000 B
swap                               = 0
```

`<=96` 只是 fail-closed 结构上限；正式资格仍由 `<=560 MB` 总字节决定。禁止 tolerance-based
factor merge。exact numeric dedup可以使用，但不能成为通过预算的必要假设。

## 5.3 refinement metadata Gate

只做 metadata/class discovery，不 factor p6/h5：

```text
p4/h10
p4/h5
```

要求 neighborhood/class 数增长严格低于 cell 数增长；若 refinement 后产生随 cell 近线性增长的
factor identity，关闭该路线，不外推 p6/h1。

---

# 6. M4：稳定的 residual-minimizing p-split PC

仅在 M3 factor store和资源 Gate 全 PASS 后进入。

## 6.1 禁止恢复失败的 fixed-unit sweep

不得使用：

- 8-color forward/reverse unit-step；
- 原 H2B symmetric composition；
- 16 次 residual feedback；
- stationary Richardson 把系数固定为 1。

## 6.2 两阶段可变预条件器

低阶方向：

```math
z_L=M_L^{-1}r,
\qquad
q_L=B_0z_L,
```

```math
\omega_L=
\frac{q_L^Hr}{q_L^Hq_L},
\qquad
r_1=r-\omega_Lq_L.
```

高阶补空间方向：

```math
z_H=M_H^{-1}r_1,
\qquad
q_H=B_0z_H,
```

```math
\omega_H=
\frac{q_H^Hr_1}{q_H^Hq_H}.
```

最终返回：

```math
z=\omega_Lz_L+\omega_Hz_H.
```

`M_L` 只使用 p4-low class blocks；`M_H` 只使用 row-complete 582 维 complement patches。
两次 `omega` 都必须 finite，并使用 exact full-space `B0` action。因为该 PC 随 residual 变化，
外层只能使用 right FGMRES。

该设计每个 PC apply 目标为两次 global action，而不是原 H2B 的 16 次。

## 6.3 one-apply Gate

对冻结五类 residual：

```text
checkerboard rho <= 0.70
mixed rho       <= 0.80
gradient/curl/physical rho <= 0.90
finite and deterministic
exact action closure <= 1e-11
PC apply / action wall ratio <= 6
completed online peak < 1,350,000,000 B
swap = 0
```

若只有一个 source轻微超限，禁止扫描 damping；Codex只能检查一次实现/投影闭合。确认是数值负结果
后关闭 M4，不进入 global KSP。

---

# 7. M5：coercive global FGMRES 与波传播 coarse

## 7.1 第一屏：不带 wave coarse

先运行：

```text
operator = B0 = Kcurl + k0^2 M_|epsilon|
right FGMRES restart=20
maximum iterations=100
```

Gate：

```text
20-step true residual  <= 0.40
100-step true residual <= 1e-3
iteration 50->100 仍有明确下降
completed peak < 1,550,000,000 B
swap = 0
```

## 7.2 有明确全局平台时才加 75D wave coarse

若 local p-split PC 通过 one-apply Gate，但 global solve出现传播型平台，则加入固定 75D
full-space wave basis。只保留：

```text
Z
small E=Z^H B0 Z
factor(E)
```

`B0Z` 必须逐列生成后释放，不长期保留。不得扫描 coarse dimension。

带 coarse 的 full coercive Gate：

```text
true residual <= 1e-8 within 500 iterations
process-tree peak < 1,700,000,000 B
swap = 0
```

M5 不通过则停止 PDE fast track；不能用 5000 次慢迭代绕过 coercive solver失败。

---

# 8. M6：matrix-free DtN 与时谐 PDE

仅在 M5 完整通过后自动进入。

## 8.1 DtN

保持 frozen 80-mode physical definition：

```text
explicit C/D materialized count = 0
MPI1 action identity <= 1e-11
MPI2 partition identity <= 1e-12
retained + work <= 150,000,000 B
```

不得减少 modes、改变归一化、改材料或入射条件。

## 8.2 时谐辅助算子

精确方程：

```math
A=K_{curl}-k_0^2M_\epsilon+A_{DtN}.
```

局部 p-split factors使用：

```math
B_\beta
=K_{curl}-k_0^2M_\epsilon
+i\beta k_0^2M_{|\epsilon|}.
```

只允许：

```text
beta=1.0
beta=0.5
```

先运行 `beta=1.0`；只有其 residual 明确下降但过慢/平台且资源全部通过时，才允许一次
`beta=0.5`。禁止连续扫描。

## 8.3 PDE 漏斗

```text
right FGMRES restart=20
20-step
100-step
200-step
```

Gate：

```text
20-step true residual  <= 0.60
100-step true residual <= 0.20
200-step true residual <= 0.08
iteration 150->200 improvement >= 15%
completed peak < 1,900,000,000 B
swap = 0
```

通过后正式 full：

```text
true residual <= 1e-6
max iterations = 5000
timeout = 12 h
completed process-tree RSS < 2,000,000,000 B
swap = 0
```

收敛后必须先销毁 KSP、p-split factors、transfer/work、wave basis 和 DtN work，再执行 field、
R/T/A、volume absorption 和 12+12 channels。必要时 solve 与 postprocess使用顺序 subprocess，
但不得把 incomplete process peak冒充 completed authority。

---

# 9. 与旧 p4/低阶负结果的区别

本路线不得被实现成以下已失败结构：

```text
condensed trace p4 additive correction
p4 coarse + diagonal complement
single-element full p6 inverse
fixed-unit colored forward/reverse sweep
LOR-HX hierarchy
```

V11 的必要身份为：

```text
fine_space                         = uncondensed_fullspace
condensation                       = false
static_condensed_operator_used     = false
trace_slab_pc_used                 = false
B2_B4_local_krylov_used            = false
p4_role                            = local low-subspace definition
high_order_operator                = row-complete restricted-global patch
high_order_dimension               = 582
stationary_unit_sweep              = false
outer_krylov                       = right FGMRES
```

每个 record/checker 必须显式验证这些字段。

---

# 10. 文献依据与适用边界

本路线的设计与以下高阶 `H(curl)` 多层原则一致：

1. Sun, Lee and Cendes, *Construction of Nearly Orthogonal Nedelec Bases for Rapid Convergence
   with Multilevel Preconditioned Solvers*, SIAM J. Sci. Comput., DOI `10.1137/S1064827500367531`：
   高阶 Nedelec 的 p-level 分解应显式区分低阶与高阶、旋转与梯度相关分量。
2. Lai and Olson, *Algebraic Multigrid for High-Order Hierarchical H(curl) Finite Elements*,
   SIAM J. Sci. Comput., DOI `10.1137/100799095`：高阶 curl 问题需要兼容的 p-hierarchy 和
   gradient-aware smoothing，普通点/简单 additive 方法不足。
3. Brubeck and Farrell, *Multigrid solvers for the de Rham complex with optimal complexity in
   polynomial degree*, arXiv `2211.14284`：通过正交/近正交 p 分解与适当 patch decomposition，
   可以把高阶 patch问题的时间与空间复杂度控制在合理范围。
4. Pazner, Kolev and Dohrmann, *Low-Order Preconditioning for the High-Order Finite Element
   de Rham Complex*, DOI `10.1137/22M1486534`：高阶 de Rham solver必须保持空间/映射兼容。
   本项目已关闭当前显式 LOR-HX 实现；该文献只支持兼容分解原则，不授权重开 G2。

这些文献主要针对 coercive/Riesz-map 或相应辅助算子，不能证明当前复数、非 Hermitian、
Floquet-DtN 时谐问题必然收敛。因此 V11 仍坚持先 coercive Gate，再进入时谐 PDE。

---

# 11. Codex 受控自主权限

Codex可以在本报告固定架构内自行处理：

- owner/ghost/MPC transfer adapter；
- orientation、phase-once、adjoint和canonical identity；
- deterministic QR/Householder carrier；
- JIT cache、offline matrix/factor store和hash manifest；
- exact numeric dedup；
- bounded workspace和对象生命周期；
- runner/checker/provenance/telemetry；
- MPI1/MPI2 transfer execution defect；
- FGMRES/MatPython接口和true residual监控；
- DtN action接线；
- solve/postprocess subprocess staging。

允许每阶段：

```text
1 formal campaign
+ 1 clearly evidenced execution-fix rerun
```

数值、容量或物理负结果不得包装成 execution-fix。

仍禁止：

- 新分支、PR、master合并、ordinary default修改；
- 静态凝聚或16-slab factor；
- 84个完整882维factor；
- tolerance-based factor/orbit merge；
- dense learned transform；
- 调整 p4/p6、网格、材料、角度、波长或DtN modes；
- 无界 smoother、damping、beta、restart或coarse-dimension扫描；
- 放宽2 GB/swap/true residual/physics Gate；
- 未收敛时输出official R/T/A。

---

# 12. Required outputs

```text
docs/task37_extra_development/outcomes/m1_fullspace_p4_p6_transfer.md
docs/task37_extra_development/outcomes/m2_high_complement_patch_oracle.md
docs/task37_extra_development/outcomes/m3_complement_factor_store.md
docs/task37_extra_development/outcomes/m4_psplit_preconditioner.md
docs/task37_extra_development/outcomes/m5_coercive_global_solve.md
docs/task37_extra_development/outcomes/m6_time_harmonic_pde.md
docs/task37_extra_development/response_v11.md
```

Tracked compact records使用：

```text
benchmarks/cases/101_task37_extra_development/records/m1_*.json
...
benchmarks/cases/101_task37_extra_development/records/m6_*.json
```

Heavy raw继续进入 ignored `benchmarks/artifacts/task037_extra_development/`。前一 Gate 失败时，
后续 record/outcome 必须不存在或明确 `not_run_by_gate`，不得伪造空 PASS。

---

# 13. 给执行者的简明顺序

```text
M1 full-mesh p4->p6 owner-local transfer
-> M2 representative 582D row-complete complement oracle
-> M3 all-84 complement factor store under byte Gate
-> M4 residual-minimizing p-split PC
-> M5 coercive FGMRES, then fixed 75D wave coarse only if needed
-> M6 matrix-free DtN and time-harmonic PDE
-> full solve and official physics
```

当前最短、又不重复历史失败的路线不是“再试一个 p4 coarse”，而是：

> **用 p4 精确定义低阶子空间，把 P0 已证明正确的 row-complete inverse 只保留在 582 维
> 高阶补空间中，再以 residual-minimizing p-block composition 进入 FGMRES。**

只有这条路线同时保留了 P0 的数值正确性、M0 的 p-level 结构，以及 `<2 GB` 的可审计容量路径。
