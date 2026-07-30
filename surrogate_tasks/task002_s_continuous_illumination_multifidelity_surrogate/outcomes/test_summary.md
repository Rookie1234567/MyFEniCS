# Task002 测试与执行汇总

## M4D（Review V6）

| 检查 | 结果 |
|---|---|
| clean diagnostic SHA | `0a53c42397a2e67f64e8f6dae2c680bfe3fe4b95` |
| Case118 PDE | 35/35 complete，全部 zero swap + cleanup complete |
| 失败/中心 azimuth stencil | 14/14 + 14/14，点表精确 |
| Ny convergence | Ny=3/4/5/6 全部完成 |
| surface quadrature | auto=21/31/39/47 全部完成 |
| independent projection / Gram | 完成；S 一致，P discrepancy 保留为负证据 |
| Case118 independent checker | 13/13 pass |
| Task000/001/002 + repository regression | 81 passed |
| M4D + Task002 focused tests | 41 passed |
| Case117 controlled-stop checker | 8/8 pass，历史停止边界未变 |
| compileall | pass |
| `git diff --check` | pass |
| full repository pytest | not rerun；Review V5 前置结果为 684 passed / 28 skipped / 7 个已知无关失败，本轮运行任务范围回归 |

第一次 Case117 checker 调用误用直接脚本入口，因 `src` 不在该入口的模块路径而
失败；按正式 `python -m ... --verify-stopped` 入口重跑后 8/8 通过。这是命令调用
错误，不是测试或数值失败。

## M2B

| 检查 | 结果 |
|---|---|
| Case114 final related pytest | 39 passed in 80.91 s |
| Case114 raw-to-compact checker | pass，七份 records 可重建并逐字比较 |
| Full3D p3/p4/p5 A--D | complete |
| Full3D p4/h7.5 A--D | complete，zero swap |
| Full3D p4 80-angle map | 80/80 complete |
| Hybrid p4 80-angle map | 80/80 complete，39 formal pass + 41 formal fail |
| Hybrid p5/p6 selected points | 12/12 each complete |
| axial Route A/B | 6 pairs complete |
| double Floquet probes | 48/48 Gate pass |
| formal source | `673c66ddee116e683a21b7ea8a90dc158cac2069` |
| prohibited later stages | all not run |
| Ruff | not_run：资格化 `.venv` 未安装 `ruff` 模块或命令 |

所有完成的正式 PDE 均为 MPI2、每 rank 一线程、peak swap 0、watchdog cleanup complete。

## M2A 历史

| 检查 | 结果 |
|---|---|
| Review V1 final combined regression | 91 passed in 79.31 s（保留历史结果） |
| Case110 checker | pass，37 compact responses unchanged（保留历史结果） |
| Case112 raw-to-compact checker | pass，9 samples，8 pass + 1 failed（保留历史结果） |
| Task002/Task001/Task035c gate regression | 52 passed in 2.36 s |
| Case113 scaffold/checker | pass |
| p/M matrix | 6/6 records complete |
| LF diagnostic stencil | 13/13 complete，4 pass + 9 fail |
| HF diagnostic subset | mandatory 15° + selected 30°/45°/60° complete |
| independent Full3D p4/h10 | complete，energy closure `4.92e-13` |
| raw Case112 evidence | immutable，未改写 |
| resource audit | all new runs zero swap，cleanup complete |

Case113 compact record re-extraction/checker 已通过；`git diff --check` 在提交前再次执行。
