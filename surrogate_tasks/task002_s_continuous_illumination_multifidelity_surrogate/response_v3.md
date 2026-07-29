# Task002 Response V3：Required M2B complete，M3 remains stopped

Review V2 的 Required M2B 已完整执行。Case112/113 raw evidence 未修改，现有 Gate、容差、
S-only 范围和 0.5° grazing 下限均未放宽。本轮没有开始 49 点正式 campaign、四维 bulk、
surrogate、angle DOE 或反演。

Review V2 base 为 `17589ac0578e0e1ac121429a549d00f8ae17c7bc`；正式 M2B PDE clean
baseline 为 `673c66ddee116e683a21b7ea8a90dc158cac2069`。所有正式作业均为 MPI2、每 rank
一线程、watchdog、zero swap、cleanup complete。

主要结果：

1. A--D 的 Full3D p3/p4/p5 和追加 p4/h7.5 表明 p4/h10 欠分辨；p4/h7.5 与 p5/h10
   选择同一响应分支；
2. Hybrid p5 与 same-p Full3D p5 的 12 点最大 R/T/A 差为 `1.853e-5`，所以大 p-branch
   jump 不是 Hybrid 耦合错误；
3. axial Route A/B 最大 observable 差仅 `3.30e-7`，排除 discrete axial mapping 为大跳变根因；
4. 48/48 个真实双 Floquet probe 通过，最大解析 residual `1.898e-15`、slave-row residual
   `0`、显式 `C^H A C` error `1.517e-16`；
5. p6/45° biorthogonality 失败定位为相邻 near-degenerate blocks `[114,115]` 与
   `[116,117]` 被拆分，最坏 row sum `1.7766e-6`；同类失败也出现在 1°/45°、10°/45°；
6. Hybrid p4 中心几何 80-angle map 为 39 pass / 41 fail，不能作为统一 LF；
7. bottom/top local 与 external DtN identity 基本闭合，p4 whole-domain volume closure 缺口仍超过
   原 Gate，未被重命名或隐藏。

最终选择 Route 4：暂停 Hybrid，后续候选为 Full3D static hierarchy。但 Full3D p4/h7.5 目前
只有 A--D anchors，没有 80-angle qualification，因此 M3 不获授权并继续 controlled stop，等待
Review V3 决定是否执行该最小追加资格化。

交付物：

- Case114 config/expected/test command；
- 七份 raw-derived compact records；
- `benchmarks/check_case114_task002_m2b.py` checker；
- `outcomes/m2_solver_domain_qualification.md`；
- `outcomes/solver_routing_map.md`；
- 本 `response_v3.md`。

本轮最终相关回归为 39 passed in 80.91 s，checker 可从 ignored raw artifacts 重建并逐字比较
全部七份 records。Ruff 未运行，因为资格化 `.venv` 中没有 `ruff` 命令或模块；compileall、JSON
解析和 `git diff --check` 均通过。
