# Task035e 最终审阅报告 V1

## 0. 审阅结论

```text
task = Task035e
branch = codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity
branch_base = 3f334313a55786778de70965585bcaef7c997e89
reviewed_head = 27ca26718b9ee60215243bcc98ffafcd46bfd221
classification = PARTIAL_WITH_CONTROLLED_NEGATIVES_CLOSED
ordinary_default_changed = false
reference_certification = pass
true_local_h_local_p_capability = pass
full_59_goal_blind_hp_cycle = incomplete
accepted_adaptive_candidate = none
hidden_final_audit = not_run
direct_selective_trace_lane = closed_controlled_negative
hybrid = not_run
iterative = not_run
```

Task035e 不应登记为 h/p 自适应成功，也不能登记为“h/p 无效”。准确结论是：

1. 三点高阶参考、真实多层 local-h、p4/p5/p6 active space、静态凝聚、MPI8、59-goal 伴随与 DWR 等底层能力已建立并通过相应组件或数值 Gate；
2. h/p 富集确实会显著改变并可改善解；
3. 但本任务没有找到一套自动、reference-blind、低于 11 GiB、同时保持全部 59 个目标的 accepted candidate；
4. 最终 direct selective-trace 候选只对被显式优化的目标有效，却使其他已通过目标越界，因此该路线按冻结规则关闭；
5. 下一步不应继续在 Task035e 中改变 face 数量、阈值或排名公式，而应转入静态凝聚 Full3D/Hybrid 迭代法。

本审阅不建议把 Task035e 整个分支合并到 master。选择性合并结论为：

```text
master merge now = documentation-only
source-code merge now = none
research branch retained = yes
future extraction candidates = yes, but only after independent refactor/qualification
```

---

## 1. 审阅范围

本报告审阅了：

- 正式任务书与两个 fast-hp 补充任务书；
- Task035e README、Case098 README、全部主要 outcome；
- p6/h10、p6/h7.5、p6/h5 三点参考及 59-goal compact；
- Path A/B、current、p-shadow、h-shadow、cellwise、selected-p、single-cell、post-action、structured anchor、projection trace 和 goal-oriented trace 证据；
- 与 master 的 48-commit 文件差异；
- `stage4_local_h.py`、variable-p/reduction/transfer、DWR、goal gradients、shadow transfer、blind controller、reference certifier、hidden auditor、selective trace、solver lifecycle 等主要代码；
- capability matrix、development model registry 和项目路线文档。

本报告不把 ignored 的 47 MB hidden package、场采样向量或大矩阵复制进 Git。它们继续按原 SHA 保存在 Task035e 工作站 artifact 中。

---

## 2. 原任务合同与实际完成情况

| 原任务要求 | 实际结果 | 状态 |
|---|---|---|
| p6/h10、h7.5、h5 三点收敛 reference | 三个 MPI8 direct solve 全部完成；59/59；pairwise 59/59 | pass |
| 59 个固定反演输出 | 16 power + 32 amplitude components + 5 totals + 6 fields 已冻结 | pass |
| 真正 p4/p5/p6 active space | inactive modes 不进入全局 rows/NNZ/factor | pass |
| 真正多层 local-h | level 0/1/2、2:1、periodic/hanging、MPI8 可运行 | capability pass |
| current / p-shadow / h-shadow | Path A cycle 0 三者完成；全局 endpoint DWR 59/59 | pass |
| 自动 cellwise h/p action prediction | four-cell 与 single-cell actual 均否定其定量预测 | fail |
| cycle 0 accept/reject 后进入 cycle 1 | 无 accepted action；cycle_advanced=false | incomplete |
| Path A/B 独立收敛 | Path B 只有 partial v27；无 frozen candidate | incomplete |
| p7 / level-3 saturation 后冻结 | 软件组件存在；未形成最终 candidate 认证 | incomplete |
| hidden final audit | 未有可冻结 candidate | not_run |
| Full3D hp ≤11 GiB 且全部目标通过 | 无候选同时满足 59/59 与 ≤11 GiB | fail |
| Full3D 成功后接 Hybrid | Full3D 前置 Gate 未通过 | not_run |

Task035e 最终应记录为：组件能力通过、参考认证通过、自动 blind h/p 主目标未完成。

---

## 3. 最重要的正式数值结果

### 3.1 三个 global-p6 reference

| 模型 | 网格 / cells | FE DoF / rows | matrix / factor NNZ | 59-goal | peak | elapsed |
|---|---:|---:|---:|---:|---:|---:|
| p6/h10 | `(6,3,14)` / 252 | 173,802 / 51,272 | 41,989,040 / 202,441,352 | 59/59 | 14.466988 GiB | 166.392 s |
| p6/h7.5 | `(9,4,20)` / 720 | 488,070 / 145,232 | 119,738,672 / 708,620,576 | 59/59 | 31.880505 GiB | 825.415 s |
| p6/h5 | `(12,5,28)` / 1,680 | 1,127,502 / 337,040 | 279,032,240 / 2,277,000,000 corrected | 59/59 | 77.945587 GiB | 4,380.997 s |

Pairwise 最大 `abs(delta)/tau`：

```text
h10  vs h7.5 = 0.500000
h7.5 vs h5   = 0.00441636
h10  vs h5   = 0.504386
```

全部 59 项均满足 fine increment 不大于 coarse increment。当前工程容差下，p6/h10 已通过；p6/h7.5 与 h5 高度一致；p6/h5 保留为 best available discrete endpoint。

p6/h5 的 PETSc `factor_nnz=-2017967296` 是 int32 telemetry overflow。依据同一 raw MUMPS `INFOG(9)=-2277`，正式解释为 2,277,000,000 entries，原始负值继续保留。

### 3.2 Path A cycle 0

| stage | leaves | p4/p5/p6 cells | FE DoF / rows | matrix / factor NNZ | whole-job peak | status |
|---|---:|---:|---:|---:|---:|---|
| current | 160 | 24/136/0 | 59,264 / 20,202 | 10,798,392 / 41,217,460 | 8.17 GiB | pass |
| p-shadow | 160 | 15/138/7 | 62,284 / 20,564 | 11,084,868 / 43,034,248 | 8.15 GiB | pass |
| h-shadow | 181 | 24/157/0 | 66,434 / 22,189 | 11,821,621 / 41,744,755 | 10.237 GiB | pass |

这证明真正 variable-p、多层 local-h、hanging/Floquet、静态凝聚和全局 59-goal DWR 可以组合运行。它不等于自适应 cycle 已成功，因为尚未有 accepted transition。

### 3.3 cellwise action predictor 关闭

- four-cell selected-p actual：19/59 factor-two-or-neutral，25/59 opposite sign；
- single-cell p4→p5 actual：0/59 factor-two-or-neutral，30/59 opposite sign；
- post-action global estimator 也未显示该 single-cell action 改善。

结论：full-shadow 的 cellwise attribution 可作位置诊断，但不能冒充任意 selected action 的 endpoint response predictor。

### 3.4 structured H10 fixed trace 与 selective trace

| 模型 | rows | matrix / factor NNZ | 59-goal | peak | 结论 |
|---|---:|---:|---:|---:|---|
| H10 p5-trace/p6-interior M1 | 35,000 | 20,140,928 / 101,141,150 | 52/59 | <9.78 GiB historical upper bound | 低内存但精度不足 |
| projection 200 face orbits | 39,000 | 24,696,176 / 116,348,600 | 50/59 | 13.004 GiB | accuracy+resource negative |
| goal-DWR 16 face orbits | 35,320 | 20,492,976 / 93,656,300 | 49/59 | 10.929794 GiB | resource pass，accuracy fail |
| global p6/h10 | 51,272 | 41,989,040 / 202,441,352 | 59/59 | 14.466988 GiB | accuracy anchor，resource fail |

最终 16-orbit 候选对被显式优化的 6 个独立物理目标全部预测正确并恢复为通过，说明 signed DWR、B/S/F hierarchy 和 orbit pairing 本身有效；但 10 个旁路输出越界，完整 normalized L2 恶化 91.34%。因此 direct selective-trace 不是可交付的完整多目标方案。

### 3.5 内存生命周期

最后一次 actual candidate 在 field output 前销毁 KSP/MUMPS factor、system matrix、RHS 和 solver vector：

```text
sum RSS before release = 11,123.977 MiB
sum RSS after release  =  6,905.078 MiB
released               =  4,218.898 MiB
```

这证明后处理对象重叠可以消除，但正式峰值仍发生在 MUMPS factorization。该生命周期优化不能计为 h/p structural gain。

---

## 4. 代码审阅结论

### 4.1 已经证明有价值的代码

以下代码有明确技术价值，但不代表应立即进入 master：

1. **多层 local-h / variable-p**
   - level 0/1/2 staged forest；
   - p4/p5/p6 complete degree map；
   - 2:1、periodic、material、hanging、MPI ownership；
   - zero-h fixed-trace 与 selective physical-face research plan。

2. **分布式 actual DWR**
   - `r=b-Ax`、`A^H z=g`、`eta=Re(z^H r)`；
   - owner-local vectors，无 Python full-vector gather；
   - current/shadow identity 与 cellwise partition。

3. **goal-oriented selective-trace algebra**
   - exact B/S/F hierarchy；
   - 774 periodic physical face-orbit quotients；
   - Gram-corrected signed pairing；
   - selected-goal DWR 的 actual 预测得到验证。

4. **reference certification**
   - 三点收敛、uncertainty、field sample aggregation；
   - p6/h10、h7.5、h5 正式 reference 资格化。

5. **内存实现经验**
   - field-goal p6 basis 改为逐 cell 流式；
   - h-transfer 大临时对象提前释放；
   - factor/postprocess 生命周期分离。

### 4.2 不宜合并的过度基础设施

以下内容规模大、与 Task035e 状态机和 evidence schema 强耦合，而且没有形成最终成功闭环：

- `src/adaptivity/blind_controller/*`；
- `src/adaptivity/hidden_auditor/*`；
- `benchmarks/task035e_blind_campaign.py`、bootstrap、handlers、stages、bindings；
- Path A/B crash-resume、receipt、freeze、handoff、hash orchestration；
- p7/level-3 saturation 全套 campaign bridge；
- 大量中间 schema、preflight、watchdog wrapper 和重复 plan records。

这些文件可以保存在 Task035e branch，作为研究复现和失败证据，不应进入 ordinary master 开发路径。

### 4.3 为什么本轮不建议源代码合并

尽管部分底层代码通过组件测试，本轮仍不建议把任何新增 Task035e source 文件直接选择性合并 master，原因是：

1. master 已有 Task035d 的静态凝聚、true local-p/local-h 与 exact-sequence 核心，可直接支撑下一项迭代法任务；
2. Task035e 新数值模块多数仍依赖 Task035e contracts、hash identity、research observers 和 Case098 结构；
3. 没有 accepted adaptive candidate，无法定义稳定的生产入口和使用合同；
4. 下一任务是 Full3D/Hybrid 迭代法，不需要 blind controller、p7 saturation 或 selective-trace runner；
5. 立即合并会把失败的控制策略和大量防御性基础设施带入 master，增加维护成本。

因此本轮的安全选择是：

```text
保留完整 Task035e branch
master 只合并最终文档和能力状态
未来若需要某一底层算法，单独建立小型 extraction task
```

---

## 5. Selective merge 决策

### 5.1 立即合并 master：文档

| 文件 | 决策 | 说明 |
|---|---|---|
| `docs/task035e.../review_report_v1.md` | merge | Task035e 最终 authority 与后续路线 |
| `docs/task035e.../README.md` | merge final concise version | 不再保留“正在 cycle0”的过时叙述 |
| `docs/capability_matrix.md` | update + merge | 把 selective trace 从 not_implemented 改为 research_only controlled negative；增加 Task035e 状态 |
| `docs/development_model_registry.md` | update + merge | 保留三点 reference、M1、两条 selective negative、最终 closure |
| `docs/project_service_requirements_and_forward_model_roadmap.md` | update + merge | Task035e 收口；下一步改为 static-condensed Full3D iterative → Hybrid direct 59-goal → Hybrid iterative |
| `benchmarks/cases/098.../README.md` | merge only if kept as historical index | 必须标记 closed research case，不作为 production benchmark |

### 5.2 保留在 Task035e branch，不合并 master

| 文件族 | 原因 |
|---|---|
| `src/adaptivity/task035e_*` | 强 Task035e 合同耦合；无 accepted cycle |
| `src/adaptivity/blind_controller/*` | 状态机/身份/receipt 过重且未完成正式闭环 |
| `src/adaptivity/reference_certifier/*` | 有价值但应先抽取成通用 convergence utility |
| `src/adaptivity/hidden_auditor/*` | 仅服务未完成的 blind campaign |
| `src/adaptivity/goal_oriented_selective_trace.py` | selected-goal mechanism pass，完整多目标 production fail；保留 research_only |
| `benchmarks/task035e_*` | campaign/evidence orchestration，不属于普通求解入口 |
| `Case098 records/*` 大量中间 JSON | 研究证据已由最终 report/compact 索引；不应污染 master |
| `fast_hp_sprint*` workers/plans | 一次性 development experiment |
| p7/level-3 modules/tests | 未进入最终冻结候选，不是下一任务前置能力 |

### 5.3 未来可独立抽取，但不得直接 cherry-pick 整包

1. `reference_certifier/convergence.py`：抽取为通用三点网格收敛/uncertainty utility；
2. `goal_oriented_selective_trace.py`：抽取 exact B/S/F trace quotient algebra，状态 `research_only`；
3. `task035e_actual_dwr.py`：去除 blind contracts/hash 后抽取 distributed multi-RHS adjoint/DWR kernel；
4. `stage4_local_h.py` 中 multilevel plan：在不规则或局部缺陷几何真正需要时单独资格化；
5. goal-gradient streaming 与 h-transfer cleanup：若未来 adjoint/adaptive task复用，再以性能补丁方式抽取。

每项抽取都应是小任务、少文件、独立测试、明确生产入口；不得再次把完整 Task035e campaign 一起搬入 master。

---

## 6. 文档维护要求

Task035e 收尾后，文档口径必须统一为：

```text
reference certification = pass
component capability = pass
automatic blind hp = incomplete
direct selective trace = closed controlled negative
production candidate = none
Hybrid / iterative = not_run
ordinary default = unchanged
```

必须删除或改写以下过时说法：

- “Task035e 正在准备进入第一个 cycle”；
- “selected-p / selected-h 尚未运行”；
- “selective physical p6 trace not_implemented”；
- “下一步继续改变 trace threshold”；
- “Task035e 完成后才能考虑迭代法”。

保留所有 controlled negative，不得因路线关闭而删除：

- four-cell selected-p；
- single-cell p-up；
- post-action audit；
- broad-p / isotropic-h sprint negatives；
- projection 200-orbit negative；
- goal-DWR 16-orbit negative。

---

## 7. 下一任务建议

下一任务建议冻结为 `Task035f`，不再扩展 Task035e：

### Phase A：Static-condensed Full3D iterative

固定唯一资格化对象：

```text
Full3D p6/h10
assembly-time static condensation
auxiliary DtN
MPI8
59-goal direct authority reused
```

目标：FGMRES + FEM-trace/DtN block preconditioner；先只做 primal，不接 h/p、adjoint、inverse 或参数扫描。

### Phase B：Hybrid direct 59-goal qualification

在开始 Hybrid iterative 前，先用当前冻结的 59-goal inventory 比较：

```text
Hybrid static p6/h10 M120 direct
vs
Full3D p6/h10 direct
```

迭代法不能修复 modal truncation error，因此 direct Hybrid 必须先通过。

### Phase C：Static-condensed Hybrid iterative

复用 Full3D FEM trace PC；对 modal/interface block 使用 block triangular 或 approximate Schur PC。

### Phase D：一个扩展点

只有 h10 两条迭代路径通过后，才运行一个 h7.5 或更大 M 扩展点。不得同时重启 h/p controller。

---

## 8. 最终审阅意见

Task035e 的研究价值主要在于把问题定位清楚：

- h/p、静态凝聚和 goal-oriented DWR 都有实际作用；
- 但在完整 59-goal 合同下，少量 local trace 模式会产生强 collateral coupling；
- direct MUMPS 的 factor memory 仍是核心资源瓶颈；
- 继续修改局部 face 集合不会高效解决 0.7 nm 问题。

因此本任务应在此处正式收口。完整分支作为研究档案保留，master 不吸收未交付的自动控制框架；项目主线转入静态凝聚迭代法和 Hybrid 迭代法。
