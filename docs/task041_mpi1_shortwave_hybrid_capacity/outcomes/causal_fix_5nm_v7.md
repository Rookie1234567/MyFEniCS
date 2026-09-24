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
| G2 layoutfix-r2 / `646c9fff0d08894a8dc634694caa32427bd71707` | `task041-g2b-5nm-pc1-frozen-q-correction-layoutfix-r2-20260924.service` / `81be501b290a45498314190e3049b245` / 342129 | `2026-09-24T10:54:03Z`–`11:24:47Z` / `1844.843103958 s` | `results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260924T105403.903510Z` | `results/task041_review_v6_transfer_and_5nm_24h/g2b_frozen_q_correction_layoutfix_r2_20260924T103628Z` / `finalizer/finalizer_summary.json` |

三场 G2 都将 `--task041-p4-correction-replay-from` 指向同一 G1 public runroot，目标是 G1 PC1 的 Q1/Q2。第一次 source `28c2...` 在 setup 因 capture-layout 缺字段退出；第二次 source `ed16...` 进入 stable-layout admission，但当时的新 component hash 未落盘，无法离线归因；`6d27033...` 加入 gate 前持久化，仍未运行。第三次 r2 使用 runtime source `646c...`，跨运行布局匹配，实际执行两条冻结 Q 的 0/1/2 修正。QEP producer source `b01a5932e4dfaf895e81e0424e0dd88c276fb0d3`；冻结输入 producer source `e2965ee25e56220d1623afe4dd221612542c2764`。

r2 的实际布局证据为 `.../p4_correction_replay/layout_identity_full.json`（SHA-256 `57f9ebfcb97a3545503ae4cc977ab40e7c81c40f65745f1d8e75eef258cae6b9`）和 `.../layout_identity_cell_condensed.json`（SHA-256 `555a2849a4391420738f7edc3fec5525a59a3cb7197826a0b2bf79a1aaf074d3`）。两个文件报告九项稳定 component 均与 G1 相等；逐项哈希见[机器记录](records/task041_v7_causal_fix_5nm.json)。

| 冻结 Q / step | Q 相对差 / 原限值 `1e-11` | A4 physical full / condensed | A4 augmented full / condensed | 结果 |
|---|---:|---:|---:|---|
| Q1 / 0 | `4.826827545952679e-11` | `4.2214278202527563e-11` / `4.9836562161252183e-11` | `2.982659400763239e-11` / `3.8591594436739914e-11` | Q 门未过，A4 均低于 `1e-10` |
| Q1 / 1 | `2.9154557401617235e-14` | `2.7898389312522253e-13` / `2.8037021777498243e-13` | `2.780951238507559e-13` / `2.7975386489391366e-13` | Q 与 A4 门通过 |
| Q1 / 2 | `3.0334089133384796e-14` | `2.5565072489466694e-13` / `2.523744734771677e-13` | `2.542088696638946e-13` / `2.5202730709359755e-13` | Q 与 A4 门通过 |
| Q2 / 0 | `5.193718954731701e-11` | `4.040344646356816e-12` / `4.895811675797742e-12` | `2.2078218929184212e-12` / `4.3345116992037406e-12` | Q 门未过，A4 均低于 `1e-10` |
| Q2 / 1 | `3.306986700793151e-14` | `2.401046144441526e-14` / `2.3794855457533597e-14` | `2.3796436277556684e-14` / `2.3655598898257527e-14` | Q 与 A4 门通过 |
| Q2 / 2 | `1.6691082262359168e-14` | `2.1648127213089485e-14` / `2.1511287184330335e-14` | `2.1560806857664992e-14` / `2.1421684040343718e-14` | Q 与 A4 门通过 |

所有六步输入 identity、冻结输入字节和有限性检查通过。r2 worker 的 correction action gates 通过，`qualification_pass=false` 是诊断模式的有意状态，不代表数值失败或正式资格。原 service 仍以 `ExecMainStatus=3` 结束：public supervisor 当时把 `summary.setup.side_setup.side_completion.top` 误读成顶层 `side_setup`，并要求了错误的释放状态。代码提交 `3bcf00527b3b2440a66792e079c6667cb30aec2d` 修正该只读合同路径/状态；用真实 r2 输出再次调用 `_consumer_result` 后，五项合同检查全真、诊断 complete。原 service/finalizer/exit3 raw 保留不改。

G2 三场 tree/authority 峰依次为 `38718169088 B`、`39235481600 B`、`43820285952 B`；r2 cgroup peak 为 `41557790720 B`。cap `53221163008 B`、warning `47899046707 B`、swap `0 B`。r1 的新 hash 未持久化，synthetic dofmap 反例不代表现场差异；r2 的 stable-layout 比较及全部五个 correction contract check 通过。三场用户服务的历史终态均 failed/failed、Result `exit-code`、ExecMainStatus `3`、MainPID `0`；r2 原因是 public schema误拒绝，不应覆写为服务成功。用户允许隔离并行，但 r2 与 Task39extra 并发，因此它不是无竞争性能对照，性能 `not_qualified`。finalizer 清场、artifact hash、ledger 写入检查通过。

G1 Q manifest 实际目录：
- Q1: `results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260923T231100.070610Z/consumer/numerical_output/top_causal_replay/full_reference/pc_00001/q_01_input_output/manifest.json`，SHA-256 `d947fe58d52ff7e3fa293cadd193854652529d5066bde1c8b42d26f9ac079297`。
- Q2: 同目录 `q_02_input_output/manifest.json`，SHA-256 `ced34ee9e9ee174799d4cd09b70924385c5aebf51339cbc835c72fafbd6eba0b`。

## 当前边界与下一步

G1 九项 layout component hash 已保留；r2 stable-layout 门匹配。G2 correction replay 完成的是 PC1 两个冻结 Q，不代表完整 5 nm consumer。G1 原独立 PC 7/7 通过；仅 r2 及新修正策略下的 PC action/side.apply、Schur、outer/RTA/EH 未运行。r2 并行性能 `not_qualified`。公共结果合同 4 项 targeted 节点展开为 9 passed/rc0、父 wall `2.000488571 s`；read-only recheck wall `0.006336727 s` 单列，不收费。V5 ledger 现为 42 entries / `32511.335930633035 s`：只增加本次 pytest parent wall，一次记 `2.000488571 s`；r2 finalizer `1844.843103958 s` 未重复计费。

下一步：不重跑本次 Q1/Q2。待审核后，只对 top-side 原响应入口做一次有依据的额外精化对照，范围是既有 12/493 失败项及 666 成功控制；按 packet/manifest 身份选择，不把列号硬编码为正式策略，也不扩散到全部 Q。所需文件与测试保持最小，具体建议见本次交付说明。
