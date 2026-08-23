# V3-2 联合接口机制 consumer

## 状态

`pending_conditional_not_run`。V3-2 只有在 V3-1 packet-only algebra、tiny oracle、identity 和 condition
Gate 全部通过后才可运行；本页当前仅记录冻结合同，不代表 full-span mechanism 通过。

## 机制目标

当前 V2 失败的是三个独立 projected inverse 再做 sweep。V3-2 只测试一个问题：在相同三分区、
相同 lower 296/upper 480 span 和相同 local exact group solve 下，一次求解两个接口的 776 维
耦合系统，是否能使 bare-F side equation进入可用 FGMRES 范围。

一次 action 必须包含：local/group pre-correction、形成 lower/upper interface residual、
`Y_Gamma^H` 投影、联合 reduced solve、`Z_Gamma` 合成和三个 group 的一致 back-substitution。
它不得退化成已有三个 local inverse 加 sweep。

## 运行与 Gate

允许作为 mechanism oracle 的资源边界：

| 项目 | 合同 |
|---|---|
| interface reduced solve | full rank 776，complex128，SVD/QR/dense LU均可 |
| group factors | 最多三个，simultaneous max=3 |
| exact-interface oracle | `0` |
| full-side/global factor | `0/0` |
| QEP / PDE | `0 / not_run` |
| RSS / swap | `<45 GiB` / `0` |
| cleanup | group factors `3 -> 0` |

固定 source 为五个非零 source 加 physical zero-map。checkpoint 为 `0/4/8/16`，仅在 16
步全部 finite 且最近 8 步下降至少 `0.25 decade` 时授权 32；只有 32 步最坏 residual
`<=0.1` 且最近 16 步继续单调下降时才授权 64。首个同时满足 mandatory `<=1e-2`、
modal+/modal-/external `<=1e-3` 的 checkpoint 才能分类：

```text
COUPLED_INTERFACE_FULL_SPAN_PASS
```

若 tiny/packet identity 通过但最终 64 仍未通过，必须分类：

```text
COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL
```

不得继续同 span analytic、bounded patch 或增加 Krylov budget。

## 当前边界

V3-2 尚未启动；没有 residual、cross-block、rank/condition、RSS 或 formal root。V3-2 仍属于
research mechanism oracle，不是 production side inverse 或 0.7 nm scalable candidate。
