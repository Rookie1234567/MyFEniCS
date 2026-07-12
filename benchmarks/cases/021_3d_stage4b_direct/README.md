# 021：3D Stage 4B Target Direct

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `021_3d_stage4b_direct` / manifest `l3_direct_h5/h3` |
| 2. 证明 | target p2 h5/h3 MPI4 MUMPS direct 可解并给出 official RTA |
| 3. 不证明 | h2 在 14 GB 可 direct、h1.5 或任意几何 |
| 4. 物理问题 | 3D EUV 周期 Si block grating |
| 5. 几何 | period 50x25 nm；block 17x25x120；air 130；substrate 10 |
| 6. 材料 | air + complex Si substrate/grating |
| 7. 波长/角度/偏振 | 13.5 nm；theta 80、phi 0；s |
| 8. 边界 | x/y Floquet；auto-propagating auxiliary DtN |
| 9. FE/网格 | N1curl p2；h5/h3；MPI4 |
| 10. PyCharm preset | main 的 Stage4 h5/h3 是演示几何；canonical 用下述 CLI |
| 11. 参数表 | record metadata.command、`stage4_runtime.target_stage4_config` |
| 12. 精确命令 | [`../../records/direct_p2_h5_mpi4.json`](../../records/direct_p2_h5_mpi4.json) / h3 metadata |
| 13. 调用链 | run_3d_cases -> Stage4B -> common flow -> dtn_port_3d |
| 14. 理论 | Stage ladder、DtN、direct solver、RTA |
| 15. 求解器 | MPI4 PETSc preonly+LU+MUMPS |
| 16. RTA 恒等式 | `R+T+A_volume≈1`；h5/h3 与迭代交叉 |
| 17. 输出 | full fields/artifact + lightweight direct record |
| 18. Gates | residual、RTA closure、direct/iterative delta、RSS |
| 19. Canonical 结果 | h5 RSS 2.293 GB；h3 RSS 8.18 GB，数值见 records |
| 20. Records | [`direct_p2_h5_mpi4.json`](../../records/direct_p2_h5_mpi4.json)、[`direct_p2_h3_mpi4.json`](../../records/direct_p2_h3_mpi4.json) |
| 21. Artifact 规则 | `benchmarks/artifacts/direct` ignored |
| 22. 限制 | h2 direct 仅 reviewed historical reference，非 Task28 rerun |
