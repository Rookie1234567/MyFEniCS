# Task004 Review Report V6：M4G 全域负结果审阅、结构“安全域”更正与可拒绝角度代理闭合路线

## 1. 审阅结论

本轮批准保留并正式接受：

```text
M4G train112 frozen outer folds                = approved
complete 112-row OOF for four local candidates = approved
finite E1/E2 ensemble comparison               = approved
post-active outlier audit                       = approved as heuristic diagnostic
Aggregate Level A full-domain negative result   = approved for the reviewed candidate set
Order Level B negative result                   = approved
Case128 independent checker                     = pass
```

本轮不批准：

```text
ANGLE_AGGREGATE_MODEL_SELECTION_LOCK            = absent / not authorized
ANGLE_ORDER_MODEL_SELECTION_LOCK                = absent / not authorized
ANGLE_AGGREGATE_SAFE_DOMAIN_CANDIDATE            = structural support only, not a qualified safe domain
Task004 second active-learning round             = forbidden
any new training FEM                             = forbidden
Task004 blind-validation FEM                     = sealed until selective model lock
formal Fisher angle ranking                      = forbidden
geometry sensitivity / inversion                 = forbidden
Task003 Round3 / frozen validation               = forbidden / sealed
```

当前正式状态冻结为：

```text
forward_solver_sha              = fdf961545f217d620e22800f2704ae9913a6d270
training_dataset_id             = task004_angle_nominal_p5_ny4_train112_v1
training_rows                   = 112
fixed_geometry                  = h=120 nm, w=17 nm
angle_domain                    = grazing 0.5-10 deg, azimuth 0-90 deg
forward_model                   = Full3D static uniform N1curl p5/h10/Ny4
MUMPS                           = ICNTL(14)=40, MPI2, thread1
blind_validation_rows_measured  = 0 / 24
full_domain_aggregate_status    = not_qualified under the frozen finite candidate set
order_resolved_status           = not_qualified
new_training_FEM_budget         = 0
required_next_stage             = M4H selective angle surrogate with abstention
```

本轮停止不是程序卡死，也不是有限元失败。M4G 已完成 Review V5 要求的全部 112 点局部资格化；停止原因是没有任何单模型或有限集成同时满足 full-domain accuracy、supported-window、composition 和 uncertainty Gates。

从本报告起，Task004 不再继续尝试通过增加模型种类或第二轮 FEM 来强行建立“完整矩形内每个角度都给出合格预测”的代理。下一步只允许建立：

> **selective angle surrogate**：对训练内证据支持的角度返回经过资格化的 `R/T/A`；对高风险角度明确返回 `requires_fem`，而不是输出一个看似连续但没有精度保证的数值。

若 M4H 仍不能在合理接受率下通过，则 Task004 以 controlled-negative 关闭，不运行 blind FEM。

---

## 2. M4G 结果的正式解释

### 2.1 完整 112 点 OOF 已补齐此前资格缺口

M4G 冻结 `TRAIN112_LOCAL_REFERENCE_FOLDS.json`，使 112 个样本均恰好一次作为 outer-test，包括新增的 16 个主动学习点。以下候选均在相同 folds 上完成完整 OOF：

| candidate | R NRMSE | T NRMSE | A NRMSE | score | supported-window | uncertainty | Level A |
|---|---:|---:|---:|---:|---|---|---|
| local RBF k24 | 0.017540 | 0.023495 | 0.036288 | 3.84925 | fail | pass | fail |
| trend + local residual k24 | 0.017030 | 0.024232 | 0.036689 | 4.07189 | fail | pass | fail |
| local Matérn k24 | 0.027526 | 0.018068 | 0.035200 | 4.33840 | pass | fail | fail |
| latent median ensemble | 0.026118 | 0.019499 | 0.037083 | 4.57265 | pass | fail | fail |
| local Matérn k32 | 0.027062 | 0.023869 | 0.038534 | 4.76395 | pass | fail | fail |
| non-negative stack | 0.023031 | 0.017979 | 0.035779 | 4.95502 | fail | fail | fail |

因此，现在可以正式确认：

```text
在 train112、当前冻结 full-domain Gate 和 Review V5 批准的有限模型集合下，
没有合格的完整角度域 Aggregate Level A 模型。
```

这不是对所有可能代理方法的数学否定，但已经足以关闭继续扩大 model zoo 的路线。

### 2.2 local RBF 是 minimax 最优，但仍不能锁定

training-CV 选择 `L1_local_rbf_k24_s1e-08`。其完整 112 点结果为：

| target | NRMSE | p95 abs | max abs | Gate |
|---|---:|---:|---:|---|
| R | 0.017540 | 0.029824 | 0.045251 | fail |
| T | 0.023495 | 0.025298 | 0.106927 | fail |
| A | 0.036288 | 0.038492 | 0.112933 | fail |

它的 composition 和 cross-fitted coverage 通过，但总体与局部窗口精度明显不足，尤其是 high-azimuth/cutoff 邻域。

### 2.3 local Matérn 的窗口插值较好，但完整 OOF 与区间仍未闭合

local Matérn k24 的 supported-window Gate 通过，但完整 OOF 为：

```text
R: NRMSE=0.027526, p95=0.012252, max=0.118618
T: NRMSE=0.018068, p95=0.018866, max=0.081109
A: NRMSE=0.035200, p95=0.043384, max=0.103510
```

其 uncertainty Gate 失败的直接原因之一是 T 的经验覆盖率达到 `1.0`，超过冻结的 `[0.90,0.99]`，表明区间过于保守；这不能通过简单放宽上限来包装成成功，因为 accuracy 本身仍明显失败。

### 2.4 两种有限集成都没有解决尾部问题

E1 latent median 与 E2 non-negative stack 均保持 `R+T+A=1`，但没有同时通过 accuracy、supported-window 和 uncertainty。该负结果说明，现有三个局部预测器的简单稳健组合不足以消除高方位角/cutoff 的局部尾部误差。

---

## 3. 异常点审计说明了什么

`POST_ACTIVE_OUTLIER_AUDIT` 显示，最高误差主要集中在：

```text
high azimuth
low grazing + cutoff-near
cutoff/high-curvature transitions
少量剩余 coverage hole
```

典型点包括：

```text
(2.961689°, 82.168203°): T/A 绝对误差约 0.107/0.113
(4.0°, 75.0°):          T/A 绝对误差约 0.070/0.065
(0.907298°, 82.131934°): R/A 绝对误差约 0.045/0.046
```

新增 16 点中仍有部分进入最高误差列表，说明主动学习降低了部分尾部误差，但没有使这些局部高曲率区域整体闭合。

需要注意：`coverage_hole / cutoff_high_curvature / boundary_one_sided / model_instability` 是基于距离、cutoff margin 与模型 disagreement 的**启发式分类**，不是已经证明的物理根因。后续可以用它们构造风险信号，但不得把分类标签当作真值。

---

## 4. 对“安全域”文件的正式更正

当前 `ANGLE_AGGREGATE_SAFE_DOMAIN_CANDIDATE.json` 报告：

```text
safe_count = 4074 / 4096
safe_fraction = 0.99462890625
excluded by unsupported topology = 22
excluded by nearest distance      = 0
```

该结果**不能解释为 99.46% 角度域已经安全**，原因有三点。

### 4.1 它只检查结构支撑，不检查预测误差

当前规则只使用：

```text
mask signature 是否在 train112 出现
candidate 到完整 train112 的最近距离
```

没有在 candidate pool 上应用：

```text
local Matérn predictive risk
RBF/Matérn disagreement
cross-fitted error-control threshold
```

因此它只能称为：

```text
structural_support_domain_candidate
```

不得称为误差资格化的 safe domain。

### 4.2 最近距离阈值的两侧定义不一致

代码使用：

```text
threshold = train112 OOF 点到“各自 outer-fold training rows”的距离 p95
candidate distance = candidate 到“完整 train112”的距离
```

完整 112 点的距离天然通常小于只使用约 89-90 个 fold-training 点的距离，所以阈值过于宽松。这解释了为什么 4096 个 candidate 中没有一个因 distance 被排除。

下一轮不得沿用该距离规则作为安全性证明。

### 4.3 未见 topology 只直接阻塞 Order Level B

对于 Aggregate R/T/A，mask topology 变化是风险特征，但不改变输出维数；对于各衍射级输出，未见 topology 必须 fail closed。因此：

```text
Aggregate selective support
Order structural support
```

必须分别定义，不能用一个布尔值同时代表两层资格。

本报告要求保留原文件作为负面/结构诊断，并新增更准确命名的 authority；不得原地改写历史证据。

---

## 5. Task004 的路线决策

### 5.1 完整角度域模型路线关闭

在以下条件不变时，不再继续 full-domain 模型搜索：

```text
train112 不变
no second active-learning round
no new training FEM
same Level A error Gates
same finite model families
```

不得继续加入神经网络、随机森林、更多 kernel、更多局部邻居数或手工 region switch 来碰运气。

### 5.2 允许建立可拒绝的 selective surrogate

实际接口改为：

```python
AngleSurrogate.predict(grazing_deg, azimuth_deg)
```

但返回状态必须有两种：

```text
predicted_qualified
requires_fem
```

只有风险 Gate 通过的角度才返回 qualification-backed `R/T/A`；其余角度明确要求调用固定 Full3D FEM。不得对被拒绝点静默给出普通数值。

Order Level B 继续整体 `not_qualified`。即使 Aggregate selective model 通过，公开接口也不得把各衍射级功率标记为 qualified。

---

## 6. Required M4H：selective surrogate 训练内闭合

M4H 不运行任何新 FEM，不访问 blind response，只使用不可变 train112、冻结 folds、现有有限候选和 response-blind candidate/blind designs。

### 6.1 冻结 selective contract

建立：

```text
ANGLE_AGGREGATE_SELECTIVE_QUALIFICATION_CONTRACT.json
SELECTIVE_RISK_SIGNAL_CONTRACT.json
```

点预测候选只允许：

```text
P1 = local RBF k24
P2 = local Matérn k24
P3 = E1 latent median
```

不得新增其他 point predictor。

风险信号只允许使用预测时可获得的：

```text
local Matérn k24 native/calibrated std
RBF vs Matérn k24 disagreement
Matérn k24 vs k32 disagreement
nearest training distance
signed nearest-cutoff margin / cutoff order
low-grazing / high-azimuth / boundary flags
mask signature support
```

不得使用 query 的真实 FEM response。

### 6.2 cross-fitted selective risk

每个 outer fold 必须：

1. 只使用其它 outer folds 的 OOF `risk/error` 对归一化系数和接受阈值进行拟合；
2. 将阈值应用于当前 fold；
3. 当前 fold response 只能用于最终评分，不得参与阈值学习；
4. 保存每个样本的 risk components、threshold source folds、accepted/rejected 和原因。

优先复用 M4E2 已验证的 monotone acquisition ensemble；只允许有限比较：

```text
S1 = pre-frozen M4E2 ensemble risk
S2 = max calibrated std + model disagreement
```

不允许训练复杂黑箱 error classifier。

### 6.3 selective training-only Gates

只有某一 `(point predictor, risk rule)` 同时满足下列条件，才可创建 selective model lock：

#### 接受范围

```text
accepted OOF rows >= 70% of 112
accepted response-blind candidate4096 >= 70%
accepted response-blind blind-design angles >= 12 / 24
unsupported Order topology may be accepted for Aggregate only,
but must remain order-unqualified
```

#### accepted OOF accuracy

对 accepted rows 的 R/T/A 分别要求：

```text
NRMSE <= 0.01
p95 absolute error <= 0.01
max absolute error <= 0.03
composition exact
```

#### 支撑与区间

```text
accepted supported-window points p95 <= 0.02
accepted-set cross-fitted 95% coverage in [0.90,0.99]
rejected points are never counted as zero error
acceptance/rejection is determined before seeing each held-out response
```

#### 分区透明度

必须分别报告：

```text
low_grazing acceptance rate
high_azimuth acceptance rate
cutoff_near acceptance rate
ordinary_interior acceptance rate
boundary acceptance rate
old96 / new16 acceptance rate
```

不得仅通过拒绝全部困难区域来隐藏问题；若任一主要区域 acceptance 为 0，必须在 API domain statement 中明确排除该区域。

### 6.4 safe-domain 文件更名与重建

保留原：

```text
ANGLE_AGGREGATE_SAFE_DOMAIN_CANDIDATE.json
```

新增：

```text
ANGLE_AGGREGATE_STRUCTURAL_SUPPORT_DOMAIN.json
ANGLE_AGGREGATE_SELECTIVE_ACCEPTANCE_DOMAIN.json
```

前者只记录 topology/distance 等 response-blind 结构信息；后者由 cross-fitted risk contract 决定，才允许使用 `selective acceptance` 语义。

---

## 7. selective 模型锁与 blind-validation 条件授权

若 M4H 全部 training-only Gates 通过，创建：

```text
ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK.json
```

锁必须绑定：

```text
train112 dataset/file hashes
forward_solver_sha
surrogate training code SHA
fold identity
point predictor
risk formula and weights
cross-fitted threshold procedure
final threshold
accepted/rejected training rows
candidate4096 acceptance hash
blind24 design acceptance hash（只用角度，不用response）
uncertainty calibration
validation_target_accessed=false
```

模型锁通过独立 checker 后，条件批准使用固定 forward SHA 一次性运行全部 24 个 blind-validation FEM。

在运行 FEM 前，必须先根据角度冻结：

```text
blind24 accepted indices
blind24 rejected indices
```

blind responses 返回后：

1. 正式精度 Gate 只在预先 accepted 的 blind rows 上评分；
2. rejected rows 仍保存 FEM truth，用于审计拒绝策略，但不得事后改成 accepted；
3. accepted blind rows 必须至少 12 个；
4. accepted blind R/T/A 使用与 training accepted-set 相同 Gate；
5. 若 selective blind 失败，不得调阈值后再次声称 blind validation。

通过后创建：

```text
ANGLE_AGGREGATE_SELECTIVE_QUALIFICATION.json
```

公开 API 必须返回：

```text
status
R/T/A mean and calibrated interval（仅 predicted_qualified）
risk score / threshold
nearest training distance
cutoff identity
model disagreement
acceptance reason or FEM fallback reason
fixed forward/model/dataset/code identity
aggregate_qualified=true
order_resolved_qualified=false
```

---

## 8. M4H 失败时的关闭规则

若没有 selective candidate 同时满足：

```text
accepted OOF accuracy
minimum acceptance fraction
supported-window accepted accuracy
cross-fitted coverage
```

则：

```text
Task004 full-domain angle surrogate = controlled-negative closed
Task004 selective angle surrogate   = controlled-negative closed
blind-validation FEM                = not run
```

后续角度研究只能采用：

```text
已有离散 FEM 角度表
或按需调用固定 Full3D FEM
```

不得执行第二轮主动学习，也不得继续增加模型类型。

---

## 9. Order Level B 边界

当前：

```text
mask agreement                    = 100%
sidewise ledger                   = pass
primary-channel maximum NRMSE     ≈ 0.406
primary-channel p95/max           = fail
```

Order Level B 保持 `not_qualified`。M4H 不再训练或调试 order-resolved 模型；其数据和负结果保留，等待未来独立任务。Aggregate selective blind 即使通过，也不改变该状态。

---

## 10. 交付要求

建立 Case129，例如：

```text
benchmarks/cases/129_task004_selective_angle_surrogate/
```

至少交付：

```text
SELECTIVE_RISK_SIGNAL_CONTRACT.json
SELECTIVE_RISK_CROSSFIT.json
SELECTIVE_MODEL_COMPARISON.json
ANGLE_AGGREGATE_STRUCTURAL_SUPPORT_DOMAIN.json
ANGLE_AGGREGATE_SELECTIVE_ACCEPTANCE_DOMAIN.json
ANGLE_AGGREGATE_SELECTIVE_QUALIFICATION_CONTRACT.json
selective OOF records
region-wise acceptance/error report
independent checker
ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK.json（仅Gate通过时）
blind24 pre-acceptance manifest（仅lock通过时）
blind24 FEM/qualification（仅获条件授权后）
test_summary_v7.md
response_v7.md
```

checker 必须重新计算，而不是只相信 JSON 布尔值：

- train112 identity/hashes；
- each-index-once folds；
- no held-out response leakage in risk threshold；
- accepted/rejected counts and hashes；
- accepted-set metrics；
- candidate/blind design response-blind acceptance；
- no model lock on Gate failure；
- no blind FEM before lock；
- no new training FEM；
- Task003 validation untouched。

---

## 11. Codex 执行边界

请执行 `git pull --ff-only`，完整阅读本报告，然后执行 Required M4H。

```text
禁止任何新training FEM
禁止第二轮active learning
禁止提前运行blind FEM
禁止访问Task003 frozen validation
禁止Fisher、geometry sensitivity和inversion
```

只有 selective training-only Gate 全部通过并创建锁后，才允许在同一执行轮运行 24 个 blind-validation FEM；否则受控停止等待 Review V7。
