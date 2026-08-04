# Task005 Review Report V2：M5R 最终验收、DOE lock 批准与 Task006 固定照明结构代理移交

## 1. 审阅结论

本轮正式批准并接受 M5R 的 derived-only 结果：

```text
M2 weak-channel ranking stability audit        = approved
illumination-count 5% tradeoff                 = approved
derived sensitivity supplement                 = approved
Task001 baseline interpretation addendum        = approved
Fisher parameterization / hash schema           = approved
Case134 independent checker                     = pass
new FEM in M5R                                  = 0
raw sensitivity package                         = unchanged
historical V1 lock                              = unchanged
```

本轮正式批准 Task005 的科学结论：

```text
best robust single             = A05
best robust pair               = A05 + A07
best robust triple             = A05 + A07 + A09
information-best quadruple     = A05 + A06 + A07 + A09
M4-validated operational set   = A05 + A07 + A09
```

其中：

```text
A05 = grazing 2 deg, azimuth 0 deg
A06 = grazing 2 deg, azimuth 45 deg
A07 = grazing 2 deg, azimuth 90 deg
A09 = grazing 4 deg, azimuth 60 deg
```

`DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json` 的数值、数据与科学内容获得批准，但其文件状态仍为 `review_ready`。Task005 在进入最终 closeout 前还需完成一个不运行 FEM 的 provenance/state closure，见第 7 节。

当前状态冻结为：

```text
forward_solver_sha        = fdf961545f217d620e22800f2704ae9913a6d270
raw_dataset_id            = task005_discrete_angle_hw_sensitivity_p5_ny4_v1
derived_dataset_id        = task005_discrete_angle_hw_sensitivity_p5_ny4_derived_contract_v1
nominal geometry          = h=120 nm, w=17 nm
selected steps            = delta_h=1.25 nm, delta_w=0.25 nm
new FEM M1-M4             = 93
new FEM M5R               = 0
formal inversion          = false
Task004 blind24            = not run
Task005 scientific status = approved pending metadata closeout
recommended next task     = Task006 fixed-illumination h/w surrogate
```

---

## 2. M5R 补齐了 Review V1 的全部科学缺口

### 2.1 M2 弱通道稳定性已闭合

M2 仅比 M1 多保留功率位于 `1e-5` 到 `1e-3` 之间的弱衍射级。最新审计表明：

```text
weak-channel observations = 28
angles containing them     = 13 / 16
nominal power range        = 1.27707e-5 to 8.18441e-4
```

这些功率与 N1/N2 的绝对噪声底处于相同量级，因此 M2 继续作为 diagnostic contract 是合理的。

M2/N1 单独排名时，最佳 pair/triple/quad 可发生变化；但 M2 在 N1/N2 最坏情形下的最佳 single、pair、triple、quad 与 M0/M1 robust 选择完全一致。各规模 robust 与 M2 worst-case 排名的 top-k overlap 与 Spearman 均高度一致：

```text
single Spearman = 1.000000
pair   Spearman = 0.999681
triple Spearman = 0.999902
quad   Spearman = 0.999940
```

因此可以冻结：

> M2 弱通道不会推翻正式 M0/M1 robust 选择，但 isolated N1 变化必须作为弱通道警告保留。

### 2.2 照明数量语义已正确分开

5% 少照明规则已真正执行：

```text
single / pair  = 0.541718, not a tie
pair / triple  = 0.683999, not a tie
triple / quad  = 0.770081, not a tie
```

因此：

- 四角度 `A05+A06+A07+A09` 是 1–4 角度范围内的 information-global-best；
- 三角度 `A05+A07+A09` 不是全局 Fisher 最大值；
- 三角度是 best robust triple，也是唯一完成规定 G1–G3 nonlinear recovery 的集合；
- 下一阶段采用三角度，是经过验证的 cost-information compromise，而不是对 5% 规则的静默覆盖。

该语义现在清楚且可接受。

### 2.3 派生数据 supplement 已补齐

新的 companion package 确定性保存：

```text
perturbed_inputs.npy
M0_Dh.npy / M0_Dw.npy
M0 N1/N2 noise arrays
M1 ragged derivatives and N1/N2 noise arrays
M2 ragged derivatives and N1/N2 noise arrays
channel contracts / tiers
source record identities
```

它明确绑定原始 v1 manifest 与 file hashes，并声明：

```text
source_raw_package_modified = false
generated_without_fem       = true
new_fem_count               = 0
```

原始数据包仍是唯一 forward-data authority；supplement 只是便携派生层。

### 2.4 Task001 基准解释已闭合

A14+A15 在 M0 下仍可满秩，但在 M1 robust-order 合同中，每个角度只剩少量主通道，h/w 方向近乎共线，最坏条件数达到约 `5.65e5`。M2 弱通道可改善该诊断，但不能改变 robust lock。

这应解释为 observable、通道阈值和噪声合同的变化，而不是 Task001 被简单判错。

---

## 3. Task005 DOE lock 的正式语义

批准后的 Task005 lock 必须同时保留三层结果：

### 3.1 最佳双角度

```text
A05 + A07
```

它是成本最低的强 pair，可作为实验最小配置或降级配置，但 Fisher 分数显著低于三角度，且尚未单独执行规定的三几何 nonlinear recovery。

### 3.2 下一任务的 operational 三角度

```text
A05 + A07 + A09
```

这是下一阶段结构代理的正式照明合同，原因是：

1. best robust triple；
2. M0/M1 和 N1/N2 均稳健；
3. M2 worst-case 仍为 rank 1；
4. G1–G3 nonlinear recovery 全部通过；
5. 相比四角度减少一次照明和每个几何一次 Full3D 求解。

### 3.3 信息最优四角度

```text
A05 + A06 + A07 + A09
```

它应保留为未来实验资源允许时的高信息配置。当前不把它作为 Task006 primary，是因为尚未完成与三角度同等的 nonlinear validation，且会将每个几何的 forward-data 成本由 3 次增加到 4 次。

---

## 4. Task006 不得误读的边界

Task005 的批准不等于：

```text
正式反演完成
实验噪声已经标定
CRLB 等于实际测量精度
全域 h/w 非线性关系已验证
P 偏振、波长、材料或更多参数已支持
```

N1/N2 仍是 provisional diagonal DOE scenarios。下一阶段必须将模型误差、数值误差和未来实验误差分开。

Task006 应只建立：

```text
(h,w) -> fixed responses at A05/A07/A09
```

不得重新将 grazing/azimuth 作为连续输入，也不得恢复 Task004 任意角度代理。

---

## 5. 下一步正式路线：Task006 固定三照明 h/w 代理

批准建立：

```text
surrogate_tasks/task006_fixed_illumination_hw_surrogate/
```

### 5.1 输入与固定条件

输入：

```text
height h in [115,125] nm
width  w in [16,18] nm
```

固定：

```text
wavelength = 13.5 nm
incident polarization = S
angles = A05, A07, A09
forward = Full3D p5/h10/Ny4
```

### 5.2 输出合同

两个生产合同必须独立建模和评分：

```text
S0 aggregate:
    per angle R_total, T_total, A_balance
    composition-constrained reconstruction

S1 robust order-total:
    Task005 M1 frozen channel identities
    nonnegative power prediction
    no aggregate/order duplicate in one inversion likelihood
```

M2 weak channels只作诊断，不得决定正式代理资格。

### 5.3 冻结 7x7 几何母网格

```text
h nodes = [115,117.5,118.75,120,121.25,122.5,125]
w nodes = [16,16.5,16.75,17,17.25,17.5,18]
```

共 49 个几何点。

初始 training = 37 geometries：

1. 全部 24 个边界点；
2. 现有三角度均完整的 8 个中心附近点：
   - (120,17)
   - (118.75,17), (121.25,17)
   - (120,16.75), (120,17.25)
   - (118.75,16.75), (118.75,17.25), (121.25,17.25)
3. 四个 coarse-axis 点：
   - (117.5,17), (122.5,17)
   - (120,16.5), (120,17.5)
4. 一个缺失对称象限点：
   - (121.25,16.75)

剩余 12 个内部网格点冻结为 geometry-blind validation，不得在模型选择前读取其响应。

预计 initial training 新 FEM：

```text
24 boundary geometries x 3 angles                = 72
4 coarse-axis geometries, only A05 missing       = 4
1 missing-quadrant geometry x 3 angles            = 3
initial new FEM total                              = 79
```

已有 Task005 records 必须按完整 tuple/source/config/schema/hash 精确复用；不能只按文件名或近似参数复用。

### 5.4 有限模型集合

只比较：

```text
baseline A = tensor Chebyshev / Legendre degree 2-4
baseline B = local RBF
primary    = Matérn-5/2 ARD exact GP
optional   = low-order trend + GP residual
```

不使用神经网络，不开展无边界 kernel/model zoo。

### 5.5 训练评价

必须采用 geometry-grouped outer CV：一个 held-out geometry 的三个角度全部同时留出，禁止按单角度行随机切分。

至少报告：

```text
per-target NRMSE / p95 / max
noise-normalized surrogate discrepancy under N1/N2
physics ledger / composition
cross-fitted uncertainty coverage and width
held-out synthetic h/w recovery
boundary vs interior error
```

最终资格必须同时包含 forward accuracy 和参数恢复，而不是只看平均 R/T 误差。

### 5.6 阶段边界

Task006 第一轮只授权：

```text
M0  Task005 final closeout + design/reuse checker
M1  initial 37-geometry training data generation
M2  training-only surrogate comparison and CV
```

本轮不授权：

```text
12 blind geometry FEM
主动学习新增几何
正式 Bayesian inversion
实验数据拟合
Task007
```

M2 完成后必须停止等待审阅。只有 training-only 证据通过，下一轮才决定是否直接 model lock + blind validation，或进行最多一轮 geometry active learning。

---

## 6. 需要特别监控的科学风险

1. **固定 M1 通道跨几何域稳定性**：若某个 frozen robust channel 在部分 h/w 点不再 power-carrying、缺失或低于可测阈值，必须 fail closed 或重新定义生产合同；不得用零填充。
2. **边界非线性**：Task005 nonlinear checks只覆盖中心附近 ±1.25/±0.25 nm；Task006 边界点是第一次检验完整 h/w 范围。
3. **数值离散误差**：本代理首先逼近 p5/h10/Ny4 operational FEM，不得把 GP 方差解释成连续 Maxwell 真值误差。
4. **多角度相关噪声**：N1/N2 仍假设对角协方差。正式实验反演前需另做 covariance calibration。
5. **照明数量选择**：三角度是 operational choice；四角度信息更高。Task006 结论不得写成四角度无价值。

---

## 7. Task005 最终 metadata closeout（无新 FEM）

在开始 Task006 M0 前，Codex 必须先完成：

```text
TASK005_FINAL_STATUS.json
TASK005_APPROVED_CLOSEOUT.md
README / outcomes summary status update
```

最终状态文件不得改写 V2 lock，而应引用其 file SHA，并分别记录：

```text
M0-M4 implementation SHA = d24395b377259da129a81384f88d8a4ad74602d2
M5R generator commit SHA = 25327ab792a580fb198f07e59564c84149e952a1
M5R source file SHA256   = SHA256(src/surrogate/doe/m5r.py)
review authority          = review_report_v2.md
V2 lock status by review  = approved
Task006 M0-M2             = authorized
```

这是 provenance 修正，不是数值返工。不得修改 V1/V2 lock 或原始/派生数据包。

---

## 8. 给 Codex 的执行边界

```text
请先完成 Task005 metadata closeout，不运行任何 FEM；随后进入 Task006 M0-M2。

Task006 只生成37个training geometry的三固定角度数据并完成training-only CV；
不得运行12个blind geometries，不得主动加点，不得开始正式反演。

任何未解释的前向失败、通道身份变化、数据混源或资源异常均立即停止。
```
