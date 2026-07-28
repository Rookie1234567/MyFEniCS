# Task001 结果总览

## M9 V3 受控停止更新

用户已暂停进一步开发。F1 的 trace-map consistency 根因已修正；F2--F5 的独立 Full3D
p4/h10 reference 全部通过 residual/energy Gate，确认 P 配置物理有效，但当前 Hybrid P
路径仍未通过原 interface/energy Gate。因此本文件此前的 Task001“完成”表述只描述 M8/V2
历史状态，不能解释为 M9 已完成。当前正式状态是 `controlled_stop_incomplete`，Task002
继续阻塞。详见 `five_configuration_failure_correction.md` 与 `response_v3.md`。

## 结论

Task001 完成了有限元前向封装、多保真资格化与局部可辨识性确认；没有生成
Task002 的 49 点数据，没有训练代理模型，也没有执行正式反演。正式 PDE 全部绑定
clean numerical baseline
`68f4f9bc92de6cd7ec2896755ef210fb182280a1`，使用原生 WSL `.venv`、complex128、
MPI2、每 rank 1 thread、单任务串行和 10.5 GiB watchdog；未进入 Docker。

用户输入已分为两类：

| 类别 | 含义 | Task001 字段 | 是否反演 |
|---|---|---|---|
| `configuration` | DOE 可控制的实验配置 | 13.5 nm、掠射角、方位角、S/P | 否 |
| `geometry` | 样品待反演参数 | height 115--125 nm、width 16--18 nm | 是 |

用户角度采用相对样品表面的掠射角，内部换算为
`solver theta = 90° - grazing`、`phi = azimuth`。接口合同允许掠射角
0.5--10°、方位角 0--90°、S/P；但 Task001 的数值证据只资格化了下文列出的
S 条件，不能据此宣称整个连续角域和 P 已可靠。
Review V1 与用户确认覆盖旧 task 中 solver `theta=70°/80°` 的候选表述；没有改成
20° grazing，也没有补算 solver theta=70°。

## 保真度选择

| 模型 | p / h / M / MPI | 状态 | 资源/数值结论 | 决策 |
|---|---|---|---|---|
| HF10 | global p6 / h10 / M120 / 2 | measured pass | nominal 8,464 local rows/side；6,156,616 NNZ/side；23,023,456/23,139,232 factor NNZ；3,287,891,968 B；253.971 s；residual `2.48e-12` | selected HF |
| HF7P5 | global p6 / h7.5 / M120 / 2 | `controlled_stop_resource_projection` | optimistic 9,393,977,051 B；central 11,588,731,106 B；conservative 15,878,719,347 B；PDE 未启动 | 不选，资源 Gate 阻止 |
| LF4 | global p4 / h10 / M120 / 2 | measured pass | 5 点平均 wall/HF `0.19155`，RSS/HF `0.31765`；高度/宽度灵敏度 cosine `0.999689/0.999998` | selected LF |
| LF5 | global p5 / h10 / M120 / 2 | not run | LF4 已通过最低和期望 Gate | 不需要 |
| M160 | p6 / h10 / M160 | not run | Task001 正式身份冻结在 M120；可选项不满足必要性 | 不需要 |

HF10 nominal 与 Case095/096 的 12 个显著通道比较中，最大功率绝对差
`2.052e-12`，最大边界复振幅绝对差 `2.183e-12`。它证明 current-source
nominal 与冻结 best-available 离散参考一致；该参考不是 continuum truth。

LF4/HF10 的 R/T/A bias 平滑且可学习：5 点最大绝对差分别为
`R=0.0012214`、`T=0.0062201`、`A_balance=0.0050971`；top-80% Fisher
通道没有灵敏度符号反转。

## 正式运行汇总

| 分类 | 数量 | 结论 |
|---|---:|---|
| measured pass | 37 | 同一 baseline；全部 solver gates pass；全部零 swap；watchdog 清理完成 |
| physical Gate failure | 3 | 0.5°/90°/P、10°/0°/P、10°/90°/P |
| trace-map consistency failure | 2 | 0.5°/0°/S 与 P，在生成 solver record 前 fail closed |
| HF7P5 projection stop | 1 个模型决定 | PDE 未启动，不属于数值求解失败 |

37 个通过记录的最坏值为 residual `2.942e-11`、interface-E `2.397e-5`、
interface-H `1.626e-3`、`|energy closure|=2.843e-7`、peak RSS
4,181,561,344 B；仍全部满足各自正式 Gate。

## 照明筛选与可辨识性

首轮 8 个端点配置只做离散代表点筛选，不是连续扫描：

| grazing / azimuth / pol | LF nominal 状态 | 结论 |
|---|---|---|
| 10° / 0° / S | pass，9 geometry | selected planar |
| 10° / 90° / S | pass，9 geometry | selected conical |
| 0.5° / 90° / S | pass，9 geometry | 单独 R+T `rho=-0.9839`，高度/宽度强耦合，不选 |
| 0.5° / 0° / S | failed | trace map `6.988e-8 / 6.308e-8`，不放宽 Gate |
| 0.5° / 0° / P | failed | trace map `1.375e-7 / 1.376e-7`，不放宽 Gate |
| 0.5° / 90° / P | physical failed | E `0.8993`、H `0.02020`、energy `8.729e-4` |
| 10° / 0° / P | physical failed | E `0.6008`、H `0.02167`、energy `2.203e-5` |
| 10° / 90° / P | physical failed | E `0.6005`、H `0.01924`、energy `2.566e-5` |

选定最小 `configuration` bundle：

1. `grazing=10°, azimuth=0°, polarization=S`；
2. `grazing=10°, azimuth=90°, polarization=S`。

| 数据/观测 | rank | cond(Jw) | rho(h,w) | provisional sigma h/w at 1% |
|---|---:|---:|---:|---:|
| LF reflection-only | 2 | 1.3250 | `-5.79e-5` | 0.03536 / 0.04685 nm |
| LF reflection+transmission | 2 | 1.8386 | -0.2659 | 0.02844 / 0.01660 nm |
| HF reflection-only | 2 | 1.3217 | `1.82e-4` | 0.03150 / 0.04164 nm |
| HF reflection+transmission | 2 | 1.2208 | -0.1479 | 0.02648 / 0.02320 nm |

HF 最大“同一通道同时贡献高度和宽度信息的较小份额”为 0.0808，远低于本任务采用的
0.90 dominance 判据。0.5%、1%、2% provisional noise 下，LF selected bundle 的
R+T cond 为 1.660--1.921、`rho=-0.193..-0.375`，没有灾难性退化。这些噪声是 DOE
设计假设，不是实测仪器精度。

HF 局部线性 sanity recovery 的中心点严格回到零；两个 `(+0.5,+0.1)` 和
`(-0.5,-0.1)` nm target 无噪声精确回代。2,000 次 1% noise 抽样的标准差约为
height 0.0264--0.0267 nm、width 0.0236--0.0237 nm，bias 均小于 0.001 nm。
这不是代理模型或正式 Bayesian inversion。

角点相对局部线性误差最大为：10°/0°/S `0.0791`、0.5°/90°/S `0.0321`、
10°/90°/S `0.1617`。Task002 应使用 GP/多保真 discrepancy 和额外 HF anchors，
不能用高阶全局多项式掩盖非线性。

## Observable v2 母响应与有损模式语义

旧 raw execution 的 observable identity 为 `task001.fixed-n0-orders.v1`；不改写 raw 的前提下，
37 个通过记录已重建为 `task001.fixed-n0-orders.v2`。每侧固定保存 9 个
`m=(0,-1,-2,-3,-4,-5,-6,-7,+1), n=0` grouped orders，共 18 条/run：

- sample-level `incident_polarization`；
- `side=reflection/transmission`、`port_side=top/bottom`、m/n；
- `kx/ky/kz={re,im}`，单位 `1/nm`；
- `dispersion_propagating` 与 `power_carrying`；
- `components.s/p = {amplitude_re, amplitude_im, power, power_carrying}`；
- `order_total_power = S power + P power`；
- 分开的 `n_nonzero_reflection_power_sum`、`n_nonzero_transmission_power_sum` 与
  `n_nonzero_max_abs_amplitude`。

有损基底中 `dispersion_propagating=false` 但 Poynting 功率为正的模式仍正确计入 T；
非功率携带 component/order 的 `power=null`，传播但数值为零的功率仍保留 `0.0`。
37-run 最大 n!=0 reflection/transmission leakage 为 `1.416e-7 / 1.592e-7`，最大复振幅
`1.892e-4`；这些值只作数值诊断，不进入训练向量。复振幅只保存 real/imag，phase 为派生量。

## Task002 冻结计划

| 阶段 | geometry count | configuration count | physical solve count |
|---|---:|---:|---:|
| LF Chebyshev-Lobatto 7x7 | 49 | 2 | 98 |
| initial HF anchors | 9 | 2 | 18 |
| adaptive HF | 6--10 | 2 | 12--20 |
| independent HF validation | 6--8 | 2 | 12--16 |
| total planned | 70--76（跨保真计数） | 2 | 140--152 |

Task001 没有执行这些 solves。材料仍固定；未来把材料加入 `configuration` 或反演参数时，
必须升级 schema、重新生成对应数据并重新训练，不能让当前模型隐式外推。

## 证据与变更

- compact records：`benchmarks/cases/110_surrogate_two_parameter_pilot/records/`；
- v2 mother responses：`records/compact_diffraction_responses.json`（37 runs，raw hash-bound）；
- raw ignored artifacts：`benchmarks/artifacts/cases/110/`；
- checker：`benchmarks/check_case110_task001.py`；
- 参数/拓扑/提取/资源/DOE：`src/forward_data/`；
- p6 surface-form roundoff Gate 修正及测试：condensation 实现与对应测试；
- 本目录 outcomes 与 `response_v2.md`。

数值 baseline 与后处理/文档 HEAD 有意分离：前者固定 PDE 身份，后者只修正有损 order
提取语义、重算证据并写报告，不再启动 PDE。

## Selective merge 分组

| 组 | 内容 | 数值行为 |
|---|---|---|
| production numerical/core | p6 static-condensation surface roundoff Gate | 只稳定理论消元的 roundoff 判定；实际 residual/interface/energy Gate 不变 |
| reusable forward-data | schema、configuration/geometry、topology、order extraction、resource、identifiability | 新增隔离入口；ordinary default 不变 |
| checker/benchmark | Case110 config、checker、watchdog/campaign glue | 只读重算与受控执行 |
| compact evidence/docs | records、outcomes、response、development progress | 不改变数值 |
| research/negative evidence | 5 个失败照明与 HF7P5 projection stop | 保留，不提升为 production pass |
| do-not-merge as defaults | P、0.5°/0°、HF7P5、LF5、M160、Task002 bulk | 未资格化或未运行 |
