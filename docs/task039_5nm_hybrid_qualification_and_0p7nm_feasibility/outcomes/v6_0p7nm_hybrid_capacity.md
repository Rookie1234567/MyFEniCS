# V6：0.7 nm Hybrid capacity 边界

本页是容量审计，不是 0.7 nm 正式算例。2 TiB 规划线用于说明风险位置；只有真实
process-tree、完整生命周期和数值 Gate 才能建立可行性。V6 bottom port/modal
component 在 5 nm h4 已于 construction hard line 停止，所以不能把该路线外推为
0.7 nm 可行。

## 已有 2 TiB 规划线

| 线 | 2 TiB = 2048 GiB |
| --- | ---: |
| 70% | 1433.6 GiB |
| 80% | 1638.4 GiB |
| 90% | 1843.2 GiB |

这些是规划线，不是 V6 solver Gate。对象 bytes 也不能相加后冒充同时刻 RSS。

## 5 nm measured anchors

| 对象/阶段 | measured evidence | 可支持的结论 |
| --- | ---: | --- |
| h4 direct | 93.377006531 GiB | matched reference |
| V4 h4 exact-side iterative | 104.334560394 GiB | numerical/physics pass；resource regression |
| V5-2 h4 setup-only | 85.376991272 GiB | setup baseline，非完整 solve |
| V6-1 post-compaction setup | 42.70841979980469 GiB | 超过 42.019652939 GiB setup line；exact-side full formal closed |
| V6 port/modal bottom | 22.025470733642578 GiB | 超过 22 GiB construction line；bottom family closed |
| h5 current direct sidecar | 50.356239318847656 GiB | nonblocking borderline；不是空间收敛 |

V6 port/modal run 的 22.025470733642578 GiB 是完整 process-tree authoritative peak，
不是只加某几个对象容量；construction end、retained state、outer-ready 都没有到达。

## 0.7 nm 的 measured / derived / unresolved 分栏

| 项目 | 数值或证据 | 分类 | 未知边界 |
| --- | --- | --- | --- |
| Full3D factor values-only | 3234.18–32341.76 GiB 的旧 envelope | predicted/conditional | ordering、fill、pivot、OOC、recovery 未测 |
| 单 air-side W | 约 201.22 GiB 的旧 derived estimate | derived/conditional | 不是 two-side process-tree RSS |
| 单 air-side W + K/LU | 205.049–208.878 GiB | derived/conditional | 约为 2 TiB 的 10.0%–10.2%，低于 70%线；只接近旧 256 GiB hard-stop |
| h4 streaming-W object change | W 158,223,360 B；derived C action约97,507,312 B；差约60,716,048 B | derived component capacity | 不是 formal RSS saving，未建立 0.7 nm scale law |
| side factors | h4 exact factors已证明是主风险；V6 exact-side full formal关闭 | blocker / unresolved at 0.7 nm | 没有 0.7 nm factor-free production authority |
| K/LU | h4 V6 bottom K rank296、condition 10.4705、W 81,070,848 B | measured h4 component | 0.7 nm K/channel增长和时间无上界 |
| P/T coupling | h4 derived CSR estimates；无 0.7 nm resident inventory | unresolved | two-side coupling与生命周期未测 |
| modal Schur / Krylov | V5 component evidence only；V6 rank ladder未到64 | unresolved/not_run | outer-ready、Krylov、recovery均未测 |
| full two-side/recovery/allocator | 没有 formal artifact | unresolved | 不能裁决70/80/90%任何完整峰值 |
| 0.7 nm PDE | 无 | not_run | 禁止写成通过或失败的正式算例 |

```math
B_{\mathrm{payload}}(M)=B_{\mathrm{header}}+M\,B_{\mathrm{item}},
\qquad
\mathrm{RSS}_{\mathrm{peak}}\ne\sum B_{\mathrm{payload}}.
```

即使已知的 air-side W+K/LU 低于 2 TiB 的 70% 线，也不能由此推出完整 two-side
Hybrid 的总峰值；side factor、P/T、modal、Krylov、recovery 和 allocator 的未知量
必须被实测或保守上界覆盖。V6 的实测结果反而显示：在更早的 5 nm bottom construction
阶段，port/modal candidate 已超过专门的 22 GiB 线。

## 最终容量裁决

0.7 nm Full3D/Hybrid PDE、top、both-side、outer、recovery、R/T/A 和 arbitrary-3D
qualification 全部 not_run。当前没有“数值合格且满足内存目标”的 h4 Hybrid iterative，
也没有可把 V6 bottom resource negative 推翻的 0.7 nm capacity evidence。不得继续
V6 top/full，也不得调参或重跑本 family。
