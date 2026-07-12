# 013：3D Stage 2C Fresnel

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `013_3d_stage2c_fresnel` |
| 2. 证明 | 平界面材料 tag、Fresnel background、incident-scattered 与 PML 可运行 |
| 3. 不证明 | Stage4 多模 DtN 或高精度 p2 Fresnel |
| 4. 物理问题 | air/substrate 平界面 |
| 5. 几何 | Stage2 盒，interface z=0 |
| 6. 材料 | air 1，substrate 默认 1.45 或显式 complex |
| 7. 波长/角度/偏振 | 633 nm normal smoke；代码支持 s/p oblique |
| 8. 边界 | x/y Floquet、z PML |
| 9. FE/网格 | N1curl p1，h300 nm smoke |
| 10. PyCharm preset | `3d_stage2c_fresnel_smoke` |
| 11. 参数表 | quick start 23 |
| 12. 精确命令 | `python src/main.py --preset 3d_stage2c_fresnel_smoke` |
| 13. 调用链 | Stage2C -> analytic_fields_3d -> incident-scattered flow |
| 14. 理论 | Maxwell、PML、Stage ladder |
| 15. 求解器 | ordinary direct |
| 16. RTA 恒等式 | 无损对 Fresnel/R+T；复材料增加 A_volume |
| 17. 输出 | numerical/reference E/H/R/T/A differences |
| 18. Gates | Fresnel unit、field error、energy、PML sensitivity |
| 19. Canonical 结果 | 尚无冻结 record |
| 20. Records | 无 |
| 21. Artifact 规则 | `benchmarks/artifacts/013/` ignored |
| 22. 限制 | experimental；历史 p2 路线只作 diagnostic |
