# 001：2D TM PML + Floquet

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `001_2d_tm_pml_floquet` |
| 2. 证明 | TM Nedelec scattered-field、x-Floquet、上下 PML 可联合运行 |
| 3. 不证明 | 任意 PML 参数、EUV 光栅网格收敛或生产迭代 |
| 4. 物理问题 | 二维周期矩形光栅散射场 |
| 5. 几何 | preset 中 600 nm 周期、850/350 nm air/substrate |
| 6. 材料 | air 1、substrate/grating 1.45，默认无损 |
| 7. 波长/角度/偏振 | 633 nm、15 度、TM |
| 8. 边界 | x-Floquet；y 上下 PML |
| 9. FE/网格 | N1curl p1，target h80 nm，triangle |
| 10. PyCharm preset | `2d_tm_pml_floquet_smoke` |
| 11. 参数表 | [`../../../notes/quick_start/10_2d_pml_floquet.md`](../../../notes/quick_start/10_2d_pml_floquet.md) |
| 12. 精确命令 | `python src/main.py --preset 2d_tm_pml_floquet_smoke` |
| 13. 调用链 | main -> run_cases -> solve_vector_maxwell -> power_metrics |
| 14. 理论 | Maxwell、Floquet、PML 三篇规范理论 |
| 15. 求解器 | serial manual reduction + SuperLU（preset） |
| 16. RTA 恒等式 | 无损目标检查 `R+T`；PML 不计入 A_volume |
| 17. 输出 | ordinary `results/` summary/log/VTU/power JSON |
| 18. Gates | complex mode；residual；Floquet mismatch；PML 扫描；R/T 稳定 |
| 19. Canonical 结果 | 当前未冻结 machine-readable record |
| 20. Records | 无；晋级时新增 `records/2d_tm_pml_floquet.json` |
| 21. Artifact 规则 | `benchmarks/artifacts/001/`，不提交 |
| 22. 限制 | 当前 `test-backed`；不能用 preset 存在宣称生产精度 |
