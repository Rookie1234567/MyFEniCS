# Case110：13.5 nm 两参数 Hybrid 多保真 pilot

本 case 只执行 Task001 的小规模资格化与可辨识性 pilot。它不会生成 Task002
冻结的 49 点 low-fidelity design，也不会训练 surrogate 或执行反演。

## 固定范围

- geometry：height 115--125 nm，width-x 16--18 nm；
- wavelength：13.5 nm fixed；period 50 x 25 nm 和材料保持
  `target_stage4_config` 权威；
- illumination：theta 70/80（75 仅 fallback）、phi 0/90、S/P；
- observable：固定 `m=(0,-1,-2,-3,-4,-5,-6,-7,+1), n=0` order schema；
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

## 测试

见 `test_command.txt`。formal records 必须绑定一个 clean Task001 implementation
baseline SHA；发现实现 bug 后立即停止 campaign，不混用旧 SHA。
