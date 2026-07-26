# Task035c 测试总结

## 1. 环境

所有Python、MPI、PETSc、DOLFINx和测试都在同一WSL shell中通过
`source scripts/activate_myfenics_wsl.sh`执行。

| Gate | 结果 |
|---|---|
| qualified activation marker | pass |
| Python | repository `.venv/bin/python` |
| PETSc scalar / int | `complex128 / int32` |
| Windows Python/Git/MPI contamination | none |
| ordinary default | `standard_full` unchanged |

## 2. 组件验证

| 组件 | 覆盖 | 结果 |
|---|---|---|
| scalar-CG propagation | phase symbol、stable two-sided propagation、invalid geometry/degree fail-closed | pass |
| scalar-CG traction | endpoint dynamic-stiffness derivative、phase-only negative、combined model | pass |
| p6 cross-section Floquet | p1–p6 exact entity DoF、orientation、serial/MPI2/MPI8 identity | pass |
| static trace projection | slave absolute cutoff、interior scale cutoff、nonfinite/true leakage fail | `14 passed, 4 skipped` focused static suite |
| real cross-rank scale | MPI2 distributed active-scale reduction | pass |
| p6 launch gates | final source/full reference/hash/MPI/profile/preflight | pass |
| channel/resource checker | boundary-plane amplitude、nested reference hash、six-path and resource comparisons | pass after final checker update |
| Case096 compact generator | raw SHA验证、六路径/rank/negative ledger及MPI8 PSS/USS smaps ledger重新生成 | `--check` pass |
| Case096 hermetic contract | 不读取ignored artifact，只校验tracked compact records | pass |

## 3. 数值运行Gate

| PDE batch | 结果 |
|---|---|
| p2/h5 corrected static Hybrid M120/M160 | 12/12 power + 12/12 amplitude |
| p6/h10 Full3D standard/static MPI8 | formal pass、12/12+12/12 |
| p6/h10 Hybrid standard/static M120/M160 MPI8 | formal resource/numeric pass；independent 12/12+12/12 |
| p6/h10 Full3D static MPI1/MPI2 | formal pass |
| p6/h10 Hybrid static M120 MPI1 | numerical controlled negative，biorthogonality越界 |
| p6/h10 Hybrid static M120 MPI2 | resource-authority controlled negative，terminal drain race |

## 4. 最终收口验证

| 命令 / 范围 | 最终结果 |
|---|---|
| Task035c focused：test179–182 + Case095/096 | `29 passed` |
| documentation contract + Case096 | `19 passed` |
| Task034 numerical-blob hardening targeted | `13 passed` |
| Case096 PSS/USS backfill contract | 仅全8-rank同时可读样本；独立复算峰值与降幅 | `6 passed`（单文件当前契约） |
| Case095/096 compact contracts | closeout 时重跑，见选择性合并验证 |
| Case096 raw regeneration `--check` | pass |
| 四个 p6 Hybrid authority 的独立 checker | 每条 `recomputed_pass`，均12/12+12/12 |
| full repository `python -m pytest -q` | `616 passed, 28 skipped in 452.07 s` |
| JSON parse | Case096 compact authority 当前登记 `6` 个 records；全部 parse pass |
| Ruff / compileall / `git diff --check` | pass |

首次full repository运行得到`615 passed, 28 skipped, 1 failed`；唯一失败是
Task034 numerical-blob checker未分类已完成p6 PDE重跑的
`src/constraints/cross_section_floquet.py`。加入真实
“numerical kernel changed + corresponding PDE rerun required”分类并更新
fail-closed期望后，targeted 13项和最终full suite均通过。该修复不改变PDE数值。

没有GitHub Actions证据，因此这里只声明本地WSL测试。昂贵p6 PDE已绑定数值
source `244b62e1...`；后续checker、compact evidence和文档收口没有触发
无理由PDE重跑。
