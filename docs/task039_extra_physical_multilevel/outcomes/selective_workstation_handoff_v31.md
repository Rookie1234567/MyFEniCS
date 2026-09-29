# V31 选择性交接清单：本机 authority-limited 完成

本清单记录 V31 首次人工中止及其后用户明确授权的一场 completion rerun。第二次运行通过当前离散系统的完整残差和输出一致性 Gate；匹配参考场仍不可用，因此 FE field error 与跨离散误差未获得资格。该结果不构成端到端性能对照或跨机器迁移授权。

| 依赖组 | 内容 | 数值行为 / 证据 | 当前裁决 |
|---|---|---|---|
| production numerical/core | V31 H6 积分点自然序内部布局，显式 profile 接线 | 126 步；独立 final/post-release A6 residual=9.283162411158934e-7；80 模态和能量闭合通过 | 仅保留在显式 V31 profile；ordinary default 不变；等待 review，不推广到工作站 |
| reusable runner/watchdog | 既有 user-service runner 与 physical-memory-pressure watchdog | watchdog COMPLETED；tree RSS peak=7,331,401,728 B；后代清场；PSS disabled/null；swap observe-only | 没有新增通用 runner；不推断固定内存上限 |
| checker/benchmark | V31 dynamic checker 修正；新增只读 raw-output checker | dynamic=DYNAMIC_PASS_EVIDENCE_LIMITED；raw output=PASS_WITH_AUTHORITY_LIMITATION；19 targeted tests passed | checker 与小测试可审；manifest 线程变量证据缺项继续披露 |
| compact evidence/docs | response_v33、V31 outcome、test summary、授权重跑机器记录、run index | 首次 USER_CONTROLLED_STOP 及其 2.714e-6 checkpoint 仍保留；第二次 run 独立登记 | 供主控 review；授权账本和原始 output SHA 可复核 |
| research-only | 固定形状矩阵乘法、局部批处理、流式端口路线 | 未采用或本场未测 | 不提升为生产默认或工作站路线 |
| do-not-merge / do-not-promote | 端到端提速、连续极限收敛、field error 等价、跨机器资格、master merge | 无性能对照；参考场 unavailable；无最终 merge approval | 不做上述声明，不合并、不推广 |

本次完成 run 的 monotonic workflow 为 2313.526 s、保守 realtime settle 为 2534.117 s。该值是 completion 记录，不和首次停止场直接比较，也不解释为加速或变慢。完整字段与预算边界见 [authorized rerun record](records/projection_layout_v31_authorized_rerun.json)，首次停止证据见 [首场 compact record](records/projection_layout_v31_compact.json)。
