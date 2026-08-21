# V8-4：layer-sweep full formal

| 项目 | 状态 |
|---|---|
| full formal | `not_run` |
| 阻止原因 | bottom `LAYER_SWEEP_NUMERICAL_LIMIT_NOT_REACHED_BY_FB4` |
| outer/recovery/physics | `not_run` |
| R/T/A、field、closure | `not_run` |

没有通过 bottom preferred action，就没有资格构造 both-side 或 full formal。这里不生成任何
full-workflow residual、memory saving 或物理结果。
