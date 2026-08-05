# Task037 Review Report V4：候选方法索引、当前结论与最后的有界路线

## 0. 审阅身份

```text
review                         = Task037 Review Report V4
reviewed_branch                = codex/20260803-task37-matrix-free-iterative-development
reviewed_response              = response_v3.md
reviewed_partial_outcome       = p4_core_partial_condensation_controlled_negative.md
reviewed_candidate_f_outcome   = candidate_f_f0_implementation_gate.md
ordinary_default               = unchanged
merge_to_master                = not authorized
Task037b Hybrid block solver   = not authorized
0.7 nm production PDE          = not authorized
```

本报告统一整理 Task037 中所有 candidate 的含义，并对最新三项结果作出区分：

1. p4-core 部分凝聚的核心代数已经通过，但 public DtN/recovery 接线仍有明确的 eliminated-complement 一致性缺口；
2. Candidate F 的 p6 → p4 → p2 容量实验尚未产生科学结果，只被一个 PETSc int32/int64 索引实现错误拦住；
3. Matrix-free DtN 的小型代数组件已通过，但正式 80-mode p6/h10 identity 尚未完成。

因此当前状态不是“所有新路线均已失败”，而是：

```text
M3a p6-slab ILU                    = 唯一完成 full numerical/physical pass 的迭代法
A/B2/B4/C/D                        = 已取得受控数值负结果
p4-core partial condensation       = 组件正结果；public integration 未通过
Candidate F p6->p4->p2             = implementation gate failed；科学 Gate 未运行
Matrix-free DtN                    = component pass；formal 80-mode qualification 未完成
Candidate E modal-assisted coarse  = 尚未运行
```

---

# 1. Candidate 名称与含义总表

> 注意：Task37 早期的 `F0/F1/F2...` 是开发阶段编号；Candidate F 内部的 `F0/F1` 是该候选自己的 oracle/solver 阶段。二者不是同一个编号体系。

| 名称 | 方法含义 | 是否保留 p6 因子 | 当前结果 | 后续状态 |
|---|---|---:|---|---|
| Direct authority | p6/h10 静态凝聚 + 全局 MUMPS direct | 全局 direct factor | 数值权威 | 只作参考 |
| M3a | 16 个重叠 p6 slab ILU(0) + 75D wave coarse + FGMRES | 是，91.4M NNZ | full pass；MPI1 4.60 GiB | 当前可用基线 |
| Candidate A | 全局 p2 auxiliary + p6 shifted diagonal pre/post | 否 | 100 步 residual 0.9625 | 关闭 |
| Candidate B2 | 每个 p6 slab 使用无预条件固定 2 步 local GMRES | 否 | 200 步 residual 0.2096 | 关闭 |
| Candidate B4 | B2 改为固定 4 步 local GMRES | 否 | 200 步 residual 0.1406 | 关闭，不增加裸步数 |
| Candidate C | B4 + one-hot RAS + 未正确定位的 interface shift | 否 | 200 步 residual 0.1489 | 当前实现关闭 |
| Candidate D | 每个 p6 slab 的 local Krylov 内加入局部 p2 auxiliary | 否 | high/mixed contraction 比 B4 更差 | 关闭 |
| R7 / p4-core partial | 每单元保留 108 个 p4-core interior modes，只消去 342 个高阶 complement modes | 研究路径 | 核心代数通过；public complement Gate 失败 | 只做一次定位诊断 |
| Candidate F | 局部 p6 → p4 → p2 exact-sequence p-multigrid | 正式目标为 p6/p4 factor-free，仅保留小 p2 factors | transfer 通过；capacity oracle 尚未运行 | 允许最小修复后重跑一次 F0 |
| Candidate E | 将 Task36 的 M120 左/右本征模作为 Full3D coarse/deflation space | 否 | not run | Candidate F 后的最后候选 |
| Matrix-free DtN | 不物化完整 C/D；逐通道施加 $D$、$H^{-1}$、$C$ | 不适用 | synthetic component pass | 必须完成 formal 80-mode qualification |

---

# 2. 当前可用基线：M3a

M3a 求解的是精确 p6/h10 静态凝聚方程。对第 $j$ 个 slab，局部矩阵近似分解为

$$
A_j \approx L_j U_j,
$$

并构造加权 Schwarz 预条件器

$$
M_{\mathrm{M3a}}^{-1} r
=
\sum_{j=1}^{16}
R_j^T W_j U_j^{-1}L_j^{-1}R_j r
+
Q_{75}r.
$$

它是当前唯一完成以下全部 Gate 的方法：

- reported、condensed、full-FE true residual；
- canonical active/full field；
- 12/12 powers、12/12 boundary amplitudes；
- R/T/A 与能量闭合；
- MPI1/2/4/8 跨 MPI identity；
- zero swap。

代价是长期保留

$$
91{,}415{,}952
$$

个 p6 局部 factor NNZ。MPI1 峰值仍为 4.600 GiB，因此 M3a 不能按当前形式机械扩展到 0.7 nm。

---

# 3. 已关闭的 factor-free 候选

## 3.1 Candidate A

Candidate A 使用

$$
M_A^{-1}
=
D_6^{-1}
+
P_{2\to6}A_2^{-1}P_{2\to6}^H
+
\text{post-diagonal correction}.
$$

100 步残差仍为 0.9625。结论：全局 p2 与对角修正无法覆盖 p6 静态凝聚系统的中高阶误差。禁止重新扫描 omega、shift 或 pre/post 次数。

## 3.2 Candidate B2/B4

每个 slab 不保存矩阵或因子，而以固定步数局部 Krylov 近似

$$
z_j \approx \operatorname{GMRES}_k(A_{6,j},r_j),
\qquad k=2,4.
$$

B4 是 factor-free 中最好的既有候选，但 200 步残差仍为 0.1406，后期进入平台。禁止继续测试裸 B6/B8/B12。

## 3.3 Candidate C

原计划只在人工 slab 接口施加 impedance shift，但实际 audit 得到

$$
N_{\mathrm{interface}}=N_{\mathrm{active}}=51{,}192.
$$

因此该实现没有真正分离人工接口；主要新增机制只是 one-hot RAS。它比 B4 更差。当前 C 关闭，但这不等于真正的几何 optimized Schwarz 已被理论否定。

## 3.4 Candidate D

Candidate D 试图在局部 p6 Krylov 中使用局部 p2 auxiliary：

$$
B_{2,j}^{-1}
=
P_j A_{2,j}^{-1}P_j^H
+
D_{6,j}^{-1}.
$$

其代数投影误差约为 $3.45\times10^{-16}$，p6 factor inventory 为零，但 high/mixed contraction improvement 分别只有 0.929 和 0.906，小于 1。该候选是数值负结果，不得重开调参。

---

# 4. p4-core 部分凝聚：组件成立，public integration 尚未闭合

完整 p6 单元局部空间为

$$
882=432\ \text{trace}+450\ \text{interior}.
$$

R7 路线保留 exact-sequence 嵌入的 108 个 p4-core interior modes，只消去 342 个 p5/p6 complement modes。局部、全局 retained action 与 compiled-form assembly-time 组件均达到 $10^{-14}$ 至 $10^{-15}$ 级一致性。

在真实 two-cell public DtN/recovery 测试中：

$$
\frac{\|r_{\mathrm{full}}\|}{\|b\|}
=4.27\times10^{-11},
$$

但 eliminated-complement norm 为

$$
5.00\times10^{-10},
$$

而 exact-equivalence Gate 为 $10^{-11}$，因此停止。

该结果应解释为：

```text
partial-condensation algebra         = positive
public DtN/recovery composition      = unresolved numerical mismatch
production/full PDE                  = not qualified
```

## 4.1 只允许一次来源定位

在完全相同的 tiny compiled fixture 中，依次比较：

1. 无 DtN 的 retained partial system；
2. 显式 block C/D/H DtN；
3. Matrix-free DtN。

三条路径必须使用同一个 exact solution/RHS 和相同 complement residual 定义。

分类规则：

- 无 DtN 已失败：问题在 retained RHS/recovery/partial elimination；
- 无 DtN 通过、显式与 matrix-free 均失败：问题在 shared public DtN adapter；
- 显式通过、matrix-free 失败：问题在 Matrix-free DtN composition；
- 三条都通过：修复后再审阅，不能自动进入重型 PDE。

禁止放宽 $10^{-11}$ Gate，也禁止直接启动 p6/h10 20-step screen。

---

# 5. Candidate F：允许最小 ABI 修复后重跑一次 F0

Candidate F 研究三层局部 p-multigrid：

$$
p6\rightarrow p4\rightarrow p2.
$$

真实 exact-sequence transfer 已经通过：

- $P_{24}\to P_{46}$ composition error：$3.51\times10^{-15}$；
- $P_{24}$ interpolation error：$8.33\times10^{-16}$；
- $P_{46}$ interpolation error：$6.60\times10^{-15}$；
- adjoint、orientation 与 Floquet identity 均通过。

真正的 p4 capacity oracle 尚未执行，失败原因只是

```text
numpy int64 index -> PETSc int32 getValues
```

即一个 ABI/实现 Gate，而不是方法的科学负结果。

## 5.1 唯一授权修复

只允许将相关索引显式转换为

```python
np.asarray(rows, dtype=PETSc.IntType)
```

并在 clean SHA 上重跑同一个 F0。禁止同时修改 source、threshold、shift、local steps 或 oracle 定义。

## 5.2 F0 科学 Gate

构造

$$
A_{4,j}=P_{46,j}^H A_{6,j}P_{46,j}
$$

并暂时用 exact complex128 p4 solve 测试空间容量。对与 Candidate D 相同的 low/high/mixed sources，计算

$$
\rho_j
=
\frac{\|r_j-A_{6,j}z_j\|}{\|r_j\|}.
$$

只有 high 与 mixed 相对 B4 的 improvement 都不小于 1.5，才允许开发正式 factor-free p6→p4→p2 V-cycle。

若 F0 数值 Gate 失败，记录

```text
P4_INTERMEDIATE_SPACE_NOT_EFFECTIVE
```

并关闭整个 p-multigrid candidate family；不得改成 p3/p5 或扫描更多层级。

---

# 6. Matrix-free DtN：必须完成正式 80-mode 资格化

当前小型 synthetic component 已验证

$$
A_{\mathrm{cond}}x
=
Fx-C H^{-1}Dx
$$

可以在不物化完整 $C/D$ 的情况下施加，且 auxiliary recovery 误差达到 $10^{-12}$ 量级。但还没有正式 80-mode p6/h10 identity。

下一步必须完成：

1. 使用冻结的 80 个 mode objects；
2. 对 deterministic random vectors 比较显式 block 与 matrix-free action；
3. 比较 auxiliary amplitude recovery；
4. 检查全部 mode keys、beta、polarization、Rayleigh flags；
5. serial、MPI2、MPI4 identity；
6. `explicit_C_count=0`、`explicit_D_count=0`；
7. $H^{-1}$ 使用逐通道 1×1/2×2 block action，不保留不必要的全 dense inverse replica；
8. 提供 adjoint/Hermitian-transpose action，为未来 Petrov/modal coarse 服务。

Gate：

$$
\frac{\|A_{\mathrm{MF}}x-A_{\mathrm{block}}x\|}
{\|A_{\mathrm{block}}x\|}
\le10^{-11}.
$$

该工作独立于 Candidate F 是否成功，必须完成，但不因它单独运行新的 full PDE。

---

# 7. Candidate E：最后一个候选——M120 modal-assisted Full3D PC

Task36 否定的是用 M120 作为完整 direct Hybrid 接口空间；它没有否定 M120 作为 Full3D coarse/deflation space。

保留右模态 $Z_m$ 和左/伴随模态 $W_m$，构造非 Hermitian coarse operator

$$
E_m=W_m^H A_6 Z_m,
$$

以及 correction

$$
Q_mr=Z_mE_m^{-1}W_m^H r.
$$

与最佳 factor-free/local PC 组合：

$$
M_E^{-1}r
=
M_0^{-1}r
+
Q_m\left(r-A_6M_0^{-1}r\right).
$$

其优势是：完整 p6 fine operator 与 Krylov space 始终保留，端部近场、traction complement 与 Task36 中 M120 遗漏的方向仍由 Full3D 空间修正；模态只消除长程传播慢误差。

Candidate E 仅在下列条件之一满足时启动：

- Candidate F 的 F0 科学 Gate 失败；
- Candidate F 通过但正式 F1 在 200 步仍不满足 Gate。

第一版只允许冻结 M120，不做 rank sweep，不加入 Task36 correctors。MPI8 Gate：

```text
20-step residual < best non-modal candidate
100-step residual <= 0.10
200-step residual <= 0.05
coarse rank full
coarse condition explicitly reported
additional peak <= 0.30 GiB
```

失败后停止，不再选模、扩 rank 或训练新 basis。

---

# 8. 下一步执行顺序

```text
V4-1  修复并重跑 Candidate F F0 的 PETSc.IntType implementation Gate

V4-2  完成 p4-core partial condensation 的三路 complement 来源定位

V4-3  完成正式 80-mode Matrix-free DtN action/recovery/adjoint identity

V4-4  若 Candidate F F0 通过：只实现一个冻结 F1 p6->p4->p2 V-cycle，
      运行 MPI8 20/100/200 漏斗

V4-5  若 F0 或 F1 失败：启动一次 Candidate E M120 modal-assisted coarse

V4-6  写 response_v4.md，提交 compact evidence，并停止
```

禁止事项：

- 不重开 A/B2/B4/C/D；
- 不增加裸 local Krylov steps；
- 不放宽 partial complement Gate；
- 不扫描 p3/p5、modal rank、overlap、slab 数或 shift；
- 不启动 Hybrid block solver、0.7 nm PDE 或 surrogate；
- 不改变 ordinary defaults。

---

# 9. 文档数学公式渲染规范

GitHub Markdown 的正式数学格式统一为：

- 行内公式：`$...$`；
- 独立公式块：上下各一行 `$$`；
- 禁止在普通 Markdown 正文中继续使用 `\(...\)` 与 `\[...\]`；
- fenced code block 内的反斜杠示例保持原样；
- 所有 Task37 与 Case100 Markdown 文档必须通过自动检查，不得残留正文中的旧 delimiter。

本审阅同时提供 `scripts/fix_task37_markdown_math.py`，用于一次性修复和 `--check` 验证。批量修复必须作为独立 docs-only commit 执行，不得与数值源码改动混在同一提交中。
