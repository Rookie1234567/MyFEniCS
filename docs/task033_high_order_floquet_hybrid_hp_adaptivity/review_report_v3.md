# REVIEW REPORT V3：Task033 Phase B matching-trace 复审与 Phase C 准入

## 0. 审阅身份与决定

```text
review = Task033 review_report_v3
branch = codex/20260715-task33-high-order-floquet-hybrid-hp
reviewed_head = 18ef2000df24e848df3609a43d717445616b8113
phaseB_measurement_source = bd7a6023bde7a7c06d456e702af4b7f9f047b3fc
phaseB_aggregation_source = 9ac29db45b387d4590de084710abe2cc38b25ffe
phaseB_aggregate_sha256 = 3e606384f68ecad28d02eb4113ca515d24c39bab767df5586c61846ed44f7a04
review_status = PHASE_B_ACCEPTED_WITH_QUALIFICATIONS
p3_matched_trace_component = PASS
p4_basic_matched_trace_component = PASS_WITH_SCOPE_LIMIT
phaseC_p3_h5 = APPROVED_WITH_PRELAUNCH_GATES
phaseC_p3_h3 = NOT_APPROVED
p4_target_hybrid = NOT_APPROVED
h_adaptivity = DEFERRED_TO_FINAL_PHASE
ordinary_default_changed = false
whole_branch_merge = NOT_YET_APPROVED
```

Phase B 按 `review_report_v2.md` 的最小矩阵执行，没有重复 Case090、QEP36、目标光栅 full3D、Hybrid 或自适应计算。五条实测记录为：

```text
p2 / MPI1
p3 / MPI1
p3 / MPI4
p4 / MPI1
p4 / MPI4
```

本报告接受 Phase B 对基础 matching-interface 电切向迹、左右模态迹投影、MPI ownership、加阶积分与小型存储结构的组件资格。该结论不等价于目标光栅的完整 Maxwell 耦合已经通过，也不构成 p4 目标 Hybrid 的准入。

---

# 1. Phase B 已完成内容

## 1.1 空间与匹配几何

Phase B 使用 `h=10 nm` 的固定匹配结构网格：

```text
3D = hexahedron N1curl p
2D = quadrilateral N1curl p
3D interface x/y axes = 2D cross-section x/y axes
3D face-trace local dimension = 2D N1curl cell dimension
```

| degree | 3D global DoF | 2D trace global DoF | 3D face trace DoF/cell | 2D cell DoF |
|---:|---:|---:|---:|---:|
| p2 | 7,246 | 162 | 12 | 12 |
| p3 | 23,073 | 351 | 24 | 24 |
| p4 | 53,084 | 612 | 40 | 40 |

MPI1 与 MPI4 的 matching mesh hash、空间 global DoF、投影形状、trace-mass NNZ、积分阶次和近简并块结构一致。

## 1.2 电切向迹与符号

规范迹固定为：

```text
canonical electric trace = (E_x, E_y)
```

bottom 和 top 的 local-FEM outward normal 与 modal outward normal 均严格相反。仿射三维 Nédélec 场提取到二维迹空间后的最坏相对误差约为：

```text
p2: 5.951e-15
p3: 9.566e-15
p4: 9.835e-15
```

所有插值点均已解析，`unresolved_points=0`，并且没有 gather 完整三维场向量。

## 1.3 右重构与左 Petrov 投影

| shard | coefficient round-trip | right reconstruction residual | 最大 left unit projection error | Gram rank | Gram condition |
|---|---:|---:|---:|---:|---:|
| p2 MPI1 | `2.948e-16` | `3.485e-16` | `3.469e-18` | 2/2 | 30.4995 |
| p3 MPI1 | `2.828e-16` | `8.067e-17` | `1.112e-16` | 2/2 | 90.7920 |
| p3 MPI4 | `2.685e-16` | `3.326e-16` | `6.939e-18` | 2/2 | 90.7920 |
| p4 MPI1 | `5.769e-16` | `5.227e-16` | `2.220e-16` | 2/2 | 35.2663 |
| p4 MPI4 | `2.611e-16` | `4.466e-16` | `3.469e-18` | 2/2 | 35.2663 |

以上结果远低于冻结 Gate。Gram 矩阵均满秩，p3 和 p4 的两模态块使用 `near_degenerate_block_inverse`，没有将近简并块强行逐模对角归一化。

## 1.4 加阶积分

Phase B 显式使用：

$$
q_{\mathrm{selected}} = 2p + 2g + c + 2,
$$

其中平面线性几何 `g=1`，常系数 `c=0`；加阶对照使用：

$$
q_{\mathrm{raised}} = q_{\mathrm{selected}} + 2.
$$

| degree | selected | raised | trace-mass delta | Gram delta | coefficient delta |
|---:|---:|---:|---:|---:|---:|
| p2 | 8 | 10 | 0 | 0 | 0 |
| p3 | 10 | 12 | 0 | 0 | 0 |
| p4 | 12 | 14 | 0 | 0 | 0 |

该结果接受为当前平面、常系数、小型迹积分的充分性证据。它不能外推为曲边高阶几何或任意非光滑系数上的普遍零误差。

## 1.5 MPI 身份

| degree | MPI1→MPI4 最大 beta 相对差 | Gram condition 相对差 | Gram singular values 最大相对差 |
|---:|---:|---:|---:|
| p3 | `5.546e-14` | `6.887e-15` | `1.162e-14` |
| p4 | `4.267e-14` | `6.850e-15` | `9.464e-15` |

这些结果接受为 compact matching-trace invariant 的 MPI 身份。Phase B 没有 gather 完整本征向量，也没有进行 MPI1 与 MPI4 的全向量能量范数比较；因此不得把本结论描述为“完整模态向量逐自由度相同”。

---

# 2. 代码与存储审阅

## 2.1 可接受设计

`ModalTraceProjection` 当前存储为：

```text
sparse distributed trace mass
+ distributed right trace columns
+ distributed left trace columns
+ replicated small M x M Gram block
```

没有形成 `N_Gamma × N_Gamma` 的稠密接口矩阵。Phase B 两模态记录中的 replicated Gram 仅为 `2×2`。

三维场值通过 DOLFINx point ownership 在拥有单元的 rank 上计算，再把两个 complex128 切向分量返回请求 rank。该路径没有 gather 完整三维场，也没有 gather 完整模态向量。

## 2.2 当前规模限制

Phase B 的通信实现仍包含：

1. structured-axis metadata 的 communicator allgather；
2. Python object `alltoall` 发送切向复数二元组；
3. replicated `M×M` Gram；
4. 每次迹提取重新执行 point ownership。

这些设计在当前小型 matching fixture 和 Task33 的 M80–M160 current-scale anchor 中可以接受，但不是 0.7 nm、万级 M 或巨大接口的可扩展性证明。文档必须继续准确写为：

```text
no full field/mode vector gather
```

而不是笼统写为：

```text
no allgather or no replicated modal object
```

## 2.3 资源证据边界

Phase B 报告的是每 rank historical peak RSS 与小型组件时间，不是 Task33 重型求解要求的权威内存：

$$
\max\left(
\text{simultaneous live MPI worker RSS sum},
\text{container cgroup current}
\right).
$$

因此 Phase B 的约 239–262 MiB 记录只能说明小型 fixture 没有异常资源增长，不能用于批准 p3/h5 或 p4/h5 重型目标计算。

## 2.4 source cleanliness 边界

Phase B runner 的内部 source 检查使用 tracked status，并以 `--untracked-files=no` 排除未跟踪文件。历史 Phase B 记录不因此失效，但 Phase C 正式运行必须使用更严格的外部 watchdog source gate：

```text
git status includes all nonignored untracked paths
HEAD before = HEAD after = verified clean SHA
no tracked or nonignored untracked source changes
```

不得仅复用 Phase B runner 的 `source_clean_verified` 字段作为 Phase C 的完整 clean-worktree 证明。

---

# 3. 资格范围与未关闭项

## 3.1 p3

Phase B 已足以关闭 p3 的基础 matching electric-trace 组件：

```text
p3 3D/2D degree semantics = pass
p3 affine tangential trace = pass
p3 right reconstruction = pass
p3 left Petrov projection = pass
p3 two-mode near-degenerate Gram = pass
p3 MPI1/MPI4 compact identity = pass
p3 raised quadrature = pass
```

因此允许 p3 进入 Phase C 的目标光栅 `p3/h5` 最小全链路。

## 3.2 p4

Phase B 只使用两个模态，验证了一个二维近简并迹块。Phase A 中曾识别出的关键 p4 现象是四维近简并子空间的基底旋转。因此当前结论必须写为：

```text
p4 basic two-mode matched-trace component = pass
```

不能写为：

```text
all p4 near-degenerate trace blocks = qualified
```

在申请 p4 目标 Hybrid 前，至少需要一个小型 p4 四模态迹记录：

```text
mode count = 4
block size = 4
right reconstruction = pass
left Petrov projection = pass
Gram full rank = 4/4
principal-angle or block invariant = pass
MPI1/MPI4 compact identity = pass
```

该补测不阻塞 p3 Phase C。

## 3.3 尚未验证真实 H/traction 耦合

Phase B 验证了：

- `(E_x,E_y)` 电切向迹；
- normal opposition；
- 示例 `n×E_t` 的符号关系；
- 模态迹的左右投影。

它没有独立验证目标 Hybrid 弱式中的完整磁场或 traction 耦合项。因此真正的：

```text
E continuity
H / traction continuity
local DtN signs
bottom/top coupled block signs
```

必须在 Phase C 的 full residual、interface E/H 和 selected-plane E/H 对照中关闭。Phase B 不得被描述为完整 Maxwell interface coupling pass。

---

# 4. Phase B 处置

```text
Phase B p2 regression anchor = ACCEPTED
Phase B p3 basic matched trace = ACCEPTED
Phase B p4 basic two-mode matched trace = ACCEPTED_WITH_SCOPE_LIMIT
Phase B aggregate = ACCEPTED AS COMPONENT EVIDENCE
Case090 rerun = NOT REQUIRED
QEP36 rerun = NOT REQUIRED
Phase C p3/h5 = APPROVED WITH PRELAUNCH GATES
Phase C p3/h3 = NOT APPROVED
p4 target full3D/Hybrid = NOT APPROVED
```

Case090 仍绑定原高阶 3D Floquet source；Phase B 记录绑定包含迹修改的新 source。Phase C 必须生成自己的新 full3D 与 Hybrid 证据，不能使用 Case090 或 Phase B 小 fixture 代替目标求解。

---

# 5. Phase C：p3/h5 目标光栅最小全链路

## 5.1 Phase C0：启动前准备

在启动任何目标大算例前必须：

1. 冻结新的 clean source SHA；
2. full3D 与所有 Hybrid 记录使用同一数值 source SHA；
3. 使用严格 source watchdog，包括 nonignored untracked paths；
4. 刷新容器上限、宿主可用内存、cgroup current 和 swap；
5. 对 full3D、Hybrid M80、M120、M160 与 augmented anchor 分别做 candidate-specific 内存预测；
6. 一次只运行一个重型 case；
7. 不依赖 swap；
8. 不因 Phase B 的小型 RSS 直接批准目标运行。

启动 Gate 保持：

```text
two independent center predictions <= 11.5 GiB
conservative upper <= 12.8 GiB
controlled termination = 13.0 GiB
hard limit = 14.0 GiB or lower effective environment limit
```

如果任一候选不满足 Gate，记录 `not_run_by_memory_gate`，不得强行运行。

## 5.2 必跑最小矩阵

只批准以下 p3/h5 primary S-polarized 10° grazing 目标记录：

```text
1. p3/h5 full3D direct reference
2. p3/h5 Hybrid Schur-minimal M80
3. p3/h5 Hybrid Schur-minimal M120
4. p3/h5 Hybrid Schur-minimal M160
5. one augmented-direct anchor at the selected converged M
```

执行规则：

- 重型正式运行优先使用预测选择的一个 MPI 规模，不自动复制 MPI1/MPI4；
- Phase B 已提供组件 MPI identity，Phase C 只有发现并行异常时才增加第二 MPI 规模；
- augmented anchor 不需要对 M80/M120/M160 分别重复；
- 若 M120→M160 未通过截断 Gate且资源允许，条件增加 M240；
- 不运行 p3/h3；
- 不运行 p4 目标光栅；
- 不恢复完整 p/h 矩阵或自适应。

## 5.3 Phase C 必须比较

| 类别 | 必须记录 |
|---|---|
| reference identity | degree、h、波长、角度、方位角、偏振、材料、几何、接口位置 |
| 代数 | full explicit true residual、rows、NNZ、factor NNZ |
| official outputs | R、T、A、能量闭合 |
| 远场 | 各显著衍射级复振幅、相位与效率 |
| 接口 | actual E continuity、actual H/traction continuity、bottom/top sign |
| 场 | 选定平面 E/H 误差 |
| 模态 | QEP DoF/NNZ、有效模式数、M 漏斗、尾部系数、截断状态 |
| 路径 | augmented 与 Schur-minimal modal coefficients、local fields、R/T/A、residual 等价性 |
| 资源 | simultaneous worker RSS、cgroup current、swap、assembly/setup/factor/solve/recovery/postprocess 时间 |

至少保持：

```text
full true residual <= 1e-9
max absolute R/T/A delta <= 1e-5
M120 -> M160 truncation evidence required
interface E and H/traction Gates explicitly declared
selected-plane E/H Gates explicitly declared
no swap
memory authority below controlled termination
```

不得仅凭 R/T/A 接近就宣布 p3 Hybrid 等价。

## 5.4 Phase C 停止点

Phase C 完成上述 p3/h5 最小矩阵后必须停止并提交：

```text
outcomes/p3_h5_phaseC.md
records/stage3_p3_h5/phaseC_summary.json
response_v4.md
```

在新的独立 review 之前，不得进入：

```text
p3/h3
p4 target full3D/Hybrid
fixed-p equal-accuracy expansion
interface buffer
h adaptivity
```

---

# 6. 明确禁止的重复与外推

后续不得自动：

- 重跑 Case090 144 PDE；
- 重跑完整 QEP36；
- 重跑 Phase B 五条记录，除非迹数值代码再次变化；
- 将 Phase B 两模态 Gram 成本外推到 M160 或 M10000；
- 将小型 historical RSS 当作目标内存预测；
- 将 affine electric trace pass 写成完整 H/traction coupling pass；
- 将 p4 两模态块 pass 写成四维近简并块 pass；
- 将 p3/h5 成功自动外推到 p3/h3；
- 提前恢复自适应。

---

# 7. 当前最终结论

```text
Task033 Stage1 high-order 3D Floquet = ACCEPTED
Task033 Phase A p3/p4 QEP components = ACCEPTED_WITH_SCOPE
Task033 Phase B p3 matched trace = ACCEPTED
Task033 Phase B p4 basic matched trace = ACCEPTED_WITH_SCOPE_LIMIT
Task033 Phase C p3/h5 = APPROVED_WITH_PRELAUNCH_GATES
p4 four-mode trace block = REQUIRED BEFORE p4 TARGET HYBRID
p4 target Hybrid = NOT APPROVED
p3/h3 = NOT APPROVED
h adaptivity = FINAL PHASE
same branch continuation = APPROVED
ordinary default = UNCHANGED
whole branch merge = NOT YET APPROVED
```

下一步 Codex 应只执行 Phase C0 资源与 source preflight；Gate 通过后，按第 5 节运行 p3/h5 的最小 full3D + Hybrid 闭环。