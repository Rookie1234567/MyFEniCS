# Task004 Review Report V8：M4I 最终审阅、controlled-negative 闭合与离散角度 DOE 路线

## 1. 审阅结论

本轮批准并正式接受：

```text
M4I predictor-specific threshold correction       = approved
no-fallback / highest-acceptance quantile contract = approved
accepted-distribution conditional conformal        = approved
immutable train112 / frozen outer folds             = approved
response-blind candidate4096 / blind24 screening    = approved
Case130 independent checker                         = pass
Task004 selective aggregate result                  = controlled-negative, final
```

本轮不批准、且 Task004 后续不再申请：

```text
ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK = absent / permanently not authorized for Task004
ANGLE_AGGREGATE_MODEL_SELECTION_LOCK           = absent
ANGLE_ORDER_MODEL_SELECTION_LOCK               = absent
Task004 blind-validation FEM                   = 0/24, remain unmeasured
Task004 second active-learning round            = forbidden
any additional Task004 training FEM             = forbidden
additional Task004 model families / kernels      = forbidden
post-hoc Gate or threshold relaxation            = forbidden
formal Fisher / geometry inversion inside Task004 = forbidden
```

当前最终状态冻结为：

```text
forward_solver_sha                 = fdf961545f217d620e22800f2704ae9913a6d270
training_dataset_id                = task004_angle_nominal_p5_ny4_train112_v1
training_rows                      = 112
fixed_geometry                     = h=120 nm, w=17 nm
angle_domain                       = grazing 0.5-10 deg, azimuth 0-90 deg
forward_model                      = Full3D static uniform N1curl p5/h10/Ny4
MUMPS                              = ICNTL(14)=40, MPI2, thread1
full_domain_aggregate_status       = controlled_negative
selective_aggregate_status         = controlled_negative
order_resolved_status              = not_qualified
blind_validation_rows_measured     = 0 / 24
new_Task004_FEM_budget             = 0
Task004_status                     = closed_controlled_negative
recommended_next_task              = discrete-angle sensitivity and Fisher DOE
```

本轮停止不是程序卡死、内存不足、有限元失败或不确定度实现错误。Review V7 要求修正的阈值复用、fallback、quantile 选择和 accepted-distribution 区间校准均已完成；剩余失败是严格 cross-fitted accepted OOF 中仍存在真实的大点预测误差。因此，Task004 已达到预先约定的最终关闭条件。

---

## 2. 为什么现在可以接受 controlled-negative 为最终结论

### 2.1 Review V7 的实现缺口已经全部闭合

M4I 已完成：

1. 每个 predictor、每个 outer fold 独立拟合 source-only threshold；
2. source rows 没有通过候选时不再 fallback 为“通过”；
3. 在固定 quantile grid 中选择接受率最高的 source-Gate-passing quantile；
4. final quantile 在统一全 OOF normalization 下重建 production threshold；
5. interval 只由 source accepted rows 的 targetwise absolute residual finite-sample conformal quantile生成；
6. held-out truth 不参与本折 acceptance 或 interval calibration；
7. interval 采用 coverage lower bound 与 half-width sharpness Gate，不再以 coverage>0.99 作为安全失败。

两个 predictor 的条件区间均通过：

```text
coverage >= 0.90
p95 half-width <= 0.02
max half-width <= 0.03
finite and positive
```

因此，本轮失败不能再归因于旧的全域区间过于保守。

### 2.2 Q1 local Matérn k24 的真实 accepted-set 失败

Q1 + S1 的 cross-fitted accepted set 为：

```text
accepted = 92 / 112 = 0.821429
candidate pool accepted = 4013 / 4096
blind design preaccepted = 22 / 24
```

其 accepted OOF 结果：

| target | NRMSE | p95 abs | max abs | Gate |
|---|---:|---:|---:|---|
| R_total | 0.006426906 | 0.003352608 | 0.035889638 | max fail |
| T_total | 0.009335989 | 0.007049532 | 0.037588537 | max fail |
| A_balance | 0.016954577 | 0.008558446 | 0.067467046 | NRMSE/max fail |

一个代表性 accepted 大误差点为：

```text
grazing = 2.961689197458 deg
azimuth = 82.168203396723 deg
identity = old96
cutoff margin = 0.0026696040600640014
absolute errors = [0.035889638, 0.031577407, 0.067467046]
```

该点位于高方位角/cutoff 高曲率区域，但 S1 仍将其接受。这说明当前 response-blind risk signals 不能完全召回真实尾部误差。

### 2.3 Q2 latent median 的真实 accepted-set 失败

Q2 + S1 的 cross-fitted accepted set为：

```text
accepted = 91 / 112 = 0.812500
candidate pool accepted = 4013 / 4096
blind design preaccepted = 22 / 24
```

其 accepted OOF 结果：

| target | NRMSE | p95 abs | max abs | Gate |
|---|---:|---:|---:|---|
| R_total | 0.002600732 | 0.002724782 | 0.009456919 | pass |
| T_total | 0.007524943 | 0.005770360 | 0.037575777 | max fail |
| A_balance | 0.010323225 | 0.007004455 | 0.044913575 | NRMSE/max fail |

一个代表性 accepted 大误差点来自唯一主动学习轮次：

```text
grazing = 6.854549495038 deg
azimuth = 83.504671286792 deg
identity = new16
cutoff margin = 0.0019936217892752017
absolute errors = [0.007337798, 0.037575777, 0.044913575]
```

该点已经是专门针对困难区域增加的高保真样本，但当其在 outer fold 中作为未见测试点时，选择器仍未拒绝它。这是比“训练点数量略少”更强的证据：当前有限的局部预测器与 response-blind 风险信号组合无法可靠识别所有高方位角/cutoff 尾部。

### 2.4 不能继续通过同一 OOF 数据调阈值

M4I 之后若继续根据上述 accepted 大误差点：

```text
降低quantile
增加一个high-azimuth惩罚项
手工排除某几个角度
改变max-error Gate
删除A_balance
```

都会使用已经多轮审阅过的同一 OOF truth 继续优化选择器，形成明显的 training-evidence overfitting。即使随后在 training-only 指标上通过，也不能再被视为独立资格证据。

因此，Review V7 预先约定的规则应执行：M4I 失败后 Task004 以 controlled-negative 关闭，不运行 blind FEM。

---

## 3. Task004 已经获得的有效成果

Task004 的 controlled-negative 不等于没有成果。正式保留：

### 3.1 可靠的二维角度 FEM 数据集

```text
train96 + one active round 16 = train112
Full3D p5/Ny4
single forward SHA
all FEM measured_pass
zero unexplained numerical/resource failure
```

该数据集是后续角度研究、离散 DOE 和局部响应分析的权威来源。

### 3.2 MUMPS 鲁棒性修正

```text
mat_mumps_icntl_14 = 40
```

已纳入数值身份，并经独立 fresh-process 与 anchor 闭合验证。

### 3.3 主动学习 acquisition 证据

M4E2 acquisition 对 OOF 尾部具有可用排序能力，唯一 16 点主动学习确实降低了 local Matérn k24 的部分最大误差。该 acquisition 设计可作为今后其他 surrogate task 的参考，但不能继续用于 Task004 第二轮加点。

### 3.4 物理一致性代理框架

已实现并验证：

```text
R/T/A composition reconstruction
R+T+A=1
power-carrying mask authority
sidewise power ledger
train/validation isolation
immutable dataset and hash identity
nested/cross-fitted uncertainty
selective abstention audit
```

这些基础设施应复用到后续结构参数代理。

### 3.5 明确的困难物理区域

最高误差稳定集中在：

```text
high azimuth
Rayleigh/cutoff high-curvature neighborhoods
部分低掠射与cutoff叠加区域
少量局部coverage holes
```

这说明未来不应再要求一套统一的角度连续代理覆盖完整矩形并同时达到高精度。

---

## 4. Task004 最终交付与关闭要求

Codex 下一轮只执行文档和状态闭合，不运行模型或 FEM：

建立：

```text
TASK004_FINAL_STATUS.json
TASK004_CONTROLLED_NEGATIVE_CLOSEOUT.md
```

其中必须冻结：

```text
Task004_status = closed_controlled_negative
full-domain model lock = absent
selective model lock = absent
order model lock = absent
blind24 FEM = intentionally_not_run
train112 dataset = retained authority
no additional Task004 FEM or model tuning authorized
```

同时更新 Task004 README/summary，使任何后续智能体不会把：

```text
Case130 checker pass
```

误读为：

```text
surrogate qualification pass
```

Case130 的 `status=pass` 只表示证据与 fail-closed 流程正确；科学资格为 controlled-negative。

---

## 5. 推荐的下一步：新建离散角度灵敏度与 Fisher DOE 任务

Task004 的原目标是建立：

```text
(grazing, azimuth) -> R/T/A at nominal geometry
```

但最终反演真正需要的是：

```text
∂response/∂h
∂response/∂w
```

以及多角度组合能否区分高度与宽度。一个角度的 nominal R/T/A 预测很准，并不自动表示它适合反演。

因此下一步不应继续修复任意角度代理，而应新建独立任务，例如：

```text
Task005: discrete illumination sensitivity and Fisher DOE
```

### 5.1 目标

在有限、明确、可直接由 FEM 验证的角度集合中，寻找最适合区分：

```text
height h
width w
```

的单角度、双角度或多角度组合。

### 5.2 角度候选

优先从 train112 中选择已有 nominal FEM 的角度，避免重新计算中心几何。建议冻结 12-20 个离散候选，覆盖：

```text
普通内部稳定区
低掠射但非灾难性尾部
中等方位角
少量高方位角作为对照
cutoff两侧但避免最强不稳定点
```

候选选择可以使用现有 nominal FEM 响应与物理区域标签，但必须在任何 h/w 扰动 FEM 运行前冻结。

### 5.3 每个候选的几何扰动

中心点：

```text
h0 = 120 nm
w0 = 17 nm
```

建议第一版中央差分：

```text
h- = 117.5 nm
h+ = 122.5 nm
w- = 16.5 nm
w+ = 17.5 nm
```

名义点若已在 train112 中则直接复用。每个候选只需新增四个 FEM：

```text
(h-, w0)
(h+, w0)
(h0, w-)
(h0, w+)
```

若冻结 16 个角度，总新增预算约为：

```text
16 x 4 = 64 FEM
```

该预算比继续构建全域角度代理更直接服务于反演目标。

### 5.4 灵敏度与 Fisher

对每个角度计算：

\[
\frac{\partial \mathbf y}{\partial h}
\approx
\frac{\mathbf y(h_+,w_0)-\mathbf y(h_-,w_0)}{h_+-h_-},
\]

\[
\frac{\partial \mathbf y}{\partial w}
\approx
\frac{\mathbf y(h_0,w_+)-\mathbf y(h_0,w_-)}{w_+-w_-}.
\]

建立 Jacobian：

\[
J=[\partial\mathbf y/\partial h,\ \partial\mathbf y/\partial w],
\]

并在明确的测量噪声模型下计算：

\[
F=J^T\Sigma^{-1}J.
\]

至少报告：

```text
rank(J)
condition number
minimum singular value
det(F) / logdet(F)
minimum eigenvalue of F
predicted h-w correlation
single-angle and multi-angle rankings
```

### 5.5 输出选择

第一层优先使用实验上最容易获得的：

```text
R_total
T_total
selected strong diffraction orders
```

A_balance 可由 R/T 得到，不应作为完全独立测量重复计权。弱到实验不可测的通道不得因为数值灵敏度大就自动进入 Fisher。

### 5.6 后续代理路线

在选出 2-4 组正式照明后，再建立：

```text
(h,w) -> responses at fixed selected illuminations
```

的二维结构参数代理。将来扩展到 5-6 个结构参数时，也应保持角度为固定测量配置，建立：

```text
(structural parameters) -> multi-angle response vector
```

而不是再次把所有结构参数与连续角度共同放入一套全局代理。

---

## 6. 给 Codex 的下一步指令

```text
请执行 git pull --ff-only，并完整阅读：

surrogate_tasks/task004_nominal_geometry_angle_surrogate/
review_report_v8.md

本轮只完成 Task004 controlled-negative closeout：

1. 建立 TASK004_FINAL_STATUS.json；
2. 建立 TASK004_CONTROLLED_NEGATIVE_CLOSEOUT.md；
3. 更新 Task004 README/summary 的最终状态；
4. 保留 train112、Case124-130 和全部 negative evidence；
5. 明确 Case130 checker pass != surrogate qualification pass；
6. 明确 blind24 intentionally not run；
7. 不得运行任何 FEM、模型训练、阈值调整或 blind validation。

完成 closeout 后停止。

不得在未经新任务书审阅的情况下执行 Task005 FEM。
下一项建议工作是另建 Task005：
discrete illumination sensitivity and Fisher DOE。
```

---

## 7. 最终判断

Task004 已证明：

```text
固定几何的二维角度响应在多数局部区域可较准确预测，
但完整0.5-10 deg x 0-90 deg矩形中存在少数稳定复现的
high-azimuth/cutoff尾部；现有response-blind风险信号不能可靠拒绝全部尾部。
```

因此正式结论为：

```text
full-domain angle surrogate      = controlled-negative
selective angle surrogate        = controlled-negative
order-resolved angle surrogate   = not qualified
blind validation                 = intentionally not run
```

这不是代理模型研究的总体失败，而是明确了一个重要架构结论：

> 后续应将“角度选择”改为有限角度的直接灵敏度/Fisher DOE，并在选定照明下建立结构参数代理，而不再追求覆盖完整连续角域的统一代理。
