# 011：3D Stage 2A 双 Floquet

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `011_3d_stage2a_floquet` |
| 2. 证明 | x/y Floquet MPC、p1 edge/p2 trace、角边链可运行 |
| 3. 不证明 | PML、Fresnel 或端口功率 |
| 4. 物理问题 | 周期空气盒解析平面波 correction |
| 5. 几何 | Stage2 preset 空气盒 |
| 6. 材料 | n_air=1 |
| 7. 波长/角度/偏振 | 633 nm，normal smoke；测试含 oblique |
| 8. 边界 | x/y Floquet，z 解析 reference boundary |
| 9. FE/网格 | N1curl p1 preset；p2 由 test17 |
| 10. PyCharm preset | `3d_stage2a_floquet_smoke` |
| 11. 参数表 | quick start 21 |
| 12. 精确命令 | `python src/main.py --preset 3d_stage2a_floquet_smoke` |
| 13. 调用链 | Stage2A wrapper -> floquet_3d -> common flow |
| 14. 理论 | `floquet_periodicity.md` |
| 15. 求解器 | ordinary direct |
| 16. RTA 恒等式 | 非本 case Gate |
| 17. 输出 | constraint counts、probe/mismatch、E/H error |
| 18. Gates | test05/06/12/17、serial/MPI consistency |
| 19. Canonical 结果 | 无冻结 record；测试为当前证据 |
| 20. Records | 无，晋级需小型 MPI2 record |
| 21. Artifact 规则 | `benchmarks/artifacts/011/` ignored |
| 22. 限制 | test-backed，不外推到 Stage4 材料面和 DtN |
