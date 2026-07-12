# 031：工作站 MPI4 迭代生产档

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `031_workstation_iterative` / manifest `l3_iterative_h5/h3/h2` |
| 2. 证明 | target p2 h5/h3/h2 在 14 GB WSL2 限定环境完整收敛并输出 official RTA |
| 3. 不证明 | h1.5、任意角度/材料/几何、严格 mesh-independent |
| 4. 物理问题 | 与 case021 相同 3D EUV Si block grating |
| 5. 几何 | 50x25x140 nm；17x25x120 nm block |
| 6. 材料 | air + complex Si substrate/grating |
| 7. 波长/角度/偏振 | 13.5 nm；80/0 度；s |
| 8. 边界 | 双 Floquet + auto-propagating auxiliary DtN |
| 9. FE/网格 | N1curl p2，h5/h3/h2，MPI4 |
| 10. PyCharm preset | 无；禁止普通单进程 main 静默启动 |
| 11. 参数表 | [`../../configs/workstation_p2.json`](../../configs/workstation_p2.json) |
| 12. 精确命令 | 各 record 的 `canonical_rerun_command`；批量 `sh benchmarks/scripts/run_level3_iterative.sh` |
| 13. 调用链 | iterative runner -> stage4_runtime -> condensation -> two-level PC -> RTA |
| 14. 理论 | iterative PC、DtN condensation、RTA |
| 15. 求解器 | right FGMRES(100)+75D coarse+16 shifted slabs+sm2 |
| 16. RTA 恒等式 | full residual 后 `R+T+A_volume≈1`，h5/h3 对 direct |
| 17. 输出 | parameters/progress/record + ignored full RTA artifacts |
| 18. Gates | qualified、reason>0、三残差、coarse、condition、RSS、RTA、identity |
| 19. Canonical 结果 | h5 1201 iter；h3 993；h2 1804；h2 RSS 13.080 GB |
| 20. Records | [`h5`](../../records/workstation_p2_h5_mpi4.json)、[`h3`](../../records/workstation_p2_h3_mpi4.json)、[`h2`](../../records/workstation_p2_h2_mpi4.json) |
| 21. Artifact 规则 | `benchmarks/artifacts/iterative` ignored |
| 22. 限制 | 资格严格等于 physical_model+resolved_config；任何偏离 experimental |
