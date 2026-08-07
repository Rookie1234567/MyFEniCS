# Task037 V7 最终响应：静态凝聚 Full3D 迭代收口

## 结论先行

| 事项 | 当前结论 | 资格边界 |
|---|---|---|
| E0 Matrix-free DtN | 通过；80/80 模态，40/40 每方向 | component Gate；ordinary default 未改变 |
| M3a Full3D iterative | 通过 MPI1/2/4/8 | explicit opt-in research baseline，不是 production default |
| canonical active/full | 两组 comparator 通过 | relative tolerance `1e-5`；仅证明 canonical identity |
| A | closed negative | 不生产化 |
| B2 long-tail | plateau，closed | 不把 200-step 停滞当成功 |
| B4 extension | closed | 不作为 Task37b 算法 |
| C | 当前 RAS 路线 closed | 不合入 production |
| D | contraction negative | 不生产化 |
| R7/p4 | partial component-positive | public complement 未闭合 |
| F | frozen ideal-capacity negative | coarse-capacity 不足 |
| E | E1 basis pass；E2 late residual `6/6` fail | Candidate E closed，不是 Task37b |
| E3–E5 | `not_run` | V6/V7 硬停止 |
| E6 | completed | 本文与 Case100 compact evidence |

V7 的 reviewed source 是 `d8b16c349f7726b4873ce1932668c12a1ba78926`。V7 review
commit 是 `229aaf743072550fa07bb0f03f9c4104e6a25d63`，V7.1 remote-handoff commit
是 `d8b16c349f7726b4873ce1932668c12a1ba78926`。最终数值 formal 使用
`0fcf08a3f09e3beb137212d41f411823cb2e24e8`；其后仅发生 test53、格式合同和本
文档收口变化。本文不把后续文档 SHA 冒充数值源码 SHA。

## 1. 研究对象与算法边界

静态凝聚把每个高阶单元内部的自由度先精确消去，只在剩余界面未知量上做外层
迭代。matrix-free fine action 则在需要乘算子时通过局部 Schur action 计算，
不把完整全局矩阵 `A/F` 物化。M3a 再用 owner-local physical slabs、75 维
coarse space、factor-only ILU 和右 FGMRES 处理剩余的全局耦合。

M3a 是显式 opt-in 的 p6/h10 数值 qualified research baseline。它约需 `91.4M`
个 p6 local factor NNZ，因此不能宣称 `0.7 nm` 的 resource scalability，也不能
改变 ordinary defaults。Task37b 只保留为 V7.1 的远程分支交接计划；本 docs commit
形成时尚未创建，只有 master 成功 push 后才按 V7.1 创建并 push，且不开发。

```math
A_{\mathrm{condensed}} = F - C H^{-1}D
```

## 2. 最终数值证据

### 2.1 E0：Matrix-free DtN component

| 指标 | 实测值 |
|---|---:|
| status | `pass` |
| modes | `80/80`，每方向 `40/40` |
| primary C/D materialization | `0/0` |
| global A/F materialized | `false/false` |
| action error max | `1.2367630350859273e-15` |
| recovery error max | `1.1141146096537195e-15` |
| physical RHS identity | `0` |
| oracle | `1/1` |
| ordinary_default_changed | `false` |
| wall | `304.9213732070057 s` |
| process-tree peak | `0.662296 GiB` |
| swap | `0` |

这是一个正的 component correctness Gate，不是对 M3a 或 `0.7 nm` 的完整资源
承诺。矩阵统计对 MatPython/SHELL 使用 `not_applicable` 语义，显式 assembled
AIJ 的统计语义保持不变。

### 2.2 M3a：p6/h10 MPI scaling

| MPI | process-tree peak | wall | 状态 |
|---:|---:|---:|---|
| 1 | `4.600 GiB` | `1999 s` | pass |
| 2 | `5.683 GiB` | `1153 s` | pass |
| 4 | `8.266 GiB` | `712 s` | pass |
| 8 | `12.593 GiB` | `471 s` | pass |

资源表是同时存活的 process-tree 峰值，不是累计对象体积，也不是 `0.7 nm`
预测。正式最终-source MPI4 记录如下：

| 指标 | MPI4 final-source 值 |
|---|---:|
| status / profile | `pass` / `never_materialized_owner_local_overlap0125_partition` |
| KSP | `CONVERGED_RTOL` / `365` |
| reported residual | `9.923273221632137e-07` |
| condensed true residual | `9.923273222042328e-07` |
| full augmented true residual | `9.923273222042328e-07` |
| full-FE relative residual | `9.923273521134805e-07` |
| official result | `true` |
| significant powers / amplitudes | `12/12` / `12/12` |
| R | `0.0007628813414780547` |
| T | `0.6027016365247433` |
| A_volume | `0.396535483656842` |
| closure | `1.0000000015230635` |
| coarse / slabs / overlap | `75` / `16` / `0.125` |
| coarse condition estimate/number | `4754.709602715809` |
| global A/F | `false/false` |
| global factor | `0` |
| wall / peak | `696.873 s` / `8392.023 MB = 8.195335 GiB` |
| swap | `0` |

四个 residual 字段分别是 reported residual，以及 condensed、full-augmented、
full-FE 三个 explicit/true residual；`official=true` 只在这些 residual、12/12
通道和 closure 共同通过后成立。

### 2.3 Canonical active/full identity

| manifest | SHA256 | common | missing | extra | duplicate | relative L2 | 结论 |
|---|---|---:|---:|---:|---:|---:|---|
| active | `e01458aa9380276fa02522ca230e5a913e654e71e7c22a73211634feda389d23` | 60402 | 0 | 0 | 0 | `1.2553897989392794e-06` | PASS |
| full | `095c19eeae37bed2b605e54d0247e034376f50f36fb016329827b6ea3bb6b004` | 173802 | 0 | 0 | 0 | `7.880394014572244e-07` | PASS |

两组 comparator 都使用 `relative_tolerance=1e-5`。ownership-order 不是跨运行的
canonical physical identity；这里比较的是现有 canonical artifact contract，不是
把不同 partition 的 local row 编号直接当作同一编号。

## 3. A–F/E 关闭表

| 路线 | 最终裁决 | 证据边界 |
|---|---|---|
| A | closed negative | 不把失败的低内存预条件器提升为 production |
| B2 long-tail | residual plateau，closed | 200-step screen 不是 convergence success |
| B4 extension | closed | residual carrier 保留作历史证据 |
| C | current RAS closed | 不把 failed RAS 路线带入 master |
| D | contraction negative | 不能用 contraction proxy 代替 Full3D Gate |
| R7/p4 | partial component-positive | public complement 与完整 production contract 未闭合 |
| F | frozen ideal-capacity negative | ideal coarse action 仍不足，不能达到 late-residual 门槛 |
| E1 | 240/240 basis pass | M120 implementation Gate 通过 |
| E2 | implementation 全通过；late capacity `6/6` fail | 约 `0.3–0.4%` 改善，Candidate E closed |
| E3–E5 | `not_run` | 不因 E2 负结果继续扩大候选 |

E2 的 ideal capacity oracle 给 M120 最有利的系数；如果在这种最有利情况下，
late residual 仍只能改善约 `0.3–0.4%`，那么同一 coarse action space 的正式
preconditioner 不可能满足 V6 的 late-residual 门槛。这是 capacity negative，
不是内存或环境失败；它也不是 Task37b 的算法结论。

## 4. selective merge 与提交 provenance

本次 master 采用文件/hunk 级 selective merge，不做 whole-branch merge 或大型
cherry-pick。本 docs closeout 之前的 10 个 selective code/test commits 为：

| SHA | 职责 |
|---|---|
| `f1e14315dc3de7a0afcc58c1aa2041b79c7691bc` | static-condensed Full3D foundation |
| `9ea04c0fb5fe153fe37a7e9048fc1b5dd8cf2e37` | matrix-free DtN 与 action-only telemetry |
| `71f92e0031c1db2cc59e24ee96989ff77d342e68` | slim static-condensed iterative core |
| `1aa84568db3f07716151badfea9b92b25c74e353` | canonical trace 与 modal safety |
| `211ea4908ab5fe09b79928a54b35e4a80e39b1ba` | never-materialized local-Schur authority |
| `3fa5e54f56140d963a820b7bd76a2f58113d648c` | focused iterative/matrix-free tests |
| `c5ce98d45ced817014e07fa56c915ecfb2b34b1f` | Matrix-free DtN probe telemetry |
| `0fcf08a3f09e3beb137212d41f411823cb2e24e8` | external solver profile telemetry |
| `0f3dbacc38cd797f7a59272b4f185393e7980121` | reviewed high-order Hybrid quadrature contract |
| `55cf2555ac5b3aa52878091869f03fb94a2c0765` | test53 mechanical formatting closure |

V7/V7.1 review材料本身的 provenance 是 reviewed source `d8b16c3...`、V7
review commit `229aaf7...`、V7.1 handoff commit `d8b16c3...`；它们不能与
final-source numerical SHA 混写。

### 可审查能力与不合入能力

| 分组 | 处理 |
|---|---|
| reusable production foundation | MatPython-safe telemetry、matrix-free DtN action、external solver lifecycle、canonical comparator 与 M3a opt-in core |
| research-only | M3a 的 p6/h10 baseline、所有 A–F/E candidate negative、E1/E2 modal capacity evidence |
| do-not-merge | p2/p4/factor-free candidate families、M120 capacity/campaign runners、E1/E2 snapshot/capacity CLI、RAS 失败实验、旧 raw artifacts |

显式排除的 named files 为 V7 列出的 10 个 solver 文件和 17 个 negative tests，
共 27 个；另排除 A/B2/B4/C/D/F/E campaign CLI、funnels、capacity/M120、p4
和 raw families。Task37b 的 task、代码和 remote branch 在本 docs commit 形成时
尚未创建；只有 master 成功 push 后才按 V7.1 创建并 push，且不开发。

## 5. 测试与最终边界

| Gate | 结果 |
|---|---|
| serial targeted | `85 passed / 7 skipped` |
| MPI2 targeted | 每 rank `58 passed / 2 skipped` |
| MPI4 targeted | 每 rank `9 passed / 1 skipped` |
| assembled/no-global-AF smoke | 各 `1 passed` |
| telemetry final patch | serial `8 passed`；MPI2 每 rank `1 passed` |
| formal E0/M3a | pass |
| canonical active/full | pass |
| full repository pytest（唯一一次） | `849 passed, 48 skipped, 3 failed`；`1115.51s` |
| full-suite后的最小闭环 | test53 reviewed contract 修复后 `3 passed`；最终格式后 `3 passed/223.86s`；test69 补齐 5 个历史对象且源码不改后 `3 passed/0.25s` |

full pytest 不改写为 PASS，也没有第二次 full pytest。已知三项失败均已按最小
闭环完成：test53 是已审查的 quadrature contract 陈旧断言，test69 是历史 Git
对象依赖。最终结论是 targeted closure 后没有剩余已知 failure；这不等于把
full-suite 原始 exit=1 改写成无条件全绿。

本响应和 [Case100 README](../../benchmarks/cases/100_static_condensed_full3d_iterative/README.md)
共同构成 closeout 入口；5 个 compact records 见
[Case100 records](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/)。
完整审阅边界见 [review_report_v7.md](review_report_v7.md) 和
[review_report_v7.1](review_report_v7_1_task37b_remote_handoff.md)。

最终状态：Task037 closed；ordinary defaults unchanged；M3a 保留为 explicit
opt-in research baseline。Task37b 在本 docs commit 形成时尚未创建，后续只有在
master 成功 push 后按 V7.1 创建并 push，且不开发。
