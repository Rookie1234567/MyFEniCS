# 精确 DtN 凝聚代码

## dense reference

`condense_dense_blocks(F,C,D,H,f,g)` 用 NumPy 直接形成 `F-C solve(H,D)` 与 RHS；`recover_dense_auxiliary` 回代。它是单测参考，不用于大规模 MPI。

## PETSc block extraction

`extract_petsc_condensed_blocks` 按全局 `n_fe/n_aux` 创建 IS，并提取 F/C/D/H 与 f/g。`PetscCondensedBlocks` 明确拥有这些 submatrix/subvector，`destroy()` 统一释放。

H 由 `gather_small_petsc_matrix` 收集为每 rank 可用的小 dense array；`SmallDenseInverse` 预分解/求解 H 和需要的转置形式。

## matrix-free operator

`CondensedDtnMatContext` 保存 blocks、H inverse 和工作向量。`mult` 执行：

```text
work_aux = D*x
work_aux = H^-1*work_aux
y = F*x - C*work_aux
```

`create_matrix_free_condensed_operator` 把 context 放入 PETSc Python Mat。`build_explicit_condensed_operator` 只为小规模比较显式形成 Schur。`relative_action_error` 随机比较 action。

## RHS 与回代

`condensed_rhs` 形成 `f-C H^-1 g`；`recover_petsc_auxiliary` 形成 `H^-1(g-D e)`。benchmark 用回代结果构造完整 augmented vector，再对原 A/b 重算 residual。

## 所有权规则

operator shell 不拥有 blocks；销毁顺序应是 KSP/solution -> operator/context work -> rhs -> blocks。重复 destroy 由上层避免。转置和 Hermitian action 的测试防止复矩阵共轭错误。

理论见 `theory/dtn_modal_ports_and_condensation.md`；测试是 `test_22_condensed_dtn.py`，case 022 是运行级契约。
