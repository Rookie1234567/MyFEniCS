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
| 10. PyCharm preset | `3d_stage4b_demo_mumps_ooc`, `3d_stage4b_demo_mumps_blr` |
| 11. 参数表 | quick start 32、MUMPS user guide |
| 12. 精确命令 | `python src/main.py --preset 3d_stage4b_demo_mumps_ooc`（BLR 同理） |
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

## 物理问题

本 case 验证 Stage4 direct profile 的软件契约：MUMPS OOC 把部分 factor 写磁盘，BLR 压缩 factor block。默认 preset 使用 demo 几何，不宣称复现 target Case021。

## 参数说明

`config.json` 固定 profile 名、基础 PETSc option 和 artifact policy；`expected.json` 要求 option 映射、MUMPS 可用性、真残差及 OOC 成功清理/失败保留语义。用户附加 PETSc option 会覆盖 profile，必须保存 resolved options。

## PyCharm

选择更新后的 `3d_stage4b_demo_mumps_ooc` 或 `3d_stage4b_demo_mumps_blr`。运行前确认磁盘目录可写。target 实验应复制为显式 candidate CLI，不把 demo preset 改名伪装成 target。

## CLI 或测试

```text
python src/main.py --preset 3d_stage4b_demo_mumps_ooc
python src/main.py --preset 3d_stage4b_demo_mumps_blr
python -m unittest src.test.test_18_direct_solver_profiles src.test.test_19_mumps_ooc_runtime
```

规范 focused 命令见 [`test_command.txt`](test_command.txt)。

## 代码路径与理论

`main -> run_3d_cases -> common_3d_solve::_prepare_direct_lu_options_for_comm -> MUMPS -> residual/OOC cleanup`。详见 [`../../../notes/reference/code_walkthrough/30_direct_solver_profiles.md`](../../../notes/reference/code_walkthrough/30_direct_solver_profiles.md)。

## 当前证据

当前是 test-backed/experimental：option 和目录生命周期已自动验证，历史 Task10 有资源结果，但 Task28 没有新增 OOC/BLR canonical physical record。

## 结果解释

OOC 的磁盘文件出现不代表成功，必须同时有 positive KSP reason、真残差、RTA 和 cleanup status。BLR 的 KSP iteration 不是迭代次数；压缩误差靠真残差和 direct delta 判断。

## 限制

OOC 可能受 I/O 和 factor fill 限制，BLR 可能增加误差。二者都不保证 h2 低于 14 GB，也不替代 Case031 的 FGMRES production profile。
