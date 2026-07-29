# Task002 Review Report V3

## 1. 审阅结论

```text
review_status = targeted_changes_required_before_M3
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
M2B_evidence = approved_and_retain
p4_h10_underresolved_conclusion = approved
hybrid_p5_same_p_consistency = approved
axial_route_large_branch_root_cause = rejected
cross_section_double_floquet_probe = approved_with_test_limitations
hybrid_p6_near_degenerate_root_cause = approved
route4_full3d_direction = approved
proposed_LF_full3d_p4_h7p5 = rejected_as_low_fidelity
M3_bulk_generation = not_authorized
surrogate_training = not_authorized
angle_DOE = not_authorized
production_inversion = not_authorized
required_next_action = M2C_full3d_hierarchy_and_core_robustness
```

M2B 已经完成了一次有价值的 solver-domain qualification，并把此前混在一起的几个问题分开：

1. `p4/h10` 在低掠射区域确实欠分辨；
2. Hybrid p5 与同阶 Full3D p5 高度一致，p4→p5 的大响应跳变不是 Hybrid coupling 制造的；
3. continuous/discrete axial route 的差异只有 `O(1e-7)`，不是大分支跳变根因；
4. 双 Floquet 高阶约束通过了真实解析和代数 probe；
5. p6/45° 的失败已定位为 near-degenerate blocks 被错误拆分；
6. Hybrid p4 在 80-angle map 中只有 39/80 formal pass，不能用于连续角域正式数据生成。

因此，**暂停 Hybrid 作为 Task002 V1 的 production route 是正确决定**。但当前 `solver_routing_map.md` 提议把 `Full3D p4/h7.5` 作为 LF、`Full3D p5/h10` 作为 HF，这个层级在成本上倒置，不能直接采用：

```text
Full3D p4/h7.5 measured maximum:
  wall ≈ 76.98 s
  peak RSS = 5,289,787,392 B

Full3D p5/h10 measured maximum:
  wall ≈ 62.56 s
  peak RSS = 4,218,630,144 B
```

`p4/h7.5` 比 `p5/h10` 更慢、占用更多内存，只能作为独立 h-refinement / discretization audit，不能称为 low fidelity。

下一阶段应改为：

```text
candidate LF = Full3D static uniform N1curl p4/h10
candidate HF = Full3D static uniform N1curl p5/h10

p4/h7.5 = convergence/discretization audit only
```

如果完整角域证据表明 p4→p5 discrepancy 不够平滑、灵敏度方向不一致或无法用少量 HF 校正，则放弃多保真，直接建立 p5 single-fidelity surrogate；不得为了保留“multi-fidelity”名称而强行使用低质量 LF。

---

## 2. 本轮接受并冻结的 M2B 证据

### 2.1 p4/h10 欠分辨

强制四点的独立 Full3D 结果证明：

| point | p4/h10 R | p5/h10 R | p4/h7.5 R |
|---|---:|---:|---:|
| 0.5° / 15° | 0.818608 | 0.631656 | 0.634389 |
| 0.5° / 45° | 0.649408 | 0.621729 | 0.623374 |
| 2° / 15° | 0.325438 | 0.081682 | 0.083440 |
| 10° / 45° | 0.000828 | 0.000769 | 0.000773 |

`p4/h7.5` 与 `p5/h10` 在四点选择同一响应分支，因此粗 `p4/h10` 的低掠射分支不能作为 high-fidelity truth。

但是，四点 `p4/h7.5 - p5/h10` 的最大 R 绝对差仍达到：

```text
2.733e-3, 1.645e-3, 1.758e-3, 3.357e-6
```

所以 `p5/h10` 目前应称为：

```text
best_available_operational_high_fidelity
```

而不是 continuum truth。后续反演必须保留 discretization/model-discrepancy term。

### 2.2 Hybrid p5 same-p consistency

12 个 selected points 中，Hybrid p5 与 Full3D p5 的最大 R/T/A 差为 `1.853e-5`。这足以证明大 p-branch jump 不是 Hybrid p5 coupling 的主要错误。

该结果只批准“same-p consistency”结论，不重新批准 Hybrid production route。Hybrid 仍受以下问题阻塞：

- p6 near-degenerate block split；
- p4/p5 volume-energy Gate failures；
- mode-set continuity 和 basis identity 尚未达到 production 要求；
- 当前尺度下 Hybrid p4 还没有速度优势。

### 2.3 Axial Route A/B

`continuous_beta + continuous_qep_beta` 与 `full3d_uniform_cg + scalar_cg_discrete_derivative` 的最大 observable 差仅 `3.30e-7`。因此离散 axial mapping 不是 p4→p5 的 `O(1e-1)` 跳变根因。

这不代表 scalar-CG axial mapping 已成为通用 exact Maxwell operator。它仍是经过有限 scope 验证的 compatibility approximation；由于 Task002 V1 改用 Full3D route，本轮不继续扩大其 production claim。

### 2.4 双 Floquet probe

48/48 个 probe 通过，最大：

```text
analytic quasiperiodic residual = 1.898e-15
slave-row residual              = 0
C^H A C action error            = 1.517e-16
```

这足以排除当前中间方位角失败由基本 x/y/corner phase 或高阶 orientation 错误直接造成。

但现有 `C^H A C` probe 使用同一个 `reduce_matrix_hermitian()` 路径，并采用对角测试矩阵，因此属于强 self-consistency test，不是完全独立的显式消元 authority。第 7 节要求增加一个小型 off-diagonal dense reference，但这不是 Full3D production route 的 blocker。

### 2.5 p6 near-degenerate root cause

p6 在 `0.5°/45°` 的失败已定位到：

```text
block [114,115]
block [116,117]
```

被 beta-only clustering 拆开，而 block 间 cross-overlap 超过 Gate。最坏 row sum 为 `1.7765586e-6`。相同问题也出现在 `1°/45°` 和 `10°/45°`。

这证明：

```text
PDE residual 正常
candidate pool 数量足够
reciprocal beta 基本正确
真正失败在 near-degenerate block partition / normalization
```

该缺陷不能通过放宽 `1e-6` Gate 处理。

---

## 3. 对当前 solver-routing 决定的修正

### 3.1 拒绝 `p4/h7.5` 作为 LF

一个 low-fidelity model 至少应满足：

```text
cost_LF << cost_HF
```

当前实测相反：

```text
p4/h7.5 wall_max  > p5/h10 wall_max
p4/h7.5 RSS_max   > p5/h10 RSS_max
```

所以：

```text
Full3D p4/h7.5 = validation anchor / discretization audit
```

不得用于 LF bulk，也不得出现在模型 ID 中作为 low fidelity。

### 3.2 新候选 hierarchy

```text
LF candidate:
  model_id = S_LF_FULL3D_STATIC_P4_H10
  element  = uniform N1curl p4
  mesh     = fixed-topology h10 family
  backend  = assembly-time static condensation

HF candidate:
  model_id = S_HF_FULL3D_STATIC_P5_H10
  element  = uniform N1curl p5
  mesh     = same fixed-topology h10 family
  backend  = assembly-time static condensation
```

该 hierarchy 的优点：

- p4/h10 已完成中心几何 80-angle map；
- p5/h10 实测约 4 GiB，无 swap；
- p5/h10 比 p4/h7.5 更便宜；
- 两层采用同一 Full3D formulation，避免 Hybrid route identity 变化；
- p4 的大 bias 可显式交给 discrepancy model，但必须先证明可学习性。

### 3.3 允许 single-fidelity fallback

M2C 完成后必须做二选一：

```text
A. p4->p5 discrepancy 平滑且灵敏度相关
   -> 使用 Full3D p4/h10 LF + p5/h10 HF

B. discrepancy 不平滑、通道符号/敏感度不一致或 MF validation 无收益
   -> 放弃 LF，使用 Full3D p5/h10 single fidelity
```

禁止第三种做法：为了保持 multi-fidelity 名称而继续使用一个不能稳定修正的 p4 层。

---

## 4. 前一轮静态代码审查中仍未修正的问题

### R1：历史 Hybrid HF 元素身份仍被错误描述

Task002 文档曾把 Hybrid HF 写为：

```text
p5 trace / p6 interior exact sequence
```

但 `task001_stage4_config()` 只设置 `nedelec_degree=6`，没有设置：

```text
nedelec_trace_degree = 5
nedelec_interior_degree = 6
```

所以 Case112--114 中的 Hybrid p6 实际是：

```text
uniform N1curl p6
```

而不是 fixed p5-trace/p6-interior。

必须：

1. 修正文档、model registry、outcomes 和 future record identity；
2. 历史 raw records 不改写，但增加 explicit identity addendum；
3. 每个新 record 保存：
   - `nedelec_fixed_trace_enabled`；
   - resolved trace/interior degree；
   - actual UFL/Basix element signature；
   - topology/element hash。

Route 4 的 Full3D p4/p5 均应明确称为 uniform N1curl。

### R2：未来 h/w 参数化 Full3D runner 尚未建立固定拓扑合同

Case114 固定 `h=120,w=17`，所以没有测试几何变化时的 topology continuity。

正式 surrogate 不能直接调用通用 `run_3d_cases` 的 target-size mesh policy。必须新建 Task002 Full3D config/runner，冻结：

```text
x region cell counts
substrate cell count
grating-height cell count
air cell count
y cell count
cell connectivity
material tag topology
```

改变 `h,w` 时只能移动已冻结拓扑的坐标，不得改变：

```text
cell count
connectivity
DoF layout
periodic entity identity
```

每个样本应保存 resolved x/y/z axes、connectivity hash、cell-tag hash 和 DoF-layout identity。

### R3：Hybrid near-degenerate clustering 逻辑已知有缺陷

当前代码先按 beta 距离构造 groups，再在各 group 内求逆归一化；`block_rotation_tolerance` 的语义没有真正用于跨 group 合并。对于 p6/45°，相邻 blocks 的 beta 和 Q' overlap 已证明需要合并。

修复要求见第 8 节。Hybrid 未修复前必须从 Task002 model registry 和 formal campaign route 中 hard-disable，而不是只在文档中写“暂停”。

### R4：解析 reciprocal negative basis 的 full/reduced representation 不一致

当前 analytic negative basis：

- full vector 执行 `(Et,Ez)->(Et,-Ez)`；
- reduced vector 仅复制 positive reduced vector；
- polynomial residual、biorthogonality metadata 直接复制。

因此 negative mode 的 full/reduced objects 不严格代表同一个向量。主耦合多使用 full vector，但 mode tracking、reduced overlap 和未来 continuation 可能被污染。

若继续保留 Hybrid，必须通过 constraint transform 正确生成/限制 negative reduced vector，并重新计算：

```text
Q(-beta) residual
left residual
Q' overlap
full = C q residual
```

### R5：当前 mode-continuation metric 仍是诊断性而非物理 authority

Case114 archive 使用 rank-0 gathered full coefficient vectors、Euclidean normalization 和 Euclidean QR/SVD。Nedelec coefficient vector的 Euclidean norm不是物理 L2/H(curl)/trace norm；不同 Floquet phase 下也没有去除 Bloch gauge。

因此当前结果足以证明“所选 mode set 强烈交换”，但不应把数值 principal angle 当成严格物理子空间角。

未来 Hybrid continuation 应使用：

- full physical space mass/trace Gram；
- 或去除 Bloch factor后的 periodic envelope；
- near-degenerate block principal angle；
- cluster-level continuation，而不是单个 mode index。

### R6：Hybrid whole-domain closure 的主要缺口应表述为接口功率不一致

Case114 energy ledger 中，p4/45°：

```text
top local interface outward flux = 1.3998139354
middle top positive-z flux        = 1.3980244427
```

差值约 `1.7895e-3` code units，除以 incident power 后约为 whole-domain `3.3e-4` closure 缺口。

所以问题不能笼统写成“volume postprocessing”。需要区分：

```text
local-FE interface variational work
modal interface variational work
pointwise reconstructed Poynting flux
volume absorption
```

若 variational work闭合而 pointwise flux不闭合，则是 reconstruction/postprocess；若 variational work也不闭合，则是 coupling operator。

### R7：现有 `C^H A C` probe 仍需独立 authority

当前 action check使用：

```text
reduce_matrix_hermitian(A,C)
vs
C^H(A(Cq))
```

二者共享同一个 C 和 PETSc product，且 A 为对角矩阵。建议增加小网格独立 NumPy/dense reference：

- complex off-diagonal A；
- slave/master/corner 交叉耦合；
- 独立构造 dense C；
- 比较 full matrix 与 action；
- MPI1/2；
- 可再对实际小型 K0/K1/K2 做同样比较。

这属于测试加固，不否定当前 48/48 probe 结果。

---

## 5. Required M2C-A：Full3D production hierarchy 资格化

### M2C-A0：保留证据与 source 纪律

1. Case112--114 raw/compact evidence 不改写；
2. 本 Review V3 后先完成代码修改和测试，再提交一个 clean implementation SHA；
3. 所有新 PDE 绑定该完整 SHA；
4. 一次一个 solve，MPI2，每 rank 1 thread，zero swap，watchdog；
5. 不 merge/rebase master；
6. 不启动 surrogate fit、angle DOE 或 inversion。

### M2C-A1：建立独立的 parameterized Full3D runner

建议新增：

```text
Task002Full3DParameters
Task002Full3DFidelity
build_task002_full3d_config(...)
run_formal_task002_full3d(...)
```

正式输入：

```text
height_nm  = [115,125]
width_nm   = [16,18]
grazing    = [0.5,10]
azimuth    = [0,90]
wavelength = 13.5 fixed
polarization = S fixed
```

正式 model IDs：

```text
S_LF_FULL3D_STATIC_P4_H10
S_HF_FULL3D_STATIC_P5_H10
```

runner 必须输出：

- actual element identity；
- resolved mesh axes和topology hash；
- fixed-order mother response；
- R/T/A、A_volume、true residual；
- source/config/artifact hashes；
- wall/RSS/PSS/USS/swap；
- `solver_route_id`。

### M2C-A2：固定拓扑测试

在不运行 PDE 的情况下，至少对：

```text
h = 115, 120, 125
w = 16, 17, 18
```

的 9 个组合构造 mesh/config，并要求：

```text
cell count identical
connectivity hash identical
DoF-layout identity identical
material-tag topology identical
Floquet entity topology identical
only coordinates/material-boundary positions change
```

随后对中心和四个几何轴向点各做一项 LF/HF smoke，确认真实 run identity 与静态 topology audit 一致。

### M2C-A3：完成 Full3D p5/h10 80-angle map

复用 Case114 已有 p5 points，只补缺失点：

```text
grazing = [0.5,0.75,1,2,4,6,8,10]
azimuth = [0,5,10,15,20,30,45,60,75,90]
```

每点要求：

```text
completed direct solve
true residual <= 1e-9
|R+T+A_volume-1| <= 1e-8 preferred, <=1e-7 hard
zero swap
cleanup complete
fixed-order schema complete
```

若 Full3D p5 在任意普通点失败，应停止 bulk、保留证据并分析；不得跳过失败点。

### M2C-A4：判断 p4/h10 是否有多保真价值

使用同一 80-angle p4/p5 paired dataset，报告：

1. 每个 R/T/A 与 fixed-order channel 的：
   - Pearson correlation；
   - Spearman correlation；
   - normalized RMSE；
   - maximum discrepancy；
2. 角度邻接梯度的一致性：
   - `d/dgrazing` sign agreement；
   - `d/dazimuth` sign agreement；
3. p4→p5 discrepancy 的空间平滑性和局部长度尺度；
4. 用冻结的 p5 validation angles 做一个小型 discrepancy pilot：
   - 训练 12/16/24 个 p5点；
   - 验证剩余点；
   - 比较 MF 与直接 p5-only 插值。

建议 Gate：

```text
主要通道 Spearman >= 0.90
角度梯度符号一致率 >= 0.85
MF validation 必须显著优于 LF raw 和不差于相同HF预算的p5-only基准
```

若 Gate 不满足，冻结：

```text
production_surrogate = Full3D p5 single fidelity
```

### M2C-A5：几何灵敏度 pilot

在以下五点：

```text
(120,17)
(117.5,17), (122.5,17)
(120,16.5), (120,17.5)
```

以及代表角度：

```text
0.5°/0°
0.5°/45°
2°/15°
10°/45°
```

运行 paired p4/h10 与 p5/h10。计算：

```text
dy/dh, dy/dw
LF/HF sensitivity cosine
channel sign agreement
noise-weighted Jacobian rank/condition
```

这一步不是正式训练集，而是验证 LF/HF 关系在几何方向上也成立。若角度响应相关但 h/w sensitivity 不一致，不能使用多保真反演代理。

### M2C-A6：离散误差与 HF 语义

保留 Case114 的 p4/h7.5 anchors作为 independent h-refinement。必要时只在误差峰值或几何 pilot 中补 4--8 个 p4/h7.5 点，不运行完整 80-angle p4/h7.5 map。

建立：

```text
sigma_discretization(angle,geometry,channel)
```

第一版可使用保守 envelope / GP discrepancy，但必须把该项加入：

```text
Sigma_total = Sigma_measurement + Sigma_surrogate + Sigma_discretization
```

任何报告不得把 p5/h10写成 continuum truth。

---

## 6. Required M2C-B：Hybrid hardening 或 hard quarantine

Task002 V1 已选择 Full3D route，因此 Hybrid 修复不应继续阻塞 production surrogate。但已知缺陷不能留在可选择的正式模型注册表中。

在恢复 M3 前，至少满足以下二选一：

### 方案 B1：完成 targeted near-degenerate repair

1. 在 left/right individual assignment 之前进行 cluster-level matching；
2. cluster graph同时使用：
   - beta proximity；
   - normalized Q' cross-overlap；
   - `block_rotation_tolerance`；
3. 若两个 blocks 的 cross-overlap 超过阈值，递归合并直到 block 外 overlap 受控；
4. block normalization 使用 SVD / rank-revealing QR，不直接对 `cond≈1e12` block 求逆；
5. candidate pool若在第 M 个模式处截断一个近简并簇：
   - 自动扩充完整簇，或
   - fail closed为 `incomplete_near_degenerate_cluster`；
6. 修正 analytic negative full/reduced consistency并重新计算 residual；
7. 对以下点回归：
   - p6 0.5°/45°；
   - p6 1°/45°；
   - p6 10°/45°；
   - p6 0.5°方位 0--90°；
8. 原 biorthogonality Gate不放宽。

即使修复通过，也不得自动把 Hybrid 加回 Task002 dataset；需要独立 review。

### 方案 B2：正式 hard quarantine

若本轮不修 Hybrid：

- 从 Task002 formal model enum 中移除/拒绝所有 Hybrid IDs；
- CLI 和 campaign 对 Task002 Hybrid请求 fail closed；
- 保留 research diagnostic gate；
- 文档明确 `hybrid_route_status=deferred_known_near_degenerate_bug`；
- 增加测试证明 production path无法静默选择 Hybrid。

只有文档写“暂停”而代码仍允许 formal selection，不满足 hard quarantine。

---

## 7. 测试加固

### 7.1 Full3D route tests

至少新增：

- parameter schema/domain fail-closed；
- p4/p5 model identity；
- fixed topology 9-point test；
- source/config hash determinism；
- order schema deterministic identity；
- MPI1/2 small-case R/T/A consistency；
- failed run不得进入dataset；
- mixed solver route不得静默拼接。

### 7.2 Floquet independent dense reference

保留现有48个 probes，并新增一个 tiny mesh test：

```text
complex off-diagonal A
independent dense C
NumPy C^H A C
PETSc reduce_matrix_hermitian
MPI1/2
```

### 7.3 Hybrid energy operator diagnostic

若执行 B1，增加：

- local interface variational work；
- modal interface variational work；
- pointwise Poynting flux；
- volume loss；
- operator-level power residual。

必须明确是 coupling error 还是 postprocess error。

---

## 8. M2C 通过条件

只有以下全部满足，才允许 Review V4 考虑恢复 M3：

1. Full3D parameterized runner完成并绑定 clean SHA；
2. p4/h10、p5/h10 actual element/mesh identity明确；
3. 9-point geometry topology invariant Gate通过；
4. Full3D p5 80-angle map 80/80通过；
5. p4→p5 multi-fidelity价值有定量结论，或明确改用 p5-only；
6. h/w 五点灵敏度 pilot通过；
7. p5高保真语义和 discretization uncertainty已冻结；
8. p4/h7.5没有被误用为 LF；
9. Hybrid完成B1修复或B2 hard quarantine；
10. 历史 Hybrid p6元素身份已更正；
11. 现有Case112--114负证据保留；
12. 未开始正式4D bulk、surrogate fit、angle DOE或inversion。

---

## 9. 建议交付物

建议建立：

```text
benchmarks/cases/115_task002_full3d_hierarchy_qualification/
  config.json
  expected.json
  records/full3d_p5_angle_map.json
  records/full3d_fidelity_screen.json
  records/mesh_topology_identity.json
  records/geometry_sensitivity_pilot.json
  records/discretization_uncertainty.json
  records/hybrid_hardening_or_quarantine.json
  records/solver_routing_map_v2.json

surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
  outcomes/m2c_full3d_hierarchy_qualification.md
  outcomes/solver_routing_map_v2.md
  outcomes/hybrid_hardening_or_quarantine.md
  response_v4.md
```

完成后提交并只推送当前代理分支，停止等待 ChatGPT Review V4。不得自行恢复 M3--M10。

---

## 10. 最终方向

本 Review V3 的目标不是继续围绕 Hybrid逐点修补，而是形成两条清晰边界：

```text
Task002 production:
  使用经过全角域和几何拓扑资格化的 Full3D static route

Hybrid research:
  修复 near-degenerate / power-identity 问题，或在 production 中 hard quarantine
```

这样既能继续推进代理模型，也不会让已知数值缺陷以“低保真便宜”的名义进入训练数据。