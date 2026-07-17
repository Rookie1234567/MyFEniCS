# Task033 QEP 阶次研究

## 1. 已完成数据

MPI1 正式运行覆盖：

```text
3 materials × p1/p2/p3/p4 × h5/h3/h2.5 = 36 shards
```

36/36 均为 `measured_shard_pass`、`return_code=0`、`numeric_pass=true`、
`formal_pass=true`。其中 p3/p4 为 18/18。

每个 shard 仍标记 `physical_qualified=false`，因为单项记录需要 aggregate/funnel 才能升级；
因此本阶段只声明“QEP 分片扩展与数值 Gate 完成”。

## 2. 解析 beta 精度

| 材料 | h/nm | p3 相对误差 | p4 相对误差 | p4 相对 p3 改善 |
|---|---:|---:|---:|---:|
| air | 5 | `6.85412e-3` | `1.02270e-4` | 98.51% |
| air | 3 | `6.44754e-4` | `4.21583e-6` | 99.35% |
| air | 2.5 | `2.59567e-4` | `1.24265e-6` | 99.52% |
| lossy homogeneous | 5 | `7.28088e-3` | `1.08618e-4` | 98.51% |
| lossy homogeneous | 3 | `6.84785e-4` | `4.47750e-6` | 99.35% |
| lossy homogeneous | 2.5 | `2.75679e-4` | `1.31978e-6` | 99.52% |

## 3. p3/p4 九项最坏值

| 指标 | p3 | p4 |
|---|---:|---:|
| 最大解析 beta 相对误差 | `7.28088e-3` | `1.08618e-4` |
| 最大右 QEP 残差 | `6.27074e-14` | `1.90927e-12` |
| 最大左 QEP 残差 | `2.07128e-13` | `2.06286e-12` |
| 最大双正交 identity 误差 | `8.04164e-9` | `9.16674e-7` |
| 最大左右 beta 配对误差 | `7.56401e-11` | `1.83210e-8` |
| 最大 full/reduced DoF | 5,857 / 5,670 | 10,329 / 10,080 |
| 最大四矩阵 NNZ 合计 | 1,262,520 | 3,413,760 |
| 最大 assembly / solve time | 1.511 / 0.536 s | 1.952 / 1.239 s |
| 最大同时 worker RSS | 352.3 MiB | 659.1 MiB |

## 4. Phase A block/subspace tracking 更新

对 36 个分片做 post-hoc 全局聚合时，结果是
`qep_component_aggregate_not_qualified`：

- p1 的 air/lossy 解析 beta 误差随 h 细化不满足单调 Gate；
- patterned p1 的跨 h 模态跟踪失败；
- patterned p2 的 h5→h3 最大 beta drift 为 `0.26087`，略高于 `0.25`；
- patterned p4 的 h5→h3 最小 overlap 为 `0.48444`，略低于 `0.5`。

p3 自身的解析趋势与两段 patterned tracking 均通过。Phase A 对 p4 的四维近简并块
`[4,5,6,7]` 做基底无关 principal-angle tracking 后，得到：

- 四维块中心 beta drift `8.11363e-7`；
- right/left 子空间满秩；
- 最小 symmetric principal cosine `0.999999999999851`；
- 外部相对谱间距约 `0.0437`。

因此 `0.48444` 是近简并子空间内的单模基旋转，p4 patterned tracking 现已通过。阈值没有
放宽，p2 的 `0.2608686 > 0.25` 真实 beta drift 和 p1 失败仍保留。

按 degree 独立判定：`p1=not_qualified`、`p2=not_qualified`、`p3=qualified`、
`p4=qualified`。legacy p1–p4 全阶 aggregate 仍为
`qep_component_aggregate_not_qualified`，因为它要求四个阶次同时通过。

Phase A 在 clean source `bb830ba...` 上新增 p3/h3、p4/h3 各一个 MPI2 与 MPI4 正向测试。
四项均 formal pass；相对 MPI1 的最大 beta drift 不超过 `2.15e-12`，最小 overlap 为
`0.615322`。之前的 1 秒 timeout-negative 仍只作为合同负向测试。

完整数值与执行理由见 `qep_tracking_diagnostic.md`。
