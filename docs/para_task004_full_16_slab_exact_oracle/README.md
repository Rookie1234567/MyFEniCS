# PARA-Task004：Full 16-Slab Exact-Local-Inverse Oracle

```text
status = planned / research-only continuation
branch = ChatGPT/20260715-para-task-neural-local-pc
ordinary_default_changed = false
branch_management = prohibited
master_operations = prohibited
```

本任务不训练神经网络。它先回答一个更基础的问题：

```text
当全部 16 个 physical slabs 都使用 exact local inverse，
并且对应 ILU factors 真正不构造、不保留时，
当前 two-level FGMRES 架构的 outer iterations、operator actions、时间和内存
最多能够改善多少？
```

PARA-Task003 已证明：

```text
slab 9 exact LU       : 860 -> 862 iterations
slab 0/9/10 exact LU  : 860 -> 840 iterations (-2.33%)
```

少量 selected slabs 的 exact inverse 缺乏足够全局杠杆，但该结果不能否定全 16-slab replacement。本 Task 使用 4/8/16-slab oracle 梯度，并比较：

```text
Lane A = all-exact + current two-step smoother
Lane B = all-exact + one-step smoother
```

只有 full 16-slab exact oracle 显示明确全局收益，后续任务才允许讨论：

```text
16 个独立 NN-only models
3 类 expert models
shared trunk + slab adapters
```

## 入口

- [任务书](task.md)
- `outcomes/summary.md`：执行后维护
- `review_report_vN.md`：ChatGPT 审阅
- `response_vN.md`：执行者回应审阅

## 核心边界

- h5、MPI4、13.5 nm、当前 Si grating、16 slabs、75D coarse、right FGMRES90 全部冻结；
- exact-enabled slab 不得构造或保留 ILU factor；
- 本 Task 不生成训练数据、不训练模型、不创建 checkpoint；
- 强制顺序：no-hidden-ILU lifecycle → 4 slabs → 8 slabs → 16 slabs two-step → 条件 one-step；
- full residual、official R/T/A 和 energy closure 始终保留；
- h3/h2、通用模型和任何 production claim 均不属于本 Task；
- 仅在现有分支写代码和文档，不执行任何分支或 `master` 操作。