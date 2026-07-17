# REVIEW REPORT V2：Task033 Phase A QEP 跟踪闭合与 Phase B 准入

## 0. 审阅身份与最终决定

```text
review = Task033 review_report_v2
branch = codex/20260715-task33-high-order-floquet-hybrid-hp
reviewed_head = 97bfb96b2625524e130ffb825ba06787ba0292ec
Phase A numerical source = bb830ba5dd74ced30475402bd6bc6d3c1856c630
Case090 numerical source = 6613f94b91ebc77eb50e74086475c67df46236f6
review_status = PHASE_A_PASS_WITH_QUALIFICATIONS
p3 QEP component = ACCEPTED
p4 QEP component = ACCEPTED_WITH_SCOPE_QUALIFICATION
legacy p1-p4 aggregate = NOT_QUALIFIED / ACCEPTED_NEGATIVE
Phase B matched trace = APPROVED_TO_START
Phase C p3 target Hybrid = NOT_YET_APPROVED_TO_START
Case090 rerun = NOT_REQUIRED
h adaptivity = REMAINS_FINAL_PHASE
ordinary default = UNCHANGED
whole branch merge = NOT_APPROVED
```

本轮没有发现新的 Maxwell 物理公式错误、QEP 矩阵装配错误、阈值被人为放宽、伪造 MPI 正向资格或重复运行 Case090 的问题。Codex 基本按 `review_report_v1.md` 的 Phase A 最小闭环执行：先重放已有 MPI1 compact evidence，修正近简并跟踪，再只补原来缺失的 p3/p4 MPI2、MPI4 正向身份记录。

Phase A 可以通过，允许在同一分支进入 Phase B。Phase B 完成并形成独立 checkpoint 前，不得提前启动 p3/h5 目标光栅 full3D 与 Hybrid 大算例。

---

# 1. 本轮审阅范围

本轮复审覆盖：

- `response_v2.md`；
- `outcomes/qep_tracking_diagnostic.md`；
- 更新后的 `outcomes/qep_order_study.md`、`negative_results.md`、`summary.md`；
- 更新后的轻量 `stage_summary.json`；
- `benchmarks/task033_qep_qualification.py` 中的 block/subspace tracking；
- Case090 non-numerical descendant reuse audit；
- p3/p4 h3 的 MPI2、MPI4 正向 watchdog 结果；
- Task032 p2 QEP/mode regression；
- 新增和更新的 fail-closed tests。

相对 Review V1 提交，本分支新增 3 个提交；Phase A 的数值与 aggregate 实现绑定 clean source `bb830ba...`，最终文档收口 HEAD 为 `97bfb96...`。

---

# 2. Review V1 Phase A 要求关闭情况

| Review V1 要求 | 当前处理 | 审阅结果 |
|---|---|---|
| 先复用已有 36 个 MPI1 shards 离线诊断 | 使用原 measured compact inputs 重放 assignment 和 block tracking | closed |
| 不直接放宽 overlap / beta-drift Gate | 单模 `0.5`、beta drift `0.25` 均保持 | closed |
| 使用 near-degenerate block/subspace 指标 | 增加左右公共 Fourier fingerprint 的 principal-cosine tracking | closed_with_scope |
| 解释 p1/p2，而非只修 p4 | p1 分支容量/方向不闭合、p2 真实谱漂移均保留负结果 | closed |
| 算法修改后先最小复测 | 未重复相同 MPI1 PDE；对已有 exact compact inputs 做离线重放 | accepted |
| 补 p3/p4 MPI2、MPI4 正向资格 | p3/p4 h3 共 4 项正式正向运行 | closed |
| ordinary p2 regression | Task032 QEP/mode classification 13 tests passed | closed |
| 不重跑 Case090，除非高阶数值行为变化 | 严格祖先与路径白名单审计通过 | closed |

这里的 `closed_with_scope` 表示：当前 block tracking 是在已测公共 Fourier fingerprint 空间中的基底无关子空间比较，不是完整分布式本征向量在能量内积下的全空间 principal-angle 证明。该限定不阻塞 Phase B，但必须继续保留。

---

# 3. p4 近简并跟踪验收

## 3.1 原失败

p4 patterned h5→h3 的最小单模 overlap 为：

```text
0.484436658879 < 0.5
```

Codex 没有降低阈值，也没有把单模失败直接删除。

## 3.2 block/subspace 证据

失败模式位于同一个四维近简并块 `[4,5,6,7]`：

| 指标 | 结果 | Gate / 解释 |
|---|---:|---|
| 四维块最小 symmetric principal cosine | `0.999999999999851` | `>=0.5` |
| 四维块 beta 中心相对漂移 | `8.11363e-7` | `<=0.25` |
| h5/h3 right fingerprint rank | `4 / 4` | full rank |
| h5/h3 left fingerprint rank | `4 / 4` | full rank |
| 最大右残差 | `1.32144e-14` | pass |
| 最大左残差 | `2.48937e-14` | pass |

代码只有在以下条件同时成立时，才允许把低单模 overlap 解释为 block 内基底旋转：

1. 前后块大小一致；
2. 左右 fingerprint 子空间均满秩；
3. 传播方向兼容；
4. 最小 symmetric principal cosine 通过；
5. 块中心 beta drift 通过；
6. 所有低 overlap 的单模配对都落入一个完整通过的近简并块；
7. block assignment 完整。

该逻辑是 fail-closed 的，没有发现通过修改结果字段绕过 recomputation 的路径。当前 p4 失败可合理解释为近简并子空间内的基向量旋转，而不是谱子空间漂移。

## 3.3 资格边界

因此接受：

```text
p4 QEP component = qualified for the current compact common-Fourier
fingerprint subspace-tracking contract
```

但禁止扩张为：

- p4 目标光栅 Hybrid 已通过；
- 任意参数、任意网格下的 p4 mode tracking 已完全解决；
- full-vector energy-norm subspace identity 已证明；
- p4 matched trace 已通过。

这些仍需 Phase B/C 的独立证据。

---

# 4. p1 与 p2 负结果验收

Codex 没有为了让 legacy aggregate 变绿而隐藏低阶负结果。

## p1

- air/lossy 的解析 beta 误差随 h 细化反而增大；
- patterned h5→h3 最小 overlap 约 `1.02e-12`；
- 最大 beta drift 约 `1.20599`；
- 部分传播方向/分支在后续候选集合中消失；
- block 数量与方向不闭合。

结论保持：

```text
p1 = diagnostic / regression only
p1 full Hybrid matrix = stopped
```

## p2

p2 h5→h3 单模和二维块的子空间 overlap 均接近 1，但 beta drift 为：

```text
0.2608686 > 0.25
```

所以这是 h5 粗离散造成的真实谱位置漂移，不能由 block tracking 消除。p2 h3→h2.5 已恢复通过，Task032 ordinary p2 regression 也通过。

因此同时接受：

```text
Task033 p2 patterned h5->h3 trend = negative
ordinary Task032 p2 QEP path = no regression observed
```

legacy p1–p4 aggregate 继续保持 `not_qualified` 是正确的；degree-specific p3/p4 component 通过不应覆盖该历史负状态。

---

# 5. MPI 正向资格验收

本轮在 clean source `bb830ba...` 上新增 4 个真正的正向 QEP 运行：

| degree | MPI | 与 MPI1 最小 overlap | 最大 beta drift | memory authority peak | 结果 |
|---:|---:|---:|---:|---:|---|
| 3 | 2 | `0.904811` | `3.81218e-13` | `0.610775 GiB` | pass |
| 3 | 4 | `0.873001` | `4.47319e-13` | `1.042454 GiB` | pass |
| 4 | 2 | `0.750120` | `1.43471e-12` | `0.777660 GiB` | pass |
| 4 | 4 | `0.615322` | `2.14815e-12` | `1.245392 GiB` | pass |

四项均通过：

- source identity；
- QEP shard numerical Gates；
- Case090 reuse Gate；
- simultaneous worker RSS / cgroup authority；
- no swap；
- timeout Gate。

p4 MPI4 的 fingerprint overlap `0.615322` 虽通过 `0.5`，但裕量不算大。Phase B 的 matched-trace MPI1/MPI4 对照应继续保留严格阈值和逐模式/逐块诊断，不能只看 beta drift。

此前 MPI2/4 的 1 秒 timeout-negative 仍然只保留为 watchdog 合同测试，没有被伪装成正向资格。该边界处理正确。

---

# 6. Case090 复用审计

本轮没有重跑 144 个 Case090 PDE，符合 Review V1。

复用 Gate 要求：

1. Case090 source 是当前 source 的祖先；
2. Git diff 可读；
3. 变化只能位于 docs、notes、tests 或明确列出的 aggregate/watchdog 文件；
4. 任何 QEP measurement、3D/QEP assembly、solver、Floquet numerical path 变化均拒绝复用。

本轮记录：

```text
disallowed_changed_paths = []
numerical_source_unchanged = true
```

该白名单当前足够保守，接受复用决定。后续 Phase B 若修改 2D/3D trace、modal projection、quadrature、QEP measurement、mode classification 或任何数值源文件，必须重新判断受影响证据；不能机械沿用本轮 Case090 reuse 结论。

---

# 7. 测试与证据验收

接受以下记录：

| 验证 | 结果 |
|---|---|
| Ruff：tracking/watchdog files | pass |
| host focused Task33 tests | 41 passed, 1 skipped |
| watchdog/Case090 reuse focused tests | 29 passed, 1 skipped |
| Docker Task032 p2 QEP/mode regression | 13 passed |
| p3/p4 selected MPI2/4 | 4/4 formal pass |
| maximum beta drift vs MPI1 | `2.14815e-12` |
| minimum Fourier overlap vs MPI1 | `0.615322` |

新增测试覆盖了：

- source SHA before/after；
- dirty/untracked source fail-closed；
- resource authority 与 swap；
- forged stored Gate 不覆盖 raw recomputation；
- near-degenerate basis rotation；
- block size/rank/direction/beta drift 失败；
- Case090 descendant whitelist；
- timeout 与不可读 authority fail-closed。

GitHub combined-status API 本次返回 403，因此没有独立的远程 status-check 结论。本报告依据 branch diff、clean-source watchdog、测试摘要和 lightweight hash-bound evidence 作出判断。

---

# 8. Phase A 最终结论

```text
Phase A QEP/tracking = PASS_WITH_QUALIFICATIONS
p3 QEP component = PASS
p4 QEP component = PASS in compact fingerprint-subspace scope
p1/p2 low-order negatives = RETAINED
legacy all-degree aggregate = NOT_QUALIFIED
Case090 = REUSED CORRECTLY / NO RERUN
```

Phase A 不应被描述为“整个高阶 Hybrid 组件全部通过”。它关闭的是 QEP、左右模、分类、双正交、近简并跟踪和 selected MPI identity；3D–2D matched trace 与目标 Hybrid 仍未资格化。

---

# 9. Phase B 执行要求

允许 Codex 继续在同一分支进入 Phase B，但必须严格保持最小矩阵。

## 9.1 必做对象

在小型 matching-interface fixture 上验证：

- 3D p3 tangential trace；
- 2D p3 modal trace；
- right reconstruction；
- left Petrov projection；
- coefficient round-trip；
- normal / traction sign；
- degree-aware quadrature 与 raised-order comparison；
- MPI ownership；
- 无 full field gather；
- 无 dense interface square。

p4 做相同最小组件记录，因为 Phase A p4 已通过；但 p4 的失败不得阻塞 p3。

## 9.2 最小运行矩阵

```text
p2: one MPI1 regression anchor
p3: MPI1 + MPI4
p4: MPI1 + MPI4
```

不运行目标光栅 full3D/Hybrid，不恢复完整 QEP 36 项，不重跑 Case090。

## 9.3 Phase B 必须记录

| 类别 | 必须字段 |
|---|---|
| space identity | 3D/2D Basix family、degree、entity/trace DoF |
| interface geometry | matching mesh hash、orientation、normal convention |
| algebra | projection/lifting shapes、NNZ、rank、condition diagnostic |
| accuracy | coefficient round-trip、right reconstruction、left projection、E/H 或 traction error |
| quadrature | chosen degree、raised-order delta |
| MPI | ownership、ghost handling、MPI1/MPI4 difference |
| scalability | gather flags、dense-object flags、communication bytes、RSS、time |

## 9.4 Phase B Gate

```text
p3 matched trace component = pass
p4 matched trace component = pass or fail-closed independently
p2 regression = pass
MPI1/MPI4 identity = pass
raised quadrature = stable
no full vector gather = true
no dense interface square = true
```

若 p3 Phase B 失败，不得进入 Phase C。若只有 p4 失败，停止 p4 路线，p3 可以继续。

Phase B 完成后，应新增 `response_v3.md` 或等价 phase response，并提交独立轻量 aggregate，由 ChatGPT 复审后再决定是否启动 Phase C 的 p3/h5 目标光栅大算例。

---

# 10. 最终处置

```text
Task033 Stage1 high-order 3D Floquet = ACCEPTED
Task033 Phase A QEP/tracking = ACCEPTED_WITH_QUALIFICATIONS
Phase B matched trace = APPROVED_TO_START
Phase C p3/h5 full3D + Hybrid = WAIT_FOR_PHASE_B_REVIEW
p4 target Hybrid = CONDITIONAL
h adaptivity = FINAL PHASE
same branch continuation = APPROVED
selective merge = NOT_REQUESTED
whole branch merge = NOT_APPROVED
ordinary default = UNCHANGED
```
