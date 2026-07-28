# Case110：13.5 nm 两参数 Hybrid 多保真 pilot

本 case 只执行 Task001 的小规模资格化与可辨识性 pilot。它不会生成 Task002
冻结的 49 点 low-fidelity design，也不会训练 surrogate 或执行反演。

## 固定范围

- 输入封装分为 `configuration` 和 `geometry`：前者是 DOE 可控的实验配置，
  后者是待反演的样品参数；
- geometry：height 115--125 nm，width-x 16--18 nm；
- wavelength：13.5 nm fixed；period 50 x 25 nm 和材料保持
  `target_stage4_config` 权威；
- illumination 用户合同：掠射角连续 `0.5--10 deg`、方位角连续
  `0--90 deg`、S/P 离散；求解器换算为 `theta=90-grazing`、`phi=azimuth`；
- Task001 首轮只取掠射角 `0.5/10 deg`与方位角 `0/90 deg`的代表组合，
  `5.25 deg` 仅在首轮可辨识性失败时 fallback；这不是连续扫描；
- observable：`task001.fixed-n0-orders.v2`，固定
  `m=(0,-1,-2,-3,-4,-5,-6,-7,+1), n=0`；每个 side/order grouping 保存
  `kx/ky/kz` complex identity、outgoing S/P amplitude real/imag、S/P power 与
  `order_total_power`；
- Hybrid：static local FEM、M120、modal-Schur memory-minimal、discrete axial
  propagation/traction；
- formal MPI：先资格化 MPI2，最终 dataset version 不混用 ranks；
- threads：每 rank 1；同一时刻最多一个 forward job；no swap。

## Fidelity candidates

| ID | p / h / M | fixed topology | role |
|---|---|---|---|
| HF10 | p6 / h10 / M120 | `(6,3,14)`；z material layers `1/12/1` | nominal HF fallback |
| HF7P5 | p6 / h7.5 / M120 | `(9,4,20)`；z material layers `2/17/1` | only after prediction Gate |
| LF4 | p4 / h10 / M120 | `(6,3,14)` | preferred LF |
| LF5 | p5 / h10 / M120 | `(6,3,14)` | fallback LF |

坐标随 height/width 连续变化；logical adjacency、material cell-index pattern、
Floquet pairing count 和 element identity 不变。普通 pilot 不保存完整 volume field。

## 安全 Gate

hard ceiling 为 `min(10.5 GiB, 0.77 * WSL MemTotal)`，prediction ceiling 为
hard 的 90%。启动时要求至少 hard + 1 GiB MemAvailable、swap used 0、磁盘可用
至少 20 GiB。watchdog 只终止自己创建的 process group，记录 RSS/PSS/USS/swap、
heartbeat、stage、timeout 和退出码。

p6/h7.5 只能在 HF10 nominal 同一 Task001 baseline 通过后进行三路资源预测；
central 超过 prediction ceiling 或 conservative 明显超过 hard 时保持
`controlled_stop_resource_projection / PDE launched=false`。

## Task001 结果与证据

- numerical source：`68f4f9bc92de6cd7ec2896755ef210fb182280a1`；所有正式 PDE
  都绑定该 clean SHA；
- selected HF/LF：`HF10 = global p6/h10/M120` 与 `LF4 = global p4/h10/M120`；
- HF7P5：central 预测 11,588,731,106 bytes，conservative 预测
  15,878,719,347 bytes，均越过相应启动/硬上限，因此 PDE 未启动；
- selected configuration bundle：`grazing=10°, azimuth=0°, S` 与
  `grazing=10°, azimuth=90°, S`；它们是 DOE 实验配置，不属于反演参数；
- geometry 反演参数仍只有 height/width；Task001 没有训练 surrogate；
- 0.5° 与 P 的失败/限制保留在 compact manifest 中，不能据本 pilot 宣称完整连续
  `configuration` 域已经资格化。

`records/` 由 `python -m benchmarks.check_case110_task001 --write-records` 从 ignored
raw artifacts 重算；`--check-records` 会逐字检查 compact evidence 是否过期。提取器把
正的向外 Poynting 功率定义为 `power_carrying`，并另存原始色散分类
`dispersion_propagating`，从而正确处理有损基底中 `dispersion=false` 但仍计入端口 T
的模式。

`compact_diffraction_responses.json` 包含 37 个通过记录的 v2 母响应，并逐 run 绑定旧 raw
`task001.fixed-n0-orders.v1` execution/solver SHA-256。每个 run 有 18 个 grouped orders；
checker 验证 S+P=order total、wavevector real/imag、分侧 `n!=0` leakage、raw R/T 和
lossy propagation/power 语义。该文件完全由既有 artifacts 生成，没有重跑 FEM。

## 测试

见 `test_command.txt`。formal records 必须绑定一个 clean Task001 implementation
baseline SHA；发现实现 bug 后立即停止 campaign，不混用旧 SHA。
