# PARA-Task006：Zero-Copy Audit Architecture Qualification for All-Slab Learned PC

```text
status = planned / research-only continuation
branch = ChatGPT/20260715-para-task-neural-local-pc
predecessor = PARA-Task005
ordinary_default_changed = false
production_claim_allowed = false
model_training_allowed = false except reuse of frozen Task005 R4 checkpoints
branch_management = prohibited
master_operations = prohibited
```

本任务不继续扩大模型容量，也不训练 16 个新模型。它专门解决 PARA-Task005 的决定性阻塞：

```text
private exact-audit CSR = 40.458 MiB / owner
+ smallest admissible learned models = 27.824 MiB / owner
= 68.282 MiB / owner
```

目标是在不保存每-rank 私有完整 local CSR 副本的条件下，建立并资格化：

```text
strict low-storage proxy
+ periodic exact local audit
+ injected-failure detection
+ drift detection
+ fail-closed runtime
```

通过后，才允许在后续任务中恢复 PARA-Task005 的 P3：训练和筛选 16 个 independent slab-specific learned inverses。

## 入口

- [任务书](task.md)
- [PARA-Task005 审阅报告](../para_task005_comprehensive_all_slab_learned_pc/review_report_v1.md)
- [PARA-Task005 结果总结](../para_task005_comprehensive_all_slab_learned_pc/outcomes/summary.md)
- `outcomes/summary.md`：执行后维护
- `review_report_vN.md`：ChatGPT 审阅

## 核心边界

- 不训练新的 full-16 learned models；
- 不运行 learned-active no-hidden-ILU global candidate；
- 不运行 h3/h2；
- 不改变 two-step smoother、post-smooth、75D coarse 或 right FGMRES90；
- exact audit 必须复用已有 operator action、临时对象或可证明的小型 sketch，不得持久复制完整 local CSR；
- proxy 资格化是冻结问题上的经验安全证据，不得宣称对任意未知误差具有数学上的绝对零漏检保证；
- 所有工作只允许在现有分支进行，不执行任何分支或 `master` 操作。

## 主要成功条件

```text
private persistent local CSR bytes = 0
proxy false accept = 0 on frozen qualification corpus
all required injected failures detected
periodic exact audit detects injected drift within frozen latency bound
R4 live shadow numeric result unchanged because ILU still writes back
learned model + proxy + buffers <= 33.670 MiB / owner preferred
or <= 50.505 MiB / owner speed-first guard
projected Task005 owner path remains <= 11.514 ms / one-level apply
```

Task006 只决定 audit architecture 是否允许 Task005 从 P3 恢复，不自动恢复训练。