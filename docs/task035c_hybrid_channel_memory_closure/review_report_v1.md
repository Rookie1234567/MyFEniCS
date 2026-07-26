# Task035c Review V1：Hybrid 精度/内存闭合验收、适用边界与后续 h/p 路线

## 1. 审阅结论

```text
review_status = TASK035C_ACCEPTED_WITH_QUALIFIED_SCOPE
reviewed_branch = codex/20260726-task35c-hybrid-channel-memory-closure
reviewed_response = response_v1.md
numerical_source = 244b62e1fb4f299a468363cf90a2dd548dc34ff6
Task035c_physics_closure = pass
Task035c_mandatory_memory_gate = pass
Task035c_preferred_memory_gate = pass
user_50pct_static_hybrid_memory_target = not_achieved
modal_coupling_time_hard_gate = cancelled_by_user / report_only
PSS_USS_authority = not_qualified_in_tracked_evidence
ordinary_default = standard_full
ordinary_default_changed = false
qualified_geometry_scope = fixed_rectangular_axis_aligned_affine_hexa_uniform_z
curved_irregular_nonuniform_mixed_scope = not_qualified
Task035c_completion = accepted
Task035c_master_merge = not_authorized_by_this_review
recommended_successor = Task035d_goal_oriented_exact_sequence_hp_adaptivity
```

Task035c 可以按正式任务 Gate 判定为成功。这里的成功包含两个已经由正式 p6/h10 六路径证据证明的结论：

1. Full3D 与 Hybrid 的 12 个显著衍射级功率和 12 个物理边界面复振幅已经闭合；
2. static Hybrid 相对 standard Hybrid 的 MPI8 峰值内存下降约 29.5%–31.9%，通过 15% mandatory 和 25% preferred Gate。

用户进一步提出的 50% static-Hybrid 峰值下降没有达到，继续作为工程缺口保留。该缺口不推翻 Task035c 的正式成功分类，也不能被写成“当前已经达到内存下限”。

---

## 2. 已接受的主要结果

### 2.1 逐通道误差根因已经闭合

旧 Hybrid 在中间均匀层使用连续 QEP 传播因子和连续端点 traction，而 Full3D 在 z 方向实际采用 scalar CG(p) 有限元链。Full3D 因此具有自己的离散传播相位和离散端点导数符号。

p2/h5 隔离实验已经证明：

```text
原 Hybrid：                     3/12 powers + 2/12 amplitudes
只替换 scalar-CG 离散相位：    4/12 powers + 4/12 amplitudes
离散相位 + 离散端点 traction： 12/12 powers + 12/12 amplitudes
```

所以原误差不是 M120/M160 模态截断不足，也不是接口 modal trace 子空间缺秩；根因是 Full3D 与 Hybrid 使用了不同的轴向离散符号。

修复仍是显式 opt-in：

```text
internal_propagation_model = full3d_uniform_cg
internal_traction_model = scalar_cg_discrete_derivative
```

### 2.2 p6/h10 六路径已经形成正式高阶 authority

| 路径 | active rows | matrix NNZ | factor NNZ | 峰值内存 | 总时间 |
|---|---:|---:|---:|---:|---:|
| Full3D standard | 173,882 | 210,353,168 | 438,050,956 | 34.041 GiB | 2581.55 s |
| Full3D static | 51,272 | 41,989,040 | 212,343,992 | 14.722 GiB | 260.74 s |
| Hybrid standard M120 | 52,292 | 60,434,236 | 141,010,528 | 11.077 GiB | 942.03 s |
| Hybrid static M120 | 17,168 | 12,313,232 | 45,293,792 | 7.544 GiB | 322.78 s |
| Hybrid standard M160 | 52,372 | 60,434,236 | 141,010,528 | 11.247 GiB | 1014.71 s |
| Hybrid static M160 | 17,248 | 12,313,232 | 45,293,792 | 7.929 GiB | 393.84 s |

六条路径均通过：

- full explicit residual；
- Rtotal、Ttotal、Aclosure、Avolume；
- interface E/H 与 selected middle-plane E/H；
- 12/12 significant powers；
- 12/12 physical-boundary-plane complex amplitudes；
- 0 swap。

M120→M160 没有可测物理收益，M160 反而增加峰值、modal coupling 和总时间。因此当前推荐点是 static Hybrid M120。

### 2.3 modal-coupling 时间限制的准确状态

用户已经明确取消 `modal-coupling time <= 1.25× standard` 作为硬性否决 Gate。Task035c 文档将其作为 report-only 指标是正确的。

即使仍沿用旧 1.25× 标准，p6/h10 的实测比值约为 1.076，也会通过。因此该口径不会改变本 Review 的成功判定。

---

## 3. PSS/USS 是否必须重新运行模型

### 3.1 当前可接受的证据

Task035c 的正式相对内存结论使用同一工作站、同一 MPI、同一采样器和同一输出合同下的 simultaneous process-tree/live-worker RSS。对 standard/static 的成对比较而言，该口径足以支持 31.89% 和 29.50% 的相对峰值下降。

当前 tracked compact evidence 没有资格化的 per-rank PSS/USS 时间序列，因此不能从 RSS 数值反推出 PSS/USS，也不能在进程已经退出后重新构造真实 PSS/USS。

### 3.2 不重新跑 PDE 时应怎样处理

Codex 先检查本机仍保留的 ignored raw timeline/watchdog artifact：

1. 若原始运行已经保存 `/proc/<pid>/smaps_rollup`、PSS、USS 或等价逐进程快照，可以只重建 compact resource ledger，不需要重新求解 PDE；
2. 若原始 artifact 只有 RSS/process-tree 数据，则不得估算 PSS/USS。应在 README、summary、response、Case096 和 registry 中明确写：

```text
PSS/USS = historical campaign did not record qualified values
RSS comparison = formal authority for this task
```

Task035c 不需要为了补一个未采集的诊断字段重跑全部六条 p6/h10 路径。

若未来确实需要一组正式 PSS/USS 对照，可使用外部只读 smaps sampler，仅重跑最有价值的一对：

```text
p6/h10 Hybrid standard M120
p6/h10 Hybrid static M120
```

这应当是独立的资源遥测补充，而不是重新打开 Task035c 的物理资格化。

### 3.3 本 Review 的决定

```text
PSS/USS numerical backfill without raw samples = impossible
PSS/USS documentation clarification = required
full six-path rerun only for PSS/USS = not required
future heavy campaigns must collect PSS/USS from start = required
```

---

## 4. 当前方法的适用边界

### 4.1 已资格化范围

Task035c 的新离散传播/traction 和 static Hybrid 目前只在以下范围内有正式证据：

```text
fixed rectangular block grating
structured tensor-product mesh
axis-aligned first-order affine hexahedra
uniform z segmentation in the modal middle region
one well-defined axial h for the scalar CG(p) chain
supported axial degree p1–p6
complex128
Floquet periodicity
sparse auxiliary DtN
standard/static direct solve
```

这里最关键的限制是：`full3d_uniform_cg` 与 `scalar_cg_discrete_derivative` 使用均匀 scalar CG(p) 链的单元动态刚度和 Bloch 符号。它不能直接套用到非均匀 z 单元链。

### 4.2 尚未资格化的范围

```text
nonuniform z spacing
locally refined or hanging-node hexa mesh
curved or distorted hexahedra
high-order curved geometry mapping
tetrahedral static condensation
hexa/tetra/prism/pyramid mixed mesh
sloped sidewalls, rounded corners, roughness or defects
arbitrary irregular geometry
production automatic hp adaptivity
```

这些情况不是已知“不可能”，只是本任务没有证明。后续获得真实曲面或不规则结构后，应根据实际几何、网格类型和轴向离散重新推导并资格化，不应现在凭空设计假设性不规则模型。

### 4.3 合并前必须完成的文档修订

Codex 应在不重跑重型 PDE 的前提下，把上述限制同步写入：

- Task035c `README.md`；
- `task.md` 的完成边界；
- `outcomes/summary.md`；
- `response_v1.md`；
- Case096 README；
- `docs/development_model_registry.md`；
- 新传播/traction 配置字段的注释、运行日志和 fail-closed 错误。

不得只在 Review 中写一次，普通用户在配置入口和运行时报错中也必须看到适用边界。

---

# 5. 下一步建议：先真正解决 h/p 自适应

用户给出的顺序是合理的：

```text
真正 h/p 自适应
→ 专用迭代法
→ matrix-free / streaming / 更低内存实现
```

原因是 h/p 自适应先决定最终离散空间和矩阵结构。若在空间仍不断变化时先投入大量迭代预条件和低存储优化，后续真正 local-p、local-h 或 Hybrid 映射可能使已有求解器工作失效。

## 5.1 推荐新任务

```text
Task035d：goal-oriented exact-sequence local hp adaptivity
```

当前只针对 Task034 固定规则矩形结构，不研究曲面和不规则几何。

## 5.2 Task035d 的核心起点

不要再从不准确的低阶模型向上猜测，而应从已经闭合的 p6/h10 高阶空间向下压缩：

```text
p6/h10 Full3D static reference
→ 识别对目标量不重要的 p6 edge/face/interior modes
→ 物理删除不活跃模式
→ 对 p 收敛缓慢的局部区域做 h-refinement
→ 重新求解并用12通道检查
```

这是 fail-closed 路线：初始空间已经准确，任何模式删除或网格粗化都必须证明没有破坏目标量。

## 5.3 Phase A：真正的 local-p，而不是系数置零

必须建立 exact-sequence-compatible entity degree map：

```text
edge degree
face degree
cell-interior degree
```

并满足：

- 相邻单元共享同一个 edge/face degree；
- edge/face/cell degree满足H(curl)层级兼容；
- periodic master/slave按完整orbit同步；
- inactive modes不生成全局row，不进入NNZ和MUMPS front；
- 不能组装完整p6矩阵后把系数强制为零；
- static condensation与variable-p恢复保持exact sequence。

Task035b未完成的 selective trace 应在这里以正式 active-space 架构闭合，而不是继续停留在fixture。

## 5.4 Phase B：真正的 local-h

当前 directional-z h13只是方向性全局加层，不是真正local-h。Task035d需要至少一种正式的局部h路径：

- 周期闭合的局部hexa block/octree refinement，并实现H(curl) hanging-trace约束；或
- 若hexa hanging-node能力尚不成熟，先以已有periodic tetra DWR作为局部h权威，但不能把tetra-h和hexa-p的独立结果冒充同一hp空间。

最终成功必须在同一离散架构中完成h/p选择与重算。

## 5.5 Phase C：多目标hp判别

目标集合至少包括：

```text
R00
Rtotal
Ttotal
Aclosure
12 significant powers
12 physical-boundary-plane complex amplitudes
selected interface/field probes
```

每个候选局部动作都比较：

```text
goal-error reduction / added active rows
goal-error reduction / added NNZ
goal-error reduction / estimated factor cost
```

判别原则：

```text
smooth + goal-sensitive + p-surplus快速衰减  -> 保持或提高p
p-surplus衰减慢 / interface or singular     -> 局部减小h
smooth + low goal impact                    -> 降低p或保持粗网格
```

## 5.6 Task035d 建议成功 Gate

以 p6/h10 reference-v1 为权威：

```text
12/12 significant powers pass
12/12 complex amplitudes pass
R/T/A/residual/fields pass
Full3D-equivalent DoF <= 90,000 mandatory
65,000–75,000 preferred
active rows, NNZ, factor NNZ and measured peak all decrease
MPI identity and periodic closure pass
```

达到Full3D Gate后，再把同一局部FE h/p分配接入已经修复的 static Hybrid M120。Hybrid只能增加降维收益，不能掩盖Full3D自适应误差。

---

# 6. h/p 完成后的迭代法路线

下一阶段再建立Task035e，针对冻结的hp-condensed Hybrid系统开发专用预条件器。此前简单Jacobi、ASM/ILU和z-slab方案失败，下一次不应继续微调同类参数。

推荐结构：

```text
FGMRES
+
H(curl) auxiliary-space or p-multigrid for FE trace block
+
exact/small dense inverse for modal block
+
block Schur or low-rank interface correction
```

Task035d得到的p层级可以直接成为p-multigrid层级，这也是先做hp、后做迭代的主要好处。

---

# 7. 最后的低内存路线

在hp空间和迭代法都稳定后，再进入Task035f：

- matrix-free/partial-assembly local Schur action；
- modal projection/coupling分块streaming；
- bottom/top factor错峰或彻底factor-free；
- QEP modes分布式/分批驻留；
- selected-plane和volume field流式重构；
- incremental compact serialization；
- PSS/USS/native-object完整生命周期账本；
- 为0.7 nm准备no replicated dense M²和blocked modal Schur。

当前Task035c已经说明，只优化最终JSON写出或简单`del/gc`无法把7.544 GiB降到5.538 GiB以下。更低内存必须依靠空间压缩、迭代替代LU以及真正的分块/流式生命周期共同完成。

---

## 8. 最终决定

```text
Task035c = ACCEPTED_WITH_QUALIFIED_SCOPE
Hybrid channel root cause = resolved
p6/h10 Full3D-Hybrid 12-channel closure = pass
static Hybrid mandatory/preferred memory gate = pass
50pct static-Hybrid memory target = open
PSS/USS missing field = document now, measure in next heavy campaign
uniform structured geometry limitation = must be explicit everywhere
next priority = true exact-sequence goal-oriented hp adaptivity
iterative solver = after hp space freezes
matrix-free/streaming low-memory = after hp + iterative
```
