# Task037 Review Report V2：MPI scaling 定论、局部 ILU 因子语义与 factor-free 发展路线

## 0. 审阅身份与最终判定

```text
review                         = Task037 Review Report V2
reviewed_branch                = codex/20260803-task37-matrix-free-iterative-development
reviewed_case                  = Case100 / M3a overlap-0.125 partition
reviewed_MPI                   = 1 / 2 / 4 / 8 full solves
reviewed_record                = task37_m3a_mpi_scaling_v1.json
reviewed_outcome               = m3a_mpi_scaling_comparison.md
ordinary_default               = unchanged
merge_to_master                = not authorized by this review
Task037b / Hybrid              = not authorized by this review
0.7 nm PDE                     = not authorized by this review
```

本轮接受的正式结论为：

```text
M3a numerical correctness on MPI1/2/4/8              = PASS
cross-MPI canonical field identity                    = PASS
current minimum process-tree peak                     = 4.600486755 GiB at MPI1
current p6 slab-ILU architecture below 2 GiB          = impossible without structural change
current dominant scalable object                      = retained local ILU factors
exact factor-class reuse                              = deferred optional optimization
complex64 local factors                               = deferred optional optimization
factor-free p6 local solves + p2 auxiliary PC         = primary authorized research direction
FGMRES restart reduction                              = authorized as a bounded companion study
optimized/non-overlapping Schwarz                     = authorized only as one bounded candidate
matrix-free DtN                                       = authorized algebraically; low current-memory priority
partial/uncondensed p6 comparison                     = fallback bounded study only
```

最重要的审阅结论是：

> **当前 `91,415,952 stored factor NNZ` 表示 16 个局部 slab 矩阵经过 ILU(0) 分解以后，长期保留的 L/U 因子总存储；它不是 16 个原始 slab 矩阵的存储量。原始 slab 矩阵在 setup 中逐个形成，完成因子化后即释放。若要把 MPI1 从 4.60 GiB 降到 2 GiB 以下，必须取消或大幅替代这些 p6 因子，而不能只继续调 MPI、restart 或对象释放顺序。**

---

# 1. 最新 MPI1/2/4/8 证据

冻结的 p6/h10、13.5 nm、10° 掠射、S 偏振、16 slabs、overlap 0.125、partition-of-unity、75D wave coarse 候选，在 MPI1/2/4/8 下均完成正式 full solve：

| MPI | iterations | full-FE true residual | process-tree peak | wall | official physics |
|---:|---:|---:|---:|---:|---|
| 1 | 352 | `9.9736128e-7` | **4.600486755 GiB** | 1999.03 s | pass |
| 2 | 352 | `9.9980922e-7` | 5.682544708 GiB | 1153.02 s | pass |
| 4 | 365 | `9.9232735e-7` | 8.265838623 GiB | 711.57 s | pass |
| 8 | 341 | `9.8613618e-7` | 12.593410492 GiB | 470.57 s | pass |

四组结果的 R/T/A、80 个 modal keys、canonical active trace 和完整 FE 场均闭合。由此可正式确认：

1. 增加 MPI rank 会降低单 rank 内存并缩短时间；
2. 当前实现的 process-tree 总内存却随 MPI rank 增加；
3. 极限总内存应在 MPI1 或 MPI2 上评价；
4. 数值研发和短 screen 可以在 MPI8 上进行，以缩短反馈时间；
5. 一个候选只有在 MPI8 数值 Gate 通过后，才运行一次 MPI1 full 评价最低内存。

MPI1 的阶段峰值为：

| 阶段 | process-tree peak |
|---|---:|
| process start | 0.195 GiB |
| FE setup | 0.261 GiB |
| static-condensed assembly | 0.651 GiB |
| solver / factor stage | **4.262 GiB** |
| after field | 4.405 GiB |
| canonical export | 4.600 GiB |

因此 MPI1 从静态凝聚完成到 solver/factor 阶段增加：

$$
4.262-0.651=3.611\ \mathrm{GiB}.
$$

这说明当前最低内存的主要矛盾已经不再是 global matrix，而是预条件器 factor、相关工作区以及求解生命周期。

---

# 2. `91,415,952 stored factor NNZ` 到底是什么

## 2.1 局部 slab 系统

对第 $j$ 个重叠物理 slab，定义 restriction $R_j$。当前局部 shifted operator 为：

$$
A_j
=
R_j\left(S-i\sigma D\right)R_j^T,
\qquad \sigma=0.1,
$$

其中 $S$ 是精确 p6 静态凝聚 trace operator，$D$ 是局部对角尺度。

## 2.2 ILU(0) 分解

每个局部矩阵执行：

$$
A_j\approx L_jU_j.
$$

ILU(0) 的含义是：L/U 的填充模式基本限制在局部矩阵既有稀疏图中，不进行完整 LU 那样的任意 fill-in。每次预条件器作用执行：

$$
L_jy_j=r_j,
\qquad
U_jz_j=y_j.
$$

然后用 partition-of-unity 权重装配：

$$
M_{\mathrm{AS}}^{-1}r
=
\sum_{j=1}^{16}
R_j^TW_jz_j.
$$

## 2.3 存储语义

当前实现的生命周期是：

```text
构造 slab 1 原始局部矩阵
→ ILU(0) factorization
→ 保留 factor 1 的 L/U 数据
→ 释放 slab 1 原始矩阵
→ 构造 slab 2
→ ...
→ 最终长期只保留 16 份 factor
```

因此：

```text
stored_factor_nnz = 91,415,952
```

指的是：

$$
\sum_{j=1}^{16}
\operatorname{nnz}(L_j,U_j),
$$

而不是：

$$
\sum_{j=1}^{16}
\operatorname{nnz}(A_j)
$$

的长期常驻存储。

在 PETSc 的 factor-only 路径中，L/U 通常被存放在一个 factor matrix 对象中。原始 local matrix 不长期保留，但在正在处理某一个 slab 时，当前 local matrix、ILU setup workspace 与新 factor 会短暂共存，所以 setup 峰值仍高于最终 factor `.nbytes`。

## 2.4 1.7 GiB 是总计，不是每个 slab

使用 complex128 数值和 int32 列索引，最低 CSR payload 为：

$$
M_{LU,\min}
\approx
91{,}415{,}952\times(16+4)
\approx
1.703\ \mathrm{GiB}.
$$

这是 16 个 factor 的**全局总和**，不是每个 factor 1.7 GiB。

还未计入：

- 行指针和对角位置；
- RCM permutation；
- PETSc factor 对象；
- 局部 RHS 与 solution vectors；
- ILU setup workspace；
- allocator 对齐与碎片；
- 三角求解临时对象。

因此 factor 体系的实际常驻和高水位高于 1.703 GiB。MPI1 的 solver/factor 阶段比静态凝聚阶段高 3.611 GiB，与这一判断一致。

---

# 3. 为什么当前 ILU 架构不可能把 MPI1 压到 2 GiB

MPI1 的静态凝聚阶段已经需要：

$$
M_{\mathrm{pre-PC}}\approx0.651\ \mathrm{GiB}.
$$

FGMRES(90)、恢复与输出还需要约：

$$
M_{\mathrm{Krylov+recovery}}
\approx0.5\text{--}0.7\ \mathrm{GiB}.
$$

若 whole-job peak 要求：

$$
M_{\mathrm{peak}}\le2.0\ \mathrm{GiB},
$$

留给预条件器的预算最多约：

$$
2.0-0.651-(0.5\text{--}0.7)
\approx0.65\text{--}0.85\ \mathrm{GiB}.
$$

而当前 L/U 的**最低 payload**已经为：

$$
1.703\ \mathrm{GiB}.
$$

所以：

$$
\boxed{
\text{保留当前 16 个 p6 ILU factors 时，MPI1 < 2 GiB 在存储下界上就不成立。}
}
$$

当前 0.7 nm 规划不应继续以“稍微压缩 ILU”作为主假设，而应把：

```text
p6 retained factor NNZ = 0
```

设为主路线目标。

---

# 4. 路线决策

## 4.1 路线 1：exact factor-class reuse

MPI1 当前观察到：

```text
16 slab factors
7 unique exact factor classes
9 exact duplicates
```

若完全复用，规则结构上可能明显省内存。但该收益依赖：

- 相同几何；
- 相同材料；
- 相同局部网格；
- 相同边界/shift；
- 完全相同的 factor fingerprint。

对未来复杂结构，16 个 slab 很可能全部不同。因此本审阅决定：

```text
priority          = deferred
production credit = forbidden
```

只有在后续真实结构仍出现较高 exact duplicate ratio 时，才作为低风险补充优化。当前不以它作为 0.7 nm 主路线，也不要求先实现。

## 4.2 路线 2：complex64 local factors

仅把 local PC factors 改成 complex64，fine p6 operator、solution、true residual 和 R/T/A 仍保持 complex128，理论上不会改变最终求解方程，只可能改变收敛路径。

但用户对精度和收敛裕量有合理担忧。因此本审阅决定：

```text
priority = deferred after a successful complex128 factor-free/auxiliary PC
```

以后若启用，必须满足：

```text
fine operator                    = complex128
outer solution/residual          = complex128
DtN and official observables     = complex128
only approximate PC storage      = complex64
full true residual               <= 1e-6, final authority <= 1e-8
12/12 powers + 12/12 amplitudes  = pass
canonical H(curl) field          = pass
```

不得把 complex64 fine action用于 official result。

## 4.3 路线 3：factor-free local slab solves —— 主路线 A

本路线取消：

$$
A_j\approx L_jU_j
$$

的长期 L/U 存储。

仍保留 16 个物理 slab 的定义，但对每个 slab 只提供 matrix-free action：

$$
v_j\mapsto A_jv_j
=
R_jA_6R_j^Tv_j,
$$

局部近似逆通过固定步数内层 Krylov得到：

$$
z_j
\approx
\operatorname{FGMRES}_{k}
\left(A_j,P_{2,j}^{-1},r_j\right),
\qquad k=2,4,6\text{ 等小整数}.
$$

全局 PC 仍是：

$$
M^{-1}r
=
\sum_jR_j^TW_jz_j
+
R_wA_w^{-1}R_w^Hr.
$$

这里：

- 仍有 16 个 slab；
- 但不再保留 16 个 p6 L/U factors；
- 只保留 slab row/support、少量局部 vectors和低阶 PC；
- 内层求解可能随 apply 有轻微变化，所以外层继续使用 right FGMRES。

本路线必须冻结：

```text
retained p6 slab factor count = 0
retained p6 factor NNZ        = 0
retained p6 slab matrices     = 0
```

这是达到 MPI1 < 2 GiB 的必要条件之一。

## 4.4 路线 4：p2 exact-sequence auxiliary PC —— 主路线 B

这不是把最终 p6 解降成 p2。最终 Maxwell fine operator仍是精确 p6：

$$
A_6x=b.
$$

建立 H(curl)-一致的 transfer：

$$
P_{2\to6}:V_2\to V_6,
$$

以及真实 Galerkin auxiliary operator：

$$
A_2=P_{2\to6}^HA_6P_{2\to6}.
$$

若继续采用 16 个物理 slabs，可以在 p2 空间建立 16 个低阶局部矩阵：

$$
A_{2,j}=R_{2,j}A_2R_{2,j}^T,
$$

再对这些 p2 局部系统使用：

- 很小的 ILU；
- AMG；
- 短步局部 Krylov。

因此，用户的理解可以修正为：

> **是的，概念上可以把“16 个 p6 slab factors”替换为“16 个 p2 slab solvers/factors”；但它们只用于预条件器，最终解仍是 p6。**

局部基础维数由 p6 trace 的 432 级降低到 p2 的低阶实体空间，潜在局部 pair 数大幅下降。实际 factor 内存必须测量，不能仅按阶次平方宣称收益。

完整预条件器建议为：

$$
\boxed{
M^{-1}
=
P_{2\to6}\widetilde A_2^{-1}P_{2\to6}^H
+
M_{6,\mathrm{high}}^{-1}
+
R_wA_w^{-1}R_w^H
}
$$

其中：

- $\widetilde A_2^{-1}$：p2 auxiliary solve；
- $M_{6,\mathrm{high}}^{-1}$：不存 factor 的高阶 complement smoother；
- $R_wA_w^{-1}R_w^H$：现有 75D wave coarse。

M4d 已经否定了简单 single-element/high-order patch 的 efficacy。因此不得重复无限扩展 element/face/edge patch；高阶 complement 优先尝试：

1. diagonal / block-diagonal scaling；
2. Chebyshev 或低次 polynomial smoother；
3. 由 p2 PC 预条件的短步 local Krylov；
4. 最多一个小型 p6→p4→p2 p-multigrid prototype。

## 4.5 路线 5：更小 overlap 或 optimized Schwarz —— 次级、有界

继续把 overlap 从 0.125 向零扫描，不应成为主线。允许最多一个新候选：

```text
non-overlapping or near-non-overlapping RAS
+ impedance/Robin transmission
+ existing wave coarse
```

禁止：

- 连续扫描多个 overlap；
- 同时扫描 slab 数、shift、restart、smoother；
- 普通 block Jacobi失败后再进行大规模参数修补。

该路线只有在路线 3/4 已建立 factor-free PC 后才有意义，因为当前 p6 ILU 架构即使减少 overlap，仍然保留大量 p6 factors。

## 4.6 路线 6：降低 FGMRES restart —— 授权伴随研究

当前 restart=90。FGMRES 因 flexible PC 大致需要保存两组 Krylov方向，因此不是“只存 90 个向量”，而是约：

$$
2m+O(1)
$$

个 vectors。

当前一个 active vector：

$$
51{,}192\times16
\approx0.781\ \mathrm{MiB}.
$$

从 restart 90 降到 20，当前 anchor 的原始向量存储大约可减少：

$$
2(90-20)\times0.781
\approx109\ \mathrm{MiB}.
$$

当前模型收益不大，但若 rows 放大 1000 倍，则同一差异会达到百 GiB 量级，所以必须提前验证。

冻结顺序：

```text
90 → 60 → 40 → 30 → 20
```

每次只能在当前最佳 factor-free PC 上测试，不允许独立形成大参数网格。每档执行 100/200-step residual screen，满足以下条件才继续降低：

```text
reported and true residual consistent
no stagnation across the last restart cycle
predicted full iterations <= 3000
no loss of 12-channel accuracy on authorized full solve
```

允许迭代次数增加，只要内存下降、wall 在预算内且 full true residual通过。

## 4.7 路线 7：matrix-free DtN —— 授权但低当前优先级

当前只有 80 个 DtN auxiliary modes，显式 C/D/H 不是当前 4.60 GiB 的主要来源。但到 0.7 nm，mode count 可能显著增加，因此应建立不依赖显式大 C/D 的 action 接口：

$$
E_t
\to
\widehat E_{mn}
\to
\widehat q_{mn}
\to
q_t.
$$

当前阶段只授权：

1. action 与现有 exact C/D/H 的随机向量相对误差 `<=1e-11`；
2. complex128；
3. 不减少 mode count；
4. 不改 R/T/A 定义；
5. 不因该路线单独启动 full PDE。

只有 volume PC 已通过后，才将 matrix-free DtN 接入正式候选。

## 4.8 部分凝聚 / 未凝聚 —— fallback、有界

当前数据已显示 fully condensed p6 trace matrix每行较宽，p6 slab ILU 昂贵。但不能未经测量就宣布 uncondensed 一定更省。

只允许一次小型对照：

```text
A. fully condensed
B. partial condensation
C. uncondensed
```

在同一个 p6/h10、同一个 factor-free auxiliary PC 下比较：

- active/full rows；
- matrix-free vectors bytes；
- retained local cache bytes；
- PC resident bytes；
- 20-step residual slope；
- peak before official output。

先做 setup-only 和 20-step，不自动做三次 full solve。只有某候选同时满足：

```text
predicted MPI1 peak < current best by >=20%
20-step residual no worse than 2x current best
```

才允许一次 full solve。

---

# 5. 下一阶段正式执行顺序

## P0：固定当前 authority，不再修改 M3a

当前 M3a MPI1/2/4/8 作为：

```text
numerical authority for iterative architecture
current minimum-memory baseline = MPI1 4.600486755 GiB
```

不得通过修改 Gate 或删除输出重写该基线。

## P1：factor-free local PC 的纯代数与小型 oracle

先不运行 p6/h10 full PDE。实现并验证：

1. p6 slab matrix-free action；
2. p2-to-p6 restriction/prolongation；
3. p2 auxiliary operator；
4. 局部固定步数 Krylov；
5. p6 factor count/NNZ严格为零；
6. PC apply finite/deterministic；
7. exact p6 fine action identity；
8. PC linearity/variability由外层 FGMRES合法承载。

## P2：MPI8 的 20/100/200-step 漏斗

为了快速反馈，候选开发在 MPI8运行：

```text
20-step smoke
100-step screen
200-step decision
```

最多允许三个候选：

```text
A. p2 auxiliary + diagonal/high-order scaling
B. p2 auxiliary + fixed 2–4 step local Krylov
C. one bounded optimized-Schwarz variant, only if A/B show a mechanism
```

禁止开放参数 sweep。

200-step full authorization：

```text
true residual <=5e-2
predicted iterations <=3000
p6 retained factor NNZ = 0
no global A/F
zero swap
```

## P3：一个 MPI8 full solve

只运行最优候选，验证：

- reported/condensed/full-FE residual；
- canonical active/full FE；
- H(curl) field norm；
- 12/12 powers；
- 12/12 amplitudes；
- R/T/A/closure；
- no hidden direct fallback。

## P4：restart 90→20 的有界缩减

在同一个已通过 PC 上按 90/60/40/30/20 做短 screen，只选择一个最低仍稳定的 restart。不得为每个 restart重新调 PC。

## P5：一个 MPI1 full solve，评价极限内存

只有 MPI8 数值 full通过后，才运行 MPI1：

```text
whole-job peak target        <=2.0 GiB
preferred target             <=1.5 GiB
p6 retained factor NNZ       =0
zero swap                    =true
official physics             =pass
```

若 MPI1仍高于2 GiB，必须输出对象账本并停止，不得通过连续删除正确性检查来达到数字。

## P6：matrix-free DtN algebraic integration

仅在 P3/P5完成后执行，不单独触发新的大型 PDE。

## P7：partial/uncondensed fallback

仅当 factor-free p2 auxiliary PC未达到内存或收敛要求时启动一次 bounded comparison。

---

# 6. 资源 Gate 与 0.7 nm 规划

MPI1 当前：

$$
M_{\mathrm{peak}}=4.600\ \mathrm{GiB},
\qquad
N_{\mathrm{active}}=51{,}192.
$$

对应：

$$
\approx94.2\ \mathrm{KiB/active\ row}.
$$

若未来粗略放大到 50 million active rows，2 TiB 预算只允许：

$$
\approx41\ \mathrm{KiB/row}.
$$

更安全的1.5 TiB设计只允许：

$$
\approx31\ \mathrm{KiB/row}.
$$

因此当前小模型的最终评价必须同时报告：

```text
whole-job MPI1 peak
fixed runtime overhead
scalable resident bytes / active row
p6 factor bytes / row
Krylov bytes / row
mesh/trace metadata bytes / row
DtN bytes / mode
```

注意：直接用 `4.6 GiB × 1000` 只是危险量级估算。Python等固定开销不会线性放大，而 factor、vectors、mesh和field会近似放大；高频收敛和 DtN mode count 还可能使增长更差。

另外，p6/h1 在0.7 nm下的相对分辨率比当前 p6/h10 at 13.5 nm更粗；它是否满足物理精度需要单独验证。本审阅不把 h1 假设视为已资格化离散。

---

# 7. 正确性不可妥协项

任何低内存候选都必须保持：

```text
fine p6 operator                   = exact complex128
DtN mode set                       = unchanged
outer true residual                = computed by exact fine operator
reported/condensed/full FE         <=1e-6
final authority rerun              <=1e-8 when authorized
canonical active/full FE           <=1e-5
relative H(curl)                   <=1e-5
12/12 powers                       = pass
12/12 boundary amplitudes          = pass
R/T/A + volume absorption          = pass
zero swap                          = true
hidden global direct fallback      = forbidden
official RTA on nonconvergence      = forbidden
```

预条件器可以近似、低阶、短步或后续 mixed precision；fine equation和official verification不能近似。

---

# 8. 最终路线优先级

```text
Priority 1:
    factor-free p6 local action
    + p2 exact-sequence auxiliary PC
    + short inner Krylov

Priority 2:
    reduce FGMRES restart toward 20
    after the PC mechanism is established

Priority 3:
    one bounded optimized-Schwarz / low-overlap candidate

Priority 4:
    matrix-free DtN algebra and future scalability

Fallback:
    one bounded partial/uncondensed comparison

Deferred optional:
    exact factor-class reuse
    complex64 local PC factors
```

本审阅不授权继续开发 exact factor reuse 作为主线，也不授权复杂结构前就把 mixed precision写成正式方案。真正面向0.7 nm的成功判据是：

$$
\boxed{
\text{删除 91.4M p6 ILU factor entries，
而不是仅把它们换一种方式重复存储。}
}
$$
