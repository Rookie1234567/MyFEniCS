# Task003 Review Report V2：第一轮主动学习审阅、同口径学习曲线与第二轮条件授权

## 1. 审阅结论

```text
review_status = round1_evidence_approved_fixed_reference_audit_required
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
M3S_contract_completion = approved_and_retain
active_learning_round1_plan = approved_and_retain
active_learning_round1_FEM = approved_8_of_8_measured_pass
round1_dataset_104_plus_16 = provisionally_accepted_pending_tracked_exact_checker
training_cv_104 = hard_gate_failed
MODEL_SELECTION_LOCK = not_authorized
frozen_validation = sealed_not_accessed
round2_FEM = conditionally_authorized_only_after_M3T_fixed_reference_gate
round3_FEM = not_authorized
formal_angle_DOE = not_authorized
formal_inversion = not_authorized
required_next_action = M3T_status_repair_and_fixed_reference_audit_then_optional_round2
```

第一轮停止是正确的，不是程序崩溃、内存不足或有限元失败。Review V1 只授权了一轮 8 点主动学习，并明确规定：104 点 training-only CV 若仍未通过 hard Gate，必须停止等待 Review V2。Codex 已遵守该边界。

当前证据支持以下判断：

1. M3S 合同修正有效，feature B、top/bottom mask、P2 功率重构和有限 G1/G2 模型集合可以保留；
2. 8 个新增 Ny4 p5 Full3D 点全部数值通过，前向数据质量没有问题；
3. 104 点训练仍未达到反演级 hard Gate，不得解封 16 点 frozen validation；
4. 当前 `96 -> 104` 学习曲线不是严格同口径比较，因为数据量变化后 CV fold 被重新生成，同时选定模型由 G1 变为 G2；
5. 在决定第二轮 FEM 前，必须先完成一个不新增 FEM、不访问 validation 的 M3T 固定参考审计；
6. 若 M3T 证明第一轮在相同测试行和相同模型合同下产生了稳定改善，则允许在同一执行轮中进行**仅一轮**新的 8 点主动加点；否则不得继续堆样本，应停止并提出分区/局部代理方案。

---

## 2. 已接受的第一轮证据

### 2.1 M3S 合同

接受并冻结：

```text
production feature = B
    height_scaled
    width_scaled
    grazing_scaled
    azimuth_scaled

aggregate latent:
    zR = log((R+eps)/(A+eps))
    zT = log((T+eps)/(A+eps))
    reconstruction = softmax(zR,zT,0)

aggregate candidates:
    G1 = constant-mean Matérn-5/2 ARD exact GP
    G2 = degree-2 Legendre trend + Matérn-5/2 ARD residual GP

allowed jitter:
    1e-10, 1e-8, 1e-6

power model:
    P1 independent log power = diagnostic only
    P2 predicted side total + masked active-channel fractions = physical candidate
```

P2 的反射侧和透射侧功率账本在 OOF 重构中闭合到约 `1e-16`，说明非负性、inactive-null 语义与 side-total conservation 已正确实现。物理重构可以保留，但守恒本身不能替代预测精度 Gate。

### 2.2 第一轮选点与 FEM

接受：

```text
candidate pool = frozen 4096 points
round = 1
selected points = exactly 8
production source SHA = 10e3356ba8364286a452077f71d7e3b92ea24cd5
model = S_PROD_FULL3D_STATIC_P5_H10_NY4
mesh = (6,4,14)
MPI2 / thread1
```

8 个点全部完成 `measured_pass`，零 swap，cleanup complete。首次只读 JIT cache 停止发生在 PDE 前，随后通过隔离 `/tmp` cache 重试成功；它是解释清楚的执行环境事件，不是数值失败。

第一轮选点明显偏向低掠射/cutoff：8 点中多数位于 `grazing <= 1.5 deg`，只有一个普通 interior 和一个 high-azimuth 点。这个分布与上一轮误差热点一致，因此不是错误，但它限制了第一轮对完整四维域全局误差的改善能力。

### 2.3 104 点训练结果

接受当前 104 点 training-only CV 的事实结果：

| target | NRMSE | p95 absolute | p95 relative (`truth>=1e-2`) |
|---|---:|---:|---:|
| `R_total` | `0.0296161` | `0.0468790` | `0.309233` |
| `T_total` | `0.0121282` | `0.0162212` | `0.0719471` |
| `A_balance` | `0.0366639` | `0.0459915` | `0.1039108` |

选定候选为：

```text
G2_degree2_trend_residual_gp
feature B
jitter = 1e-10
```

这些值明显没有达到冻结的 aggregate hard Gate：

```text
NRMSE <= 0.02
p95 absolute <= 1e-3
truth >= 1e-2: p95 relative <= 1%
```

因此：

```text
MODEL_SELECTION_LOCK = forbidden
frozen validation unlock = forbidden
production surrogate claim = forbidden
```

---

## 3. 为什么当前不能直接根据 `96 -> 104` 表决定第二轮

### 3.1 CV folds 发生了变化

当前 `folds(x)` 根据传入的全部输入点重新进行 maximin ordering，再按该顺序生成五折。训练点从 96 增加到 104 后：

```text
point set changes
-> maximin ordering changes
-> test membership changes
-> fold hash changes
```

因此 96 点与 104 点表中的误差不是在完全相同的测试行上计算的。

### 3.2 选定模型也发生了变化

当前学习曲线比较的是：

```text
96 rows  -> G1 constant GP
104 rows -> G2 degree-2 trend + residual GP
```

它同时改变了：

- 训练样本数；
- fold membership；
- selected model family。

所以该表可以说明“当前各自最优合同下仍未通过 Gate”，但不能严格量化“8 个新点单独贡献了多少改善”。

### 3.3 第一轮 acquisition 使用了原 96 点训练信息

第一轮点位由原 96 点的 OOF error、uncertainty、distance 和 cutoff 指标生成。因此原 96 点不能再被描述为完全独立的盲测集合。后续固定参考比较只能作为 **training-only paired diagnostic**，不能替代 16 点 frozen validation。

---

## 4. 当前证据中的一致性问题

### R1：`TRAINING_STAGE_STATUS.json` 已过期

当前 tracked 状态仍写有：

```text
training_count = 96
selected_candidate = G1_constant_gp
active_learning.points_used = 0
first_round_plan = eligible_for_review_only
```

但实际当前状态是：

```text
training_count = 104
round1 points used = 8
selected candidate = G2_degree2_trend_residual_gp
round1 FEM = complete
```

必须生成新的 post-round1 authority，不能让自动 checker 或后续任务继续读取旧状态。

### R2：104+16 数据集缺少足够明确的 tracked exact-design authority

报告称 deterministic adapter 已生成 104+16 compact dataset，但正式继续前必须有独立 tracked 记录证明：

- 原 96 个 training sample 各出现一次；
- Round1 的 8 个 sample 各出现一次；
- frozen validation 仍为原 16 个 tuple；
- missing=0、extra=0、duplicate=0；
- Case119 与 Case121 source/model/route/schema 均符合合同；
- validation target 仍未被加载；
- 104 数据数组、sample IDs、split 与文件 hashes 可重建。

### R3：测试与状态报告未完整升级到 Round1 后语义

`test_summary.md`、Case120 checker 状态和最终 response inventory 必须明确区分：

```text
M3R 96-row evidence
M3S 96-row evidence
Round1 8-point FEM evidence
104-row CV evidence
```

不能继续用只覆盖早期 96 点阶段的摘要充当当前最终状态。

---

# 5. Required M3T：固定参考学习曲线审计

本阶段不得运行新 FEM，不得读取 frozen validation。

## M3T-1：冻结原 96 点 reference folds

从原 96 个 training rows、feature B 和冻结 seed 重建并跟踪：

```text
BASE96_REFERENCE_FOLDS.json
```

其中每个原 96 点的 test fold 永久固定。后续所有 `96 vs 104 vs 112` 学习曲线都必须在这组**相同原始测试行**上报告 paired metrics。

## M3T-2：同模型、同测试行的 paired comparison

对每个模型合同分别比较，而不是只比较各数据集自行选择的 winner：

```text
G1 / jitter 1e-10
G2 / jitter 1e-10
```

对每个固定 fold：

### Baseline-96

```text
train = 该 fold 的原96训练行
    test = 该 fold 的原96测试行
```

### Enriched-104

```text
train = 同一 fold 的原96训练行 + 全部8个Round1新点
    test = 完全相同的原96测试行
```

报告：

- R/T/A NRMSE；
- p95 absolute；
- p95 relative；
- max error；
- 每个测试点的 paired error delta；
- low-grazing、cutoff、high-azimuth、interior breakdown。

该结果只用于判断主动加点是否改善 training-domain interpolation，不得称为 blind validation。

## M3T-3：8 个新点的 prospective acquisition audit

第一轮 FEM 运行前，96 点模型没有见过这 8 个 target。因此必须重建并保存：

```text
96-point pre-addition prediction at each of 8 points
new FEM truth
absolute / relative / standardized error
predicted uncertainty
acquisition score and components
```

该审计回答：

> acquisition 是否真的选中了原模型预测困难或不确定的点？

同时做 leave-one-new-point-out diagnostic：每次用原 96 点加其余 7 个新点预测被留出的 1 个新点。该结果仍是 training-only 诊断，但可判断 8 点之间是否只覆盖了同一个狭窄局部区域。

## M3T-4：更新当前 authority

必须新增或更新：

```text
outcomes/ROUND1_COMPLETION_STATUS.json
outcomes/ROUND1_DATASET_VERIFICATION.json
outcomes/learning_curve_fixed_reference.md
outcomes/round1_prospective_audit.md
outcomes/test_summary.md
outcomes/TRAINING_STAGE_STATUS.json
```

新的 `TRAINING_STAGE_STATUS.json` 至少包含：

```text
training_count = 104
frozen_validation_count = 16
active_learning_round1_points = 8
active_learning_total_points_used = 8
selected_104_candidate
aggregate metrics
power metrics
validation_target_accessed = false
round2_status
```

---

# 6. Round 2 条件授权 Gate

完成 M3T 后，只有同时满足以下条件，才允许在同一执行轮中运行第二轮 8 个 FEM 点：

1. 在固定 reference folds 下，Enriched-104 相对 Baseline-96：
   - `R_total` NRMSE 至少改善 10%；
   - `A_balance` NRMSE 至少改善 10%；
   - `T_total` NRMSE 不得恶化超过 10%；
2. 三个 aggregate 中至少两个的 paired p95 absolute error 改善；
3. 第一轮 8 点 prospective audit 没有显示 acquisition 完全失效；
4. 104+16 exact-design checker 通过；
5. frozen validation target 仍未访问；
6. Round2 plan 独立 checker 通过。

若任一条件不满足：

```text
Round2 FEM = forbidden
required action = controlled stop and propose regional/partitioned surrogate
```

不得为了继续预算而无条件追加点。

---

# 7. Round 2 设计约束

若第 6 节 Gate 通过，批准**仅一轮**新的 8 点。Round 3 仍不授权。

## 7.1 数据与模型身份

必须继续使用：

```text
FEM source SHA = 10e3356ba8364286a452077f71d7e3b92ea24cd5
model = S_PROD_FULL3D_STATIC_P5_H10_NY4
route = full3d_static_uniform_n1curl_p5_h10_ny4
mesh = (6,4,14)
MPI2 / thread1
compact output
```

不得改变已有 104 点和 16 点 frozen validation。

## 7.2 防止再次过度集中

第一轮已强烈覆盖 low-grazing/cutoff。第二轮必须增加全域多样性：

```text
最多3点 grazing <= 2 deg
至少2点 grazing >= 4 deg
至少2点 azimuth >= 60 deg
至少2点 ordinary interior / non-cutoff
至少覆盖3个不同 h 区间和3个不同 w 区间
```

单个点可以同时满足多个区域要求，但 8 点至少应形成 4 种不同的 region signature。

## 7.3 acquisition

允许使用：

- 104 点 fixed-reference OOF error surrogate；
- calibrated GP uncertainty，仅作为排序指标；
- feature-B nearest distance；
- cutoff proximity；
- primary power P2 error contribution；
- maximin diversity。

不得使用 frozen validation target、位置相关误差或其派生统计。

## 7.4 Round2 后停止

若 8 个点全部通过，形成：

```text
training = 112
frozen validation = unchanged 16
```

然后执行：

1. fixed-reference learning curve；
2. normal 112-row training-only CV；
3. P2 power audit；
4. uncertainty diagnostic；
5. exact-design dataset checker。

无论是否通过，均停止等待 Review V3：

```text
Round3 = forbidden
validation unlock = forbidden unless hard Gate passes and Review V3 approves lock
```

---

# 8. 不允许的做法

不得：

- 根据当前 104 点失败直接解封 validation；
- 修改 16 个 frozen validation tuple；
- 放宽 aggregate 或 power hard Gate；
- 将旧 Ny3、p4、Hybrid 或 discretization-audit 数据混入训练；
- 无固定参考审计便启动 Round2；
- 自动执行 Round3；
- 开始 angle DOE、反演、MCMC 或 P incident surrogate；
- 将 GP OOF 方差表述为已校准物理不确定度。

---

# 9. 交付要求

至少新增：

```text
benchmarks/cases/122_task003_round1_fixed_reference_and_optional_round2/
    README.md
    config.json
    expected.json
    checker.py
    records/

surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes/
    ROUND1_COMPLETION_STATUS.json
    ROUND1_DATASET_VERIFICATION.json
    BASE96_REFERENCE_FOLDS.json
    learning_curve_fixed_reference.md
    round1_prospective_audit.md
    ACTIVE_LEARNING_ROUND2_PLAN.json        # 仅Gate通过时
    training_cv_112.md                      # 仅Round2完成时
    TRAINING_STAGE_STATUS.json              # 更新
    test_summary.md                         # 更新

surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/
    response_v4.md
```

最终报告必须明确：

- M3T Gate 每一项的 observed value；
- Round2 是否被实际授权并执行；
- 新 FEM 的状态和资源；
- 96/104/112 的同口径学习曲线；
- frozen validation 是否仍封存；
- 当前 qualified / unqualified 输出；
- 下一步停止边界。

---

# 10. Codex 执行摘要

```text
1. 保留 Case121 与现有104点结果，不改写历史证据；
2. 先执行 M3T，无新FEM、无validation访问；
3. 修正过期状态与104+16数据集authority；
4. 生成固定原96测试行的paired learning curve；
5. 审计8个新点的pre-addition prediction；
6. 只有第6节Gate全部通过，才生成并运行Round2恰好8点；
7. Round2后形成112+16、重做training-only CV并停止；
8. 不得执行Round3、validation、DOE或inversion。
```
