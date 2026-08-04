# Task005 Review Report V1：M0–M4 条件验收、DOE lock 语义修正与 M5R 无新 FEM 闭合

## 1. 审阅结论

本轮正式批准保留并接受：

```text
M0 frozen 16-angle design and nominal reuse             = approved
M1 coarse/half finite-difference audit                  = approved
production steps delta_h=1.25 nm, delta_w=0.25 nm      = approved
M2 16-angle perturbation FEM campaign                   = approved
M2 raw immutable sensitivity dataset                    = approved as forward-data authority
M3 Fisher matrices and exhaustive 1–4 angle enumeration = approved as provisional DOE evidence
M4 three-angle off-centre recovery                      = approved
Case131 / Case132 / Case133 independent checkers        = pass
93 / 93 new FEM attempts                                = measured_pass
resource / residual / energy / topology / ledger Gates = pass
```

但本轮仅**条件接受**当前：

```text
outcomes/DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json
status = frozen_review_pending
```

它还不能升级为最终批准的 DOE lock，也不能据此直接开始下一结构代理任务。原因不是 FEM 结果错误，而是最终科学与数据合同尚有三个无须重算 FEM 的缺口：

1. 任务书要求的 M2 弱通道排名稳定性尚未形成正式审计；
2. “最佳 pair / triple / quadruple”与“下一阶段采用哪个照明集合”的语义没有完全分开，5% 少照明规则未真正实现；
3. M2 不可变数据包虽包含完整原始响应和 `derivatives.json`，但缺少任务书明确要求的若干便携派生数组。

因此当前正式状态冻结为：

```text
forward_solver_sha             = fdf961545f217d620e22800f2704ae9913a6d270
implementation_sha             = d24395b377259da129a81384f88d8a4ad74602d2
nominal_dataset                = task004_angle_nominal_p5_ny4_train112_v1
sensitivity_dataset            = task005_discrete_angle_hw_sensitivity_p5_ny4_v1
angle_count                    = 16
new_FEM_count                  = 93
selected_steps                 = delta_h=1.25 nm, delta_w=0.25 nm
best_pair                      = A05 + A07
M4_validated_triple            = A05 + A07 + A09
information_best_quad          = A05 + A06 + A07 + A09
current_lock_status            = frozen_review_pending
required_next_stage            = M5R derived-only final-lock correction
new_FEM_budget                 = 0
Task006                        = not yet authorized
formal inversion               = not performed
```

本轮停止不是计算卡死。Task005 已按任务书完成 M0–M4，并正确等待审阅。下一步只允许执行 M5R；不得重跑已有 93 个 FEM，也不得开始新的几何训练集。

---

## 2. 可正式接受的数值与工程成果

### 2.1 冻结角度和 nominal reuse 合格

16 个候选角度 A00–A15 均在 Task004 不可变 `train112` 中恰好出现一次；中心几何：

```text
h0 = 120 nm
w0 = 17 nm
```

没有重复运行 nominal FEM。Case131 已独立核对角度 tuple、固定物理身份、nominal source/config hashes、扰动域与 Task004 关闭边界。

该处理避免了：

- 中心点重复计算；
- 不同 forward SHA 混源；
- Ny3、p4、Hybrid 或 P 入射数据混入；
- Task004 blind24 被意外访问。

### 2.2 有限差分步长审计合格

M1 在五个代表角度：

```text
A00 = (0.5 deg, 0 deg)
A07 = (2 deg, 90 deg)
A09 = (4 deg, 60 deg)
A14 = (10 deg, 0 deg)
A15 = (10 deg, 90 deg)
```

比较了：

```text
coarse: delta_h=2.5 nm, delta_w=0.5 nm
half:   delta_h=1.25 nm, delta_w=0.25 nm
```

40/40 fresh-process Full3D 状态均为 `measured_pass`。M0 aggregate 与 M1 robust order-total 在 N1 下，h/w 的 whitened cosine、relative-L2、dominant-channel sign 和 signal Gate 均达到任务要求，最终选择 half steps。

N2 中个别 half-step signal-floor 诊断未通过不构成本任务步长失败，因为任务书冻结的生产资格是 N1 mandatory，N2 为保守诊断；这一边界必须继续在最终报告中明确，不能写成“N1/N2 全部步长 Gate 均通过”。

### 2.3 M2 全 16 角度灵敏度 FEM 合格

生产状态数：

```text
16 angles x 4 perturbation states = 64
20 exact reuse from M1
44 new M2 FEM
```

所有 raw records 绑定同一个：

```text
Full3D static uniform N1curl p5/h10/Ny4
mesh = (6,4,14)
MUMPS ICNTL(14)=40
MPI2 / thread1
observable = task002.fixed-n0-orders.v3
```

Case132 从 raw arrays 和 records 重建 M0/M1/M2 中央差分，核对 hashes、状态重用、通道 identities、mask、残差、能量与资源信息，结果通过。

因此 `task005_discrete_angle_hw_sensitivity_p5_ny4_v1` 可作为后续派生计算的唯一 forward-data authority；M5R 不得修改其现有文件或 hashes。

### 2.4 Fisher 数学核心正确且范围清楚

当前实现使用物理导数：

\[
J_{h,w}=\begin{bmatrix}\partial y/\partial h & \partial y/\partial w\end{bmatrix},
\]

以及参数尺度：

\[
\theta_h=(h-120)/5,\qquad \theta_w=(w-17)/1,
\]

构造：

\[
F=J_\theta^T\Sigma^{-1}J_\theta.
\]

程序精确穷举：

```text
16 singles
120 pairs
560 triples
1820 quadruples
```

并排除 aggregate/order 重复计数：

```text
M0 = [R_total,T_total], A only audit
M1 = robust active order-total powers, threshold 1e-3
M2 = extended active order-total powers, threshold 1e-5
```

N1/N2 都含绝对噪声底。该 Fisher 结果可以作为 local DOE 指标，但仍必须标注：

```text
provisional diagonal noise scenarios
not experimental covariance calibration
not achieved metrology uncertainty
not Bayesian posterior
```

### 2.5 Task001 基准保留是正确的

历史基准：

```text
A14 = (10 deg,0 deg)
A15 = (10 deg,90 deg)
```

没有被删除或重新命名。最新结果显示该 pair 在 M0 aggregate 场景下仍可满秩且条件较好；其 robust worst-case 主要被 M1/N2 拉低，因为在 `1e-3` robust-order 合同下，每个角度仅保留很少可测通道，两个参数方向接近退化。

因此 Task005 结果不应写成“Task001 判断错误”，而应解释为：

> Task001 的局部结论依赖当时的输出/噪声合同；Task005 使用非冗余、绝对底噪和 robust-channel 筛选后，A14+A15 对可测 order-total 的稳健性不足。

最终 closeout 应增加这一解释，避免不同任务的 Fisher 数字看起来互相矛盾。

### 2.6 M4 非线性局部恢复通过

冻结三角度：

```text
A05 = (2 deg,0 deg)
A07 = (2 deg,90 deg)
A09 = (4 deg,60 deg)
```

在三个离中心几何：

```text
G1 = (118.75,16.75) nm
G2 = (121.25,17.25) nm
G3 = (118.75,17.25) nm
```

共 9/9 Full3D FEM 通过。M1/N1 主 Gate 的恢复误差为：

| geometry | |height error| | |width error| |
|---|---:|---:|
| G1 | 0.036023 nm | 0.001204 nm |
| G2 | 0.035285 nm | 0.000986 nm |
| G3 | 0.005661 nm | 0.000085 nm |

均明显低于：

```text
height <= 0.5 nm
width  <= 0.1 nm
```

这证明 nominal Jacobian 在这三个规定几何和该三角度组合下具有良好的局部非线性恢复能力。

但它仍不是正式反演验证：

- 测试响应来自同一前向模型；
- 没有加入随机实验噪声；
- 没有材料、模型差异或测量系统误差；
- 只覆盖三个规定几何；
- 没有构造 Bayesian posterior。

---

## 3. 当前 DOE lock 不能直接最终批准的原因

### 3.1 缺少 M2 排名稳定性审计

任务书明确要求：

```text
rank separately for M0/M1/M2 and N1/N2
report whether ranking changes under M2 extended weak channels
```

当前 `FISHER_COMBINATION_RANKING.json` 确实保存了每个组合的 M2/N1/N2 `scenario_results`，但正式 robust ranking key 只使用：

```text
M0 x N1/N2
M1 x N1/N2
```

M2 没有进入推荐准则，这是合理的，因为 M2 弱通道只应作为诊断；问题在于目前没有形成正式报告回答：

- M2 单独最优 pair/triple/quad 是什么；
- A05+A07+A09 在 M2/N1 与 M2/N2 中的排名；
- M2 top-k 与 robust M0/M1 top-k 的重合度；
- 弱通道是否改变关键角度选择；
- 若改变，改变是否由接近绝对噪声底的通道驱动。

在上述审计完成前，不能声称推荐组合已满足任务书全部 M3 合同。

### 3.2 “信息最优”与“M4 已验证”必须分开

当前按 M0/M1、N1/N2 的 worst-case minimum eigenvalue：

| size | best set | worst minimum eigenvalue |
|---:|---|---:|
| 1 | A05 | 12.882983 |
| 2 | A05+A07 | 23.781704 |
| 3 | A05+A07+A09 | 34.768648 |
| 4 | A05+A06+A07+A09 | 45.149335 |

因此：

```text
triple vs pair improvement ≈ 46.2%
quad vs triple improvement ≈ 29.9%
```

它们不属于“信息指标相差 5% 以内”的 tie。当前代码的排序 key 只在前述指标完全相同时才用组合长度作为 tie-break，并没有真正实现任务书中的 5% fewer-illumination rule。

同时，任务书 M4 又明确要求选择一个三角度集合做非线性验证。因此当前三角度集合应被准确称为：

```text
best robust three-angle set
+ only nonlinearly validated set
+ recommended operational three-angle compromise
```

而不能不加限定地称为：

```text
globally information-optimal illumination set
```

最终 lock 必须同时保留：

```text
best pair                     = A05+A07
M4-validated recommended triple = A05+A07+A09
information-best quadruple    = A05+A06+A07+A09
```

并明确：三角度被选作下一阶段默认照明，是基于任务书固定的 M4 三角度验证、实验成本和已有非线性证据；四角度仍是局部 Fisher 信息上界参考，尚未做同等 off-centre validation。

### 3.3 M2 不可变数据包缺少任务书规定的便携派生数组

当前 raw immutable package 已保存：

```text
angles.npy
nominal_inputs.npy
nominal_aggregates.npy
perturbed_aggregates.npy
nominal_order_powers.npy
perturbed_order_powers.npy
nominal_order_mask.npy
perturbed_order_mask.npy
derivatives.json
order_identity.json
record_identity.json
```

这些足以从原始数据重建导数，因此 forward evidence 是完整的。

但任务书还明确要求至少保存：

```text
perturbed_inputs.npy
Dh arrays by contract
Dw arrays by contract
channel identities and tiers
noise sigma arrays N1/N2
```

这些目前没有作为 hash-bound arrays 显式列入 `M2_DATASET_MANIFEST.json`。

不能修改已经标记为 immutable 的 v1 raw package。应从现有 arrays/JSON 确定性生成一个 companion derived supplement，并绑定原 package hashes。该修正不需要任何新 FEM。

### 3.4 Hash 与 covariance 命名需要消歧

当前文件中同时存在：

```text
angle_tuple_sha256
point_tuple_sha256
design_file_sha256
recommended_triple_hash
```

它们可能分别对应二维角度、完整四元组、ID 列表或整个设计文件。最终 lock 必须为每个 hash 明确：

```text
hash input schema
ordering
rounding
是否含 h/w
是否含 angle ID
```

恢复与 Fisher 结果中的 `covariance_scaled` 也需要明确其参数化。最终派生报告应分别给出：

```text
covariance_theta
covariance_physical_nm
CRLB_theta
CRLB_physical_nm
```

不得只依靠字段名猜测尺度。

---

## 4. Required M5R：不运行新 FEM 的最终闭合

M5R 只读取现有不可变数据、Fisher JSON、recovery JSON 和任务书；不得启动 forward solver。

### 4.1 M2 ranking-stability audit

新增：

```text
outcomes/M2_RANK_STABILITY_AUDIT.json
outcomes/M2_RANK_STABILITY_AUDIT.md
```

至少包含：

1. M2/N1 和 M2/N2 分别的 best single/pair/triple/quad；
2. M2 在 N1/N2 worst-case 下的 best single/pair/triple/quad；
3. A05、A05+A07、A05+A07+A09、A05+A06+A07+A09 的 M2 ranks；
4. 对每个 size，robust M0/M1 ranking 与 M2 ranking 的：
   - top-10 overlap；
   - top-20 overlap；
   - Spearman 或 Kendall rank correlation（只在共同 full-rank 集合上）；
5. 推荐三角度在 M2 下是否仍位于合理 top-k；
6. M2 新增弱通道的数量、nominal power 范围和 sigma 范围；
7. 明确 M2 仅为 diagnostic，不得反向覆盖 robust M0/M1 选择。

若 M2 排名变化很大，必须指出哪些弱通道驱动变化，而不是静默宣布稳定。

### 4.2 Illumination-count tradeoff audit

新增：

```text
outcomes/ILLUMINATION_COUNT_TRADEOFF.json
outcomes/ILLUMINATION_COUNT_TRADEOFF.md
```

必须真正实现任务书的 5% 规则，并分别冻结：

```text
best_single
best_pair
best_triple
best_quad
information_global_best
M4_nonlinearly_validated_set
recommended_operational_set_for_next_task
```

推荐 operational triple 可继续为 A05+A07+A09，但必须明确理由：

- 它是 best robust triple；
- 它已完成规定的三几何非线性恢复；
- 相比 quad 少一次照明；
- quad 信息更高且不在 5% tie 内，因此 triple 不是 global information optimum；
- quad 留作后续成本—信息对照，而不是被删除。

### 4.3 M2 derived supplement

不得改写原 v1 raw package。新增 companion package，例如：

```text
benchmarks/artifacts/cases/132_task005_sensitivity_dataset/
    derived_contract_v1/
```

至少包含：

```text
perturbed_inputs.npy               shape (16,4,4)
M0_Dh.npy / M0_Dw.npy              fixed aggregate channels
M1_derivatives.npz                 ragged-safe values + channel IDs per angle
M2_derivatives.npz                 ragged-safe values + channel IDs per angle
M0_noise_sigma_N1.npy / N2.npy
M1_noise_sigma_N1.npz / N2.npz
M2_noise_sigma_N1.npz / N2.npz
channel_contracts.json
source_record_ids.json
DERIVED_SUPPLEMENT_MANIFEST.json
```

允许采用等价的明确 schema，但必须：

- 从原 v1 arrays 和 JSON 确定性重建；
- 不读取新的 FEM；
- 不改写原 v1 hashes；
- 每个导数和 sigma 可由独立 checker 重算；
- inactive channels 保留 mask/null 语义，不填成普通零。

### 4.4 Baseline interpretation addendum

新增：

```text
outcomes/TASK001_BASELINE_INTERPRETATION_ADDENDUM.md
```

至少分开报告 A14+A15 的：

```text
M0/N1
M0/N2
M1/N1
M1/N2
M2/N1
M2/N2
```

并解释 Task001 与 Task005 结论差异来自：

```text
observable contract
robust-channel threshold
absolute noise floor
non-redundant measurement representation
```

不得写成某一历史结果“虚假”或“被推翻”，除非有直接数值证据证明当时实现错误。

### 4.5 Covariance / hash interpretation addendum

新增：

```text
outcomes/FISHER_PARAMETERIZATION_AND_HASH_SCHEMA.md
```

明确：

```text
J physical units
J scaled units
Fisher parameterization
covariance_theta
covariance_physical
CRLB unit
all tuple/hash input schemas
```

现有 v1 结果不删除；若字段名不准确，新派生文件中使用无歧义名称并给出映射。

### 4.6 Final DOE lock V2

在上述 checker 全部通过后，新增而不是覆盖：

```text
outcomes/DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json
```

至少包含：

```text
status = review_ready
raw sensitivity dataset identity and hashes
derived supplement identity and hashes
forward solver SHA
16-angle exact tuple schema/hash
production h/w steps
M0/M1/M2 and N1/N2 contracts
M2 ranking-stability conclusion
best pair / best triple / best quad
M4-validated operational triple
5% count-tradeoff result
Task001 baseline interpretation
physical/scaled Fisher and covariance semantics
three off-centre recovery records
explicit provisional-noise warning
formal_inversion = false
Task006_authorized = false
```

V1 lock 保留为历史，不得删除或原地修改。

### 4.7 Case134 independent checker

建立：

```text
benchmarks/cases/134_task005_final_lock_review/
```

checker 必须独立核验：

- 原 M2 raw package hashes 未变化；
- M2 rank audit 可从 Fisher ranking JSON 重算；
- top-k overlap/rank correlation 可重算；
- 5% illumination-count rule 可重算；
- supplement arrays 可从 raw arrays/records 重建；
- sigma 与 noise contract 一致；
- lock V2 与所有输入 hashes 一致；
- no new FEM / no Task004 blind / no formal inversion；
- V1 lock 仍在且未改写。

输出：

```text
records/case134_check.json
outcomes/test_summary_v2.md
response_v2.md
```

---

## 5. M5R 之后的项目路线

### 5.1 当前立即执行的下一步

```text
M5R derived-only final-lock correction
new FEM = 0
```

完成后停止等待 Review V2。不得在同一轮开始 Task006。

### 5.2 Review V2 通过后的推荐下一任务

建议建立独立 Task006：

```text
fixed-illumination nonlinear h/w surrogate and inversion readiness
```

默认照明采用经过 M4 非线性验证的：

```text
A05 = (2 deg,0 deg)
A07 = (2 deg,90 deg)
A09 = (4 deg,60 deg)
```

其前向映射应为：

\[
(h,w)\longrightarrow \mathbf y_{A05,A07,A09},
\]

而不是恢复任意连续角度代理。

Task006 应重新建立：

- 二维 h/w space-filling 训练设计；
- 独立 blind validation；
- M0 与 M1 primary measurement contracts；
- M2 仅作弱通道诊断；
- nonlinear surrogate 与 Jacobian/Fisher 对照；
- 噪声下 recovery / Bayesian inversion readiness。

但 Task006 当前尚未授权，必须等待 M5R 和 Review V2。

---

## 6. Codex 执行指令

```text
请执行 git pull --ff-only，并完整阅读：

1. surrogate_tasks/AGENTS.md
2. surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/task.md
3. surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/response_v1.md
4. surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/review_report_v1.md

严格执行 Required M5R。

本轮不得运行任何 FEM，不得改变 forward solver SHA，不得改写原 M2 raw
immutable package、V1 DOE lock、Task004 train112 或 blind24。

必须完成：

- M2 ranking-stability audit；
- illumination-count 5% tradeoff audit；
- M2 derived supplement；
- Task001 baseline interpretation addendum；
- Fisher parameterization/hash schema；
- DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json；
- Case134 independent checker；
- response_v2.md。

完成后提交并推送当前唯一代理分支，然后停止等待 Review V2。

不得开始 Task006、正式 surrogate training、Bayesian inversion 或任何新 FEM。
```
