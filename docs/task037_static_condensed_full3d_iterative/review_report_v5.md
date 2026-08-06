# Task037 Review Report V5：p6 → p4 → p2 路线的最终理想容量裁决

## 0. 审阅身份与核心决定

```text
review                         = Task037 Review Report V5
reviewed_branch                = codex/20260803-task37-matrix-free-iterative-development
reviewed_response              = response_v4.md
reviewed_candidate             = Candidate F / p6 -> p4 -> p2
ordinary_default               = unchanged
merge_to_master                = not authorized
production qualification       = NO
Task037b Hybrid block solver   = not authorized
0.7 nm production PDE          = not authorized
```

当前 Candidate F 的修复后 F0 已取得真实科学负结果：exact-sequence transfer、Floquet/orientation、Galerkin action 与重复求解均通过，但当前修正

```math
z_F
=
P_{46}A_4^{-1}P_{46}^{H}r
+
D_6^{-1}r
```

对 low/high/mixed 三类 source 均放大残差：

| source | B4 residual | 当前 F0 residual | improvement = B4/F0 |
|---|---:|---:|---:|
| low | 0.2459994542 | 1.7392087354 | 0.1414433180 |
| high | 0.2465189644 | 1.3350076892 | 0.1846573367 |
| mixed | 0.2461297192 | 1.5174573392 | 0.1621987735 |

该结果足以关闭“当前 additive p4 Galerkin + p6 diagonal”实现，但尚不足以严谨地关闭整个 p6 → p4 → p2 family。原因是：

1. 当前 F0 没有使用 p2 solve；虽然构造了 $A_2$，实际 correction 只使用 exact $A_4^{-1}$ 与 additive diagonal；
2. 非 Hermitian、不定、non-normal Maxwell 系统中，Galerkin coarse correction 不保证欧氏 residual 单调下降；
3. 当前测试不是 p4 trial space 内的 minimum-residual 最优下界；
4. 当前测试也不是原计划的 multiplicative p6 smoother → p4 → p2 V-cycle。

因此 V5 只授权一个最后的、理想化且具有上界意义的 F0b。它不是为路线“找通过方法”，而是回答：

> 即使给予 p4 空间最有利的 minimum-residual 系数，并与当前 B4 四步局部 Krylov 的搜索空间联合，p4 是否仍无法显著降低局部残差？

若答案仍为否，则因为 p2 嵌套在 p4 中，p6 → p4 → p2 路线可在冻结问题与冻结 candidate family 下正式关闭。

---

# 1. Candidate 名称快速索引

| 名称 | 含义 | 当前状态 |
|---|---|---|
| M3a | 16 个重叠 p6 slab ILU(0) + 75D wave coarse + FGMRES | 唯一 full numerical/physical pass；MPI1 4.60 GiB |
| A | 全局 p2 auxiliary + p6 diagonal pre/post | 关闭 |
| B2 | factor-free p6 slab + 裸 local GMRES(2) | 关闭；MPI1 长尾在 2500 步仍约 0.1563 |
| B4 | factor-free p6 slab + 裸 local GMRES(4) | 当前 factor-free 数值基线；200 步约 0.1406 |
| C | B4 + 当前 one-hot RAS/interface shift | 当前实现关闭 |
| D | local p6 Krylov 内加入 local p2 auxiliary | D0 contraction 比 B4 更差，关闭 |
| R7 | p4-core 部分凝聚：保留 108 个 p4 interior modes | 核心代数通过，public DtN complement Gate 未闭合 |
| F | p6 → p4 → p2 exact-sequence p-multigrid | 当前 additive F0 负结果；V5 进行最终理想容量裁决 |
| E | M120 左/右本征模作为 Full3D coarse/deflation | 尚未运行；F family 关闭后的最后候选 |
| Matrix-free DtN | 不物化完整 C/D，逐通道执行 $D$、$H^{-1}$、$C$ | component pass；formal 80-mode qualification 待完成 |

---

# 2. 为什么当前 F0 不能单独证明整个 p-multigrid 失败

## 2.1 当前 F0 的 Galerkin correction

当前构造

```math
A_4=P_{46}^{H}A_6P_{46}
```

并求解

```math
A_4 y=P_{46}^{H}r,
\qquad
z_4=P_{46}y.
```

它保证 Petrov/Galerkin 条件

```math
P_{46}^{H}(r-A_6z_4)=0,
```

但不保证

```math
\lVert r-A_6z_4\rVert_2
<
\lVert r\rVert_2.
```

当前 Maxwell 局部算子为复数、非 Hermitian、不定且可能高度 non-normal，因此 Galerkin 正交并不等价于 residual 最小化。

## 2.2 当前 additive diagonal 可能过冲

当前 F0 将两个 correction 对同一个原始 residual 直接相加：

```math
z_F=z_4+D_6^{-1}r.
```

更标准的 multiplicative 形式应先更新 residual：

```math
z_D=D_6^{-1}r,
```

```math
r_D=r-A_6z_D,
```

```math
z=z_D+P_{46}A_4^{-1}P_{46}^{H}r_D.
```

因此当前 residual 放大可能来自 p4 空间缺乏容量，也可能来自 Galerkin test space或 additive 组合。V5 必须分离这三种原因。

## 2.3 p2 尚未进入当前 correction

当前代码虽然构造

```math
A_2=P_{24}^{H}A_4P_{24},
```

但 correction 没有调用 $A_2^{-1}$。所以当前 F0 不是完整三层 V-cycle。

不过，p2 空间满足嵌套关系

```math
\operatorname{range}(P_{46}P_{24})
\subseteq
\operatorname{range}(P_{46}).
```

因此，如果连完整 p4 trial space 在最优 minimum-residual 意义下都不能改善 B4，那么任何仅使用其子空间 p2 的三层实现都不可能弥补 trial-space 容量缺失。这是 V5 能够形成最终关闭结论的数学依据。

---

# 3. V5 唯一授权实验：F0b 理想 minimum-residual 容量上界

## 3.1 冻结输入

必须复用修复后 F0 的完全相同 fixture、slab、operator、shift、transfer 与 source：

```text
local p6 rows       = 432
p4 rows             = 192
p2 rows             = 48
source              = frozen low / high / mixed
B4 local steps      = 4
fine scalar         = complex128
PETSc IntType       = int32
p6 matrix/factor    = 0 / 0
thresholds          = unchanged
```

不得修改：

- low/high/mixed source 定义；
- B4 baseline；
- shift；
- p4/p2 degree；
- transfer；
- local step 数；
- Gate；
- residual norm。

只允许新增一个独立 oracle/test 文件，或在现有 capacity oracle 中增加不改变原 F0 输出的诊断函数。

## 3.2 必须计算的五个 correction

### F0b-1：diagonal only

```math
z_D=D_6^{-1}r.
```

记录

```math
\rho_D
=
\frac{\lVert r-A_6z_D\rVert_2}{\lVert r\rVert_2}.
```

### F0b-2：p4 Galerkin only

```math
z_G
=
P_{46}(P_{46}^{H}A_6P_{46})^{-1}P_{46}^{H}r.
```

记录 $\rho_G$，用于判断残差放大是否主要来自 p4 Galerkin 本身，还是来自 additive diagonal。

### F0b-3：multiplicative diagonal → p4 Galerkin

```math
z_D=D_6^{-1}r,
```

```math
r_D=r-A_6z_D,
```

```math
z_{DG}
=
z_D
+
P_{46}(P_{46}^{H}A_6P_{46})^{-1}P_{46}^{H}r_D.
```

记录 $\rho_{DG}$。

### F0b-4：p4 minimum-residual capacity

令

```math
Y_4=A_6P_{46}.
```

使用 rank-revealing QR 或 SVD 求

```math
y_{4,\mathrm{MR}}
=
\arg\min_y
\lVert r-Y_4y\rVert_2,
```

并定义

```math
z_{4,\mathrm{MR}}=P_{46}y_{4,\mathrm{MR}},
```

```math
\rho_{4,\mathrm{MR}}
=
\frac{\lVert r-A_6z_{4,\mathrm{MR}}\rVert_2}
{\lVert r\rVert_2}.
```

这是完整 p4 trial space能够达到的最佳 residual 下界。必须报告：

```text
rank(Y4)
condition / singular spectrum summary
least-squares residual
orthogonality ||Y4^H residual||
```

禁止使用 normal equations；必须使用 QR/SVD。

### F0b-5：B4 + p4 的联合最佳容量

必须提取实际 B4 四步 local GMRES 的搜索基 $K_4(r)$。令 $V_{B4}$ 为该次 Arnoldi/search basis，并构造

```math
Z_{\mathrm{aug}}
=
\begin{bmatrix}
V_{B4} & P_{46}
\end{bmatrix}.
```

再令

```math
Y_{\mathrm{aug}}=A_6Z_{\mathrm{aug}},
```

并通过 QR/SVD 求

```math
c_{\mathrm{aug}}
=
\arg\min_c
\lVert r-Y_{\mathrm{aug}}c\rVert_2.
```

定义

```math
\rho_{\mathrm{aug,MR}}
=
\frac{\lVert r-A_6Z_{\mathrm{aug}}c_{\mathrm{aug}}\rVert_2}
{\lVert r\rVert_2}.
```

这是“当前四步 factor-free p6 local Krylov + 任意完整 p4 correction”联合搜索空间的最佳残差上界。任何实际的 additive、multiplicative、Galerkin、Petrov 或 p4→p2 approximate V-cycle，在不增加新的 p6 搜索方向时，都不应被声称优于这个理想容量界。

---

# 4. 嵌套与实现 Gate

在评估科学结果前，必须再次确认：

```math
\frac{
\lVert P_{26}-P_{46}P_{24}\rVert
}{
\lVert P_{26}\rVert
}
\le 10^{-11}.
```

同时要求：

```text
P46/P24 adjoint identity          <= 1e-11
Y4 action identity                <= 1e-11
all QR/SVD solutions finite       = true
least-squares repeat error        <= 1e-12
p6 matrix/factor/NNZ              = 0 / 0 / 0
ordinary default                  = unchanged
```

若这些实现 Gate 失败，只能分类为 implementation failure，不得写成 p-multigrid 科学失败。

---

# 5. 最终科学关闭 Gate

对 low/high/mixed 三类 source，定义

```math
I_{4,\mathrm{MR}}
=
\frac{\rho_{B4}}{\rho_{4,\mathrm{MR}}},
```

```math
I_{\mathrm{aug,MR}}
=
\frac{\rho_{B4}}{\rho_{\mathrm{aug,MR}}}.
```

## 5.1 正式关闭条件

若 high 与 mixed 同时满足任一条件：

```text
I_aug,MR < 1.5
```

或

```text
rho_aug,MR >= 0.15
```

则记录：

```text
P6_P4_P2_FAMILY_CLOSED_ON_FROZEN_CAPACITY_ORACLE
```

并给出推理：

1. $Z_{\mathrm{aug}}$ 已包含当前 B4 的四步 p6 搜索方向；
2. $Z_{\mathrm{aug}}$ 还包含完整 p4 trial space，而不是 p4 的近似求解；
3. p2 trial space嵌套在 p4 内；
4. 因此任何仅用 p2 近似 p4 correction 的实际三层 V-cycle，不可能修复已经在理想完整 p4 trial space中不存在的容量；
5. 关闭结论适用于冻结 p6/h10 局部 slab、冻结 exact-sequence p4/p2 hierarchy、冻结 B4 四步 local family。

关闭后：

- 不开发 F1；
- 不测试 p3/p5；
- 不扫描 smoother、shift、steps、overlap；
- 不运行 MPI8 PDE；
- 不运行 MPI1；
- 不再使用“也许完整 p6→p4→p2 会成功”作为继续研发理由。

## 5.2 若理想容量通过

若 high 与 mixed 均满足：

```text
I_aug,MR >= 1.5
rho_aug,MR < 0.15
```

则不能声称 p6→p4→p2 已失败。此时只能记录：

```text
P4_TRIAL_SPACE_HAS_CAPACITY_CURRENT_GALERKIN_COMBINATION_FAILED
```

随后停止并等待新审阅，不得自动开发 F1。下一份审阅必须决定是否值得实现非 Hermitian Petrov coarse 或真正的 p4→p2 V-cycle。

这条分支是科学诚信要求；V5 的目的不是强行得到负结论，而是使负结论具有上界意义。

---

# 6. 执行与资源边界

本轮只允许 serial tiny/local oracle，不运行重型 PDE。

```text
maximum pytest runs       = 1 clean run
rerun after scientific fail = forbidden
MPI heavy screen          = forbidden
full solve                = forbidden
parameter tuning          = forbidden
```

需要报告：

- clean source SHA；
- exact command；
- low/high/mixed 的 B4、diagonal、Galerkin、multiplicative、p4-MR、augmented-MR residual；
- QR/SVD rank、condition 和 orthogonality；
- p4/p2 transfer inventory；
- p6 factor inventory；
- wall、MaxRSS、swap；
- raw artifact hash；
- measured/derived/not-run 字段区分。

完成后写：

```text
docs/task037_static_condensed_full3d_iterative/response_v5.md
benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_candidate_f_f0b_decisive_capacity_v1.json
```

然后停止等待审阅。

---

# 7. 其他路线的状态

## 7.1 Matrix-free DtN

formal 80-mode action/recovery identity仍值得完成，但不得与 F0b 同一数值提交混合。F0b 收口后可作为独立基础设施任务继续；它不会改变 p4 trial-space capacity 结论。

## 7.2 p4-core 部分凝聚

只保留一次来源定位：无 DtN、显式 block DtN、Matrix-free DtN。不得通过放宽 complement Gate继续重型 PDE。它与 Candidate F 的 p4 trace hierarchy不是同一个科学问题。

## 7.3 Candidate E：M120 modal-assisted coarse

只有当 V5 得到正式 family-closed 结论后，才允许进入最后一个 Candidate E。其目标是用 M120 左/右本征模消除 Full3D Krylov 的长程传播慢误差，而不是重新启动 direct Hybrid。

---

# 8. 公式渲染要求

本文件所有独立公式均使用 GitHub fenced math block：

````text
```math
...
```
````

后续 `response_v5.md` 也必须使用同一格式；禁止重新引入多行 `$$...$$`、`\[...\]` 或独占一行 `=` 导致的 Setext-heading 冲突。

---

# 9. 最终授权顺序

```text
V5-1  实现 F0b 五类 correction 和 QR/SVD oracle
V5-2  一个 clean serial run
V5-3  按理想容量 Gate给出 family closed 或 trial-space capacity pass
V5-4  写 compact record + response_v5.md
V5-5  停止
```

不得自动进入 Candidate E、Matrix-free DtN formal PDE、部分凝聚 heavy screen、Hybrid 或 0.7 nm。