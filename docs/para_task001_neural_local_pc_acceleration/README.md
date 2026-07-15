# PARA-Task001：Neural Local PC Acceleration

```text
status = planned / research-only
branch = ChatGPT/20260715-para-task-neural-local-pc
ordinary_default_changed = false
```

本并行任务研究在当前完整 3D p2 Nédélec Maxwell 求解器中，以冻结的神经局部预条件器替换或增强 physical-slab 局部 ILU 修正，目标是减少 outer/inner Krylov 的真实 Maxwell action 次数，并评估是否能够进一步降低 local factor 内存。

## 入口

- [任务书](task.md)
- `outcomes/summary.md`：由执行者在完成实验后创建并维护
- `review_report_vN.md`：由 ChatGPT 审查时创建
- `response_vN.md`：由执行者回应审查时创建

## 任务边界

- 保留 exact condensed operator、right FGMRES、75D coarse、full true residual 和 official R/T/A；
- NN 只作为 local slab solver / ILU residual correction backend；
- 先 h5，再按 Gate 进入 h3/h2；
- 训练数据、矩阵和 checkpoint 等重型 artifact 不提交 Git；
- 本 research branch 不整体合并 production，也不改变 Task032–Task035 主路线。
