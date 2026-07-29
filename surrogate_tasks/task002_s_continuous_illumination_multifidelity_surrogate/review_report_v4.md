# Task002 Review Report V4

## 1. 审阅结论

```text
review_status = M3_design_authorized_after_targeted_preflight_corrections
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
M2C_evidence = approved_and_retain
parameterized_Full3D_route = approved_with_runtime_identity_fix
p5_80_angle_solver_domain = approved
p4_to_p5_multifidelity = rejected
production_surrogate_route = Full3D_p5_h10_single_fidelity
Hybrid_production = hard_quarantined_and_approved
M3_design = authorized_after_P0_fixes
M4_bulk_generation = not_authorized
surrogate_training = not_authorized
angle_DOE = not_authorized
production_inversion = not_authorized
required_next_action = M3R_single_fidelity_schema_and_frozen_design
```

M2C 已完成了决定求解路线所需的主要工作：参数化 Full3D p5/h10 在中心几何的 80 个角度全部通过；p4/h10 与 p5/h10 的统一多保真关系被定量否决；Hybrid 已从 Task002 production route 硬隔离。因此，Task002 可以离开 solver-selection 阶段，进入**修订后的 M3：p5 单保真数据 schema、设计与 split 冻结**。

但是，不能直接执行 M4 批量 PDE。代码审阅发现三个 production-data blocker：

1. 当前固定 diffraction-order window 在高方位角漏掉可传播的 `m=+2,+3`；
2. 当前“真实运行拓扑 smoke”实际将同一个解析 helper 的输出与自身比较，没有从已创建的实际 mesh、cell tags 和 function space 反读身份；
3. 代码和旧任务书仍允许/描述 p4 LF、多保真 split，而最终 production 决定已经是 p5-only。

本 Review 授权 Codex 完成这些 P0 修正并冻结 M3 设计，完成后停止等待 Review V5。不得自行进入 M4。

---

## 2. 已接受的 M2C 结果

### 2.1 Full3D p5/h10 作为 operational forward authority

接受：

```text
model_id = S_HF_FULL3D_STATIC_P5_H10
solver_route_id = full3d_static_uniform_n1curl_p5_h10
element = uniform N1curl p5
mesh family = boundary-fitted fixed logical topology (6,3,14)
backend = assembly-time static condensation
MPI = 2
threads/rank = 1
```

中心几何的角域：

```text
grazing = [0.5,0.75,1,2,4,6,8,10] deg
azimuth = [0,5,10,15,20,30,45,60,75,90] deg
```

共 80 点，80/80 完成并通过 residual、energy、zero-swap、cleanup 和现有 compact extraction Gate。59 个新点 wall 约 61.55--85.27 s，最大 RSS 约 4.42 GB，适合在当前本机逐个生成数据。

p5/h10 的正式语义冻结为：

```text
best_available_operational_high_fidelity
not continuum truth
```

### 2.2 p4→p5 多保真关系正式否决

接受生产决定：

```text
production_surrogate = Full3D p5/h10 single fidelity
```

主要依据：

```text
A_balance/A_volume Spearman = 0.74587 < 0.90 Gate
0.5°/0° LF/HF geometry-sensitivity cosine = 0.68425
2°/15° LF/HF geometry-sensitivity cosine = 0.82875
```

虽然小型 discrepancy interpolation pilot 表现较好，但它不能覆盖吸收相关性和反演几何灵敏度失败。不得为了保留“multi-fidelity”名称而继续将 p4 作为生产 LF。

p4/h10 仅保留为 diagnostic fidelity；p4/h7.5 仅保留为 h-refinement/discretization audit。

### 2.3 Hybrid hard quarantine

接受 B2：

```text
hybrid_route_status = deferred_known_near_degenerate_bug
```

Task002 production schema、campaign 和 CLI 必须继续拒绝 Hybrid。历史 Case112--114 只作为不可变 diagnostic evidence。Hybrid p6 的实际身份已更正为 uniform N1curl p6。

### 2.4 Full3D p5 的离散误差语义

现有四个 p4/h7.5 对 p5/h10 anchor 的 aggregate maximum envelope 可作为初始保守证据：

```text
R_total     2.73315e-3
T_total     3.78696e-4
A_balance   2.64436e-3
A_volume    2.64436e-3
```

但四个中心几何角度不足以证明完整四维域上的误差分布。最终角度 DOE 和 Task003 必须使用：

```text
Sigma_total = Sigma_measurement + Sigma_surrogate + Sigma_discretization
```

M3 中应冻结额外的少量 discretization-audit 设计；不需要运行完整 p4/h7.5 角域图。

---

## 3. P0-1：固定 diffraction-order schema 不完整

当前：

```text
FIXED_M_ORDERS = (0,-1,-2,-3,-4,-5,-6,-7,+1)
```

该集合最初针对接近 `phi=0°` 的掠入射条件设计，不适用于完整 `phi=0--90°` 连续域。

在 `phi=90°` 时：

```text
kx_inc = 0
k0 = 2*pi/13.5 = 0.465421 1/nm
Gx = 2*pi/50 = 0.125664 1/nm
```

因此 top air 中：

```text
m=+2: |2 Gx| = 0.251327 < k0  -> propagating
m=+3: |3 Gx| = 0.376991 < k0  -> propagating
```

但当前 mother response 没有 `+2,+3`。现有 `fixed_order_schema_complete` 只检查“预期的旧九个 order 是否都提取到”，并不检查是否遗漏了其他传播/功率携带 order，所以 80/80 Gate 不能证明 order window 完整。

### 必须修正

1. 在完整正式角域上做高分辨解析审计，并结合 Case114/115 raw `auto_propagating` order tables 检查实际功率；
2. 候选新固定集合至少应覆盖 top-air union：
   ```text
   m = -7,-6,-5,-4,-3,-2,-1,0,+1,+2,+3
   n = 0
   ```
   最终集合以 top/bottom 解析和 raw-power audit 为准；
3. 新建 observable schema，例如：
   ```text
   task002.fixed-n0-orders.v3
   ```
4. 更新：
   - order extractor；
   - dataset order axis；
   - masks、hashes、tests；
   - cutoff/order-window audit；
5. 对已有 Case114/115 raw artifacts 只做 re-extraction/checker，不因 schema 升级重跑 PDE；
6. 在任何正式 M4 sample 前冻结唯一的 v3 schema。

`n!=0` 仍作为 y-invariant leakage diagnostic，不进入 production output，但 raw leakage 必须保留。

---

## 4. P0-2：当前 real-run topology smoke 是自我比较

`run_task002_full3d.py` 在 PDE 完成后调用：

```text
task002_full3d_topology_identity(parameters)
```

该函数根据 config 和逻辑网格计划重新计算 topology identity，并没有从实际创建的：

```text
mesh connectivity
mesh geometry coordinates
actual cell tags
actual boundary/Floquet entities
actual H(curl) function space
```

反读身份。

Case115 checker 随后再次调用同一个 helper，并比较两个结果。因此：

```text
identity_matches_static_audit = true
```

目前主要证明 helper 是 deterministic，不是“实际运行网格与计划一致”的独立证据。

### 必须修正

新增实际 runtime identity，例如：

```text
actual_runtime_mesh_identity
```

它必须从真实 mesh/V/cell_tags/facet topology 获取：

- actual global cell count；
- partition-independent logical connectivity或canonical cell-vertex hash；
- actual coordinate-axis values/hash；
- actual material cell-tag topology/hash；
- actual periodic boundary entity counts/identity；
- actual element family/cell/degree/signature；
- actual global DoF count和layout identity；
- actual mesh-axis counts。

然后分别保存：

```text
planned_topology_identity
actual_runtime_topology_identity
planned_vs_actual_gate
```

在 9 个静态几何和至少现有 10 个真实 smoke 中，必须用 actual runtime identity 完成比较。不得再用同一 helper 两次构成所谓独立 smoke。

该修正若只增加记录和验证、不影响 mesh/matrix/RHS，可以不重跑 Case115 qualification PDE；但必须在新 clean baseline 下重新运行最小 5 个 p5 smoke 验证 actual runtime Gate。

---

## 5. P0-3：production 代码必须真正冻结为 p5-only

当前最终路由是 p5-only，但代码仍有以下旧多保真语义：

- `TASK002_FIDELITIES` 同时允许 p4 和 p5；
- production campaign 可接受 p4 model ID；
- dataset schema 仍包含 `train_lf_indices` 和 p4 LF route；
- `task.md` 的 Sections 2、5、6、M3--M7 仍以 Hybrid LF/HF / multi-fidelity 为主。

这会使下一轮 Codex 误按旧任务书生成 p4 bulk。

### 必须修正

建议分为：

```text
TASK002_PRODUCTION_FIDELITIES:
  S_PROD_FULL3D_STATIC_P5_H10

TASK002_DIAGNOSTIC_FIDELITIES:
  S_DIAG_FULL3D_STATIC_P4_H10
  P4_H7P5_DISCRETIZATION_AUDIT
  historical Hybrid identities
```

要求：

1. production campaign/CLI 对 p4 和 Hybrid fail closed；
2. diagnostic runner 使用显式 diagnostic gate，不得写入 production campaign manifest；
3. 新建 single-fidelity dataset schema v2，推荐数组：
   ```text
   train_indices.npy
   frozen_validation_indices.npy
   discretization_audit_indices.npy   # optional separate audit table/reference
   ```
   不再把空/旧 LF split 作为 production 语义；
4. production dataset 只允许 p5 route；
5. 更新 README/task/outcomes，明确 Review V4 supersedes 旧 Hybrid/multi-fidelity sections；
6. M6 不再训练 multi-fidelity GP。正式候选只保留：
   - low-order PCE/Chebyshev diagnostic；
   - single-fidelity Matérn-5/2 ARD GP。

---

## 6. P0-4：Case115 的“frozen validation disjoint”表述不正确

`fixed_hf_angle_pilot()` 的 9 个角度中，以下 6 个属于 80-point angle grid：

```text
(0.5,0), (0.5,90), (10,0), (10,90), (0.5,45), (10,45)
```

只有 `grazing=5.25°` 的三个点是 off-grid。

但 checker 将：

```text
validation_is_frozen_and_disjoint_from_training = true
```

直接写死为 true，并未实际检查交集。因此该 interpolation pilot 是**qualification diagnostic**，不能称为严格 frozen validation。

这不改变“p4 multi-fidelity 被拒绝”的最终结论，因为拒绝还由 Spearman 和 geometry sensitivity 独立支持；但 tracked report 必须添加 addendum，更正其语义。

M3 的正式 validation 必须：

- 使用独立 seed；
- 与 training/anchors 做精确 tuple/hash intersection test；
- 在写文件时 fail closed；
- validation 永远不参与超参数和模型选择。

---

## 7. P1：代理角度特征应显式包含 normal wavevector information

当前主特征：

```text
[h_norm, w_norm, kx/k0, ky/k0]
```

在 `grazing=0.5--10°` 中，`cos(grazing)` 变化很小，而物理 normal component：

```text
kz/k0 = sin(grazing)
```

近低掠射端线性变化并显著影响响应。虽然 `(kx,ky)` 在数学上可以恢复 grazing/azimuth，但其 Euclidean distance 会压缩低掠射差异。

在 training-only CV 中至少比较：

```text
A = [h_norm,w_norm,kx/k0,ky/k0]
B = [h_norm,w_norm,kx/k0,ky/k0,kz/k0]
C = [h_norm,w_norm,sin(grazing),cos(phi),sin(phi)]
```

不得使用 frozen validation 选择 feature map。建议优先采用单位传播方向三分量，允许 ARD 处理冗余。

---

## 8. 修订后的 M3R：p5 单保真设计与 split 冻结

P0 修正和 targeted tests 完成并提交新 clean implementation SHA 后，允许执行 M3R。M3R 只设计和冻结点表，不运行 production PDE。

### 8.1 正式文件

生成并 track：

```text
training_design.json
frozen_validation_design.json
candidate_pool.json
discretization_audit_design.json
split_hashes.json
sampling_design.md
```

旧：

```text
lf_design.json
hf_initial_design.json
```

不再是 production authority。

### 8.2 初始 p5 training design

建议：

```text
scrambled Sobol seed = 20260729
initial interior points = 64
```

增加并去重：

- 16 个四维 domain corners；
- 中心几何的角度 corner/edge/center anchors；
- 高度和宽度轴向 anchors；
- schema v3 cutoff 两侧的少量 deterministic anchors。

初始 training 总数建议约 80--96，记录实际去重数量。预算不是硬凑数。

### 8.3 Frozen validation

```text
scrambled Sobol seed = 20260730
initial validation = 16 points
```

要求：

- 与 training/anchors 精确不相交；
- 单独 hash；
- 不用于 kernel/feature/transform/model selection；
- 只有 dataset/source bug 才能整体作废。

### 8.4 Candidate pool

```text
scrambled Sobol seed = 20260731
candidate count >= 4096
```

用于后续 single-GP uncertainty、PCE/GP disagreement、coverage、cutoff proximity 和 Fisher potential acquisition。

### 8.5 Discretization-audit design

现有四个 center-geometry p4/h7.5 anchors保留为 qualification。另冻结 6--10 个 audit candidates，覆盖：

- geometry corners/axes；
- low grazing；
- intermediate/conical azimuth；
- p5 response extrema；
- 后续推荐角度附近。

这些不进入 surrogate training，只用于构造/验证 `sigma_discretization`。是否全部运行由后续证据决定。

### 8.6 Source纪律

Case114/115 数据属于 solver qualification。它们混合了历史和 M2C source SHA，不得直接并入正式 production dataset。

M4 的所有 training/validation PDE 必须绑定 P0 修正后的**一个新 clean full SHA**。若要复用任何旧 PDE，必须先建立正式 numerical-core equivalence contract；本 Review 默认不授权复用。

---

## 9. M3R 通过条件

Review V5 只有在以下全部满足时才考虑授权 M4：

1. observable v3 覆盖完整传播/重要功率 order window；
2. Case114/115 raw records可按 v3 无 PDE 重跑地重新提取并通过 checker；
3. actual runtime topology/element identity Gate通过；
4. production schema/campaign/dataset hard-freeze为 p5-only；
5. p4/Hybrid production 请求 fail closed；
6. Case115 false-disjoint validation表述已更正；
7. training/validation/candidate/audit 设计冻结并 hash-bound；
8. validation 与 training 精确不相交；
9. 新 single-fidelity dataset schema和checker通过 synthetic tests；
10. 所有设计绑定新 clean implementation SHA；
11. 尚未运行 M4 bulk、surrogate fit、angle DOE 或 inversion。

---

## 10. 下一阶段边界

本 Review 的结论是：

```text
可以进入下一步：M3R 设计冻结
不能直接进入：M4 p5 bulk generation
```

M3R 完成后，预计 M4 将按以下顺序执行：

```text
1. p5 initial training 80--96 points
2. p5 frozen validation 16 points
3. compact dataset v2 + checker
4. preliminary CPU PCE/GP diagnostic
5. only if required: expand training toward 128 and adaptive additions
```

每次只运行一个 Full3D p5 solve，MPI2/thread1，zero swap，checkpoint/resume。

---

## 11. 交付物

建议新增：

```text
benchmarks/cases/116_task002_single_fidelity_design/
  config.json
  expected.json
  records/order_window_v3_audit.json
  records/runtime_topology_identity.json
  records/single_fidelity_schema.json
  records/design_and_split.json
  records/case115_validation_addendum.json

surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
  outcomes/m3r_single_fidelity_design.md
  outcomes/order_schema_v3.md
  outcomes/runtime_topology_audit.md
  response_v5.md
```

完成后提交并只推送当前代理分支，停止等待 Review V5。不得自行进入 M4--M10。
