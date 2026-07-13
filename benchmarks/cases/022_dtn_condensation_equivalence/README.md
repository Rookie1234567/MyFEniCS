# 022：DtN 凝聚等价性

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `022_dtn_condensation_equivalence` / manifest `l2_condensation_mpi1` |
| 2. 证明 | augmented、explicit Schur、matrix-free action、RHS、回代和 transpose 等价 |
| 3. 不证明 | Krylov 在任意 Maxwell 网格收敛 |
| 4. 物理问题 | 人工小型复块矩阵与 Stage4 block extraction |
| 5. 几何 | 无；纯代数 contract |
| 6. 材料 | 无 |
| 7. 波长/角度/偏振 | 无 |
| 8. 边界 | H/C/D 表示抽象 DtN auxiliary coupling |
| 9. FE/网格 | dense/PETSc 小矩阵 |
| 10. PyCharm preset | 无 |
| 11. 参数表 | `src/test/test_22_condensed_dtn.py` fixtures |
| 12. 精确命令 | `python -m unittest src.test.test_22_condensed_dtn` |
| 13. 调用链 | test -> condensed_dtn dense/PETSc APIs |
| 14. 理论 | `dtn_modal_ports_and_condensation.md` |
| 15. 求解器 | dense solve + PETSc shell action |
| 16. RTA 恒等式 | 不适用 |
| 17. 输出 | unittest assertions，无重型 artifact |
| 18. Gates | action/RHS/backsub/transpose/Hermitian relative error |
| 19. Canonical 结果 | Level2 pass |
| 20. Records | manifest pass；无独立数值 record |
| 21. Artifact 规则 | no_artifact |
| 22. 限制 | 只证明同一离散系统的代数等价，不证明连续物理 |

## 物理问题

这是无几何的复块矩阵 fixture，模拟 FE/modal 增广系统 `[F C; D H]`。它把 exact Schur condensation 从 Maxwell 物理中隔离出来，便于验证 action、RHS、转置、Hermitian 和 auxiliary 回代。

## 参数说明

`fixture.json` 说明矩阵 shape、随机种子/构造与 H 条件；`expected.json` 冻结 relative action、RHS 和回代容差。dense reference 支持一般可逆 H，explicit PETSc helper 只支持当前已验证 `H=I`。

## PyCharm

新建 Python Module 配置 `unittest`，参数 `src.test.test_22_condensed_dtn`，Working directory 为仓库根。MPI focused 仍需 External Tool 通过 `mpiexec` 运行。

## CLI 或测试

精确命令保存在 [`test_command.txt`](test_command.txt)：

```text
python -m unittest src.test.test_22_condensed_dtn
mpiexec -n 4 python -m unittest src.test.test_22_condensed_dtn
```

## 代码路径与理论

`test -> condensed_dtn::extract_petsc_condensed_blocks -> create_matrix_free_condensed_operator -> condensed_rhs -> recover_petsc_auxiliary`。逐句映射见 [`../../../notes/reference/code_walkthrough/31_exact_condensation.md`](../../../notes/reference/code_walkthrough/31_exact_condensation.md)。

## 当前证据

Level2 test 在 serial/MPI 验证 dense、explicit、matrix-free、transpose/Hermitian、RHS 与回代。该 case 无重型 artifact；Gate 输出是 unittest 与总 benchmark checker。

## 结果解释

action 一致说明 `F-C H^-1 D` 的 MatPython 实现正确；full augmented residual 仍需实际 runtime 回代后验证。代数精确不意味着 Krylov 快，也不意味着端口 mode 物理正确。

## 限制

`SmallDenseInverse` 当前显式构造 `np.linalg.inv(H_dense)`；explicit distributed builder 对非单位 H 抛 `NotImplementedError`。这些限制必须在新增 modal formulation 前重新评估。
