# Task004 Review Report V3：二维角度代理首轮训练失败审阅、资格层拆分与局部/拓扑感知路线

## 1. 审阅结论

本轮批准保留 Task004 M4A、M4B、M4C 的全部实现、不可变 `train96` 数据包、交叉验证结果和负结果证据，但**不批准创建 `ANGLE_MODEL_SELECTION_LOCK.json`，不批准立即运行 16 个主动学习 FEM，也不批准运行 24 个 blind-validation FEM**。

当前正式状态冻结为：

```text
forward_solver_sha                         = fdf961545f217d620e22800f2704ae9913a6d270
training_dataset_id                        = task004_angle_nominal_p5_ny4_train96_v2
training_rows                              = 96
blind_validation_rows_measured             = 0 / 24
training_dataset_identity                  = approved_and_immutable
global_stationary_GP                       = not_qualified
aggregate_angle_surrogate                  = not_qualified_but_viable
order_resolved_power_surrogate             = not_qualified
cross_fitted_uncertainty_pipeline          = implemented_and_retained
ANGLE_MODEL_SELECTION_LOCK                 = absent
immediate_active_learning_FEM              = not_authorized
Required_next_stage                        = M4E_model_structure_revision_on_train96
conditional_one_round_active_learning      = M4F_at_most_16_angles
formal_Fisher_angle_ranking                = forbidden
geometry_sensitivity / inversion           = forbidden
Task003_Round3 / frozen_validation          = forbidden / sealed
```

本轮失败不应解释为：

```text
二维角度响应无法代理
96个Ny4/p5数据不可信
有限元前向模型失败
角度域必须增加到数百或数千点
```

更准确的解释是：

> 固定几何下的二维角度响应在大部分区域具有良好的局部可插值性，但完整角度矩形同时跨越低掠射、Rayleigh cutoff、不同传播通道组合和高方位角边界。当前单一全局、平稳 Matérn GP 需要用一套相关长度同时描述这些区域，发生了明显的模型形式折中。与此同时，当前资格合同把“总体 R/T/A”“各衍射级功率”“有训练支撑的域内插值”和“整条边界区域外推”绑定为一次全通过，掩盖了已经取得的部分成功。

因此，下一轮先改变**代理结构与资格层级**，不先机械追加 FEM 数据。

---

## 2. 本轮可正式接受的成果

### 2.1 `train96` 数据包通过

不可变训练包：

```text
dataset_id = task004_angle_nominal_p5_ny4_train96_v2
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
sample_count = 96
fixed geometry = h=120 nm, w=17 nm
angle domain = grazing 0.5–10 deg, azimuth 0–90 deg
forward model = Full3D static uniform N1curl p5/h10/Ny4
MUMPS ICNTL(14) = 40
```

独立 Case125 checker 已确认：

- 96 个角度与冻结设计逐点一致；
- 单一 clean forward SHA；
- 单一 model/route/observable identity；
- 全部样本 `measured_pass`；
- 所有 numerical/resource Gates 通过；
- training 与 blind-validation tuple 不相交；
- blind-validation response 未运行、未访问；
- dataset builder SHA 与 forward solver SHA 已分开记录。

因此不得重跑、原地改写或混入其他 SHA/网格/阶次的数据。

### 2.2 训练与验证隔离通过

本轮没有运行或读取 24 个 blind-validation FEM，没有访问 Task003 的 frozen validation，也没有创建模型锁。当前 blind validation 仍然保持真正的 response-blind 状态。

### 2.3 物理重构合同通过

总体响应继续使用：

\[
z_R=\log\frac{R+\epsilon}{A+\epsilon},\qquad
z_T=\log\frac{T+\epsilon}{A+\epsilon},
\]

并通过 `softmax(z_R,z_T,0)` 恢复，保证：

\[
R,T,A\ge0,\qquad R+T+A=1.
\]

各衍射级功率的 OOF 已改为：

```text
fold内训练的aggregate模型给出R/T
+ fold内训练的active-channel fraction模型
+ 解析power-carrying mask
```

没有使用 test-fold 的真实 R/T。当前：

```text
mask agreement = 100%
maximum sidewise power-ledger error = 2.22e-16
truth leakage = false
```

这些实现应保留。

### 2.4 cross-fitted uncertainty 流程通过

代表 GP 的 R/T/A 经验覆盖率约为：

```text
R = 0.9271
T = 0.9583
A = 0.9479
```

进入冻结的 0.90–0.99 区间。该结果证明 cross-fitted 校准流程可以工作，但校准放大系数较大，说明原始全局 GP 存在明显模型失配；当前不确定度只能用于模型比较、困难区域识别和候选排序，不能解释为完整物理或实验不确定度。

---

## 3. 训练失败的定量含义

### 3.1 全局 Matérn GP 未通过 aggregate Gate

本轮用于代表失败结果的 production candidate 为：

```text
Matérn-5/2 ARD exact GP
feature = F3（角度 + signed cutoff margins）
jitter = 1e-6
```

其关键结果包括：

| 输出 | NRMSE | p95 abs | max abs | 状态 |
|---|---:|---:|---:|---|
| `R_total` | 未通过统一 Gate | 见完整 CV | `0.14197` | fail |
| `T_total` | 接近但未通过 | `0.01437` | 见完整 CV | fail |
| `A_balance` | `0.04139` | `0.02466` | `0.14322` | fail |

冻结 Gate 为：

```text
NRMSE <= 0.01
p95 absolute <= 0.01
max absolute <= 0.03
```

其中 `A_balance` 是最主要瓶颈。由于 composition 强制

\[
A=1-R-T,
\]

局部 R/T 误差会在 A 上合并；这不是能量不守恒，而是局部 R/T 插值误差的累积表现。

### 3.2 local RBF 提供了“局部可插值”的正证据

local RBF baseline 的总体响应分数优于所有 production GP：

```text
local-RBF selection score = 4.4861
best representative GP score = 4.9507
```

其 R/T 的 OOF 指标已达到或接近 Task004 aggregate Gate，A 仍未完全通过。该结果说明：

> 训练数据并非完全不足，二维响应面的大部分区域可以被局部方法捕捉；主要矛盾是全局平稳核在不同物理区域之间折中，而不是“二维函数不可学习”。

local RBF 目前缺少可信的原生预测方差，所以不能直接按旧合同锁定为 production model；下一轮应为局部模型建立独立、交叉拟合的 conformal uncertainty，而不是因为它没有 GP 标准差就永久排除。

### 3.3 order-resolved power 比 aggregate 更难

当前 primary channel Gate 为 `0/5` 通过。典型结果：

```text
reflection m=0, outgoing S:
    NRMSE = 0.2070
    p95 abs = 0.001742

reflection m=-1, outgoing S:
    NRMSE = 0.2056

transmission m=-1, outgoing S:
    p95 abs = 0.01438
```

这说明即便总反射/总透射大致正确，能量在不同衍射级之间的分配仍可能明显错误。严格功率账本只能保证：

\[
\sum_j P_j^R=R,\qquad \sum_j P_j^T=T,
\]

不能保证每个 `P_j` 都准确。

因此，从本轮起必须区分：

```text
Level A = aggregate angle surrogate（R/T/A）
Level B = order-resolved angle surrogate（各衍射级功率）
```

允许未来出现：

```text
aggregate_qualified = true
order_resolved_qualified = false
```

Level B 的失败不得继续自动否定 Level A 已达到的研究价值，但公开接口必须明确返回各层资格状态。

---

## 4. 对传播拓扑覆盖的正式更正

最新 `MASK_TOPOLOGY_COVERAGE.json` 是本轮权威。它表明：

```text
train96 observed mask signatures = 8
blind24 unseen signatures relative to train96 = 0
all five CV folds have test-signature support in their fold training rows
candidate4096 rare unseen signatures = 7
rare unseen candidate count = 38 / 4096 ≈ 0.93%
```

因此需要更正此前可能形成的错误印象：

- 训练集不是只覆盖 2 种 topology；
- 24 个 blind-validation 角度没有训练集未见 topology；
- 当前 training CV 失败不能归因于 validation topology 缺失；
- 4096 candidate pool 中确实存在 7 种极少见、靠近传播边界的 unseen topology。

当前 API 对这些 rare unseen signatures 必须继续 fail closed：

```text
status = unsupported_mask_topology
```

在未增加对应 FEM 支撑前，不得宣称完整角度矩形内“任意角度”的 order-resolved 输出全部已资格化。

对于 aggregate R/T/A，这些 topology 变化仍会造成局部非平稳性，但输出维数本身不改变；因此 aggregate 与 order-resolved 的拓扑要求应分开处理。

---

## 5. spatial holdout 失败应怎样解释

当前冻结窗口中：

```text
low_grazing       training_support_count = 0
high_azimuth      training_support_count = 0
cutoff_near       training_support_count = 0
ordinary_interior training_support_count = 8
```

这说明前三个窗口实际上是：

> 删除整条边界/困难区域后，从其他区域向其外推的压力测试。

它们不等价于“训练点包围下的域内局部插值测试”。这些结果仍然重要，因为它们证明模型不能跨整条低掠射带、高方位角边界或 cutoff 带可靠外推；但不能与 ordinary-interior 小洞插值使用完全相同的 hard Gate。

下一轮必须拆分：

```text
supported_interpolation_windows = hard Gate
region_extrapolation_stress_tests = advisory / warning Gate
```

已有三个边界压力窗口不得删除或改写；保留为 advisory evidence。另行 response-blind 冻结具有周边训练支撑的局部窗口作为正式插值 Gate。

---

## 6. Required M4E：只用现有 train96 修订模型结构

M4E 不运行新的 FEM，不访问 blind validation，不改变 train96。

### 6.1 冻结新的资格层级

建立：

```text
ANGLE_AGGREGATE_QUALIFICATION_CONTRACT.json
ANGLE_ORDER_QUALIFICATION_CONTRACT.json
```

Aggregate Level A 的目标：

```text
(grazing, azimuth) -> R_total, T_total, A_balance, uncertainty
```

Order Level B 的目标：

```text
(grazing, azimuth) -> fixed-order S/P powers, mask, uncertainty
```

二者分别给出 `qualified / not_qualified`，模型包和 API 不得用一个总布尔值掩盖不同层次。

### 6.2 冻结 supported interpolation windows v2

在不读取 response 的前提下，基于角度坐标、解析 cutoff margin、mask signature 和最近训练距离生成：

```text
SUPPORTED_INTERPOLATION_WINDOWS_V2.json
```

要求：

- 至少包含 low-grazing、high-azimuth、cutoff-near、ordinary-interior 四类；
- 每个窗口为有限大小的局部孔洞，而不是删除整条区域；
- 每个 holdout 点在其余训练数据中具有明确的一侧或周边支撑；
- 保存 window indices、tuple hash、support indices、nearest-support distance；
- 在任何模型拟合前冻结；
- 原 `SPATIAL_HOLDOUT_WINDOWS.json` 保留为 extrapolation stress authority。

### 6.3 只比较有限的局部/拓扑感知候选

禁止扩展为无边界 model zoo。M4E 只允许：

#### L1：local RBF + cross-conformal uncertainty

- aggregate composition latent 仍为 `zR,zT`；
- local RBF 只使用 fold-training rows；
- 邻居数仅比较固定集合，例如 `24/32/48`；
- smoothing 只比较预冻结的极小集合；
- 使用 outer-fold OOF residual 构造 target-wise、必要时 region-wise conformal interval；
- uncertainty 不能由同一测试残差同时校准和评分。

#### L2：local Matérn-5/2 exact GP

- 对每个 query 只使用最近 `24/32/48` 个 fold-training rows；
- 保持 ARD、确定性优化初值和显式 jitter；
- 保存每点使用的邻域、kernel、LML 和距离；
- 预测标准差进行 nested/cross-fitted 校准。

#### L3：topology-aware local experts

- 使用解析 mask signature 或 signed cutoff region 作 gating；
- 每个专家只使用同 topology 或同 cutoff 一侧的训练数据；
- cutoff 附近可使用预冻结的平滑 blending；
- 未见 topology 必须返回 unsupported；
- 不得根据 blind validation 调整区域边界。

#### L4：global low-order trend + local residual（可选）

- 全局 Chebyshev trend 只负责大尺度变化；
- local GP/RBF 学习残差；
- 仍需满足与 L1–L3 相同的 OOF 和不确定度合同。

不得新增神经网络、随机森林、SVR、大规模 kernel sweep 或 deep-learning 路线。

### 6.4 Aggregate Gate

Level A 维持：

```text
OOF NRMSE <= 0.01
OOF p95 absolute <= 0.01
OOF max absolute <= 0.03
supported interpolation windows p95 <= 0.02
R+T+A exact
cross-fitted 95% coverage in [0.90,0.99]
```

原 low-grazing/high-azimuth/cutoff 整区外推结果必须报告，但改为 advisory，不阻塞“有训练支撑的域内插值”资格。公开 API 在离训练支撑过远时必须返回 warning。

### 6.5 Order-resolved Gate

Level B 维持：

```text
mask agreement = 100%
sidewise ledger <= 1e-12
primary channel NRMSE <= 0.03
primary channel p95 absolute <= 0.01
inactive = NaN + false mask
unseen topology = unsupported
```

若 Level B 未通过，仍可继续评估和锁定 Level A，但模型包必须明确：

```text
order_resolved_qualified = false
```

且不得对未资格化 order 输出给出“可信预测”标签。

---

## 7. M4F：条件式一轮主动学习，最多 16 个 FEM

M4E 完成前不得运行新 FEM。

仅当以下条件同时满足时，才允许生成 `ACTIVE_LEARNING_ANGLE_ROUND1_PLAN.json`：

1. 至少一个 L1–L4 aggregate candidate 明显优于当前全局 GP；
2. 相对 local-RBF baseline，A 的 p95 或 max error 有实质改善，或提供了通过 cross-fitted 检验的可信 uncertainty；
3. OOF 高误差可定位到有限角度区域；
4. acquisition 不依赖 blind-validation response；
5. train96 与 candidate identity/checker 通过。

若用户目标仍是“完整矩形内任意角度”，16 点设计应同时处理精度和稀有 topology：

```text
7 points  = candidate pool中7种unseen mask signature各至少1个anchor
5 points  = A_balance及R/T最高cross-validated error / uncertainty热点
2 points  = supported interpolation holes
2 points  = low-grazing / high-azimuth / cutoff边界多样性
```

若某一 unseen signature 仅有极少 candidate，选择 response-blind maximin 代表点。一个 topology 只有一个 anchor 不足以证明 order-resolved 插值已资格化，因此这些区域在后续仍可保持 `sparse_topology_support` warning。

所有新增 FEM 必须使用固定只读 forward worktree：

```text
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
MUMPS ICNTL(14) = 40
Full3D p5/Ny4, MPI2/thread1
```

形成新的不可变：

```text
task004_angle_nominal_p5_ny4_train112_v1
```

不得原地覆盖 train96。

112 点训练后只允许重新执行一次 training-only qualification，并停止等待 Review V4。不得自行进行第二轮主动学习。

---

## 8. Blind validation 仍然禁止

只有在 aggregate Level A 的 training-only Gate 全部通过、并创建：

```text
ANGLE_AGGREGATE_MODEL_SELECTION_LOCK.json
```

之后，才允许使用固定 forward SHA 运行 24 个 blind-validation FEM。

若 order Level B 同时通过，可另建：

```text
ANGLE_ORDER_MODEL_SELECTION_LOCK.json
```

blind validation 只允许一次性评分；不得根据其结果重新选择模型、特征、邻域、区域边界、校准系数或主动学习点。

当前不批准运行 24 个 blind-validation FEM。

---

## 9. 交付要求

M4E 至少交付：

```text
benchmarks/cases/126_task004_local_topology_angle_surrogate/
    config.json
    expected.json
    checker.py
    records/

surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes/
    ANGLE_AGGREGATE_QUALIFICATION_CONTRACT.json
    ANGLE_ORDER_QUALIFICATION_CONTRACT.json
    SUPPORTED_INTERPOLATION_WINDOWS_V2.json
    model_structure_comparison.md
    aggregate_qualification.md
    order_qualification.md
    uncertainty_qualification.md
    topology_support.md
    active_learning_eligibility.md
    test_summary_v4.md

surrogate_tasks/task004_nominal_geometry_angle_surrogate/
    response_v4.md
```

所有比较必须使用同一 train96、同一固定 folds 或可重建的 nested folds、同一目标表示和同一误差指标。不得选择性省略失败区域或弱通道。

---

## 10. Codex 下一步指令

```text
请执行 git pull --ff-only，并完整阅读：

surrogate_tasks/task004_nominal_geometry_angle_surrogate/
review_report_v3.md

严格执行 Required M4E。

本轮不得运行任何新FEM，不得运行24个blind-validation点，
不得访问Task003 frozen validation。

必须：
1. 保持train96不可变；
2. 将aggregate与order-resolved资格拆分；
3. 冻结有训练支撑的local interpolation windows v2；
4. 保留原整区holdout为extrapolation stress evidence；
5. 只比较local-RBF+conformal、local Matérn GP、
   topology-aware local experts和可选global-trend+local-residual；
6. 使用nested/cross-fitted uncertainty，禁止校准/评分复用；
7. 生成aggregate/order两个独立qualification结果；
8. 生成ACTIVE_LEARNING eligibility，不得直接执行FEM。

只有M4E明确满足本报告第7节eligibility时，
后续才允许一轮最多16点的M4F；本轮先停止等待Review V4。

禁止第二轮active learning、Fisher、geometry sensitivity和inversion。
```

---

## 11. 最终审阅判断

当前最可信的结论是：

\[
\boxed{
\text{二维角度代理具有局部可行性，但当前单一全局平稳 GP 和一体化资格合同不合适。}
}
\]

下一步优先验证局部/拓扑感知模型能否在不增加数据的情况下，把 aggregate R/T/A 提升到筛选级精度；只有证明模型结构合理后，才使用 16 个 FEM 补齐误差热点和稀有传播 topology。
