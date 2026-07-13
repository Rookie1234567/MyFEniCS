# Next Decision

下一步不应继续调 SciPy SPILU，也不应把 plain ASM/ILU 作为主线。

## 推荐任务

建立 `real-split same-H1 AMS/HX FE-response service`：

| 模块 | 目标 |
|---|---|
| real split FE block | 将 complex `A_FE q = rhs` 转成 real 2x2 block |
| same-H1 AMS/HX data | 复用 task013 中内存最低且收敛的 same-H1 auxiliary |
| service lifecycle | 在进程启动早期构造一次 AMS hierarchy，避免 repeated setup/destroy |
| selected RHS API | 输入 selected `C_j`，输出 filtered `q_j=-A_FE^{-1}C_j` |
| Schur integration | 先接 h=5 的 selected/full aux Schur，再 gated 到 h=2 |
| R/T/A gate | residual 达到阈值后必须回填 official dtn_port + A_volume |

## Gate

| gate | threshold |
|---|---|
| h=5 | official R/T/A 与 direct 差异在 `1e-8` 以内 |
| h=2 selected response | `relative_fe_column_cancellation < 1e-2` 或 one-shot residual 明显低于 ASM/ILU |
| h=2 solver | minimum useful: residual < 1e-2 或 improvement >= 2x |
| memory | peak RSS 明确记录，14 GB 内可运行 |

若 real-split AMS/HX 仍不能给出 h=2 selected response 正信号，再转向外部 direct selected-response cache 或 sweeping/domain-decomposition 预条件器。
