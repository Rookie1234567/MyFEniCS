# L4：exact-A 五类 source contraction

## 状态

L4 必须使用当前 exact physical operator（T2 matrix-free volume action + T3 streaming Fourier-DtN），对五类 source 计算 `rho=||r-Az||/||r||`。L2 在正定辅助算子 `B_h` 的首个 source 已失败，所以 L4 未获授权启动。

| 项目 | 状态 |
|---|---|
| L4 classification | `not_run_by_L2_gate` |
| exact physical `A` | 未构造、未应用 |
| T2 volume + T3 DtN | 未用于本阶段 |
| 五类 exact-A source | 全部未运行 |
| rho / repeat / closure | 无数值结果 |
| process-tree / swap | 无 L4 资源结果 |

L2 的 `rho=1.7348663090876784` 是 positive auxiliary `B_h` 一次应用的 formal 负结果，不能改写成 exact-A 的 rho，也不能外推成 physical Maxwell、DtN 或散射失败。反过来，L2 也没有证明 exact-A 会通过或失败。

本阶段没有调 omega、shift、scaling、V-cycle、source 顺序或参数；没有生成 physical RHS、R/T/A、E/H 或 PDE 结果。L4 关闭只表示其前置 L2 Gate 未通过。
