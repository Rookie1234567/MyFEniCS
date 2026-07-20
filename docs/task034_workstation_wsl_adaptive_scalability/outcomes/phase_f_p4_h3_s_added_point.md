# Phase F：p4/h3 S 偏振新增点

## 结论

用户新增的 `p4/h3`、S polarization、MPI8 点已按分级 Gate 完成：

- Full3D assembly-only 正式通过；factorization 保守预测超过固定 termination，在 `KSPSetUp` 前形成受控资源负结果。
- Hybrid M160 在 canonical authority、Case090 high-order core、clean source、外部 watchdog 和 zero-swap Gate 下完整运行，状态为 `measured_shard_pass`。
- 本点不声称 Full3D/Hybrid closure，也不声称 M 收敛；这是用户缩减范围下的单个 M160 可计算性和数值链证据。

## Full3D 分级 Gate

assembly-only 使用 clean SHA `19f0366a65152821b8fde60d8fbd9b0a4bc1d0a2`：

| status | elapsed | peak | rows | NNZ | swap |
|---|---:|---:|---:|---:|---:|
| `assembly_calibration_pass` | 3035.139 s | 80.538 GiB | 1,540,028 | 696,091,072 | 0 |

三种 factorization 预测中心为 `111.914 / 136.088 / 79.481 GiB`。其中 factor-fill 中心保留当前 assembly 峰值并叠加预测 factor payload，不扣除 baseline memory，避免在边界附近作乐观抵扣。保守上界为 `204.132 GiB`，超过固定 termination `184.163 GiB`，因此未启动 factorization-only 或 full solve，也未降低阈值、允许 swap 或等待 OOM。

## Hybrid M160

Hybrid 使用 clean SHA `9db1a8a92572945eaf597073aece1d43acac8a5b`，参数为 `MPI8`、M160、candidate pool 320、`modal-schur-memory-minimal`：

| status | elapsed | peak | true residual | R | T | A(balance) | A(volume) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `measured_shard_pass` | 3662.685 s | 42.481 GiB | 2.924e-11 | 0.00076218 | 0.60270630 | 0.39653151 | 0.39653151 |

volume energy closure error 为 `2.704e-12`；interface E projection、FE/modal traction equilibrium 和 physical field gates 均通过。watchdog 未触发 warning、termination 或 timeout，job swap 为 0。

`physical_qualified=false` 是预期边界：协议只在 M80/M120/M160 funnel aggregate 后提升物理 qualification，而用户要求该新增点只执行一个资源安全的 Hybrid 示例；同时本点没有获准执行 Full3D full solve。因此结果不能解释为 M 收敛或同点 Full3D/Hybrid closure。

## 资格化与范围边界

- p4/h3 Full3D：assembly Gate 通过；factorization/full-solve 为受控资源负结果。
- p4/h3 Hybrid：M160 formal/numeric/memory Gate 通过。
- p4/h3 的 M80、M120、M240、其他 MPI 和 P polarization 均未授权、未运行。
- 原始失败和资源负结果均保留；阈值未放宽。

## 证据哈希

| evidence | SHA-256 |
|---|---|
| Full3D assembly watchdog | `a8fb4074f3dd33b884693a68e29fa3f286230d879a66829eefc8b6c349ab7f71` |
| resource Gate | `638108912e91feeede12ebf8f5714c163b83e8864a17d7d8b1545f1bf699e479` |
| Hybrid watchdog summary | `7d2e54c7b952ebb3f395d500756f51d3787044834c7984dafd251697a5eaa8bc` |
| Hybrid solver record | `650b1fe17d3817913f76f6cf27fa474887a74aeb2f8e44ef9337c420fe338cd0` |

## 下一步

用户新增的 `p2/h1`、`p3/h2`、`p4/h3` 三个 S polarization 点均已完成各自允许范围。后续回到 Task034 主线剩余工作：adaptive、Case093、resource model v2、0.7 nm 投影与最终交付汇总。
