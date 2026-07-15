# Task032 Phase 6d 单体增广直接法代数

## 1. 当前资格边界

`src/solvers/hybrid_fem_modal_augmented_direct.py` 首次把上下局部 FEM-DtN、内部模态 traction、
trace projection 和稳定传播装入一个 PETSc AIJ，并用 MUMPS `preonly + LU` 求解。

本步通过的是 h10、两条解析 Bloch 切向模式的代数 Gate。它证明 block shape、MPI ownership、
传播消元、右端拼接和直接求解残差正确；真实 patterned QEP basis、模式数收敛、接口 E/H 连续、
official R/T/A 与 full-3D h5/h3 对比仍未资格化。

## 2. unknown 和接口方程

单体未知量是：

```text
x = [u_bottom, u_top, a_b+, a_t-]
```

其中 `u_bottom/u_top` 已包含各自 40 个外部 Fourier-DtN auxiliary unknown。内部 outgoing amplitude
不作为独立 unknown，而由 Phase 4 的稳定传播得到：

```text
a_b- = P- a_t-
a_t+ = P+ a_b+
```

设负向迹到正向 canonical trace basis 的小矩阵为 `N-`，两个接口 E-trace 方程为：

```text
Q_b u_b - a_b+      - N- P- a_t- = 0
Q_t u_t - P+ a_b+   - N-    a_t- = 0
```

因此内部小块为：

```text
H_modal = [ -I    -N- P- ]
          [ -P+   -N-    ]
```

局部 FE 行的 modal traction 列分别为：

```text
C_bottom = [T_b+, T_b- P-]
C_top    = [T_t+ P+, T_t-]
```

最终仍是任务书中的三块结构，但内部 unknown 是 `2M`，没有伪 `4M` trace，也没有 growing inverse。

## 3. 为什么使用 rank-major ownership

bottom 和 top 是两个独立分布式 PETSc 矩阵。若直接按全局 `bottom -> top -> modal` 排列，单个 rank
会拥有两个不连续区间，不满足普通 MPI AIJ 的连续 ownership。`HybridAugmentedLayout` 因此采用：

```text
rank 0: bottom-owned, top-owned
rank 1: bottom-owned, top-owned
...
last rank: bottom-owned, top-owned, 2M modal
```

初始化时只 allgather 每个原矩阵的 ownership range。映射函数把原 bottom/top global index 转成
monolithic rank-major global index；矩阵逐 owned row 复制，所有目标行仍由当前 rank 拥有。
向量在每个 rank 的本地数组中按相同切片 pack/split，只 bcast `2M` 个小型 modal coefficients。

## 4. 对象与求解

`HybridAugmentedDirectSystem` 拥有 monolithic `A/b`，不接管 Phase 6b local systems 或 Phase 6c
coupling，避免 double destroy。`HybridAugmentedDirectSolution` 拥有 `x/KSP` 和拆出的 bottom/top
向量；两个 `destroy()` 都是幂等的。

求解路径固定为：

```text
PETSc KSP preonly
-> PC LU
-> MUMPS
-> explicit r = A*x-b
-> ||r||/||b||
-> split bottom/top/modal
```

KSP 设置 `error_if_not_converged`，不能只凭函数返回便声称成功。

## 5. 当前 Gate

```bash
python -m unittest -v src.test.test_39_task032_hybrid_augmented_direct
mpiexec -n 2 python -m unittest -v src.test.test_39_task032_hybrid_augmented_direct
mpiexec -n 4 python -m unittest -v src.test.test_39_task032_hybrid_augmented_direct
```

最终 serial、MPI2、MPI4 均为每 rank `3/3`。MPI4 轻量证据：

```text
matrix size = 2432 x 2432
matrix nnz = 251720
true relative residual = 3.732133e-13
MUMPS setup = 0.046960 s
MUMPS solve = 0.003048 s
```

测试还直接比较 monolithic modal-only action 与原始 `T+/T-/P+/P-/H_modal` 块作用，防止
“矩阵可解但列映射错误”。右端 pack/split、AIJ 类型、rank-local size 总和以及幂等释放也在同一
合同中覆盖。

## 6. 下一步

下一子步骤必须使用 Phase 3 真实正/反向 QEP basis，而不是解析测试 mode；随后逐步增加 M，报告
接口投影/连续性 residual、真实 Hybrid R/T/A 和 full-3D 差异。只有这些 Gate 通过，才能把
Phase 6 从 `algebra_pass` 升级为 `physical_augmented_direct_pass`。
