# Task035d：目标量驱动、保持 exact sequence 的局部 h/p 自适应

## 当前身份

```text
status = PARTIAL_WITH_CONTROLLED_NEGATIVES
execution_branch = codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
base = 9c2160d41382026352908d692ad479dc4508424d
ordinary_default = unchanged
irregular_geometry = out_of_scope
iterative_solver = out_of_scope_until_hp_space_freezes
matrix_free_low_memory = out_of_scope_until_hp_and_iterative_close
full3d_hp_production_candidate = none
hybrid_phase_f = not_run_full3d_hp_gate_failed
```

Task035c 已按 Review V2 完成选择性整合；本执行分支从上述干净
post-Task035c master 创建。Task035d 已完成 reference active-space、真实
assembly-time local-p、2:1 balanced hexa local-h、H(curl) hanging/Floquet
约束、compiled cell tensor、PETSc ownership、静态凝聚、完整场恢复和
MPI1/2/8 identity 的同一离散架构。所有正式候选都真实删除 inactive rows，
没有构造完整 p6 矩阵后置零。

正式 MPI8 研究先关闭 p-only lane，随后运行 h15 local-h、combined hp、
factorial bridge、十面 selective-p6-trace 和 bounded single-root local-h
判别点。最强资源结果达到 `76,205` active FE DoF、`18,470` rows、
`7.29866 GiB`；最终 left-grating 判别点为 `88,915` DoF、`21,650` rows、
`8.06120 GiB`，相对 p6/h10 static 的 rows、matrix NNZ、factor NNZ 和峰值
分别下降 `57.77%/70.51%/82.46%/45.24%`。但正式候选最佳显著通道仍只有
`6/12 powers + 6/12 amplitudes`，没有任何候选达到 `12/12 + 12/12`。

因此本任务按任务书定义归类为
`PARTIAL_WITH_CONTROLLED_NEGATIVES`。bounded single-root top-air local-h
lane 在两个正式精度负信号后关闭；outer-periodic、multi-seed 和整个
top-port selective-trace 能力分别保留为 `not_run_by_lane_stop`、
`not_evaluated_by_stop_rule` 和 `incomplete_not_run`，不得误写成数值失败。
Full3D hp Gate 未通过，所以 static Hybrid M120 Phase F 没有运行。

## 这个任务要解决什么问题

Task035/035b已经证明：

- 提高阶次通常比全域缩小网格更高效；
- DWR局部h可以工作；
- `p5-trace/p6-interior`和方向性h能明显压缩规模；
- 但尚未形成一个真正自动、同一离散架构中的local-h/local-p循环；
- 预算内最强h13候选仍有弱衍射级没有达到p6/h10参考精度。

Task035d要完成的不是再扫描几个`p/h`组合，而是建立：

```text
准确p6/h10参考
→ 多目标误差与局部平滑性分析
→ 真实local-p active space
→ 真实local-h约束
→ h/p成本收益竞争
→ 重算与12通道严格审计
```

“真实local-p”表示不活跃高阶模式根本不生成global row，不进入NNZ和MUMPS因子，而不是在完整p6矩阵中把系数设为零。

“真实local-h”表示局部单元被细分，并通过H(curl)兼容的悬挂trace或共形过渡保持切向连续，不是给整个z方向统一增加一层。

## 固定研究范围

当前只研究：

- Task034固定矩形块光栅；
- 13.5 nm；
- S偏振，10°掠入射；
- axis-aligned affine hexa主线；
- p6/h10 Full3D static与Case096 reference-v1；
- static Hybrid M120作为Full3D候选通过后的下游验证。

不研究：曲面、斜侧壁、圆角、粗糙度、缺陷、任意不规则几何、四面体静态凝聚、混合网格、迭代求解器和0.7 nm外推。

## 开始前必须阅读

- 根目录 `AGENTS.md`；
- `docs/AGENTS.md`；
- Task035 `review_report_v6.md` 与 `outcomes/summary.md`；
- Task035b `review_report_v4.md` 与最终outcomes；
- Task035c `review_report_v2.md`、`response_v1.md` 与全部outcomes；
- Case094、Case095、Case096 README和compact authority；
- `docs/development_model_registry.md`；
- 本目录 `task.md`。

## 主要交付

```text
docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/
    outcomes/summary.md
    outcomes/test_summary.md
    response_vN.md

benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/
```

并同步更新 `docs/development_model_registry.md`。
