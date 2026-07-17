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

## 4. 为什么不写成“QEP 全面资格通过”

对 36 个分片做 post-hoc 全局聚合时，结果是
`qep_component_aggregate_not_qualified`：

- p1 的 air/lossy 解析 beta 误差随 h 细化不满足单调 Gate；
- patterned p1 的跨 h 模态跟踪失败；
- patterned p2 的 h5→h3 最大 beta drift 为 `0.26087`，略高于 `0.25`；
- patterned p4 的 h5→h3 最小 overlap 为 `0.48444`，略低于 `0.5`。

p3 自身的解析趋势与两段 patterned tracking 均通过。p4 的解析趋势通过，只有上述
一段 tracking Gate 阻止升级。这是聚合层负结果，不应改写成“p4 求解失败”。

MPI2/4 只各做了一次 `stage4_xy_p2_h3` 的 1 秒 clean-timeout 合同测试；
它们验证 watchdog/来源/资源/超时闭合，不证明 MPI2/4 QEP 正向性能。
