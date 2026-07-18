# P7 R4 live shadow report

`P7 = not_run_by_gate`。

P2 Q0 calibration 没有产生 usable locked proxy，P3-P6 未解锁，因此不允许把
learned output、proxy 和 periodic exact audit 接入 live solver。Task006 没有运行
R4 shadow，也没有 active learned writeback。

已知且仅可作为前置 guard 的证据：

| 项目 | 证据 |
|---|---|
| P0 ordinary ILU | 852 iterations；numeric/RTA pass |
| P1 qualification后 ordinary ILU | 852 iterations；三 residual/RTA一致 |
| ILU writeback shadow | 未运行 |
| live proxy false accept | 未测试 |
| live periodic latency | 未测试 |
| paired shadow peak | 未测试 |

ordinary default 未改变。不得声称 live shadow safe、learned acceleration 或
Task005 P3 已可恢复。
