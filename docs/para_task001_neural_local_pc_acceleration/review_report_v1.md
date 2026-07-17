# REVIEW REPORT V1：PARA-Task001 Neural Local PC 最终审阅

## 0. 审阅结论

```text
review = PARA-Task001 review_report_v1
branch = ChatGPT/20260715-para-task-neural-local-pc
reviewed_implementation_sha = ee5d248e09aaff3700f22805024ce0abc2e25822
review_status = PASS_WITH_QUALIFICATIONS
numerical_result = PASS
local_neural_feasibility = PASS
performance_result = FAIL
memory_result = NO_SAVING
final_classification = h5_numeric_pass_engineering_negative
h3_allowed = false
h2_allowed = false
ordinary_default_changed = false
production_claim_allowed = false
merge_to_master = NOT_REQUESTED_AND_NOT_APPROVED
branch_management = explicitly_out_of_scope_by_user_instruction
```

PARA-Task001 已完成一个可信的研究闭环：神经网络能够在真实 complex Maxwell slab 上学习局部修正，one-slab ILU+NN 候选保持 full true residual、official R/T/A 与能量闭合，但没有获得工程加速，且没有节省内存。当前 POD-MLP 单 slab 路线必须以负性能结果收口，不得进入 h3/h2，不得提升为 production profile。

本报告只在现有 research branch 中记录审阅结论。按照用户明确要求，不创建、移动、合并、rebase、删除或更新任何分支，不对 `master` 做任何操作。

---

# 1. 审阅范围

本轮重点审阅：

```text
docs/para_task001_neural_local_pc_acceleration/task.md
docs/para_task001_neural_local_pc_acceleration/outcomes/summary.md
docs/para_task001_neural_local_pc_acceleration/outcomes/experiment_matrix.csv
docs/para_task001_neural_local_pc_acceleration/outcomes/local_action_metrics.csv
docs/para_task001_neural_local_pc_acceleration/outcomes/runtime_breakdown.csv
docs/para_task001_neural_local_pc_acceleration/outcomes/memory_report.md
docs/para_task001_neural_local_pc_acceleration/outcomes/model_and_dataset_provenance.md
docs/para_task001_neural_local_pc_acceleration/outcomes/merge_recommendation.md
benchmarks/cases/090_neural_local_pc_acceleration/
src/solvers/local_slab_solver.py
src/solvers/neural_local_pc.py
src/solvers/physical_slab_two_level.py
benchmarks/neural_pc/
benchmarks/run_workstation_iterative.py
src/test/test_31_neural_local_pc.py
src/test/test_32_neural_slab_petsc_adapter.py
src/test/test_33_para_task001_contract.py
```

重型 dataset、CSR、checkpoint、raw profiler 和完整运行日志位于 Git ignored artifact 目录，本报告接受 outcomes 中记录的 checksum、provenance 和轻量结果，但没有在审阅端重新运行 WSL MPI4/GPU 重型实验。

---

# 2. 任务合同执行情况

## 2.1 可信求解框架保持不变：通过

实现没有用 NN 替代真实 Maxwell 算子，也没有绕过数值 Gate。以下内容保持原路径：

- exact condensed operator `F-C H^-1D`；
- outer right FGMRES；
- 75D true-action Galerkin coarse correction；
- physical-slab ownership、overlap weighting 和 MPI scatter；
- full explicit condensed/full augmented true residual；
- official modal R/T/A 和 volume absorption；
- ordinary solver default。

NN 只作为 local slab backend 或 ILU residual-correction backend。这一插入边界符合任务书，也避免把代理模型误当作高保真求解器。

## 2.2 数据与训练合同：通过

实现完成了：

- portable complex local CSR；
- operator fingerprint、checkpoint checksum 和 metadata；
- bounded real Krylov RHS capture；
- synthetic/teacher/real-Krylov/ILU-residual 数据路径；
- offline PyTorch GPU training；
- frozen runtime inference；
- 独立 validation run；
- 大型训练数据和 checkpoint 不提交 Git。

没有保存完整全局 `A/b` 作为训练集，也没有在正式求解中在线反向传播。

## 2.3 Runtime 安全：通过

实现包括：

- finite output 检查；
- output norm sanity；
- local residual ratio；
- checkpoint schema/checksum/fingerprint；
- NN-only fail closed；
- ILU+NN non-degradation；
- fallback 计数和诊断；
- deterministic repeated inference。

这些保护使 one-slab 候选即使 NN 失效，也不会静默污染最终全局解。

---

# 3. 接受的数值结果

## 3.1 Toy local feasibility：通过

固定 toy 配置：

```text
samples = 1024
POD rank = 48
hidden width = 128
batch = 512
epochs = 300
seed = 20260717
GPU training = 3.679 s
```

独立 validation：

| 指标 | 结果 |
|---|---:|
| local rho median | 0.133051 |
| local rho p95 | 0.145946 |
| correction error median | 0.133512 |
| determinism error | 0 |
| frozen NumPy inference mean | 35.3 µs |
| frozen NumPy inference p95 | 52.7 µs |

该结果证明 reduced POD-MLP 可以学习一个受控 complex sparse 局部逆动作，但不等同于真实 full-3D 全局加速。

## 3.2 真实 slab 9：局部修正有正信号

真实 h5 slab-9 rank256/hidden512 模型在独立 `ilu_residual` validation 上达到：

```text
rho median = 0.5733
rho p95 = 0.7116
```

运行时 5124 次调用：

```text
accepted calls = 5124
fallback = 0
rho median = 0.3779
rho p95 = 0.5303
```

这说明模型确实能够改善被选择 slab 的 ILU 剩余误差，并不是完全无效的随机修正。

## 3.3 全局 h5 数值正确性：通过

one-slab ILU+NN 结果：

```text
condensed true residual = 9.903219e-7
full augmented true residual = 9.903219e-7
R = 0.0890216041
T = 0.4425882733
A = 0.4683901210
energy closure = -1.529e-9
max R/T/A delta from baseline/direct < 2e-9
```

因此：

```text
numerical correctness Gate = PASS
```

---

# 4. 性能结果：失败

正式同机 MPI4 h5 A/B：

| h5 run | iterations | solve s | total s | peak GiB |
|---|---:|---:|---:|---:|
| original ILU baseline | 861 | 93.312 | 156.746 | 1.602940 |
| one-slab ILU+NN | 854 | 412.318 | 452.641 | 1.654888 |

变化：

```text
iteration reduction = 7 = 0.813%
solve time ratio = 4.419x slower
total time ratio = 2.888x slower
peak memory change = +3.241%
```

任务书要求 h5 同 action baseline wall time 至少下降 20%。当前候选不只是未达 Gate，而是明显反向退化。

```text
h5 performance Gate = FAIL
h3 unlock Gate = FAIL
h2 unlock Gate = FAIL
```

---

# 5. 性能失败根因

## 5.1 NN 只增强 16 个 slab 中的一个

只有 slab 9 获得神经修正，其余 15 个 slab 保持原 ILU。即使 slab 9 局部 residual 有明显改善，也不足以显著改变整个两级预条件器的谱性质，因此 outer iterations 仅下降 0.813%。

## 5.2 在线路径是 NumPy/Python 串行小调用

当前冻结 runtime 每次调用包含：

```text
complex pack
-> POD input projection
-> dense MLP
-> POD output reconstruction
-> local sparse actions
-> safety/non-degradation checks
-> MPI owner synchronization
```

这不是 GPU 批量推理，也没有把多个 slab 合并成高吞吐 batch。小模型理论 FLOP 很低，但 Python/NumPy 调度和内存搬运占主导。

## 5.3 安全检查重复执行局部 sparse action

Lane B 当前至少需要：

```text
ILU baseline solve
A_s z_ilu
NN correction
A_s delta / candidate check
full candidate residual check
```

统计显示：

```text
NN inference accumulated = 35.036 s
NN residual checks accumulated = 69.543 s
```

安全检查本身比网络推理更贵。

## 5.4 MPI 等待放大 owner-rank 额外成本

神经 slab 所属 rank 更慢，其他 ranks 在同步点等待，因此单 slab 的局部开销会放大为整个 MPI4 求解器的 wall time。

## 5.5 没有替代原有昂贵步骤

当前 Lane B 是：

```text
ILU + NN correction
```

原 ILU factor 和两步 smoother 都仍然存在。NN 是额外叠加层，而不是替代 inner GMRES action 或 ILU storage，因此既不省时间，也不省内存。

---

# 6. 内存结论

当前候选保留 ILU，并增加：

- 45,094,912-byte checkpoint；
- POD bases 和 MLP weights；
- portable local CSR；
- inference buffers；
- residual-check buffers。

实测峰值从 1.602940 GiB 增至 1.654888 GiB，增加 3.241%。虽然没有超过任务书 `<=10%` 的安全上限，但没有任何内存节约。

```text
memory safety guard = PASS
memory-saving claim = FAIL / NOT DEMONSTRATED
```

只有未来真正移除部分 ILU factors 或 inner Krylov buffers，才可以重新提出内存下降主张。

---

# 7. 代码与研究基础设施审阅

以下设计质量良好，允许继续留在 research branch 作为下一任务基础：

- `LocalSlabSolver` 稳定 backend 协议；
- portable complex CSR 和 action contract；
- dataset/operator schemas；
- bounded Krylov capture；
- offline GPU trainer；
- frozen checkpoint export；
- checksum/fingerprint；
- fail-closed、fallback 和 non-degradation；
- local timing/rho telemetry；
- PETSc owner-computes adapter tests；
- Case090 和完整负结果文档。

但以下内容不得提升为普通 solver：

- 当前 slab-9 checkpoint；
- current frozen NumPy POD-MLP runtime；
- one-slab ILU+NN profile；
- 由该结果外推到 all-slab、h3、h2 或多参数通用性；
- “NN 已经加速 full-3D Maxwell”的表述。

---

# 8. Slab fingerprint 风险

两次独立真实运行之间有 6/16 slab 出现位级 fingerprint 变化。当前 fail-closed 匹配是正确的，但说明：

```text
物理问题相同
!= local CSR bytes 必然完全相同
```

后续任务必须区分：

- 真正不同的局部 operator；
- 仅由 DoF ordering、MPI ownership、装配顺序或浮点舍入造成的等价表示变化。

在没有 canonical local ordering 或 action-equivalence certificate 前，不得直接放宽 fingerprint 安全检查。

---

# 9. 最终决定

| 对象 | 决定 | 原因 |
|---|---|---|
| PARA-Task001 research execution | 接受并关闭 | 完成可信正/负结果闭环 |
| numerical result | 接受 | true residual、R/T/A、closure 通过 |
| local NN feasibility | 接受 | toy 和真实 slab 均有局部正信号 |
| current one-slab runtime | 拒绝提升 | 2.888× total、4.419× solve 退化 |
| memory-saving claim | 拒绝 | 峰值增加 3.241%，ILU 未移除 |
| all-slab/h3/h2 | 不运行 | h5 性能 Gate 已失败 |
| ordinary default | 不改变 | research-only |
| master merge | 不讨论、不操作 | 用户明确禁止任何分支管理和 master 操作 |
| reusable infrastructure | 仅留在当前 research branch 继续试验 | 尚未决定是否具有长期价值 |

最终分类：

```text
PARA-Task001 = h5_numeric_pass_engineering_negative
review disposition = PASS_WITH_QUALIFICATIONS
```

---

# 10. 下一步要求

允许在同一 research branch 建立 PARA-Task002，但必须改变研究假设，不能简单把当前 one-slab POD-MLP 扩展到 16 slabs。

下一任务应优先回答：

1. 能否把多个 local operations 批量执行，消除 per-call Python/NumPy overhead；
2. 能否让 NN **替代** inner GMRES action 或部分 ILU，而不是额外叠加；
3. 能否把 local safety check 与已有 operator action 融合，或使用可审计的抽样检查；
4. 能否在 h5 one-slab microbenchmark 中先把 one-level apply cost 压到接近原 ILU；
5. 能否获得至少数量级更大的迭代数下降，而不是 0.813%；
6. 只有 h5 wall-time 达到正收益后，才讨论 all-slab、h3 或 h2。

---

# 11. 审阅状态

```text
PARA-Task001 disposition = CLOSED_AS_ENGINEERING_NEGATIVE
review_report_v1 = FINAL_FOR_CURRENT_IMPLEMENTATION
response_v1 = optional acknowledgement / no Task001 rerun required
PARA-Task002 = allowed as a new research task on the same existing branch
branch operations = prohibited
master operations = prohibited
```
