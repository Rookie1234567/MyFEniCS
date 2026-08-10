# Task037b 继承基线审计

## 身份与测试

| 项目 | 事实 |
|---|---|
| branch | `codex/20260807-task37b-hybrid-iterative-development` |
| tested SHA | `26e48e2767d200b6ec58b39d117c354afbdba30c` |
| upstream | `origin/codex/20260807-task37b-hybrid-iterative-development` |
| clean-before-test | true |
| origin/master | `454df04358bd4e1670ec14c5b0276b430249cd37` |
| focused result | `76 passed / 1 skipped / 225.86s` |

本审计使用的唯一 focused pytest 命令为：

```text
python -m pytest -q src/test/test_24_repository_work_principles.py src/test/test_26_documentation_contract.py src/test/test_28_direct_memory_telemetry.py src/test/test_179_task035b_hybrid_static_condensation.py src/test/test_217_task037_f0_direct_authority.py src/test/test_218_task037_static_iterative_port.py src/test/test_219_task037_external_solver_runtime.py src/test/test_224_task037_static_local_schur_action.py src/test/test_230_task037_dtn_direct_blocks.py src/test/test_231_task037_dtn_action_only_port.py src/test/test_53_task033_high_order_hybrid_components.py src/test/test_hybrid_interface_audits.py
```

命令 exit 为 0；没有删除测试或放宽断言，pytest 报告 1 个既有 skip。

## ABI 与版本

| 项目 | 值 |
|---|---|
| qualified activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| Python | `/home/Projects/MyFEniCS/.venv/bin/python`, Python 3.12.3 |
| PETSc scalar/index | `complex128 / int32` |
| PETSc / SLEPc | `3.19.6 / 3.19.2` |
| petsc4py / slepc4py | `3.19.6 / 3.19.2` |
| DOLFINx / Basix | `0.10.0.post2 / 0.10.0` |
| mpi4py / MPI | `3.1.5 / Open MPI 4.1.6` |
| MPI world size | 1 for this serial focused command |

四个 Python 包来自同一 Linux PETSc ABI 栈；本阶段没有运行 MPI 或 PDE。

## Task037 selective history

以下是从 `f8fab5e12a4cc33cd60dc96d40f628caca446b58` 到 `454df04358bd4e1670ec14c5b0276b430249cd37` 的 11 个提交，按时间顺序列出完整 SHA 与 subject：

| # | SHA | subject |
|---:|---|---|
| 1 | `f1e14315dc3de7a0afcc58c1aa2041b79c7691bc` | feat(task037): integrate static-condensed Full3D foundations |
| 2 | `9ea04c0fb5fe153fe37a7e9048fc1b5dd8cf2e37` | feat(task037): integrate matrix-free DtN and action-only telemetry |
| 3 | `71f92e0031c1db2cc59e24ee96989ff77d342e68` | feat(task037): integrate static-condensed Full3D iterative core |
| 4 | `1aa84568db3f07716151badfea9b92b25c74e353` | fix(task037): integrate canonical trace and modal-basis safety |
| 5 | `211ea4908ab5fe09b79928a54b35e4a80e39b1ba` | fix(task037): restore never-materialized local Schur authority |
| 6 | `3fa5e54f56140d963a820b7bd76a2f58113d648c` | test(task037): add focused iterative and matrix-free coverage |
| 7 | `c5ce98d45ced817014e07fa56c915ecfb2b34b1f` | fix(task037): propagate matrix-free DtN probe telemetry |
| 8 | `0fcf08a3f09e3beb137212d41f411823cb2e24e8` | fix(task037): propagate external solver profile telemetry |
| 9 | `0f3dbacc38cd797f7a59272b4f185393e7980121` | test(task037): align high-order Hybrid quadrature contract |
| 10 | `55cf2555ac5b3aa52878091869f03fb94a2c0765` | style(task033): normalize high-order Hybrid test formatting |
| 11 | `454df04358bd4e1670ec14c5b0276b430249cd37` | docs(task037): record controlled closeout and Task37b handoff |

## 继承边界

- formal Matrix-free DtN 与 M3a 仍是显式 opt-in；没有把它们改成 ordinary default。
- Task037 Candidate A–F/E 的 campaign modules、capacity/M120 负结果和 raw evidence 均未作为 production/default 进入 master；它们保持 research-only 或 negative-evidence 边界。
- Task036 strong-trace 与 exact-trace 仍是 research-only oracle，没有成为 ordinary Hybrid default。
- ordinary direct 与 ordinary Hybrid defaults unchanged。
- Task037 的 Full3D coarse negative 不替代本任务的 Hybrid block-system 验证。

## Full pytest 历史边界

Task037 full pytest 的历史原样为 `849 passed / 48 skipped / 3 failed`；随后 test53、test69 与相关 targeted closure 通过，但没有第二次 full pytest。因此该历史不能写成 inherited full-suite PASS。

本文件只记录继承审计；H1 direct authority、solver 修改、MPI/PDE 和 Task037b outcomes 尚未开始。
