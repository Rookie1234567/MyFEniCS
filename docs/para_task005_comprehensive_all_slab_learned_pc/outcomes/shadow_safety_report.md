# Shadow / safety report

| 项目 | 状态 | 原因 |
|---|---|---|
| P-shadow | `not_run_by_gate` | P2 operator+model storage failure |
| exact audit every call | `not_run_by_gate` | full-16 integration未解锁 |
| harmful/OOD distribution | `not_run_by_gate` | 无 shadow solve |
| proxy false accept | `not_implemented` | 无资格化 strict proxy |
| injected failure | `not_run_by_gate` | P2 已早停 |
| periodic audit drift | `not_run_by_gate` | P2 已早停 |
| P-fallback | `not_run_by_gate` | P-shadow 未运行 |
| true no-hidden-ILU | `not_run_by_gate` | P2 storage failure |

这不是“零 harmful”的证据。没有运行就保持 `not_run_by_gate`，不得写成 pass。
