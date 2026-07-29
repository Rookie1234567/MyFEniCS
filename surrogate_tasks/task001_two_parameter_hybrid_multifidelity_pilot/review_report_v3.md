# Task001 Review Report V3：S 偏振范围闭合与 Task002 放行

## 1. 审阅结论

```text
review_status = approved_with_scoped_solver_routing
Task001_S_scope = closed
Task001_P_Hybrid_scope = deferred_numerical_method_research
Task002_S_continuous_illumination = authorized
Task002_bulk_generation = authorized_only_after_Task002_preflight_and_pilot_gates
surrogate_training = authorized_in_Task002
production_inversion = not_authorized
```

用户已作出正式工程决策：第一版代理和反演只使用 S 偏振；P 偏振暂不进入代理训练。P 照明需要时使用已经验证的 Full3D assembly-time static-condensed direct route，当前 Hybrid-P 的 middle representation/energy-closure 问题作为独立数值方法研究延期，不再阻塞 S 偏振代理主线。

本报告覆盖并解除旧 `task002_dataset_plan.md`、`summary.md` 和 `response_v3.md` 中的 Task002 blocking 状态，但不删除或改写任何负证据。

---

## 2. Task001 接受的最终范围

### 2.1 待反演参数

```text
height_nm in [115, 125]
width_x_nm in [16, 18]
```

### 2.2 固定物理量

```text
wavelength_nm = 13.5
polarization = S for Task002 V1
period_x = 50 nm
period_y = 25 nm
width_y = period_y
current fixed material model
rectangular vertical-sidewall geometry
Floquet x/y + auxiliary DtN
```

### 2.3 连续实验配置目标

Task002 将把以下两个实验控制量作为前向代理输入，而不是反演未知量：

```text
grazing_deg in [0.5, 10.0]
azimuth_deg in [0, 90]
```

用户角度约定是相对于样品表面的掠射角，内部求解器继续使用：

```text
incident_theta_deg = 90 - grazing_deg
incident_phi_deg = azimuth_deg
```

精确 `grazing_deg=0` 对普通法向功率归一化的 R/T 是退化极限，不得由代理静默外推。Task002 正式训练域从 0.5° 开始；用户接口对 0°必须返回结构化的 zero-grazing-limit 状态，而不是伪造预测。

---

## 3. 接受的数值路线

### 3.1 S 偏振 low fidelity

```text
model_id = S_LF_HYBRID_P4_H10_M120
method = Hybrid modal-Schur memory-minimal + assembly-time static condensation
field degree = global p4
mesh target = h10
mode count = M120 per direction
MPI = 2
threads per rank = 1
```

Task001 五点 stencil 中，LF/HF 高度和宽度灵敏度方向 cosine 分别为 `0.999689` 与 `0.999998`，计算时间与峰值内存显著低于 HF。LF 允许存在可学习的 bias，但不得冒充高保真。

### 3.2 S 偏振 high fidelity

```text
model_id = S_HF_HYBRID_P6_H10_M120
method = Hybrid modal-Schur memory-minimal + assembly-time static condensation
field contract = p5 trace / p6 interior exact sequence
mesh target = h10
mode count = M120 per direction
MPI = 2
threads per rank = 1
```

p6/h7.5 已被资源 Gate 分类为 `controlled_stop_resource_projection`，本地 16 GB 机器不再尝试。

### 3.3 P 偏振

```text
Task002 V1 surrogate input = S only
P input = fail closed / route-not-trained
validated direct reference = Full3D assembly-time static-condensed p4/h10
Hybrid-P = deferred
```

F2--F5 的 independent Full3D direct references 证明 P 配置物理上可解；这些记录保留为数值参考。它们不进入 S-only dataset，也不允许与 Hybrid S 数据静默混合。

---

## 4. 接受的 Task001 证据

- S-HF10 nominal 与 Case095/096 冻结显著通道闭合；
- S-LF4/HF10 五点灵敏度方向一致；
- `10°/0°/S + 10°/90°/S` 在 HF 上的噪声加权 Jacobian rank=2、condition number `1.2208`、`rho_hw=-0.1479`；
- F1 `0.5°/0°/S` reciprocal trace coordinate/degree/quadrature 根因已修复，未放宽原 Gate；
- fixed-order mother-response schema `task001.fixed-n0-orders.v2` 已批准；
- Case110 原有 37 个 pass 和 Case111 negative/direct-reference evidence 保持 hash-bound；
- Task001 没有生成正式 4D 数据集、没有训练代理、没有执行正式反演。

---

## 5. Task002 授权边界

Task002 可以执行：

1. S 偏振连续角域的求解器资格化；
2. 四维输入 `(height, width, grazing, azimuth)` 的 LF/HF 设计与数据生成；
3. 固定物理身份的 mother responses 与训练特征构建；
4. PCE/Chebyshev 诊断基准、Matérn GP 和多保真 discrepancy surrogate；
5. 独立 HF 验证和自适应 HF 加点；
6. 基于 surrogate + Fisher information 的照明角度设计；
7. 可调用的 forward-surrogate CLI/API。

Task002 不可以执行：

- P 偏振 surrogate；
- Hybrid-P 数值架构改造；
- 材料、侧壁角、圆角、粗糙度或波长反演；
- 真实实验参数反演；
- 正式 Bayesian posterior/MCMC；
- 将本支线合入 master。

正式反演放入后续 Task003。

---

## 6. Task002 启动前必须重新冻结的内容

Task002 不得直接把 Task001 PDE baseline 当成生产 dataset source。实现连续角域、数据 schema、campaign 和训练代码后，必须：

1. 提交一个 clean Task002 implementation baseline；
2. 在该 SHA 上重新运行并通过最小 S anchor：
   - `10°/0°/S` center；
   - `10°/90°/S` center；
   - `0.5°/90°/S` center；
   - 修复后的 `0.5°/0°/S` center；
3. 与 Task001 hash-bound evidence 比较；
4. 冻结一个 dataset source SHA、parameter schema 和 observable schema；
5. 通过连续角域 pilot 后，才允许正式 LF/HF campaign。

---

## 7. 完成状态

```text
Task001 = CLOSED for S-polarized surrogate scope
Task002 = AUTHORIZED under its own staged gates
Task003 = NOT STARTED
P-Hybrid research = DEFERRED
```
