# Task037 Review Report V1：数值核心通过、资源目标未通过与极限低内存路线

## 0. 审阅身份

```text
review                         = Task037 Review Report V1
reviewed_branch                = codex/20260803-task37-matrix-free-iterative-development
base_master_sha                = f8fab5e12a4cc33cd60dc96d40f628caca446b58
branch_ahead_before_review     = 28 commits
reviewed_response              = docs/task037_static_condensed_full3d_iterative/response_v0.md
reviewed_response_parent       = 3abe278600aac6c63d81e876f9198e976c5505e9
F0_direct_source               = 03f4fa02aece62bb2f193c01616177bffff0aa51
F3_assembled_source            = 00ae05df1553ff672b76ffa0199856747f39372c
F5b_matrix_free_source         = 690458b473dda23d0603ea277df695fae5b6906c
ordinary_default               = unchanged
merge_to_master                = not authorized by this review
Task037b                       = not authorized by this review
```

本审阅覆盖：

- `outcomes/summary.md`；
- `outcomes/assembled_fgmres_full.md`；
- `outcomes/matrix_free_report.md`；
- `outcomes/resource_and_mpi_report.md`；
- `outcomes/test_summary.md`；
- `response_v0.md`；
- F0、F3、F5b tracked records；
- `static_condensed_iterative.py`；
- `static_local_schur_action.py`；
- `physical_slab_two_level.py`；
- 与 external linear-solver port、静态凝聚、DtN Schur、恢复和 watchdog 直接相关的修改。

最终审阅结论为：

```text
static-condensed Full3D iterative algebra       = PASS on the frozen case
right-FGMRES two-level solver                    = PASS on the frozen case
cell-local Schur fine action                     = PASS algebraically
R/T/A and 12+12 channel observables              = PASS
raw ownership-order vector comparison            = comparator contract failure / unresolved
resource objective                               = FAIL
MPI4/8 final identity                            = not demonstrated
full repository suite after final fixes          = not rerun
production qualification                         = NO
whole-branch merge recommendation                = NO
```

Task037 不能概括为“迭代法失败”。更准确的结论是：

> **精确静态凝聚算子、FGMRES、两层预条件器和 cell-local Schur action 已经在冻结的 p6/h10 Full3D 案例上给出了正确的物理解；但当前 setup 和预条件器仍然是 matrix-materialized、factor-heavy 的，因此没有实现显著的增量内存节省。**

---

## 1. 证据判定

## 1.1 F0 direct authority：接受

当前源码的 p6/h10、13.5 nm、10° 掠射、`phi=0`、S 偏振、MPI8、assembly-time static-condensed direct authority 为：

```text
full FE DoFs                    = 173802
full trace rows                 = 60402
independent active trace rows   = 51192
auxiliary rows                  = 80
augmented rows                  = 51272
matrix nnz                      = 41989040
MUMPS factor nnz                = 209772680
full true residual              = 2.8094057923e-11
process-tree peak               = 15.2550010681 GiB
wall                            = 370.18 s
12 significant powers          = 12/12 pass
12 boundary amplitudes          = 12/12 pass
R/T/A and energy closure        = pass
swap                            = 0
```

该运行可以作为 Task037 后续同一离散、同一物理的 direct authority。

需要注意，Task037 的当前 direct peak 为 `15.255 GiB`，而历史 Case096 为约 `14.722 GiB`。二者差异约 3.62%，不影响数值 authority，但所有 Task037 资源百分比必须绑定当前 F0，而不能挑选更有利的历史峰值。

## 1.2 F3 assembled FGMRES：数值通过、资源不通过

F3 使用：

```text
fine operator                   = assembled static-condensed F
DtN treatment                   = exact H inverse in F-C H^-1 D
outer                           = right FGMRES
residual norm                   = unpreconditioned original residual norm
restart                         = 90
rtol                            = 1e-6
physical slabs                  = 16
slab overlap                    = 0.25
local shift                     = -i 0.1 |diag(F)|
local factor                    = COMM_SELF ILU(0), factor-only
inner smoother                  = two-step GMRES
coarse                          = 75D Floquet z-hat basis
coarse solve                    = dense exact LU
pre/post                        = 2-step smoothing + coarse + 2-step smoothing
```

结果：

```text
iterations                      = 337
reported residual               = 9.8166144382e-7
condensed true residual         = 9.8166144376e-7
full augmented true residual    = 9.8166144376e-7
full FE residual                = 9.8166147334e-7
12+12 channels                  = pass
R/T/A                           = pass
process-tree peak               = 13.6522331238 GiB
wall                            = 410.546 s
```

因此，F3 已经证明：

1. p6 static trace system 可以由当前两层 FGMRES 求解；
2. reported residual 与三个显式 residual 一致；
3. 预条件器没有改变物理解；
4. 取消 global MUMPS factor 后仍可恢复 auxiliary、完整 FE 场和全部 official observables。

但其资源只比 F0 direct 低约 10.5%，高于 `10.30 GiB` Gate，不能称为低内存成功。

## 1.3 F5b released matrix-free：action 通过、whole-job memory 不通过

F5b 的正式身份是：

```text
assembled_setup_then_static_local_schur_matrix_free_solve
```

它不是 `never-materialized`。流程为：

1. 形成全局 augmented matrix 和 fine `F`；
2. 从 `F` 建立 16 个 slab submatrices/ILU factors；
3. 由 exact fine action构造 75D coarse operator；
4. 资格化 cell-local Schur action；
5. 在 outer KSP 前释放 `F` 和 augmented matrix；
6. solve 中使用 cell-local Schur action。

其 fine-action 相对误差：

```text
9.2309237020e-16
```

F5b 与 F3：

```text
iterations                      = 337 / 337
active trace relative difference= 1.5478270800e-14
full FE relative difference     = 1.4162962151e-14
R/T/A                           = record precision identical
12+12 channels                  = identical pass
```

因此，F5b 的 matrix-free fine action 是可信的。

但：

```text
F3 peak                         = 13.6522331238 GiB
F5b peak                        = 13.6580085754 GiB
```

F5b 没有降低 whole-job peak，因为 global matrix 被释放前，setup high-water 已经发生；后续释放只能降低 current RSS，不能降低历史最大值。

---

## 2. 对 raw-vector Gate 的重新判定

## 2.1 当前 raw indexwise 比较不能作为物理向量 authority

当前记录给出：

```text
F3 vs F0 active raw L2          = 1.4210359558
F3 vs F0 full FE raw L2         = 1.4121310623
F5b vs F0 same
```

若这些数字真代表同一物理 basis 中同一坐标顺序的向量差，那么 R/T/A、固定物理采样和 F3/F5b action 不可能同时达到当前一致水平。

现有证据反而显示：

- F3 与 F5b ownership-order vectors 在 `1e-14` 水平一致；
- F3/F5b 与 F0 的向量范数比约为 1；
- magnitude-sorted 差约为 `1e-6`；
- 固定物理采样的 E/H/E_t/H_t 差约为 `3e-7–1.2e-6`；
- 所有显著衍射功率和复振幅通过；
- F1 将 F0 raw active vector直接解释为当前 trace coordinates 时，explicit residual 约为 `3029.7`，表明二者不是同一坐标身份。

因此，本审阅将该项重新分类为：

```text
NONCANONICAL_RAW_VECTOR_COMPARATOR_FAILURE
```

而不是：

```text
ITERATIVE_PHYSICAL_SOLUTION_FAILURE
```

这不等于向量 Gate 已通过。Task037 仍缺少一个真正 canonical 的 vector comparator。

## 2.2 必须建立的 canonical comparator

active trace 应按物理实体键比较，而不是按 PETSc ownership-order bytes 比较。建议 key 至少包含：

```text
entity dimension
canonical physical edge/face identity
local entity basis index
Basix orientation state
Floquet master identity and coefficient
component / trace role
```

推荐比较流程：

1. 将 active coordinates 通过 `TraceConstraintMap` 展开到完整 original trace；
2. 对 edge/face orientation 做 canonical transform；
3. 按 physical entity key排序；
4. 比较 canonical trace coefficients；
5. 通过 cell recovery 得到 full FE canonical entity coefficients；
6. 同时计算物理质量范数和 H(curl) 范数，而不只比较字节。

正式 Gate建议为：

```text
canonical active-trace relative L2     <= 1e-5
canonical full-FE relative L2          <= 1e-5
relative tangential trace mass norm    <= 1e-5
relative H(curl) field norm            <= 1e-5
fixed physical samples                 <= existing tolerance
```

在 comparator 修复前，不应因为 raw byte mismatch否定已经通过的物理求解；也不能删除该失败后直接宣布向量完全一致。

---

## 3. 为什么没有继续节约一半内存

## 3.1 静态凝聚已经取得了第一轮大收益

历史 standard p6 direct 约为：

```text
34.041 GiB
```

当前 static direct 为：

```text
15.255 GiB
```

静态凝聚本身已经节约约：

```text
55.2%
```

F5b 相对 standard direct 总体约节约：

```text
59.9%
```

因此，“相对最原始 Full3D 已节约约一半”仍然成立。Task037 未实现的是：

> **在已经高度优化的 static direct 基线上，再额外节约 30–50%。**

## 3.2 当前预条件器仍保留约半个 global factor 的局部 factors

F0 global MUMPS factor：

```text
209772680 nnz
```

F3/F5b 16 个 ILU(0) factors aggregate：

```text
103336560 stored factor nnz
```

约为 global factor NNZ 的：

```text
49.3%
```

CSR payload 估计已约：

```text
2067298912 bytes
```

这还没有包括 PETSc factor对象、顺序向量、scatter、Python对象、allocator overhead 和临时 submatrix。

当前方法并不是 factor-free，而是：

```text
one global MUMPS factor
    -> sixteen overlapping local ILU factors
```

## 3.3 overlap 导致局部行重复约 2.77 倍

16 个 slab 的累计 row count 为：

```text
14 * 8424 + 2 * 11988 = 141912
```

相对 51192 个独立 active rows：

```text
141912 / 51192 = 2.772
```

重叠是当前收敛机制的一部分，但它使很多全局行同时存在于多个 local matrix 和 factor 中。

## 3.4 setup 中存在多套大对象重叠

`static_condensed_iterative.py` 的当前顺序是：

```text
request.A still live
extract F/C/D/H
create local-Schur action
build 75D coarse basis/operator
extract slab submatrices
build sixteen ILU factors
then release blocks.F and request.A
```

因此 setup 某一时刻可能同时存在：

- augmented `A`；
- extracted fine `F`；
- C/D/H blocks；
- local slab submatrices或其 setup workspace；
- 16 个 ILU factors；
- retained static local Schur/recovery data；
- 75D basis和 coarse work；
- mesh、V、MPC、DtN 与 field objects。

这正是 released matrix-free 与 assembled 路径峰值几乎相同的根因。

## 3.5 matrix-free 只改变 solve action，没有改变 setup high-water

F5b 的关键 RSS 为：

```text
assembly                    = 6998.43 MiB
augmented finalized         = 13359.16 MiB
after field output          = 13985.80 MiB
```

outer KSP 前释放 `F`，不能抹去已经达到的约 13 GiB setup峰值。

## 3.6 full-field recovery 和输出又增加约 0.6 GiB

从 `augmented finalized` 到 `after field output` 增加约：

```text
626.6 MiB
```

当前 official output 同时恢复完整 173802-entry FE 场、计算场诊断、吸收和输出数组。对于只需要 R/T/A 和衍射通道的生产运行，这部分可以流式化。

## 3.7 MPI8 和 replicated metadata 仍有扩展风险

当前代码中存在：

- full diagonal shift通过 `allgather` 在每个 rank复制；
- complete subdomain row sets在各 rank复现；
- Python/PETSc/DOLFINx runtime按 rank复制；
- coarse和局部 factor管理包含多个 host-side结构。

这些对象在 51k rows 时不是最大项，但在 0.7 nm 大规模中会成为不可接受的 `O(N * nrank)` 复制。

---

## 4. 当前代码的可保留成果

以下能力值得保留：

1. default-off external linear solver port；
2. exact DtN Schur action与 auxiliary recovery；
3. trace-aware physical slab partition；
4. right-FGMRES合法性与三/四残差监控；
5. two-level PC抽象；
6. active-trace 75D Floquet basis；
7. cell-local static Schur fine action；
8. no-global-direct-factor inventory；
9. 未收敛时 official RTA fail-closed；
10. watchdog、zero-swap和 process-tree memory authority。

但不建议原样合入整个 Task037 分支，原因包括：

- resource目标未通过；
- canonical vector comparator 未完成；
- formal full solve只做 MPI8；
- full suite在最终 targeted fixes后没有重新运行；
- 当前 matrix-free profile仍依赖 global matrix完成 setup；
- runner和证据代码改动较大，需要选择性审阅。

---

# 5. 极限低内存的总体原则

要同时保证精度和低内存，最重要的原则是：


a. **精确 fine operator 保持 complex128；**

b. **预条件器可以近似、低阶、低精度或局部化；**

c. **外层 FGMRES 始终针对精确 fine operator计算 true residual；**

d. **只有 full residual 和物理 Gate 通过才输出 official result。**

数学上，预条件器只改变收敛路径：

$$
A M_k^{-1} y = b,\qquad x=M_k^{-1}y.
$$

只要每一步 `A*x` 使用精确 p6 operator，最终检查：

$$
\frac{\|Ax-b\|}{\|b\|}
$$

并达到冻结 Gate，那么 low-order、mixed-precision 或 approximate PC 不会把最终方程偷偷换成另一个物理模型。

因此，极限省内存不应通过以下方式实现：

- 降低 fine p6 离散；
- 减少 DtN modes；
- 放宽 residual；
- 修改材料吸收来让原问题更容易；
- 使用近似 operator生成 official R/T/A；
- 未收敛时输出结果。

应当只压缩：

- operator的存储方式；
- preconditioner的精度与空间；
- setup对象重叠；
- Krylov和后处理临时对象。

---

# 6. 极限低内存路线

## M0：先完成峰值归因，不再盲调 restart

下一步首先应细化 lifecycle timeline。至少在以下事件采样 process-tree RSS/PSS/USS，并记录 live object ledger：

```text
mesh built
V/MPC built
local static tensors/recovery ready
base active RHS ready
global active F allocated
global augmented A finalized
F/C/D/H extracted
local-Schur action ready
one slab submatrix allocated
one slab factor ready
all slab factors ready
75D basis ready
coarse operator ready
F released
A released
outer KSP setup
outer KSP solved
full residual complete
solver/PC released
field recovery complete
RTA complete
```

当前 `augmented finalized` 标签不足以区分：

- A/F duplicate；
- local factor setup；
- retained local Schur；
- PETSc allocator high-water。

在没有对象级归因前，不应把全部 6 GiB 差值归因给一个 matrix。

## M1：真正 no-global-A / no-global-F setup

这是最优先的结构改动。

需要从 assembly-time condensation直接输出：

```text
TraceConstraintMap
cell class local Schur actions
cell-to-active support
active RHS
interior recovery metadata
DtN C/D/H actions
```

而不创建全局 active `F` 和 augmented `A`。

fine action直接为：

$$
F x = \sum_K C_K^H S_K C_K x.
$$

DtN仍使用：

$$
Sx = Fx-C H^{-1}Dx.
$$

### M1 的关键实现

1. 为 `AssemblyTimeCondensedSystem` 增加 action-only identity，而不是强制持有 `matrix`；
2. active RHS由 cell-local condensation contribution直接 scatter-add；
3. C/D/H单独、稀疏、流式构造；
4. coarse matrix通过 matrix-free action形成：
   $$A_c=R_c^H S R_c;$$
5. 不创建 augmented AIJ 作为 intermediate；
6. action资格化仍对比当前 assembled F0/F3 oracle。

### M1 预期

M1 的合理第一目标是：

```text
whole-job peak <= 10.30 GiB
```

即先达到 Task037 原 resource-positive Gate。仅移除 global matrix 不保证直接达到 7.5 GiB，因为 local ILU factors仍然很大。

## M2：不从 global F 提取 slab matrices，直接组装 owner-local subdomain matrices

当前 local factors依赖：

```text
global F -> createSubMatrices -> local factors
```

真正 scalable 的做法是，对每个 slab owner直接累计：

$$
A_i = R_i F R_i^T
    = \sum_K R_i C_K^H S_K C_K R_i^T.
$$

实现要求：

- 一个 cell contribution可以发送到所有覆盖它的 slab owner；
- owner只保存自己负责的 subdomain matrix；
- 顺序构造、factor、释放临时 matrix；
- 不在每个 rank复制全部 slab row arrays；
- 不保存完整 global diagonal shift；只 scatter当前 owner需要的 diagonal entries；
- 因 overlap导致的重复是预条件器定义的一部分，不能漏算或多算 cell contribution。

M2 可以消除 global matrix与 local factor setup同时驻留，是降低 peak 而不仅是 current RSS 的必要条件。

## M3：降低 p6 overlapping-factor 内存

当前 103M factor NNZ 是下一大项。

### M3a：有界测试 overlap 0.125 / RAS

历史 p2 结果表明 overlap 0.125 可以降低 factor存储，但会增加迭代数。p6只能做一个有界比较：

```text
16 slabs / overlap 0.25 / basic AS
16 slabs / overlap 0.125 / restricted or partition-weighted AS
```

必须比较：

```text
factor nnz
peak RSS
20/100/200-step decline
full iterations
wall
```

不能只展示 factor变小，也不能只展示 residual下降。

### M3b：复用 exact duplicate factors

当前 16 factors 中只有 2 个 exact duplicates、14 个 unique classes。允许复用 exact fingerprint完全相同的 factor和局部矩阵，但预期收益有限；禁止近似共享不同 factors来换内存。

### M3c：顺序 factor setup

每个 owner按：

```text
assemble one subdomain
factor it
retain factor-only
release matrix/workspace
next subdomain
```

执行，避免多个 submatrices和 factor setup workspace同时存活。

## M4：将预条件器从 p6 ILU 转移到低阶 exact-sequence 空间

这是实现 50% 增量节省最有希望的步骤。

保持 fine solve：

```text
p6/h10 exact static-condensed operator
```

预条件器改为：

$$
M^{-1}
=
M_{\mathrm{high\text{-}order\ patch}}^{-1}
+
P_{2\to6} A_2^{-1} P_{2\to6}^H
+
R_w A_w^{-1}R_w^H.
$$

其中：

- `P_{2->6}`：H(curl)-一致、Floquet/方向正确的 p2-to-p6 active-trace transfer；
- `A2`：同一网格、同一物理的 shifted p2 H(curl) auxiliary operator；
- `M_high-order patch`：只平滑 p6高阶 complement，可用 element/face patch block Jacobi或小块 Schwarz；
- `Rw`：现有 75D wave coarse，捕捉 grazing propagation慢误差。

这不是降低最终精度。p2只存在于 PC，最终 residual仍由 p6 exact operator计算。

### M4 Gate

- transfer orientation/Floquet/adjoint error `<=1e-11`；
- exact-sequence/gradient compatibility明确；
- p2 coarse action为真实：
  $$A_2=P^HSP;$$
- p6 true residual通过；
- 12+12 channels通过；
- 不形成 p6 local ILU factors，或将其限制为小型 high-order patches；
- coarse和patch对象的完整 memory ledger。

若 M4 成功，目标应为：

```text
whole-job peak <= 7.6 GiB
```

即相对当前 F0 static direct至少节约约 50%。

## M5：mixed-precision 只用于预条件器

更激进但仍可保持最终精度的方案是：

```text
fine operator / solution / residual   = complex128
DtN H and official postprocess        = complex128
coarse critical solve                 = complex128
local approximate factors/patch data  = complex64 candidate
```

outer继续使用 FGMRES，并在 complex128 exact operator下监控 true residual。

这可将 local factor数值存储近似减半，但必须满足：

- 无 NaN/Inf；
- residual不因低精度停滞；
- exact complex128 residual达到 Gate；
- R/T/A和全部通道不变；
- mixed-precision只作为 PC，不得替代 fine action。

当前 PETSc build为 complex128，mixed local factors可能需要独立 owner-local实现。该项应排在 no-global-F 和低阶辅助空间之后，不应先开发。

## M6：流式 full residual、吸收和场恢复

对于 production R/T/A运行，不需要同时常驻完整 E、H、curl、real/imag/abs 和可视化 copies。

建议：

1. active trace解保持；
2. 按 cell或cell class恢复 interior field；
3. 立即累计：
   - full residual；
   - volume absorption；
   - 指定 sample/切片；
4. 用完即释放该 cell/block；
5. R/T直接从 auxiliary amplitudes计算；
6. 默认不输出全域场；
7. 如需全场，保存 active solution checkpoint，在独立 postprocess运行恢复。

当前这项至少可能消除约 0.6 GiB 的 solver/output overlap；在未来大模型中收益更大。

## M7：移除 rank-replicated O(N) metadata

当前实现中以下模式必须在大规模前消除：

```text
allgather full diagonal shift to every rank
replicate every complete subdomain index array
replicate global adjacency/support metadata
```

改为：

- owner-local subdomain metadata；
- PETSc VecScatter/neighbor communication；
- 只发送 owner需要的 rows；
- 全局只保留标量 audit和hash；
- 负载平衡依据 local factor rows/nnz，而不只依据 row count。

当前 p6/h10 应正式比较 MPI4 与 MPI8。MPI4可能降低进程运行时复制，但可能增加单-rank factor workspace；只能以 process-tree peak和wall实测决定。

## M8：Krylov 存储优化放在最后

当前 51192 rows 下，FGMRES(90) 的向量 payload不是主要内存来源，因此不应优先把 restart从90降到20并牺牲收敛。

但面向0.7 nm，FGMRES会同时保存 Arnoldi basis和preconditioned basis。预条件器成熟后可比较：

```text
FGMRES restart 90
FGMRES restart 40/50 + retained coarse/deflation
fixed linear PC + GMRES/GCRODR candidate
```

任何非 FGMRES路径必须先证明 PC线性和确定性。不能仅为了少存向量切换到不适合 variable PC 的 GMRES、TFQMR或BiCGStab。

---

# 7. 量化目标与现实预期

以当前 F0 `15.255 GiB` 为基线：

| 阶段 | 主要技术 | 建议峰值目标 | 评价 |
|---|---|---:|---|
| 当前 F5b | released matrix-free solve + p6 slab ILU | 13.658 GiB | 数值通过，资源负结果 |
| Level 1 | no-global-A/F + owner-local sequential setup | `<=10.30 GiB` | 应作为下一项最低成功线 |
| Level 2 | Level 1 + overlap/RAS +低阶 auxiliary PC | `<=7.6 GiB` | 相对 static direct约50%节省，具有工程意义 |
| Level 3 | Level 2 + streamed recovery + distributed metadata | `5–6.5 GiB` | 激进但有物理依据 |
| Stretch | mixed-precision PC + factor-free high-order patches | `<=4–5 GiB` | 尚无证据，不得承诺 |

需要明确：

- `<=7.6 GiB` 是有条件、但合理的中期目标；
- `5 GiB` 需要同时改变 global setup 和 p6 factor-heavy PC；
- `4 GiB` 目前只能作为 stretch；
- 仅释放 fine matrix或降低 restart不可能从13.7 GiB直接降到4 GiB。

---

# 8. 每一项内存优化必须通过的正确性阶梯

## 8.1 Fine operator Gate

对至少三个确定性复向量和一个随机种子，检查：

$$
\frac{\|A_{candidate}x-A_{assembled}x\|}
{\|A_{assembled}x\|}
\le 10^{-11}.
$$

范围包括：

- local static Schur；
- Floquet constraints；
- DtN condensed action；
- serial/MPI2/MPI4；
- final MPI8 anchor。

## 8.2 Preconditioner Gate

预条件器允许近似，但必须报告：

- finite/deterministic action；
- 若使用普通 GMRES，则 linearity `<=1e-11`；
- FGMRES下允许 variable PC，但必须固定最大inner work；
- local/coarse factor inventory；
- no hidden global direct fallback。

## 8.3 Solver Gate

开发阶段：

```text
reported residual                <= 1e-6
condensed true residual          <= 1e-6
full augmented true residual     <= 1e-6
full FE residual                 <= 1e-6
```

最终 p6/h10 qualification建议再运行一次：

```text
all four residuals               <= 1e-8
```

用以确认弱通道对 solver tolerance有足够裕量。不得在每个screen都强制1e-8，避免无谓成本。

## 8.4 Canonical field Gate

用第2节的新 comparator：

```text
canonical active trace           <= 1e-5
canonical full FE                <= 1e-5
H(curl)/trace mass norms         <= 1e-5
```

禁止继续以跨运行 ownership-order bytes作为物理 authority。

## 8.5 Physical Gate

- 12/12 significant powers；
- 12/12 outgoing boundary amplitudes；
- R/T/A；
- volume absorption；
- energy closure；
- fixed physical E/H samples；
- zero swap。

未收敛或任一正式 residual失败：

```text
official R/T/A = not_run
```

## 8.6 Resource Gate

- external process-tree RSS authority；
- simultaneous PSS/USS；
- zero swap；
- setup和solve分别采样；
- release后current下降不能冒充peak下降；
- memory对比绑定同一MPI和当前F0 source。

---

# 9. 测试与代码审阅意见

## 9.1 Full suite 尚未闭合

记录为：

```text
828 passed, 42 skipped, 2 failed
```

后续 targeted tests修复了两个旧合同，但没有在最终 source上重跑完整 suite。因此：

```text
final_full_suite = not_verified
```

这阻止 whole-branch merge建议。

## 9.2 Formal MPI identity 尚未完成

F5a action components覆盖 serial/MPI2/MPI4；F3/F5b正式 full solve只有MPI8。Task037原要求的MPI4/8 final identity未完成。

## 9.3 Python local-Schur loop不是0.7 nm最终kernel

`static_local_schur_action.py` 当前按 cell在Python层循环并执行 SciPy sparse expansion与dense local Schur乘法。它适合作为正确性实现和p6/h10 anchor，但面向0.7 nm需要：

- compiled/C++/Numba-like kernel或FFCx级action；
- batch by cell class；
- vectorized sum-factorization或block action；
- owner/ghost通信与计算重叠。

不得因为当前wall与direct接近，就直接外推其大规模吞吐。

## 9.4 当前 global metadata模式不具大规模资格

`allgather` full shift、replicated subdomains和host-side全局列表在当前规模可接受，但应明确标注：

```text
not 0.7nm scalable
```

---

# 10. 审阅决策

## 10.1 接受的结论

```text
F0 current-source direct authority             = accepted
F3 p6 static two-level FGMRES numerical solve  = accepted on frozen case
F5a/F5b cell-local fine action                 = accepted algebraically
F5b physical observables                       = accepted on frozen case
```

## 10.2 不接受的结论

```text
Task037 low-memory objective                    = not achieved
F5b whole-job matrix-free                       = false; setup materializes A/F
raw vector means physical failure              = not supported
MPI-independent final solver qualification      = not demonstrated
0.7 nm scalability                              = not demonstrated
production qualification                        = not demonstrated
```

## 10.3 最终分类

本审阅将 Task037 状态写为：

```text
NUMERICAL_CORE_PASS_RESOURCE_ARCHITECTURE_NEGATIVE
```

它比 `PARTIAL_WITH_CONTROLLED_NEGATIVES` 更具体，但不改变不允许合入 production 的结论。

## 10.4 Merge 与后续边界

当前不授权 whole-branch merge，也不授权直接开始 Task037b。

若用户继续低内存 Full3D，下一受控工作应优先为：

```text
1. canonical vector comparator
2. peak object attribution
3. never-materialized global A/F
4. owner-local sequential slab setup
5. p2 exact-sequence auxiliary PC
```

完成其中前两项前，不应开始新的重型 full solve；完成 no-global setup与预条件器screen后，最多再授权一个正式 p6/h10 full run。

如果用户选择先进入 Hybrid iterative，也必须诚实承认：

> 当前 Full3D iterative infrastructure在数值上可迁移，但其 factor-heavy setup尚未解决；直接迁移会继承同类内存瓶颈，只是 Hybrid endcap规模较小，不能代替通用低内存架构。

---

# 11. 一句话总结

> Task037 已经证明“静态凝聚 p6 Full3D 可以用两层 FGMRES 正确求解”，但尚未证明“当前实现是低内存求解器”。要在不牺牲结果正确性的前提下做到极限省内存，必须保持 complex128 exact fine operator和严格 true-residual/RTA Gate，同时把全局矩阵、p6重叠ILU、复制型metadata和全场后处理从峰值生命周期中移除；最有希望的最终结构是 **never-materialized p6 fine action + low-order exact-sequence auxiliary preconditioner + small high-order patch smoother + wave coarse + streamed recovery**。