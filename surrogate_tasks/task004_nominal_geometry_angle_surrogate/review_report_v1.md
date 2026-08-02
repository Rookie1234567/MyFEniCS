# Task004 Review Report V1：首个基线锚点停止、MUMPS 工作区修正与二维角度代理重启要求

## 1. 审阅结论

本轮批准保留 Task004 已完成的设计、代码骨架和受控停止证据，但**不批准把当前结果解释为前向模型失效，也不批准直接开始 96 点训练 campaign**。

当前正式状态冻结为：

```text
Task004 M0 design                         = provisionally approved and retained
Task004 clean-SHA forward qualification  = failed before first official result
failure classification                   = MUMPS workspace underestimation, retryable only under reviewed ladder
training FEM                             = 0 / 96
blind-validation FEM                     = 0 / 24
surrogate training                       = not started
ANGLE_MODEL_SELECTION_LOCK               = absent
Task003 Round3                           = forbidden
Task003 frozen validation                = sealed and untouched
formal Fisher angle ranking              = forbidden
geometry inversion                       = forbidden
```

下一步不是修改物理模型、换网格、降低有限元阶次，也不是放宽残差或能量 Gate；下一步是执行本报告规定的：

```text
M0R = solver provenance + angle-pipeline correctness hardening
M1R = deterministic MUMPS workspace qualification
M2R = five-anchor forward requalification
M3R = 16-angle canary, then 96-angle training campaign
```

只有 M2R 五个锚点全部通过，才允许进入 M3R。

---

## 2. 本轮实际完成了什么

### 2.1 已完成并可保留

Task004 已冻结：

| design | count | status |
|---|---:|---|
| structured + enrichment training angles | 96 | response-blind, not measured |
| independent blind-validation angles | 24 | sealed, not measured |
| active-learning candidate pool | 4096 | response-blind |
| clean-SHA anchors | 5 | first point attempted, then controlled stop |

训练和 blind validation 没有精确 tuple 交集；enrichment 只使用角度坐标、解析 cutoff margin、低掠射标签和空间填充距离，没有读取 FEM response。该设计思路可以保留。

Task004 还建立了：

```text
src/surrogate/angle/
Case123 design/checker skeleton
AngleSurrogate.predict(grazing_deg, azimuth_deg) skeleton
finite candidate families: local RBF / Chebyshev / Matérn-5/2 GP
```

这些实现尚未经过真实 Task004 数据测试，当前只能称为代码骨架，不能称为已资格化代理。

### 2.2 没有完成

当前没有任何 Task004 official response：

```text
training measured = 0
validation measured = 0
aggregate model fitted = no
power model fitted = no
spatial holdout = not run
blind validation = not run
angle maps = not generated
```

因此本轮不能评价二维角度代理的误差、样本量、模型优劣或是否能够预测任意角度。

---

## 3. 首个锚点为什么停止

首个锚点为：

```text
height_nm  = 120
width_x_nm = 17
grazing    = 0.5 deg
azimuth    = 0 deg
S incident
Full3D static uniform N1curl p5/h10/Ny4
MPI2 / one thread per rank
```

执行到 augmented Fourier-DtN 系统的 MUMPS numerical factorization 时停止：

| field | value |
|---|---:|
| PETSc error code | 76 |
| MUMPS INFOG(1) | -9 |
| MUMPS INFO(2) | 919260 |
| process-tree peak RSS | 5,690,605,568 bytes |
| peak swap | 0 bytes |
| true residual | not measured |
| R/T/A | not measured |
| formal record | absent |

MUMPS `INFOG(1)=-9` 的标准含义是：numerical factorization 使用的内部 real/complex work array `S` 太小。正的 `INFO(2)` 给出报错时仍缺少的 entries 数。这里缺少约 919,260 个 complex entries；按 complex128 的裸数据量估计约为 14 MiB，但实际重新分配开销不能只按这个裸值判断。

这与以下错误不同：

```text
-13 / -19：请求或允许的总内存本身不足
-10：数值奇异
```

因此当前证据不支持以下结论：

```text
该角度物理上无解
矩阵奇异
16 GB 内存一定不足
Ny4/p5 前向模型退化
```

正确分类应为：

```text
retryable_mumps_workspace_underestimate
```

但必须通过显式、可审计的 workspace ladder 重试，不能简单重复同一命令碰运气。

---

## 4. 为什么这不是新的前向数值回归

前一 measured-pass reference SHA 为：

```text
dd8b89dda86081992e8f758279ab77dd0ae602f8
```

当前失败 baseline SHA 为：

```text
7fe366304023c32bf2e8ddcacdb2ada9996d3e7c
```

这两个 SHA 之间仅修改：

```text
src/surrogate/angle/design.py
```

没有修改：

```text
Maxwell weak form
mesh
N1curl element
Floquet constraints
DtN auxiliary system
static condensation
MUMPS/PETSc factorization code
R/T/A postprocess
```

因此，不能把这次 `-9` 归因于新角度代理代码改变了前向矩阵。它更符合 MUMPS symbolic estimate 对 numerical pivoting/fill-in 留出的 workspace margin 不足，或正式运行没有显式冻结该 margin 的情形。

当前 production direct path 的另一个明显弱点是：

- `mumps_ooc` 和 `mumps_blr` profile 显式设置 `mat_mumps_icntl_14 = 80`；
- ordinary/default MPI-MUMPS production path 只选择 `mumps`，没有显式冻结 `ICNTL(14)`。

这使同一离散模型的 factorization robustness 依赖 MUMPS 默认 workspace margin，而该参数又没有进入 Task002/Task004 config identity。

---

## 5. Required M0R：前向求解与 provenance 加固

### 5.1 显式 MUMPS workspace 参数

为 Task004 所调用的 Ny4/p5 production route 增加显式、记录在案的 MUMPS workspace 参数。

不得直接把 OOC 或 BLR 变成 production 默认。首先使用 ordinary in-core MUMPS，仅改变：

```text
mat_mumps_icntl_14
```

执行顺序冻结为：

```text
40：两个独立 fresh-process attempts
若任一 attempt 出现 -9，则停止 40，转 80
80：两个独立 fresh-process attempts
若任一 attempt 出现 -9，则停止 80，转 120
120：最多两个独立 fresh-process attempts
```

选择规则：

1. 取能够连续两次完成 full solve 且通过全部 numerical Gates 的最小值；
2. 若 40 连续两次通过，可以冻结 40；
3. 若 40 不稳定而 80 连续两次通过，冻结 80；
4. 若 120 仍出现 `-9`，受控停止，不得继续无限增加；
5. 任一 attempt 出现 swap、资源 watchdog stop、`-13/-19` 或系统可用内存危险，立即停止 ladder。

每次 attempt 必须是新进程、新 run directory，旧失败记录不得覆盖。

### 5.2 不允许隐藏 PETSc option

每次 attempt 必须保存：

```text
requested PETSc option dictionary
KSP prefix
actual factor solver type
actual ICNTL(14)
MUMPS INFO/INFOG/RINFOG memory and factor statistics when available
matrix rows / NNZ / ownership
ordering and pivot-related options
PETSC_OPTIONS environment value
peak RSS/PSS/USS and swap
```

必须证明 `mat_mumps_icntl_14` 真正被 prefixed KSP 消费，而不是作为 unused option 被忽略。

### 5.3 solver options 必须进入 config identity

`task002_full3d_config_identity(...)` 当前没有绑定 direct-solver profile 和 PETSc/MUMPS option。修正后至少加入：

```json
"linear_solver": {
  "ksp_type": "preonly",
  "pc_type": "lu",
  "factor_solver": "mumps",
  "direct_solver_profile": "default",
  "mat_mumps_icntl_14": 40,
  "mat_mumps_icntl_22": 0
}
```

其中数值按最终冻结值填写。

必须增加测试：

```text
ICNTL(14)=40 与 ICNTL(14)=80 的 config_sha256 不相同
formal execution record 能重建同一个 solver identity
隐藏的全局 PETSc option 不得静默覆盖正式身份
```

旧 Task003/Case119 dataset 保持原身份，不得回写或重新标记。Task004 使用新的 solver/config/source identity，从头生成自己的数据。

### 5.4 failure 分类

增加明确分类：

```text
failed_direct_lu_workspace_underestimate
failed_direct_lu_memory_limit
failed_direct_lu_numerical_singularity
failed_direct_lu_other
```

`INFOG(1)=-9` 不再只记录成笼统的 `failed_direct_lu_exception`。

---

## 6. Required M0R：clean-SHA anchor checker 加固

当前 `qualify.py` 需要在重跑锚点前修正。

### 6.1 order identity 必须逐项一致

比较旧、新 mother response 前，必须断言每个 order 的：

```text
side
m
n
component order
```

完全一致。不得只使用 `zip(...)` 后默认顺序正确。

### 6.2 null/mask identity 必须一致

若旧记录中某通道为 non-power-carrying/null，而新记录为 power-carrying，或反之，必须直接失败。不能因为某一侧 `power is None` 就跳过比较。

必须比较：

```text
power_carrying mask
dispersion_propagating identity
fixed order axis
```

### 6.3 完整数值身份

anchor identity 至少比较：

```text
model_id
solver_route_id
uniform N1curl p5 element signature
axis_cell_counts = [6,4,14]
topology_element_hash
observable schema v3
parameter schema
assembly backend
MUMPS workspace identity
MPI2/thread1
source SHA and clean status
```

### 6.4 原 Gate 保持不变

五个 anchor 的 shared observables 仍要求：

```text
max |delta aggregate| <= 1e-10
max |delta shared order power| <= 1e-10
max |delta shared complex component| <= 1e-9
true residual <= 1e-9
|R + T + A_volume - 1| <= 1e-7
n!=0 leakage Gate passed
zero swap
cleanup complete
```

MUMPS workspace 参数只改变内存预留，不应改变数学解；若 observable 超过这些 Gate，必须调查，不能以“solver setting changed”放宽数值闭合。

---

## 7. Required M0R：Task004 角度代理代码修正

由于目前尚未生成 Task004 数据，现在正是修正训练代码的最低成本阶段。下列问题必须在正式 96 点 campaign 前处理。

### 7.1 power OOF 存在 truth leakage

当前 `_power_oof(...)` 在测试 fold 中把真实 FEM：

```text
aggregates[test, :3]
```

传给 power reconstruction。这样 channel power 的 OOF 评价使用了测试点真实 R/T side total，不是端到端代理预测。

必须改为：

```text
aggregate OOF prediction
+
analytic power-carrying mask
+
predicted channel fractions
```

然后评价最终 channel power。

### 7.2 mask agreement 不能写死

当前：

```text
mask_agreement = True
```

必须替换为真实检查：

```text
analytic mask from angle and material authority
vs
FEM dataset mask
```

训练集要求 100% 一致；不一致点必须单列，不得进入模型资格化。

### 7.3 OOF nearest distance 目前恒为零

当前对每个 OOF 点使用全部 angles（包含它自己）计算最近训练距离，因此结果恒为零。

必须按每个 fold 使用：

```text
nearest distance from test point to that fold's training rows only
```

主动学习和误差解释不得使用包含自身的距离。

### 7.4 region 必须是独立/可重叠标签

当前单一优先级：

```text
low_grazing > high_azimuth > cutoff_near > ordinary
```

会把同时属于 low-grazing 和 cutoff-near 的点只计入 low-grazing，导致 cutoff holdout 不完整。

必须建立独立布尔 mask：

```text
is_low_grazing
is_high_azimuth
is_cutoff_near
is_ordinary_interior
```

spatial holdout 分别用各自的真实 mask；报告允许同一点出现在多个困难区域统计中。

### 7.5 nearest-neighbour fraction 只能是 baseline

当前 `FractionPowerModel` 实际是：

```text
取最近训练角度的 channel fractions
按预测 R/T 重新归一化
```

它可以保留为 `power_baseline_nearest_fraction`，但不能作为最终 production power surrogate，原因包括：

- 新开启的通道可能在最近训练点仍为 inactive；
- cutoff 两侧可能复制错误的 fraction topology；
- 返回的 power uncertainty 被写成全零；
- 无法满足“带预测不确定度”的正式接口。

正式候选保持有限，只新增一个物理约束模型：

```text
per-side active-channel fraction surrogate
=
analytic mask-topology partition
+
additive-log-ratio / centered-log-ratio representation
+
Matérn-5/2 GP 或 local RBF（由 training-only CV 选择）
+
sidewise softmax reconstruction
```

必须保证：

```text
sum reflection channel powers = predicted R
sum transmission channel powers = predicted T
inactive channels = null, not numeric zero
power uncertainty is measured/derived, never hard-coded zero
```

### 7.6 uncertainty Gate 不能是自我校准后必然通过

当前使用同一组 OOF standardized residual 计算 inflation factor，再在同一组 OOF 上检查校准 coverage，容易形成近似自洽 Gate。

必须至少报告：

```text
per-target uncalibrated OOF coverage
per-target calibrated OOF coverage
per-region coverage
standardized residual p50/p90/p95/max
calibration factor per target
```

最终可信度由一次性 blind validation 判断，训练阶段不得声称 uncertainty 已最终校准。

### 7.7 model lock 必须 fail closed

`fit_final_model(...)` 必须显式拒绝：

```text
training_gate != true
spatial_holdout_gate != true
power_gate != true
```

模型锁还必须绑定：

```text
dataset file hashes
training tuple hash
selected feature/output transform
model family/kernel/jitter
power model identity
fold seed and optimization seeds
training code SHA
solver/config/source identity
uncertainty calibration
```

### 7.8 dataset checker 加固

dataset builder 不能只从第一条记录读取 source SHA。必须逐条验证：

```text
single source SHA
single config hash
single solver workspace identity
single model/route/element/topology/observable identity
measured_pass
all numerical Gates
exact fixed geometry
exact design coverage
```

`fixed_geometry` 字段统一使用 `width_x_nm`。

validation loader 必须要求一个已存在且 hash 匹配的 `ANGLE_MODEL_SELECTION_LOCK.json`，不能仅凭函数调用约定读取 sealed targets。

### 7.9 design metadata 修正

当前 design schema 仍名为：

```text
task002.m3r-design.v1
```

应改为 Task004 专用 schema。

16 个 enrichment point 不能全部标记为同一个 `cutoff_low_grazing_enrichment`；每点保存真实多标签和选择原因。

anchor 与 training 的预期 overlap 应显式记录；当前无操作的 `if ...: pass` 应删除或改成真实检查。

角度 tuple 本身可保持不变；修正 metadata 后重建 hash-bound design package，并证明所有 `(grazing, azimuth)` tuple 与本轮冻结设计完全一致。

---

## 8. Required M1R：MUMPS workspace 定向诊断

只在完成 M0R、提交新的 clean implementation SHA 后执行。

固定原失败点：

```text
(120 nm, 17 nm, 0.5 deg, 0 deg, S)
```

运行本报告第 5.1 节的 40/80/120 ladder。

每次必须保存：

```text
attempt index
requested and actual ICNTL(14)
matrix identity
MUMPS INFO/INFOG/RINFOG
KSP/factor inventory
full true residual
R/T/A/A_volume
orders and leakage
wall time and stage timing
peak RSS/PSS/USS/swap
```

禁止：

```text
重复同一失败 attempt 并覆盖目录
在 ladder 中换网格、p、MPI 或物理参数
直接切换 OOC/BLR 以绕过原因
放宽 residual/energy/leakage Gate
```

M1R 只有在某个 ICNTL(14) 值连续两个 fresh-process full solves 全部通过时完成。

---

## 9. Required M2R：五锚点重新资格化

冻结 M1R 选出的 workspace identity，运行原五个 anchor：

```text
(0.5, 0)
(0.5, 90)
(10, 0)
(10, 90)
(5.25, 45)
```

全部通过第 6.4 节 Gate 后，建立：

```text
TASK004_FORWARD_BASELINE_v2.json
```

其中必须区分：

```text
old mathematical/discretization reference = Case119 Ny4/p5
new execution identity = same discretization + explicit MUMPS workspace margin
```

若任一 anchor observable 与旧 reference 不闭合，停止等待 Review V2。

---

## 10. Required M3R：训练数据 campaign

M2R 通过后，先从 96 点 training design 中运行 16 个 canary：

- 覆盖 domain edges/corners；
- 覆盖 low-grazing；
- 覆盖 high-azimuth；
- 覆盖 cutoff-near；
- 覆盖 ordinary interior；
- 至少包含 4 个 enrichment points。

16/16 全部 measured-pass 后，可在同一执行轮继续剩余 80 个 training angles。

遇到第一个非 workspace、非已解释环境类 failure，立即停止；不得跳点。

### blind validation 的执行顺序修订

24 个 blind-validation tuple 继续冻结，但**不要在模型锁之前运行其 FEM**。推荐顺序：

```text
96 training FEM
-> training-only dataset/checker
-> CV + spatial holdout
-> optional one round <=16 active-learning FEM
-> training Gate passed
-> create immutable ANGLE_MODEL_SELECTION_LOCK
-> only then run 24 blind-validation FEM
-> evaluate once
```

这样可以从执行层面避免 validation response 被提前读取。

若 96 点未通过且满足任务书主动学习条件，最多增加一轮 16 点；112 点仍未通过则停止，不得自行继续第二轮。

---

## 11. 本轮批准与禁止事项

### 批准

```text
保留 Case123 frozen angle tuples
保留当前 -9 failure evidence
执行 M0R code/provenance fixes
执行 M1R MUMPS workspace ladder
M1R 通过后执行 M2R five anchors
M2R 通过后执行 M3R training campaign
```

### 不批准

```text
把 -9 解释成角度物理无解
直接重跑全部96点
改变 p5/Ny4/mesh/physics
混入 Ny3 或 Task003 variable-geometry samples
读取 Task003 frozen validation
提前运行或读取 Task004 blind validation responses
Fisher angle ranking
height/width sensitivity surrogate
inversion
P incident or wavelength expansion
```

---

## 12. Codex 下一轮交付

下一轮至少提交：

```text
benchmarks/cases/124_task004_mumps_workspace_and_anchor_requalification/
    config.json
    expected.json
    checker.py
    records/

surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes/
    mumps_workspace_ladder.md
    forward_baseline_v2.md
    angle_pipeline_static_corrections.md
    design_rebind.md
    test_summary_v2.md
    TASK004_FORWARD_BASELINE_v2.json

response_v2.md
```

若 M2R 未通过，`response_v2.md` 在失败处停止，不得生成训练数据。

若 M2R 通过并完成 M3R，则额外交付 training dataset、training-only CV、spatial holdout 和（仅在模型锁后）blind-validation 结果。

---

## 13. 给 Codex 的直接执行摘要

```text
请完整阅读 Task004 review_report_v1.md。

先执行 M0R，不得直接恢复96点 campaign：

1. 为 Ny4/p5 production route 增加显式、hash-bound 的 MUMPS ICNTL(14)；
2. 将 solver options 写入 config/formal/dataset identity；
3. 加固 anchor comparer、dataset checker 和 failure classification；
4. 修正 Task004 power OOF truth leakage、hard-coded mask agreement、
   OOF nearest-distance=0、互斥region标签、零power uncertainty和model-lock guard；
5. 保持所有冻结 angle tuples 不变，只重建 metadata/source/config hashes。

提交新的 clean SHA 后，在原失败锚点执行 ICNTL(14)=40/80/120 的受控 ladder，
每个候选值需连续两个 fresh-process full solves 通过。

冻结最小稳定值后运行5个 clean-SHA anchors，并与Case119 Ny4/p5 reference比较。

只有5/5 anchors全部通过，才运行16点training canary；16/16通过后可继续剩余80点。

blind-validation FEM必须等ANGLE_MODEL_SELECTION_LOCK建立后再运行。

任何未解释 numerical failure 立即停止，不得跳点。
```
