# V11 memory, residual and time boundary

## 口径

本页区分完整 workflow 峰值与单一 research component。V11-1 的 12.7808799744 GiB 是只读 bottom projection/algebra component 的过程树峰值，不是完成 workflow 的 saving，也不能与 direct full workflow 直接比较。

| 参考对象 | 峰值/边界 | 状态 |
|---|---:|---|
| historical direct full workflow | 93.377006531 GiB | inherited authority |
| historical best full workflow | 80.025856018 GiB | inherited authority |
| inherited bottom exact-side producer | 50.7548675537 GiB; payload 2034244800 B; max residual 1.52248376596e-10; factor 1→0 | sequential component evidence |
| V11-1 bottom component | 12.7808799744 GiB | measured component only |
| V11-1 hard stop | 45 GiB | not reached |
| swap | 0 | pass |

完整 workflow 的峰值口径是同时运行阶段的最大过程树峰值，而不是各阶段求和：

```math
workflow_peak = max(bottom_producer_peak, top_producer_peak, consumer_peak)
```

本轮只测了 bottom component，因此 workflow peak、cold/reuse wall 和新的 saving tier 都是 not_established。历史 best full 相对 direct 的 14.298113646% 仍是唯一完整 workflow saving authority；74.701605225、65.363904572、56.026203919、46.688503266 GiB tiers 没有被本轮刷新。

此前 45.277 GiB controlled stop 到本次 12.781 GiB projection completion 说明 row-flush/streamed projection 修复消除了该阶段的实现/内存阻塞；它没有证明 response packet 的 AX、Schur 或 trace algebra。
