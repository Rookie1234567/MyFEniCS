# 012：3D Stage 2B PML

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `012_3d_stage2b_pml` |
| 2. 证明 | z-PML tensor 与双 Floquet/3D flow 可组合运行 |
| 3. 不证明 | 任意 PML 参数的低反射或 Stage4 production 精度 |
| 4. 物理问题 | 周期空气盒 correction + 上下 PML |
| 5. 几何 | Stage2 preset，PML 各 250 nm |
| 6. 材料 | air continuation |
| 7. 波长/角度/偏振 | 633 nm，normal smoke |
| 8. 边界 | x/y Floquet，z PML |
| 9. FE/网格 | N1curl p1，h300 nm smoke |
| 10. PyCharm preset | `3d_stage2b_pml_smoke` |
| 11. 参数表 | quick start 22 |
| 12. 精确命令 | `python src/main.py --preset 3d_stage2b_pml_smoke` |
| 13. 调用链 | Stage2B -> pml_3d/common_3d_forms -> common flow |
| 14. 理论 | `pml_robin_and_open_boundaries.md` |
| 15. 求解器 | ordinary direct |
| 16. RTA 恒等式 | PML 不计 A_volume；本 case 主要看衰减/误差 |
| 17. 输出 | PML tag/field decay/reference error |
| 18. Gates | PML tensor unit test、decay、physical-region error、parameter scan |
| 19. Canonical 结果 | 尚无冻结 record |
| 20. Records | 无 |
| 21. Artifact 规则 | `benchmarks/artifacts/012/` ignored |
| 22. 限制 | experimental；旧 Stage2 数据有精度限制，能力矩阵不得写 recommended |
