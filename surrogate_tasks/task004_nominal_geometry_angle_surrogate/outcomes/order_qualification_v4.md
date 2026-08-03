# Task004 Order Level B qualification v4

使用 training-CV 选择的 local RBF k24 aggregate OOF，独立重算 order power：

| Gate | result | limit |
|---|---:|---:|
| mask agreement | 100% | 100% |
| maximum side-wise ledger error | `2.220446049250313e-16` | `1e-12` |
| primary-channel maximum NRMSE | `0.405996` | `0.03` |
| primary-channel p95 / max | up to `0.0268353 / 0.341594` | `0.01` |
| order qualification | not qualified | — |

Aggregate 和 order 资格继续分离；order 失败不改写 aggregate 负结果，也不把
未资格化通道暴露给公开 API。
