# REVIEW REPORT 20260703：R/T/A 输出整理与体吸收积分

## 1. 审查范围

本报告审查分支：

```text
codex/20260702-rta-output-volume-absorption
```

本报告属于任务目录：

```text
docs/task002_rta_output_volume_absorption/review_report.md
```

审查重点包括：

1. 是否完成四类 R/T/A 输出拆分：`port`、`probe_eh_fourier`、`net_flux`、`volume_absorption`。
2. 是否新增材料体吸收积分 `A_volume`。
3. 是否完成 13.5 nm EUV 的 Stage 4A / Stage 4B 验证运行。
4. 当前结果是否可作为物理 benchmark。
5. 下一轮最应该优先修复的问题。

---

## 2. 总体结论

本轮任务在“后处理输出结构”和“体吸收接口”层面基本完成：

- 新增了 `src/postprocessing/rta_3d.py`。
- 新增了 `power_summary.csv`。
- 新增了正式输出文件：

```text
port_power.json
probe_power.json
flux_power.json
volume_absorption.json
```

- 新增了理论说明，迁移后路径为：

```text
notes/theory/THEORY_RTA_AND_VOLUME_ABSORPTION.md
```

- 跑完了 9 个正式 case：

```text
Stage 4A flat-layer: 10 / 5 / 3 nm
Stage 4B zero-contrast: 10 / 5 / 3 nm
Stage 4B real Si block: 10 / 5 / 3 nm
```

但是，本轮结果也明确暴露出严重问题：

```text
port / probe_eh_fourier / net_flux / volume_absorption 四类功率口径没有通过一致性检查。
```

因此，本分支目前适合保留为“后处理接口重构与问题暴露”的中间分支，不能作为 Stage 4 物理 benchmark 合并依据。下一轮应优先修复 flat-layer power consistency，而不是继续扩展复杂光栅物理案例。

---

## 3. 积极发现

### 3.1 输出结构已经明显变清晰

现在每个 Stage 4 result folder 计划输出：

```text
run_summary.json
power_summary.csv
port_power.json
probe_power.json
flux_power.json
volume_absorption.json
```

这比旧的 `R_total/T_total/A_balance` 混合输出更清楚。特别是 `power_summary.csv` 一行一个 method，可以直接比较四类结果。

### 3.2 四类方法的角色已经写清楚

理论文档中已经明确：

| method | role | meaning |
|---|---|---|
| `port` | primary | DtN port 辅助模态振幅给出的主 R/T/A |
| `probe_eh_fourier` | cross_check | probe plane 上 E/H Fourier directional fitting |
| `net_flux` | diagnostic | sampled Poynting flux 总能流检查 |
| `volume_absorption` | absorption_check | 材料区体吸收积分 |

这正是后续做物理验证需要的结构。

### 3.3 A_volume 已经有初版实现

`A_volume` 当前实现为：

```text
P_abs = integral 0.5*k0^2*Im(epsilon_r)*|E_total|^2 dV
A_volume = P_abs / incident_power_code_units
```

并且做到了：

- 使用 `epsilon_r = n^2`；
- 使用 `Im(epsilon_r)`，而不是 `Im(n)`；
- 分 grating / substrate 输出；
- 排除空气和 PML；
- 记录 `A_volume_total` 与 `A_port_balance` 等差值。

这一步是有价值的，但公式归一化仍需在下一轮审查和验证中确认。

### 3.4 zero-contrast 对照有价值

zero-contrast block 和 flat-layer 在同一网格下几乎给出相同结果。这说明：

```text
block geometry / material tag / mesh split 本身大概率没有引入额外虚假散射。
```

因此，当前最主要问题不应优先怀疑几何 tag，而应优先怀疑共同的端口、场、功率归一化和 probe/flux 后处理口径。

---

## 4. 主要数值发现

### 4.1 所有 consistency checks 都失败

outcomes 中 9 个 case 的 consistency pass 均为 false。典型问题包括：

- `port` 与 `probe_eh_fourier` 的 R/T 差异极大；
- `port` 在 5 nm / 3 nm 出现 `T > 1` 和负 `A_balance`；
- `net_flux` 在 5 nm / 3 nm 出现 `R > 1` 和负 `T`；
- `A_volume` 与 `A_port_balance` 无法闭合。

这说明当前不是单纯“输出格式问题”，而是 Stage 4 功率口径之间存在实质性不一致。

### 4.2 flat-layer 10 nm 暴露 probe_eh_fourier 重大异常

flat-layer 10 nm 中：

```text
port:            R ≈ 1, T ≈ 0, A ≈ 0
net_flux:        R ≈ 1, T ≈ 0, A ≈ 0
volume_absorp.:  A ≈ 0
probe_eh_fourier: R ≈ 0.0037, T ≈ 0, A ≈ 0.996
```

这几乎可以确定 `probe_eh_fourier` 在该场景下存在严重后处理问题，可能来自：

- 入射场扣除错误；
- up/down 方向分离错误；
- `H = curl(E)/(i*k0*mu)` 的符号约定不一致；
- probe z 相位因子错误；
- 复 beta 或 vertical_sign 使用不一致；
- 有损 substrate 中 modal power 归一化不一致。

### 4.3 flat-layer 5 nm / 3 nm 暴露 port/net_flux 也不可靠

flat-layer 5 nm / 3 nm 中 port 出现：

```text
T_port > 1
A_port_balance < 0
```

net_flux 出现：

```text
R_flux > 1
T_flux < 0
```

这说明不能继续默认 `port` 一定是可信主结果。下一轮必须用解析 flat-layer benchmark 来重新校准 port、probe、net_flux 和 volume_absorption。

### 4.4 A_volume 有初步趋势，但归一化还未被证明

real Si block 中 `A_volume_total` 随网格细化从 10 nm 的近零增长到 5/3 nm 的几个百分点量级，并且能够分出 grating/substrate 吸收。这个方向是有用的。

但是当前 `R_port + T_port + A_volume_total - 1` 仍有明显误差，说明 `A_volume` 尚未和 port 功率口径闭合。原因可能是：

- `A_volume` 的系数应为 `0.5*k0*Im(epsilon_r)|E|^2` 还是 `0.5*k0^2*Im(epsilon_r)|E|^2` 需要重新从当前 code units 推导；
- 积分区域与 flux/port 边界截面不完全一致；
- `E_total` 的端口入射场或背景场构造不一致；
- port power 本身尚未正确。

下一轮必须把 A_volume 的归一化与 analytic Poynting flux balance 一起验证。

---

## 5. 最可能需要排查的根因

### 5.1 Flat-layer analytic reference 缺失

当前结果没有把 Stage 4A flat-layer 与解析 Fresnel / layered reference 做逐项对照。没有解析参考，就无法判断 port、probe、net_flux 哪个错。

必须新增 analytic flat-layer benchmark，包括：

```text
R_ref
T_ref at chosen bottom plane
A_ref between top/bottom planes
analytic E/H on probe planes
analytic volume absorption
```

### 5.2 DtN port incident/outgoing amplitude 定义可能有问题

重点检查：

- top incident projection 是否与 top outgoing amplitude 在同一相位和归一化下；
- top source traction 符号是否正确；
- upward/downward `vertical_sign` 与 outward normal 是否一致；
- `mode.power_per_unit_amplitude` 在 lossy substrate 中是否可直接用于 T；
- auxiliary row/column 是否使用了正确的复共轭和 phase sign。

### 5.3 probe_eh_fourier 方向分解明显异常

对 analytic field 直接喂给 probe 后处理，必须能恢复解析 R/T。若不能，先修 probe，不要用 FEM 结果调试。

### 5.4 net_flux 符号约定需要确认

当前定义：

```text
R_from_net_flux = 1 + top_flux_outward / incident_power
T_from_net_flux = bottom_flux_outward / incident_power
```

这个公式在正常情况下是合理的，但 5/3 nm 出现 `T_flux < 0`，说明 sampled H、normal、bottom traveling direction 或 total field 都可能有问题。

### 5.5 A_volume code-unit 系数需要重新推导

当前代码使用：

```text
0.5*k0^2*Im(epsilon_r)*|E_total|^2
```

需要从当前代码中的 `H_code = curl(E)/(i*k0*mu)` 和 `S_code = 0.5*Re(E x H*)` 推导体耗散项。很可能应检查是否应为：

```text
0.5*k0*Im(epsilon_r)*|E_total|^2
```

最终以 analytic plane wave attenuation / flux difference 验证，而不是只靠公式直觉。

---

## 6. 合并建议

暂不建议把该分支合并进 master。

原因：

1. 输出整理代码有价值，但当前 numerical outcomes 全部 consistency failed。
2. `A_volume` 公式和归一化尚未闭合验证。
3. Stage 4 port/probe/net_flux 之间存在严重矛盾。
4. 若现在合并，后续 master 会包含一套尚未可信的 power postprocess 口径。

建议在同一分支继续完成下一轮修复任务：

```text
docs/task003_stage4_power_consistency/task.md
```

等 flat-layer analytic benchmark 和四类功率一致性通过后，再考虑合并。

---

## 7. 立即下一步

下一轮任务应聚焦一个目标：

```text
用 Stage 4A flat-layer analytic benchmark 校准 port / probe_eh_fourier / net_flux / volume_absorption 四类功率口径。
```

不要先扩展复杂 grating；不要再大量跑 real block；先让 flat-layer 的解析场、FEM 场、port/probe/flux/volume 闭合。只有 flat-layer 过关，zero-contrast 和 real block 才有意义。
