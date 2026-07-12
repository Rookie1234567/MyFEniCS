# 040：MPI、阶次与代数回归

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `040_mpi_p_algebra_regression` / Level2 |
| 2. 证明 | p1/p2 constraint、condensation、owner slabs、sm2 在 serial/MPI 测试契约下稳定 |
| 3. 不证明 | 重型 target 的 wall-time 或 RTA |
| 4. 物理问题 | 小型解析/PETSc fixtures |
| 5. 几何 | 各 test 固定小网格 |
| 6. 材料 | air/Fresnel/人工矩阵按 test |
| 7. 波长/角度/偏振 | 按 test fixture |
| 8. 边界 | Floquet/PML/DtN 分层覆盖 |
| 9. FE/网格 | p1/p2，MPI1/2/4 |
| 10. PyCharm preset | 无 |
| 11. 参数表 | test source 与 Level2 script |
| 12. 精确命令 | `sh benchmarks/scripts/run_level2_mpi.sh` |
| 13. 调用链 | script -> unittest MPI groups -> checker |
| 14. 理论 | Floquet、condensation、two-level PC |
| 15. 求解器 | focused direct/shell/local KSP |
| 16. RTA 恒等式 | 仅相关 fixture；不产生产 RTA |
| 17. 输出 | unittest/console + checker report |
| 18. Gates | all tests pass、MPI no hang、checker pass |
| 19. Canonical 结果 | Task28 Level2 pass |
| 20. Records | benchmark gate report/manifest |
| 21. Artifact 规则 | no heavy artifact |
| 22. 限制 | 这是软件/代数回归，不替代 Level3 物理 benchmark |
