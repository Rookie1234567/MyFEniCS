# Task004 Review Report V7：M4H 选择性代理审阅、条件区间校准缺口与 blind-validation 前最终闭合

## 1. 审阅结论

本轮批准保留并正式接受：

```text
M4H implementation and evidence integrity                  = approved
immutable train112 / frozen outer folds                    = approved
S1/S2 response-blind risk-signal arithmetic                = approved as diagnostic evidence
six predictor/rule OOF records                             = approved
structural-support / selective-acceptance domain separation = approved
no validation leakage / no new FEM                         = approved
Case129 independent checker                                = pass
```

但本轮**不接受**当前文件所给出的：

```text
ANGLE_AGGREGATE_SELECTIVE_QUALIFICATION = controlled_negative
```

作为 Task004 的最终科学关闭结论。

原因不是放宽误差要求，而是代码审阅发现：当前 `local Matérn k24 + S1` 和
`latent median + S1` 的 accepted-set 点预测已经通过全部冻结精度 Gate；它们
唯一的正式失败项是 accepted subset 上的经验区间覆盖率为 `1.0`，超过旧上限
`0.99`。当前区间是在完整 OOF 分布上构造的，选择器随后只保留低风险、较容易
的子集，却没有在该 accepted distribution 上重新进行条件式 calibration。
因此 `coverage=1.0` 首先说明原区间在 accepted subset 上过于保守，而不是点
预测不可靠。

同时，当前阈值实现还存在三个会影响资格结论的合同缺口：

1. 当 source rows 上没有任何 quantile 同时通过旧 coverage 上限时，程序回退到
   `q=0.70`；但最终 `crossfit_threshold_gate` 只检查 held-out response 未被使用，
   没有检查 `source_gate_selection_failed`，因此 fallback threshold 被错误描述为
   threshold Gate 通过；
2. 每个 risk rule 的 threshold 只根据 `local Matérn k24` 的 source prediction/
   std 拟合，然后原样应用给 RBF、Matérn 和 latent median 三个 predictor；这不是
   真正的 predictor/rule pair qualification；
3. `_source_threshold(...)` 的文档称选择“最高覆盖率”的通过候选，但实现使用
   `min(quantile)`，会在存在多个通过阈值时选取接受率最低的候选。

因此，当前正式状态应更正为：

```text
forward_solver_sha                         = fdf961545f217d620e22800f2704ae9913a6d270
training_dataset_id                        = task004_angle_nominal_p5_ny4_train112_v1
training_rows                              = 112
blind_validation_rows_measured             = 0 / 24
full_domain_aggregate_status               = not qualified
selective point-prediction status          = conditionally near-qualified
selective interval status                  = not conditionally calibrated
order_resolved_status                      = not qualified
ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK = absent
required_next_stage                        = M4I selective-threshold and conditional-conformal correction
new training FEM budget                    = 0
conditional blind FEM budget               = 24, only after M4I lock
```

本报告授权：

```text
M4I = no-FEM correction and final training-only selective qualification
M4J = run the already frozen 24 blind FEM only if M4I creates a valid lock
```

若 M4I 仍失败，则 Task004 以 controlled-negative 关闭；不得继续增加模型、
修改 Gate、执行第二轮主动学习或增加 training FEM。

---

## 2. M4H 中已经取得的实质结果

### 2.1 S1 确实识别了高风险尾部

S1 对三种 predictor 使用同一风险接受集：

```text
accepted OOF              = 81 / 112 = 0.723214
rejected OOF              = 31 / 112
candidate-pool accepted   = 3937 / 4096 = 0.961182
blind-design preaccepted  = 22 / 24
```

其拒绝点主要包含此前已知的 high-azimuth、cutoff-high-curvature 和局部覆盖空洞。
S2 接受 `112/112`，没有实现有效 abstention，因此 S2 可以保留为负诊断，但不得
再作为 production selective-rule 候选。

### 2.2 `local Matérn k24 + S1` 的 accepted 点预测已经通过

冻结接受集上的实测 OOF 为：

| target | NRMSE | p95 abs | max abs | Gate |
|---|---:|---:|---:|---|
| `R_total` | 0.002451 | 0.002872 | 0.009597 | pass |
| `T_total` | 0.003897 | 0.006238 | 0.012920 | pass |
| `A_balance` | 0.005261 | 0.006531 | 0.013170 | pass |

冻结限值仍为：

```text
NRMSE <= 0.01
p95 absolute <= 0.01
max absolute <= 0.03
```

composition 精确，accepted supported-window Gate 也通过。因此该 pair 的点预测
不是“勉强接近”，而是对所有三个 aggregate target 均有明确余量。

### 2.3 `latent median + S1` 同样通过点预测 Gate

其 accepted-set OOF 为：

| target | NRMSE | p95 abs | max abs | Gate |
|---|---:|---:|---:|---|
| `R_total` | 0.002436 | 0.002157 | 0.009457 | pass |
| `T_total` | 0.003840 | 0.005701 | 0.012920 | pass |
| `A_balance` | 0.005250 | 0.005709 | 0.013342 | pass |

该结果与 Matérn 非常接近。M4I 只需在这两个 predictor 中完成最终选择，不能
再引入新的点预测模型。

### 2.4 RBF/S1 应退出 production 候选

RBF/S1 的 accepted `A_balance`：

```text
NRMSE = 0.014811
p95   = 0.013960
```

已经超过精度 Gate。因此 RBF 继续作为 disagreement/risk signal 和诊断基线，
但不得在 M4I 中再次竞争最终 point predictor。

### 2.5 旧 coverage 失败的真实含义

Matérn/S1 和 median/S1 的 accepted-set empirical coverage 均为：

```text
R = 1.0
T = 1.0
A = 1.0
```

当前代码直接使用 M4G 完整域 OOF 中的 std/残差半径。选择性规则剔除困难点后，
保留下来的样本自然比原 calibration population 更容易，因此完整域区间在该
子集上会显得过宽。

在 selective prediction 中，正确问题应是：

> 在不使用当前 held-out response 的前提下，针对“将被接受的样本分布”校准
> 区间后，是否达到至少 90% 的 held-out coverage，同时区间宽度仍具有实用性？

旧的 `[0.90,0.99]` 上限没有配套 interval-sharpness Gate，而且经验覆盖率以
`1/81` 为离散步长。仅因 `81/81` 而否定已经通过点预测的 selective model，
并不能区分“安全但稍保守”和“毫无信息的超宽区间”。M4I 必须改用条件式
conformal calibration + sharpness，而不是直接删除 uncertainty 要求。

---

## 3. 需要修正的实现与资格合同

### 3.1 threshold fallback 不能再被标记为通过

当前 `_source_threshold(...)` 在没有 candidate 通过时回退到 `q=0.70`，并写入：

```text
source_gate_selection_failed = true
```

但 `crossfit_threshold_gate` 只检查：

```text
held_out_response_used_for_threshold = false
```

两者不是同一件事。无 leakage 是必要条件，但 source Gate 失败后的 fallback
不能称为合格 threshold。

M4I 必须冻结：

```text
crossfit_threshold_gate =
    no held-out response used
    AND every outer-fold source threshold has source_gate_selection_failed=false
```

任何 fold 发生 fallback，则该 predictor/rule pair 整体失败。

### 3.2 threshold 必须按 predictor 单独拟合

当前 source threshold 只使用：

```text
P2 local Matérn k24 prediction/std
```

随后同一个 accepted mask 被套用到 P1/P2/P3。M4I 只保留 P2 和 P3，并分别
使用各自 source prediction、source interval 和 source accepted accuracy 拟合
threshold。风险 score 可以继续共用 S1，但 threshold eligibility 不得共用。

### 3.3 通过候选应选择最高接受率，不是最低 quantile

对固定 quantile grid：

```text
0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95
```

若多个 candidate 均通过，应选择：

```text
maximum accepted fraction
then minimum point-error score
then deterministic lower threshold as tie-break
```

不得继续使用当前的 `min(passing quantile)`。

### 3.4 final production threshold 应冻结 quantile，再在统一尺度重建

当前 final threshold 是不同 outer-fold normalization 下数值 threshold 的中位数。
更稳健的合同是：

1. 保存每折成功选中的 quantile；
2. 冻结 predictor-specific final quantile；
3. 在全体 train112 OOF risk 上使用统一 q05/q95 normalization；
4. 以 final quantile 重新计算 production threshold；
5. 再 response-blind 地预筛 candidate4096 和 blind24。

必须报告 OOF acceptance 与 full-trained response-blind screening acceptance 的
分布漂移，不得只保存最终 accepted count。

---

## 4. Required M4I：不运行 FEM 的最终修正

M4I 只能读取：

```text
immutable train112
TRAIN112_LOCAL_REFERENCE_FOLDS
TRAIN112_LOCAL_OOF
response-blind candidate4096 design
response-blind blind24 design
```

禁止读取任何 validation response，禁止运行任何 FEM。

### 4.1 冻结候选

Point predictor 只允许：

```text
Q1 = L2 local Matérn k24
Q2 = E1 latent median ensemble
```

Risk rule 只允许：

```text
S1 = pre-frozen M4E2 monotone ensemble
```

RBF 只作为 S1 disagreement signal，不再作为 point-predictor 候选；S2 正式退出。

### 4.2 Predictor-specific cross-fitted threshold

对每个 outer fold 和每个 Q1/Q2：

1. source rows = 另外四个 outer folds；
2. q05/q95 risk normalization 只拟合 source rows；
3. 在冻结 quantile grid 上逐一计算 source accepted set；
4. source Gate 检查：

```text
accepted fraction >= 0.70
R/T/A NRMSE <= 0.01
R/T/A p95 abs <= 0.01
R/T/A max abs <= 0.03
accepted supported-window p95 <= 0.02
composition exact
```

5. 从通过 candidate 中选择接受率最高者；
6. 将该 threshold 应用于 held-out fold；
7. held-out response 只用于最终评分，不参与本行 threshold。

若任何 fold 无通过 candidate：

```text
pair = threshold_not_qualified
```

不得 fallback 后继续声称 Gate 通过。

### 4.3 Accepted-distribution conditional conformal interval

每个 outer fold、每个 target 的区间必须仅使用 source accepted rows 校准。
冻结唯一方法：

```text
nonconformity = abs(source_OOF_prediction - source_truth)
finite-sample 95% conformal quantile
interval = heldout_prediction +/- targetwise_quantile
```

不得使用 held-out truth，不再比较多种 interval 算法。R/T/A 区间裁剪到物理
`[0,1]` 只能在保存未裁剪 half-width 后进行，不能通过裁剪伪造 sharpness。

Training-only interval Gate 改为：

```text
cross-fitted accepted coverage per target >= 0.90
p95 interval half-width per target <= 0.02
max interval half-width per target <= 0.03
all half-width finite and > 0
```

旧的 `coverage > 0.99` 不再作为安全失败；必须作为：

```text
conservative_interval_warning
```

单独报告。该更正不是放宽点预测误差，而是用 interval sharpness 取代不合理的
经验覆盖率上限。

### 4.4 Selective training-only Gate

Q1/Q2 中某一 pair 只有同时满足以下条件才能锁定：

```text
accepted OOF fraction >= 0.70
candidate4096 accepted fraction >= 0.70
blind-design preaccepted count >= 12 / 24
accepted R/T/A point accuracy Gate
accepted supported-window Gate
composition exact
conditional-conformal coverage/sharpness Gate
all outer-fold source thresholds genuinely qualified
no validation response accessed
```

若 Q1 和 Q2 都通过，选择顺序冻结为：

1. accepted-set maximum absolute error 更小；
2. p95 absolute error 更小；
3. accepted fraction 更高；
4. deterministic candidate name。

### 4.5 生产锁

通过后建立：

```text
ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK.json
```

至少锁定：

```text
train112 file hashes and tuple hash
forward_solver_sha
surrogate_training_code_sha
fold identity
point predictor
S1 formula and normalization
per-fold source quantile/threshold and no-fallback proof
final production quantile and threshold
conditional-conformal radii
candidate4096 accepted/rejected hashes
blind24 preaccepted/prerejected indices and tuple hashes
point-accuracy / coverage / sharpness metrics
order_resolved_qualified = false
```

独立 Case130 checker 必须从原始 OOF 重新计算阈值、接受集、误差、区间和 hashes，
不得只相信 lock 内布尔值。

---

## 5. Conditional M4J：模型锁后运行 24 个 blind FEM

只有 M4I lock checker 通过，才批准在同一轮运行全部 24 个 blind FEM。

### 5.1 固定前向身份

```text
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
Full3D static uniform N1curl p5/h10/Ny4
mesh = (6,4,14)
MUMPS ICNTL(14)=40
MPI2 / one thread per rank
compact_surrogate_record
```

不得使用当前 surrogate HEAD 作为 forward baseline。

### 5.2 Blind 纪律

- 运行前已经在 lock 中冻结 accepted/rejected blind indices；
- 24 个点全部计算，不得只运行 accepted 点；
- 不得根据任何 blind response 调整 predictor、threshold、quantile 或 interval；
- 第一个未解释 numerical/resource failure 立即停止；
- validation 形成独立不可变包，不能修改 train112。

### 5.3 Blind Gate

对**预先 accepted** blind rows：

```text
accepted count >= 12
R/T/A NRMSE <= 0.01
R/T/A p95 abs <= 0.01
R/T/A max abs <= 0.03
composition exact
conditional interval empirical coverage per target >= 0.90
```

由于 blind accepted count 仅约 12–24，coverage 不设经验上限；同时继续使用锁定
的 interval half-width sharpness，不得在 blind 后放大区间。

对预先 rejected rows 必须报告 truth/error/risk，但不计入 accepted accuracy。
重点检查：

```text
rejected rows 的误差分布是否明显高于 accepted rows
高风险角度是否被正确 abstain
```

Blind 通过后建立：

```text
ANGLE_AGGREGATE_SELECTIVE_QUALIFICATION.json
```

并允许发布 API：

```text
predicted_qualified -> return R/T/A + locked interval
requires_fem        -> no qualified numerical prediction
```

Order Level B 继续返回 `not_qualified`。

Blind 失败则保存不可变负结果并关闭 Task004；不得再调 threshold 后重复使用同一
24 点声称 blind validation。

---

## 6. 若 M4I 仍失败

若 Q1/Q2 均不能在无 fallback、条件 interval 和至少 70% 接受率下通过：

```text
Task004 full-domain aggregate surrogate = controlled-negative closed
Task004 selective aggregate surrogate   = controlled-negative closed
blind FEM                               = not run
new training FEM                        = forbidden
```

后续角度工作只能使用：

```text
已有离散 FEM 表
或指定角度按需运行固定 Full3D FEM
```

不得启动第二轮主动学习、继续增加模型类型或修改已冻结 point-accuracy Gate。

---

## 7. 交付要求

建立 Case130，例如：

```text
benchmarks/cases/130_task004_selective_interval_correction/
```

至少交付：

```text
SELECTIVE_THRESHOLD_CORRECTION.json
SELECTIVE_CONDITIONAL_CONFORMAL.json
SELECTIVE_MODEL_COMPARISON_V2.json
SELECTIVE_OOF_V2.json
ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK.json（若通过）
lock_checker.py
blind24 records/package/checker（仅若lock通过）
selective_blind_validation.md（仅若运行）
outcomes/test_summary_v8.md
response_v8.md
```

测试至少包括：

- predictor-specific source threshold；
- no-fallback threshold Gate；
- highest-acceptance passing quantile；
- held-out response exclusion；
- source-accepted-only conformal calibration；
- coverage + interval-sharpness 重算；
- candidate/blind preacceptance hash；
- fixed forward SHA enforcement；
- validation package 与 train112 分离；
- no second active learning / no Task003 access。

完成后推送当前唯一代理分支并停止等待下一轮审阅。若 M4I lock 成立且 M4J blind
已经在本轮按授权执行，则等待 Review V8；若 M4I 失败，则以 controlled-negative
结果等待 Review V8。

---

## 8. 直接执行指令

```text
请执行 git pull --ff-only，并完整阅读：

surrogate_tasks/task004_nominal_geometry_angle_surrogate/
review_report_v7.md

严格执行 Required M4I。

本轮不得运行任何新的training FEM，不得执行第二轮active learning，
不得访问Task003 frozen validation。

只保留：
- Q1 local Matérn k24
- Q2 latent median
- S1 pre-frozen risk rule

必须修正：
1. predictor-specific source threshold；
2. fallback threshold不得通过Gate；
3. 选择最高接受率的passing quantile；
4. final quantile在统一OOF normalization下重建threshold；
5. accepted-distribution targetwise conformal interval；
6. coverage lower bound + interval-sharpness Gate；
7. 独立Case130 checker。

只有M4I全部Gate通过并创建
ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK.json，
才允许在同一轮使用固定forward SHA运行24个blind FEM。

blind accepted/rejected indices必须在运行前锁定；不得根据blind response调参。

若M4I失败，不得运行blind FEM，按controlled-negative停止。
若blind失败，不得重复使用该24点调参或重新声称blind validation。

禁止第二轮active learning、Fisher、geometry sensitivity和inversion。
```
