# P5 Periodic exact audit report

`P5 = not_run_by_gate`。

P2 没有产生 usable、可冻结的 two-seed composite proxy，故 P3 locked replay 未解锁，
P4 fault injection 也未解锁。没有安全候选可用于比较 K=4/8/16/32；此时继续优化
periodic schedule 会绕过 frozen Gate，并可能用 exact audit 频率掩盖 proxy 的高
false-reject。

P1 已独立测得单个 collective borrowed exact audit 约 6.207 ms，可供未来架构预算
参考；这不等于 K schedule 已资格化，也没有 drift latency 结论。
