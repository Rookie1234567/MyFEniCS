# L5：条件 T6-S 20/100/150/200 步 screen

## 状态

L5 是条件 screen：只有 L4 五类 exact-A contraction 全部通过后，才允许运行固定 restart=20、max_it=200 的 true-residual screen。本次 L2 首案已 hard stop，L5 未启动。

| checkpoint / 项目 | 状态 |
|---|---|
| iteration 20 | `not_run_by_L2_gate` |
| iteration 100 | `not_run_by_L2_gate` |
| iteration 150 | `not_run_by_L2_gate` |
| iteration 200 | `not_run_by_L2_gate` |
| true residual history | 无 |
| wall / matvec / PC apply | 无 |
| process-tree peak / swap | 无 |
| T6-F、official physics、R/T/A、full 0.7 nm PDE | `not_authorized` / `not_run` |

L5 没有任何数值或资源结论。不得把 L2 positive auxiliary 的一次 rho、单进程 RSS 或 L1 transfer 结果写成 T6 screen 结果，也不得因 L2 失败自行改变 screen 参数或继续运行。
