# Task035e：无参考解、多层局部 h/p 自适应

## 当前身份

```text
task = Task035e
status_at_creation = staged_on_Task035d_branch
execution_branch = codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity
branch_creation = by Codex after Task035d selective merge
branch_base = exact post-Task035d master SHA
ordinary_default = unchanged
geometry = Task034 fixed rectangular block grating
wavelength = 13.5 nm used as a reference-blind surrogate for future 0.7 nm
primary_solver = Full3D assembly-time static condensation + MUMPS direct
hybrid = only after Full3D blind hp candidate passes
iterative_solver = out of scope
heavy_PDE_concurrency = one at a time
```

Task035e 模拟未来 0.7 nm 的真实困难：完整收敛解不可获得，自适应程序不能读取一个“老师答案”来决定哪里细化、哪里升阶、何时停止。

本任务把工作严格分成三层：

1. **Reference certifier**：独立运行 p6/h10、p6/h7.5、p6/h5，检查高阶序列是否收敛，并生成封存的 hidden authority；
2. **Blind adaptive controller**：只能使用当前解、残差、伴随、local p-shadow、local h-shadow 和误差预算，不能读取 hidden authority；
3. **Final hidden auditor**：自适应候选完全冻结后，才读取 hidden authority 检查算法是否真的成功。

当前不再按功率大小筛“显著通道”。对于固定13.5 nm、S偏振、10°掠入射、沿 y 不变化的结构，正式低阶输出集合固定为：

```text
N = 8
n = 0
m = 0, -1, -2, -3, -4, -5, -6, -7
```

对 top/bottom 两个端口分别审计每个级的功率和复振幅，并同时保存完整传播谱、R00、Rtotal、Ttotal、Aclosure、Avolume、场与残差。

Task035e 的重点不是把 p6/h10 轻微删改，而是从真正粗网格开始，允许多个 local-h level 与 local-p 同时存在，使最终网格真实包含大、中、小不同单元。

正式任务书：

```text
docs/task035e_reference_blind_multilevel_hp_adaptivity/task.md
```

## 当前执行进度

Task035e 的软件层已进入正式 PDE 前资格化阶段。当前实现已经具备：

- 真实 dyadic level-0/1/2 local-h forest、2:1 closure、periodic/hanging trace；
- production p4/p5/p6 exact-sequence variable-p，inactive 高阶 mode 不进入全局矩阵；
- 固定 59-goal current snapshot、actual DWR、p-shadow、h-shadow 与双路径状态机；
- p6→p7 和 level-2→level-3 的 shadow-only saturation authority；
- crash-resumable Path A/B campaign、单 heavy-job lock、private artifact root；
- 两路径正式 `compare_frozen_paths`、不可变 candidate freeze receipt/bundle；
- blind campaign 完全退出后才可调用的独立 evaluator handoff/preflight。

最后一项刻意不放进 blind campaign 的 import graph：控制器只负责冻结候选，
独立 evaluator 进程随后验证 receipt/bundle，验证通过前不会打开 sealed
reference。这样不会为了方便 orchestration 而破坏三层隔离。

这些内容当前只获得 software/component qualification，不等于 reference、
blind candidate、hidden audit 或 Hybrid 数值通过。Case098 ledger 在正式 MPI8
运行写入前仍保持 `SCAFFOLD_NOT_RUN`。
