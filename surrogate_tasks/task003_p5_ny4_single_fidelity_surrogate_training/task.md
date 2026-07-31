# Task003 任务书：p5/Ny4 单保真四维前向代理构建与资格化

## 0. 权威、目标与硬边界

开始前必须完整阅读：

1. 根目录 `AGENTS.md`；
2. `surrogate_tasks/AGENTS.md`；
3. `surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/review_report_v8.md`；
4. Task002 `response_v8.md`；
5. Task002 `outcomes/m4e_ny4_production.md`；
6. Task002 `outcomes/m4e_dataset_report.md`；
7. 本任务 `README.md` 与 `task.md`。

固定 Git 身份：

```text
repository = Rookie1234567/MyFEniCS
branch = codex/only-one-13p5nm-surrogate-inversion
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
```

本任务目标是建立并资格化：

```text
ForwardSurrogateV1:
    input:
        height_nm
        width_x_nm
        grazing_deg
        azimuth_deg
    fixed:
        wavelength_nm = 13.5
        incident_polarization = S
        forward solver identity = p5/Ny4 Case119 dataset
    output:
        R_total, T_total, A_balance
        fixed-order outgoing S/P powers
        analytic power-carrying mask
        prediction uncertainty
        domain / model / dataset provenance
```

复振幅 real/imag surrogate 是本任务的条件式第二层目标。正式角度 Fisher 排名、实验反演、Bayesian posterior、MCMC、P incident surrogate 和 FEM 基线升级均禁止。

---

## 1. 权威数据身份

只允许使用：

```text
dataset_id = task002_m4e_p5_ny4_112_v3
dataset schema = task002.s-p5-ny4-single-fidelity-dataset.v3
dataset source SHA = 10e3356ba8364286a452077f71d7e3b92ea24cd5
model_id = S_PROD_FULL3D_STATIC_P5_H10_NY4
solver_route_id = full3d_static_uniform_n1curl_p5_h10_ny4
observable schema = task002.fixed-n0-orders.v3
mesh = (Nx,Ny,Nz) = (6,4,14)
training = 96
frozen validation = 16
```

禁止使用：

- Case117/Ny3 的 56 个 pass；
- Task001 Hybrid 数据；
- p4/h10、p4/h7.5、Hybrid p5/p6 诊断数据；
- 不同 source SHA、model ID、route ID、observable schema 的样本；
- discretization-audit 数据作为训练样本；
- 手工添加、替换或删除冻结 validation tuple。

权威 tracked evidence：

```text
benchmarks/cases/119_task002_p5_ny4_bulk_campaign/
```

实际数组位于数据生成电脑的 ignored artifact：

```text
benchmarks/artifacts/cases/119/m4e/compact_dataset/
```

---

# M0：分支、环境与数据包移交

## M0.1 Git Gate

执行并记录：

```bash
pwd
git rev-parse --show-toplevel
git remote get-url origin
git branch --show-current
git rev-parse --abbrev-ref --symbolic-full-name '@{u}'
git rev-parse HEAD
git rev-list --left-right --count 'HEAD...@{u}'
git status --short
```

不得 merge/rebase master 或其他分支。

## M0.2 不污染 FEM 环境

代理训练使用独立环境，例如：

```text
.venv-surrogate
```

不得修改或升级正式 FEM `.venv` 中的 PETSc、DOLFINx、MPI、Basix、UFL 或 ABI 栈。

记录：

- OS / Python；
- NumPy / SciPy；
- scikit-learn、GPyTorch 或选定 GP 框架；
- PyTorch/CUDA（若使用）；
- CPU/GPU；
- BLAS；
- random seeds；
- CPU threads / GPU memory。

数据只有 96 个训练点，不得以“必须使用 GPU”为预设。先做 CPU/GPU 稳定性与时间小测试，选择可复现且简单的后端。

## M0.3 Deterministic dataset package

在数据生成电脑上，将以下目录打包：

```text
benchmarks/artifacts/cases/119/m4e/compact_dataset/
```

生成：

```text
task002_m4e_p5_ny4_112_v3.tar.zst
PACKAGE_MANIFEST.json
PACKAGE_SHA256.txt
```

若系统无 zstd，可使用 `.tar.gz`，但只能选择一种正式格式。

`PACKAGE_MANIFEST.json` 至少包含：

```text
dataset_id
source_sha
schema versions
sample_ids_hash
split_hash
all relative file paths
file sizes
file SHA256
array shape/dtype
package SHA256
created_by_code_sha
```

二进制数据包不得直接提交 Git。通过用户认可的 `scp`、`rsync` 或其他明确传输方式移动到工作站。

工作站解包前后必须验证：

```text
package hash
all file hashes
sample count = 112
train count = 96
validation count = 16
sample_ids_hash
split_hash
```

任何 hash 不一致必须 fail closed，不得重新生成一个“看起来相同”的数据集替代。

### M0 Gate

```text
package verified = true
workstation copy exact = true
Git evidence and binary package identities match = true
```

---

# M1：只读数据加载器与冻结验证保护

在 `src/surrogate/` 新增隔离模块，不重写 FEM 内核。

推荐结构：

```text
src/surrogate/
    dataset.py
    features.py
    targets.py
    physics.py
    pce.py
    gp.py
    validation.py
    package.py
    cli.py
```

## M1.1 默认 train-only

实现：

```python
view = load_dataset(package_dir, split="train")
```

默认代码路径不得读取 validation target rows。

validation unlock 必须要求：

```text
MODEL_SELECTION_LOCK.json 已存在
显式 --unlock-frozen-validation
记录 unlock 时间、代码 SHA、模型包 hash
```

在模型选择冻结前，测试必须证明 validation targets 没有被加载、标准化、统计或可视化。

## M1.2 数据完整性

独立于 Case119 writer，再检查：

- 112 个 sample ID 唯一；
- 96/16 split 精确；
- train/validation 无交集；
- inputs 域内且无重复；
- aggregates 有限；
- amplitude/power NaN 与 mask 一致；
- false mask 不得被 zero-fill 后参与 loss；
- fixed order identity 与 array axis 一致；
- R/T/A 与 order ledger 一致；
- 所有 file hashes 与 package manifest 一致。

## M1.3 Structural null 语义

`power_carrying_mask=false` 表示通道在该输入下没有功率定义，不能解释为“真实测量值等于零”。

预测 API 对此返回：

```text
power = null
amplitude = null
power_carrying = false
```

传播/功率状态由解析 order identity 或经过验证的 mask 逻辑决定，不训练一个不透明分类器来猜。

### M1 Gate

```text
train-only loader pass
frozen validation access guard pass
mask/NaN integrity pass
physics ledger pass
```

---

# M2：训练集内部审计与冻结特征

全阶段仅使用 96 个 training samples。

## M2.1 输入特征

用户接口保持：

```text
height_nm, width_x_nm, grazing_deg, azimuth_deg
```

代理内部主特征冻结为：

\[
\mathbf x=(\tilde h,\tilde w,k_x/k_0,k_y/k_0),
\]

其中：

\[
k_x/k_0=\cos\alpha\cos\phi,
\qquad
k_y/k_0=\cos\alpha\sin\phi.
\]

`h,w` 线性缩放到 `[-1,1]`。不得从 validation 计算均值、标准差或 feature range。

精确 `grazing=0°` 继续 fail closed；正式域：

```text
height 115–125 nm
width 16–18 nm
grazing 0.5–10°
azimuth 0–90°
```

## M2.2 Training-only exploratory audit

报告：

- 每个 aggregate 的范围、分位数和梯度近似；
- 每个 order/component 的 active fraction；
- power dynamic range；
- outgoing P 的信号量级；
- structural-null topology；
- Rayleigh/cutoff 邻域；
- 训练点空间填充距离；
- 是否存在单点异常或不连续证据。

不得据此删除“难点”或改变冻结 validation。

## M2.3 输出层级

### Tier A：强制完成

1. aggregate composition：
   ```text
   R_total, T_total, A_balance
   ```
2. fixed-order outgoing S/P powers；
3. analytic mask；
4. uncertainty。

### Tier B：条件式完成

```text
fixed-order complex amplitude real/imag
```

如果 complex surrogate 在训练内部 CV 中不满足冻结 Gate，可以将 Task003 结论限定为 power-surrogate-qualified，并保留 amplitude blocker；不得伪造相位精度。

## M2.4 物理约束输出表示

Aggregate 不得独立回归后任意 clip。优先采用 composition transform，例如：

\[
z_R=\log\frac{R+\epsilon}{A+\epsilon},
\qquad
z_T=\log\frac{T+\epsilon}{A+\epsilon},
\]

预测后以 softmax 重构：

```text
R >= 0
T >= 0
A_balance >= 0
R + T + A_balance = 1
```

`epsilon` 必须固定并记录，不能用 validation 调整。

对 fixed-order powers，必须满足：

```text
nonnegative
inactive -> null
reflection channel sum = predicted R
transmission channel sum = predicted T
```

优先方案是对每侧 active-channel fractions 建模；若 mask topology 使 log-ratio basis 不稳定，可使用独立 log-power GP 后做确定性、记录在案的 side-wise renormalization。必须同时报告 renormalization 前后误差。

`A_volume` 可作为诊断 target。若 `A_volume-A_balance` 只处于求解器数值噪声量级，则模型包应明确将 operational absorption 定义为 `A_balance`，不得训练一个纯噪声通道。

### M2 Gate

形成并提交：

```text
FEATURE_CONTRACT.json
TARGET_CONTRACT.json
CHANNEL_IDENTITY.json
TRAINING_ONLY_DATA_AUDIT.md
```

一旦进入 M3，未经 controlled stop 和新审阅不得更改。

---

# M3：模型候选与训练内模型选择

禁止 model zoo。只允许以下角色明确的模型。

## M3.1 低阶基准：Sparse Chebyshev / PCE

只运行：

```text
degree 2
degree 3
```

用途：

- 判断全局响应是否低阶光滑；
- 提供可解释敏感度；
- 为 GP 结果提供简单基准。

禁止不断增加到 4、5、6 阶来追逐训练误差。

## M3.2 主模型：Matérn-5/2 ARD GP

要求：

```text
kernel = Matérn 5/2
ARD = true
mean = constant or training-frozen low-order trend
nugget/jitter = explicit and recorded
hyperparameter bounds = frozen
optimizer restarts and seeds = recorded
```

96 点规模允许 exact GP。可以使用独立 channel GP 或经过训练内重构验证的 latent representation；不得因方便而把 mask 不同的通道直接拼进同一个普通 PCA。

## M3.3 交叉验证

使用 training-only 的确定性 5-fold space-filling CV；fold 定义必须 hash-bound。额外报告：

- domain corners；
- low-grazing；
- high-azimuth；
- cutoff 邻域；
- geometry extremes。

不得使用 validation target 做 early stopping、kernel 选择、transform 选择或 PCE/GP 比较。

## M3.4 Training-CV Gate

Aggregate 硬 Gate：

```text
range-normalized RMSE <= 0.02
p95 absolute error <= 1e-3
when truth >= 1e-2: p95 relative error <= 1%
```

目标 Gate：

```text
range-normalized RMSE <= 0.01
p95 absolute error <= 5e-4
when truth >= 1e-2: p95 relative error <= 0.5%
```

主要 order-power 通道定义必须仅用 training 冻结，例如：

```text
training max power >= 1e-6
or training Fisher/information contribution in frozen top set
```

主要通道硬 Gate：

```text
NRMSE <= 0.02
p95 |error| / sqrt((0.01*truth)^2 + 1e-8^2) <= 1.0
```

目标为 `0.01` 与 `0.5`。

物理 Gate：

```text
negative power count = 0
aggregate composition error <= 1e-12
side power ledger error <= 1e-10
inactive channel non-null count = 0
```

不满足 hard Gate 时不得解封 validation，先进入 M4 主动加点或 controlled stop。

---

# M4：训练集驱动的主动加点（仅在需要时）

若 96 点 training-CV 已满足 hard Gate，可跳过 M4。

若不满足，允许使用已冻结的 4096 candidate pool，最多：

```text
3 rounds
8 new FEM points per round
24 total new points
```

选点依据只能来自：

- training-only GP posterior variance；
- CV error surrogate；
- input-space distance；
- cutoff proximity；
- aggregate/order channel importance；
- 预冻结的组合 acquisition score。

不得查看 frozen validation target 选择点。

## M4.1 新 FEM source 身份

所有新点必须由**精确 production forward SHA**：

```text
10e3356ba8364286a452077f71d7e3b92ea24cd5
```

在隔离 clean clone/worktree 中运行。当前训练代码 HEAD 的变化不得改变 FEM source identity。

新样本必须通过 Case119 同一 residual、energy、leakage、ledger、runtime topology、zero-swap 和 cleanup Gate。

新增后建立新 dataset version；原 16 validation tuple 保持不变且继续封存。

## M4.2 停止规则

- hard CV Gate 达到后停止；
- 达到 24 点预算仍失败则 controlled stop；
- 首个未解释 FEM failure 立即停止；
- 不得跳过难点继续凑数。

---

# M5：模型选择冻结

在读取 validation 前生成不可变：

```text
MODEL_SELECTION_LOCK.json
```

至少包含：

```text
dataset/package hashes
training sample IDs
feature contract hash
target contract hash
fold hash
selected model class
kernel / transform
hyperparameters
random seeds
training code SHA
model artifact hashes
CV metrics
primary channel list
uncertainty calibration method
validation unopened assertion
```

锁定后不得修改模型。若后续 validation fail，需要新 review 和新的 blind validation，不得在同一 16 点上反复调参。

---

# M6：一次性冻结验证

只有 M5 Gate 通过后，才允许显式解封 16 个 validation targets。

## M6.1 验证指标

报告：

- aggregate R/T/A；
- 主要 order powers；
- secondary powers；
- mask/ledger；
- GP predictive intervals；
- domain-region breakdown；
- PCE 与 GP，但模型选择不得改变。

Frozen-validation hard Gate：

```text
aggregate NRMSE <= 0.02
aggregate p95 absolute error <= 1e-3
truth >= 1e-2: aggregate p95 relative error <= 1%
primary power NRMSE <= 0.02
primary p95 normalized error <= 1.0
all physics/mask/ledger Gates pass
```

目标仍为 `0.01 / 5e-4 / 0.5% / 0.5`。

不确定度诊断：

```text
95% interval empirical coverage should not be materially under-dispersed
standardized residuals and NLL reported
```

16 点很少，不以单一 coverage 百分比做虚假精确判断，但明显过窄必须 fail。

## M6.2 Validation failure

如果 hard Gate 失败：

- validation 被标记为 consumed；
- 不得根据其具体误差调参后再次把同一 16 点称为 blind validation；
- 保存失败证据并停止等待审阅；
- 后续若主动加点，必须冻结新的独立 blind validation design。

---

# M7：复振幅条件式资格化

仅在 Tier A power surrogate 通过 M6 后执行。

训练 real/imag，而不是直接回归 wrapped phase。每个 active channel 使用固定尺度标准化。

主要复振幅通道 Gate：

```text
complex NRMSE <= 0.05
significant channels p95 |a_pred-a_true| / max(|a_true|, a_floor) <= 0.10
power reconstructed from amplitude is consistent with predicted/measured power
```

`a_floor` 只能由 training 数值噪声证据冻结。

若失败：

```text
power surrogate = qualified
complex amplitude surrogate = not qualified
```

不得让 amplitude 失败推翻已经合格的 power model，也不得虚假返回高精度相位。

---

# M8：离散误差与最终模型包边界

8 个 discretization-audit points 尚未执行。它们不阻塞拟合 p5/Ny4 solver surrogate，但阻塞将 GP uncertainty 解释为完整物理不确定度。

本任务至少必须输出：

```text
discretization_uncertainty_status = pending_8_point_audit
```

如用户在本轮明确允许执行 audit，应先编写独立 audit plan 并保持 audit 结果不进入训练。建议至少比较 production Ny4 与 Ny5 y-refinement；x/z/p 的更高参考需要资源预检和独立授权。

在 audit 完成前：

- 可以发布“p5/Ny4 operational solver surrogate”；
- 不得发布 continuum-accuracy claim；
- 不得执行正式角度 Fisher 排名或最终反演置信区间。

## M8.1 模型包

模型包至少包含：

```text
MODEL_MANIFEST.json
feature/target/channel contracts
trained model states
normalization constants
training and validation metrics
dataset/package/file hashes
training code SHA
environment lock
seeds
supported domain
unsupported inputs
uncertainty semantics
discretization status
```

二进制模型可保存在 ignored artifact；Git 跟踪 compact manifest、hash、指标和重建命令。

## M8.2 API / CLI

至少实现：

```bash
python -m src.surrogate.cli predict \
  --model-package <path> \
  --height-nm 120 \
  --width-nm 17 \
  --grazing-deg 5 \
  --azimuth-deg 45 \
  --output prediction.json
```

输出：

```text
status
inputs
R/T/A
fixed-order S/P powers
power-carrying mask
prediction standard deviations / intervals
model and dataset identity
in-domain status
warnings
```

必须 fail closed：

- 精确 grazing=0°；
- 域外输入；
- P incident 请求；
- 非 13.5 nm；
- 缺失/错误模型包 hash；
- 请求未资格化 complex amplitude 时。

---

# M9：测试、报告与交付

至少生成：

```text
benchmarks/cases/120_task003_surrogate_training/
    README.md
    config.json
    expected.json
    records/
    checker

surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/
    outcomes/summary.md
    outcomes/test_summary.md
    outcomes/data_transfer.md
    outcomes/training_cv.md
    outcomes/model_selection.md
    outcomes/frozen_validation.md
    outcomes/model_package.md
    response_v1.md
```

测试至少覆盖：

- package/file hash；
- train-only default；
- validation access guard；
- mask/NaN；
- deterministic folds/seeds；
- PCE/GP reload identity；
- physical reconstruction；
- prediction domain fail-closed；
- CPU/GPU或重复运行一致性；
- model package tamper rejection；
- CLI roundtrip；
- independent checker。

最后报告：

```text
repository root
branch/upstream
full HEAD SHA
changed paths
dataset/package/model identities
training backend and environment
CV metrics
frozen-validation metrics
active-learning inventory
resource usage
qualified outputs
unqualified outputs
remaining uncertainty boundaries
```

提交并只推送当前代理分支，然后停止等待 ChatGPT 审阅。

---

## 禁止事项总结

不得：

- 重新抽取或修改现有 16 点 frozen validation；
- validation 驱动模型选择；
- 混入 Ny3、p4 或 Hybrid 数据；
- 修改 FEM production identity；
- 运行无边界 model zoo；
- 训练 P incident 或波长可变代理；
- 开始正式 angle DOE；
- 开始参数反演、MCMC 或 Bayesian posterior；
- 合入 master。
