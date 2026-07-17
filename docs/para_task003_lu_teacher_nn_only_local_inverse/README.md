# PARA-Task003：LU-Teacher NN-Only Local Inverse Feasibility

```text
status = planned / research-only continuation
branch = ChatGPT/20260715-para-task-neural-local-pc
ordinary_default_changed = false
branch_management = prohibited
master_operations = prohibited
```

本任务研究在当前完整 3D Maxwell 两级 FGMRES 框架中，使用高精度局部 sparse LU 生成 teacher labels，训练不依赖 ILU 输入、ILU 输出或 ILU residual 的 **NN-only local inverse**：

```text
raw local residual r_s
-> learned local inverse
-> z_s^NN ≈ A_s^{-1} r_s
```

任务先在 h5 的单个代表 slab 上验证 teacher、exact-LU oracle 上限、NN-only 局部质量和真实 factor-removal；通过后才扩展到三个代表 slab。本 Task 不训练 16 个模型，也不研究通用模型；其目标是先回答“NN 独立替代 ILU 是否可行”。

## 入口

- [任务书](task.md)
- `outcomes/summary.md`：执行后维护
- `review_report_vN.md`：ChatGPT 审阅
- `response_vN.md`：执行者回应审阅

## 核心边界

- 高精度 LU 只用于离线 teacher 和 exact-local-oracle，不进入最终 NN-only runtime；
- 训练标签不得来自 ILU、当前 PC 或其 residual correction；
- selected slab 的正式 factor-removal candidate 不得构造或保留 ILU factor；
- 保留 exact condensed operator、right FGMRES、75D coarse、full true residual 和 official R/T/A；
- 强制顺序：slab-9 LU teacher/oracle → slab-9 NN-only → 条件扩展 slab 0/10；
- 16-slab、通用模型、h3、h2 均不属于本 Task；
- 仅在现有分支写代码和文档，不执行任何分支或 `master` 操作。
