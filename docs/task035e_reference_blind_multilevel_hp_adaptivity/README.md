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

Task035e 的软件预资格已完成，数值研究已进入 partial Path A cycle 0。当前实现
已经具备：

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

这些软件能力本身仍只属于 component qualification。数值进度另由 Case098
的 hash-bound progress checkpoint 记录；严格最终 `config.json` 继续保持
`SCAFFOLD_NOT_RUN`，因为其 schema 不能安全表达 partial cycle。

截至 2026-07-29，Path A cycle 0 的 current、完整 p-shadow、完整 h-shadow
和 cellwise partition 均已通过。在 numerical source
`f1ba5627f163da54fa383b43be58fd38c0da7bc9` 上又只运行了一条获授权的
selected-p actual candidate。该 candidate 的 residual、energy、Floquet、
hanging、MPI8、11 GiB 和 zero-swap Gate 全部通过，但既有四-cell DWR
预测相对 actual candidate-current 只有 `19/59` 落在 factor-two 范围，且
`25/59` 符号相反。因此 action 被保存为 controlled negative，cycle 0 current
继续保留，`cycle_advanced=false`。

详细结论见：

- [selected-p actual outcome](outcomes/path_a_cycle0_selected_p_actual.md)；
- [selected-p hash-bound checkpoint](../../benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_a_cycle0_selected_p_actual_checkpoint_v1.json)。

selected-h、Path B 新运行、cycle 1 shadow、p7/level-3、hidden audit 和 Hybrid
均未启动。Task035e 仍为 partial research，而不是最终 blind hp 成功。

随后又按单独授权只验证
`cell:r42:l1:i1:j0:k0 : p4 -> p5`。这条 single-cell candidate 的全部数值与
资源 Gate 通过，实际只增加 132 个 cell-interior modes、16 个 face modes、
148 个 Full3D-equivalent DoF 和 16 个 augmented rows；whole-job memory
authority 为 7.560097 GiB、swap 为 0。但既有单-cell DWR prediction 为
`0/59` factor-two-or-neutral、`30/59` opposite-sign，其中 53 个正式逐级与
总量目标有 24 个符号相反。因此 candidate 同样 rejected，cycle 0 current
继续保留，当前 cellwise-p quantitative predictor 正式关闭。

新增证据与后续离线设计见：

- [single-cell p-up actual outcome](outcomes/path_a_cycle0_single_cell_p_actual.md)；
- [single-cell hash-bound checkpoint](../../benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_a_cycle0_single_cell_p_actual_checkpoint_v1.json)；
- [cellwise-p estimator repair design](outcomes/cellwise_p_estimator_repair_design.md)。

cellwise partition 只能保留为无定量 credit 的 ranking signal。在
entity/mode-orbit 或 exact selected-action DWR 先通过既有 single/grouped raw
actual candidates 的离线回放前，不再开放其他 selected-p cell 或 selected-h。
