# Task041 V7：5 nm 冻结输入因果修正进度

**进度快照；V7 未完成。** Q 是粗层校正，p4 恢复是回到原有限元自由度，A4 是原方程残差检查。

## G1 实测

Rank0 汇总覆盖 rank 0–7，PC1 的 Q1/Q2 各 rank 全局比较标量相同。G1 只覆盖列 12/493/666；每列两后端自由响应，7 个冻结 PC 节点（1、30–33、56、57），14 次独立 Q 重放。

| PC1 冻结输入 | 输入与 PH 输出 | p4 恢复相对差 | Q 输出相对差 / 原限值 | A4 physical full / condensed | A4 augmented full / condensed |
|---|---|---:|---:|---:|---:|
| Q1 | Q 输入、PH 输出均逐字节相同 | `4.825884073423821e-11` | `4.835081880078008e-11` / `1e-11`，失败 | `3.9464450760276146e-11` / `6.182890011924572e-11` | `2.8873234816987417e-11` / `5.637969700358617e-11` |
| Q2 | Q 输入、PH 输出均逐字节相同 | `5.164430142728058e-11` | `5.19243276103674e-11` / `1e-11`，失败 | `3.4284403371928055e-12` / `5.409279310936007e-12` | `2.2433325962304662e-12` / `4.309485690767991e-12` |

A4 四组值均低于原 `1e-10` 门。14 项独立 Q 全超 `1e-11`；首次已记录差异在 p4 恢复，但根因未证明。7 项独立 PC 全过 `1e-8`，相对差范围 `4.947082135840808e-11`–`5.6776937919181746e-11`。

| 列 / manifest ordinal | e_x | e_A | 原限值 `1e-8` |
|---|---:|---:|---|
| 12 / 5 | `1.1210098132838252e-8` | `3.042995719987375e-8` | 两项失败 |
| 493 / 7 | `2.8209859775046248e-8` | `7.657308734067504e-8` | 两项失败 |
| 666 / 6 | `4.6517113135754246e-12` | `2.761034144410454e-12` | 两项通过 |

`e_x` 是响应向量相对差；`e_A` 是原 side operator 作用后差的相对量。

## G1/G2 身份、路径与终态

时间由主控宿主通过 `systemctl --user show` 核验的 CST 读数换算为 UTC；表中精确 wall 使用各自 finalizer，不以秒级起止差替代。

| 阶段 / source SHA | Unit / Invocation / PID | UTC start–exit / finalizer wall | Public runroot | Outerroot / finalizer |
|---|---|---|---|---|
| G1 / `e2965ee25e56220d1623afe4dd221612542c2764` | `task041-g1c-5nm-top-causal-20260924.service` / `c92af396fec2441a91661223c91af9af` / 246596 | `2026-09-23T23:10:59Z`–`2026-09-24T00:01:45Z` / `3047.166289001 s` | `results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260923T231100.070610Z` | `results/task041_review_v6_transfer_and_5nm_24h/g1c_top_causal_run_20260924` / `finalizer/finalizer_summary.json` |
| G2 first / `28c2ca95c9ca9ae0431797c66449b30be97c0cac` | `task041-g2b-5nm-pc1-frozen-q-correction-20260924.service` / `36836ada01ba46b8bbd3693c0ef8b010` / 307083 | `2026-09-24T06:49:57Z`–`07:17:49Z` / `1673.342361168 s` | `results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260924T064958.063572Z` | `results/task041_review_v6_transfer_and_5nm_24h/g2b_frozen_q_correction_20260924T063626Z` / `finalizer/finalizer_summary.json` |
| G2 layoutfix-r1 / `ed16b8e3d55aa15b99a9c2d596bef2431c2f42d7` | `task041-g2b-5nm-pc1-frozen-q-correction-layoutfix-r1-20260924.service` / `7f479b688f8141c49f340d6ae1b8d55a` / 317364 | `2026-09-24T08:20:03Z`–`08:47:56Z` / `1673.806519391 s` | `results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260924T082003.946929Z` | `results/task041_review_v6_transfer_and_5nm_24h/g2b_frozen_q_correction_layoutfix_r1_20260924T080226Z` / `finalizer/finalizer_summary.json` |

两场 G2 都将 `--task041-p4-correction-replay-from` 指向同一 G1 public runroot，目标是 G1 PC1 的 Q1/Q2；两次都未实际加载并执行修正。首次 source `28c2...` 在 setup 因 capture-layout 缺字段退出；source `ed16...` 修 capture 开关后进行第二次，stable layout admission 报差异。后续 `6d27033...` 只增加 gate 前比较证据持久化，没有真实运行，也没有解决现场差异。

G2 两场 tree/authority 峰分别 `38718169088 B`、`39235481600 B`；cap `53221163008 B`、warning `47899046707 B`、swap `0 B`。九项比较字段运行时已计算，但新 hash 未持久化；独立 `layout_identity_full` 与 `layout_identity_cell_condensed` 文件均 `not_generated`。微测刻意改变 dofmaps 是 synthetic 输入，不是现场差异。三场用户服务终态均 failed/failed、Result `exit-code`、ExecMainStatus `3`、MainPID `0`；finalizer 清场、artifact hash、ledger 写入检查通过。

G1 Q manifest 实际目录：
- Q1: `results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260923T231100.070610Z/consumer/numerical_output/top_causal_replay/full_reference/pc_00001/q_01_input_output/manifest.json`，SHA-256 `d947fe58d52ff7e3fa293cadd193854652529d5066bde1c8b42d26f9ac079297`。
- Q2: 同目录 `q_02_input_output/manifest.json`，SHA-256 `ced34ee9e9ee174799d4cd09b70924385c5aebf51339cbc835c72fafbd6eba0b`。

## 当前边界与下一步

G1 九项旧 layout component hash 已保留，G2 新 hash 未持久化，无法离线恢复或认定某个 component 变化。V7 唯一 blocker 是跨运行冻结输入布局身份未证明。完整 5 nm consumer、G2 stage 0/1/2、PC、Schur、outer/RTA/EH 均未运行。V5 ledger 仍是 40 entries / `30664.492338104035 s`；本快照不追加费用。

下一步：用已提交的落盘代码取得同一最小 top/PC1 诊断的真实新旧九组件比较；身份门不过则在载入前逐项归因并停止，不关门、不按长度加载。身份通过后，才对 Q1/Q2 执行最多两次同因子修正。
