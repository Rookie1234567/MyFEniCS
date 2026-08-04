# Task006 Review Report V1：train37 条件验收、S1 物理账本闭合与 blind12 条件授权

## 1. 审阅结论

本轮正式批准并保留：

```text
Task005 final metadata closeout                         = approved
Task006 M0 49-point mother grid / 37-train / 12-blind = approved
Task006 exact reuse inventory                          = approved
Task006 M1 forward campaign                            = approved
79 / 79 new FEM                                        = measured_pass
32 exact reused records                                = approved
train37 immutable dataset                              = approved
finite six-candidate model comparison                  = approved
geometry-grouped training-only CV                      = approved
current training candidate Matérn-5/2 ARD exact GP    = highly promising
training-only synthetic h/w recovery                   = approved as readiness evidence
Case135 / 136 / 137                                    = pass
no blind / validation leakage                          = approved
```

但本轮**尚不批准**：

```text
TASK006_MODEL_SELECTION_LOCK       = absent / not yet authorized
12 blind geometry FEM             = not yet authorized before M2R
Task006 production surrogate       = not yet qualified
formal inversion / Bayesian task   = not authorized
```

原因不是当前预测精度不足。当前 training-only 数字已经远优于冻结 Gate；需要在消耗 36 个 blind FEM 之前，闭合一个无须新增 FEM 的 S1 物理合同和证据独立性缺口。

当前状态冻结为：

```text
forward_solver_sha       = fdf961545f217d620e22800f2704ae9913a6d270
train37_dataset_id       = task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1
train37 geometry count   = 37
fixed angles             = A05=(2 deg,0 deg), A07=(2 deg,90 deg), A09=(4 deg,60 deg)
new FEM                   = 79
exact reuse               = 32
blind geometry count      = 12
blind FEM measured        = 0 / 36
current candidate         = matern52_ard_exact_gp
candidate status          = training_candidate_review_pending
required next stage       = M2R no-FEM contract correction and deterministic replay
conditional next stage    = M3 blind12, only after a valid model lock
```

本报告授权：

```text
M2R = derived/training-only correction, new FEM budget 0
M3  = 12 blind geometries x 3 fixed angles, conditionally authorized only after M2R lock
```

---

## 2. Task005 closeout 与 Task006 M0–M1 数据阶段

### 2.1 Task005 已正确关闭

`TASK005_FINAL_STATUS.json` 已将 Task005 标记为 `approved_closed`，并分别记录 M0–M4 implementation SHA、M5R generator commit、M5R source hash 和 V2 lock hash。Task005 原始/派生数据包未被修改，Task004 blind24 仍未运行。

该 provenance closeout 可以正式接受，不需返工。

### 2.2 49 / 37 / 12 几何设计正确

当前设计满足：

```text
mother grid       = 49 geometries
training design   = 37 geometries
blind design      = 12 strictly interior geometries
train/blind overlap = 0
all 24 boundary geometries are in training
```

训练集包含完整边界和中心附近高价值几何，blind12 全部位于内部，因此后续 blind test 是域内插值验证，不是域外外推。

### 2.3 复用与新 FEM 账本正确

train37 共 111 条角度记录：

```text
37 geometries x 3 angles = 111
79 new FEM
32 exact reuse
```

所有新与复用记录均绑定同一个 forward SHA、Full3D p5/h10/Ny4、MUMPS ICNTL(14)=40、MPI2/thread1 和 observable v3。Case135–137 已核对设计、复用、前向状态和 compact dataset hashes。

因此：

> train37 数据本身是合格的，不应重算 79 个 FEM，也不需要增加 training geometry 才能进入下一步。

---

## 3. 当前 training-only 结果的科学含义

### 3.1 固定三照明成功消除了 Task003/004 的主要非平稳性

Task003 将 `(h,w,grazing,azimuth)` 同时作为输入；Task004 又要求一个模型覆盖完整连续角度域。两者都受 cutoff、高方位角和传播状态变化影响。

Task006 固定 A05/A07/A09 后，输入只剩：

```text
height h in [115,125] nm
width  w in [16,18] nm
```

当前结果显示，这三个固定照明下的二维几何响应面非常平滑，证明 Task005 的离散 DOE 路线是正确的。

### 3.2 当前选中的 GP 是由训练 CV 选出，不是硬编码

有限候选为：

```text
Legendre degree 2 / 3 / 4
local RBF k8
Matérn-5/2 ARD exact GP
quadratic trend + Matérn residual
```

其中通过全部当前 stored training Gates 的候选为：

```text
matern52_ard_exact_gp
degree2_trend_plus_matern52_residual
```

按冻结 selection score，当前选择：

```text
matern52_ard_exact_gp
```

当前摘要报告：

```text
S0 maximum NRMSE                 = 9.75281e-5
S0 maximum absolute error        = 9.95103e-6
S1 maximum NRMSE                 = 7.78114e-5
S1 maximum N1-normalized error   = 0.010780
minimum OOF coverage             = 1.0
p95 interval half-width / N1 sigma = 0.966271
```

这些结果远优于 Task006 的 readiness Gate。

### 3.3 geometry-grouped CV 和 synthetic recovery 路线合理

每个 held-out geometry 的 A05/A07/A09 及全部 S0/S1 targets 同时作为 test，没有按角度行随机拆分。

当前 37 个 outer-test geometry 的 S1/N1 synthetic recovery：

```text
p95 |height error| = 0.000677341 nm
p95 |width error|  = 0.000137901 nm
max |height error| = 0.000986796 nm
max |width error|  = 0.000217014 nm
rejected           = 0 / 37
```

这说明当前训练内的前向近似和参数恢复流程都非常有希望。但它仍是同一 37 点 training evidence 上的 cross-fitted readiness test，不能替代 blind12。

---

## 4. blind12 前必须闭合的主要问题

### 4.1 当前 S1 side total 与 S0 预测是两套独立模型

任务书要求：

```text
selected robust powers + other = predicted R or T
```

当前实现分别拟合：

```text
S0 aggregate latent -> softmax R/T/A
S1 side_total        -> independent predicted side totals
S1 fraction logit    -> selected / other fractions
```

然后使用：

```text
selected_prediction = independent_side_total * selected_fraction
other_prediction    = independent_side_total * (1-selected_fraction)
```

因此 S1 内部 ledger 相对于它自己的 `independent_side_total` 确实由构造闭合，但尚未证明：

```text
S1 reflection selected + other = S0 predicted R
S1 transmission selected + other = S0 predicted T
```

若以后公开 API 同时输出 S0 和 S1，这可能出现两套不同的总反射/总透射。

### 4.2 当前 physics Gate 使用硬编码布尔值，而非数值审计

当前 candidate result 将：

```text
s1_selected_le_side = true
s1_ledger_exact_by_construction = true
```

直接写入结果；Case138 检查这些字段存在且为真，但没有从 OOF 数值重新计算：

```text
selected >= 0
other >= 0
selected + other - S0 side total
maximum sidewise ledger residual
```

数学构造本身合理，但在正式 model lock 前不能只依赖布尔声明。

### 4.3 fold 身份和 boundary/interior breakdown 需要正式冻结

当前 folds 由 deterministic index-modulo 规则生成，OOF records 保存 fold、region 和 nearest distance；但尚缺少一个独立、hash-bound 的：

```text
TRAIN37_GEOMETRY_FOLDS.json
```

当前 summary 也没有完整列出每个 candidate/target 的 boundary vs interior metrics。任务书要求这些内容，且 blind lock 必须绑定准确 fold identity。

### 4.4 Case138 是证据完整性 checker，不是完整 fitter replay

Case138 能确认：

```text
候选集合有限
selected candidate 来自 training CV
OOF geometry grouped and complete
uncertainty / recovery / no-blind flags存在
```

但它没有独立地从 train37 重跑确定性 selected candidate、重建 OOF prediction 和重新计算全部 metrics。当前结果非常好，正式消耗 blind FEM 前应增加一次 deterministic replay checker。

---

## 5. Required M2R：无新 FEM 的最终训练合同闭合

M2R 只使用不可变 train37。不得运行 blind12，也不得增加模型类型。

### 5.1 统一 S0 与 S1 的 side-total authority

生产 S1 必须使用 S0 composition 输出作为唯一 side-total authority：

```text
reflection side total   = S0 predicted R_total
transmission side total = S0 predicted T_total
```

只需要为 S1 继续学习 selected/other fraction；恢复：

```text
selected = S0 side total * fraction_selected
other    = S0 side total * (1-fraction_selected)
```

原独立 side-total model 可以保留为 diagnostic comparison，但不得进入 production S1 或最终 model lock。

不允许为使结果通过而改变 frozen channel identities 或加入新模型。

### 5.2 在 OOF 中保存和审计完整功率账本

每个 geometry、angle、side 必须保存：

```text
S0 predicted side total
selected predicted power
other predicted power
selected + other
ledger residual
selected <= side total
selected >= 0
other >= 0
```

硬 Gate：

```text
max |selected + other - S0 side total| <= 1e-12
all selected / other nonnegative
```

该 Gate 必须从实际数组重算，不能由硬编码 flag 代替。

### 5.3 冻结并独立检查 geometry folds

新增：

```text
outcomes/TRAIN37_GEOMETRY_FOLDS.json
```

至少保存：

```text
five train/test index sets
geometry tuples per fold
fold tuple hashes
boundary/interior counts
all 37 geometries exactly once as test
all three angles and all targets grouped by geometry
```

### 5.4 使用相同有限候选重新执行 training-only CV

只允许重新比较当前六个候选。不得新增 kernel、邻居数、神经网络或手工例外规则。

重新生成：

```text
TRAIN37_MODEL_COMPARISON_V2.json
TRAIN37_OOF_PREDICTIONS_V2.json
TRAIN37_UNCERTAINTY_V2.json
TRAIN37_SYNTHETIC_RECOVERY_V2.json
TRAINING_MODEL_SELECTION_CANDIDATE_V2.json
```

需要补充：

```text
per-target boundary/interior metrics
actual S1 cross-contract ledger residuals
selected + other OOF records
```

若 selected candidate 因正确 S1 重构而变化，这是允许的；选择仍须仅依赖 training CV。

### 5.5 Case139 deterministic replay checker

新增：

```text
benchmarks/cases/139_task006_m2r_contract_replay/
```

checker 至少必须：

1. 核对 train37、Task005 lock、fixed illumination 和 fold hashes；
2. 重建 S0/S1 truth transformations；
3. 独立重算 OOF composition 和 sidewise ledger；
4. 确认每个 geometry 只在一个 test fold；
5. 确认 model selection 只使用 training evidence；
6. 以确定性临时输出重跑 selected candidate，并比较 OOF metrics / prediction hashes；
7. 确认 blind12 response 仍未访问。

---

## 6. M2R 通过后的模型锁

只有修正后的 selected candidate 同时满足原冻结 Gates，才能建立：

```text
TASK006_MODEL_SELECTION_LOCK.json
```

模型锁必须在任何 blind FEM 前冻结：

```text
train37 dataset/file hashes
forward solver SHA
fixed angle order
S0 transform and epsilon
S1 frozen channels / fraction transform / other semantics
selected candidate and all fitted-model metadata
geometry fold identity
uncertainty calibration
training OOF metrics
synthetic recovery metrics
blind12 geometry tuple hashes
blind response accessed = false
```

若 M2R 未通过：

```text
不得运行 blind12
不得自动主动加点
停止等待下一轮审阅
```

---

## 7. M3：条件授权 blind12

M2R 和 Case139 全部通过、model lock 创建成功后，Codex 可在同一执行轮运行：

```text
12 blind geometries x A05/A07/A09 = 36 Full3D FEM
```

所有 blind FEM 必须继续使用：

```text
forward SHA fdf961545f217d620e22800f2704ae9913a6d270
Full3D static p5/h10/Ny4
MUMPS ICNTL(14)=40
MPI2 / thread1
```

blind12 必须一次性评分；不得根据 blind response 重新选择模型、调超参数、改 channel、改 threshold 或改 Gate。

### 7.1 Blind forward Gate

沿用原 training readiness Gates：

S0 每个 target：

```text
NRMSE <= 0.01
p95 absolute error <= 0.005
max absolute error <= 0.015
composition <= 1e-12
```

S1 每个 frozen primary channel：

```text
NRMSE <= 0.02
p95 N1-normalized error <= 0.75
max N1-normalized error <= 2.0
sidewise ledger <= 1e-12
```

uncertainty：

```text
coverage >= 0.90
finite positive widths
p95 half-width <= corresponding N1 sigma
```

### 7.2 Blind recovery Gate

使用锁定模型，对 12 个 blind geometry 的 synthetic observations 执行相同 deterministic recovery：

```text
p95 |height error| <= 0.25 nm
p95 |width error|  <= 0.05 nm
max |height error| <= 0.50 nm
max |width error|  <= 0.10 nm
no rejected / unresolved cases
```

### 7.3 Blind 后停止

Blind 通过时建立：

```text
TASK006_FORWARD_SURROGATE_QUALIFICATION.json
```

并停止等待 Review V2。该资格只表示：

```text
在固定 A05/A07/A09、S、13.5 nm、p5/h10/Ny4 operational FEM 下，
二维 h/w 前向代理通过独立几何验证。
```

它不表示实验噪声已标定，也不表示 Bayesian inversion 已完成。

Blind 失败时：

```text
保存不可变失败报告
不得使用 blind12 调参后再次声称其为 blind validation
不得自动开始 active learning
停止等待审阅
```

---

## 8. 下一科学方向

若 Task006 blind12 通过，下一独立任务应是固定三照明下的参数反演资格化，而不是继续扩大代理输入维度。建议后续 Task007 分为：

1. 使用已资格化代理进行全域 synthetic inversion；
2. 比较 S0 likelihood 与 S1 likelihood，不重复计数二者；
3. 使用 N1/N2 的噪声 Monte Carlo 检查 bias、coverage、failure rate；
4. 将 surrogate discrepancy 单独加入 covariance；
5. 再建立 Bayesian posterior / MAP / credible interval；
6. 最后才接入实验 covariance 和真实测量。

若 Task006 blind12 未通过，应回到 training-only 证据设计新的几何采样或局部代理，但不能使用 blind12 继续调参后保留其 blind 名义。

---

## 9. 给 Codex 的执行指令

```text
请执行 git pull --ff-only，并完整阅读：

surrogate_tasks/task006_fixed_illumination_hw_surrogate/review_report_v1.md

先严格执行 M2R，不得立即运行 blind FEM：

1. 让 production S1 使用 S0 predicted R/T 作为唯一 side-total authority；
2. 保存 selected、other、S0 side total 和实际 ledger residual；
3. 冻结 TRAIN37_GEOMETRY_FOLDS.json；
4. 使用原六候选重新做 geometry-grouped CV、uncertainty 和 synthetic recovery；
5. 增加 boundary/interior metrics；
6. 建立 Case139 deterministic replay checker。

只有修正后的全部 training Gates 和 Case139 通过，才创建
TASK006_MODEL_SELECTION_LOCK.json，并可在同一轮运行 12 个 blind
geometries × 3 angles。

blind 模型、transform、channel、uncertainty 和 accepted Gate 必须在运行前锁定；
不得根据 blind response 调参。blind 后无论通过或失败均停止等待 Review V2。

禁止 geometry active learning、正式 Bayesian inversion、实验数据拟合、
P 入射、波长/材料/更多结构参数扩展。
```
