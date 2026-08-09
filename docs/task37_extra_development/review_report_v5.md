# Task037-extra Review Report V5：H1R2 正式通过与 H1R3 分布式/细化缩放资格化

## 0. 审阅身份与最终决定

```text
review                         = Task037-extra Review Report V5
working_branch                 = codex/20260806-task37-iterative-extra-development
reviewed_measurement_source    = 66ccb5891b7f6caac3ebfe08f72cf525c40f3fef
reviewed_evidence_head         = bfc740ac1bd2da962ccf4c7660a307a9446b7c4c
reviewed_response              = docs/task37_extra_development/response_v4.md
reviewed_outcome               = docs/task37_extra_development/outcomes/h1r2_single_source_action.md
H1R2                           = ACCEPTED_PASS
H1R2_scope                     = p6/h10, MPI1, single-source, full-space volume action only
H1R3                           = AUTHORIZED_WITH_SEQUENTIAL_GATES
H2                             = LOCKED_PENDING_H1R3_REVIEW
H3_H4_full_PDE                 = PROHIBITED
G2_LOR_HX                      = G2_FAIL_FROZEN
G3_additive_LOR_HX             = PROHIBITED
old_G4_sweep                   = PROHIBITED
create_new_branch              = FORBIDDEN
pull_request                   = FORBIDDEN
merge_to_master                = PERMANENTLY_NOT_PLANNED
ordinary_default_change        = FORBIDDEN
```

本审阅接受 H1R2 的正式数值、资源、canonical 和 provenance 证据。H1R2 是当前
extra 分支第一次在真实 p6/h10 完整 Nédélec 空间中证明：

- 不物化 global matrix；
- 不静态凝聚；
- 不保存 cell/slab factor；
- 不在每次作用中生成 dense `882 x 882` cell tensor；
- 仍能以接近现有 DOLFINx/MPC authority 的时间完成精确 action。

但是，H1R2 仍然只是一条单源、MPI1、h10、无 DtN、无 KSP 的 action-only 证据。
它不能被写成 full-space factor-free PDE 已经可收敛，也不能被写成 p6/h1 已经满足
2 TiB 预算。

下一步不直接进入 H2。V5 只授权 H1R3 的三段顺序资格化：

```text
H1R3.0  MPI1 warm-repeat / allocator-lifecycle Gate
H1R3.1  p6/h10 MPI2 full-scale partition identity Gate
H1R3.2  p6/h5 MPI1 h-refinement scaling Gate
```

任一阶段失败，立即停止后续阶段并等待新审阅。

---

# 1. H1R2 审阅结论

## 1.1 正式测量

| 指标 | H1R2 authority |
|---|---:|
| degree / mesh / MPI | `p6 / h10 / MPI1` |
| global rows / constraints | `173802 / 9210` |
| source | fixed `seed_17037` |
| reference applies / candidate applies | `1 / 2` |
| reference first apply | `1.1653526849113405 s` |
| candidate first apply | `1.2354860971681774 s` |
| candidate second apply | `1.195433100918308 s` |
| candidate second / reference | `1.0258122853248122` |
| relative error | `2.7326039504560278e-17` |
| finite / deterministic / repeat equal | `true / true / true` |
| completed process-tree peak | `332636160 B = 0.30979156494140625 GiB` |
| swap | `0` |
| candidate retained payload | `6151104 B = 5.86614990234375 MiB` |
| per-apply packed temporary | `3556224 B`，apply 后释放 |
| canonical packets / duplicates | `164592 / 0` |
| KSP / DtN / official field / RTA | `0 / 0 / false / false` |

H1R2 通过 Review V4 的 `<=1.25 GiB` process-tree Gate，也通过用户更宽的 decimal
`<2,000,000,000 B` action-only目标。该内存结果只属于 completed MPI1 action worker，
不是完整求解器峰值。

## 1.2 归一化常数

用于后续 refinement 对照的冻结常数为：

```math
b_{retained,h10}
=
\frac{6151104}{173802}
=
35.3914454379\ \mathrm{bytes/row}.
```

```math
b_{temporary,h10}
=
\frac{3556224}{173802}
=
20.4613525736\ \mathrm{bytes/row}.
```

```math
t_{apply,h10}
=
\frac{1.195433100918308}{173802}
=
6.8781320176\times10^{-6}\ \mathrm{s/row}.
```

process-tree peak 除以 row 得到约 `1913.88 B/row`，但这个量被 Python、PETSc、
DOLFINx、MPI 和动态库的固定启动成本主导，不能直接线性外推。后续必须用 h10/h5
两点分离固定成本和增量斜率。

---

# 2. 代码审阅

## 2.1 当前 candidate 的真实结构

当前 candidate 为：

```text
DOLFINx rank-one UFL action
+ existing output Vec
+ fresh coefficient packing per apply
+ flat/vectorized MPC R^H reduction
+ slave identity rows
```

核心实现位于：

```text
src/solvers/hcurl_rank_one_mpc_action.py
```

它保留：

- 一个 coefficient Function；
- 一个 output Vec；
- 常数数组；
- 按 constraint NNZ 线性增长的 flat MPC metadata/work arrays。

它不保留：

- global A；
- global constraint matrix；
- condensed Schur；
- cell dof/coordinate Python objects；
- dense cell tensor；
- per-cell factor；
- slab factor；
- KSP 或 DtN 数据。

这与 Review V3 拒绝的 dense-cell-tensor reassembly action 是结构性不同的实现。

## 2.2 reference 独立性的准确边界

reference 使用 `MpcFormActionContext` / `dolfinx_mpc.assemble_vector`；candidate 使用普通
DOLFINx rank-one residual assembly，再由独立的 flat/vectorized MPC `R^H` 路径完成
约束归约。两者的 MPC reduction 实现不同，因此 H1R2 有效验证了 candidate 的约束作用、
slave identity 和 distributed-Vec 输出语义。

但 reference 与 candidate 仍共享相同的 UFL form、FFCx form compiler 和底层 volume
integration kernel。H1R2 的 `2.73e-17` 不能被解释成一个完全独立的物理离散软件交叉验证。
完整证据链应准确表述为：

1. H1R.1 在单元级比较 dense cell-tensor authority 与 direct rank-one action，误差约
   `1e-15`；
2. H1R2 在真实 full mesh 比较现有 MPC form-action 与独立 candidate MPC reduction，
   误差约 `1e-17`；
3. 未来 PDE 仍必须通过 explicit true residual、R/T/A、12+12 channel 和 canonical field
   Authority，不能只依赖 action identity。

## 2.3 当前正信号

对于固定 `p=6` 的纯 h-refinement，当前 retained 数组、coefficient packing 和 rank-one
assembly 都应以 DoF/cell 数近似线性增长；没有出现 `O(N^2)` global/slab factor 或
每个 cell 保留 dense tensor 的结构。

candidate second apply 只比 reference first apply 慢约 `2.58%`，说明低存储 candidate
没有为当前 h10 action 付出数量级时间代价。

## 2.4 尚未关闭的风险

H1R2 仍未回答：

1. **full-scale MPI identity**：当前正式结果只有 MPI1；tiny fixture 的 MPI2 不能替代
   p6/h10 下 remote master、ghost accumulation 和 canonical partition identity。
2. **h-refinement scaling**：当前只有 h10 一点，不能计算 retained payload exponent、
   action time/row 稳定性或 process-tree 增量斜率。
3. **重复调用生命周期**：完整 KSP 会调用 action 数百次。当前每次都会 fresh pack
   coefficient arrays；必须证明 repeated apply 不产生 RSS 爬升或 allocator 高水位增长。
4. **source coverage**：单一丰富 source 对线性算子已是有效主测试，但不能替代 MPI 分区和
   refinement 测试。V5 不要求重新做四源 h10 campaign，而用更有价值的分区/规模 Gate
   取代重复 source。
5. **solver gap**：action 正确且低存储，不代表存在可收敛的 factor-free smoother、coarse
   correction 或 time-harmonic preconditioner。
6. **boundary gap**：H1R2 只含 volume `curl-curl-k0^2 epsilon mass`；DtN、incident
   correction 和 official postprocess 均未进入。

---

# 3. V5 决定：H1R2 接受，H1R3 解锁，H2 继续锁定

```text
H1R2 = PASS
H1R3 = AUTHORIZED
H2    = LOCKED
```

原因是：对长期 p6/h1 目标，action 层必须先证明以下三点，才值得在其上构造 smoother：

```text
重复调用无内存爬升
+ full-scale MPI partition identity
+ h-refinement 下近线性 bytes/time scaling
```

若现在直接进入 H2，即使局部 smoother 有正信号，也无法判断基础 action 是否满足未来
h1 的内存/时间缩放要求。

---

# 4. H1R3.0：MPI1 warm-repeat 与 allocator 生命周期

## 4.1 固定范围

| 项目 | 合同 |
|---|---|
| degree / mesh / MPI | `p6 / h10 / MPI1` |
| source | 固定 `seed_17037` |
| reference | 1 次 |
| candidate | 固定 12 次 |
| timeout | 120 s |
| canonical | 只在最终数值 Gate 通过后写一次 |
| KSP / DtN / PDE | 禁止 |

第一次 candidate apply 允许 warm-up；正式 steady-state timing 使用 candidate apply
`5--12` 的 median。

## 4.2 必须增加的遥测

每次 candidate apply 后记录并立即 flush：

- apply index；
- wall time；
- process-tree RSS/PSS/USS；
- candidate retained payload；
- packed temporary bytes；
- output SHA/repeat identity；
- source start/end clean identity。

不得为每次 apply 写 canonical 文件。

## 4.3 Gate

```text
all 12 outputs finite and bitwise deterministic
first and last candidate vs reference relative error <= 1e-11
retained payload exactly stable after build
packed temporary bytes exactly stable
apply 5--12 median <= 1.25 * H1R2 candidate-second time
RSS max(apply 5--12) - min(apply 5--12) <= 64 MiB
completed process-tree peak <= 0.45 GiB
swap = 0
completion <= 120 s
```

时间阈值数值为：

```math
1.25\times1.195433100918308
=
1.494291376147885\ \mathrm{s}.
```

若 RSS 稳定性失败，不允许用 `malloc_trim` 每次强制清理来伪造稳定；必须先定位
packing/output/canonical 或 Python temporary 生命周期。

---

# 5. H1R3.1：p6/h10 MPI2 full-scale partition identity

只在 H1R3.0 全部通过后进入。

## 5.1 固定范围

| 项目 | 合同 |
|---|---|
| degree / mesh | `p6 / h10` |
| MPI | `2` |
| source | 固定 `seed_17037` |
| reference / candidate | `1 / 2` |
| timeout | 180 s |
| canonical authority | H1R2 MPI1 manifest |
| KSP / DtN / PDE | 禁止 |

## 5.2 必须比较

1. same-run reference 与 MPI2 candidate distributed Vec；
2. MPI2 candidate canonical manifest 与 H1R2 MPI1 manifest；
3. global rows、constraints、packet identity；
4. retained payload global sum/global max；
5. process-tree总峰值，而不是单 rank peak。

## 5.3 Gate

```text
same-run relative error <= 1e-11
finite and deterministic
MPI2 vs MPI1 canonical relative L2 <= 1e-12
canonical missing / extra / duplicate = 0 / 0 / 0
canonical packet count = 164592
candidate retained global-sum bytes / global rows <= 45 bytes/row
candidate second apply <= 2 * same-run reference apply
candidate second apply <= 2 * H1R2 MPI1 candidate-second apply
completed process-tree peak <= 0.75 GiB
swap = 0
completion <= 180 s
```

第二个时间上限数值为：

```math
2\times1.195433100918308
=
2.390866201836616\ \mathrm{s}.
```

MPI2 的 process-tree peak 不要求低于 MPI1，因为 Python/PETSc runtime 会被两个 rank
重复；但总峰值必须保持在明确预算内，不能只报告 per-rank peak。

---

# 6. H1R3.2：p6/h5 MPI1 h-refinement scaling

只在 H1R3.1 全部通过后进入。

## 6.1 固定范围

| 项目 | 合同 |
|---|---|
| degree / mesh / MPI | `p6 / h5 / MPI1` |
| source | 固定 `seed_17037` |
| reference / candidate | `1 / 2` |
| timeout | 300 s |
| canonical | 不写全量 canonical；避免把大规模文件 I/O 混入 action scaling |
| KSP / DtN / PDE | 禁止 |

runner 可以增加一个固定的 `h1r3-h5-worker/watchdog` 窄入口，但不得开放任意 degree、h、
source 或 repeat 扫描 CLI。

## 6.2 必须记录

- actual global rows、constraints、cells；
- reference/candidate timing；
- retained component bytes；
- packed temporary bytes；
- process-tree peak、swap；
- h10/h5 payload exponent；
- h10/h5 process-peak 增量斜率；
- action time/row ratio。

定义：

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
M = candidate retained numeric payload global sum
P = completed process-tree peak
N = global full-space rows
```

## 6.3 Gate

```text
relative error <= 1e-11
finite and deterministic
retained payload / global rows <= 45 bytes/row
packed temporary / global rows <= 28 bytes/row
alpha_payload <= 1.10
action seconds / global row <= 1.5 * H1R2 value
b_peak <= 512 bytes/row
completed process-tree peak <= 0.75 GiB
swap = 0
completion <= 300 s
```

时间/row 上限为：

```math
1.5\times6.8781320176\times10^{-6}
=
1.03171980264\times10^{-5}\ \mathrm{s/row}.
```

还必须根据实测 `b_peak` 给出 p6/h1 action-only core 的线性外推：

```math
P_{h1,pred}
=
P_{h10}
+
b_{peak}(N_{h1}-N_{h10}).
```

该外推只用于 action layer 风险评估，不能称为 full solver 2 TiB qualification。

---

# 7. H1R3 hard stops

以下任一项发生，立即停止后续阶段并保留真实负证据：

1. warm repeat 出现持续 RSS 爬升、packed bytes 漂移或 non-determinism；
2. MPI2 canonical missing/extra/duplicate 非零，或 partition relative L2 超限；
3. h5 action error 超限；
4. retained payload exponent `>1.10`；
5. h5 time/row、peak slope 或总峰值超限；
6. 需要恢复 dense cell tensor、per-cell metadata、global matrix、Schur 或 factor；
7. 需要修改 ordinary default、安装新依赖、建立新分支或改变物理问题；
8. weekly quota 显示为 0。

失败后禁止：

- 原样重跑；
- 放宽 timeout/memory/error Gate；
- 同时开发多个 action backend；
- 自动切换 source、MPI 或 h；
- 启动 H2/H3/H4/PDE；
- 将 incomplete peak 冒充 completed authority。

若失败原因有单一且由 raw 支持的实现缺陷，先提交 narrow evidence，等待下一次 review；
不得在同一轮自行无限修复并重跑 heavy。

---

# 8. 本轮明确禁止的工作

```text
H2 coercive block smoother
H3 two-grid / PCMG
H4 exact time-harmonic FGMRES
DtN action integration
official field / RTA / 12+12 channel
p6/h2.5 或 p6/h1
MPI4/MPI8
多 source campaign
LOR-HX 重开
sweep / shifted-parameter scan
new branch / PR / master merge
```

H1R3 全部通过后，也不得由 Codex 自动进入 H2；必须先提交结果并等待下一次审阅。

---

# 9. Required outputs

## 9.1 Tracked compact records

```text
benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat.json
benchmarks/cases/101_task37_extra_development/records/h1r3_mpi2_partition_identity.json
benchmarks/cases/101_task37_extra_development/records/h1r3_h5_action_scaling.json
```

只创建实际运行阶段的 record；若前一 Gate 失败，后续 record 必须不存在并明确记录
`not_run_by_gate`。

## 9.2 Outcomes

```text
docs/task37_extra_development/outcomes/h1r3_warm_repeat.md
docs/task37_extra_development/outcomes/h1r3_mpi2_partition_identity.md
docs/task37_extra_development/outcomes/h1r3_h5_action_scaling.md
```

## 9.3 Consolidated response

```text
docs/task37_extra_development/response_v5.md
```

`response_v4.md` 保持为冻结 H1R2 authority，不覆盖。H1R3 的已运行、未运行、Gate、
raw hash、source SHA、测试和下一步资格统一写入 `response_v5.md`。

## 9.4 Heavy raw

全部进入 ignored artifact 目录，不得 git add：

```text
benchmarks/artifacts/task037_extra_h1r3_*/
```

---

# 10. Test 与 Git 合同

执行前必须确认：

```text
branch = codex/20260806-task37-iterative-extra-development
upstream = origin/codex/20260806-task37-iterative-extra-development
ahead/behind = 0/0
tracked and nonignored-untracked worktree = clean
```

每个阶段先通过对应 pure/focused tests，再允许唯一一次正式 run。必须覆盖：

- fixed source/MPI/h/repeat/timeout contract；
- repeated RSS/payload telemetry；
- MPI1/MPI2 canonical compare；
- h10/h5 exponent/slope recomputation；
- fail-closed missing-summary semantics；
- raw SHA/evidence closure。

提交时逐文件 stage；只能 push 到当前 extra 分支。不得创建 PR。

---

# 11. H1R3 通过后的下一步边界

若 H1R3.0/1/2 全部通过，Candidate H 才完成 action-layer 的以下资格：

```text
exact
+ repeat-stable
+ MPI-partition invariant
+ h-refinement near-linear
+ low-memory
```

届时下一次 review 最多讨论 **H2.0 exact block-class inventory**，而不是直接授权完整
coercive smoother或 PDE。H2.0 必须先证明：

- exact class 数在 h10/h5 不随 cell 数增长；
- 每类只保存一份小型 block factor；
- 无 per-cell factor；
- retained factor payload 明显低于用户 p6/h10 预算；
- local block 数学作用和 PoU 合并正确。

本 V5 不授权 H2.0；这里只给出后续审阅边界。

---

# 12. 给 Codex 的执行摘要

```text
只在 codex/20260806-task37-iterative-extra-development 工作。
完整阅读 response_v4.md 与 review_report_v5.md，以 V5 为最高优先级合同。

按顺序执行：
H1R3.0 warm-repeat；通过后 H1R3.1 MPI2；通过后 H1R3.2 h5。
任一 Gate 失败立即停止后续阶段。

不得进入 H2/H3/H4/PDE/DtN/RTA，不得新建分支或 PR，不得修改 master/default。
最终只提交实际运行的 compact records、outcomes 和 response_v5.md，push 同一 extra 分支，
然后停止等待审阅。
```
