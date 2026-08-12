# 011：3D Stage 2A 双 Floquet

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `011_3d_stage2a_floquet` |
| 2. 证明 | x/y Floquet MPC、p1 edge/p2 trace、角边链可运行 |
| 3. 不证明 | PML、Fresnel 或端口功率 |
| 4. 物理问题 | 周期空气盒解析平面波 correction |
| 5. 几何 | Stage2 preset 空气盒 |
| 6. 材料 | n_air=1 |
| 7. 波长/角度/偏振 | 633 nm，normal smoke；测试含 oblique |
| 8. 边界 | x/y Floquet，z 解析 reference boundary |
| 9. FE/网格 | N1curl p1 preset；p2 由 test17 |
| 10. Task38 input | [`input/smoke/3d_stage2a_floquet_smoke.dat`](../../../input/smoke/3d_stage2a_floquet_smoke.dat) |
| 11. 参数表 | quick start 21 |
| 12. 精确命令 | `python scripts/run_case.py input/smoke/3d_stage2a_floquet_smoke.dat` |
| 13. 调用链 | Stage2A wrapper -> floquet_3d -> common flow |
| 14. 理论 | `floquet_periodicity.md` |
| 15. 求解器 | ordinary direct |
| 16. RTA 恒等式 | 非本 case Gate |
| 17. 输出 | constraint counts、probe/mismatch、E/H error |
| 18. Gates | test05/06/12/17、serial/MPI consistency |
| 19. Canonical 结果 | 无冻结 record；测试为当前证据 |
| 20. Records | 无，晋级需小型 MPI2 record |
| 21. Artifact 规则 | `benchmarks/artifacts/011/` ignored |
| 22. 限制 | test-backed，不外推到 Stage4 材料面和 DtN |

## 物理问题

在均匀空气盒上把 x/y 两对边改为 Bloch 周期，并用解析平面波 correction 检查相位、边 orientation 和 corner chain。该 case 专门隔离 double Floquet，不加入 PML、界面或 DtN。

## 参数说明

`config.json` 冻结轻量 p1 preset；`expected.json` 将状态标为 `test_backed`。p2 不是由该 CLI record 证明，而由 `test_17_3d_high_order_floquet_trace.py` 的 trace moment fixtures 支持。

## PyCharm

使用仓库根目录下的 [`input/smoke/3d_stage2a_floquet_smoke.dat`](../../../input/smoke/3d_stage2a_floquet_smoke.dat)。调 oblique 入射时同时修改 dat 中的角度、polarization 和相关物理字段；不要只改 phase 字符串绕过配置派生关系。

## CLI 或测试

```text
sh benchmarks/cases/011_3d_stage2a_floquet/run.sh
python scripts/run_case.py input/smoke/3d_stage2a_floquet_smoke.dat
python -m unittest src.test.test_05_floquet_dof_constraints src.test.test_06_airbox_double_floquet_pde
```

## 代码路径与理论

`run_stage2a_floquet_airbox_3d_case -> run_prepared_3d_case_flow -> floquet_3d::build_double_floquet_mpc`。p1 使用 edge topology，p2 还处理 face trace moment 和 orientation。推导见 [`../../../notes/theory/floquet_periodicity.md`](../../../notes/theory/floquet_periodicity.md)。

## 当前证据

当前没有独立 physical record。证据来自 `test_05/06/12/17` 的 serial/MPI、p1/p2 和 orientation 回归，以及可执行 `run.sh`。README 和目录状态明确不把这些测试冒充 RTA 资格。

## 结果解释

检查 global constraint count、owned slave coverage、pairing/probe error 和 total-field Floquet mismatch。corner 约束必须只出现一次并包含 x/y 相位乘积。

## 限制

该 case 不覆盖材料面对齐、PML 衰减、DtN surface quadrature 或 official RTA。Stage4 的 p2 仍需 Case021/031 的完整证据。
