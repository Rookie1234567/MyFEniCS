# PARA-Task002：Batched Low-Overhead Neural Smoother Acceleration

```text
status = planned / research-only continuation
branch = ChatGPT/20260715-para-task-neural-local-pc
ordinary_default_changed = false
branch_management = prohibited
master_operations = prohibited
```

本任务承接 PARA-Task001 的负性能结论，但不延续其“单 slab、NumPy 小调用、ILU 后额外叠加 NN”的实现方式。核心目标是验证：通过 owner-local 批量执行、低开销 reduced operator、融合/抽样安全检查，以及真正替代 inner GMRES action 或部分 ILU，能否在保持 full true residual 与 official R/T/A 的前提下获得真实 wall-time 或内存收益。

## 入口

- [任务书](task.md)
- `outcomes/summary.md`：由执行者完成实验后创建并维护
- `review_report_vN.md`：由 ChatGPT 审阅时创建
- `response_vN.md`：由执行者回应审阅时创建
- 前置审阅：[`../para_task001_neural_local_pc_acceleration/review_report_v1.md`](../para_task001_neural_local_pc_acceleration/review_report_v1.md)

## 任务边界

- 继续保留 exact condensed operator、right FGMRES、75D coarse、full true residual 和 official R/T/A；
- 第一阶段只做 h5 microbenchmark 与 one-slab/owner-batch A/B；
- 不允许直接运行 h3/h2；
- 不允许在线训练；
- 不允许把当前 research branch 合并到 `master`；
- 不进行任何分支创建、切换、移动、合并、rebase 或删除操作；
- 重型 dataset、CSR、checkpoint、profiler 和完整场继续写入 Git ignored artifacts。
