
# V8-1 authority：六层 block operator 重构

V8-1 已有独立 formal component：它只从真实 h4 side `F` 的稀疏连接重构六层 block-tridiagonal action，
不建 layer factor、不读 selected-mode packet、不做 QEP 或 outer solve。完整 JSONL 的 process-tree RSS
历史最大值为 `16180523008 B = 15.0692863464 GiB`（15430.94921875 MiB）；PSS/USS 未测量。六层、132300 rows、105038640 NNZ、
same-layer 75327840、adjacent 29710800、long-range 0、half-bandwidth 1 与原始 F action identity
均通过，bottom/top 采用同一 graph pattern。

V8-3 的 layer sweep 是后续独立数值动作：它使用六个 layer factors 与 five-candidate sweep，
construction peak `22.273887634 GiB`，但五个冻结 source residual/稳定性 Gate 未通过。V8-1 graph/action
通过不能替代 V8-3 residual，也不能把 V8-3 的负结果回写为 graph operator 失败。

| 证据 | status | 边界 |
|---|---|---|
| V8-1 graph reconstruction | `PASS` | local-F action/graph authority；不是 full solver |
| V8-3 bottom layer sweep | `LAYER_SWEEP_NUMERICAL_LIMIT_NOT_REACHED_BY_FB4` | resource construction pass，numerical negative |

后续 top、both-side、matrix-free K 和 full formal 均需独立 Gate；本结项不把 V8-1 graph evidence
外推为这些阶段的结果。
