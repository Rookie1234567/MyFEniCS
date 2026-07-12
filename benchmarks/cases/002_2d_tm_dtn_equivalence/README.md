# 002：2D TM DtN 等价性

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `002_2d_tm_dtn_equivalence` / manifest `l1_2d_zero_contrast` |
| 2. 证明 | manual auxiliary DtN 与边界 trace 功率一致，零对比功率闭合 |
| 3. 不证明 | MPI nonlocal DtN、任意高 order 或真实材料收敛 |
| 4. 物理问题 | 2D 零材料对比 total-field port |
| 5. 几何 | period 10 nm，air/substrate 各 5 nm，虚拟 grating 5x2 nm |
| 6. 材料 | 三个区域 n=1 |
| 7. 波长/角度/偏振 | 13.5 nm、默认 15 度、TM |
| 8. 边界 | x-Floquet；上下 Fourier-DtN |
| 9. FE/网格 | N1curl p1，h2 nm |
| 10. PyCharm preset | `2d_tm_dtn_auxiliary_smoke` 是相近入口；record 用专用命令 |
| 11. 参数表 | record metadata.command 与 Level1 脚本 |
| 12. 精确命令 | 见 [`../../records/2d_zero_contrast_dtn_smoke.json`](../../records/2d_zero_contrast_dtn_smoke.json) `metadata.command` |
| 13. 调用链 | run_cases -> solve_port_maxwell -> auxiliary DtN -> power_metrics |
| 14. 理论 | `dtn_modal_ports_and_condensation.md` |
| 15. 求解器 | serial constrained sparse/direct |
| 16. RTA 恒等式 | `R+T=1`；auxiliary 与 trace R/T 差接近舍入误差 |
| 17. 输出 | Level1 artifact + lightweight record |
| 18. Gates | residual、Floquet error、R+T、aux/trace difference |
| 19. Canonical 结果 | record 中 `R+T=1.0000000000000007`（source run） |
| 20. Records | [`../../records/2d_zero_contrast_dtn_smoke.json`](../../records/2d_zero_contrast_dtn_smoke.json) |
| 21. Artifact 规则 | `benchmarks/artifacts/level1/2d_smoke` ignored |
| 22. 限制 | explicit matrix 等价由 focused tests/旧验证补充，不由该单一 record 单独证明 |
