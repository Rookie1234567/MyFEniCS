# V26 setup-efficiency 收口

## 结论

V26 本轮正式运行已经完成 126 次外层迭代，显式真残差为 `9.283164976754267e-7`，通过残差和物理一致性检查，但没有匹配的独立 h7.5 reference，因此只能称为离散结果通过、authority limited。与已有的 V25 Q4 r2 相比，V26 完整 workflow 慢 `481.67352542698063 s`（`15.46659149457179%`），纯 KSP 慢 `18.90140881935669%`，setup 单调时间慢 `5.257852565220267%`。所以 r2 继续作为速度基线，V26 不提升为默认路线。

执行端的一次重复启动没有进入 PDE。`myfenics-case-20260923T014131-156906.service` 在 worker 启动前因 V26 的一次 replay 额度已经用完而被拒绝；没有新的残差、factor、KSP 或物理输出。该负记录保存在 [relaunch gate record](records/setup_efficiency_v26_relaunch_gate_rejection_20260923T014131.json) 中，本轮正式结果不被覆盖。

本批还保留两次更早的预启动拒绝（`000330` 缺 profile 参数、`001329` 缺 hash-bound replay evidence）以及第一次 source `973c0c3...` 的 `000422` worker failure：outer-route guard 报错，实测 `64.91704543396747 s`，没有进入 factor/KSP。账本最终为 2 个 fresh workers、1 次 bug replay；这些成本和失败不从结果中删除。

## 模型与正式结果

| 项目 | V26 本轮正式运行 |
|---|---:|
| 模型 | Full3D，host p6/h7.5，coarse p4，990 cells，80 modes，MPI1/thread1 |
| source / input | `c27c07e305739b2dcf02c18dde44a0bc8bc70642` / `2ad95964964175c07faf1890b666249b86037e5f6fce0ad4dc8536e1a59927cc` |
| 迭代 / 最终显式真残差 | `126` / `9.283164976754267e-7` |
| solver / KSP | `2983.060933997012 s` / `2716.518828 s` |
| full workflow | 单调 `3595.9571450339936 s`；保守观测 `3943.2766163249958 s` |
| setup | 单调 `823.0868099959989 s`；保守 `916.674193935 s` |
| 官方 R/T/A | `0.3650975537006226 / 0.013016803347760205 / 0.6218856429516172` |
| `A_volume` / `R00_total` | `0.621885642133916` / `0.36506086288704565` |
| process-tree RSS authority / worker PSS / swap | `7381557248 / 7346483200 / 0 B` |

“Setup”是从流程记录得到的阶段边界；保守时间包含 UTC 与单调时钟的观察差异。两种口径都保留，不能把差异解释成代码性能或外部供电事件的因果结果。

## 每 16 步残差与耗时

以下是 V26 本轮正式记录，不是被拒绝的重复启动。r2 列用于前一个案例耗时对比；残差在浮点误差范围内一致，V26 耗时更长。

| 步数 | V26 残差 | V26 solve (s) | r2 残差 | r2 solve (s) |
|---:|---:|---:|---:|---:|
| 16 | `4.143722296409995e-3` | 384.0337115070026 | `4.1437222964080065e-3` | 323.3362546709826 |
| 32 | `3.352917960308131e-4` | 777.1027530929997 | `3.352917960387092e-4` | 650.6104775810122 |
| 48 | `1.941922143554351e-4` | 1167.9473363410007 | `1.9419221371048617e-4` | 957.0546633300296 |
| 64 | `3.023352345638768e-5` | 1586.7619330320051 | `3.0233523443058283e-5` | 1281.9846078490243 |
| 80 | `1.760946875614058e-5` | 1936.0104711780182 | `1.760946862124978e-5` | 1590.69534846704 |
| 96 | `3.776699912546929e-6` | 2307.2483297520203 | `3.7766998795463687e-6` | 1915.863995520064 |
| 112 | `2.7139958418956275e-6` | 2641.9852813600146 | `2.71399585136905e-6` | 2225.8895136200404 |
| 120 | `1.2975777548194936e-6` | 2825.9313595170174 | `1.2975777533057327e-6` | 2378.8047570660283 |
| 126 | `9.283164976753938e-7` | 2982.967928542012 | `9.283165086752617e-7` | 2514.900594385036 |

## 计算流程与资源

V26 的 p6 路径使用 action-only 局部凝聚：它对每个 cell 保留小型局部块和恢复信息，在需要作用时计算结果，不建立完整的全局 p6 矩阵；这样减少常驻对象，但不等于已经证明端到端更快。p4 仍建立 84680 行的凝聚矩阵，并记录 `32320342` 个存储 NNZ、`45403840` 个预分配 NNZ。MUMPS 记录的 `INFOG(19)/INFOG(22)` 为 `4687/4326 MB`。

本轮四项 setup 优化有真实 990-cell 配对证据：

| 优化 | 对照结果 | 说明 |
|---|---:|---|
| 不生成 sum-factorization 不消费的完整参考表 | new path `full_reference_tabulation_performed=false` | 保持同一 ABI、积分点和参考身份 |
| 直接构建选定 H6 backend | `direct_selected_backend_used=false → true` | 避免先构建再销毁 native action |
| 共享只读 geometry/reference bundle | new bundle 借用 curl/mass，材料数据不共享 | 990-cell identity、readonly arrays 和 reference data 均有 raw 记录 |
| H6 局部类型复用与批量 grouping | diagonal `45.07978344000003 → 4.169365248999384 s`；H6 setup `84.68341056300414 → 43.2881181279954 s` | new local-type cache `139` 类、`851` hits；projection reuse 未采用 |

A6 physical median 为 `6.215509254499921 → 5.547621760000766 s`，A6 volume median 为 `4.437351659504202 → 3.616020113498962 s`；operator equivalence 的最大列入记录的相对差 `9.524399166150845e-15`。这些是组件配对成本，不替代完整 workflow 速度结论。

阶段记录包括 p6 retained build `259.0239490659951 s`、p4 condensation `29.55984354500106 s`、interface stack setup `269.76726094100013 s`、H6 apply `563.9873873629695 s`、matrix operation `601.801216872962 s` 和 power `41.70184108400281 s`。这些是有嵌套关系的阶段账，不相加冒充 workflow 总时间，也没有足够的 matched component baseline 支持逐项因果归因。

资源按各自 authority scope 分列：V26 `run_summary.resource_authority` 的 process-tree RSS 为 `7381557248 B`、13247 个样本，swap 峰值 0；PSS `7346483200 B` 来自 worker-emitted process-tree PSS 的 1176 个样本。r2 的对应 process-tree RSS authority/PSS 为 `7390937088/7354803200 B`。V26 只观察到少量下降，不能据此形成一般性内存结论。

## 离线一致性回归

没有启动新 PDE。对已保存的 V26 与 r2 输出做了独立保存场、通道和功率重算：

- same-discrete FE field regression 通过；场记录中的相对 L2 为 `1.7056415936e-14`、scaled-curl 为 `7.5585951743e-14`。
- 另一份 selected-field checker 的 E/H/interface E/interface H 相对差分别为 `2.2178191553446018e-14`、`1.49476327946998e-13`、`1.3953770020874106e-14`、`9.81709619709013e-14`，最大值通过限值。
- 80/80 通道检查通过；saved-output checker 通过。
- power 最大绝对差 `1.1657341758564144e-14`，modal power 最大差 `7.16093850883226e-15`，modal amplitude 相对差 `1.3035632415474604e-14`。
- `abs(R+T+A_volume-1)=8.177012400523154e-10`，`abs(A-A_volume)=8.177012400523154e-10`，均在记录限值内。

动态 checker 从 131 个 boundary、262 个 logical p4 单元和 267 个实际 MatSolve 原始记录重算，5 次同 factor correction 后的最大最终 p4 相对残差为 `7.243731544969288e-11`，`all_final_p4_relative_le_1e-10=true`；修正前 raw 最大值 `2.8870661155266027e-10` 作为历史负观察保留。完整 derived record 见 [dynamic checker](records/setup_efficiency_v26_dynamic_checker.json)。

机器可读入口是 [FE regression](records/setup_efficiency_v26_r2_field_regression.json)、[power regression](records/setup_efficiency_v26_r2_power_regression.json) 和 [compact power record](records/setup_efficiency_v26_r2_power_regression.json)。完整 checker 原件位于 ignored artifact，记录了实际返回值和原始文件 hash；compact 中不手写替代 hash。

## 策略与边界

本轮正式运行的 worker summary 是 `observe_only`，但 wrapper/watchdog 原始记录仍保留 strict `require_zero_swap` 字段。该策略接线已在 `32bf03e0ab50ea67487ecb1ca06f5da468800482` 修正并做 targeted mock 测试；没有用修复后的 source 重新消耗 PDE 额度，因此不能把修复后的策略说成已在 V26 数值运行中验证。

local numeric cache/factor reuse 没有合格 loader、packet schema 或第二场证据。V26 实际是 `numeric_cache_mode=build`、`numeric_cache_loads=0`、numeric factor 未复用；T5 标记为 `DEFERRED`，不因结构 map 或 JIT reuse 推断收益。

最终决策见 [decision](records/setup_efficiency_v26_decision.json) 和 [selective merge manifest](selective_merge_manifest_v26.md)：r2 保持速度基线，V26 仅显式 opt-in/review-only，不改 ordinary default，不申请 master merge。
