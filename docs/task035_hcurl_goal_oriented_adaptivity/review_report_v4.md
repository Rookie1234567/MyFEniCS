# Task035 Review V4：连续自主自适应研究授权

## 1. 审查结论

```text
review_status = CONTINUOUS_AUTONOMOUS_ADAPTIVITY_RESEARCH_AUTHORIZED
phase_boundaries = planning_guidance_not_review_stop_gates
review_waiting_during_research = not_required
negative_lane_policy = preserve_evidence_then_switch_direction
heavy_p4_and_later_phases = authorized_by_internal_evidence_and_resource_preflight
ordinary_default_change = not_authorized_without_final_review
master_merge = not_authorized_without_final_review_and_user_confirmation
```

本轮审查对象：

```text
branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
branch_head_at_review = a0488c4f5672c27677fcf01e05ead7cdb163d394
response = docs/task035_hcurl_goal_oriented_adaptivity/response_v4.md
final_phase_cd_record_source = db2d1e7a49f5754de8d0dec6dda3622a9635e6bb
base_master = 5002636852ffb67b4711443da70eb536c303e34e
```

Phase C/D 的结果和测试继续接受。此前将 Task035 按 Phase 分段等待审查的执行方式现已取消。`task.md` 中的 Phase A–K 仍用于组织研究问题、证据和交付物，但不再是必须停下来等待 ChatGPT 的审批关卡。

Codex 获得在当前 Task035 分支上持续研究、实现、试验和切换路线的授权。基本策略是：

```text
提出候选
→ 做最小可信实现
→ 在低成本真实问题上测量
→ 出现正信号则加深并扩大规模
→ 出现明确负信号则保存证据、关闭该 lane、切换下一候选
→ 直到形成可信 adaptive 主线，或所有合理路线均被证据排除
```

不再因为完成某个 Phase、单个候选失败、局部测试失败、文档或 schema 问题而停止等待审阅。Codex 应主动选择下一步，不需要逐阶段取得新授权。

---

## 2. 已接受的当前结论

### 2.1 Estimator

以下结果接受为方向性证据：

| coarse → enriched | R5 effectivity proxy | R5 Pearson / Spearman | sampled R1 Pearson / Spearman | observable error reduction |
|---|---:|---:|---:|---:|
| p2/h5 → p2/h3 | 0.9086 | 0.9903 / 0.9918 | -0.0356 / -0.0359 | 87.46% |
| p2/h3 → p2/h2 | 0.8106 | 0.9981 / 0.9949 | -0.0768 / -0.0622 | 81.55% |
| p3/h10 → p3/h7.5 | 0.9894 | 0.9892 / 0.9836 | -0.0202 / -0.0361 | 94.00% |

准确解释为：

- coarse/enriched field-difference R5 proxy 有很强正信号；
- sampled-grid strong residual proxy 对当前局部误差无有效相关性；
- 当前 R5 仍不是 formal hierarchical/local two-level FE estimator；
- 81%–94% 的下降来自全局 enriched 离散点，不是 estimator-marked local refinement 的因果结果；
- 下一优先方向应是 actual FE two-level estimator，而不是继续调 sampled R1 的归一化。

### 2.2 Component fixtures

B3 material-interface/corner component fixture 与 B4 Hybrid Et/Ht、M/DtN、QEP component fixture 接受。它们支持材料界面、方向性、Hybrid error split 和 MPI compact identity，但不构成新的目标 PDE adaptive qualification。

### 2.3 Mesh backend

当前工程结论为：

```text
Task034 strip/tensor = controlled_negative
Cartesian axis-cut hexa = locality blocker for that implementation family
tetra marked refinement = positive research-control signal
```

`cartesian_axis_cut_hexa` 的负结果不得扩大为“所有局部六面体自适应均不可能”。但在 tetra 最小闭环尚未成功前，不应继续把主要精力投入复杂 transition-cell/hexa 基础设施。

### 2.4 Tetra quality audit

此前体积字段采用 `abs(det(J))/6`，只能证明最小绝对体积为正，不能检测反转单元。后续正式 positive record 必须增加真正的 orientation/Jacobian audit：

```text
minimum_absolute_tetra_volume
minimum_oriented_jacobian_determinant
nonpositive_jacobian_count
quality quantiles
serial/MPI identity
```

首次 MPI2 topology-to-geometry indexing failure record 必须保留。

### 2.5 测试

以下结果接受，不要求因本 Review 重跑：

```text
C+D focused test88-test97 = 33 passed
full repository pytest = 527 passed, 18 skipped
serial/MPI2 compact identity = pass
Ruff = pass
compileall = pass
git diff --check = pass
```

Phase A 环境、MUMPS/PEP、Task034 heavy references 和完整 artifact inventory 继续有效，除非其绑定输入发生变化。

---

## 3. “解决自适应问题”的目标定义

Task035 不以“代码能 refine 一次”作为完成。可信解法至少需要形成以下闭环：

```text
TARGET SOLVE
→ ACTUAL FE ESTIMATE
→ MARK
→ PERIODIC/MATERIAL/INTERFACE CLOSURE
→ LOCAL REFINE OR hp CHANGE
→ REBUILD TAGS/FLOQUET/DtN
→ TARGET RE-SOLVE
→ PHYSICAL AND COST AUDIT
```

### 3.1 研究级成功

至少一个 p2 或 p3 Full3D sequence 满足：

- 至少两个连续 estimator-marked cycles 的目标误差下降；
- full true residual 和 official R/T/A/energy gates 通过；
- field/interface error 不隐藏恶化；
- periodic/Floquet、material tags、DtN 和 mesh-quality audits 通过；
- 相近 DoF/rows 成本下不劣于 uniform refinement control；
- serial/MPI2 一致，必要时 MPI4 一致。

### 3.2 工程级成功

在研究级成功基础上，将最佳路线推进到 p4/h5 或同等可信高阶点，并证明：

- same-error 或 improved-error；
- DoF/rows、factor fill、峰值内存或总时间至少一项有明确工程收益；
- 没有依靠放宽物理误差换取压缩；
- 不规则网格导致的 fill、负载不均衡和 field transfer 成本已实测。

### 3.3 扩展级成功

若 Full3D 主线成功，继续尝试：

- Hybrid spatial / external DtN / internal M error separation；
- selected mesh 的 Full3D–Hybrid closure；
- 1°/5°/10° S common-mesh robustness；
- global-p 与条件 hp；
- recovery/equilibrated independent audit。

这些不是开始研究前的审批锁，而是沿正信号自然推进的后续目标。

---

## 4. 自主研究决策规则

### 4.1 候选组合

Codex 同时保持最多：

```text
2 条主候选 lane
+ 1 条独立 control/audit lane
```

避免无界组合爆炸。当前优先候选为：

1. actual global two-level R5 + tetra local refinement；
2. actual cell/face R1 或 goal-oriented DWR + tetra local refinement；
3. uniform tetra refinement 作为 cost-matched control。

可根据证据切换到：

- local patch R5；
- recovery R3；
- DWR G1/G2；
- equilibrated R4；
- global-p / local-hp；
- improved hexa、prism/pyramid、octree 或 nonmatching-interface backend；
- Hybrid adaptive。

### 4.2 正信号

出现以下任一组合时，应继续加深该 lane：

- local indicator 与独立 error proxy 稳定相关；
- estimator-marked refinement 后目标 observable 实际下降；
- 连续两个 cycle 正向；
- 相近成本下优于 uniform control；
- p2 正信号可迁移到 p3；
- Full3D 正信号可迁移到 Hybrid 或 p4；
- 网格局部性、质量、周期闭合与 MPI identity 同时通过。

### 4.3 负信号

出现以下情况时保存完整证据并切换路线，不等待审阅：

- estimator 与误差无相关且 refinement 不改善 observable；
- 连续两个 cycle 无改善或明显反弹；
- backend 无法满足周期闭合、质量或局部性；
- 资源收益被 factor fill、transfer 或 imbalance 抵消；
- 某候选只能通过放宽 residual/physics Gate；
- 经过合理参数和实现修正后仍无正信号。

单个 lane 的 controlled negative 不等于 Task035 失败。

### 4.4 探索顺序

建议但不强制的路线：

```text
A. actual global two-level R5 + periodic tetra MVP
B. p2 真实 adaptive cycles + uniform control
C. p3 transfer/smoke
D. actual R1 / DWR / recovery independent comparison
E. p4 Full3D heavy mainline when lower-cost evidence is positive
F. Hybrid / M-DtN split / robust-angle extension
G. alternative hexa or hp route if tetra succeeds but production geometry requires it
```

Codex 可以根据 measured evidence 调整顺序，不需要因任务书字母阶段顺序停下来。

---

## 5. 立即优先实现的内容

### 5.1 Actual two-level R5

第一版优先选择实现速度快且可审查的路线：

```text
p2 coarse solve
+ p3 same-mesh enriched solve
→ project/compare fields
→ localize correction energy to coarse cells
```

资源不合适时可改为：

```text
p2 coarse mesh
+ uniformly refined p2 enriched solve
→ transfer/project
→ localize to coarse cells
```

必须记录：

- enriched solve residual 与 official observables；
- finite/nonnegative cell contributions；
- global indicator/correction closure；
- actual distributed cell ownership；
- marked-set hash；
- estimator time/memory；
- 不得使用保存的 sample-grid field difference 作为最终 indicator。

Global two-level MVP 成功后，再决定是否值得实现 local patch R5。

### 5.2 Actual cell/face R1 baseline

实现实际 FE mesh 上的：

```text
volume curl-curl residual
interior curl-flux jump
material/interface contribution
external DtN boundary contribution
Floquet/periodic diagnostic
```

每个 owned cell 必须有独立贡献。R1 可以得到负结果，不阻塞其他 lane。

### 5.3 Periodic tetra backend

建立 Task034 fixed geometry 的 tetra pipeline：

- x/y periodic surfaces geometrically matching；
- material cell tags；
- top/bottom DtN tags；
- periodic marker closure including edges/corners；
- refine 后 rebuild tags/Floquet/DtN；
- actual Jacobian/orientation audit；
- serial/MPI2，必要时 MPI4；
- deterministic mesh/closure/tag hashes。

### 5.4 Actual adaptive cycles

首个主线建议为：

```text
13.5 nm
10° grazing
S polarization
Task034 fixed geometry
Full3D p2
research tetra backend
actual R5 marking
Dörfler theta = 0.5
```

运行 2–4 cycles。若有正信号，继续 p3、p4、Hybrid 或 angle robustness；若无正信号，切换 estimator/backend 组合。

每轮必须输出：

```text
mesh/closure/tag hashes
cells, DoF, rows, NNZ
estimator totals/components
marked-set hash and closure expansion
full true residual
official R/T/A/A_volume/R00/orders
field/interface errors
energy closure
memory/time/fill/imbalance
mesh quality/Jacobian
```

---

## 6. Heavy run 与资源授权

本 Review 允许 Codex在内部证据支持时自行运行 p4/h5、Hybrid 和后续 heavy cases，不需要新的阶段授权。但必须遵守：

- one-heavy-case-at-a-time；
- 运行前做 rows/NNZ/memory/swap/disk/OOC preflight；
- 使用 watchdog 和完整进程组终止；
- 不设置任意短 timeout；
- 先跑最低成本可区分实验，再扩展规模；
- 正式 heavy record 绑定 clean committed source SHA；
- OOM、swap thrashing、磁盘不足或进程异常时保留证据并调整方案；
- 不得把资源终止写成数值方法失败或成功。

Codex可以在 p2/p3 未完全成功前运行少量 p4 diagnostic，以解决明确歧义，但不得无证据地进行大规模参数遍历。

---

## 7. 测试与提交节奏

### 7.1 测试金字塔

```text
小改动：targeted unit/fixture tests
一个 lane 收口：serial + MPI2，必要时 MPI4
数值核心发生变化：相关 regression/anchor
重大里程碑或最终交付：full repository pytest
```

不再要求每个 Phase 或每几个提交都运行 full pytest。文档、schema、record、lint 小问题只做 targeted rerun。

### 7.2 持续提交而不等待

Codex 应在以下时机提交并推送，但提交后继续工作：

- 一个候选实现可运行；
- 一个 measured experiment 完成；
- 一个 lane 得到 positive/controlled-negative 决定；
- 一个重型 record 完成；
- 一个重大 bug 修复并通过 targeted regression。

提交和推送不是等待审阅的停止点。

### 7.3 文档收敛

不要为普通进展创建新的 addendum 或 review。持续更新：

```text
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/test_summary.md
Case094 machine-readable records
```

只有在以下情况创建下一份 `response_vN.md`：

1. 已形成研究级或工程级 adaptive success；
2. 所有合理路线均被证据排除，需要架构决策；
3. 出现真正需要用户处理的硬 blocker；
4. 用户明确要求阶段总结；
5. 准备最终 selective merge。

创建 response 后也不必自动停止，除非属于第 2、3、5 类。

---

## 8. 真正的硬停止条件

只有以下情况需要停止整个 Task035 并请求用户或审阅：

1. 需要用户输入 sudo 密码、SSH passphrase、凭据或进行系统级人工操作；
2. WSL complex ABI、source/base hash 或 accepted evidence 身份发生无法解释的不一致；
3. 发现 accepted production core 或历史 evidence 被错误修改/污染；
4. MPI、true residual、official physics 或 mesh orientation 出现系统性错误且继续运行会制造虚假结论；
5. 内存、swap、磁盘、OOC 或进程状态存在工作站安全风险；
6. 所有合理 estimator/backend/hp/Hybrid 路线均已形成可审计负结果，继续只会重复已有实验；
7. 准备改变 ordinary default；
8. 准备合并 `master` 或结束 Task035。

以下情况不得停止整个任务：

- 单个 estimator 或 backend 失败；
- 一个 heavy case 资源终止；
- 一个 MPI/fixture bug 原因明确且可局部修复；
- 某个 Phase 得到 pass 或 controlled negative；
- README、schema、record、lint、链接或 metadata 问题；
- 某条路线需要换参数、换实现或换候选。

---

## 9. 最终边界

本 Review 授权 Task035 剩余研究阶段的持续执行，包括低成本和重型 Full3D、Hybrid、p/h/hp、robust-angle 和独立 estimator audit。Phase 名称不再构成审批锁。

但以下事项仍必须在最终审阅和用户确认后执行：

```text
将 research capability 宣称为 production default
改变 ordinary user-facing default
把 Task035 分支合并到 master
删除或改写 controlled-negative/failed evidence
```

Codex 应以解决自适应问题为目标持续探索，但不能保证预先存在一个一定成功的方法。若最终没有路线满足研究级成功标准，也必须给出“哪些路线已排除、根因在哪里、下一架构应是什么”的完整工程结论。