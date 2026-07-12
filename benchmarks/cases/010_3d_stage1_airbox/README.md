# 010：3D Stage 1 空气盒

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `010_3d_stage1_airbox` / manifest/record `l1_3d_stage1` |
| 2. 证明 | 3D H(curl)、解析平面波、MPI2 direct 和并行输出可运行 |
| 3. 不证明 | Floquet、PML、Fresnel、DtN、光栅 |
| 4. 物理问题 | 均匀空气盒平面波 |
| 5. 几何 | 10x10x10 nm smoke |
| 6. 材料 | n_air=1 |
| 7. 波长/角度/偏振 | runner Stage1 normal 默认 |
| 8. 边界 | 解析场边界；无 Floquet/PML |
| 9. FE/网格 | N1curl p1，h5 nm，MPI2 |
| 10. PyCharm preset | `3d_stage1_airbox_smoke`（默认） |
| 11. 参数表 | record metadata + quick start 20 |
| 12. 精确命令 | [`../../records/3d_stage1_mpi2_smoke.json`](../../records/3d_stage1_mpi2_smoke.json) `metadata.command` |
| 13. 调用链 | run_3d_cases -> Stage1 wrapper -> common flow |
| 14. 理论 | Maxwell 强/弱式与 Stage ladder |
| 15. 求解器 | MPI2 PETSc/MUMPS direct |
| 16. RTA 恒等式 | 不作为 Stage1 Gate；检查 Poynting 方向 |
| 17. 输出 | E/H error、residual、RSS、fields |
| 18. Gates | residual、relative E/H error、direction cosine |
| 19. Canonical 结果 | residual `1.3947e-16`，direction cosine 1 |
| 20. Records | [`../../records/3d_stage1_mpi2_smoke.json`](../../records/3d_stage1_mpi2_smoke.json) |
| 21. Artifact 规则 | `benchmarks/artifacts/level1/3d_stage1` ignored |
| 22. 限制 | 极粗网格 smoke，E/H error 不代表收敛阶研究 |
