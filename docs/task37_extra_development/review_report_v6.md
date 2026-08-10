# Task037-extra Review Report V6：H1R3.0 实质通过、审计闭合修复与后续缩放 Gate

## 0. 审阅身份与最终决定

```text
review                         = Task037-extra Review Report V6
working_branch                 = codex/20260806-task37-iterative-extra-development
reviewed_measurement_source    = 003b8fa185b59bb424e60331d336d2d976d0563f
reviewed_evidence_head         = 1ce637e1085a5315bd9d97abb101d3fac559cc28
reviewed_response              = docs/task37_extra_development/response_v5.md
reviewed_outcome               = docs/task37_extra_development/outcomes/h1r3_warm_repeat.md
H1R2                           = ACCEPTED_PASS
H1R3_0_measurement             = ACCEPTED_SUBSTANTIVE_PASS
H1R3_0_formal_qualification    = NOT_PASS_DUE_TO_AUDIT_SCHEMA_OMISSION
H1R3_0_timeout                 = FALSE
new_authorized_stage           = H1R3_0R_NARROW_AUDIT_CLOSURE
H1R3_1                         = CONDITIONALLY_AUTHORIZED_AFTER_H1R3_0R_PASS
H1R3_2                         = CONDITIONALLY_AUTHORIZED_AFTER_H1R3_1_PASS
H2                             = LOCKED_PENDING_COMPLETE_H1R3_REVIEW
H3_H4_full_PDE                 = PROHIBITED
G2_LOR_HX                      = G2_FAIL_FROZEN
G3_additive_LOR_HX             = PROHIBITED
old_G4_sweep                   = PROHIBITED
create_new_branch              = FORBIDDEN
pull_request                   = FORBIDDEN
merge_to_master                = PERMANENTLY_NOT_PLANNED
ordinary_default_change        = FORBIDDEN
```

本审阅接受 H1R3.0 原始运行所证明的数值、重复调用、时间、内存、canonical 与
provenance 事实；同时保留其正式 `GATE_FAILED` 状态，因为 worker audit 中缺少两个
必须显式存在的 inventory 字段：

```text
cell_schur_matrix_nnz
slab_matrix_nnz
```

本轮失败不是超时，不是内存越界，不是 swap，不是数值误差，也不是重复调用导致的
RSS 爬升。正式 worker 在约 `26.72 s` 内完成，`controlled_stop=null`。因此用户所说的
“时间长一点可以接受”不影响这次失败的根因，也不需要通过延长 timeout 来修复。

V6 只授权一次窄审计闭合：在 candidate 的真实 audit 中增加上述字段并由 focused test
证明它们确实为零；禁止只在 checker 中给缺失字段默认填零。修复后允许一次同配置的
H1R3.0R 正式重跑。只有该次重跑正式通过，才可依序进入 MPI2 分区身份 H1R3.1 和
p6/h5 缩放 H1R3.2。

---

# 1. 关于“超时”的准确解释

## 1.1 历史 H1.2 的确曾经超时

旧 H1.2 在 `1800 s` 后受控停止。后来 Review V3 已经确认，旧实现每次 MatMult、每个
单元都重新生成并定向完整 `882 x 882` 稠密单元 tensor，再做 dense GEMV。该路径的
p6 单元内核不具备 h-refinement 可扩展性，历史超时不能通过“再等久一点”解决。

H1R.1 随后将内核改为 direct rank-one residual action，不再在每次 apply 中形成 dense
cell tensor；H1R2 已在 p6/h10、MPI1 上以约 `14.13 s` 完成单源 action-only Gate。

## 1.2 最新 H1R3.0 没有超时

最新 H1R3.0 的正式资源事实为：

| 项目 | 实测值 |
|---|---:|
| completion elapsed | `26.716238772962242 s` |
| watchdog wall | `26.72631202498451 s` |
| controlled stop | `null` |
| process-tree peak | `335233024 B` |
| swap | `0` |
| candidate applies | `12` |

因此当前没有理由延长 H1R3.0 timeout。即使允许更长时间，缺失 audit 字段仍然会让同一
checker fail-closed。

## 1.3 后续允许更宽的总 wall，但不放宽 action 缩放 Gate

用户可以接受较长 setup/mesh/form compile 时间。V6 因此把后续 watchdog timeout 视为
安全上限，而不是唯一科学性能指标：

```text
H1R3.0R timeout = 180 s
H1R3.1  timeout = 600 s
H1R3.2  timeout = 1800 s
```

但是 action 的稳定性和单位行时间 Gate 不放宽。原因是最终目标为 p6/h1；若 action
seconds/row 随 h-refinement 明显恶化，即使当前愿意等待，也无法形成长期可扩展方案。

---

# 2. H1R3.0 原始运行审阅

## 2.1 已通过的实质性 Gate

| Gate | 实测 | 审阅结论 |
|---|---:|---|
| first error | `2.7326039504560278e-17` | PASS |
| last error | `2.7326039504560278e-17` | PASS |
| finite | `true` | PASS |
| bitwise deterministic | `true` | PASS |
| 12 次 output SHA | 完全一致 | PASS |
| apply 5--12 median | `1.1308611669810489 s` | PASS |
| timing limit | `1.494291376147885 s` | PASS |
| retained payload | `6151104 B`，12 次稳定 | PASS |
| packed temporary | `3556224 B`，12 次稳定 | PASS |
| steady RSS span | `0 B` | PASS |
| completed process-tree peak | `335233024 B` | PASS |
| Review V5 0.45 GiB Gate | `335233024 <= 483183820` | PASS |
| user decimal 2 GB Gate | `335233024 < 2000000000` | PASS |
| swap | `0` | PASS |
| canonical packets | `164592`，duplicates `0` | PASS |
| source start/end | same clean SHA | PASS |

这组数据足以支持如下实质结论：

> 当前 p6/h10 full-space rank-one matrix-free volume action 可以连续重复调用，数值不漂移，
> retained/temporary bytes 不增长，process-tree RSS 不爬升，且稳定 apply 时间约为
> `1.13 s`。

这仍然只是 action layer 结论，不是 KSP/PDE 收敛结论。

## 2.2 唯一正式失败根因

当前 `HcurlRankOneMpcAction.audit` 已明确写出：

```text
global_matrix_materialized              = false
global_constraint_matrix_materialized   = false
global_condensed_schur_materialized     = false
retained_dense_cell_tensor_count        = 0
dense_cell_tensor_materialized_per_apply = false
factor_count                            = 0
ksp_created                             = false
dtn_used                               = false
```

但 H1R3.0 evaluator 还要求两个更窄的 inventory key：

```text
cell_schur_matrix_nnz = 0
slab_matrix_nnz       = 0
```

worker audit 没有这两个 key，evaluator 正确地将缺失字段判为 false，没有把 `missing`
猜成 `0`。因此：

```text
worker.qualification_pass = true for numerical/resource subgates
worker.status              = gate_failed because inventory gate is incomplete
watchdog.status            = worker_failed
watchdog.return_code       = 1
```

这是证据合同遗漏，不是算法遗漏。现有 raw 不能被静默改写为 PASS；必须保留为历史
`gate_failed` authority。

---

# 3. 代码审阅与修复边界

## 3.1 缺失字段应写在哪里

必须在实际 action 对象建立 audit 的位置写出，而不是在 checker 中补默认值。目标文件为：

```text
src/solvers/hcurl_rank_one_mpc_action.py
```

在 `HcurlRankOneMpcAction.__init__()` 创建 `_audit` 时增加：

```text
cell_schur_matrix_nnz = 0
slab_matrix_nnz       = 0
```

建议同时显式增加：

```text
cell_schur_matrix_materialized = false
slab_matrix_materialized       = false
```

后两个字段用于增强可读性，但正式 checker 的必要字段仍以前两个精确 `nnz=0` 为准。

这些值必须与实现事实一致：当前 candidate 只保留 coefficient Function、output Vec、常数、
扁平 MPC metadata/work arrays；没有任何 cell Schur 或 slab matrix 构造路径。

## 3.2 禁止的“修复”方式

以下做法不被授权：

- 在 evaluator 中使用 `audit.get(key, 0)`；
- 在 compact checker 中把 missing 自动改写为 0；
- 直接编辑旧 raw `run_summary.json`；
- 修改旧 compact record 的 measurement 字段；
- 删除历史 `gate_failed` 记录；
- 以相邻字段为依据对旧 raw 做推断式 PASS；
- 同时改变 action 算法、packing、MPC reduction 或内存生命周期。

本轮只修 audit schema，不改数值路径。

## 3.3 必须增加的 focused test

在现有 H1R2/H1R3 测试中增加明确断言：

```text
"cell_schur_matrix_nnz" in audit
"slab_matrix_nnz" in audit
audit["cell_schur_matrix_nnz"] == 0
audit["slab_matrix_nnz"] == 0
```

若增加 materialized 布尔字段，还应断言：

```text
audit["cell_schur_matrix_materialized"] is False
audit["slab_matrix_materialized"] is False
```

测试还必须保留：

- assembled/reference/candidate error `<=1e-11`；
- repeat deterministic；
- no dense/global/factor；
- payload component closure；
- evaluator 在字段缺失时仍 fail-closed；
- evaluator 在字段显式为零时通过 inventory 子 Gate。

---

# 4. H1R3.0R：唯一一次审计闭合正式重跑

## 4.1 固定配置

```text
degree / h / MPI       = p6 / h10 / MPI1
source                 = seed_17037
reference applies      = 1
candidate applies      = 12
canonical export       = once, after numerical Gate
timeout                = 180 s
process-tree peak Gate = 0.45 GiB
swap                   = 0
KSP / DtN / PDE        = forbidden
```

除新增 audit 字段外，数值代码、source、repeat、threads 和环境全部冻结。

## 4.2 Gate

H1R3.0R 必须同时满足 Review V5 原 Gate与新增 inventory closure：

```text
all 12 outputs finite and bitwise deterministic
first/last relative error <= 1e-11
apply 5--12 median <= 1.494291376147885 s
retained payload exactly stable
packed temporary exactly stable
steady RSS span <= 64 MiB
completed peak <= 0.45 GiB
swap = 0
completion <= 180 s
cell_schur_matrix_nnz = 0 and key present
slab_matrix_nnz = 0 and key present
```

## 4.3 证据保存

旧 H1R3.0 raw 与 compact record保持不变。新重跑使用新目录和新 record：

```text
benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v6_*/
benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat_v2.json
docs/task37_extra_development/outcomes/h1r3_warm_repeat_v2.md
```

不得覆盖：

```text
benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat.json
docs/task37_extra_development/outcomes/h1r3_warm_repeat.md
```

新的 consolidated handoff 写入：

```text
docs/task37_extra_development/response_v6.md
```

---

# 5. H1R3.1：p6/h10 MPI2 分区身份

只在 H1R3.0R 正式 PASS 后进入。

## 5.1 固定范围

```text
p6 / h10 / MPI2
source = seed_17037
reference = 1
candidate = 2
timeout = 600 s
canonical authority = H1R2 MPI1 manifest
KSP / DtN / PDE = forbidden
```

较宽 timeout 只容纳 MPI startup、form compile、mesh partition 和 canonical I/O；action
性能 Gate不放宽。

## 5.2 Gate

```text
same-run candidate/reference relative error <= 1e-11
finite and deterministic
MPI2 vs MPI1 canonical relative L2 <= 1e-12
missing / extra / duplicate = 0 / 0 / 0
packet count = 164592
retained global-sum / global rows <= 45 bytes/row
candidate second apply <= 2 * same-run reference
candidate second apply <= 2.390866201836616 s
completed process-tree peak <= 0.75 GiB
swap = 0
completion <= 600 s
```

必须报告 process-tree 总峰值与 global-sum payload，不能只报告单 rank。

若数值和内存都通过但总 wall 较长，应分别报告 setup、reference apply、candidate apply、
canonical export；不得仅凭较长 setup 判定 action 科学失败。

---

# 6. H1R3.2：p6/h5 MPI1 h-refinement scaling

只在 H1R3.1 正式 PASS 后进入。

## 6.1 固定范围

```text
p6 / h5 / MPI1
source = seed_17037
reference = 1
candidate = 2
timeout = 1800 s
full canonical export = false
KSP / DtN / PDE = forbidden
```

h5 的较宽安全 timeout 响应用户“时间长一点可以接受”的要求，但核心 action
seconds/row Gate保持不变。必须用细粒度 marker区分 mesh、space、MPC、form compile、
reference apply、candidate apply和 summary。

## 6.2 缩放量

```math
\alpha_{payload}
=
\frac{\log(M_{h5}/M_{h10})}
{\log(N_{h5}/N_{h10})}.
```

```math
b_{peak}
=
\frac{P_{h5}-P_{h10}}
{N_{h5}-N_{h10}}.
```

其中：

```text
M = retained numeric payload global sum
P = completed process-tree peak
N = full-space global rows
```

## 6.3 Gate

```text
relative error <= 1e-11
finite and deterministic
retained payload / row <= 45 bytes/row
packed temporary / row <= 28 bytes/row
alpha_payload <= 1.10
action seconds / row <= 1.03171980264e-5
b_peak <= 512 bytes/row
completed process-tree peak <= 0.75 GiB
swap = 0
completion <= 1800 s
```

如果总 wall 超过旧 300 s 但 action seconds/row、内存和数值 Gate 全部通过，必须准确
分类为“setup/wall 较长但 action scaling 通过”，不能因用户愿意等待而删除 action time
Gate，也不能因总 wall较长而误判为 action kernel失败。

必须给出 p6/h1 action-only 线性外推：

```math
P_{h1,pred}
=
P_{h10}
+
b_{peak}(N_{h1}-N_{h10}).
```

该外推只属于 action layer；不能称为 full solver 的 2 TiB qualification。

---

# 7. H2 仍然锁定

即使 H1R3.0R、H1R3.1 和 H1R3.2 全部通过，Codex 也不得自动进入 H2。

原因是目前只证明或正在证明：

```text
A_h x 的低存储精确作用
```

尚未证明：

```text
M^{-1} r 作为有效低存储近似逆
```

凝聚 B2/B4 的长尾已经说明，低成本 action 不等于可收敛 solver。H1R3 全部通过后，
下一次审阅最多考虑 H2.0 block-class inventory 与 coercive one-apply contraction；不会
直接授权原时谐 KSP/PDE。

---

# 8. Hard stops

以下任一项发生，立即停止后续阶段并提交真实 evidence：

1. H1R3.0R 新 audit 字段仍缺失或不为零；
2. 数值误差、determinism、payload、RSS 稳定性回归；
3. MPI2 canonical missing/extra/duplicate 非零；
4. MPI2 partition relative L2 超限；
5. h5 payload exponent `>1.10`；
6. h5 action seconds/row、peak slope 或总峰值超限；
7. 出现 global matrix、Schur、cell/slab matrix、factor 或 dense tensor；
8. 需要修改 ordinary default、安装依赖、新建分支或改变物理问题；
9. weekly quota 显示为 0。

禁止：

- 修改旧 raw；
- checker 默认补零；
- 无证据原样重跑；
- 同时开发多个 action backend；
- 启动 H2/H3/H4/KSP/PDE/DtN/RTA；
- 重开 LOR-HX 或 sweep；
- new branch / PR / master merge。

---

# 9. 测试、提交与输出合同

## 9.1 最小测试

修复提交前至少运行：

```text
test_280_task037_extra_h1r2_mpc_rank_one_action.py
test_282_task037_extra_h1r2_watchdog_checker.py
test_283_task037_extra_h1r3_warm_repeat.py
```

并覆盖：

- audit key presence/value；
- missing-key fail-closed；
- explicit-zero pass；
- existing numerical/payload contracts；
- compileall；
- git diff --check。

不安装 Ruff；若环境没有 Ruff，准确写 `unavailable`。

## 9.2 Git 约束

只在：

```text
codex/20260806-task37-iterative-extra-development
```

工作和 push。禁止创建子分支、PR、rebase、force push、cherry-pick 或 master 合并。

## 9.3 执行顺序

```text
R0  narrow audit-field implementation + focused tests
R1  commit/push clean implementation
R2  one H1R3.0R formal run and checker
R3  if and only if R2 PASS: H1R3.1 MPI2
R4  if and only if R3 PASS: H1R3.2 h5
R5  consolidate response_v6.md, commit/push, stop for review
```

每个正式 run 必须使用已提交、已 push、clean 且与 upstream一致的源码。正式 run后不得
修改同一 raw；checker修复只能在独立证据中明确说明，不能改 measurement。

---

# 10. 给执行 Codex 的摘要

```text
继续只在 codex/20260806-task37-iterative-extra-development 工作。
完整阅读 response_v5.md、review_report_v5.md 和 review_report_v6.md，V6 为最高优先级。

最新 H1R3.0 不是 timeout：26.7 s 完成，数值/时间/内存/12次重复全部通过；
正式失败仅因 audit 缺少 cell_schur_matrix_nnz 和 slab_matrix_nnz。

先只做窄修复：在真实 candidate audit 中显式写两个字段为 0，并增加 focused tests；
禁止在 checker 中给 missing 默认补 0，禁止修改旧 raw。

测试通过后提交并 push，再运行一次 H1R3.0R。新 evidence 使用 v2 文件名，保留旧
h1r3_warm_repeat evidence 不变。

只有 H1R3.0R PASS 才进入 H1R3.1 MPI2；只有 MPI2 PASS 才进入 H1R3.2 h5。
后续允许更宽 watchdog wall，但 action time/row 和内存缩放 Gate 不放宽。

不得进入 H2/H3/H4/KSP/PDE/DtN/RTA，不得新建分支或 PR，不得修改 master。
最终更新 response_v6.md，提交并只 push 当前 extra 分支，然后停止等待审阅。
```
