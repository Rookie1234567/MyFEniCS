# Task001 Codex Response V2

## Review V1 定向修正完成

本轮只修正 compact diffraction 母响应 schema。没有重跑任何 FEM/PDE，现有 numerical
source `68f4f9bc92de6cd7ec2896755ef210fb182280a1`、HF10、LF4、HF7P5
`controlled_stop_resource_projection`、37 个 pass、5 个失败及全部 solver-theta=80° 结果均保持。

用户确认的正式范围是相对样品表面的 `grazing_deg=0.5--10°`，内部
`solver theta=90°-grazing`。Review V1 覆盖旧 task 中 theta=70°/80° 的候选描述；本轮没有
改成 20° grazing，也没有补算 solver theta=70°。

## Observable schema v2

schema 从 raw execution 使用的 `task001.fixed-n0-orders.v1` 升级为派生 compact
`task001.fixed-n0-orders.v2`。每 run 固定 18 个 grouped `(side,m,n=0)` orders：reflection/
transmission 各 9 个，m=`0,-1,-2,-3,-4,-5,-6,-7,+1`。

每个 sample/order 保存：

```text
incident_polarization
side = reflection / transmission
port_side = top / bottom
m, n
kx, ky, kz = {re, im}, unit 1/nm
dispersion_propagating
power_carrying
components.s/p.amplitude_re / amplitude_im
components.s/p.power / power_carrying
order_total_power
```

`order_total_power` 由非 null 的 S/P component power 求和。非功率携带 component/order 继续
使用 `power=null`；传播但恰为零的功率保持 `0.0`。`dispersion_propagating` 与
`power_carrying` 分离，因此真实 0.5° lossy substrate 的 bottom m0 仍表现为
`dispersion=false, power_carrying=true` 并正确计入 T。

`n!=0` 不进入固定训练向量，只保存：

```text
n_nonzero_reflection_power_sum
n_nonzero_transmission_power_sum
n_nonzero_max_abs_amplitude
```

37 个通过记录的最大值分别为 `1.4160391e-7`、`1.5919775e-7`、`1.8922744e-4`。

## Raw 重建与 checker

新增 `compact_diffraction_responses.json`，包含 37 个 v2 mother responses。每个 response
绑定原 `execution.json` 和 `solver_record.json` SHA-256、parameter hash、raw schema v1、
compact schema v2 与 numerical source。

`kx/ky` 从冻结的 Floquet 参数与 m/n 重建；`kz` 使用 top/bottom outgoing 方向，并将 analytic
beta 与 raw `beta_per_nm` 逐 component 核对。边界复振幅直接来自 raw
`outgoing_amplitude_at_boundary`，只拆为 real/imag，没有 phase unwrap。checker 从 raw table
重新验证：

- S power + P power = order total；
- grouped S/P wavevector/dispersion identity 一致；
- wavevector complex JSON 字段完整；
- reflection/transmission 的 n!=0 leakage 分开；
- raw order sums 与 reported R/T 一致；
- lossy power/dispersion 语义不退化；
- 42 artifact count、37 pass/5 fail 与 raw hashes 不变。

原始 numerical values 和 raw artifacts 未修改。

## 照明与 Task002 边界

selected bundle 仍为：

```text
(10° grazing, 0° azimuth,  S)
(10° grazing, 90° azimuth, S)
```

P 是当前 Hybrid numerical qualification failure，不表示 P 在真实物理中不存在或实验不可测。
Task001 的 1% noise 仍只是 DOE 假设，不是仪器误差或 Bayesian posterior。

Task002 plan 已改为显式使用 v2 母响应 schema，并保持独立 S/P power feature 选择；不会把
S、P、S+P 同时作为独立反演观测。

## 未执行

- 未进入 Docker；
- 未运行或重跑 FEM/PDE；
- 未开始 49 点数据生成；
- 未训练 surrogate；
- 未执行正式反演。

完成提交和推送后停止等待 Review V2。
