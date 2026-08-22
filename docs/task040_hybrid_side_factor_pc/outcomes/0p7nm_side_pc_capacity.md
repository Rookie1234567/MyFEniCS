# 0.7 nm side-PC capacity boundary

## Status: not_run_by_gate

T40-3 只验证了固定三组、固定一阶 impedance 和固定 forward/backward sweep 的
cross-section oracle；五个非零 source rho 全部超过 `<1` mandatory Gate。因此它不能作为
0.7 nm-oriented side inverse，也没有证明所有 bounded local PC 失败。

Task40 没有运行 0.7 nm PDE、h3 scaling、完整 Hybrid 或 coarse-space experiment。当前最
严格的结论是：冻结的 Level-A transmission mechanism 不足以进入可扩展候选；若未来继续，
必须先重新审议传输机制和全局信息来源，并保持冻结物理与输入身份。

由于 exact subdomain solve 仍给出 rho>1，当前缺失类别可定位为人工截面上的跨截面/多模
切向传播耦合信息；固定标量一阶 impedance 不足以表达它。这排除了“只是 local solve 不准”
作为当前根因，但没有证明必须使用 coarse、modal DtN 或任何单一具体实现。
