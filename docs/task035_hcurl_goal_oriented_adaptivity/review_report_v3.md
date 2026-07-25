# Task035 Review V3：Phase C–D 连续项目开发授权

## 1. 审查结论

```text
review_status = PHASE_C_AND_D_CONTINUOUS_DEVELOPMENT_AUTHORIZED
phase_a = accepted
phase_b_algebraic_precursor = accepted_with_correct_scope
phase_b_real_fixture_minimum_gate = accepted_with_qualifications
phase_c_low_cost = authorized
phase_d_mesh_backend_bakeoff = authorized_after_internal_C_gate
review_checkpoint = after_phase_d
phase_e_adaptive_cycles = not_yet_authorized
p4_h5_heavy_adaptive = not_authorized
additional_review_between_phase_c_and_d = false
```

本轮审查对象为：

```text
branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
response = docs/task035_hcurl_goal_oriented_adaptivity/response_v3.md
implementation_commit = 563593b2195edd951c5a4f4d089e04c4f73045a1
base_master = 5002636852ffb67b4711443da70eb536c303e34e
```

Response V3 已经从环境和纯代数前置转入真实有限元开发：B1/B2 使用实际三维 hexa mesh、Basix N1curl、DOLFINx/UFL form、piecewise-complex coefficient 和 MPI1/2 compact records。其状态、测试节奏和 Windows Codex 客户端 + WSL 后端执行方式总体正确。

当前可以把工作重点转向真正的 estimator 筛选和网格 backend 开发，不再围绕 Phase A、Python 环境和重复全仓测试反复停顿。

本 Review 授权 Codex 连续完成：

```text
Phase C estimator bake-off
+
Phase D mesh-backend bake-off
```

Phase C 完成后不需要停下来等待审查；满足内部 Gate 后直接进入 Phase D。Phase D 完成后再提交一份集中 response 并停止等待 Review V4。

---

## 2. Response V3 已接受内容

以下内容接受，不要求重复：

1. Windows Codex 客户端作为用户唯一交互和编排界面；
2. WSL Ubuntu `/home/Projects/MyFEniCS` 作为 Git、Python、MPI、PETSc/SLEPc、DOLFINx 和计算后端；
3. canonical activation 使用 `source scripts/activate_myfenics_wsl.sh`；
4. Phase A 环境、ABI、MPI1/2/4/8、MUMPS/PEP 和 Task034 baseline binding；
5. algebraic precursor 的降级命名；
6. R2 只保留 `chi=|k|h/p` diagnostic，不再缩放 R1；
7. B1 real periodic Nédélec/H(curl) minimum fixture；
8. B2 real flat lossy layer / fixture goal minimum fixture；
9. serial/MPI2 compact scalar identity；
10. Phase C-low-cost entry 只标记为 `in_progress`，没有提前选择 production estimator；
11. B3/B4/R4 保持 pending/research lane；
12. 本轮没有运行目标 p4/h5 adaptive、Task034 heavy PDE 或 production mesh backend。

最终 targeted 结果：

```text
Task035 focused + governance/document = 49 passed
real FE provenance + Phase C entry = 8 passed
B1/B2 serial = pass
B1/B2 MPI2 = pass
serial/MPI2 identity = pass
Ruff/compileall/diff-check = pass
```

这些结果足以支持低成本项目开发继续，不需要为了本 Review 重跑 full repository pytest。

---

## 3. B1/B2 的准确资格边界

### 3.1 B1 接受范围

B1 真实验证了：

- 三维 hexahedral N1curl p1/p2 空间；
- 解析横向 plane wave 的实际 FE 插值；
- UFL cell curl-curl strong residual；
- interior facet curl-flux jump；
- FE tangential trace probe 的 Floquet phase consistency；
- orientation/phase fault injection；
- MPI-owned cell count/sum/sum-square identity；
- p2 相比 p1 的 field error 与 R1 indicator 下降。

但它当前的 Floquet 检查是固定 FE trace probes，不是完整的高阶 MPC DOF topology/entity-transformation 重新资格化。因此准确状态为：

```text
real_FE_periodic_trace_fixture_pass
not_a_new_full_Floquet_MPC_topology_qualification
```

Task034/Case090/Case093 已接受的 Floquet MPC 资格继续作为 production topology 依据；B1 只负责 estimator fixture 层。

### 3.2 B2 接受范围

B2 真实验证了：

- interface-aligned hexa mesh；
- N1curl p1/p2；
- piecewise-complex DG0 permittivity；
- 三个实际 h/p 离散点；
- field error、R1 indicator 和 DtN boundary component 的 measured trend；
- 实际 FE top trace 上的归一化零级反射功率 functional；
- coefficient-vector directional derivative 与中心有限差分一致；
- DtN operator perturbation 可检测。

但 B2 使用解析 Fresnel 场插值，不是由离散 Maxwell system 求出的 primal solution；当前 derivative 也不是由真实离散 adjoint solve 得到。因此：

```text
real_FE_goal_derivative_fixture_pass
actual_discrete_DWR_adjoint = pending
```

Response V3 已把 G1/G2 的 adjoint 和可排名能力保持 pending，处理正确。B2 中 R00 error 为机器精度，不能用于 estimator 排名；该受控结论继续保留。

---

## 4. Phase C：低成本 estimator bake-off 授权

Phase C 应从 fixture 转入当前项目目标几何的低成本实际筛选。不得只在 B1/B2 解析场上继续生成更多人为序列。

### 4.1 正式低成本点

至少覆盖：

```text
p2 / h5
p2 / h3
p3 / coarse point
10 deg grazing
S incidence
fixed Task034 geometry
```

优先复用 Task034 已接受的 Case093 records、fields 和 materialized hash-bound artifacts，不得无理由重跑 p4/h5 reference、M funnel 或 MPI matrix。

若局部 error proxy 需要 reference field，应明确采用：

- accepted p4/h5 Full3D discrete reference；或
- accepted p3/h3 discrete direction reference；或
- 局部 enriched/projected reference。

必须在 record 中说明 reference identity；不得称 continuum truth。

### 4.2 候选主线

Phase C 至少实际筛选：

```text
R1 standard residual/jump
R5 hierarchical/two-level 或 G1/G2 actual discrete adjoint 中至少一个
B1 external DtN split
R2 kh/p diagnostic only
```

R3 recovery 可作为独立对照；R4 不阻塞主线。

不能只比较 R1 与 R1 的不同归一化后宣称 bake-off 完成。最终应尽量形成：

```text
one residual/energy-oriented candidate
+
one goal-oriented or two-level candidate
```

若所有 goal/two-level lane 都失败，保留 `controlled_negative`，Phase D 仍可使用 provisional R1 进行 backend 工程比较，但不得宣称 Phase C 已选出完整双主线 estimator。

### 4.3 必测指标

对每个候选记录：

- global estimator 与各 component；
- effectivity 或明确的 proxy ratio；
- cell indicator 与 local-error proxy 的 Spearman/Pearson correlation；
- top marked set overlap；
- marked-set hash；
- assembly time 与额外内存；
- serial/MPI2，必要时 MPI4 partition stability；
- R/T/A、A_volume、R00 和显著衍射级的目标差异；
- refinement 后 observable error reduction。

相关系数只用于筛选，不能单独构成通过。真正的主 Gate 是：

```text
按该 estimator 标记并完成低成本 refinement 后
预定 observable error 实际下降
且其他关键 observable 没有隐藏恶化
```

### 4.4 Phase C 与 Phase D 可协同迭代

由于“refinement 后误差下降”需要一个可工作的局部 mesh backend，Phase C 与 Phase D 可以在本批次中迭代：

```text
C 初筛 estimator
→ D 构造低成本 backend candidate
→ 回到 C 做 actual marked refinement Gate
→ 再完成 D backend 比较
```

不需要因为严格的字母顺序停下来等待 review。

---

## 5. B3/B4 并行完成要求

B3/B4 不阻塞 Phase C 的开始，但必须在 Phase D 最终 backend 决策前得到 measured decision。

### 5.1 B3 material interface / corner

至少需要：

- actual material tags 和 coefficient jump；
- interface residual 从 FE field/trace 计算；
- tag/coefficient fault injection；
- local enriched/reference proxy；
- indicator 排名与 local error 的可审查关系；
- directional preference 由 defect/candidate solve 得出，不硬编码 axis。

### 5.2 B4 Hybrid interface

至少需要：

- 实际 matching trace 或已有小型 QEP/Hybrid fixture；
- Et/Ht projection；
- spatial、external DtN 和 internal M 的独立 perturbation；
- 至少两个低成本 M 值；
- QEP eigen residual 保持 diagnostic；
- MPI1/2 或 MPI1/4 identity。

某一 lane 失败时保留 `controlled_negative` 并停止该 lane，不停止整个 C–D 批次。

---

## 6. Phase D：mesh-backend bake-off 授权

Phase C 内部筛选达到可用 provisional estimator 后，直接进入 Phase D，不等待额外 review。

至少比较：

1. Task034 strip/tensor mechanism，作为 negative control；
2. 真正局部的 multi-block conforming hexa regeneration candidate；
3. DOLFINx simplex/tetra marked refinement control lane；
4. metric/size-field 路径仅在周期拓扑可审查时作为 diagnostic。

### 6.1 multi-block hexa 最低要求

当前 Task 的 MVP 可以先服务固定 Task034 geometry，不要求一次实现任意 CAD 通用网格器，但代码应进入可复用 `src/geometry/` 模块，不继续堆在 task-numbered runner 中。

至少检查：

- local block refinement；
- x/y periodic mate closure；
- periodic corner/edge/face signature；
- material plane exactness；
- Hybrid top/bottom matching plane exactness；
- no unqualified hanging nodes；
- positive Jacobian；
- 可审查的尺寸过渡；
- deterministic plan/mesh hash；
- tag transfer/rebuild；
- Nédélec orientation；
- MPI repartition/ghost consistency。

### 6.2 directional candidates

至少支持并筛选：

```text
x, y, z, xy, xz, yz, xyz
```

方向必须来自 directional defect、projection error 或 local candidate comparison，不能对所有角点写死同一方向。

### 6.3 tetra control

四面体 lane 用于区分：

```text
estimator 正确但 hexa backend 受阻
vs
estimator 本身错误
```

不得将 tetra 与 hexa 的 DoF、误差和时间在没有说明元素类型/阶次/几何逼近差异时直接比较。

### 6.4 Phase D 允许的负结论

若 multi-block hexa 无法满足局部、共形和周期同步要求，可以得到：

```text
hexa_backend_blocker
```

但仍应完成 tetra control 和 strip negative control。该结论是合格的工程决定，不应导致整个 Task 在中途长期卡住。

---

## 7. 两阶段连续执行与停止规则

本批次授权：

```text
Phase C
+
Phase D
```

Codex 不得在以下普通情况中停止等待用户或 ChatGPT：

- 单个 estimator 失败；
- 单个 fixture 失败但原因明确；
- 某个 mesh backend 形成 controlled negative；
- README、schema、record、lint、链接或 metadata 小问题；
- targeted test 的明确局部失败；
- Phase C 通过并准备进入 Phase D。

处理方式应是：

```text
局部修复并 targeted rerun
或
关闭失败 lane、保留证据、继续其他主线
```

只有以下情况立即停止整个批次：

1. WSL complex ABI、source SHA 或 baseline hash 不一致；
2. production/accepted core 被意外修改且旧证据失效；
3. MPI identity 出现无法局部解释的系统性失败；
4. full true residual 或正式物理 observable 系统性失败；
5. 数学定义不明确且继续会使结果失真；
6. negative Jacobian、周期拓扑破坏或未资格化 hanging-node 被用于正式正结果；
7. 内存、swap、磁盘或进程终止 Gate；
8. 工作需要越过本 Review 启动 p4/h5 heavy adaptive、Phase E 或 ordinary-default 变更。

---

## 8. 测试节奏

继续使用 Windows Codex 客户端编排、WSL Ubuntu 执行。环境敏感命令保持单 shell：

```powershell
wsl.exe -d Ubuntu -- bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && <command>'
```

测试节奏：

```text
每个小改动：单元/单 fixture targeted test
每个 estimator 或 backend 收口：serial + MPI2，必要时 MPI4
Phase C 收口：Task035 Phase C focused suite
Phase D 收口：Task035 C+D focused suite
整个 C–D 批次结束：正确 activation 下 full pytest 一次
```

不得重复：

- Phase A 环境完整资格化；
- MPI1/2/4/8 MUMPS/PEP matrix；
- Task034 六份 artifact 全量 hash；
- Task034 p3/h3、p4/h5、M funnel 或 MPI heavy matrix；
- 每次小改动后的 full pytest。

正式 C/D measured records 应优先在 clean committed source SHA 上运行。若在提交前运行，必须记录完整 tracked content hashes，并在阶段收口后用最终 commit 重跑相应低成本 record；不得让正式结论只绑定 dirty/uncommitted source。

---

## 9. Phase D 后集中交付

完成 C–D 批次后新增：

```text
docs/task035_hcurl_goal_oriented_adaptivity/response_v4.md
```

不要创建额外 addendum 或平行 review 文档。

Response V4 至少报告：

- 精确 base、实现和最终 branch HEAD；
- Phase C estimator matrix 与各 lane 决定；
- p2/h5、p2/h3、p3 coarse 的 measured results；
- marked refinement 后 observable error reduction；
- B3/B4 决定；
- Phase D backend comparison；
- hexa/tetra/strip 的 locality、DoF、quality、periodic、orientation、MPI、memory/time；
- 所有 controlled negatives；
- focused/full test results；
- 是否存在进入 Phase E 的可信 estimator + backend 组合；
- 工作树状态和 evidence index。

完成后停止等待 Review V4。不得自动进入：

```text
Phase E adaptive cycles
Phase F p4/h5 mainline
任何 p4/h5 heavy adaptive run
```

除非用户或下一份 review 明确授权。
