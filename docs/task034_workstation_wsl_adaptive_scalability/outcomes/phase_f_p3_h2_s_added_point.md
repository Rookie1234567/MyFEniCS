# Phase F：p3/h2 S 偏振新增点

## 结论

用户新增的 `p3/h2`、S polarization、MPI8 点已完成分级尝试：

- Full3D assembly-only 正式通过；factorization 保守预测超过固定 termination，因此在 `KSPSetUp` 前形成受控资源负结果。
- Hybrid M160 在 canonical authority、Case090 high-order core、clean source、外部 watchdog 和 zero-swap Gate 下完整运行，状态为 `measured_shard_pass`。
- 本点不声称 full3D/Hybrid closure，也不声称 M 收敛；这是用户缩减范围下的单个 M160 可计算性与数值链证据。

## Full3D 分级 Gate

assembly-only 使用 clean SHA `b93d59c11d7625291824f216db1d431585319ed5`：

| status | elapsed | peak | rows | NNZ | swap |
|---|---:|---:|---:|---:|---:|
| `assembly_calibration_pass` | 1334.645 s | 64.015 GiB | 2,047,298 | 488,789,000 | 0 |

三种 factorization 预测中心为 `141.862 / 135.579 / 154.973 GiB`，保守上界为 `232.460 GiB`，超过固定 termination `184.163 GiB`。因此未启动 factorization-only 或 full solve，且没有通过降低阈值、允许 swap 或 OOM 后记失败来绕过 Gate。

## Hybrid M160

Hybrid 使用 clean SHA `f7924f52584b801c48930477a7f9ce4e4bb4a2db`，参数为 `MPI8`、M160、candidate pool 320、`modal-schur-memory-minimal`：

| status | elapsed | peak | true residual | R | T | A(balance) | A(volume) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `measured_shard_pass` | 3513.818 s | 49.642 GiB | 3.613e-11 | 0.00076447 | 0.60269013 | 0.39654541 | 0.39654541 |

volume energy closure error 为 `1.782e-12`；interface E projection 和 FE/modal traction equilibrium Gate 均通过。watchdog 未触发 warning、termination 或 timeout，job swap 为 0。

`physical_qualified=false` 是预期边界：协议只在 M80/M120/M160 funnel aggregate 后提升物理 qualification，而用户要求该新增点只执行一个资源安全的 Hybrid 示例。本结果不能被解释为 M 收敛或同阶 closure。

## 受控失败证据

第一次 parser 级启动被旧 added-point scope 正确拒绝，没有启动 solver。补齐 p3/h2 M160-only CLI 限制并通过测试后，第一次 preflight 又因将文件 raw SHA 误作 Case090 canonical evidence SHA 而 fail closed；该 `not_run_preflight_failed` 记录已保留。使用记录内部 canonical SHA 后 attempt2 才正式启动并通过。

## 证据哈希

| evidence | SHA-256 |
|---|---|
| Full3D assembly watchdog | `c355c3ebe746c790ac25bdedf65a1733bfd07f65ae168c3b721f29140fceabf7` |
| resource Gate | `607c7106a14057b0ecec36bc209116b71fb3b60ef784cbe99e0fb179c16ec606` |
| Hybrid watchdog summary | `b709705292736c9b22a25cc0bcd8667f5195b862da1d2195807df21b347b9f34` |
| Hybrid solver record | `d797614a03138c6265485398996f10bc2759cdaa8fa98d675f44b42f6f05d4e9` |
| preserved preflight negative | `2fa421a1b331bf66f830660c29f2198b676f4e79c39812d53ebf75fe468f760f` |

## 下一步

继续用户新增的 `p4/h3` S polarization：先执行 Full3D assembly-only，再依据实测 rows/NNZ/RSS 更新 factorization Gate；Hybrid 仍只允许单个、受资源预测和 live watchdog 约束的 M160 尝试。
