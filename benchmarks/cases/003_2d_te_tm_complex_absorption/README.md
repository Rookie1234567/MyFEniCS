# 003：2D TE/TM 与复材料吸收

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `003_2d_te_tm_complex_absorption` |
| 2. 证明 | TE 标量与 TM H(curl) 分路、complex index 解析、体吸收字段可运行 |
| 3. 不证明 | TE 与 TM 数值应相同，或材料数据对特定实验准确 |
| 4. 物理问题 | 2D 周期端口复材料 |
| 5. 几何 | EUV preset 100 nm 周期、100/50 nm air/substrate、50 nm block |
| 6. 材料 | Si 示例 `0.999002304859+0.00182649365j` |
| 7. 波长/角度/偏振 | 13.5 nm、0 度、分别 TE/TM |
| 8. 边界 | x-Floquet；TM DtN 或 TE Robin/DtN |
| 9. FE/网格 | TM N1curl、TE Lagrange，p2，h3 nm smoke |
| 10. PyCharm preset | `2d_complex_absorption`, `2d_te_port_smoke` |
| 11. 参数表 | quick start 12/13 |
| 12. 精确命令 | `python src/main.py --preset 2d_complex_absorption` |
| 13. 调用链 | run_cases -> solve_port_maxwell/solve_te_maxwell -> power_metrics |
| 14. 理论 | Maxwell TM/TE 与 official RTA 理论 |
| 15. 求解器 | serial manual direct |
| 16. RTA 恒等式 | `A_balance≈A_volume`，`R+T+A_volume≈1` |
| 17. 输出 | complex config、分区 absorption、R/T/A |
| 18. Gates | parser complex；positive Im(eps)；residual；absorption identity |
| 19. Canonical 结果 | 当前未冻结 record |
| 20. Records | 无；晋级需 TE/TM 各一份轻量 record |
| 21. Artifact 规则 | `benchmarks/artifacts/003/` ignored |
| 22. 限制 | `test-backed`；外部 n 数据必须先统一时间谐波符号 |
