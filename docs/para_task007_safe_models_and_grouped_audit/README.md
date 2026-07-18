# PARA-Task007：Safer Learned Local Inverses and Graph-Certified Grouped Borrowed Audit

```text
status = planned / research-only continuation
branch = ChatGPT/20260715-para-task-neural-local-pc
predecessor = PARA-Task006
ordinary_default_changed = false
production_claim_allowed = false
branch_management = prohibited
master_operations = prohibited
```

本任务同时推进两条互补路线：

1. **Lane A：提高 learned local inverse 本身的 per-sample 安全性**，重点解决 Task006 中 `A_D0_R64` 在 Q0 上出现 `58/1024` harmful outputs 的问题；
2. **Lane B：将 borrowed exact audit 从逐 slab 串行 collective 改造成图耦合认证后的 grouped audit**，在不保存 private local CSR 的前提下降低 exact audit 成本。

两条路线必须分别通过 Gate，并在 R4 live shadow 中联合验证。任何一条失败，都不得恢复 PARA-Task005 的 full-16 P3。

## 入口

- [任务书](task.md)
- `outcomes/summary.md`：执行后维护
- `review_report_vN.md`：ChatGPT 审阅
- `response_vN.md`：执行者回应审阅

## 核心边界

- 只允许在冻结 R4 `{0,5,9,15}` 上进行有限、预冻结的模型改进；不得训练 16 个新模型；
- 重点关注 slab 5/9 的 harmful outputs 和尾部 residual；
- grouped audit 必须由真实离散矩阵图或严格 action certificate 证明 cross-coupling 条件，不能凭几何距离或 two-color 名称假设；
- private persistent local CSR 必须继续为 0；
- borrowed exact action 仍是局部 residual 权威；
- one-step smoother、h3/h2、跨波长/角度 operator 泛化和 ordinary default 不属于本任务；
- 只有本任务通过最终 ChatGPT review，后续独立任务才可恢复 Task005 P3。

## 前序硬事实

```text
Task006 borrowed action:
16/16 slabs action equivalence <= 6.030e-16
private persistent local CSR = 0
single-slab collective audit mean = 6.207 ms

Task006 proxy:
best non-harmful acceptance = 43.37%
best two-seed acceptance = 42.96%
worst slab false reject = 81.89%

Task005 A_D0_R64 on Q0:
harmful = 58 / 1024
slab 0/5/9/15 = 2 / 31 / 23 / 2
```

这些数字是本任务的起点，不是未来成功声明。
