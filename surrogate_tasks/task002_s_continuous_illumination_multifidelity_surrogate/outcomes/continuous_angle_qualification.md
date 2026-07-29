# M2 连续角域资格化

解析 order-window Gate 通过，但数值 pilot Gate 未通过。49 点 grid 上可传播 n=0 order 的
union 为 `m=-7..0`，被固定 `0,-1..-7,+1` 完整覆盖；n!=0 仍仅为 y-invariant 几何的数值
泄漏诊断。

四个角 corner 的 LF/HF center anchors 全部通过。首个新增 LF 点 `0.5°/15°/S` 的唯一正式
失败为 energy closure `-2.6061279e-5`（limit `1e-5`）。它同时位于 m0 near-cutoff：
`|beta|/k0=0.0087265`。residual、assembled E 和 exact traction 均通过，因此不是线性求解
失败；但现有证据不足以把它安全分区或纳入训练。

结论：`S-Hybrid computable across the full formal angle domain = not established`。M2 controlled
stop，禁止 bulk。
