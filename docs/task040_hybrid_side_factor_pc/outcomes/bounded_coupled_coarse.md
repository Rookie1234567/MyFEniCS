# V3-3 bounded-rank 联合 coarse

## 状态

`pending_conditional_not_run`。只有 V3-2 full-span mechanism 通过后才允许进入；当前不选择 rank、不运行
FGMRES、不构造任何 coarse factor。

## 冻结的候选集合

从同一个 776 维 joint operator 形成嵌套候选，且只允许：

```text
64 / 128 / 256 / 512
```

basis 选择必须使用 complex biorthogonal SVD、RRQR 或等价稳定方法，并绑定 mode-key 与
linear-combination coefficients。不能按列号随意截断，也不能把 full 776 称为 scalable
candidate。

## Gate

每个授权 rank 使用相同的 one-apply 与 `4/8/16/(32)/64` screen，并记录 rank、basis hash、
`E` condition、rho/rho*/correlation、residual checkpoints、RSS 与 wall。选择第一个满足
V3-2 numerical Gate 的最小 rank。

必须保持无 FE numeric allgather、无每 rank full basis replica、无 full-side/full-cross-section
factor；coarse rank 上限为 512。若 rank 512 仍失败但 full 776 通过，停止并分类：

```text
FULL_SPAN_MECHANISM_PASS_BUT_BOUNDED_COARSE_NOT_ESTABLISHED
```

只有某个 `rank <=512` 通过，才可进入 V3-4。

## 当前边界

V3-3 的 rank screen、资源、残差、factor inventory 和正式 root 均为 `pending_conditional_not_run`；本页
不预写任何 bounded coarse 通过或扩展性结论。
