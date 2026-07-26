# Task035c：Hybrid 逐通道精度与静态凝聚内存闭合

## 任务做了什么

Hybrid FEM–Modal 把上下两段复杂三维区域继续交给有限元，把中间规则长段改成
二维截面模态传播。通俗地说，它避免在整个高度上重复求解相似的三维未知量。
静态凝聚则在每个有限元单元内部先精确消去只属于该单元的内部自由度，只把单元
边界上的 trace 送入全局矩阵；求解后再恢复完整场。两者结合后，理论上应同时
减少矩阵行列、稀疏矩阵和直接分解的存储。

Task035c 只关闭两个在 Task035b 中暴露的问题：

1. Full3D 与 Hybrid 的总反射、透射接近，但 12 个显著衍射级的功率和复振幅不闭合；
2. 低阶 static Hybrid 已减少 rows/NNZ，却没有降低峰值内存并显著拖慢 modal coupling。

权威范围见 [`task.md`](task.md) 和 Task035b
[`review_report_v4.md`](../task035b_high_order_local_hp_resource_envelope/review_report_v4.md)。

## 最终结论

| 项目 | 结论 | 数据身份 / 边界 |
|---|---|---|
| `p2/h5` 根因 | Full3D 轴向使用 scalar CG(p) 离散传播相位与离散端点导数；旧 Hybrid 使用连续 `beta` 与连续 traction | measured diagnostic；不是 modal M 不足 |
| `p2/h5` 修复 | M120/M160 均为 12/12 power + 12/12 boundary-plane complex amplitude | final-source diagnostic pass |
| `p6/h10` MPI8 六路径 | Full3D standard/static、Hybrid standard/static M120/M160 全部完成；物理、残差、场、12 通道 Gate 通过 | measured；numerical source `244b62e1...` |
| static Hybrid M120 | `11.076893 → 7.544262 GiB`，下降 `31.8919%`；总时间比 `0.342646×` | 通过 Review mandatory 15% 和 preferred 25% |
| static Hybrid M160 | `11.247025 → 7.929413 GiB`，下降 `29.4977%`；总时间比 `0.388133×` | 同样通过正式 Gate |
| 用户期望的 50% Hybrid 内存下降 | 未达到 | 峰值在 `record_and_release`；modal coupling 本身的 M120 stage peak 约 `5.756 GiB` |
| 推荐点 | static Hybrid M120 | M160 没有物理收益，反而增加内存、coupling 和总时间 |
| MPI rank lane | MPI1 数值 Gate 失败；MPI2 资源 authority 末端采样失败；两个连续负信号后关闭，不跑 MPI4 | 两条 controlled negative 均保留 |
| ordinary default | `standard_full` 不变 | 新传播/traction 与 static backend 均显式 opt-in |
| 正式分类 | `HYBRID_CHANNEL_AND_MEMORY_CLOSURE_SUCCESS` | Review V4 的精度、15% mandatory、25% preferred 与总时间 Gate 通过 |
| 用户 50%目标限定 | `not_achieved / open_engineering_gap` | 不改变正式分类，但不得把当前峰值写成理想内存下限 |

用户已明确取消 modal-coupling `<=1.25×` 的硬限制。本任务仍测量并尽量降低
该时间，但只把它作为诊断指标，不据此否决已经满足物理、内存和总时间 Gate 的
候选。

## 文档入口

| 文件 | 内容 |
|---|---|
| [`outcomes/p2_h5_channel_root_cause.md`](outcomes/p2_h5_channel_root_cause.md) | 低成本根因隔离、phase-only 负结果和离散 traction 修复 |
| [`outcomes/p6_h10_channel_closure.md`](outcomes/p6_h10_channel_closure.md) | 六路径高阶数值、逐通道、场与资源 authority |
| [`outcomes/object_lifecycle_and_rank_study.md`](outcomes/object_lifecycle_and_rank_study.md) | 峰值对象生命周期、50%缺口和 MPI1/2 rank 负结果 |
| [`outcomes/dependency_failures.md`](outcomes/dependency_failures.md) | p6 约束、roundoff audit、launcher/watchdog 失败证据 |
| [`outcomes/test_summary.md`](outcomes/test_summary.md) | targeted、MPI、checker、Ruff 和 compileall |
| [`outcomes/summary.md`](outcomes/summary.md) | 表格优先的完整回顾 |
| [`response_v1.md`](response_v1.md) | 对 Review V4 / Task035c 的集中回应 |
| [Case096](../../benchmarks/cases/096_hybrid_channel_memory_closure/README.md) | compact、hash-bound、可独立复算的正式 evidence |

重型 JSON、timeline、场样本和 stdout 保留在 gitignored
`benchmarks/artifacts/task035c_hybrid_channel_memory/` 与
`benchmarks/artifacts/cases/091/`，不进入 Git。
