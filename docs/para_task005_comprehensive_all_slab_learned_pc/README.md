# PARA-Task005：Comprehensive All-Slab Learned Local Inverse Capability Qualification

```text
status = active / P1 complete / research-only continuation
branch = ChatGPT/20260715-para-task-neural-local-pc
predecessor = PARA-Task004
ordinary_default_changed = false
production_claim_allowed = false
branch_management = prohibited
master_operations = prohibited
```

本任务研究当前完整 3D Maxwell 两级 FGMRES 架构中，**全部 16 个 physical slabs 的 learned local inverse** 是否能够在不构造任何 ILU factor 的条件下，保留 PARA-Task004 全 exact-local-inverse oracle 的主要谱收益，并真正获得全局 wall-time 加速。

核心 runtime 目标保持：

```text
raw local residual r_s
-> slab-specific learned local inverse
-> z_s^learned ≈ A_s^{-1} r_s
```

第一优先级是 16 个独立 slab-specific 模型，作为 fixed-operator 能力与工程上限实验。只有该上限 profile 通过 full global Gate，才允许在本任务后段比较三类 expert 模型和 shared trunk + slab adapters。

## 入口

- [任务书](task.md)
- [P0 环境与基线](outcomes/p0_environment_and_baseline.md)
- [P1 数据与教师报告](outcomes/data_and_teacher_report.md)
- [P1 逐 slab 教师摘要](outcomes/p1_teacher_summary.csv)
- `outcomes/summary.md`：执行后维护
- `review_report_vN.md`：ChatGPT 审阅
- `response_vN.md`：执行者回应审阅

## 核心边界

- 训练输入只能是 raw local residual 与任务书明确允许的 slab/operator metadata；
- teacher label 只能来自高精度 local sparse LU 或严格资格化的高精度 local solve；
- 不得使用 ILU output、ILU residual 或当前 PC output 作为 teacher；
- 正式 factor-removal profile 中 16 个 ILU factors 均不得构造，ILU apply 与 hidden fallback 必须为 0；
- 保留 Task004 验证的 two-step smoother、post-smooth、75D coarse 与 right FGMRES90；
- one-step smoother 只作为 Task004 负证据，不在本任务重新提升；
- 第一阶段固定 h5、MPI4、13.5 nm 当前 Si 光栅与当前 operator；
- h3/h2、跨角度/波长 operator 泛化和 ordinary default 均不属于本任务自动范围；
- 重型 dataset、LU factors、checkpoint、raw profiler 与完整日志必须放在 Git-ignored artifacts；
- 只允许在现有分支新增或修改 Task005 相关文件，不执行任何分支或 `master` 操作。

## Task004 给出的硬预算

```text
exact-oracle baseline iterations = 861
exact G16 two-step iterations = 566
oracle iteration/action reduction = about 34.26%

20% speed target solve <= 71.352 s
independent model end-to-end local budget <= 2.878 ms/slab call
owner batch budget <= 11.514 ms/four-slab batch
memory-neutral storage <= 33.670 MiB/owner rank
```

这些只是 Task005 的进入门槛和规划预算，不是已经实现的 NN 性能。
