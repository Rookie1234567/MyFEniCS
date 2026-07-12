# Exact DtN condensation：从增广矩阵到 matrix-free FE 算子

## 1. 文件与职责

主文件是 `src/solvers/condensed_dtn.py`。它不重新定义端口物理，而是把已经装配的 3D augmented PETSc system

```math
\begin{bmatrix}F&C\\D&H\end{bmatrix}
\begin{bmatrix}u\\a\end{bmatrix}
=\begin{bmatrix}b_F\\b_H\end{bmatrix}
```

精确改写为 FE-only condensed system，并在求解后恢复 auxiliary modal amplitudes。

## 2. 公开对象与签名

| 符号 | 签名/作用 |
|---|---|
| `PetscCondensedBlocks` | 拥有 `F,C,D,H,b_fe,b_aux,n_fe,n_aux` |
| `extract_petsc_condensed_blocks(A_aug,b_aug,n_fe,n_aux)` | 用全局 IS 拆 block |
| `SmallDenseInverse(H)` | 收集小 H 并显式构造 dense inverse |
| `create_matrix_free_condensed_operator(blocks)` | 返回 PETSc MatPython 与 context |
| `condensed_rhs(blocks)` | `b_F-C H^{-1}b_H` |
| `build_explicit_condensed_operator(blocks)` | 小规模 PETSc reference；仅 `H=I` |
| `recover_petsc_auxiliary(blocks,u_fe)` | `H^{-1}(b_H-Du)` |

## 3. 调用者与被调用者

`benchmarks.run_workstation_iterative::run` 调用 block extraction、matrix-free operator、RHS 和回代。Case022/tests 同时调用 dense reference 和 explicit PETSc reference。模块依赖 PETSc Mat/Vec、NumPy 和 MPI collectives，不依赖几何。

## 4. 对象尺寸：target h=5

| 对象 | 全局 shape |
|---|---:|
| `F` | 44,698 x 44,698 |
| `C` | 44,698 x 80 |
| `D` | 80 x 44,698 |
| `H` | 80 x 80 |
| augmented `A` | 44,778 x 44,778 |
| condensed `A_c` | 44,698 x 44,698 |
| `u` | 44,698 |
| `a` | 80 |

这些数字来自 canonical h5 iterative record；h3/h2 的 `n_fe` 增长，但当前 target 的 `n_aux` 仍由端口模态数决定。

## 5. Dense reference

`condense_dense_blocks(F,C,D,H,f,g)` 使用 `np.linalg.solve` 形成：

```python
H_inv_D = np.linalg.solve(H, D)
H_inv_g = np.linalg.solve(H, g)
A_c = F - C @ H_inv_D
b_c = f - C @ H_inv_g
```

它只用于小矩阵单测，不进入 MPI 大规模 runtime。

## 6. PETSc block extraction 与所有权

`extract_petsc_condensed_blocks` 用 `_distributed_split_is` 创建 FE/aux global index sets，再用 `createSubMatrix` 和向量 segment copy 生成独立 PETSc 对象。返回的 `PetscCondensedBlocks` 拥有这些 submatrices/vectors，调用者最终必须执行 `blocks.destroy()`。

## 7. `SmallDenseInverse` 的真实实现

当前代码不是 LU factor object。构造器执行：

```python
self.H_dense = gather_small_petsc_matrix(H)
self.condition_number = np.linalg.cond(self.H_dense)
self.H_inverse = np.linalg.inv(self.H_dense)
```

`solve/solve_transpose/solve_hermitian` 分别乘 `H_inverse`、转置和共轭转置。显式 inverse 对当前 80 x 80 小块可接受，但属于非阻断技术债；若 `n_aux` 大幅增长，应改为 factor/solve 接口。

## 8. Matrix-free action 与代码映射

理论：

```math
y=(F-CH^{-1}D)x.
```

`CondensedDtnMatContext::mult` 逐句对应：

```text
F.mult(x,y)             -> y=Fx
D.mult(x,d_work)        -> d=Dx
h_solver.solve(...)     -> h=H^{-1}d
C.mult(h,c_work)        -> c=Ch
y.axpy(-1,c_work)       -> y=Fx-c
```

`multTranspose` 与 `multHermitian` 分别保护转置和复共轭语义，不能互换。

## 9. RHS 与 auxiliary 回代

`condensed_rhs` 计算 `b_c=b_F-C H^{-1}b_H`。外层 KSP 得到 `u` 后，`recover_petsc_auxiliary` 计算：

```math
a=H^{-1}(b_H-Du).
```

这个 `a` 是 official modal R/T 的来源；只求 condensed FE 解而不回代，无法完成完整 augmented residual 和 official RTA。

## 10. Explicit PETSc reference 的限制

`build_explicit_condensed_operator` 当前先收集 `H` 并检查：

```python
np.allclose(H_dense, np.eye(n_aux), atol=1e-13)
```

只有已验证的 `H=I` 才执行 `F-C@D`。任意非单位 H 会抛 `NotImplementedError`。因此它不是任意 H 的通用分布式 Schur builder；一般 H 由 matrix-free action 正确处理。

## 11. 一次真实调用顺序

```text
RuntimeStage4System.A/b
-> extract_petsc_condensed_blocks
-> create_matrix_free_condensed_operator
-> condensed_rhs
-> outer FGMRES solves u
-> recover_petsc_auxiliary
-> combine [u,a]
-> full augmented residual on original A/b
-> official modal RTA
```

## 12. PETSc 生命周期

推荐销毁顺序：outer KSP/solution work -> Python matrix/context work Vec -> condensed RHS -> blocks -> original runtime system。MatPython context 不拥有 blocks；提前销毁 `F/C/D/H` 会使后续 action 崩溃。

## 13. 测试与 benchmark

- `src.test.test_22_condensed_dtn`：dense、PETSc、mult/transpose/Hermitian、RHS、回代、MPI。
- Case022：[`../../../benchmarks/cases/022_dtn_condensation_equivalence/README.md`](../../../benchmarks/cases/022_dtn_condensation_equivalence/README.md)。
- Case031：真实 h5/h3/h2 runtime。

## 14. 身份与限制

该模块是 stable algebraic infrastructure。它保持原 augmented 物理算子，不是近似预条件器；近似发生在求解 condensed system 的 PC。限制包括显式 inverse、explicit reference 的 `H=I` 和依赖当前 small auxiliary block。

理论推导见 [`../../theory/dtn_modal_ports_and_condensation.md`](../../theory/dtn_modal_ports_and_condensation.md)。
