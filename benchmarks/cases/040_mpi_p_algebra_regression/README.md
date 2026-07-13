# 040：MPI、阶次与代数回归

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `040_mpi_p_algebra_regression` / Level2 |
| 2. 证明 | p1/p2 constraint、condensation、owner slabs、sm2 在 serial/MPI 测试契约下稳定 |
| 3. 不证明 | 重型 target 的 wall-time 或 RTA |
| 4. 物理问题 | 小型解析/PETSc fixtures |
| 5. 几何 | 各 test 固定小网格 |
| 6. 材料 | air/Fresnel/人工矩阵按 test |
| 7. 波长/角度/偏振 | 按 test fixture |
| 8. 边界 | Floquet/PML/DtN 分层覆盖 |
| 9. FE/网格 | p1/p2，MPI1/2/4 |
| 10. PyCharm preset | 无 |
| 11. 参数表 | test source 与 Level2 script |
| 12. 精确命令 | `sh benchmarks/scripts/run_level2_mpi.sh` |
| 13. 调用链 | script -> unittest MPI groups -> checker |
| 14. 理论 | Floquet、condensation、two-level PC |
| 15. 求解器 | focused direct/shell/local KSP |
| 16. RTA 恒等式 | 仅相关 fixture；不产生产 RTA |
| 17. 输出 | unittest/console + checker report |
| 18. Gates | all tests pass、MPI no hang、checker pass |
| 19. Canonical 结果 | Task28 Level2 pass |
| 20. Records | benchmark gate report/manifest |
| 21. Artifact 规则 | no heavy artifact |
| 22. 限制 | 这是软件/代数回归，不替代 Level3 物理 benchmark |

## 物理问题

这是 focused regression 集，不对应单一几何。它把 p1/p2 Floquet、PML helper、DtN condensation、slab ownership、coarse action 和 sm2 放入小型 serial/MPI fixtures，防止维护时破坏分布式代数。

## 参数说明

`fixture.json` 列出测试组、MPI size 和对象类型；`expected.json` 要求所有测试通过、无 MPI hang，并保持明确的 test-backed 身份。它不设置 R/T/A 数值。

## PyCharm

serial group 可用 PyCharm unittest 配置；MPI2/4 必须用 External Tool 调用 Level2 script 或 `mpiexec`。普通 PyCharm Run 通过不能代替 MPI ownership 测试。

## CLI 或测试

```text
sh benchmarks/scripts/run_level2_mpi.sh
python benchmarks/check_benchmarks.py --no-write
```

精确 focused 组也保存在 [`test_command.txt`](test_command.txt)。

## 代码路径与理论

覆盖 `floquet_3d`、`condensed_dtn`、`physical_slab_two_level` 及其 PETSc destroy paths。对应理论为 [`../../../notes/theory/floquet_periodicity.md`](../../../notes/theory/floquet_periodicity.md)、[`../../../notes/theory/dtn_modal_ports_and_condensation.md`](../../../notes/theory/dtn_modal_ports_and_condensation.md) 与 [`../../../notes/theory/iterative_solver_and_preconditioner.md`](../../../notes/theory/iterative_solver_and_preconditioner.md)。

## 当前证据

Task28 Level2 serial/MPI focused suite 通过；Gate 由 unittest exit code 和 benchmark checker 记录。无独立 physical JSON，也不写重型 artifact。

## 结果解释

该 case 能发现 owner 分配、空 owner、transpose/Hermitian、重复 apply、destroy 和 p2 orientation 回归。它不能回答 target 迭代次数、内存或能量闭合。

## 限制

小 fixture 的通过是进入 Level3 的必要条件而非充分条件。任何影响真实 matrix action、PC 参数或 RTA 的修改仍要跑 Case021/031 对照。
