# Scalability Addendum：external channels 与 local carrier active sets

## 0. 优先级

本文件对本目录中以下早期表述作狭窄覆盖：

```text
theory_and_design.md:
    C2 all/significant propagating carrier family

codex_handoff.md:
    E3 carrier expansion
```

覆盖原因：0.7 nm 的 physical DtN external channel inventory可能很大。完整边界 channel
inventory必须保留，但不能把每个 external channel都复制成一个全域 volume carrier。

## 1. 两种 inventory 必须分开

```text
physical boundary inventory:
    all outgoing/evanescent channels required by exact streaming DtN

volume carrier active set:
    only directions with measured source/material/residual relevance
```

因此：

```text
external channel count != volume carrier count
```

即使 boundary DtN有上万个 channels，volume carrier active set也必须 bounded或local。

## 2. global carrier只用于早期机制验证

E1–E3 的 global carrier family冻结为：

```text
C0:
    incident carrier only

C1:
    incident + specular top/bottom partners

C2-16:
    fixed-score significant carriers, total <=16

C2-32:
    conditional total <=32
```

`C2-32` 只有在 `C2-16` 对 frozen holdout true residual 至少改善 `2x` 时允许。

32 个 global carriers仍不能在 matched accuracy 下满足：

```text
total active unknowns <= ordinary matched-accuracy unknowns / 4
```

则分类：

```text
GLOBAL_CARRIER_FAMILY_NO_DOF_SIGNAL
```

并停止增加 global carriers。

## 3. fixed carrier score

候选 carrier 使用一次固定评分，不在 formal case上扫描权重：

```text
source score:
    incident/specular identity

material score:
    magnitude of epsilon/mu Fourier coupling

residual score:
    current true-residual projection on candidate trace

cutoff score:
    bounded preference for near-cutoff directions
```

建议先按 lexicographic physical class，再按归一化 score排序。必须记录：

```text
candidate key
score components
selected/not-selected reason
Gram residual ratio
canonical hash
```

## 4. production方向：local carrier supports

最终表示应把 carrier附着到具有局部支撑的全局 Nédélec basis：

```math
\mathbf E_h(\mathbf x)
=
\sum_j
\sum_{\alpha\in\mathcal C_j}
c_{j\alpha}
e^{i\boldsymbol\kappa_{j\alpha}\cdot
(\mathbf x-\mathbf x_j)}
\boldsymbol\psi_j(\mathbf x).
```

这里 `psi_j` 是一个全局 curl-conforming basis/support。乘以光滑相位仍属于 `H(curl)`。

carrier identity必须在 global support层定义。禁止：

```text
同一个共享tangential DoF
在相邻element中独立选择不同carrier
```

否则会破坏 tangential conformity。

总 unknown 数为：

```math
N_{\mathrm{local-env}}
=
\sum_j |\mathcal C_j|.
```

0.7 nm-oriented目标是：

```math
N_{\mathrm{local-env}}
\approx
\bar r_c N_{\mathrm{geom}},
```

其中平均 local carrier数 `r_c_bar` 随波长细化保持 bounded或缓慢增长，而不是随完整 external
channel inventory增长。

## 5. local prototype必须报告

```text
carrier count per support histogram
mean/max carriers per support
supports with zero/one/multiple carriers
support-overlap coupling count
local phase Gram condition
total enriched unknowns
carrier metadata bytes
live carrier vector bytes
MPI ownership and replication inventory
```

硬边界：

```text
full carrier set per-rank replication = false
FE-sized carrier allgather            = false
dense all-carrier block matrix        = false
carrier batch/live-vector count       = bounded
```

## 6. 与 Task040 Review V6 的共享边界

可共享：

```text
canonical Floquet key/order mapping
full-spectrum FFT/streamed boundary transform
physical beta/TE/TM normalization
matrix-free H(curl) action
bounded patch ownership
```

不能共享为 volume carrier basis：

```text
all physical external channels
old 776 response packet
failed Route C harmonic-Ritz family
```

## 7. Codex执行覆盖

Codex读取本并行分支时，应按以下顺序：

```text
test_318 pure algebra
-> E1 one global carrier
-> E2 two global carriers
-> E3 C0/C1/C2-16/(conditional C2-32)
-> local support carrier prototype
```

不得执行：

```text
all-propagating global carrier expansion
0.7 nm full external inventory x full volume FE space
```
