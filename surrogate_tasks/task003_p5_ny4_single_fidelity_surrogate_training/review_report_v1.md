# Task003 Review Report V1

## 1. 审阅结论

```text
review_status = M3R_approved_targeted_training_completion_and_round1_enrichment_required
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
M0_local_dataset_and_CPU = approved_and_retain
M1_M2_contracts = approved_with_targeted_corrections_below
M3R_pipeline_correction = approved_and_retain
training_cv = materially_improved_but_hard_gate_failed
selected_training_candidate = exact_gp:features=B
MODEL_SELECTION_LOCK = not_authorized
frozen_validation = sealed_not_accessed
active_learning_round1 = conditionally_authorized_after_M3S_contract_corrections_and_plan_check
active_learning_round2_or_round3 = not_authorized_in_this_review
formal_angle_DOE = not_authorized
formal_inversion = not_authorized
required_next_action = M3S_contract_completion_then_one_8_point_active_learning_round
```

Task003 的第二次停止是正确的。修正后的训练管线已经真实学习到主要响应趋势，但仍未达到预冻结的反演级 hard Gate。不得创建 `MODEL_SELECTION_LOCK.json`，不得读取 16 个 frozen-validation targets。

本轮不再把失败归因于本机资源或 GPU：本机 CPU smoke 可复现、零 swap，96 点 exact GP 的资源远低于 16 GB 上限。

同时，当前证据已经足以表明：**不应继续无限调整同一 96 点上的普通全局模型，也不应立即解封验证；下一步应先完成有限的合同修正，然后执行第一轮 8 点、训练集驱动的主动加点。**

---

## 2. 接受的 M3R 修正

接受并保留：

1. aggregate 改为真正的 composition latent：
   ```text
   zR = log((R+eps)/(A+eps))
   zT = log((T+eps)/(A+eps))
   (R,T,A) = softmax(zR,zT,0)
   ```
2. Matérn-5/2 ARD exact GP 每折使用 8 个确定性优化初值；
3. 保存每折 fitted kernel、LML、warning、boundary collision 与 optimizer status；
4. training-only 比较 feature A/B/C；
5. PCE 基准改为 degree-2/3 Legendre/Chebyshev total-degree basis；
6. power target 从 `log1p(P)` 改为 training-frozen `log(P+floor)`；
7. 保存逐点 OOF truth/prediction/std/error/fold/region；
8. frozen validation 仍未访问；
9. 未运行新的 FEM、angle DOE 或 inversion。

测试与可复现性证据可以保留。

---

## 3. 修正前后结果的正确解释

### 3.1 Aggregate 已显著改善

原始 M3 的 exact GP p95 absolute errors 约为：

```text
R = 0.554
T = 0.388
A = 0.328
```

M3R 选定 `exact_gp:features=B` 后：

| target | NRMSE | p95 absolute | p95 relative when truth>=1e-2 | max absolute |
|---|---:|---:|---:|---:|
| R_total | 0.01253 | 0.01346 | 0.2651 | 0.04571 |
| T_total | 0.01171 | 0.01555 | 0.03799 | 0.04636 |
| A_balance | 0.01994 | 0.02379 | 0.04441 | 0.04748 |

因此不能再写成“GP 完全失败”。更准确的结论是：

```text
global range-normalized shape = mostly learned
local worst-case / p95 inversion accuracy = not yet qualified
```

三个 NRMSE 已接近或达到 0.02 hard threshold，但 p95 absolute 与 relative Gate 仍明显失败。现在的主要问题是局部覆盖，而不是最初的目标变换或优化器完全失效。

### 3.2 误差集中区域

选定模型的 region evidence 表明：

- low-grazing 和 cutoff 邻域承担最大的 aggregate absolute errors；
- high-azimuth 也有局部高误差；
- geometry extremes 的 T 误差较小；
- interior 的绝对误差通常低于最坏边界/截止区域。

所以主动加点必须是训练驱动、区域多样的，不能再均匀随机增加 8 点。

### 3.3 主要功率通道并非同等失败

例如：

```text
reflection m=0 outgoing S:
    NRMSE = 0.02404
    p95 abs = 0.03616

transmission m=0 outgoing S:
    NRMSE = 0.006365
    p95 abs = 0.007315
```

说明强透射通道已经具有较好的全局趋势，而强反射和弱通道仍需改善。把 21 个通道统一写成“同一种失败”会掩盖它们的物理和数值差别。

---

## 4. 在主动加点前必须完成的 M3S 修正

这些修正只使用现有 96 个 training，不得访问 frozen validation，不得运行 FEM。

### M3S-1：冻结 selected feature B 的真实生产合同

M3R 已选定：

```text
features B = [height_scaled, width_scaled, grazing_scaled, azimuth_scaled]
```

但当前 `transform_features()` 与 `FEATURE_CONTRACT.json` 顶层仍默认描述历史 feature A。必须：

1. 生成 `FEATURE_CONTRACT_v2.json`；
2. 明确 selected feature B；
3. acquisition、最终 fit、model package 和 CLI 只能从 model manifest 读取 feature identity；
4. 禁止隐式回退到 A；
5. 保留 A/C 为 training-only rejected candidates。

### M3S-2：修正 top/bottom power-carrying mask 语义

当前 `analytic_power_mask()` 对 reflection 与 transmission 使用同一个 air-side criterion。Task001 已证明有损 bottom medium 中：

```text
dispersion classification
!=
positive finite-port Poynting power identity
```

必须使用正式 forward policy 分别计算：

```text
top air order status
bottom complex-substrate order status
```

要求：

1. 在 96 training、16 validation inputs（只允许读取 inputs，不读取 targets）和 4096 candidate pool 上计算独立 analytic mask；
2. training mask 必须逐项一致；
3. validation/candidate 只生成输入侧 mask，不读取响应；
4. 保存 `POWER_MASK_AUTHORITY.json`；
5. 若旧、正确 mask 在 candidate pool 上有差异， acquisition 与模型输出必须使用正确版本。

### M3S-3：完成 fixed-order power 的物理重构合同

当前 CV 对每个 channel 独立预测 `log(P+floor)`，但没有在 OOF 评估中执行 target contract 声明的 sidewise physical reconstruction。因此“21 个通道全部失败”仍是 raw independent-channel 结果，不是最终物理 power surrogate 的完整结论。

必须增加并比较以下有限候选，不得扩展为 model zoo：

#### P1：现有独立 log-power diagnostic

保留为基准，不作为最终 ledger-qualified 输出。

#### P2：side-total + masked channel fractions

1. aggregate 模型提供 predicted R/T；
2. 对 reflection/transmission 各自的 active channels 建模 fraction；
3. 使用固定轴上的 masked softmax / centered log-ratio 重构；
4. inactive channel 返回 null；
5. active fractions 非负且每侧和为 1；
6. reconstructed order powers 每侧严格和为 predicted R/T。

所有 OOF power metrics 必须对**最终 reconstructed powers**计算，同时报告 reconstruction 前后的误差。

### M3S-4：功率通道分级，但不得删除负证据

保留当前 21-channel metrics 原样。另建立 training-only 的输出分级：

```text
Tier P-primary:
    可测、对总功率或未来反演有实质贡献的通道

Tier P-secondary:
    max power 约 1e-6--1e-4 或只在少量点激活的弱通道

Tier structural-null:
    analytic inactive
```

建议初始 P-primary 规则：

```text
training max power >= 1e-4
and active training count >= 24
```

另可加入由 training-only sensitivity/information 排名选中的通道。规则、通道列表和理由必须在看 validation 前冻结。

不得把 P-secondary 从输出中删除；只能明确标记其资格级别与不同的 absolute-error 语义。当前 `max>=1e-6` 的 21 通道报告继续保留为审计证据。

### M3S-5：有限的最终 training-only 模型闭合

在运行新 FEM 前，只允许再比较两个有限选项：

```text
G1 = current constant-mean Matérn-5/2 ARD exact GP
G2 = degree-2 orthogonal training trend + Matérn-5/2 ARD residual GP
```

对 G1/G2 仅允许以下固定 jitter：

```text
1e-10, 1e-8, 1e-6
```

所有比较继续使用原五折 split 和 feature B。不得增加其他 kernel、神经网络、随机森林或 SVR。

若 G2/有限 jitter 没有实质改善，冻结 G1；不得继续无边界调参。

### M3S-6：不确定度只作为 acquisition ranking，不作为已校准物理不确定度

当前 pooled aggregate 95% OOF coverage 为 0.882，低于 nominal 0.95。必须增加：

- R/T/A 分别的 coverage；
- low-grazing/cutoff/high-azimuth/interior coverage；
- standardized residual quantiles；
- training-only multiplicative calibration factor。

由于两个 latent GP 独立训练，当前 delta-method 忽略 zR/zT covariance。最终 uncertainty package 尚不能资格化，但经过 OOF scaling 后可以用于第一轮 acquisition ranking。

---

## 5. 第一轮主动加点授权

完成 M3S 并通过 checker 后，批准**一轮、恰好 8 个**新 FEM training points。

### 5.1 候选池与禁区

只允许使用冻结的 4096 candidate pool：

```text
candidate tuple hash = a9831ffc1055732660bee859382f623e8558560634d9ac98702cfe355ff09fcd
```

必须排除：

- 现有 96 training；
- 16 frozen validation tuples；
- 8 discretization-audit tuples；
- 重复/过近候选；
- 域外和 grazing=0°。

### 5.2 acquisition score

使用 training-only 的固定组合：

```text
aggregate calibrated GP uncertainty
+ OOF absolute-error surrogate
+ nearest-training distance in feature B
+ cutoff proximity
+ primary-power uncertainty/error contribution
```

必须做 maximin/diversity 约束，避免 8 点全部堆在一个窄角度区域。建议至少覆盖：

- low-grazing；
- cutoff neighborhood；
- high-azimuth；
- 一个 interior high-error region；
- 不同 h/w 几何位置。

先生成并提交：

```text
ACTIVE_LEARNING_ROUND1_PLAN.json
```

其中包含每个候选的输入、各 score 分量、最近训练距离、mask topology、选择理由和与 validation/audit 的 disjoint assertion。

### 5.3 FEM 合同

8 个点必须使用精确 Case119 forward identity：

```text
source SHA = 10e3356ba8364286a452077f71d7e3b92ea24cd5
model = S_PROD_FULL3D_STATIC_P5_H10_NY4
route = full3d_static_uniform_n1curl_p5_h10_ny4
mesh = (6,4,14)
MPI2 / thread1
```

在隔离 clean clone/worktree 中逐点运行，并通过 Case119 相同的：

```text
residual
energy closure
n!=0 leakage
fixed/raw ledger
runtime topology
zero swap
cleanup
compact identity
```

首个未解释 FEM failure 立即停止，不得跳过。

### 5.4 Round-1 结束边界

建立新的 training dataset version：

```text
training = 104
frozen validation = same sealed 16
```

保存 96->104 learning-curve 对照，并用新的 hash-bound 104-point folds 重跑 M3S 模型。

- 若 aggregate hard Gate 与冻结 P-primary hard Gate 全部通过：允许创建 `MODEL_SELECTION_LOCK.json`，随后按原 Task003 合同一次性解封 validation；
- 若仍未通过：停止等待 Review V2，不得自行执行 round 2/3；
- frozen validation 在 round-1 CV 结束前继续封存。

---

## 6. 需要同时修复的代码一致性问题

1. `targets.aggregate_composition()` 当前返回列数与其 docstring/合同不一致；必须统一为 dataset/API 所需的明确 R/T/A（及可选 A_volume diagnostic）布局，并加 shape test。
2. `transform_features()` 不得继续静默返回 rejected feature A。
3. power OOF 必须调用正式 physical reconstruction 并执行 `physics_audit()`。
4. candidate selection 不得将 aggregate-selected family/feature 无审计地强制用于所有 power channels；至少对 P-primary 做 training-only P1/P2 比较。
5. final model manifest 必须分别声明 aggregate、P-primary、P-secondary、complex-amplitude 的 qualification status。

---

## 7. 当前禁止事项

仍然禁止：

- 读取 frozen-validation targets；
- 创建虚假的 model lock；
- 放宽 aggregate hard Gate；
- 将弱通道静默删除；
- 修改 16 个 validation tuples；
- 使用 Ny3、p4 或 Hybrid 数据；
- 运行 round 2/3；
- angle DOE；
- inversion、MCMC 或 Bayesian posterior；
- 修改 production FEM identity。

---

## 8. 交付

完成后至少提交：

```text
surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/
    outcomes/m3s_contract_completion.md
    outcomes/active_learning_round1.md
    outcomes/training_cv_104.md
    outcomes/learning_curve_96_to_104.md
    response_v3.md

benchmarks/cases/121_task003_active_learning_round1/
    README.md
    config.json
    expected.json
    records/
    checker.py
```

然后停止等待 Task003 Review V2，除非 104 点模型已通过全部规定 Gate并按合同完成一次性 frozen validation。