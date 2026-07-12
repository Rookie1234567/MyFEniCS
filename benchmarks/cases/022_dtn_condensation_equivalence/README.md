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
