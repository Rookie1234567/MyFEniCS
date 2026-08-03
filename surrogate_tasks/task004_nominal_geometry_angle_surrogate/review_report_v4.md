# Task004 Review Report V4：M4E 受控停止审阅、异常点主导诊断与唯一一轮主动学习条件授权

## 1. 审阅结论

本轮批准保留 Task004 Required M4E 的实现、不可变 `train96` 数据包、局部/拓扑感知模型比较、分层资格结果、不确定度证据和负结果。

本轮并不是程序崩溃，也不是前向有限元再次失败。Codex 停止的直接原因是：Review V3 只授权生成主动学习资格记录，不授权实际运行 16 个新 FEM。当前 `response_v4.md` 正确地停在：

```text
eligible_for_one_round_16_fem = true
fem_started                    = false
plan_status                    = eligibility_only_no_fem
```

当前正式状态冻结为：

```text
forward_solver_sha                         = fdf961545f217d620e22800f2704ae9913a6d270
training_dataset_id                        = task004_angle_nominal_p5_ny4_train96_v2
training_rows                              = 96
blind_validation_rows_measured             = 0 / 24
training_dataset_identity                  = approved_and_immutable
aggregate_angle_surrogate                  = not_qualified_but_viable
order_resolved_power_surrogate             = not_qualified
best_minimax_candidate                     = L1_local_rbf_k24_s1e-08
best_outlier_diagnostic_candidate          = L2_local_matern_k24
ANGLE_AGGREGATE_MODEL_SELECTION_LOCK       = absent
ANGLE_ORDER_MODEL_SELECTION_LOCK           = absent
Task004 active-learning FEM                 = conditionally authorized after M4E2 plan Gates
Task004 second active-learning round        = forbidden
Task004 blind validation                    = sealed until aggregate model lock
formal Fisher / geometry sensitivity        = forbidden
inversion                                   = forbidden
Task003 Round3 / frozen validation           = forbidden / sealed
```

本报告授权下一阶段分两步连续执行：

```text
M4E2 = 不运行 FEM 的 acquisition/diagnostic hardening
M4F  = M4E2 Gates 通过后，唯一一轮恰好 16 个 Ny4/p5 FEM
```

M4E2 通过后，Codex 可以在同一执行轮直接运行 M4F，无需再次等待 ChatGPT；若 M4E2 不通过，则不得运行任何新 FEM。

---

## 2. 这次失败应怎样理解

### 2.1 不是“二维角度代理做不出来”

当前局部模型已证明二维角度响应存在明显的可学习结构。M4E 的有限模型比较为：

| candidate | score | aggregate Gate | supported-window Gate | uncertainty Gate |
|---|---:|---|---|---|
| local RBF, k=24 | 4.4499 | fail | fail | pass |
| local RBF, k=32 | 4.4861 | fail | fail | pass |
| local RBF, k=48 | 4.4837 | fail | fail | pass |
| local Matérn, k=24 | 4.8127 | fail | **pass** | pass |
| local Matérn, k=32 | 4.8041 | fail | **pass** | pass |
| local Matérn, k=48 | 5.4264 | fail | fail | pass |
| hard topology expert, k=32 | 25.4794 | fail | fail | pass |
| degree-2 trend + local residual | 4.5014 | fail | fail | pass |

因此合理结论是：

1. 单一全局 stationary GP 不是合适的统一结构；
2. 局部模型显著改善了部分区域；
3. 当前总体 Gate 由少量大误差点和高方位角局部区域主导；
4. 一轮有目标的加点具有研究依据，但不能仅凭“覆盖率通过”盲目选点。

### 2.2 local RBF 的平均与尾部误差仍未通过

CV 选中的 `L1_local_rbf_k24_s1e-08` 为：

| target | NRMSE | p95 abs | max abs |
|---|---:|---:|---:|
| R | 0.01877 | 0.02379 | 0.06020 |
| T | 0.02995 | 0.01521 | 0.11859 |
| A | 0.04219 | 0.03665 | 0.13350 |

它的 composition 与经验区间覆盖通过，但 accuracy Gate 未通过。当前不能创建模型锁。

### 2.3 local Matérn 暴露出“少量灾难性异常点”结构

`L2_local_matern_k24` 的结果更值得用于主动学习诊断：

| target | NRMSE | p95 abs | max abs |
|---|---:|---:|---:|
| R | 0.00828 | 0.00264 | 0.03619 |
| T | 0.01996 | 0.00460 | 0.10819 |
| A | 0.03045 | 0.00485 | 0.14438 |

其中 R/T/A 的 p95 都已低于 0.01，R 的 NRMSE 也已通过；失败主要来自少量很大的 T/A 异常点。该模式说明：

> 大约 95% 的角度已经能被局部 Matérn 较好预测，剩余少数角度形成了极大的尾部误差。

这比“整个角度域都学不好”更适合使用定向主动学习解决。下一轮 acquisition 不应只使用 minimax 排名选中的 RBF，而应重点使用 local Matérn 的 query-dependent uncertainty、模型间 disagreement 和 OOF 大误差位置。

### 2.4 hard topology expert 的失败不能解释为拓扑感知路线无效

当前 L3 按完整 mask signature 硬分组。部分 signature 在 96 点中样本很少，随后又在每组内部拟合局部 RBF，容易造成数据碎片化。因此其高 score 更像是“硬切分过细”的负结果，而不是拓扑感知建模本身无效。

后续不得继续使用“每个完整 signature 一个完全独立专家”的唯一形式。若需要 topology-aware acquisition，应采用：

```text
解析 signature / cutoff side 作为标签与约束
+ 相邻 topology 共享数据或软 gating
+ unseen signature fail closed
```

---

## 3. 当前 M4E 中需要纠正的审阅问题

### 3.1 supported-window 的 nearest distance 记录存在实现错误

`freeze_supported_interpolation_windows_v2(...)` 中：

```python
order, distances = _nearest(q, t)
support = support_pool[order[:, :6]]
nearest_support_distance = distances[np.arange(len(indices)), 0]
```

`distances[:,0]` 是到 `support_pool` 第一行的距离，不是到 `order[:,0]` 指向的最近 support 的距离。正确值应按排序索引提取，例如：

```python
nearest = distances[np.arange(len(indices)), order[:, 0]]
```

因此当前 JSON 中若干大于 1 的 `nearest_support_distance` 不是可靠的最近距离。support indices 本身仍来自排序结果，但距离证据和 checker 需要修正。

### 3.2 “六个最近点”不等于真正的插值支撑

当前 checker 只验证：

- 每个 holdout 有六个不同的 support rows；
- support rows 不等于 holdout rows。

它没有证明 query 位于 support 的凸包内，也没有证明边界 query 具有合理的一侧/沿边界支撑。M4E2 必须增加几何支撑分类：

```text
interior_bracketed
boundary_one_sided_supported
unsupported_extrapolation
```

只有前两类可进入 supported interpolation hard Gate。

### 3.3 当前 local 模型实际上全部只使用 F1

代码冻结：

```python
F3_LOCAL_FEATURE = "F1"
```

因此 local RBF、local Matérn、trend residual 和 topology expert 的距离与回归全部只使用缩放后的 `(grazing, azimuth)`；并没有真正比较 signed cutoff 特征。

这不影响本轮结果的真实性，但意味着不能声称“local signed-cutoff feature 已失败”。M4E2 只允许增加一个有限的物理特征候选：

```text
F4 = scaled(grazing, azimuth)
     + signed nearest-cutoff margin
     + nearest-cutoff order categorical identity
```

不得重新开启 F1/F2/F3/大量特征的无边界搜索。

### 3.4 当前 RBF uncertainty 能通过 coverage，但不适合直接做 acquisition

local RBF 的 raw uncertainty 主要来自 outer-training 内层 OOF 的 target-wise 95% 残差半径。该半径在一个 outer fold 内对所有 query 基本相同，因此：

- 可以构造保守的经验区间；
- 不能自动区分该 fold 内哪个候选角度更值得加点。

所以：

```text
cross_fitted_uncertainty_available = true
```

不等于：

```text
uncertainty_is_useful_for_active_learning = true
```

当前 `ACTIVE_LEARNING_ELIGIBILITY.json` 的逻辑过于宽松。M4E2 必须新增 acquisition-quality 审计。

### 3.5 eligibility 尚未验证不确定度与误差的排序能力

当前 eligibility 只检查：

- local candidate 比 global score 好；
- uncertainty coverage 通过；
- 某个 supported window 的 A p95 较大。

它没有检查：

- predictive std 与 OOF absolute error 的 Spearman 相关；
- 最高不确定度点能否召回最高误差点；
- ensemble disagreement 是否定位灾难性异常点。

因此本报告保留 `eligible=true` 为“研究资格”，但在真正运行 FEM 前增加 M4E2 Gates。

### 3.6 production-model ranking 与 acquisition-model 不能强制相同

当前 minimax score 选择 local RBF k24；但 local Matérn k24/k32：

- supported-window Gate 已通过；
- p95 指标明显更好；
- 具有 query-dependent GP uncertainty；
- 只被少数大误差点拖垮。

因此下一轮允许：

```text
production candidate ranking = 继续按冻结 accuracy Gate
acquisition model             = local Matérn ensemble + RBF/Matérn disagreement
```

不能因为 RBF score 最低就强迫用近似常数的 RBF interval 选点。

---

## 4. Required M4E2：运行新 FEM 前的短诊断

M4E2 只读取不可变 train96 与 response-blind candidate4096，不访问 blind validation response，不运行 FEM。

### 4.1 修正 supported-window v3

建立：

```text
SUPPORTED_INTERPOLATION_WINDOWS_V3.json
```

要求：

1. 保留 V2 原文件不改写；
2. 修正真正的 nearest-support distance；
3. 保存 support feature coordinates；
4. 使用 Delaunay/convex-hull、局部方向覆盖或等价几何方法分类支撑；
5. 边界点可采用 one-sided supported，但必须有沿边界和法向内侧支撑；
6. 不满足支撑条件的窗口转为 advisory，不得作为 hard interpolation Gate；
7. checker 从坐标重新计算，不得只相信 JSON 布尔值。

### 4.2 生成完整 OOF error map

对以下固定候选保存逐点：

```text
L1 local RBF k24
L2 local Matérn k24
L2 local Matérn k32
L4 trend + local residual k32
```

每点至少保存：

```text
angle tuple
truth R/T/A
prediction R/T/A
absolute error
predictive std / conformal radius
standardized residual
fold
nearest fold-training distance
nearest-cutoff order and signed margin
mask signature
region labels
local neighbor indices
```

输出：

```text
M4E2_OOF_ERROR_MAP.json
M4E2_WORST_POINTS.md
```

### 4.3 Acquisition-quality Gate

分别审计：

```text
local Matérn k24 native std
local Matérn k32 native std
k24/k32 prediction disagreement
RBF/Matérn disagreement
nearest-data distance
cutoff proximity
```

对每个 target 以及 `max(|e_R|,|e_T|,|e_A|)` 报告：

```text
Spearman(acquisition, absolute OOF error)
top-20%-acquisition 对 top-20%-error 的 recall
最高10个误差点中被最高20个 acquisition 点覆盖的数量
```

执行 M4F 的最低 Gate 为满足以下任一条，并且另一条不得明显反相关：

```text
Spearman >= 0.30
或
top-20% error recall >= 0.50
```

若 GP std 单独不通过，可使用预冻结的 ensemble acquisition：

```text
normalized local-Matérn std
+ normalized k24/k32 disagreement
+ normalized RBF/Matérn disagreement
+ normalized nearest distance
+ cutoff/topology bonus
```

权重必须在查看 candidate response 前冻结并保存。

### 4.4 有限的特征复核

仅对 local Matérn k24/k32 比较：

```text
F1 = scaled(grazing, azimuth)
F4 = F1 + signed nearest-cutoff margin + cutoff-order identity
```

使用相同 folds 和 Gate。若 F4 没有改善，不继续增加特征。

### 4.5 生成正式主动学习计划

若 4.3 Gate 通过，建立：

```text
ACTIVE_LEARNING_ROUND1_PLAN_V2.json
```

恰好 16 个 response-blind candidate，要求：

- 与 train96、blind24 均无 tuple 交集；
- point tuple hash 固定；
- 每点保存 acquisition 分量与选择原因；
- 至少 6 点覆盖 local-Matérn 最大误差/高 disagreement 邻域；
- 至少 3 点位于 high-azimuth 困难区；
- 至少 3 点位于 low-grazing 或 cutoff 两侧；
- 至少 3 点位于 ordinary-interior 空洞；
- 至少 2 点覆盖 candidate 中的 rare unseen topology，优先选择与 aggregate 高误差或主要 order 相关的 signature；
- 任意两个新点的归一化距离不得过小；
- 不要求用 7/16 点机械覆盖全部 7 个极稀有 topology，因为本轮第一目标是 Aggregate Level A；未覆盖 topology 继续对 Level B fail closed。

独立 checker 必须重算所有约束。

若 M4E2 acquisition Gate 或 plan checker 不通过：

```text
M4F forbidden
controlled stop
```

---

## 5. M4F：唯一一轮 16 点主动学习

M4E2 全部通过后，批准同一轮执行恰好 16 个 FEM。

### 5.1 固定前向身份

所有新点必须使用只读 forward worktree：

```text
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
model              = Full3D static uniform N1curl p5/h10/Ny4
mesh               = (6,4,14)
MUMPS ICNTL(14)    = 40
MPI                = 2
threads/rank       = 1
output             = compact_surrogate_record
```

不得用当前代理代码 HEAD 作为 forward baseline，不得改网格、阶次、MUMPS profile 或物理参数。

### 5.2 运行纪律

- 一次只运行一个 FEM；
- 第一个未解释 numerical/resource failure 立即停止；
- 不跳过失败点凑足 16；
- 每个点保存 residual、energy、mask、power ledger、runtime topology、RSS/PSS/USS、swap 与 hashes；
- 不运行 blind validation。

### 5.3 新数据集

16/16 通过后建立新的不可变：

```text
task004_angle_nominal_p5_ny4_train112_v1
```

它由：

```text
原 train96（不可变）
+ Round1 16 点
```

组成。不得原地覆盖 `train96_v2`。

---

## 6. 112 点重新资格化

### 6.1 Paired learning curve

必须保留原 96 点的测试 rows，比较：

```text
train96 model：每折只用原 fold-training rows
train112 model：同一测试 rows，训练时加入全部16个新点
```

对 local RBF k24、local Matérn k24/k32 和最终候选分别报告。这样才能判断 16 点是否真正改善同一预测任务。

同时再运行标准 112 点 training-only CV。

### 6.2 Aggregate Level A

若满足：

```text
OOF NRMSE <= 0.01
OOF p95 abs <= 0.01
OOF max abs <= 0.03
supported interpolation v3 p95 <= 0.02
composition exact
cross-fitted coverage in [0.90,0.99]
```

则创建：

```text
ANGLE_AGGREGATE_MODEL_SELECTION_LOCK.json
```

### 6.3 Order Level B

单独重新评价：

```text
mask agreement = 100%
sidewise ledger <= 1e-12
primary channel NRMSE <= 0.03
primary channel p95 abs <= 0.01
```

若失败，允许：

```text
aggregate_qualified = true
order_resolved_qualified = false
```

不得让 Level B 自动阻塞 Level A。

### 6.4 112 点仍未通过

若 Aggregate Level A 仍未通过：

- 保存负结果与 paired learning curve；
- 不执行第二轮主动学习；
- 不运行 blind validation；
- 停止等待 Review V5。

---

## 7. Blind validation 边界

只有 Aggregate Level A 创建模型锁后，才允许使用固定 forward SHA 运行 24 个 blind-validation FEM。

validation 必须形成独立不可变包，不得修改 train96/train112 文件。只允许一次性评分；不得根据 blind 结果调参并重新宣称 blind validation。

Order Level B 未锁定时，blind validation 只对 Aggregate Level A 给出正式资格结论；order 输出继续标记 `not_qualified`。

---

## 8. 本轮交付要求

建立 Case127，例如：

```text
benchmarks/cases/127_task004_active_learning_round1/
```

至少交付：

```text
SUPPORTED_INTERPOLATION_WINDOWS_V3.json
M4E2_OOF_ERROR_MAP.json
M4E2_ACQUISITION_QUALITY.json
ACTIVE_LEARNING_ROUND1_PLAN_V2.json
active-learning checker
16-point FEM compact records（若获准执行）
train112 dataset manifest/checker（若16/16通过）
paired learning curve 96->112
aggregate/order qualification v3
outcomes/test_summary_v5.md
response_v5.md
```

测试至少包括：

- supported-distance 与几何支撑重算；
- acquisition score 不读取 response/blind target；
- tuple 去重与 split 隔离；
- fixed forward SHA enforcement；
- train96 immutability；
- train112 exact coverage；
- aggregate/order lock 分离；
- blind-validation fail-closed；
- compileall 与相关 surrogate regression。

---

## 9. Codex 下一步

Codex 应完整阅读本报告，从 M4E2 开始。M4E2 plan Gates 通过后可在同一轮执行唯一一轮 M4F 16 点；完成 112 点重新资格化后停止等待 Review V5。

不得执行：

```text
第二轮 active learning
24 点 blind validation（除非 aggregate lock 已创建）
Task003 Round3 / validation
Fisher angle ranking
geometry sensitivity
inversion
P incident / wavelength extension
```
