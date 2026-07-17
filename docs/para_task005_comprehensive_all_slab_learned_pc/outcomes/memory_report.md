# Task005 Memory / storage 报告

## 决定性结论

当前实现没有 candidate 同时满足 local、runtime 与 storage feasibility。R4 私有
exact-audit CSR operators 本身为 **40.458 MiB/owner**，已超过 memory-neutral
上限 33.670 MiB；加最小 admissible models 后也超过 speed-first guard
`1.5 × 33.670 = 50.505 MiB`。

| slab | private CSR operator | smallest admissible linear | smallest admissible nonlinear |
|---:|---:|---:|---:|
| 0 | 8.134 MiB | rank 32, 3.600 MiB | rank 32, 3.616 MiB |
| 5 | 12.095 MiB | rank 64, 10.312 MiB | rank 64, 10.501 MiB |
| 9 | 12.095 MiB | rank 64, 10.312 MiB | rank 64, 10.501 MiB |
| 15 | 8.134 MiB | rank 32, 3.600 MiB | rank 32, 3.616 MiB |
| **owner total** | **40.458 MiB** | **27.824 MiB** | **28.234 MiB** |
| **operator + model** | — | **68.282 MiB** | **68.692 MiB** |

| Gate | 上限 | linear | nonlinear | 结论 |
|---|---:|---:|---:|---|
| memory-neutral | 33.670 MiB | 68.282 | 68.692 | FAIL |
| speed-first exploratory | 50.505 MiB | 68.282 | 68.692 | FAIL |

Uniform rank-64 模型自身已分别为约 35.084 MiB（linear）和 35.840 MiB
（nonlinear），尚未计 operator/buffer 就略超 memory-neutral。

## 为什么不能删掉 operator 后宣称通过

Task005 要求 shadow 每次 exact local audit，active 也只有在 proxy 零 false-accept
并配合 periodic exact audit 后才允许抽样。当前实现尚无以下任何已资格化路径：

- 从已有 global operator 借用 action 而不复制 local CSR；
- 不持久存储 CSR 的可证明 periodic exact audit；
- zero-false-accept strict proxy；
- proxy drift injection 与 fail-closed tests。

因此不能把 40.458 MiB 从核算中静默删除。后续若开新任务，应先解决 audit storage
architecture，再恢复 full-16 训练。
