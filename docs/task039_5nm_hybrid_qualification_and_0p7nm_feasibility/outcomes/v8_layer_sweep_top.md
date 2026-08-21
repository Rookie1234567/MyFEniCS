# V8-4：top layer-sweep component

| 项目 | 状态 |
|---|---|
| top layer-sweep | `not_run` |
| 阻止原因 | bottom `LAYER_SWEEP_NUMERICAL_LIMIT_NOT_REACHED_BY_FB4` |
| top resource/residual | `not_available` |
| top raw/formal evidence | 不存在 |

Review V8 要求 bottom preferred action 同时满足数值与资源 Gate 后才可进入 top。本次 bottom 在 FB4
仍未通过 mandatory residual、preferred residual、repeat 和 linearity，因此没有启动 top，也没有创建
top factor、top Woodbury 或 top holdout 结果。
