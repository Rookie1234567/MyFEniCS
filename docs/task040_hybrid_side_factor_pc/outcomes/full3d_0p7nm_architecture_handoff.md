# Full3D / 0.7 nm architecture handoff

## Handoff status

| 项目 | 当前状态 |
|---|---|
| qualified Full3D architecture candidate | `NOT_ESTABLISHED` |
| 0.7 nm PDE / h3 scaling | `not_run` |
| factor-free candidate | `not_established` |
| full-spectrum two-source | measured numerical no-signal |
| full Hybrid | `not_run` |
| V9-E entry | established；fallback 未取得 qualified physical positive |
| merge boundary | 按依赖分组审阅；research-only 组件不等于全部代码 do-not-merge |

本页是已经建立的 boundary handoff，不是 capacity claim。当前没有足够证据把任一
research-only exploratory component提升为可部署架构候选。

## 为什么不能形成 qualified architecture candidate

| 前置条件 | 现有事实 | 结论 |
|---|---|---|
| full-spectrum source route | transform通过；两源 screen 为 `FULL_SPECTRUM_SWEEP_NO_SIGNAL` | 两源 one-apply/r8/r16/r32/r64 均已形成 |
| adaptive coarse route | Stage A local component通过；B/C在显式 coarse symbolic resource Gate停止 | 没有完整 outer residual |
| C0 | worker one-apply no-signal measured；watchdog terminal resource authority未闭合 | numerical Gate 已形成；C1 按 Review §5.5 不运行 |
| corrected external | worker 已形成 numerical no-signal，explicit residual=`0.7349227023138162`；watchdog result/resource wrapper 因旧 cleanup terminal bookkeeping 仍待裁决 | 无 positive |
| fine geometry/resource | 没有 h3、0.7 nm 或完整 Hybrid fresh PDE | 不得外推 scaling 或 2 TB 可行性 |

## 已知资源边界

历史 0.7 nm 文档中的 `NOT_ESTABLISHED / resource-blocked` 保持不变。C0 explicit route 的 peak RSS 为 `86960574464 B`，adaptive B/C 的 conservative projection 为 `130502065136 B`；二者属于不同对象生命周期，不能拿来预测 matrix-free C1 或 0.7 nm。

## 后续边界

V9-E 已满足进入条件，但 fallback 没有 qualified physical positive，因此 qualified architecture
candidate 与 0.7 nm capacity 仍未建立。本页是 boundary handoff 记录，不是已部署架构或容量结论。
任何未来 handoff 仍需单独资格化完整 source/residual 和资源生命周期；
未取得新授权前，不启动 C2、five-source、top/full Hybrid、recovery、RTA 或 0.7 nm PDE，也不改变
ordinary defaults、Task39、M480、physical DtN 或物理方程。
