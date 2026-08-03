# Task004 Review Report V2：批准 96 点前向数据，冻结二维角度代理训练、主动学习与盲验证合同

## 1. 审阅结论

本轮批准保留并正式接受 Task004 已完成的 M0R、M1R、M2R 和 M3R 前向资格化结果。

当前正式状态冻结为：

```text
forward_execution_sha                   = fdf961545f217d620e22800f2704ae9913a6d270
production_forward_model                = S_PROD_FULL3D_STATIC_P5_H10_NY4
solver_route                            = full3d_static_uniform_n1curl_p5_h10_ny4
mesh                                    = (Nx,Ny,Nz)=(6,4,14)
element                                 = uniform N1curl p5
MUMPS ICNTL(14)                         = 40
MUMPS workspace qualification           = 2/2 fresh-process pass
clean-SHA forward anchors               = 5/5 pass
Task004 training FEM                    = 96/96 measured_pass
Task004 blind-validation FEM            = 0/24, sealed and not run
ANGLE_MODEL_SELECTION_LOCK              = absent
surrogate training/CV                   = authorized after Required M4A corrections
conditional active-learning budget      = at most 16 new angles
formal Fisher angle ranking             = forbidden
geometry sensitivity / inversion        = forbidden
Task003 Round3 / frozen validation       = forbidden / sealed
```

结论分为两部分：

1. **前向数据阶段已通过。** 不得重跑或废弃现有 96 个合格 Ny4/p5 角度样本，也不得再次更改 MUMPS 工作区、网格、阶次或前向物理身份。
2. **代理训练阶段尚未开始。** 当前代码仍有若干训练/验证合同不闭合问题；必须先完成 M4A 静态修正和不可变 training-only dataset，之后才允许进行 training-only CV。

本报告条件授权：

```text
M4A = angle training/validation pipeline hardening
M4B = immutable 96-row training dataset + independent checker
M4C = training-only model comparison, OOF and spatial holdout
M4D = at most one 16-angle active-learning round, only if eligibility Gates pass
M5  = model lock followed by 24 blind-validation FEM, only if training Gates pass
```

任何阶段出现未解释的前向数值失败、数据身份混源、validation target 提前访问或模型锁条件不满足时，必须立即停止。

---

## 2. 本轮已批准的前向证据

### 2.1 MUMPS workspace 已闭合

原 `(grazing,azimuth)=(0.5°,0°)` 的 `INFOG(1)=-9` 已确认属于 MUMPS numerical-factorization workspace underestimate，而不是矩阵奇异或角度物理无解。

在新 clean SHA 下：

```text
mat_mumps_icntl_14 = 40
ordinary in-core MUMPS
MPI2 / one thread per rank
```

两个独立 fresh-process full solve 均通过：

| attempt | requested / actual ICNTL(14) | true residual | energy closure | swap |
|---:|---:|---:|---:|---:|
| 1 | 40 / 40 | 2.8504e-11 | 1.0900e-12 | 0 |
| 2 | 40 / 40 | 2.8504e-11 | 1.0900e-12 | 0 |

因此 `40` 是当前最小、经过两次独立运行证明稳定的正式值；不得无理由运行 80/120，也不得改为 OOC/BLR。

### 2.2 五个 forward anchors 已闭合

新执行身份与 Case119 Ny4/p5 参考在五个角度上闭合：

```text
(0.5,0), (0.5,90), (10,0), (10,90), (5.25,45)
```

最大差异：

```text
aggregate R/T/A            <= 1.17e-14
shared fixed-order power   <= 1.17e-14
shared complex amplitude   <= 1.65e-14
```

所以显式 ICNTL(14)=40 只提高求解鲁棒性，没有改变 Maxwell 解、衍射级结果或 observable 定义。

### 2.3 96 个训练角度全部通过

```text
training canary = 16/16 measured_pass
full training   = 96/96 measured_pass
numerical fail  = 0
resource stop   = 0
swap            = 0
```

每个样本均通过：

```text
completed direct solve
true residual <= 1e-9
energy closure <= 1e-7
fixed-order schema complete
complete n=0 power window
n!=0 leakage Gate
raw/fixed R/T ledger
uniform N1curl identity
actual runtime topology matches plan
compact-output identity
zero swap and cleanup complete
```

training index 0 的一次 `interrupted_retryable` 发生在 PDE 前，原因是错误解释器；其 fresh baseline attempt 已从头通过，不属于数值失败，也没有进入 dataset。

### 2.4 设计身份保持不变

以下 angle tuples 均保持与 Task004 初始设计相同，只重新绑定了 clean forward SHA：

| design | count |
|---|---:|
| training | 96 |
| blind validation | 24 |
| candidate pool | 4096 |
| forward anchors | 5 |

training 与 validation 无 tuple 交集；validation response 尚未运行、尚未读取。

---

## 3. 前向 SHA 与代理代码 SHA 必须分离

这是下一轮最重要的 provenance 规则。

当前 96 个 FEM 样本的正式来源是：

```text
forward_execution_sha = fdf961545f217d620e22800f2704ae9913a6d270
```

M4A 修改的是 `src/surrogate/angle/`、dataset/checker 和训练代码，提交后当前分支 HEAD 必然变化。不得把新 HEAD 冒充已有 96 个样本的 forward source，也不得为了取得单一 SHA 而重跑 96 个 FEM。

从本轮开始，所有记录必须明确区分：

```text
forward_solver_sha
surrogate_training_code_sha
```

规则如下：

1. 96 个已有 training FEM 永久绑定 `fdf9615...`；
2. 后续最多 16 个 active-learning FEM 和 24 个 blind-validation FEM 也必须运行同一个 `fdf9615...` forward execution identity；
3. 可建立一个只读、干净、固定在 `fdf9615...` 的独立 git worktree，仅用于 FEM execution；
4. 该 worktree 禁止开发、提交和推送；当前活动分支继续用于代理代码开发；
5. 模型包和模型锁必须同时保存：
   - `forward_solver_sha = fdf9615...`
   - `surrogate_training_code_sha = M4A/M4C 最终 clean HEAD`
   - dataset hashes、design hashes、solver/config/topology identities；
6. 当前 `fit_final_model(...)` 不得再把 dataset 的 `source_sha` 同时写成 training-code SHA。

任何后续 FEM 若由新的代理代码 HEAD 直接运行并记录为新 source SHA，将造成 dataset 混源，必须拒绝。

---

## 4. Required M4A：训练与验证管线硬化

M4A 不运行新的 FEM，不读取 blind validation response。

### 4.1 建立两个不可变数据包

当前实现允许在同一个 `compact_dataset` 目录中先写 96 training，再追加 24 validation。这会改变数组长度、manifest 和 file hashes，使已有模型锁失效。

必须改为：

```text
training package:
    dataset_id = task004_angle_nominal_p5_ny4_train96_v2
    仅包含 96 training responses
    创建后不可修改

blind-validation package:
    dataset_id = task004_angle_nominal_p5_ny4_blind24_v1
    仅在模型锁后生成
    不得覆盖或改写 training package

qualification bundle:
    只引用以上两个不可变 package 的 ID 与 hashes
```

若主动学习发生，则新建：

```text
task004_angle_nominal_p5_ny4_train112_v1
```

不得原地覆盖 train96 package。

training-only dataset ID 中不得出现误导性的 `96_plus24`。`sealed_validation_indices.npy` 不应作为 96-row training package 中的伪占位目标数组；validation 只保留 response-blind design identity。

### 4.2 独立 dataset checker

建立 Case125 checker，至少从 raw campaign manifests 和 formal records 独立重算：

```text
96/96 exact training tuple coverage
no missing / extra / duplicate
single forward_solver_sha = fdf9615...
single model / route / observable schema
MUMPS ICNTL(14)=40 requested and observed
all numerical/resource Gates true
fixed geometry h=120,w=17
all file hashes rebuild
array shapes/dtypes
order identity and mask axis
training design hash
validation design hash remains response-blind and disjoint
```

checker 不得读取 Task003 frozen validation，也不得运行 PDE。

### 4.3 修正 end-to-end power OOF

当前 `_power_oof(...)` 仍重新固定训练：

```text
gp:<selected feature>, jitter=1e-8
```

并将 fraction model 的 feature 硬编码为 `F1`。这不一定等于最终被选中的 aggregate candidate、feature 和 jitter。

必须改为：

```text
selected aggregate OOF R/T/std
+ selected feature
+ fold 内训练的 masked active-channel fraction model
+ analytic mask
```

不得重新建立另一套固定 GP 作为 power Gate 的 side total。

每个 fold 必须保存：

```text
aggregate candidate / feature / jitter
OOF R/T prediction and std
fraction-model identity
mask topology
channel prediction / std / error
sidewise ledger error
truth_leakage = false
```

power Gate 必须代表最终端到端模型，而不是一个与最终模型不同的诊断组合。

### 4.4 baseline 与 production candidate 分开排序

以下模型仅作为 deterministic accuracy baselines：

```text
local RBF
Chebyshev degree 2–5
```

它们没有可信预测方差，不得因为 aggregate score 最低就阻止一个满足全部 Gate 的 GP 被选中。

production candidates 限定为：

```text
Matérn-5/2 ARD exact GP
F1 / F2 / F3
jitter = 1e-10 / 1e-8 / 1e-6
8 deterministic optimizer starts
```

选择顺序必须是：

1. 先筛选满足 aggregate、spatial、uncertainty 和 power Gates 的 production GP；
2. 若存在多个合格 GP，再按冻结 selection score 和确定性 tie-break 选择；
3. 若没有合格 GP，则不得创建模型锁；
4. RBF/Chebyshev 只用于说明 GP 相对简单基准的收益。

### 4.5 冻结局部 spatial-holdout windows

当前把 `ordinary_interior` 的整个补集作为一个 holdout，等价于用困难边界数据外推大部分普通内部区域，不符合“局部插值空洞”测试目的。

必须在读取训练响应进行模型选择前，使用角度坐标和解析 cutoff 信息冻结：

```text
SPATIAL_HOLDOUT_WINDOWS.json
```

要求：

- 四类窗口：low-grazing、high-azimuth、cutoff-near、ordinary-interior；
- 每个窗口为局部、有限的角度子集，不得等于整个类别补集；
- 每个窗口建议 4–12 点；
- ordinary window 周围应有上下/左右训练支撑；
- cutoff window 由指定 order 的 signed analytic margin 决定，且两侧均有训练支撑；
- 窗口 index 和 tuple hash 在训练前冻结；
- 窗口可用于独立 spatial holdout；全域 overlapping region masks 仍用于普通 OOF 分区报告。

### 4.6 mask topology coverage

在不读取响应的前提下，对：

```text
96 training angles
24 validation angles
4096 candidate angles
```

计算 analytic power-carrying mask signatures。

生成：

```text
MASK_TOPOLOGY_COVERAGE.json
```

必须报告：

- 每个 topology signature 的 training count；
- validation/candidate 中是否存在 training 未覆盖的 signature；
- 每个 CV fold 的训练侧是否具有测试 topology 支撑。

正式 API 对训练中未见过的 topology 不得静默使用最近邻 fraction 并返回普通 `predicted`；应返回明确的 `unsupported_mask_topology` 或 `warning/unqualified`。

若某个正式 validation topology 在 96 training 中完全缺失，必须在 active-learning plan 中优先补齐；不得在 blind validation 后再补。

### 4.7 uncertainty calibration 必须 cross-fitted

当前利用全部 OOF residual 计算 calibration factor，再在同一批 OOF 点上检查 calibrated coverage，会天然接近 95%，不能作为独立校准证据。

必须：

1. 保存每个 target 的 raw OOF coverage；
2. 对每个 outer fold，使用其他 folds 的 OOF standardized residual 决定 calibration factor，再应用于当前 fold；
3. 报告 cross-fitted calibrated coverage；
4. 最终模型可用全部 OOF residual 冻结每 target 的 final calibration factor，但 blind validation 必须独立检验；
5. 模型包保存 `R/T/A` 三个独立 calibration factors，不得只保存一个最大 scalar；
6. latent-GP independence 和 delta-method 只可称为近似，不能将其解释为完整物理不确定度。

power-channel uncertainty 若仍来自 local-RBF residual scale，必须标记为：

```text
heuristic_training_residual_scale
not_calibrated_physical_uncertainty
```

不得用零方差，也不得在未验证前作为正式反演不确定度。

### 4.8 模型锁和公开 API fail closed

`fit_final_model(...)` 必须显式拒绝：

```text
training_gate != true
spatial_holdout_gate != true
uncertainty_gate != true
power_gate != true
validation_target_accessed != false
dataset hashes mismatch
forward_solver_sha mismatch
```

`AngleSurrogate.from_package(...)` 作为公开资格化入口，必须要求存在：

```text
ANGLE_MODEL_SELECTION_LOCK.json
ANGLE_MODEL_QUALIFICATION.json
```

且 blind-validation status 为 pass。训练阶段未通过 blind validation 的研究模型只能通过显式 `research/debug` loader 使用，不能被普通 `predict(...)` 当作生产模型加载。

---

## 5. M4B：构建 96-row training-only dataset

M4A 完成后，使用现有 96 个 raw records 构建不可变 training package。

不得重新运行这 96 个 FEM。

正式 manifest 至少保存：

```text
dataset_id
forward_solver_sha = fdf9615...
surrogate_dataset_builder_sha
model / route / observable / parameter schema
fixed geometry and wavelength/polarization
MUMPS workspace identity
training design hash
sample IDs hash
config hashes
topology hash
order-axis identity
array shape/dtype
file hashes
validation_target_accessed = false
```

独立 checker 通过后，M4B 才算完成。

---

## 6. M4C：training-only 模型比较与资格化

### 6.1 输入与输出

输入：

```text
(grazing_deg, azimuth_deg)
```

固定：

```text
h=120 nm, w=17 nm, wavelength=13.5 nm, S incident
```

aggregate 使用：

```text
zR = log((R+eps)/(A+eps))
zT = log((T+eps)/(A+eps))
softmax(zR,zT,0) -> R/T/A
```

fixed-order power 使用：

```text
predicted side total R/T
+ analytic active mask
+ active-channel log-ratio fractions
+ sidewise softmax reconstruction
```

### 6.2 training-only Gates

Aggregate 每个目标必须满足：

```text
OOF NRMSE <= 0.01
OOF p95 absolute error <= 0.01
OOF max absolute error <= 0.03
all overlapping-region p95 <= 0.02
all frozen spatial-window p95 <= 0.02
composition exact to <= 1e-12
```

Uncertainty：

```text
raw coverage reported per target
cross-fitted calibrated 95% coverage per target in [0.90,0.99]
region coverage reported
no NaN/zero fake uncertainty for qualified GP
```

Primary power channels：

```text
mask agreement = 100%
sidewise ledger <= 1e-12
NRMSE <= 0.03
p95 absolute error <= 0.01
end-to-end OOF uses predicted aggregate totals
```

所有 OOF 点必须保存：

```text
truth / prediction / error / std
fold
nearest actual fold-training distance
overlapping regions
spatial-window membership
cutoff order and signed distance
mask topology signature
```

### 6.3 M4C 的三种结果

#### A. 全部 training Gates 通过

创建不可变：

```text
ANGLE_MODEL_SELECTION_LOCK.json
```

随后可进入 M5，不需要再次等待审阅。

#### B. 未通过，但满足主动学习资格

只有以下条件全部满足，才允许 M4D：

```text
GP production candidate 明显优于最佳 deterministic baseline；
至少两个 aggregate 的 |OOF error| 与 predicted std 排序相关为正且可用；
主要误差集中在可解释的 low/cutoff/high-azimuth/coverage-hole 区域；
没有 dataset、mask、solver 或代码合同失败；
validation response 仍未运行/未访问。
```

生成 `ACTIVE_LEARNING_ROUND1_PLAN.json` 和 checker 后，最多运行 16 个新 FEM。

#### C. 未通过且不满足主动学习资格

受控停止等待 Review V3。不得继续换 kernel、增加第二轮样本或读取 validation。

---

## 7. M4D：最多一轮 16-angle active learning

若 M4C-B 成立，从冻结的 4096 candidate pool 选择最多 16 点。

Acquisition 可使用：

```text
cross-fitted GP uncertainty
OOF regional error model
nearest-training distance
cutoff proximity
primary-channel importance
mask-topology coverage
```

禁止使用 blind-validation response。

多样性要求：

```text
覆盖 low-grazing / cutoff / high-azimuth / ordinary-interior；
不得超过一半点集中于同一困难区域；
优先补齐训练中缺失或极少支持的 analytic mask topology；
保持全角域空间填充；
不得修改原 96 点和原 24 validation tuples。
```

所有新 FEM 必须通过固定在 `fdf9615...` 的只读 forward worktree 运行，保持：

```text
Full3D p5/Ny4
ICNTL(14)=40
MPI2/thread1
observable-v3
```

完成后新建 train112 package，并同时报告：

1. 标准 112-row OOF；
2. 固定原 96 个测试行的 paired 96-vs-112 学习曲线；
3. 新 16 点的 prospective prediction audit。

若 112 点仍未通过，立即停止；不得自行进行第二轮 active learning。

---

## 8. M5：模型锁后的一次性 blind validation

只有 train96 或 train112 的全部 training Gates 通过并创建模型锁后，才允许：

1. 使用固定 `fdf9615...` forward worktree 运行 24 个 blind-validation FEM；
2. 构建独立 `blind24` package；
3. 使用锁定模型一次性评分；
4. 不得根据 validation 结果重新选择 feature、kernel、jitter、calibration 或 power model。

Blind-validation aggregate Gate：

```text
NRMSE <= 0.01
p95 absolute error <= 0.01
max absolute error <= 0.03
region p95 <= 0.02 where region n>=3
composition exact
```

Blind-validation power Gate：

```text
mask agreement = 100%
sidewise ledger <= 1e-12
primary channel NRMSE <= 0.03
primary channel p95 absolute <= 0.01
```

Uncertainty：

```text
per-target 95% interval covers at least 22/24 points
24/24 is reported as conservative, not automatically rejected
interval width and region coverage reported
```

若 blind validation 通过，创建：

```text
ANGLE_MODEL_QUALIFICATION.json
status = qualified_for_nominal-geometry_angle-response prediction
```

若失败，保存 immutable failure report 并停止。不得在同一 Task 中使用这 24 点调参后重新声称 blind validation。

---

## 9. 通过后允许的交付

只有 blind validation 通过后，才允许发布普通 `AngleSurrogate.predict(...)` 和 dense maps。

接口必须返回：

```text
R/T/A mean and calibrated std
fixed-order powers and uncertainty semantics
analytic mask / cutoff order / signed distance
nearest training distance
mask-topology status
in-domain status and warnings
forward_solver_sha
surrogate_training_code_sha
dataset/model/qualification identities
```

图必须明确标注为 surrogate predictions，不能冒充 FEM truth。

Task004 通过仍只代表：

```text
固定 h=120 nm,w=17 nm 下的任意域内角度响应代理
```

它不授权：

```text
height/width sensitivity surrogate
Fisher angle ranking
geometry inversion
P incident
wavelength/material variation
```

---

## 10. Required deliverables

建立：

```text
benchmarks/cases/125_task004_angle_training_qualification/
```

至少交付：

```text
outcomes/training_dataset_report.md
outcomes/TRAINING_DATASET_VERIFICATION.json
outcomes/MASK_TOPOLOGY_COVERAGE.json
outcomes/SPATIAL_HOLDOUT_WINDOWS.json
outcomes/training_cv.md
outcomes/training_cv.json
outcomes/training_cv_oof.json
outcomes/model_selection.md
outcomes/uncertainty_calibration.md
outcomes/power_model.md
outcomes/test_summary_v3.md
```

条件式交付：

```text
ACTIVE_LEARNING_ROUND1_PLAN.json
learning_curve_96_to_112.md
ANGLE_MODEL_SELECTION_LOCK.json
blind_validation_report.md
ANGLE_MODEL_QUALIFICATION.json
angle_maps.md
```

本轮完成后写：

```text
surrogate_tasks/task004_nominal_geometry_angle_surrogate/response_v3.md
```

---

## 11. 测试要求

至少包括：

```text
training/validation package immutability
forward SHA vs training-code SHA separation
no validation access before lock
power OOF uses selected aggregate OOF predictions
no test-fold truth totals in power reconstruction
candidate baseline/production separation
localized spatial-window hashes
fold-training nearest distance > 0 where expected
overlapping region masks
analytic mask topology coverage
cross-fitted calibration
model-lock fail-closed
public API refuses unqualified package
Case124 forward evidence remains immutable
Case125 independent checker
compileall and git diff --check
```

若环境允许，运行 Task002/003/004 相关回归；任何已有无关历史失败必须单独列出，不得写成 Task004 通过或失败。

---

## 12. Codex 执行摘要

```text
请执行 git pull --ff-only，并完整阅读 Task004 review_report_v2.md。

批准保留 forward SHA fdf961545f217d620e22800f2704ae9913a6d270、
ICNTL(14)=40、5/5 anchors 和 96/96 training FEM；不得重跑这96点。

先执行 M4A：
- 分离 forward_solver_sha 与 surrogate_training_code_sha；
- 建立不可变 train96 与独立 blind24 package；
- 修正 selected aggregate/power OOF 一致性；
- 分开 baseline 与 production candidate；
- 冻结局部 spatial holdout windows；
- 完成 mask-topology coverage；
- 实现 cross-fitted per-target uncertainty calibration；
- model lock/API fail closed。

随后构建并检查 train96 dataset，运行 training-only CV。

若全部 training Gates 通过：创建模型锁，并可在同一轮使用固定 fdf9615...
只读 forward worktree 运行24个blind-validation FEM，一次性评分。

若未通过但满足主动学习资格：最多运行一轮16个新训练角度；使用相同
fdf9615... forward identity。112点仍未通过则停止。

禁止 Task003 Round3、Task003 validation、第二轮active learning、Fisher、
geometry sensitivity和inversion。
```
