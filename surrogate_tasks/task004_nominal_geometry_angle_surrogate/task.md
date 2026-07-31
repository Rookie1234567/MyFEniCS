# Task004 任务书：固定中心几何的二维角度代理

## 1. 目标

固定：

```text
height_nm = 120.0
width_x_nm = 17.0
wavelength_nm = 13.5
incident polarization = S
```

建立：

```text
(grazing_deg, azimuth_deg)
    -> R_total / T_total / A_balance
    -> fixed-order outgoing S/P powers
    -> predictive uncertainty
    -> analytic propagation/cutoff status
```

输入范围：

```text
grazing_deg in [0.5, 10.0]
azimuth_deg in [0.0, 90.0]
```

该模型只回答固定中心几何下的任意角度响应，不直接执行高度/宽度反演或 Fisher 角度排名。

## 2. 开始前

完整阅读根目录与 `surrogate_tasks/AGENTS.md`、Task002 `review_report_v8.md`/`response_v8.md`、Task003 `review_report_v3.md`/`response_v4.md`、本目录 README 和本任务书。

确认当前分支、upstream 和干净工作树；Task003 Round 3 不得运行，Task003 原 16 个 frozen-validation target 继续封存。

## 3. 正式前向模型

所有 Task004 正式样本统一使用：

```text
model = Full3D static uniform N1curl p5
mesh = h10, (Nx,Ny,Nz)=(6,4,14)
solver = assembly-time static condensation
MPI = 2, threads/rank = 1
observable = task002.fixed-n0-orders.v3
output = compact_surrogate_record
```

每个样本必须通过：

```text
true residual <= 1e-9
|R + T + A_volume - 1| <= 1e-7
n!=0 leakage Gate
raw/fixed power ledger
actual topology identity
zero swap
cleanup complete
```

未通过样本不得进入数据集。

## 4. 新 SHA 资格化

Task004 实现完成后提交 clean implementation SHA，并生成 `TASK004_FORWARD_BASELINE.json`。选择至少 5 个 Case119 Ny4 anchor，在当前 SHA 下重算并比较：

```text
R/T/A absolute difference <= 1e-10
shared order power difference <= 1e-10
shared complex amplitude difference <= 1e-9
same element/topology/observable identity
```

若数值核心变化或 anchor 不闭合，受控停止。旧记录只作为 reference，不混入新数据集。

## 5. 数据设计

### 5.1 Training：96 点

先冻结 80 个 Ny4 structured angles：

```text
grazing = [0.5,0.75,1,2,4,6,8,10]
azimuth = [0,5,10,15,20,30,45,60,75,90]
```

再从独立 4096-point Sobol candidate pool 中，使用解析 cutoff 距离、低掠射标记和空间填充规则冻结 16 个 enrichment angles。要求覆盖低掠射、普通内部、高方位角及 cutoff-near 区域，且不读取任何 validation response。

### 5.2 Blind validation：24 点

使用独立 seed：

```text
16 all-domain Sobol
4 low-grazing stratified
4 cutoff-near stratified
```

与 training 无交集。模型锁定前，validation response 不得被训练、特征选择、画图或主动学习读取。

### 5.3 历史数据边界

- Case115 的 80-angle map 是旧 Ny3 身份，只能用于趋势和差异报告；
- Task003 数据同时变化 h/w，不能删除几何列后作为二维角度数据；
- Task003 frozen validation 不能转作 Task004 validation。

## 6. Dataset

建立新的 Ny4-only dataset ID。每个记录仍完整保存固定 h/w、角度、波长、偏振、source SHA、模型/网格/求解器身份、R/T/A、fixed-order amplitudes/powers/mask、残差、功率账本、资源和 hashes。

compact arrays 至少包含：

```text
angles.npy
fixed_parameters.json
aggregates.npy
order_amplitudes.npy
order_powers.npy
power_carrying_mask.npy
sample_ids.npy
train_indices.npy
sealed_validation_indices.npy
```

不传播通道采用 `NaN + false mask`。独立 checker 必须验证 96/24 精确覆盖、无重复/交集、单一 SHA、Ny4/p5/observable-v3-only、所有样本 measured-pass 和文件 hash 可重建。

## 7. 输出表示

### Aggregate

继续使用 composition latent：

\[
z_R=\log((R+\epsilon)/(A+\epsilon)),\quad
z_T=\log((T+\epsilon)/(A+\epsilon)),
\]

经 softmax 恢复，保证 `R,T,A >= 0` 且 `R+T+A=1`。

### Fixed-order powers

使用：

```text
side total R/T + masked active-channel fractions
```

保证每侧通道和严格等于 R/T。通道按 training-only 冻结为 primary、secondary、structural-null；弱通道失败不得被隐藏。

复振幅本轮只保留数据和 diagnostic，不作为硬资格目标。

## 8. 有限模型候选

只比较：

```text
B1 = structured/local interpolation baseline
B2 = tensor Chebyshev degree 2–5
P1 = Matérn-5/2 ARD exact GP
P2 = analytic propagation-region local GP（仅当P1误差明确集中于不同解析区域时）
```

特征候选仅限：

```text
F1 = scaled(grazing, azimuth)
F2 = scaled(kx/k0, ky/k0)
F3 = F1 + signed analytic cutoff distances
```

GP 使用 CPU、8–16 个确定性初值和 jitter `[1e-10,1e-8,1e-6]`，保存每折 kernel、length scales、LML、warnings、wall time 和 peak RSS。不得扩展成无边界 model zoo。

## 9. 交叉验证

同时执行：

1. 固定的 space-filling 5-fold OOF；
2. spatial holdout：低掠射带、高方位角带、cutoff-near 带、普通内部窗口；
3. region-wise error 和 uncertainty coverage。

每个 OOF 点保存 truth、prediction、error、std、fold/region、cutoff distance 和 nearest-training distance。

## 10. 首轮 Gate

这些是角度响应图/筛选级标准，不是最终反演级标准。

Aggregate 每个目标：

```text
OOF NRMSE <= 0.01
OOF p95 absolute error <= 0.01
max absolute error <= 0.03
all region p95 absolute error <= 0.02
composition physics exact
```

不确定度：

```text
95% OOF interval empirical coverage in [0.90,0.99]
region coverage reported
```

Primary power channels：

```text
NRMSE <= 0.03
p95 absolute error <= 0.01
sidewise ledger error <= 1e-12
mask agreement = 100%
```

## 11. 模型锁与 blind validation

Training-only CV 与 spatial holdout 通过后，创建 `ANGLE_MODEL_SELECTION_LOCK.json`，锁定数据 hash、特征、输出变换、模型、kernel/jitter、uncertainty calibration、seeds 和代码 SHA。随后一次性读取 24 个 blind validation response，不得根据结果重新调模型。

## 12. 条件式主动学习

若 96 点未通过，但模型明显优于基准、误差集中于可解释区域且 uncertainty 可用于排序，可从 candidate pool 中增加最多 16 个角度。选择综合 uncertainty、OOF regional error、cutoff proximity、nearest distance、primary-channel importance 和多样性。

最多形成 112 training。若仍未通过，停止等待审阅，不得自行再加第二轮。

## 13. 任意角度接口与图

通过 blind validation 后实现：

```python
AngleSurrogate.predict(grazing_deg, azimuth_deg)
```

返回固定物理身份、R/T/A mean/std、fixed-order powers/mask、region/cutoff distances、nearest-training distance、model/dataset/code identity 和 warning。域外输入必须拒绝。

生成 dense prediction maps：

```text
grazing step <= 0.05°
azimuth step <= 0.5°
```

包括 R/T/A mean/std、主要 order、cutoff topology、nearest-data distance 和 validation errors。所有图必须标注为 surrogate prediction，不得冒充 FEM truth。

## 14. 交付与停止

建立：

```text
benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/
src/surrogate/angle/
```

任务目录至少交付：

```text
outcomes/design.md
outcomes/forward_baseline.md
outcomes/dataset_report.md
outcomes/model_selection.md
outcomes/spatial_holdout.md
outcomes/blind_validation.md
outcomes/angle_maps.md
outcomes/resource_summary.md
outcomes/test_summary.md
response_v1.md
```

完成后提交并推送当前唯一代理分支，停止等待 ChatGPT 审阅。不得自行开始高度/宽度灵敏度代理、Fisher 排名、反演、P 入射、波长或材料扩展。
