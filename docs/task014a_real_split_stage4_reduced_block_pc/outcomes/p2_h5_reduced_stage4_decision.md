# p2 h5 Reduced Stage 4 Decision

## 决策

```text
p2_h5_reduced_stage4_run: no
```

## 原因

task14a 要求 gated execution：

```text
只有 reduced p=1 h=5 中 FE-AMS + aux identity 明显优于 Jacobi，
才允许 optional reduced p=2 h=5。
```

本轮 p=1 h=5 主 case 结果如下：

| case | Jacobi true residual | FE-AMS true residual | 改善倍数 | 是否收敛到 1e-6 |
|---|---:|---:|---:|---|
| tiny10 auto | 8.817e-7 | 9.601e-7 | 0.92x | 两者都收敛，AMS 未改善 |
| default100 auto | 3.436e-2 | 2.147e-2 | 1.60x | 两者都未收敛 |

这不满足：

```text
true residual 至少比 Jacobi 改善 10 倍
或 FE-AMS profile 达到 <= 1e-6 且 Jacobi 未达到
```

因此 p=2 h=5 不运行。

## 对路线的含义

这不是否定 task013 的 FE-only same-H1 AMS 结果。它说明：

```text
FE-only AMS 正信号进入 Stage4 后，被 Helmholtz 不定性、Floquet/DtN 模态耦合和 aux identity 近似削弱。
```

下一轮如果继续，应先增强 block PC，而不是直接把当前 profile 推到 p=2。
