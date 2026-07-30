# Task035e：无参考解、多层局部 h/p 自适应

## 最终状态

```text
task = Task035e
branch = codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity
final_reviewed_head = 27ca26718b9ee60215243bcc98ffafcd46bfd221
classification = PARTIAL_WITH_CONTROLLED_NEGATIVES_CLOSED
ordinary_default = unchanged
reference_certification = pass
true_local_h_local_p_capability = pass
automatic_reference_blind_hp_cycle = incomplete
accepted_adaptive_candidate = none
hidden_final_audit = not_run
direct_selective_trace_lane = closed_controlled_negative
hybrid = not_run
iterative = not_run
```

Task035e 已正式停止继续改变 local face 数量、trace threshold、ranking 公式或 blind campaign 状态机。完整研究分支继续保留，下一项目路线转向 static-condensed Full3D iterative 与 Hybrid iterative。

最终审阅报告：

```text
docs/task035e_reference_blind_multilevel_hp_adaptivity/review_report_v1.md
```

---

## 1. 本任务原本要解决什么

Task035e 在 13.5 nm 下模拟未来 0.7 nm 的困难：自适应程序看不到完整收敛解，只能依据 current solution、residual、adjoint、p-shadow、h-shadow 和资源预算，自动决定哪里细化 h、哪里提高 p、何时停止。

正式输出固定为 59 个目标：

```text
16 order powers
32 complex-amplitude real/imag components
5 totals
6 field goals
```

固定级次为 top/bottom、`n=0`、`m=0,-1,...,-7`。不因弱级次功率小而将其删除。

---

## 2. 已完成且可信的结果

### 2.1 三点 global-p6 reference

| 模型 | 网格 | 59-goal | peak | 结论 |
|---|---:|---:|---:|---|
| p6/h10 | `(6,3,14)`；252 cells | 59/59 | 14.466988 GiB | 当前容差下通过 |
| p6/h7.5 | `(9,4,20)`；720 cells | 59/59 | 31.880505 GiB | 与 h5 高度一致 |
| p6/h5 | `(12,5,28)`；1,680 cells | 59/59 | 77.945587 GiB | best available discrete endpoint |

全部三对模型均为 59/59，h7.5→h5 最大差仅为 `0.00441636 tau`。p6/h5 `factor_nnz` 的 PETSc int32 overflow 已依据同一 MUMPS raw telemetry 离线修正为 `2,277,000,000`；没有重跑 PDE。

### 2.2 true local-h / local-p capability

已建立并实际运行：

- level 0/1/2 dyadic local-h forest；
- 2:1 balance、periodic/material closure、hanging H(curl) trace；
- p4/p5/p6 active exact-sequence space；
- inactive high-order modes 不进入 global rows、matrix NNZ 或 factor；
- assembly-time static condensation 与完整场恢复；
- MPI8 current、p-shadow、h-shadow；
- distributed 59-goal adjoint/DWR。

Path A cycle 0：

| stage | leaves | FE DoF / rows | whole-job peak | status |
|---|---:|---:|---:|---|
| current | 160 | 59,264 / 20,202 | 8.17 GiB | pass |
| p-shadow | 160 | 62,284 / 20,564 | 8.15 GiB | pass |
| h-shadow | 181 | 66,434 / 22,189 | 10.237 GiB | pass |

### 2.3 内存生命周期优化

- field-goal p6 basis 改为逐 cell 流式；
- h-transfer 临时对象提前释放；
- actual candidate 在 field output 前释放 KSP/MUMPS factor、system matrix、RHS 和 solver vector。

最后一次 candidate 的 sum RSS 从 `11,123.977 MiB` 降至 `6,905.078 MiB`，但正式峰值仍由 MUMPS factorization 决定。生命周期释放不计为 h/p structural gain。

---

## 3. 未成功的主线

### 3.1 cellwise action prediction

- four-cell selected-p：19/59 factor-two，25/59 opposite-sign；
- single-cell p4→p5：0/59 factor-two-or-neutral，30/59 opposite-sign；
- post-action global estimator 也未证明 single-cell candidate 改善。

结论：cellwise full-shadow attribution 只能保留为 ranking/diagnostic signal，不能当作 selected-action endpoint response predictor。

### 3.2 structured selective trace

| 模型 | 59-goal | peak | status |
|---|---:|---:|---|
| H10 p5-trace/p6-interior M1 | 52/59 | <9.78 GiB historical upper bound | accuracy fail |
| projection 200 face orbits | 50/59 | 13.004 GiB | accuracy+resource negative |
| goal-DWR 16 face orbits | 49/59 | 10.929794 GiB | resource pass，accuracy fail |

最终 16-orbit 候选对被显式优化的 6 个独立目标全部恢复为通过，说明 signed DWR 与 face-orbit quotient 本身有效；但 10 个原本通过的旁路目标越界，完整 normalized L2 恶化 `91.342535%`。

因此：

```text
direct selective trace = closed
second batch = not_run
threshold retune = not_run
ranking-formula retune = not_run
```

### 3.3 保留的受控负结果

以下结果均保留在审阅提交
[`27ca26718b9ee60215243bcc98ffafcd46bfd221`](https://github.com/Rookie1234567/MyFEniCS/tree/27ca26718b9ee60215243bcc98ffafcd46bfd221)
的 Task035e 历史中，不得因 master 只做文档合并而删除或改写为成功：

| lane | 结论 |
|---|---|
| four-cell selected-p | 数值/资源通过，但 action prediction 仅 19/59 factor-two、25/59 opposite-sign |
| single-cell p-up | 数值/资源通过，但 action prediction 为 0/59 factor-two-or-neutral、30/59 opposite-sign |
| post-action global estimator | single-cell remaining estimator 恶化 0.144216%；four-cell endpoint distance 恶化 47.7963% |
| broad-p C2/P3 | 59-goal E2 分别恶化约 9.22% |
| isotropic-h H2/H3 | E2 只改善约 0.021%/0.022%，却显著增加 rows、factor 和 DoF |
| projection 200-orbit trace | 50/59，13.004 GiB；精度和资源同时失败 |
| goal-DWR 16-orbit trace | 49/59，10.929794 GiB；资源通过但完整多目标精度失败 |

---

## 4. 为什么 Task035e 不是成功，也不是“h/p 无效”

- h 和 p 都能改善离散结果；
- true local-h/local-p、静态凝聚和 DWR 组件均有正证据；
- 失败的是在完整 59-goal 合同下，自动选择一个低内存 local h/p 子空间；
- 没有 accepted transition、cycle 1、Path A/B frozen consistency 或 hidden final audit；
- 因此不能声明 `REFERENCE_BLIND_HP_ACCURACY_PASS`。

---

## 5. 代码与 master 的处置

本任务不建议整分支合并 master，也不建议立即合并新增 source code。

```text
merge now:
    final review and project documentation only

retain on Task035e branch:
    blind controller / hidden auditor / campaign orchestration
    Task035e DWR and shadow modules
    multilevel local-h research extensions
    goal-oriented selective-trace research algebra
    reference certifier package
    p7 / level-3 saturation
    Case098 detailed records and intermediate plans
```

未来需要某一底层模块时，应建立独立、小范围 extraction task，去掉 Task035e contracts、hash orchestration 和未完成状态机后再资格化。

---

## 6. 下一步

下一任务建议为：

```text
Static-condensed Full3D iterative
→ Hybrid direct 59-goal qualification
→ Static-condensed Hybrid iterative
→ one larger-scale extension point
```

先固定 p6/h10 Full3D direct 作为迭代法权威参考，开发 FGMRES 与 FEM-trace/DtN block preconditioner；不在同一任务中重启 h/p controller。

---

## 7. 主要证据入口

master 的 documentation-only integration 不包含 Task035e source、outcomes 或
Case098 records。可在 master 直接阅读：

- [最终 Review V1](review_report_v1.md)；
- [项目模型总账 §3.40](../development_model_registry.md#340-task035ereference-blind-多层-local-hp-自适应)；
- [Case098 closed historical index @ `cef2793`](https://github.com/Rookie1234567/MyFEniCS/blob/cef2793fbc3157f8b0f65a51a395954fe5cb38bb/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/README.md)。

完整原始合同、outcomes、compact evidence、plans 和受控负结果继续固定在
[`27ca267...` 历史快照](https://github.com/Rookie1234567/MyFEniCS/tree/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity)
与其后续纯文档提交所在的 Task035e 研究分支；master 不复制这些文件。
