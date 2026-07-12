# 030：MUMPS OOC/BLR Direct Fallback

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `030_mumps_ooc_blr` |
| 2. 证明 | profile 解析、OOC 文件生命周期、BLR option 映射 |
| 3. 不证明 | OOC/BLR 对 h2/h1.5 必然低于 14 GB |
| 4. 物理问题 | Stage4B direct fallback |
| 5. 几何 | main h5 演示；历史报告含 target 诊断 |
| 6. 材料 | complex Si |
| 7. 波长/角度/偏振 | 13.5 nm，具体随 case |
| 8. 边界 | Stage4 auxiliary DtN |
| 9. FE/网格 | p2 h5 smoke；更细仅显式资源测试 |
| 10. PyCharm preset | `3d_stage4b_grating_mumps_ooc`, `...mumps_blr` |
| 11. 参数表 | quick start 32、MUMPS user guide |
| 12. 精确命令 | `python src/main.py --preset 3d_stage4b_grating_mumps_ooc`（BLR 同理） |
| 13. 调用链 | main -> 3D runner -> common_3d_solve profile |
| 14. 理论 | `direct_solvers_and_factorization.md` |
| 15. 求解器 | MUMPS direct OOC 或 BLR |
| 16. RTA 恒等式 | 必须与 default direct 比较 R/T/A/closure |
| 17. 输出 | PETSc options、backend、residual、RSS、OOC cleanup |
| 18. Gates | test18/19；MUMPS available；true residual；RTA delta |
| 19. Canonical 结果 | 当前仅 test-backed/历史 Task10；无 V2 重跑 |
| 20. Records | 无独立 V2 record |
| 21. Artifact 规则 | OOC factors 写 case dir；成功删、失败留；不提交 |
| 22. 限制 | experimental direct fallback；BLR 不是迭代法 |
