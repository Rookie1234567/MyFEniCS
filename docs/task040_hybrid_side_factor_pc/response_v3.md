# Task040 Response V3：V2-B2 projected transmission 收口

## 结论先行

本轮 V2-A1 producer 与 V2-B2 fresh consumer 都按冻结的
`5 nm / 1° / phi=0 / S / p6h4 / M480 / MPI8` 身份完成了各自的 component formal。
producer 的 packet、canonical owner remap、资源和生命周期证据通过；consumer 的资源、
身份、remap、one-apply implementation subset 和生命周期也通过，但五个非零 source 在
16 步后的 true residual 仍全部 `>=0.9`，没有达到 V2-B2 数值 Gate。最终分类严格为
`THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT`。

这不是资源失败，也不是 checker 或 packet schema 失败。`V2-C` analytic mode-aware、
`V2-D` bounded Level B、`V2-E` bottom/top/both/full 和 `V2-F` h3 scaling 均因该真实
数值负结果 `not_run_by_gate`；没有完整 Hybrid、production qualification 或 0.7 nm
qualification 结论。

## 这条路线在解决什么问题

Projected transmission 想解决的是：完整 side factor 很大，而人工截面上的传递信息可能
只需要以较小的低秩形式传给三个子域。它先在 producer 进程中构造并冻结人工截面响应，写成
每个 MPI owner 的 `U/V/G` packet；consumer 在一个全新的进程中只读取 packet，并按稳定的
canonical key 将行重新分发到自己的 owner，再接入三分区 projected action。这样可以把
“截面数据是否能跨进程、跨 owner 正确复用”和“这个传递近似是否让 Krylov 残差下降”分开
测量。

分成 producer/consumer 是必要的生命周期隔离：producer 可以在 exact oracle 释放后写包，
consumer 不构造 exact-interface oracle，也不读取 exact-output 向量。代价是必须证明
packet 的 provenance、key bijection、row remap、hash 和小矩阵身份；packet 完整也不等于
consumer 数值通过。

## 冻结身份与正式运行

| 项目 | 值 |
|---|---|
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| documentation parent / consumer numerical source | `0919ed2fa3bd1541f543057721fff84fa110f3d4` / `40b25d3281d9ce1707f6069607bfdbbf6a3ab48d` |
| telemetry/checker fix | `0919ed2fa3bd1541f543057721fff84fa110f3d4` |
| producer source / producer checker fix | `942c43881e4162085348c48b09c79fbbdac18cd9` / `bd70ab98009de2a2b45561793be6418a6a9bfcc8` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected / probe / spool SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` / `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` / `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| packet manifest | `19de50f3cdb32766bf6f13fc55c9ac498b21a9a00ddc261768d7d55b7c9da8b0` |
| producer root | `results/task040_v2_interface_packet_producer_mpi8_942c4388` |
| consumer root | `results/task040_v2_projected_packet_consumer_mpi8_40b25d32` |

## 正式数据

### Producer：V2-A1 diagnostic/oracle packet

| 项目 | 值 |
|---|---:|
| exit | natural exit, `rc=0` |
| process-tree peak | `30,823,858,176 B = 28.706954956054688 GiB` |
| process wall | `1202.5501016210765 s` |
| swap / hard stop | `0` / `55 GiB` 未触发 |
| packet | 34 files；`653,804,117 B`；24 owner-row shards |
| Gamma rows / spans | `7560/15120/7560` / `296/776/480` |
| Gram conditions | `187.9352369709664` / `1075856.58741676` / `113913.61949721041` |
| reports | physical/interface/middle-cross/complement `15/8/8/4` |
| lifecycle | exact oracle `3 -> 0`；full/global/nested `0/0/0` |

producer 是 oracle/diagnostic authority，不是 scalable side inverse。它没有运行 PDE、QEP、
FGMRES，也没有产生完整 workflow saving tier。producer 的 `1202.5501016210765 s` 与
consumer 的 wall 属于两个独立进程 component 时间，不能相加。

### Consumer：V2-B2 fresh projected transmission

| 项目 | 值 |
|---|---:|
| exit | natural exit, `rc=0` |
| process-tree peak | `34,846,629,888 B = 32.453453064 GiB` |
| process-sample wall | `1077.3351624270435 s`（raw timeline 最后一行） |
| PSS / USS | `not_recorded_not_available`；不从 RSS 推算 |
| swap / resource | `0`；独立 legacy lifecycle audit resource pass |
| remap global rows | `group0/group1/group2 = 7560/15120/7560` |
| target local rows | `912/1842/930`；source local `1902/1902/0` |
| spans | `296/776/480` |
| one-apply | implementation subset pass；formal/repeat/linearity `6/6/1`；delta `13` |
| factor inventory | same three group factors viewed as ready/projected `3/3`；simultaneous max `3` |
| cleanup | base/projected `0/0`；exact/full/global/nested `0/0/0/0` |
| QEP / PDE / exact-output vectors | `0` / `not_run` / `0 loaded` |

`factor_count_ready=3` 和 `projected_inverse_factor_count=3` 是同一组三个 group factor 的
两种 inventory 视图，不是同时驻留 3+3 个 factor。consumer 没有 numeric allgather，也
没有 global basis replica。

### Canonical remap 与 residual screen

| group | source local | target local | sent / received | roundtrip max |
|---|---:|---:|---:|---:|
| group0 | 1902 | 912 | 1902 / 912 | 0 |
| group1 | 1902 | 1842 | 1902 / 1842 | 0 |
| group2 | 0 | 930 | 0 / 930 | 0 |

one-apply 从 raw `BHB/BHY/YHY` contractions 独立重算的 mandatory rho 为：

| label | original rho | rho* | correlation magnitude |
|---|---:|---:|---:|
| modal+ | 22.245838903738115 | 0.9991091942837925 | 0.04219973812230144 |
| modal- | 23.852050340849885 | 0.999200083877325 | 0.039989903470087636 |
| external | 24.75394731434479 | 0.99926210606036 | 0.03840889730015213 |
| random0 | 22.552067871720634 | 0.9990697662027437 | 0.04312310586675284 |
| random1 | 22.454089855846412 | 0.9990604725869423 | 0.043337883131914334 |

五源 FGMRES 的 true residual：

| label | 0 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|
| modal+ | 1.0 | 0.9969577454690055 | 0.9956464719287812 | 0.9936534709381595 |
| modal- | 1.0 | 0.9985179851860166 | 0.9979287889899702 | 0.9964222027809813 |
| external | 1.0 | 0.9970453221588145 | 0.9957918044671856 | 0.9939467693618661 |
| random0 | 1.0 | 0.9978618914017243 | 0.9973369628027956 | 0.9963350357187821 |
| random1 | 1.0 | 0.9977513488058687 | 0.997255994079295 | 0.9964721803565209 |

五个 `r16` 均 `>=0.9`，所以 conditional 32 没有授权，first preferred checkpoint 为
`null`。这给出唯一数值分类：
`THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT`。它不是“local solve 不准”的证明，
而是当前三分区 projected mode subspace/sweep 没有让冻结五源残差下降到规定范围。

## watchdog teardown 与独立重算

consumer 原始 `watchdog_summary.json` 的 `all_status_readable=false` 和
`swap_authority_readable=false` 只出现在最后一个 cleanup-complete teardown sample；
raw timeline 共 2137 行，前 2136 行仍为可读、swap=0 的运行中 authority sample。原始
summary、timeline、原始 checker 输出均保持不变。

独立 legacy lifecycle audit 使用 timeline artifact hash 绑定，验证：

- `2137 = 2136 + 1`，恰有一个 terminal teardown exclusion；
- 前 2136 行的 process-tree/cgroup 证据可读且 swap=0；
- derived peak 仍为 `34,846,629,888 B`，与 summary 精确匹配；
- run summary hash 与 watchdog 绑定，natural exit/rc0 保持不变。

因此 resource evidence 可通过；这只是 telemetry lifecycle 的狭窄重算，不是改写 raw。
它不能改变 FGMRES 的数值负结果。

## 失败、边界与下一步

第一次 producer checker 失败是 implementation schema bug：真实 physical report 没有
`finite` marker，但显式数值字段和 contractions 全部 finite。独立 checker 修复后
serial/MPI2/MPI4 的 test306 均 `6/6 passed`；这个失败没有被写成 producer 或算法失败。
此前 V1 的三个 implementation-failure root、V1 resource hard stop 和 V2 raw artifact 均
保留，历史结论没有覆盖。

我赞同 V2 的 producer/consumer 分进程设计和独立 Gate：它能把内存生命周期问题与 packet
身份、owner remap、数值传递问题分开审计。本轮不采用用户提出的自由扩展，因为已经触发
Review 定义的真实 numerical Gate；继续 analytic、bounded patch 或参数调节会绕过决策树。
没有调 beta、sign、sweep、ILU 或当前 selected span。

如果未来重新授权，下一轮应优先研究三分区之外的 coarse、long-range 或 nonlocal
transmission mechanism，使人工截面能表达跨截面/多模切向传播；不应只继续调当前 scalar
或 projected span。这个建议是下一轮方向，不是本轮已运行的结果。

## 阶段边界

| 阶段 | 状态 |
|---|---|
| V2-A1 producer | `completed_diagnostic_oracle` |
| V2-B2 consumer | `controlled_numerical_negative` |
| V2-C analytic mode-aware | `not_run_by_gate` |
| V2-D bounded patch Level B | `not_run_by_gate` |
| V2-E bottom/top/both/full | `not_run_by_gate` |
| V2-F h3 scaling | `not_run_by_gate` |
| full Hybrid / production / 0.7 nm | `not_run`；没有资格化证据 |

## 证据入口与 hashes

| artifact | SHA256 |
|---|---|
| consumer watchdog summary | `7e791c7ee18369687f074646ce43c4f24558707b87902440da73568a1c2262eb` |
| consumer process timeline | `302b22e251a3ab61a684905912fca112c10bd99de2981712026ab5acaf1f70b7` |
| consumer memory stage markers | `8012116aaca050d34afde1ef7d88c3d946de618a6d645ce6984d076ea2f61f4c` |
| consumer memory stages | `a9561d36fdd768b0ff3fbd509b179e39d69e42d78e9a8999d978dc3f18c9b01c` |
| consumer worker stdout | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| consumer run summary | `deeb822b1055d133462a3ff35ac8f80e5f8089b4b5f172914bc1f67e999f796f` |
| original consumer checker | `57b6182f89ffd325a0d2ee8148c6f462bde594cbda653f75091c299db5181514` |
| legacy lifecycle checker | `307f611d028807ac1076b73b8d68fdf03f66be5795153ed6161f7b8ccf6c04d1` |
| producer watchdog / timeline | `9821701019fd64392009b28245606112e97224e304c910de7d7b9561fb4ac388` / `1259dd06b07c01566d1c3f725c0792d9b8e99e8b36bec6fccbd27cbed5712c6d` |
| producer run summary / checker after fix | `e427f2e21f3fd55cad09243ca03636976f2e7537381343261754a63ae7d49678` / `3af14190afd9b8e84a2529bf63f2bda348d465d0d47bba166c3682a0b2b32536` |

入口：[consumer compact record](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v2_projected_transmission_consumer_v1.json)、
[consumer outcome](outcomes/projected_transmission_consumer.md)、[V2 review](review_report_v2.md)。

## Task040 全部 reviewed commits

以下列出本 Task040 执行分支从最早的 side-factor 研究入口到当前 documentation parent 的
全部 reviewed commits；V2-G closeout commit SHA 由最终 handoff 报告。

```text
a3623b62b85a9552f077f040e350088e4e8f03a1 docs(task040): define controlled hybrid side-factor PC campaign
37923935d9378bcb10d4f28f859762e7a8711b8f docs(task040): finalize scalable iterative side inverse campaign
30664a6cd6e3f96ebae6e91b54439ffc47161ad6 docs(task040): audit inherited scalable side-inverse baseline
b83bca7f207e529a06fce8e62aaf7e96692ce34b feat(task040): add impedance transmission oracle carrier
74e9684db1ffdbab1835b50d747ff5bb27251c54 test(task040): tighten impedance carrier fixture
e9ea1c8cb4cec1fdf99a7d72c1bead547acbc23b feat(task040): add level-a one-apply audit
c84e4b0f33863afca23eea86693369676a9d53d0 feat(task040): add artificial z trace mass audit
1e3e435efe700adb7ef71c9b3593475b1a01bcc2 feat(task040): add multiplicative overlap transmission carrier
52c88ff3b86e507dba335fc1c7661b207dad3b79 feat(task040): add Level-A bare-F watchdog runner
483275dcdfa65fbc578bbee510878f2d065e2429 fix(task040): launch Level-A worker as module
d58368ba87ab5b8ed4ee424da23724797bd97bac record(task040): close Level-A transmission gate
5abcd30ca3a1e2116a92246b94da35cb73c46c55 docs(task040): add review v1 mode-aware transmission plan
fe93e0165a9bdce3412812e5b0044f54a198c142 docs(task040): bind review v1 to reviewed head
825d90e60a137c05296dc9eef1a7fb2c5ee1d78e docs(task040): audit review v1 transmission extension
41cb0a3079d599cc12a72606bff6d06f347ff5fb feat(task040): add scalar transmission krylov screen
bf029cbdccd50538e91dac3d3452f3a3de62b767 fix(task040): guard scalar phase2 authorization
112ac4913a531ae5c5aab941ac88f005a95b9dc4 record(task040): close v1-1 scalar krylov evidence
bc749ca29ad53986faca7d6b2ef57f3ffe277da3 record(task040): freeze v1-2 interface probes
246720946782756fac3396fb5f8ac29e238132d7 feat(task040): add interface Schur oracle core
ed725b89b466de8dcb1277720de8d29380c9cb72 feat(task040): add distributed Petrov core
59a5133fadb0419fe357ae49b02181a745560c94 feat(task040): build distributed interface bases
b7f5a2f960003c143c24ef0d29472dbf40d0ef33 feat(task040): add fixed projected group inverse
a3585c449f1ae1f9fb439ae905fe727efccb8aa7 feat(task040): wire v1-2 schur and v1-3 screen
618c668d750f228c9eae457c8b69eda5d2cfcfda fix(task040): read resolved per-side mode count
16ecba568be901325e53c3652aa10bb432de5a6b fix(task040): separate spool manifest and catalog identity
6c5e39598aada3c1ffec6affc3cb0977f2575b0e docs(task040): close v1 run b resource evidence
4da67165bdc273060353c122be8db8a372f60111 docs(task040): add review v2 process-split resource plan
20037da9a943139d3e8c2308d20b3cb180026630 docs(task040): audit review v2 inherited resource boundary
25550ef51f2a7c36799c96b4e22bfd9b2cb1b582 feat(task040): add canonical interface Schur packet kernel
f629541bf32412f7985e3bd3babd0becd64bbe54 feat(task040): bridge exact interface factors to canonical packets
942c43881e4162085348c48b09c79fbbdac18cd9 feat(task040): export exact interface packet
bd70ab98009de2a2b45561793be6418a6a9bfcc8 fix(task040): recompute packet report finiteness
810c8f3c95868ac5a5f6bc36948ed61be0d69bc4 docs(task040): record V2 interface packet producer
9cb21934c0f415e1dbafd0c8efcf896006728be3 feat(task040): hydrate projected transmission from packet
3336f9ef64fe3d601f85a17034c7a3027cf69482 feat(task040): consume projected interface packet
7d9657dd2c5cb3c72161d816477a46f4b85567ef test(task040): check projected packet consumer
adc2316fef5eb0c88cb13a3d8981609c6c5df5a5 fix(task040): synchronize packet consumer remap stages
40b25d3281d9ce1707f6069607bfdbbf6a3ab48d fix(task040): redistribute packet rows by canonical owner
0919ed2fa3bd1541f543057721fff84fa110f3d4 fix(task040): audit terminal watchdog teardown
```

## 测试与当前工作树

同一 `0919ed2fa3bd1541f543057721fff84fa110f3d4` 上最后一次代码 focused 命令为
`test_298 + test_307`，结果 `20 passed`；Ruff、format、compileall、diff-check 也通过。
immutable consumer checker 返回 `rc=2`，这是预期的 numerical negative，而非实现失败。
`src/test/test_26_documentation_contract.py` 实际为 `18 passed, 1 failed`；唯一失败是
HEAD `0919ed2fa...` 已存在的 `104_5nm_hybrid_side_factor_pc` case 目录未列入
numbered-case whitelist。这是 pre-existing baseline contract gap，不是本轮 Markdown/JSON
内容或 V2 数值 Gate 失败；本轮按窄范围不修改测试架构。本轮 JSON/Markdown/benchmark
no-write 检查已在 qualified activation 下通过。当前表列至 documentation parent
`0919ed2fa...`；本轮 evidence/docs 随 V2-G closeout commit 提交，未改 raw/results。
