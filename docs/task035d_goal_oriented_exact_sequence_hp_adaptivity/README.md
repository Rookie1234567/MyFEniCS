# Task035d：目标量驱动、保持 exact sequence 的局部 h/p 自适应

## 当前身份

```text
status = staged_after_Task035c
execution_branch = create_after_Task035c_master_merge
planned_branch = codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
base = exact post-Task035c master SHA
ordinary_default = unchanged
irregular_geometry = out_of_scope
iterative_solver = out_of_scope_until_hp_space_freezes
matrix_free_low_memory = out_of_scope_until_hp_and_iterative_close
```

本目录先保存在Task035c分支中，随Task035c选择性合并进入master。**ChatGPT不提前创建Task035d分支。** Codex只有在Task035c成功整合master、测试通过并确认工作树干净后，才从新master创建上述Task035d分支。

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