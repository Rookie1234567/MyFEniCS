# REVIEW REPORT V1：Task033 高阶组件验收与分阶段继续路线

## 0. 审阅身份与决定

```text
review = Task033 review_report_v1
branch = codex/20260715-task33-high-order-floquet-hybrid-hp
reviewed_head = 14c228000046f261c7857f66d18f2bdf432a4795
formal_compute_source = 6613f94b91ebc77eb50e74086475c67df46236f6
review_status = STAGE1_ACCEPTED_CONTINUE_WITH_PHASED_CHANGES
stage1_high_order_3d_floquet = PASS
qep_high_order_components = PASS_WITH_QUALIFICATIONS
p3_p4_target_hybrid = NOT_YET_QUALIFIED
h_adaptivity = DEFERRED_TO_FINAL_PHASE
ordinary_default_changed = false
same_branch_continuation = APPROVED
selective_merge = NOT_YET_REQUESTED
```

Task033 当前阶段已经完成最基础、风险最高的 p=3/p=4 三维 H(curl) 双 Floquet 扩展。Case090 的 144 个真实 PDE 覆盖了 p=1–4、两个网格、S/P 和 MPI1/2/4，核心约束、Bloch trace、reduced/full action、真残差和 MPI 一致性均通过。该成果接受，不要求重复运行 Case090。

本轮同时接受以下准确边界：

1. p3/p4 QEP 的单项数值链已运行，但全局模式跟踪 aggregate 尚未资格化；
2. 目标光栅只有 p2/h5、p2/h3 的 Hybrid/full3D 同阶对照；
3. p3/p4 目标光栅 Hybrid 尚未形成同阶 full3D reference；
4. 原始大规模 p/h campaign、自适应、buffer 与 1 TiB 推演没有完成；
5. 当前阶段不能合并为“完整 Task033 成功”。

用户现决定将自适应放到最后，先尽快完成前置组件。本报告据此重排后续执行顺序。原 `task.md` 保留为历史任务合同，不修改；本 Review V1 对后续优先级、运行矩阵和停止条件具有更高执行优先级。

---

# 1. 当前成果验收

## 1.1 高阶三维 Floquet

| 项目 | 当前证据 | 审阅结论 |
|---|---:|---|
| 正式 PDE 数 | MPI1/2/4 各 48，共 144 | 接受 |
| p3/p4 coverage | 各 36 项 | 接受 |
| constraint round-trip 最大值 | `2.9461e-14` | pass |
| Bloch trace mismatch 最大值 | `3.1890e-15` | pass |
| reduced/full action 最大值 | `3.1269e-16` | pass |
| full true residual 最大值 | `6.5985e-12` | pass |
| MPI result difference 最大值 | `1.0669e-11` | pass |
| global boundary allgather | false | pass |
| dense boundary square | false | pass |

实现采用 Basix entity-local orientation transform、稀疏约束、分布式 periodic entity routing 和 phase-independent topology cache，符合 Task033 的高阶 Floquet 设计目标。

### 决定

```text
Case090 = frozen accepted evidence
rerun Case090 = forbidden unless high-order Floquet numerical behavior changes
```

以下修改不应触发 Case090 全量重跑：

- 文档；
- schema 的非数值字段；
- QEP tracking；
- Hybrid runner；
- 自适应规划；
- 仅影响目标光栅的代码。

只有改动以下对象时，才需要针对受影响阶次先做最小回归，再决定是否全量重跑：

- edge/face coefficient transform；
- slave/master pairing；
- Floquet phase materialization；
- constraint prolongation；
- 3D high-order assembly 或 DtN 数值路径。

## 1.2 p4 精度与成本

Case090 已证明 p4 在小型解析 fixture 上相对 p3 有显著精度收益，但代表点中 DoF 增至约 2.28 倍、NNZ 增至约 4.31 倍，时间增长约 6–8 倍。因此：

```text
p3 = 当前优先工程候选
p4 = 高精度条件候选
p4 != 默认生产阶次
```

## 1.3 QEP 当前身份

MPI1 已完成：

```text
3 materials × p1/p2/p3/p4 × h5/h3/h2.5 = 36 shards
```

36/36 单项数值运行完成，其中 p3/p4 为 18/18。p3 的解析趋势和 patterned tracking 通过；p4 的解析精度通过，但 patterned h5→h3 最小单模 overlap 为 `0.48444`，略低于冻结 Gate `0.5`。

### 审阅解释

该 p4 结果更像近简并子空间中的单模基底旋转风险，不足以判定 p4 QEP 物理失败，也不能直接放宽阈值。应先做 block/subspace tracking，而不是立即重跑全部 36 个 QEP。

## 1.4 p1 modal-capacity 负结果

p1/h5 的 M80/M120/M160 漏斗发现，每方向只有约 120 个有限有效模态，无法满足请求的 M160。该结果来自 singular-K2 的数值无穷根过滤和低阶空间容量，不是普通运行 bug。

### 决定

```text
p1 full Hybrid matrix = stop
p1 future role = regression / low-order diagnostic only
```

不得继续为填满原 20 项表格而运行 p1/h3、h2.5、h2、h1.5 的完整 Hybrid 漏斗。

---

# 2. 新的总执行原则

后续不再启动一个覆盖全部阶段的两天式大 campaign。改用：

```text
one phase
→ one clean source SHA
→ one minimal run matrix
→ one phase summary
→ one reviewable checkpoint
→ then enter next phase
```

每个阶段必须：

1. 先复用已有正式数据；
2. 只运行关闭该阶段 Gate 所必需的最小组合；
3. 先做 serial 或小规模筛选，再做必要 MPI 验证；
4. 算法未修改时不得重复全量 PDE；
5. 单项失败后先离线诊断，不立即清空并重跑整个矩阵；
6. 正式记录必须绑定同一 clean source SHA；
7. 14 GiB watchdog 与 fail-closed Gate 保持；
8. 每阶段结束后更新 `response_v1.md` 或新增明确的 phase response，不覆盖历史内容；
9. Markdown 公式和表格必须检查 GitHub rendered view，不得提交显示源码的公式或错位表格。

---

# 3. Phase A：关闭 QEP、模式分类与 tracking 组件

## 3.1 目标

在不启动目标光栅大求解前，先使以下组件具有明确资格：

- p3/p4 QEP assembly；
- right/left modes；
- Poynting classification；
- biorthogonality；
- 正反 beta pairing；
- near-degenerate block handling；
- 跨 h 模式 tracking；
- 高阶 trace extraction。

## 3.2 首先只做离线诊断

必须复用现有 36 个 QEP shard，不重跑 PDE，完成：

1. 输出 p4 h5/h3 失败附近的 beta、左右残差、单模 overlap、block size 和谱间距；
2. 对近简并候选构造 block overlap 或 principal-angle 指标；
3. 判断失败来自：
   - 模态排序；
   - 单模相位/基底旋转；
   - 左右配对错误；
   - 真正的子空间漂移；
4. 同时解释 p1 非单调和 p2 beta drift，不得只修 p4；
5. 形成 `outcomes/qep_tracking_diagnostic.md`。

## 3.3 算法修改后的最小复测

若 tracking 算法被修改，先只复测失败或临界组合：

```text
patterned p1: h5/h3/h2.5
patterned p2: h5/h3
patterned p4: h5/h3
```

只有这些组合通过后，才允许在同一个最终 clean SHA 上重跑完整 MPI1 36 项 aggregate。

MPI2/4 在本 Phase 不需要复制 36 项矩阵。只需选择：

```text
p3 patterned h3
p4 patterned h3
```

各做一个正向 MPI2 与 MPI4 数值等价性测试。之前的 1 秒 timeout-negative 不能替代这一步。

## 3.4 Phase A Gate

```text
right/left polynomial residual = pass
biorthogonality = pass
block/subspace tracking = pass
p3 and p4 selected MPI1/2/4 result identity = pass
ordinary p2 Task032 mode regression = pass
```

单模 overlap 可以作为 diagnostic，但 near-degenerate block 的最终判定应优先使用子空间指标。

### 停止条件

若 p4 子空间本身不稳定，而非单模基底旋转，则：

```text
p4 QEP = component_not_qualified
continue p3 route
stop p4 target Hybrid
```

不得因 p4 失败阻塞 p3。

---

# 4. Phase B：高阶 matching trace 与局部 Hybrid 组件

## 4.1 目标

在小型 matched-interface fixture 上资格化：

- 3D p3/p4 tangential trace；
- 2D QEP p3/p4 modal trace；
- right reconstruction；
- left Petrov projection；
- coefficient round-trip；
- normal/traction signs；
- MPI ownership；
- degree-aware quadrature。

## 4.2 最小矩阵

不运行目标光栅全链路，先使用小 fixture：

```text
p3: MPI1 + MPI4
p4: MPI1 + MPI4 only if Phase A p4 passes
```

p2 保留一个 regression anchor，不再复制完整 p2 矩阵。

## 4.3 Gate

```text
trace coefficient round-trip <= declared tolerance
right reconstruction error = pass
left Petrov projection error = pass
normal/traction sign consistency = pass
MPI1/MPI4 difference = pass
raised quadrature comparison = stable
no full field gather
no dense interface square
```

Phase B 通过后，才允许目标光栅 p3 Hybrid。

---

# 5. Phase C：p3 目标光栅最小全链路闭环

这是后续最重要的阶段，不恢复原 20 项 p/h 大矩阵。

## 5.1 必跑组合

只运行：

```text
p3/h5 full3D direct reference
p3/h5 Hybrid M80
p3/h5 Hybrid M120
p3/h5 Hybrid M160
p3/h5 augmented direct anchor
p3/h5 Modal-Schur memory-minimal primary
```

如果 M120→M160 未收敛，资源 Gate 允许时增加 M240。不得预设所有阶次都固定使用 M160。

## 5.2 正确参考绑定

full3D reference 必须与 Hybrid 完全同阶、同网格、同物理参数：

```text
reference key = (degree, h, wavelength, angle, phi, polarization, material, geometry)
```

p3/h5 不得绑定 Task032 p2/h5 reference。

## 5.3 必须比较

| 类别 | 指标 |
|---|---|
| 线性系统 | full explicit true residual |
| official 输出 | R、T、A、能量闭合 |
| 远场 | 各显著衍射级复振幅和效率 |
| 接口 | E/H 或 traction continuity |
| 场 | 选定平面 E/H |
| 模态 | M 漏斗、有效模式数、尾部系数 |
| 规模 | FE DoF、QEP DoF、rows、NNZ、factor NNZ |
| 资源 | simultaneous RSS、cgroup、swap、各阶段时间 |
| 路径 | augmented vs Schur-minimal 等价性 |

## 5.4 Gate

至少保持 Task032 同级原则：

```text
full true residual <= 1e-9
max |ΔR/T/A| <= 1e-5 mandatory
interface and selected-field Gates explicitly declared and passed
M truncation requires two-level evidence where practical
no swap
peak memory < controlled termination limit
```

## 5.5 p3/h3 是否运行

p3/h5 完全闭合后，先做 p3/h3 两种独立内存预测。只有：

```text
center predictions <= 11.5 GiB
conservative upper <= 12.8 GiB
```

才运行 p3/h3。若失败，记录 `not_run_by_memory_gate`，不影响 p3/h5 组件资格。

---

# 6. Phase D：p4 目标光栅条件闭环

p4 不作为默认必跑阶段。进入条件：

1. Phase A 的 p4 QEP/block tracking 通过；
2. Phase B 的 p4 matched trace 通过；
3. p3/h5 全链路通过；
4. p4/h5 full3D 和 Hybrid 两类内存预测通过；
5. 预期精度收益足以补偿 p4 的 DoF/NNZ/时间增长。

若全部满足，只运行：

```text
p4/h5 full3D reference
p4/h5 Hybrid minimal M funnel
p4/h5 augmented vs Schur-minimal anchor
```

不运行 p4/h3、h2.5、h2、h1.5，除非 p4/h5 显示强等精度资源优势并经过新的 review。

若内存 Gate 不通过，正确结论是：

```text
p4 target grating = not_run_by_memory_gate
p4 analytic-fixture capability remains accepted
```

---

# 7. Phase E：固定阶次等精度效率，而非完整 20 项矩阵

在 p3 闭合、p4 条件判断完成后，建立精简等精度表。

## 7.1 复用与新增

复用：

```text
p2/h5 Task032
p2/h3 Task032
p2/h2 official R/T/A bridge where provenance is valid
```

新增优先级：

```text
p3/h5 required
p3/h3 conditional
p4/h5 conditional
```

停止继续扩展 p1 Hybrid 矩阵。

## 7.2 比较目标

回答：

- p3/h5 是否达到或优于 p2/h3 的目标量精度；
- p3/h5 的 DoF、NNZ、RSS 和时间是否优于 p2/h3；
- p4/h5 是否在相同误差下具有实际资源优势；
- 高阶收益来自 QEP、local 3D FEM，还是两者共同作用。

必须将三类误差分开：

```text
local 3D FEM discretization error
cross-section QEP discretization error
modal truncation error
```

不得把某一类误差的改善归因于另一类。

---

# 8. Phase F：接口位置与规则缓冲厚度

接口/buffer 研究放在固定阶次组件之后、自适应之前。

## 8.1 首选基线

先用最稳定且已有充分证据的：

```text
p2/h3
buffer = 10.0, 7.5, 5.0 nm
```

`2.5 nm` 仅在前三档结果平稳且 M/资源预测允许时运行。

## 8.2 每个 buffer 必须重新确定 M

接口越靠近复杂区域，local FE DoF 下降，但衰减模需求可能上升。因此每档必须记录：

- local FE DoF；
- local rows、NNZ；
- QEP DoF、求解时间；
- interface trace DoF；
- M 漏斗；
- interface residual；
- R/T/A；
- RSS 和时间。

选择标准是总成本：

$$
C_{\mathrm{total}}
=
C_{\mathrm{local\ FEM}}
+
C_{\mathrm{QEP/modes}}
+
C_{\mathrm{interface/Schur}}.
$$

不能只选择 local DoF 最少的接口。

p3 buffer 研究只在 p3/h5 或 p3/h3 全链路已经稳定后开展，且只选择 p2 研究中最有价值的 1–2 档。

---

# 9. Phase G：最后才做 h 自适应

自适应从原 Phase 5 移到所有固定阶次组件、目标 Hybrid 和 buffer 之后。

## 9.1 第一阶段仍为固定 p2、conforming graded h

顺序：

```text
reproduce uniform p2/h5
→ reproduce uniform p2/h3
→ bridge toward available p2/h2 official outputs
```

不立即开发 hanging-node 或任意 cellwise variable-p H(curl)。

## 9.2 成功等级

| 同误差 local DoF 压缩 | 结论 |
|---:|---|
| `<1.3x` | weak signal |
| `1.3–2x` | useful engineering positive |
| `2–3x` | clear success |
| `>=3x` | 联合工程目标 |
| `>=5x` | strong target |

p2 h-adaptive 未达到 3x 不等于整个 Task033 失败。

## 9.3 hp zoning

当前 variable-p capability audit 已 fail closed。除非框架提供原生、稀疏、orientation-safe、MPI-safe 的 unequal-p H(curl) conformity，Task033 不自行开发任意 variable-p 约束。

可接受收口：

```text
fixed-p p3/p4 equal-accuracy study
+
p2 conforming h-adaptive feasibility
+
hp zoning design report
```

---

# 10. 明确禁止的重复计算

后续不得自动重复：

- Case090 144 PDE；
- 未修改算法时的完整 QEP 36 shards；
- Task032 p2/h5、p2/h3 Hybrid/full3D；
- p1 完整 Hybrid p/h 漏斗；
- 未通过预测 Gate 的 p3/p4 细网格；
- 为生成完整表格而运行无决策价值的组合。

重跑必须在 phase summary 中说明：

```text
what changed
why old evidence is invalid
which minimal records are affected
why a full matrix rerun is necessary
```

---

# 11. 每阶段交付与复审点

| Phase | 交付 | 进入下一阶段的条件 |
|---|---|---|
| A | QEP tracking diagnostic、修正、最终 aggregate | p3 pass；p4 明确 pass 或 fail-closed |
| B | p3/p4 matched trace component records | 相应阶次组件 Gate pass |
| C | p3/h5 full3D + Hybrid 同阶闭环 | 物理、场、M、资源 Gate pass |
| D | p4/h5 条件闭环或 not-run 决策 | 不阻塞 p3 |
| E | 精简 fixed-p equal-accuracy 表 | 能回答 p3/p4 是否值得 |
| F | buffer–M–local DoF 联合代价 | 选择固定接口策略 |
| G | p2 h-adaptive 与可选 hp 设计 | 最终 Task033 结论 |

Codex 每完成一个 Phase，应先提交轻量结果与 response 更新，再启动下一 Phase。不得在未查看上一阶段 aggregate 的情况下继续跑后续大型矩阵。

---

# 12. 当前最终处置

```text
Task033 Stage1 high-order Floquet = ACCEPTED
Case090 rerun = NOT REQUIRED
QEP full qualification = CHANGES REQUIRED
p3 target Hybrid closure = NEXT PRIMARY MILESTONE
p4 target Hybrid = CONDITIONAL
full p/h matrix = CANCELLED IN FAVOR OF MINIMAL EQUAL-ACCURACY SET
interface buffer = AFTER HIGH-ORDER COMPONENTS
h adaptivity = FINAL PHASE
same branch continuation = APPROVED
ordinary default = UNCHANGED
whole branch merge = NOT YET APPROVED
```

下一步 Codex 应从 Phase A 开始：首先使用已经存在的 QEP records 离线诊断 p1/p2/p4 tracking，不启动新的大规模 PDE。