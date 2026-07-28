# Task001 Review Report V1

## 1. 审阅结论

```text
review_status = targeted_changes_required
valid_existing_numerical_evidence = retain
illumination_range = user_authorized_as_implemented
Task002_bulk_generation = not_yet_authorized
surrogate_training = not_authorized
production_inversion = not_authorized
required_next_action = complete_observable_schema_and_response_v2
```

Task001 已完成本地 Hybrid 高/低保真资格化、p6/h7.5 资源判定、固定拓扑、照明 pilot 和高度/宽度局部可辨识性验证。现有正式数值证据保留，不应无理由重跑。

用户已明确澄清：希望使用的是**相对样品表面的掠射角不超过 10°**。因此当前实现的：

```text
grazing_deg in [0.5, 10.0]
solver theta = 90° - grazing_deg
```

是用户授权的正式范围，不再要求改成 20° 掠射角，也不要求补算 solver theta=70°。

该澄清覆盖 Task001 原任务书中 `theta=70°/80°` 的旧候选描述。当前 `0.5°/10° grazing × 0°/90° azimuth × S/P` campaign 可作为 Task001 实际权威候选池。

目前只剩一个 blocking 项：fixed-order compact observable schema 尚未完整保存后续代理、实验 observation 和反演所需的母响应字段。Codex 只需完成该项并提交 `response_v2.md`；不得开始 Task002 的 49 点批量生成。

---

## 2. 已接受并冻结的结果

### 2.1 High fidelity

接受：

```text
selected_high_fidelity = HF10
method = Hybrid static / modal-schur-memory-minimal
field contract = p5 trace / p6 interior exact sequence
mesh = h10, axis counts (6,3,14)
M = 120
MPI = 2
numerical source = 68f4f9bc92de6cd7ec2896755ef210fb182280a1
```

名义点 `height=120 nm, width=17 nm, grazing=10°, azimuth=0°, S`：

- true residual `2.4838e-12`；
- interface E/H `1.6395e-7 / 3.8958e-5`；
- energy closure `1.5568e-10`；
- `R/T/A/Avolume = 0.0007628815 / 0.6027016340 / 0.3965354845 / 0.3965354847`；
- process-tree peak RSS `3,287,891,968 B`；
- swap `0 B`；
- Case095/096 12 个冻结通道最大功率/边界复振幅绝对差 `2.052e-12 / 2.183e-12`。

HF10 可作为 Task002 的 high-fidelity 模型。它仍是 best-available discrete reference，不是 continuum truth。

### 2.2 p6/h7.5

接受：

```text
HF7P5 = controlled_stop_resource_projection
PDE launched = false
```

central 预测 `11,588,731,106 B` 超过 launch ceiling，conservative 预测 `15,878,719,347 B` 超过 hard ceiling。未使用 swap、OOC 或 OOM 冒险。本机无需再次尝试 p6/h7.5。

### 2.3 Low fidelity

接受：

```text
selected_low_fidelity = LF4 global p4/h10/M120/MPI2
```

在 `grazing=10°, azimuth=0°, S` 五点 stencil 上：

- `cosine(dy/dh)=0.999689`；
- `cosine(dy/dw)=0.999998`；
- top-80% Fisher 通道无符号反转；
- mean wall/HF `0.19155`；
- mean RSS/HF `0.31765`。

LF4 作为多保真低层通过。LF-HF bias 必须由 discrepancy model 显式学习，不得把 LF 冒充 HF。

### 2.4 照明范围与候选结果

用户授权范围为：

```text
wavelength = 13.5 nm fixed
grazing_deg = 0.5--10.0
azimuth_deg = 0--90
incident polarization = S or P
```

Task001 实际代表点：

```text
grazing = 0.5°, 10°
azimuth = 0°, 90°
polarization = S, P
```

接受当前实际结果：

- `10°/0°/S`：通过，选为 planar configuration；
- `10°/90°/S`：通过，选为 conical configuration；
- `0.5°/90°/S`：能求解，但单独使用时 `rho=-0.9839`，不选；
- `0.5°/0°/S` 与 P：trace-map consistency failure；
- 三个 P 候选：当前 Hybrid numerical qualification failure。

P 的失败只表示当前计算路径在这些配置下未通过 interface/energy/trace Gate，不表示真实物理中 P 偏振不存在或不能测量。

### 2.5 局部可辨识性

接受的最小 configuration bundle：

```text
C1 = grazing 10°, azimuth 0°,  S
C2 = grazing 10°, azimuth 90°, S
```

HF 结果：

| 观测 | rank | cond(Jw) | rho(h,w) |
|---|---:|---:|---:|
| reflection-only | 2 | 1.3217 | 0.000182 |
| reflection + transmission | 2 | 1.2208 | -0.14793 |

这证明名义点附近的功率响应包含两个独立局部参数方向。2,000 次 1% provisional noise 抽样只属于 DOE sanity，不得解释成真实仪器精度或正式 Bayesian posterior。

### 2.6 负结果、资源与测试

接受：

- 37 个 measured pass 全部同一 numerical source；
- 全部通过记录 solver Gate 通过、zero swap、watchdog cleanup 完成；
- 5 个失败记录和日志 hash 保留；
- targeted suite `68 passed, 4 skipped`；
- Case110 checker、compileall、`git diff --check` 通过；
- Ruff 在资格化 `.venv` 中不可用，未虚假宣称通过。

---

## 3. 唯一 Blocking Finding：compact diffraction 母响应不完整

Task001 当前 `orders.py` 已正确完成：

- 固定 order identity；
- 不使用动态 top-N；
- `power_carrying` 与 `dispersion_propagating` 分离；
- 有损基底中正 outward Poynting flux 正确计入功率；
- 非功率携带模式写 `power=null`，不与零功率混淆；
- raw order sum 与端口 R/T 做一致性检查。

但是，当前 compact row 主要只有：

```text
side, m, n, polarization,
propagating/power_carrying,
dispersion_propagating,
power,
outgoing_amplitude_at_boundary
```

尚未完整保存后续代理与真实 observation 所需的母响应：

1. `kx, ky, kz` 的复数 identity；
2. 明确的 incident polarization；
3. 复振幅稳定拆分为 real/imag；
4. 同一 `(side,m,n)` 下 outgoing S/P 两个分量的分组；
5. `order_total_power = power_s + power_p`；
6. `n!=0` reflection 与 transmission 分开的功率泄漏；
7. `n!=0` 最大复振幅。

当前单一 `n_nonzero_leakage_power` 不足。

---

## 4. Required Task001 Correction Scope

Codex 下一轮只执行以下定向修正。

### M8.1 升级 observable schema

建议升级为新的版本，例如：

```text
sample-level:
  incident_polarization

order-level:
  side = reflection / transmission
  m, n
  kx = {re, im}
  ky = {re, im}
  kz = {re, im}
  dispersion_propagating
  power_carrying
  components:
    s:
      amplitude_re
      amplitude_im
      power
    p:
      amplitude_re
      amplitude_im
      power
  order_total_power

leakage:
  n_nonzero_reflection_power_sum
  n_nonzero_transmission_power_sum
  n_nonzero_max_abs_amplitude
```

不要求机械使用上述 JSON 形状，但必须保证同等物理信息和稳定 identity。

必须继续保持：

- 固定 `m=(0,-1,-2,-3,-4,-5,-6,-7,+1), n=0`；
- 非功率携带模式 `power=null`；
- `dispersion_propagating` 与 `power_carrying` 分离；
- 不把 S、P、S+P 三者同时作为独立反演观测；
- 复振幅保存 real/imag，相位只作为派生量；
- `n!=0` 不进入训练向量，只作泄漏诊断。

### M8.2 既有 PDE 不重跑

该修正属于 compact extraction/schema 层。默认从现有 raw PDE artifacts 重新提取，不重跑 37 个已通过 FEM。

必须：

- 保留 raw artifact hash；
- 记录旧/new observable schema version；
- 从 raw order table 独立重算新 compact fields；
- checker 验证 `power_s + power_p = order_total_power`；
- checker 验证分侧 leakage；
- checker 验证 raw R/T 一致性；
- 不修改已有 raw numerical values。

只有发现 raw record 本身缺少无法恢复的必要字段时，才允许补跑最小数量的代表点，并在 `response_v2.md` 说明原因。不得重跑整个 campaign。

### M8.3 文档澄清

更新：

```text
surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/
  README.md
  outcomes/summary.md
  outcomes/test_summary.md
  outcomes/illumination_identifiability.md
  outcomes/task002_dataset_plan.md
  response_v2.md
```

明确写明：

- 用户要求的是掠射角 `0.5--10°`；
- `solver theta = 90° - grazing`；
- 本 Review 覆盖旧 task 中 `theta=70°/80°` 的候选表述；
- selected bundle 为两个 `10° grazing / S` 配置；
- P 是 numerical qualification failure，不是物理不存在；
- Task001 的 1% noise 只是 DOE 假设。

### M8.4 测试

至少完成：

- Task000/001 targeted tests；
- order schema synthetic tests；
- 真实 lossy record extraction tests；
- grouped S/P power与 order total一致性；
- wavevector/re-im serialization round trip；
- 分侧 `n!=0` leakage checker；
- Case110 从 raw artifacts 重建 compact records；
- Case095/096 contract regression；
- compileall；
- `git diff --check`；
- Ruff 仅在资格化环境已有时运行。

结束后：

```text
worktree = clean
branch/upstream = unchanged
response = response_v2.md
Task002 data generation = not started
surrogate training = not started
inversion = not started
```

---

## 5. Task002 暂定方向

完成上述 schema 修正并通过 Review V2 后，可开启 Task002。

暂定 configuration bundle：

```text
(10° grazing, 0° azimuth,  S)
(10° grazing, 90° azimuth, S)
```

暂定模型：

```text
HF = HF10 global p6/h10/M120/MPI2
LF = LF4 global p4/h10/M120/MPI2
```

暂定数据设计：

```text
LF Chebyshev-Lobatto 7x7 = 49 geometries × 2 configurations = 98 solves
initial HF anchors = 9 geometries × 2 = 18 solves
adaptive HF = 6--10 geometries × 2
frozen validation HF = 6--8 geometries × 2
```

代理方法不做模型大比武：

```text
primary = multi-fidelity Matérn GP / autoregressive discrepancy
          y_H = rho_c y_L + delta_c(h,w)

baseline = low-order Chebyshev/PCE
```

若低阶 PCE 在冻结验证点上满足噪声归一化误差 Gate，可以采用更简单的 PCE；否则采用 multi-fidelity GP。

---

## 6. Review V2 通过条件

只有以下事项全部满足，才批准 Task002：

1. 用户授权的 `0.5--10° grazing` 与 schema/docs 一致；
2. fixed-order 母响应包含 wavevector、复振幅 real/imag、S/P功率和 order total；
3. `n!=0` leakage 按 reflection/transmission 分开，并保存最大复振幅；
4. lossy propagation/power 语义保持正确；
5. 既有 raw PDE 结果未被静默改写；
6. checker 从 raw artifacts 重算新 compact records；
7. Task002 plan 使用最终 observable schema；
8. 没有提前开始 bulk generation、surrogate training 或 inversion。
