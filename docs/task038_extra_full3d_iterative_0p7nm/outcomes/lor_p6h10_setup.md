# L3：p6/h10 cold setup 与 one-apply 资源资格

## 状态

L3 依赖 L2 的 p2/p3 positive auxiliary contraction 资格。L2 在 `p2-mpi1/random` 首个冻结 source 上以
`rho=1.7348663090876784 > 0.45` hard stop，因此 L3 没有启动。

| 项目 | 状态 |
|---|---|
| L3 classification | `not_run_by_L2_gate` |
| p6/h10 cold setup | 未运行 |
| p6/h10 LOR topology / AIJ inventory | 未运行 |
| GAMG hierarchy retained measurement | 未运行 |
| post-setup retained process-tree measurement | 未运行 |
| one-apply p6 resource Gate | 未运行 |
| swap / cold peak / retained peak | 无数值、无资源结果 |

## 不能从 L2 推导的结论

L2 的 p2 单进程 `/usr/bin/time -v` 观察值 `137,695,232 B` 只描述那个已完成的小 case，不能代替 p6/h10 的 cold process-tree authority，也不能证明 `<2 GB`。同样，L2 fixture 的局部 rows、LOR cells 和 map metadata 不能外推到 p6/h10 的完整 hierarchy、transfer、MPC ghost 或 retained live set。

因此本文不写 p6/h10 的 inventory、峰值、GAMG 层数、one-apply 结果或任何 PASS。没有为 L3 创建 formal record，也没有重跑 FC3 或压缩 rank/mode/lifecycle。

## 依赖边界

L3 原合同中的 p6/h10 setup、LOR edge/nodal AIJ、reference-factor transfer、一个共享 scalar PCGAMG hierarchy、post-setup retained closure 和禁止项审核全部属于未执行内容。L2 hard stop 后，L4/L5 也同样保持 `not_run_by_L2_gate`。
