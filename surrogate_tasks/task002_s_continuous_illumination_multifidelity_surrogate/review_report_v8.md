# Task002 Review Report V8

## 1. 审阅结论

```text
review_status = dataset_approved_surrogate_task_authorized
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
M4E_Ny4_production = approved_and_retain
production_dataset = approved
production_dataset_id = task002_m4e_p5_ny4_112_v3
training_split = approved_96
frozen_validation_split = approved_16_and_remains_sealed
production_forward_identity = Full3D_static_uniform_N1curl_p5_h10_Ny4
Task002_forward_data_scope = closed
Task003_surrogate_training = authorized
angle_DOE = not_authorized_until_surrogate_validation_and_discretization_gate
production_inversion = not_authorized
required_next_action = execute_Task003_dataset_transfer_training_and_validation
```

Case119 已完成 Review V7 的全部核心要求。当前已经建立的不是关系数据库或 SQL database，而是一个可复现、可校验、适合数值建模的 **compact array dataset**：

```text
inputs.npy
aggregates.npy
order_amplitudes.npy
order_powers.npy
power_carrying_mask.npy
train_indices.npy
frozen_validation_indices.npy
+ manifest / order identities / sample records / file hashes
```

该数据集满足进入代理模型构建阶段的必要条件。批准新建 Task003，用于数据包移交、训练集内部建模、单保真代理资格化和一次性冻结验证。Task003 不得执行正式角度 Fisher 排名或参数反演。

---

## 2. 已接受的生产前向身份

接受并冻结：

```text
model_id = S_PROD_FULL3D_STATIC_P5_H10_NY4
solver_route_id = full3d_static_uniform_n1curl_p5_h10_ny4
implementation/source SHA = 10e3356ba8364286a452077f71d7e3b92ea24cd5
element = uniform N1curl p5
mesh logical counts = (Nx,Ny,Nz) = (6,4,14)
backend = assembly-time static condensation
MPI = 2
threads per rank = 1
wavelength = 13.5 nm
incident polarization = S
observable schema = task002.fixed-n0-orders.v3
parameter schema = task002.s-p5-ny4-production-parameters.v3
campaign schema = task002.s-p5-ny4-design-campaign.v4
dataset schema = task002.s-p5-ny4-single-fidelity-dataset.v3
fidelity semantics = best_available_operational_high_fidelity
```

Ny3 已硬隔离。Case117 的 56 个 Ny3 measured-pass 只能作为诊断证据，不得进入任何 Task003 训练、验证、标准化、PCA、超参数初始化或误差统计。

---

## 3. M4E 修正审阅

### 3.1 Tangential projection 合同

接受 `_mode_projection_from_solution` 的切向合同修正。独立 q63 direct tangential projection 与 DtN auxiliary coefficients 的最大绝对差为：

| 点 | 最大差 |
|---|---:|
| 原失败几何 Ny3（诊断） | `1.923e-13` |
| 原失败几何 Ny4 | `1.094e-12` |
| 中心几何 54.50° Ny4 | `4.814e-13` |
| 10° / 45° Ny4 | `9.108e-14` |

全部远低于 `1e-10` Gate。Case118 中 reported outgoing-P discrepancy 确认为旧诊断在分子中错误包含 `Ez*conj(ez)`、但分母仍使用 tangential norm 所导致；它不构成 production auxiliary modal amplitudes 错误的证据。

### 3.2 Ny4 enhanced canary

接受：

- 16/16 四维 domain corners 全部通过；
- 原 Case117 training index 40 在 Ny4 下通过；
- center geometry、原 grazing 下 54.25°/54.50°/54.75° 三点泄漏均降至舍入量级；
- residual、energy、fixed/raw ledger、runtime topology、element identity、zero swap、cleanup 与 compact output 全部通过；
- 原 leakage Gate 未放宽。

### 3.3 设计身份未改变

接受原冻结四元组完全不变：

```text
training 96 tuple hash = b01f4f3b27b5b5e0466fb1d620ffe504677f6c24468ac9e955ac45fac39570fa
validation 16 tuple hash = e5733173c2c55d4d5ef8e660fc63019bf61e78063a3bd24cb0488dc6c435e50b
candidate 4096 tuple hash = a9831ffc1055732660bee859382f623e8558560634d9ac98702cfe355ff09fcd
audit 8 tuple hash = 049b973bbed7de05e46e8045fac11461ac80641f08aa464bb81d7aa72611a2aa
```

只更新了 source/model/route/topology/schema/combined identity。

---

## 4. Campaign 与数据集完整性

### 4.1 Campaign

接受：

```text
training expected/measured_pass = 96/96
frozen validation expected/measured_pass = 16/16
production samples = 112
numerical failures = 0
skipped failures = 0
formal source SHA count = 1
```

manifest 保存 113 次 attempt，其中 training index 4 的 attempt 1 因用户暂停被记录为 `interrupted_retryable`：signal 143、zero swap、cleanup complete、无 formal record。attempt 2 从头执行并通过。该中断不是 numerical failure，未产生重复 dataset sample。

资源接受：

```text
peak RSS = 6,209,052,672 bytes
peak PSS = 6,004,024,320 bytes
all production attempts zero swap = true
all cleanup complete = true
```

### 4.2 Compact dataset

接受：

```text
dataset_id = task002_m4e_p5_ny4_112_v3
sample count = 112
training = 96
frozen validation = 16
missing = 0
extra = 0
file count = 10
exact design coverage = true
```

主要数组：

| 数组 | shape | dtype | 语义 |
|---|---:|---|---|
| `inputs.npy` | `(112,4)` | float64 | height, width, grazing, azimuth |
| `aggregates.npy` | `(112,4)` | float64 | aggregate responses |
| `order_amplitudes.npy` | `(112,22,2,2)` | float64 | order × S/P × real/imag |
| `order_powers.npy` | `(112,22,2)` | float64 | order × S/P power |
| `power_carrying_mask.npy` | `(112,22,2)` | bool | structural availability |
| `train_indices.npy` | `(96,)` | int64 | training split |
| `frozen_validation_indices.npy` | `(16,)` | int64 | sealed validation split |

22 个固定 order 为 reflection/transmission 两侧的 `m=-7..+3,n=0`；structural null 使用 NaN + false mask，不得在 Task003 中静默 zero-fill。

独立 exact-design checker 已确认：

- 每个 training/validation tuple 恰好出现一次；
- train/validation 无交集；
- 一个 source SHA；
- Ny4-only route；
- observable v3-only；
- formal residual/energy/leakage/ledger/resource/runtime-topology Gate 全部通过；
- sample records、arrays、split、order identity 与 file hashes 全部通过；
- 8 个 discretization-audit points 不在 production dataset 中。

Case119 checker 6/6 通过。

---

## 5. “数据库是否建立”的准确回答

是，**用于代理训练的数值数据集已经建立并通过资格化**。

但需要准确区分：

1. Git 远程分支保存的是代码、设计表、compact evidence、manifest、hash 和 checker；
2. 实际 `.npy` 训练数组位于本地 ignored artifact：
   ```text
   benchmarks/artifacts/cases/119/m4e/compact_dataset/
   ```
3. 从远程仓库重新 clone 不会自动获得该二进制数据包；
4. Task003 必须先建立 deterministic dataset package、SHA256 和 workstation 接收复核；
5. 不得通过重新运行 112 个 FEM 来代替正常的数据移交。

---

## 6. 进入代理训练前仍需保持的边界

### 6.1 Frozen validation 必须继续封存

16 个 validation FEM 已经计算，但其响应尚未用于 feature、transform、kernel、PCA rank、模型类型或超参数选择。Task003 在模型与训练协议完全冻结前不得读取 validation target arrays。

应从代码层面提供默认 train-only loader；unlock validation 必须是显式、一次性、可记录的命令。

### 6.2 当前数据表示 operational solver，不是 continuum truth

当前 forward identity 是 best-available operational p5/Ny4 模型。现有 8 个 discretization-audit design 尚未执行。因此：

- 不阻塞训练一个“复现 p5/Ny4 前向模型”的代理；
- 阻塞将 GP uncertainty 直接解释为完整物理不确定度；
- 阻塞在没有 discretization term 的情况下发布最终角度 DOE 或反演置信区间。

Task003 必须在模型 metadata 中单独报告：

```text
surrogate_interpolation_uncertainty
discretization_uncertainty_status = pending / measured
measurement_uncertainty = not part of training data
```

### 6.3 结构性 mask 和传播级切换

不得把 NaN 直接交给回归器，也不得将非功率携带通道改成普通零标签。传播/功率携带状态应由 analytic order identity 或 dataset mask 管理；模型只在有定义的通道/区域内训练。

### 6.4 96 个训练点是否足够仍需由训练内验证决定

112/112 FEM pass 只证明数据正确，不证明 96 点一定足以满足代理误差要求。Task003 可以在训练内部交叉验证不足时，使用冻结 4096 candidate pool 做主动加点；不得以 frozen validation 结果选点。

---

## 7. Task003 授权范围

批准新建：

```text
surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/
```

Task003 可以执行：

1. compact dataset deterministic packaging、transfer、hash verification；
2. train-only loader、mask/identity/feature audit；
3. sparse Chebyshev/PCE 低阶诊断基准；
4. single-fidelity Matérn-5/2 ARD Gaussian Process；
5. aggregates 与 fixed-order power surrogate；
6. 条件式 complex-amplitude surrogate；
7. training-only cross-validation、uncertainty calibration；
8. 模型与协议冻结后，一次性读取 16 点 validation；
9. 必要时基于 training/candidate uncertainty 的受控 active learning；
10. 可调用的 forward-surrogate CLI/API 和模型包。

Task003 不可以执行：

- 将 validation 用于模型选择或反复调参；
- 神经网络、随机森林、SVR 等无边界 model zoo；
- P incident surrogate；
- wavelength/material/sidewall/roughness 扩维；
- 正式角度 Fisher 排名；
- 正式参数反演、Bayesian posterior 或 MCMC；
- 将本分支合入 master；
- 修改 production FEM source identity 或把不同 source SHA 的样本混入 dataset v3。

---

## 8. Task002 完成状态

```text
Task001 S-scope = closed
Task002 forward solver qualification = closed
Task002 Ny4 production data generation = closed
Task002 dataset = approved
Task003 surrogate training = authorized
angle-design task = not started
formal inversion task = not started
P-Hybrid research = deferred
```
