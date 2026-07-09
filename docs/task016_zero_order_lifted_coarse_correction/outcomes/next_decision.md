# Next Decision

## Decision

Task17 不应继续当前形式的 right-only lifted correction。

推荐下一步转向：

```text
Petrov / adjoint-aware zero-order coarse correction
```

或：

```text
selected-mode true FE Schur sample: q_j ≈ -A_FE^{-1} C_j
```

## Why

| evidence | meaning |
|---|---|
| `top,(0,0),y` mapping 正确 | 失败不是 mode 选错 |
| coarse condition 约 1 | 失败不是 coarse solve 病态 |
| pfe、diag、balanced、sign flip 都无效 | 失败不是简单符号或尺度 |
| minres 只改善 `1.000045x` | 普通右 coarse space 几乎不含真正误差方向 |
| KSP 阻尼后仍无效 | 不是单纯 PETSc FPE 导致 |

## Proposed Task17

1. 构造 Petrov coarse correction：`x <- x + Z (W^T A Z)^-1 W^T r`。
2. 候选 `W` 从 `AZ`、aux residual basis、或 adjoint sampled solve 中选择。
3. 只在 `top,(0,0),y` 与 top/bottom y 上做 1 到 2 模态试验。
4. 若 Petrov coarse 仍无效，则停止 real-split AMS + modal coarse 主线，转向 layered-background / RCWA-like approximate inverse 或 domain-decomposition/sweeping PC。

## Gate

继续保持：

```text
default100 p=1 h=5 达到 residual <= 2e-3 或 improvement >= 10x 后，才允许 p=2 h=5。
```
