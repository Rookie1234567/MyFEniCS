# Task002 任务书：S 偏振连续照明四维多保真前向代理与角度设计

## 0. 权威、目标与硬边界

本任务由 ChatGPT 编写并审阅，Codex 在唯一执行分支实施。开始前必须完整阅读：

1. 根目录 `AGENTS.md`；
2. `surrogate_tasks/AGENTS.md`；
3. Task001 的 `review_report_v3.md`；
4. Task001 的 `response_v3.md`、`five_configuration_failure_correction.md`、observable v2 说明和全部当前 outcomes；
5. 本目录 `README.md` 与本任务书；
6. Case095/096、Case110/111 的 tracked authority、negative evidence 和 checker。

固定执行身份：

```text
repository = Rookie1234567/MyFEniCS
branch = codex/only-one-13p5nm-surrogate-inversion
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
polarization = S only
wavelength = 13.5 nm fixed
production inversion = forbidden
P surrogate = forbidden
Hybrid-P redevelopment = forbidden
```

Task002 的正式目标是建立并资格化：

```text
ForwardSurrogate:
    (height_nm, width_x_nm, grazing_deg, azimuth_deg)
        -> S-incident diffraction response, R/T/A, uncertainty

IlluminationDesigner:
    prior/domain of height and width + measurement-noise assumptions
        -> ranked single angles and 2--4 angle bundles
```

Task002 不是 Task003。它可以做 surrogate-based synthetic blind checks，但不得使用真实实验数据宣称完成正式反演，不得执行正式 Bayesian posterior 或 MCMC。

---

## 1. 物理、参数和角度合同

### 1.1 四个连续前向输入

```text
height_nm  in [115.0, 125.0]
width_x_nm in [16.0, 18.0]
grazing_deg in [0.5, 10.0]
azimuth_deg in [0.0, 90.0]
```

其中：

- `height_nm`、`width_x_nm` 是未来反演未知量；
- `grazing_deg`、`azimuth_deg` 是已知实验配置，不是反演未知量；
- 用户输入的掠射角相对于样品表面；
- 内部求解器角度：

```text
incident_theta_deg = 90.0 - grazing_deg
incident_phi_deg = azimuth_deg
```

越界输入 fail closed，不得 clip。

### 1.2 精确 0° 的处理

用户目标可口语描述为 0--10°，但精确 0°时穿过水平入射面的法向功率为零，普通 R/T 归一化退化。因此：

```text
formal training/prediction domain = [0.5°, 10°]
grazing_deg == 0° -> structured status zero_grazing_limit_not_defined
0° < grazing_deg < 0.5° -> out_of_training_domain
```

不得让 GP/PCE 向 0°静默外推，不得返回看似正常的 R/T。

### 1.3 固定量

```text
wavelength_nm = 13.5
incident_polarization = S
period_x = 50 nm
period_y = 25 nm
grating_width_y = period_y
rectangular vertical sidewalls
existing fixed complex material indices
existing substrate/air extents
Floquet x/y
no PML
auxiliary DtN / auto propagating orders
existing physical boundary-plane amplitude convention
```

Task002 不增加：材料、波长、周期、P 偏振、侧壁角、圆角、上下宽度差、氧化层、粗糙度、强度尺度或其他反演参数。

### 1.4 参数归一化与代理内部特征

数据文件必须保留原始物理输入。模型内部至少支持：

```text
h_norm = (height_nm - 120) / 5
w_norm = (width_x_nm - 17) / 1
kx_over_k0 = cos(grazing) * cos(azimuth)
ky_over_k0 = cos(grazing) * sin(azimuth)
kz_over_k0 = sin(grazing)          # derived diagnostic
```

主 GP 输入使用：

```text
[h_norm, w_norm, kx_over_k0, ky_over_k0]
```

PCE/Chebyshev 诊断模型可使用归一化的原始四变量 `[h,w,grazing,azimuth]`。所有角函数使用 radians；用户接口仍使用 degree。

---

## 2. 前向保真度与路由

### 2.1 Low fidelity

```text
model_id = S_LF_HYBRID_P4_H10_M120
method = Hybrid modal-Schur memory-minimal
assembly = assembly-time static condensation
field degree = p4
mesh target = h10
mode count = M120 per direction
MPI ranks = 2
threads per rank = 1
```

### 2.2 High fidelity

```text
model_id = S_HF_HYBRID_P6_H10_M120
method = Hybrid modal-Schur memory-minimal
assembly = assembly-time static condensation
field contract = p5 trace / p6 interior exact sequence
mesh target = h10
mode count = M120 per direction
MPI ranks = 2
threads per rank = 1
```

### 2.3 禁止的路由

- 不运行 p6/h7.5；
- 不把 Full3D P reference 混入 S dataset；
- 不为 Task002 修改 Hybrid-P；
- 不使用不同 M、MPI、mesh、source SHA 或 schema 的样本静默拼接；
- 不把 LF4 当作 HF truth；
- 不以 Task001 historical SHA 直接生成正式 Task002 dataset。

### 2.4 Task002 clean baseline

先实现 schema、continuous-angle runner、campaign、dataset 和 checker；完成 targeted tests 后提交：

```text
Task002 implementation baseline SHA
```

然后保持工作树 clean。所有正式 Task002 FEM 必须绑定该完整 SHA。若发现数值 bug：

```text
stop campaign -> preserve evidence -> fix -> new SHA -> invalidate affected records -> rerun minimum affected set
```

文档或训练代码的后续变化不得无理由重跑 hash-bound PDE；但任何影响 config、mesh、matrix、RHS、Hybrid coupling、DtN、order extraction或 Gate 的变化必须建立新 dataset source version。

---

## 3. Mother response、传播级和输出 schema

### 3.1 当前母响应

以 `task001.fixed-n0-orders.v2` 为起点，每个 run 保存：

```text
incident polarization
side / port side / m / n
kx, ky, kz complex identity
power_carrying
dispersion_propagating
outgoing S/P boundary amplitude real/imag
outgoing S/P power
order_total_power
R_total, T_total, A_balance, A_volume
n!=0 leakage
numerical Gate/resource/provenance
```

不得动态选择“每个样本功率最大的前 N 个 order”。

### 3.2 全角域 order-window 审计

在正式数据生成前，对完整角域解析审计：

```text
grazing in [0.5,10]
azimuth in [0,90]
all top and bottom n=0 orders that can carry non-negligible outward power
```

至少：

1. 用解析色散极值和高分辨角网格检查当前 `m=(0,-1,...,-7,+1)`；
2. 检查 top air 与 lossy substrate；
3. 验证 y-invariant geometry 下 `n!=0` 只为数值泄漏；
4. 列出每个 order 的 cutoff/Rayleigh 曲线或最近距离；
5. 检查 fixed window 是否覆盖所有正式角域的重要通道。

如果不完整，必须在任何正式 Task002 sample 前升级 observable schema，并重跑最小 extraction tests。一个正式 dataset 只能使用一个固定 order schema。

### 3.3 Cutoff 与结构性 null

对于不携带功率的 component/order：

```text
power = null
power_carrying = false
```

传播但功率数值为零时保留 `0.0`。不得把 null 填成零训练。

对每个输入解析计算 cutoff proximity，例如：

```text
cutoff_metric = min relevant |beta| / k0
near_cutoff flag = threshold frozen after M2 pilot
```

默认候选阈值 `0.02`，但必须由 pilot 记录其稳定性。cutoff 邻域必须加点、提高预测不确定度并在 angle ranking 中单独标注。

### 3.4 代理的生产输出

第一版生产代理至少预测：

- `R_total`；
- `T_total`；
- `A_balance = 1 - R_total - T_total`（确定性派生）；
- 固定物理身份下选定的、实验可测的独立衍射功率通道；
- predictive mean/std/interval；
- channel availability / power-carrying mask；
- cutoff、domain-distance 和 extrapolation flags。

完整复振幅仍作为 mother-response 数据保存。Task002 应建立复振幅 surrogate 的诊断原型（real/imag，不拟合 wrapped phase），但生产验收以可测功率 surrogate 为主。复振幅模型未通过时可标记 research-only，不能篡改原始 mother responses。

### 3.5 独立观测选择

不得同时将：

```text
S power
P power
S+P total
```

三者全部当作独立观测。必须分别支持：

1. detector-only total power；
2. optional polarization-resolved S/P power。

Task002 主 DOE 默认使用 detector-only total order power；偏振分辨结果单独报告。

---

## 4. 数据集格式与不可混源合同

### 4.1 Dataset identity

正式 dataset id 至少包含：

```text
task002 schema version
dataset source full SHA
LF/HF model identities
order/observable schema
input domain
sampling seeds
MPI/thread identity
```

### 4.2 Canonical portable files

原始大 artifact 保持 ignored。正式 compact dataset 至少输出：

```text
dataset_manifest.json
sample_records.jsonl
inputs.npy
aggregates.npy
order_amplitudes.npy          # complex128 or real/imag final-axis
order_powers.npy              # float64, structural null represented by NaN
power_carrying_mask.npy       # bool
order_identity.json
train_hf_indices.npy
train_lf_indices.npy
frozen_validation_indices.npy
file_hashes.json
```

每个数组必须记录 shape、dtype、单位、axis meaning 和 checksum。结构性 null 使用独立 mask，不得与零功率混淆。

### 4.3 Sample status

```text
measured_pass
failed_numerical_gate
controlled_stop_resource
not_run
derived
predicted
```

只有 `measured_pass` 进入训练候选。失败记录保留在 manifest 和 negative evidence 中。

### 4.4 数据传输

本地 WSL 数据生成完成后：

1. 运行 dataset checker；
2. 冻结 manifest 和 hashes；
3. 打包 compact dataset，不打包无必要场文件；
4. 在工作站 materialize/复制后重新计算 hashes；
5. 工作站训练只能读取 checker 通过的 dataset id。

---

## 5. 采样设计与预算

所有随机/低差异设计必须冻结 seed 和实际点表，不能只记录生成算法。

### 5.1 M2 中心几何角度 pilot

固定：

```text
height = 120 nm
width = 17 nm
```

LF 角度网格：

```text
grazing = [0.5, 1, 2, 4, 6, 8, 10] degree
azimuth = [0, 15, 30, 45, 60, 75, 90] degree
```

最多 49 个 LF solves。已与新 dataset SHA 完全同源的 anchor 可复用；不同 SHA 不得复用为正式样本。

HF 角度 pilot：

固定 9 点：

```text
4 angle corners
4 angle-edge midpoints
angle center (5.25°,45°)
```

再允许基于 LF curvature/cutoff 选择最多 4 个 HF 点。总 HF angle pilot 不超过 13。

### 5.2 初始四维 LF 设计

使用 scrambled Sobol，seed：

```text
20260729
```

分批执行：

```text
Batch A = first 64 unique Sobol points
Batch B = expand to first 128 unique Sobol points only if preliminary gates require
```

增加 deterministic anchors：

- 几何四角 × 角度四角：16 点；
- 几何轴向点与角度边/中心组合：最多 16 点；
- 中心几何 49-point angle pilot；
- cutoff 两侧点：由 M2 解析/数值证据决定，最多 16 点。

去重后记录准确 solve count。不要为了达到名义数重复相同输入。

### 5.3 初始嵌套 HF training

第一阶段：

```text
16 nested HF points
```

必须包含：

- 4D domain boundary/corner coverage；
- Task001 两个已选 S 配置的中心及差分邻域；
- 0.5°端和 10°端；
- planar/conical/intermediate azimuth；
- 至少 4 个 maximin interior points。

若 preliminary surrogate 未达到扩展 Gate，增加到：

```text
24--32 total nested HF training points
```

所有 HF training 输入必须也有同源 LF result。

### 5.4 Frozen HF validation

在任何正式模型拟合前，使用独立 scrambled Sobol seed：

```text
20260730
```

冻结：

```text
initial = 8 points
final = 12--16 points
```

这些点：

- 同时计算 LF 和 HF；
- 永不进入训练；
- 永不用于超参数选择；
- 永不用于 adaptive acquisition；
- 只有 dataset/source bug 才能失效，失效必须重建完整 validation split。

### 5.5 Adaptive HF budget

最多 4 轮，每轮 4--8 点，总额：

```text
16--32 additional HF points
```

候选池至少为 4096 个冻结 Sobol 点。采集分数综合：

- LF-HF discrepancy uncertainty；
- multi-fidelity predictive uncertainty；
- PCE/GP disagreement；
- cutoff proximity；
- domain coverage/maximin distance；
- 对 h/w Fisher 信息的潜在贡献；
- corner/high-curvature evidence。

使用 diversity selection，禁止一批点全部聚集在同一小区域。

### 5.6 停止原则

预算是上限，不是必须使用完。验证 Gate 通过且连续两轮新增 HF 对关键指标改进小于冻结阈值时停止。若达到最大预算仍失败，不得继续无边界加点，应分析：

- cutoff/regime partition；
- schema/mesh discontinuity；
- output transform；
- LF-HF correlation；
- 参数域是否需要分区。

---

## 6. Surrogate 方法与模型选择

禁止模型动物园。只实现以下三类。

### 6.1 Sparse PCE / Chebyshev diagnostic baseline

目的：

- 判断响应是否全域低阶光滑；
- 给出可解释的敏感度和 interaction；
- 对无 cutoff 的平滑通道提供最简单基准。

规则：

- total degree 2 和 3；
- degree 4 只有 degree 3 明确欠拟合且样本/验证支持时允许；
- 不使用更高全局阶数掩盖局部非光滑；
- cutoff 跨越明显的通道应分 regime 或拒绝全局 PCE。

### 6.2 Single-fidelity Matérn GP baseline

```text
kernel = Matérn 5/2 with ARD
mean = constant or linear, selected by frozen training-only criterion
nugget = explicit numerical floor, not arbitrary noise absorber
```

使用标准化输入与输出。必须记录 hyperparameters、optimizer seed、multiple-start count 和收敛状态。

### 6.3 Production multi-fidelity candidate

对每个标量 target 或 latent component：

```text
y_H(x) = rho * y_L(x) + delta(x)
```

其中：

- `rho` 为每个通道/latent 的常数或受正则约束的简单系数；
- LF surrogate 使用 Matérn-5/2 ARD GP；
- discrepancy `delta` 使用独立 Matérn-5/2 ARD GP；
- HF 与 LF 输入必须嵌套；
- predictive variance 必须包含 LF 与 discrepancy 两部分；
- 不允许用 validation 点估计 rho 或 kernel。

### 6.4 多输出处理

首选流程：

1. 对 production power channels 分别建立标量模型；
2. 若通道数过多，再使用 PCA/latent GP；
3. PCA 只有在 frozen training 内完成；
4. latent reconstruction 在 frozen HF validation 上必须满足：
   - reconstruction error 显著小于 surrogate error budget；
   - retained variance 不低于 99.99%；
   - 弱通道不能因总方差小而被抹掉。

若 PCA Gate 不通过，回到 per-channel GP，不得强行降维。

### 6.5 功率 target transform

训练前在 training-only pilot 上比较并冻结一个变换：

```text
raw standardized power
log10(power + P_floor)
```

默认 `P_floor=1e-10`，但生产角度设计只使用达到测量/信息 floor 的通道。变换选择只依据 training cross-validation 和物理边界，不使用 frozen validation。

逆变换后：

- 只允许将数值 roundoff 级微小负值设为零；
- 大负值是模型失败；
- 所有 clipping 次数和幅度必须报告。

### 6.6 选择规则

- 如果 degree <=3 的 PCE 在 frozen HF validation 上全部通过，选择 PCE 作为最简单生产模型，GP 作为 uncertainty/active-learning 辅助；
- 如果 PCE 失败而 multi-fidelity GP 通过，选择 multi-fidelity GP；
- 如果 single-fidelity GP 与 multi-fidelity GP 同等准确，优先证据更简单、校准更好的模型；
- 如果所有模型在同一区域失败，先检查 regime/cutoff/数据，不得继续添加 NN/SVR/RF。

---

## 7. 训练环境与可复现性

### 7.1 本地 FEM 环境

不得为训练依赖破坏已资格化的 complex DOLFINx `.venv`。

### 7.2 工作站 ML 环境

建立独立 ignored 环境，例如：

```text
.venv-surrogate-ml
```

冻结依赖与版本，至少包括：

```text
Python
NumPy/SciPy
scikit-learn or equivalent PCE utilities
PyTorch
GPyTorch or chosen primary GP implementation
```

GPU 可用时使用 GPU；小规模 GP 的 CPU 结果必须数值一致到冻结容差。记录：

- GPU/driver/CUDA；
- framework versions；
- dtype；
- seed；
- CPU threads；
- peak GPU/host memory；
- training wall time；
- exact dataset/model identity。

生产 GP 默认使用 float64，除非 float32 与 float64 在固定 validation 上证明等价。

---

## 8. 验证指标和正式 Gate

所有 Gate 必须在模型拟合前写入 Case112 `expected.json`。不得看完 validation 后修改阈值来获得通过。

### 8.1 数值样本 Gate

每个 LF/HF sample 必须满足：

```text
true relative residual <= corresponding formal Gate
all Hybrid algebraic gates pass
interface/traction physical gates pass
abs(R+T+A_volume-1) <= formal Gate
raw order sums match reported R/T
mother response complete
zero swap
clean source stable
watchdog cleanup complete
```

### 8.2 Active production channel

默认 production power channel 需满足：

```text
max HF power over training/validation >= 1e-6
```

`1e-8 <= max power < 1e-6` 作为 research/weak channel 保存并报告，不默认用于 angle ranking。阈值不能用于删除高 Fisher 信息通道，例外需单独说明信噪比依据。

### 8.3 Frozen HF prediction Gate

使用以下报告，不得只给一个总 RMSE：

- per-channel MAE/RMSE/max；
- relative error for powers above floor；
- channel-range normalized RMSE；
- noise-normalized error under 0.5%、1%、2% provisional models；
- boundary vs interior；
- cutoff-near vs cutoff-far；
- aggregate R/T/A；
- LF、single-GP、multi-fidelity 三者对比。

首版接受目标：

```text
selected production channels:
    p95 absolute error / provisional 1% sigma <= 0.5
    max absolute error / provisional 1% sigma <= 1.0
    channel-range normalized RMSE <= 0.01

aggregates R/T:
    p95 absolute error <= 5e-4
    p95 relative error <= 0.5% when true value >= 1e-2

physical output:
    predicted power nonnegative except reported roundoff
    R >= 0, T >= 0
    A_balance = 1-R-T
    no domain/cutoff flag corruption
```

Provisional sigma：

```text
sigma_j = sqrt((relative_noise*y_j)^2 + (1e-6)^2)
```

这里 `1e-6` 是 Task002 surrogate design floor，不是实测仪器不确定度；必须在 model card 中注明。

### 8.4 Uncertainty calibration

至少报告：

- standardized residual；
- 50%、80%、90%、95% predictive interval coverage；
- interval width；
- cutoff/boundary coverage。

90% interval 的 empirical coverage 目标为 80%--98%。样本小导致统计不稳定时报告置信区间，不得只报 pass/fail。

### 8.5 Gradient Gate

由于 angle DOE 和反演需要导数，至少在 8 个 frozen HF/finite-difference audit 点检查：

```text
dy/dh
dy/dw
dy/dgrazing
dy/dazimuth
```

代理导数与 HF 中心差分方向 cosine 目标 `>=0.90`，重要通道不得系统性符号反转。靠近 cutoff 时单独报告，不以普通平滑导数 Gate 强行评价。

---

## 9. 连续角度 Fisher / DOE

### 9.1 Candidate grid

代理通过验证后，在不运行 FEM 的情况下扫描：

```text
grazing = 0.5:0.1:10.0 degree
azimuth = 0:1:90 degree
```

同时保留连续优化入口，但网格排名是可审查 authority。

### 9.2 Geometry robustness

不能只在中心点选角度。至少在：

```text
center + 4 geometry axial points + 4 geometry corners
```

以及可选 16--32 个 geometry Sobol prior 点上计算 Fisher。报告：

- nominal；
- prior-average；
- prior-worst-case；
- boundary；
- surrogate uncertainty penalty。

### 9.3 Total covariance

Fisher 中使用：

```text
Sigma_total = Sigma_measurement_assumed + Sigma_surrogate
```

不得假装 surrogate 没有误差。多通道相关性未知时至少报告：

1. diagonal provisional model；
2. validation residual empirical covariance；
3. sensitivity to covariance regularization。

### 9.4 Angle ranking

对每个候选角度和 angle bundle 计算：

```text
rank(Jw)
condition number
log det(F)
trace(F^-1)
rho_hw
sigma_h, sigma_w
channel contribution
surrogate uncertainty penalty
cutoff proximity
```

流程：

1. 排名所有 single angles；
2. 保留 top 100 且保持角度多样性；
3. 枚举 top-100 pairs；
4. 用 greedy/D-optimal 方法构建 3--4 angle bundles；
5. 优先最少配置且满足：rank=2、`|rho|<=0.90`、cond<=100；
6. 同等信息下优先远离 cutoff、实验易实现、代理不确定度低的配置。

### 9.5 HF 复核

最终推荐的：

- top 5 single angles；
- top 5 pair/bundle 中的 unique angles；

必须在中心和必要几何扰动点上用 HF 复核。优先从 adaptive HF budget 中分配，不得无限新增。

输出：

```text
recommended_single_angles.json
recommended_angle_bundles.json
illumination_design.md
```

这些是实验设计建议，不是实测仪器最终方案。

---

## 10. CLI/API 完成合同

至少实现：

```bash
python -m src.surrogate.cli predict \
  --model <model-package> \
  --height-nm 120 \
  --width-nm 17 \
  --grazing-deg 5 \
  --azimuth-deg 45 \
  --output prediction.json
```

输出包括：

```text
input and normalized features
model/dataset/version/hash
predicted R/T/A
selected diffraction powers
predictive uncertainty
power-carrying/availability mask
cutoff and domain diagnostics
status
```

角度设计入口：

```bash
python -m src.surrogate.cli rank-angles \
  --model <model-package> \
  --height-range 115 125 \
  --width-range 16 18 \
  --output-dir <dir>
```

Fail-closed 行为：

- P polarization request；
- wavelength !=13.5；
- exact 0° normalized R/T；
- out-of-domain geometry/angles；
- missing model/data hash；
- schema mismatch；
- prediction package not validated。

不得以 warning 后继续外推。

---

## 11. 执行里程碑

## M0：接收、仓库与双硬件审计

记录：

```text
root/git-dir/origin/branch/upstream/HEAD/status
Task001 Review V3 identity
local or workstation hardware role
FEM and ML environment identity
memory/swap/disk/GPU
current source vs master ahead/behind
```

不得自动 merge/rebase master。

## M1：Task002 schema、runner、dataset 和 checker

新增隔离模块，建议：

```text
src/forward_data/task002_schema.py
src/forward_data/task002_design.py
src/forward_data/task002_dataset.py
src/forward_data/task002_campaign.py
src/surrogate/
benchmarks/check_case112_task002.py
```

完成：

- S-only parameter schema；
- exact 0/域外 fail-closed；
- angle-to-wavevector transform；
- order-window/cutoff audit；
- canonical dataset arrays/manifests；
- split immutability；
- campaign resume/dedup；
- dataset checker；
- synthetic unit tests。

提交 clean implementation baseline。

## M2：四个 S anchor 与连续角域 pilot

先运行四个 center anchors：

```text
10°/0°/S
10°/90°/S
0.5°/90°/S
0.5°/0°/S
```

LF/HF 按任务规定执行并与 Task001 evidence 对照。随后运行 49 LF angle pilot 和 9--13 HF angle pilot。

M2 Gate：

- 所有正式点通过数值 Gate，或失败点有明确 root-cause/域分区 disposition；
- 响应、cutoff 和 channel availability 图完成；
- current order schema 被批准或在正式 dataset 前升级；
- 不存在未解释的网格拓扑跳变；
- S-Hybrid 在正式角域具备可计算性。

M2 未通过时停止，不得启动四维 bulk。

## M3：冻结设计和 split

生成并 track：

```text
lf_design.json
hf_initial_design.json
frozen_validation_design.json
candidate_pool.json
split_hashes.json
```

点表、seed、去重和边界角色必须明确。冻结后不得因模型结果不理想修改 validation 点。

## M4：本地 LF/HF 数据生成

顺序：

1. LF Sobol Batch A + anchors；
2. initial HF16；
3. frozen validation 8；
4. compact dataset/checker；
5. preliminary CPU surrogate diagnostic；
6. 只有证据要求时扩展 LF128、HF24--32、validation12--16；
7. 每次一个 FEM、zero swap、checkpoint/resume。

每 16 个 LF 或每 4 个 HF 更新 campaign manifest；不得修改已经完成的 raw artifacts。

## M5：数据冻结与工作站移交

完成：

- dataset checker；
- file hashes；
- dataset card；
- failed/controlled-stop inventory；
- compact package；
- 工作站复制后 hash recheck。

若当前执行环境仅是本地机器，允许以：

```text
status = ready_for_workstation_training
```

提交 checkpoint，但 Task002 尚未完成。

## M6：工作站代理训练

在独立 ML 环境：

1. fit PCE diagnostic；
2. fit single-fidelity GP；
3. fit multi-fidelity GP；
4. training-only model selection/hyperparameters；
5. frozen validation 只在最终评估阶段读取；
6. 保存完整 model package、state、normalization、hash、seed。

## M7：Frozen validation 与 adaptive HF

- 评估全部冻结 Gate；
- 生成 error maps；
- 若未通过，按 acquisition 选择 4--8 个 HF；
- 本地生成新 HF，更新 dataset version；
- 工作站重训；
- 最多 4 轮；
- validation 永不进入训练。

## M8：连续角度 DOE 与 HF 复核

完成 Section 9 全部内容，生成推荐 angle/bundle 和 HF 复核证据。

## M9：CLI、模型卡与 synthetic blind checks

至少建立 6--10 个隐藏 synthetic points：

- 使用 HF 生成 response；
- surrogate 预测前向响应；
- 可做局部优化 recovery sanity；
- 结果只称 Task002 blind qualification，不称正式反演。

模型卡必须声明：

- 域；
- S-only；
- 13.5 nm；
- dataset/source；
- error/coverage；
- cutoff/0°边界；
- 不支持 P、材料变化和外推。

## M10：结果闭环

必须生成：

```text
outcomes/summary.md
outcomes/test_summary.md
outcomes/continuous_angle_qualification.md
outcomes/sampling_design.md
outcomes/dataset_manifest_report.md
outcomes/surrogate_selection.md
outcomes/validation_report.md
outcomes/illumination_design.md
outcomes/model_card.md
response_v1.md
```

提交并仅推送当前分支，然后停止等待 ChatGPT Review。不得自行开始 Task003。

---

## 12. 测试要求

至少覆盖：

- Task000/001 regression；
- Case095/096、Case110/111 contracts；
- continuous angle conversion；
- exact zero and out-of-domain fail closed；
- order/cutoff analytic tests；
- fixed topology across representative 4D points；
- campaign dedup/resume；
- dataset shape/hash/split immutability；
- structural null vs zero；
- P request rejected；
- GP/PCE serialization round trip；
- CPU/GPU prediction consistency；
- gradient finite-difference checks；
- Fisher and angle-ranking synthetic tests；
- CLI output schema；
- compileall and `git diff --check`。

Ruff/formatter 只有在资格化环境已提供时运行；不得为了 lint 临时破坏 FEM 或 ML ABI。

---

## 13. Controlled-stop 条件

遇到以下任一情况必须保留证据并停止对应阶段：

- S-Hybrid 在正式角域出现未解释的数值失败；
- order schema 对全角域不完整；
- 传播级切换导致无法可靠分区；
- LF-HF 灵敏度严重反向或低相关；
- 本地资源接近 hard ceiling/swap；
- frozen validation 被污染；
- dataset 混源/hash 不一致；
- 最大 adaptive budget 后仍不满足 Gate；
- 代理在 cutoff/边界处不确定度失真；
- 工作站模型包无法重现。

Controlled stop 不等于失败，可以提交部分完成状态，但不得宣称 Task002 完成。

---

## 14. 最终回答的问题

Task002 完成后必须能够明确回答：

1. 在 `(h,w,grazing,azimuth)` 正式域内，S 偏振前向响应能否被可靠代理？
2. LF4 到 HF10 的 discrepancy 是否足够平滑、多保真是否真正节省 HF？
3. 哪些衍射功率通道在全角域稳定且对 h/w 有信息？
4. 代理误差相对于预设测量噪声是多少？
5. predictive uncertainty 是否校准？
6. 哪些单角度和 2--4 角度组合最适合区分 h 与 w？
7. 哪些角度靠近 cutoff 或模型边界，不应作为首选实验条件？
8. 用户怎样通过一条命令输入 h、w、掠射角、方位角并得到可信响应和不确定度？

只有这些问题都有 hash-bound 数值证据，Task002 才能进入 ChatGPT Review。
