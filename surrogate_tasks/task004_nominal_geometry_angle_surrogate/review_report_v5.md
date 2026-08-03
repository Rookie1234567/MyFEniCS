# Task004 Review Report V5：唯一主动学习轮次审阅、train112 局部候选资格缺口与无新增 FEM 的最终模型闭合路线

## 1. 审阅结论

本轮批准保留并正式接受：

```text
M4E2 acquisition-quality audit             = approved
ACTIVE_LEARNING_ROUND1_PLAN_V2             = approved and immutable
M4F unique 16-point FEM round              = 16/16 measured_pass
train112 immutable dataset                 = approved
paired train96 -> train112 learning curve  = approved as diagnostic evidence
standard train112 global-GP CV             = valid negative evidence for that pipeline
```

但本轮**不批准**：

```text
ANGLE_AGGREGATE_MODEL_SELECTION_LOCK       = absent / not authorized
ANGLE_ORDER_MODEL_SELECTION_LOCK           = absent / not authorized
Task004 blind-validation FEM               = 0/24, remain sealed
Task004 second active-learning round       = forbidden
formal Fisher angle ranking                = forbidden
geometry sensitivity / inversion           = forbidden
Task003 Round3 / frozen validation          = forbidden / sealed
```

当前正式状态冻结为：

```text
forward_solver_sha                         = fdf961545f217d620e22800f2704ae9913a6d270
training_dataset_id                        = task004_angle_nominal_p5_ny4_train112_v1
training_rows                              = 112
fixed geometry                             = h=120 nm, w=17 nm
angle domain                               = grazing 0.5-10 deg, azimuth 0-90 deg
forward model                              = Full3D static uniform N1curl p5/h10/Ny4
MUMPS                                      = ICNTL(14)=40, MPI2, thread1
blind_validation_rows_measured             = 0 / 24
aggregate_status                           = not_qualified, final local review incomplete
order_resolved_status                      = not_qualified
required_next_stage                        = M4G post-active local qualification on train112 only
new FEM budget                             = 0
```

本轮停止不是程序卡死，也不是 16 个主动学习点失败。直接停止原因是标准 112 点 training-only CV 仍未达到冻结 Gate，因此程序正确地没有建立模型锁、没有运行 blind validation，也没有擅自启动第二轮主动学习。

但是，当前负结论仍有一个重要资格缺口：

> M4F 后的“标准 112 点 CV”重新评价的是原 `pipeline.py` 中的全局 GP 候选，而 M4E/M4E2 建立的 local RBF、local Matérn 和局部残差候选，只在固定原 96 个测试行的 paired learning curve 中被比较；新增的 16 个点并没有在这些局部候选下轮流成为标准 OOF 测试点。

因此，目前可以确认：

```text
全局 gp:F3 在 train112 上仍未通过
```

但尚不能正式确认：

```text
train112 上所有已批准的局部候选都未通过完整标准资格
```

下一阶段 M4G 必须补齐这一缺口。M4G 不运行任何新 FEM，只使用不可变 train112。

---

## 2. 本轮可正式接受的成果

### 2.1 主动学习 acquisition 是有效的

M4E2 在 train96 的 OOF 误差上审计了 local Matérn uncertainty、k24/k32 disagreement、RBF/Matérn disagreement、最近训练距离和 cutoff/topology 信息。

冻结 acquisition ensemble 对 OOF 误差具有明确排序能力；例如对最大三目标误差的 Spearman 约为 `0.8069`，top-20% acquisition 对 top-20% error 的 recall 约为 `0.60`。因此本轮 16 点并非随机补点，也不是只按未经验证的 GP variance 盲选。

16 点计划满足：

```text
exact count = 16
train96 / blind24 tuple disjoint
minimum normalized pairwise distance >= 0.035
high-azimuth / hotspot / low-or-cutoff / interior coverage Gates
rare topology anchors
fixed forward SHA and solver identity
```

该计划与 acquisition-quality 证据可保留为以后主动学习设计的正式参考。

### 2.2 16 个新 FEM 全部成功

唯一一轮 M4F 使用完全固定的：

```text
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
Full3D static uniform N1curl p5/h10/Ny4
mesh = (6,4,14)
MUMPS ICNTL(14)=40
MPI2 / one thread per rank
compact_surrogate_record
```

结果：

```text
16 / 16 measured_pass
zero unexplained numerical failure
zero resource stop
zero swap
residual / energy / topology / mask / power-ledger Gates pass
validation_target_accessed = false
```

因此不得把本轮停止归因于有限元前向模型。

### 2.3 train112 数据包通过

不可变数据集：

```text
dataset_id = task004_angle_nominal_p5_ny4_train112_v1
rows       = original immutable train96 + 16 round-1 points
```

原 train96 保持精确前缀；新增样本没有覆盖旧数据。train112 的 tuple hash、数组身份、source SHA、模型/路线、求解器 workspace 和 validation 隔离均通过 checker。

该数据集应成为后续所有 Task004 模型研究的唯一训练数据权威，不得继续追加 FEM 或原地改写。

### 2.4 主动加点确实改善了局部模型

固定原 96 个测试 rows 的 paired comparison 显示：

| candidate | max abs, train96 | max abs, train112 | reduction |
|---|---:|---:|---:|
| local RBF k24 | 0.1334965 | 0.1136339 | 0.0198626 |
| local Matérn k24 | 0.1443802 | 0.0932643 | 0.0511159 |
| local Matérn k32 | 0.1441228 | 0.1438660 | 0.0002569 |

所以本轮 16 点不是无效数据：

- local RBF k24 的尾部误差有所下降；
- local Matérn k24 的最大误差下降约 `0.0511`；
- k32 几乎没有改善，说明邻域大小与局部响应尺度的选择仍然重要。

该结果支持继续研究 k24 局部路线，但不支持挑选性地宣称所有局部模型都已改善。

---

## 3. 当前标准 112 点结果如何理解

### 3.1 全局 GP 仍未通过

标准 112 点 training-only CV 选择：

```text
gp:F3
jitter = 1e-8
```

结果：

| target | NRMSE | p95 abs | max abs | Gate |
|---|---:|---:|---:|---|
| R_total | 0.0246633 | 0.0370765 | 0.1080872 | fail |
| T_total | 0.0120798 | 0.0140645 | 0.0360235 | fail |
| A_balance | 0.0332836 | 0.0329176 | 0.1101640 | fail |

冻结 Gate 仍是：

```text
NRMSE <= 0.01
p95 absolute <= 0.01
max absolute <= 0.03
supported interpolation p95 <= 0.02
composition exact
cross-fitted coverage in [0.90,0.99]
```

composition 和 uncertainty coverage 通过，但 accuracy 明显未通过，尤其是 R/A 尾部误差。因此不能建立 aggregate model lock。

### 3.2 失败仍由少量局部大误差主导

标准 GP 的一个代表性最差点是原 train96 enrichment sample 80：

```text
grazing = 1.536085498 deg
azimuth = 67.847807324 deg
region  = low_grazing + cutoff_near
nearest actual fold-training distance ≈ 0.324974
```

该点的 OOF 误差约为：

```text
R error = -0.1080872
T error = -0.0020768
A error = +0.1101640
```

这说明当前最大误差不是全域均匀存在，而是集中于局部训练支撑较弱、低掠射/cutoff 邻域。新增 16 点没有完全填补该 fold 下的局部空洞。

该现象支持：

```text
进一步改进模型的局部路由、稳健集成和 coverage-aware warning
```

而不支持：

```text
继续机械增加第二轮 FEM
```

### 3.3 Order Level B 仍明显失败

train112 的 order-resolved 结果：

```text
mask agreement                         = 100%           pass
maximum sidewise ledger error          = 2.22e-16       pass
maximum primary-channel NRMSE          = 0.15142        fail
maximum primary-channel p95 abs        = 0.0490633      fail
```

功率账本严格闭合不等于各衍射级准确。Order Level B 继续独立标记为 `not_qualified`，且不得阻塞未来可能单独通过的 Aggregate Level A。

---

## 4. 当前资格流程中的关键缺口

### 4.1 标准 112 点 CV 没有完整纳入 M4E 局部候选

当前 `pipeline.py` 的正式 production candidate 集合仍是：

```text
gp:F1 / gp:F2 / gp:F3
x jitter 1e-10 / 1e-8 / 1e-6
```

local RBF 与 Chebyshev 仅作为 baseline。

而 M4E 建立的：

```text
L1 local RBF k24/k32/k48
L2 local Matérn k24/k32/k48
L3 topology expert
L4 trend + local residual
```

没有作为统一的标准 train112 5-fold candidate suite 重新资格化。

`round1.py` 的 paired learning curve 只固定原 96 个测试 rows，并把 16 个新增点全部放在训练侧。该试验适合回答：

```text
新增16点是否改善原来的预测任务
```

但不能回答：

```text
局部模型能否预测新增16点本身
局部模型在完整112点标准OOF下是否通过
```

因此，当前 `aggregate_qualified=false` 对全局 GP 是成立的，对所有局部候选则仍未完成最终证明。

### 4.2 paired report 中的 “selected_final_candidate” 语义应更正

`round1.py` 在 paired learning-curve metadata 中写入固定的：

```text
selected_final_candidate = L1_local_rbf_k24_s1e-08
```

但该文件只是 diagnostic paired comparison，并没有完成完整 112 点模型选择，也没有形成模型锁。

下一版应更名为：

```text
paired_reference_candidate
```

或明确写：

```text
diagnostic_only_not_model_lock
```

避免后续自动流程把 paired 参考候选误当成最终生产模型。

### 4.3 需要统一异常点、邻域和模型分歧证据

当前已有：

- 全局 GP 的完整 112 点 OOF；
- local 模型在原 96 点固定测试行上的 paired 预测；
- M4E2 的 train96 acquisition map。

但还缺少同一份 train112 标准 OOF authority，将以下信息放在每个点的一条记录中：

```text
local RBF k24 prediction/error
local Matérn k24 prediction/error/std
local Matérn k32 prediction/error/std
robust ensemble prediction/error/std
nearest fold-training distance
model disagreement
cutoff order and signed margin
mask signature
old96 / new16 identity
acquisition score and selection reason
```

没有这份统一证据，就无法判断剩余异常点究竟来自：

- 真实局部高曲率；
- 某一 fold 的空间空洞；
- 局部 GP 超参数异常；
- k24/k32 邻域不一致；
- 或单一模型的灾难性预测。

---

## 5. Required M4G：只用 train112 完成最终局部资格化

M4G 不运行 FEM，不访问 blind response，不修改 train112。

### 5.1 冻结标准 112 点局部 folds

建立：

```text
TRAIN112_LOCAL_REFERENCE_FOLDS.json
```

要求：

- 使用固定 seed；
- 112 个点每点恰好一次 outer-test；
- folds 在任何局部模型重评前冻结；
- 保存角度 tuple、old96/new16 split、fold hash；
- 每个 fold 报告 mask-signature support 和最近训练距离分布；
- 不读取 validation response。

### 5.2 运行完整标准 112 点局部候选集

只允许以下有限候选：

```text
L1 local RBF k24
L2 local Matérn k24
L2 local Matérn k32
L4 degree-2 trend + local residual k24
```

k48 和 hard topology expert 已有足够负证据，本轮不再扩展。

所有候选必须在完整 112 点 outer OOF 上评价：

```text
R/T/A NRMSE, p95, max
supported-window-v3 metrics
region metrics
composition
cross-fitted uncertainty
per-query neighbour/kernel/LML/warnings
old96 versus new16 subgroup metrics
```

### 5.3 有限的稳健集成候选

如果单个 local Matérn 仍由少量大误差拖垮，只允许再比较两个预先冻结的稳健候选：

#### E1：latent median ensemble

在 `zR/zT` latent 中，对：

```text
local RBF k24
local Matérn k24
local Matérn k32
```

取逐点中位数，再经 softmax 恢复 R/T/A。

#### E2：cross-fitted non-negative stack

- 仅使用 outer-training 内的 inner-OOF 学习非负、和为 1 的三个模型权重；
- 权重按 latent 分别学习；
- outer-test 和 blind response 不得参与权重选择；
- 不允许按最终 test error 手工切换模型；
- uncertainty 使用 nested/cross-conformal residual，不伪造原生 GP 方差。

不得继续增加 kernel、神经网络、随机森林或无边界 model zoo。

### 5.4 建立 post-active outlier audit

输出：

```text
POST_ACTIVE_OUTLIER_AUDIT.json
POST_ACTIVE_OUTLIER_AUDIT.md
```

每个 target 至少列出最高 10 个 absolute-error 点，并记录：

```text
angle tuple
sample index
old96 or new16
fold
truth
all candidate predictions/std/errors
nearest fold-training distance
nearest training tuples
mask signature
cutoff order / signed margin
region labels
whether selected by round1 acquisition
round1 acquisition components
```

对每个异常点分类：

```text
coverage_hole
cutoff_high_curvature
boundary_one_sided
model_instability
unexplained
```

分类必须由冻结几何/模型证据重建，不能只人工写标签。

### 5.5 coverage-aware 安全域仅作为次级诊断

若完整角度域仍未通过，可以训练内冻结：

```text
nearest-distance threshold
model-disagreement threshold
unsupported-topology rule
```

建立：

```text
ANGLE_AGGREGATE_SAFE_DOMAIN_CANDIDATE.json
```

它只回答：

```text
哪些角度区域可能具有可靠插值支撑
```

不得代替 full-domain model lock，也不得因此运行 blind validation。报告必须给出 candidate4096 的安全域覆盖比例和被排除区域。

---

## 6. M4G 后的决策合同

### 6.1 若某个局部/集成候选完整通过 Aggregate Level A

满足：

```text
OOF NRMSE <= 0.01
OOF p95 abs <= 0.01
OOF max abs <= 0.03
supported-window-v3 p95 <= 0.02
composition exact
cross-fitted coverage in [0.90,0.99]
```

则创建：

```text
ANGLE_AGGREGATE_MODEL_SELECTION_LOCK.json
```

锁定：

```text
train112 file hashes
fold identity
candidate and all fixed hyperparameters
ensemble weights or median rule
uncertainty calibration
forward solver SHA
surrogate training code SHA
validation_target_accessed = false
```

模型锁 checker 通过后，允许在同一执行轮使用固定 forward SHA 运行 24 个 blind-validation FEM，并一次性评分 Aggregate Level A。

Order Level B 继续单独评价；其失败不阻塞已锁定的 aggregate 模型。

### 6.2 若完整域未通过，但 safe-domain candidate 通过

- 不运行 blind validation；
- 不创建 full-domain model lock；
- 保存安全域候选和覆盖比例；
- 停止等待 Review V6，以决定是否把 Task004 范围收缩为受限角域。

### 6.3 若完整域和安全域均未通过

- 正式关闭 Task004 的 full-domain production qualification；
- 保留 train112 和负结果作为研究证据；
- 不允许第二轮主动学习；
- 不运行 blind validation；
- 下一任务应改为固定少数角度后的结构参数代理，而不是继续扩展角度数据。

---

## 7. Order Level B 的下一步

M4G 第一目标是 Aggregate Level A。

只有确定最终 aggregate candidate 后，才使用同一 aggregate OOF R/T 和同一 folds 重算 order-resolved power。继续要求：

```text
mask agreement = 100%
sidewise ledger <= 1e-12
primary NRMSE <= 0.03
primary p95 abs <= 0.01
unseen topology = unsupported
```

若仍失败：

```text
aggregate_qualified = true/false independently
order_resolved_qualified = false
```

不得因为 order 失败而抹去 aggregate 资格，也不得把未通过的 order 输出放进公开 qualified API。

---

## 8. M4G 交付要求

建立新的只读审计 Case，例如：

```text
benchmarks/cases/128_task004_post_active_local_qualification/
```

至少交付：

```text
README.md
config.json
expected.json
checker.py
TRAIN112_LOCAL_REFERENCE_FOLDS.json
TRAIN112_LOCAL_MODEL_COMPARISON.json/.md
POST_ACTIVE_OUTLIER_AUDIT.json/.md
ANGLE_AGGREGATE_QUALIFICATION_CONTRACT_V4.json
ANGLE_ORDER_QUALIFICATION_CONTRACT_V4.json
ANGLE_AGGREGATE_SAFE_DOMAIN_CANDIDATE.json（若需要）
ANGLE_AGGREGATE_MODEL_SELECTION_LOCK.json（仅通过时）
blind24 package/checker（仅模型锁通过后）
test_summary_v6.md
response_v6.md
```

checker 必须从 train112 文件和冻结 folds 重建结果，不得只检查报告中的布尔值。

---

## 9. 直接执行指令

```text
请执行 git pull --ff-only，并完整阅读：

surrogate_tasks/task004_nominal_geometry_angle_surrogate/
review_report_v5.md

严格执行 Required M4G。

本轮不得运行任何新training FEM，不得执行第二轮active learning，
不得访问24个blind responses，除非完整train112局部/集成候选通过
Aggregate Level A并成功创建模型锁。

必须：

1. 冻结TRAIN112_LOCAL_REFERENCE_FOLDS.json；
2. 在完整112点标准OOF上重新评价：
   - local RBF k24
   - local Matérn k24
   - local Matérn k32
   - degree-2 trend + local residual k24；
3. 有限比较latent median ensemble与cross-fitted non-negative stack；
4. 生成POST_ACTIVE_OUTLIER_AUDIT；
5. 更正paired report中selected_final_candidate的误导语义；
6. 分别更新Aggregate Level A和Order Level B资格；
7. 不得改变train96/train112、forward SHA、blind24设计或Task003数据。

只有完整Aggregate Level A通过，才允许在同一轮创建模型锁并运行
24个blind-validation FEM；否则停止等待Review V6。

禁止第二轮active learning、Fisher、geometry sensitivity和inversion。
```

---

## 10. 最终判断

本轮唯一主动学习不是失败：16 个新点全部成功，并显著改善了 local k24 的固定参考误差。

当前真正尚未闭合的是：

> train112 上的最终资格化仍以全局 GP 管线为权威，而被主动学习证明最有希望的局部候选尚未经历完整 112 点标准 OOF 与新增点 held-out 测试。

因此下一步应是一次无新增 FEM 的最终局部模型闭合，而不是继续计算更多有限元数据。
