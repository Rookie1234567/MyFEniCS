# Task040 Review V6-0：factor-stage forensic

状态：`V6-0 forensic_completed_read_only`

分类：`FORENSIC_TRUE_FACTOR_STALL`

本记录只回答一个窄问题：把显式稀疏矩阵变成可重复调用的直接解算对象时，V5-2 是否把几乎整个授权时间耗在 factor 阶段。它不把旧 Task039 的 side-response 数值当成当前 bare-`F` 的数值证明，也没有启动新的 PDE、factor rescue 或 V6-2。

## 1. 比较对象与身份

| 项目 | Task039 V10 response producer | Task040 V5-2 fresh bare-`F` producer |
|---|---|---|
| producer source SHA | `dbc5e9bfdf9ad0520881caa168c7a27316d50f10` | `fd7bea41d7d7b7869dd3ade4407129b00900ef7d` |
| formal root | `results/task039_v10_h4_side_response_packet_full_producer_mpi8_dbc5e9bf` | `results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41` |
| MPI | raw manifest `8` | raw watchdog/provenance `8` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` | 同一值，由 V5 provenance 交叉核对 |
| physical-model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` | 同一值，由 V5 provenance 交叉核对 |
| resolved-config SHA256 | `f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883` | 同一值，由 V5 provenance 交叉核对 |
| 本次执行分支快照 | `860141710514ee46bcaaccaaf21155f2308faa5d`，clean，upstream 同 SHA | 仅作为审计执行快照，不冒充两个 producer 的 source SHA |

V5 operator audit 的实际文件 SHA 是
`d9c68f1586cb4e37bb3648b87cd125f603401087671de883f5715427bd2589b6`；其内部 `record_sha256` 是内容字段，不当作文件 SHA。V10 diagnostic 的实际文件 SHA 是
`184ae4bd2d4c5721131d1b735c07ee745c18df1b2cdce87fcb4b4c9d1d527830`。

共享实现的 Git blob 身份如下；两 source commit 对这些文件的 blob 相同：

| 文件 | 两个 source commit 的 Git blob SHA |
|---|---|
| `src/solvers/hybrid_local_dtn_woodbury.py` | `050bd24ec02c02180f4b9a91b8fb97e29a4b92d5` |
| `src/solvers/static_local_schur_action.py` | `d21c71d378951708404861b58cd219631e9ff687` |
| `src/solvers/hybrid_local_dtn_action.py` | `fe944de30b1658b8c0a38bfe958a150febd127f9` |
| `benchmarks/task039_v3_side_oracle.py` | `4fbde55eb76bfd83774eba21e069ad358b62dc46` |

`benchmarks/task039_v3_7_orchestration.py` 在两个 source commit 间有其他历史改动，因此这里没有把整个 orchestration 文件宣称为相同；factor 核心的 materializer 和 `ResearchExactFactorInverse` 则由上表及下面的 source call-site 审计绑定。

## 2. 原始文件与 SHA256

以下 hash 是实际读取的 raw 文件字节 SHA256。`.npy` 没有被本次 forensic 打开或读取。

| root | raw 文件 | SHA256 |
|---|---|---|
| V5-2 | `watchdog_summary.json` | `1633989020c904db5949abf627ed537d48b6da11e826d3fbf5628cae4d499d07` |
| V5-2 | `memory_stage_markers.raw.jsonl` | `c6ca72b37f767d40e425e77833034d740ce641d50deead1e58c8989b2eb02d7d` |
| V5-2 | `memory_stages.jsonl` | `1447e1ff13de5a086dfd2edb4e50d67966c175e60f34f2d5ebc22875716ca6fa` |
| V5-2 | `process_tree_samples.jsonl` | `4894aaa5e16d4463703c1e7cd1f22677f9c56e2af3e05b32a651d98338279243` |
| V5-2 | `worker/bare_f_authority/operator_semantics_audit.json` | `d9c68f1586cb4e37bb3648b87cd125f603401087671de883f5715427bd2589b6` |
| V5-2 | `worker_stdout.txt`（空文件） | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| V10 | `run_manifest.json` | `c1f9bb4aee64766e2e1fc71554430617bdd04936242811155516347dab09a4cf` |
| V10 | `run_summary.json` | `839ca1c9f59807b981dcc14096080bfe9edc8610b7110c20b87146f9cc7d81d3` |
| V10 | `numerical_output/v3_v7_diagnostic.json` | `184ae4bd2d4c5721131d1b735c07ee745c18df1b2cdce87fcb4b4c9d1d527830` |
| V10 | `numerical_output/memory_object_ledger.json` | `4827042564cf22b7ac41a7094e6be825800adfb087d49b958553a502fd4742aa` |
| V10 | `numerical_output/memory_stage_markers.raw.jsonl` | `5a7ddcc74953155ac3141c1e2db3326776574ef299501ed652bedb92d712a48a` |
| V10 | `numerical_output/memory_stages.jsonl` | `d83dafde09825230336e5a8924cf251460bb999de6f7c2de582d9bba8e9353da` |
| V10 | `numerical_output/process_tree_samples.jsonl` | `be7da1e04b2f39c75094632f73552c798ae788620447e86c1f5b3ec9e37f1988` |
| V10 | `worker_stdout.txt` | `c057e9432a31967b227d8827aebe609f47869e14c23224d991480812db3a9dff` |

V10 的 raw manifest 还把实际 input、resolved config 与 physical-model 文件绑定到上表中的三个内容 hash。V5 watchdog 的 `command` 同样指向官方 input、冻结 spool 和自己的 source SHA；V5 没有成功写出 `run_summary.json`。

## 3. Factor 阶段原始时间线

### 3.1 V5-2

V5 有两个必须分开的时间原点。`construction_begin` 是
`2026-08-25T21:24:07.454801Z`；`v5_bare_f_factor_setup_begin` 是
`2026-08-25T21:40:19.585536Z`，所以 marker 相对 construction 的时间是
`972.130735 s`。watchdog 的第一条 `process_start` 是
`2026-08-25T21:24:00.837527Z`，同一个 factor marker 相对 process start 的总 wall 是
`978.748009 s`。下面的 marker elapsed 仍明确采用 construction 原点：

| marker | elapsed (s) | 原始 detail 中的事实 |
|---|---:|---|
| `construction_begin` | `0.000000000000` | bottom current bare-`F` route 开始 |
| `v5_bare_f_system_ready` | `450.547994000000` | `bare_f_rows=132300`，`C/D/H=0`，QEP `0` |
| `v5_one_cell_source_factor_ready` | `791.734126000000` | source factor construction `1`，active `1`，peak simultaneous `1` |
| `v5_one_cell_source_factor_apply` | `836.087321000000` | apply `1`，MUMPS solve call `1`，source columns `2` |
| `v5_one_cell_source_factor_apply` | `836.704672000000` | apply `2`，MUMPS solve call `2`，source columns `4` |
| `v5_one_cell_source_factor_destroyed` | `840.381328000000` | factor count `0`，destroyed `true`，matrix alive `false` |
| `v5_one_cell_source_cleanup_complete` | `842.943107000000` | cleanup complete，bare-F factor 尚未建立 |
| first `v5_bare_f_rhs_ready` | `863.731244000000` | 五个 RHS 顺序中的第一个 |
| last `v5_bare_f_rhs_ready` | `972.125950000000` | 五个 RHS 已生成；仍未有 exact output |
| `v5_bare_f_factor_setup_begin` | `972.130735000000` | `explicit_current_bare_F`；factor count `0`；这是最后一个 marker |

因此：

* factor 前总时间为 `972.130735 s`；
* source-factor ready 到 source cleanup 为 `51.208981 s`；cleanup 到第一个 RHS marker 为 `20.788137 s`；五个 RHS marker span 为 `108.394706 s`；这些区间不包含未被 marker 单独拆出的 assembly 子阶段；
* watchdog 最后一条 authority sample 的 UTC 是
  `2026-08-26T03:24:01.295946Z`，因此用同一 UTC 时间轴得到 factor-stage 观测下界
  `03:24:01.295946 - 21:40:19.585536 = 20621.710410 s`；
* 末样本的 watchdog perf-counter elapsed 是 `21600.381713289993 s`。用它减去
  `978.748009 s` 得到的 `20621.633704 s` 混合了两个时钟，只能作近似，不能替代上面的 UTC 主值；同理
  `21600 - 972.130735 = 20627.869265 s` 只是不同原点下的预算余量，不是精确 total-wall factor duration；
* marker 原点下的 factor 前段是 `972.130735 s`，占 configured `21600 s` 的
  `4.500605254630%`；按同一 UTC 时间轴的 factor 下界占 configured wall 至少
  `95.470881527778%`。两个百分比使用不同原始时钟口径，不能相加为一个精确分解；
* watchdog raw 为 `return_code=1`、`termination_reason=wall_timeout`、`run_summary_present=false`，没有 `v5_bare_f_factor_ready`，不能把 OS 进程终止写成 factor `1→0`。

V5 进程树 raw 有 `39341` 行；最大 RSS 为 `45432283136 B = 42.312110900879 GiB`，最大 swap 为 `0 B`。configured preferred/warning/hard 分别为 `59055800320 B`、`62277025792 B`、`68719476736 B`（55/58/64 GiB），raw 没有越过 hard line。因此这是 wall/resource window exhaustion during factor construction，而不是 64 GiB hard-stop 或 numerical residual failure。

### 3.2 Task039 V10

V10 marker elapsed 以其 producer 进程时钟为准：

| marker/raw field | elapsed 或 wall (s) | 事实 |
|---|---:|---|
| `setup_begin` | `0.0317509489832446` | setup 起点 marker |
| `v10_side_response_packet_full_producer_factor_ready` | `2967.286635097` | underlying exact-side factor ready `1` |
| marker interval `setup_begin → factor_ready` | `2967.254884148017` | factor-specific setup interval 的可观测上界口径 |
| first `modal_response` begin | `2971.3388379670214` | factor ready 后 `4.052202870022` s |
| diagnostic `measured_full_packet_setup_wall_seconds` | `2971.3064760629786` | producer report 的 setup wall |
| diagnostic `measured_full_packet_total_wall_seconds` | `4390.176657371572` | producer report 的 total wall |
| `packet_written` marker | `4524.082296481007` | launcher marker elapsed |
| `full_producer_cleanup` marker | `4524.467549795052` | factor after cleanup `0` |

`diagnostic` 的 producer wall 字段与 marker elapsed 使用的起止/采样口径不同；本记录保留两者，不把 `4524.467549795052` 静默改写成 report 的 `4390.176657371572`，也不反向用 report 字段伪造 marker 时间。用 marker 的 setup→ready interval 与 V5 factor 下界比较得到：

```text
20621.710410 / 2967.254884148017 = 6.949760372851
```

这只说明 V5 的未完成 factor 阶段显著更慢；它本身不是配置回归证明。

## 4. 矩阵、ownership 与 operator 语义

| 项目 | V5-2 raw | V10 raw/source | 结论 |
|---|---|---|---|
| global rows | marker `bare_f_rows=132300`；canonical/layout/vector metadata `global_size=132300` | packet `global_rows=132300` | 全局行数一致 |
| MPI layout | 8 ranks；current-`F` ranges `[0,17118]`, `[17118,33948]`, `[33948,49428]`, `[49428,66618]`, `[66618,82380]`, `[82380,100068]`, `[100068,116634]`, `[116634,132300]` | 8 ranks；response shard ranges `[0,16260]`, `[16260,32388]`, `[32388,49434]`, `[49434,67272]`, `[67272,82440]`, `[82440,99606]`, `[99606,116844]`, `[116844,132300]` | global size 相同但 rank ownership 不同；不能比较 rank-local 时间/数组位置 |
| source-level Mat constructor | `materialize_research_explicit_fine_matrix(condensed)` | 同一 materializer；Git blob `d21c71d378951708404861b58cd219631e9ff687` | source-level 都走显式 AIJ materializer |
| runtime Mat type | raw 未写 `Mat.getType()` | raw 未写 `Mat.getType()` | unavailable；不把 source constructor 当 runtime readback |
| NNZ | raw 未写 global/local NNZ | raw 未写 NNZ | unavailable |
| block size | raw 未写 `Mat.getBlockSize()` | raw 未写 block size | unavailable |
| matrix hash | V5 marker 记录 `operator_hash=a672183780b34a0f39739458a68f952a631316248955926fed697fb8d619ac5e`；没有 V10 对应 hash | 未提供 matrix hash | 不能由 raw 建立跨 root 数值矩阵 equality |

作为同冻结配置的**继承 compact evidence**，`task039_v9_bare_f_full_side_diagnostic_v1.json` 记录了
`F=132300×132300`、`NNZ=105038640`、`type=mpiaij`。这不是 V5-2 或 V10 root 的
runtime `Mat.getType()`/NNZ readback，不能用它补造本次 run-specific equality；两 root 的 block size
仍为 `unavailable`。

V5 operator audit 将 current route 写成 `explicit_current_bare_F`，`C/D/H=0`、`physical_dtn_operator=false`、QEP `0`，并使用 `ResearchExactFactorInverse(F)`。V10 的 `ResearchExactSideLuAction` 也把同一个显式 `F` 传给同一 `ResearchExactFactorInverse`；该类在两个 source commit 的 blob 都是
`050bd24ec02c02180f4b9a91b8fb97e29a4b92d5`。因此就“被 factor 的显式 F”这一 stage 而言，没有 raw/source 证据显示换了另一种矩阵构造。

但两条 route 的完整 consumer 不是同一数学算子：V10 manifest 的 preconditioner 是
`hybrid_block_ldu_exact_side_lu_dtn_woodbury`，V10 diagnostic 记录 `C/D/H` 组件和 Woodbury-associated side action；V5 明确禁止并未构造 C/D/H/Woodbury，只做 bare-`F`。所以 V10 的 response packet 不能当作 V5 bare-`F` solution 或 residual 的等价证据。本分类仅针对底层显式 F factor-stage；end-to-end operator equality 仍是 `not_established`。

## 5. MUMPS/PETSc 选项和内部阶段

| 检查项 | V5-2 | V10 | 结论 |
|---|---|---|---|
| factor solver | raw/source `factor_solver_type="mumps"` | 同一 `ResearchExactFactorInverse`，V10 factor ready marker | 两者一致 |
| factor-only storage | V5 call `factor_only_storage=True` | V10 call `factor_only_storage=True` | 两者一致 |
| explicit ordering | raw 无；相关 source 无 active call | raw 无；相关 source 无 active call | unavailable |
| ICNTL/CNTL | V5 没有 profile/readback 字段 | V10 `profile_ready.mumps_blr_profile=null`；raw 无 ICNTL/CNTL；worker stdout 无 `ICNTL`/`CNTL` | 没有可证明的 active explicit setting或readback |
| PETSc `setFromOptions` | relevant source 无调用；raw 无 | relevant source 无调用；raw 无 | unavailable/default resolution not measured |
| OOC/BLR | V5 route 未记录 profile | V10 profile 明确为 `null`；raw 无 OOC/BLR readback | 不得声称启用了或关闭了某个具体 MUMPS 模式 |
| memory relaxation | raw/source 未提供因子内部 relaxation readback | raw/source 未提供 | unavailable；watchdog hard line 不是 MUMPS relaxation |
| symbolic/numeric split | 只有 `v5_bare_f_factor_setup_begin`，没有 ready | 只有 setup→factor_ready，未分 symbolic/numeric | unavailable |
| INFOG/RINFOG | V5 stdout 为空，marker 无字段 | V10 stdout SHA 对应文件中无 `INFOG`/`RINFOG`，marker 无字段 | unavailable；没有进度读数 |

共享 factor class 的 source 只在 `compressed_factor_profile` 非空时调用 BLR-specific `setMumpsIcntl`/`setMumpsCntl`；V10 raw profile 为 `null`，V5 bare-`F` call 也没有传 profile。这个检查排除了一个可具体修复的 ordering/ICNTL/CNTL/BLR 配置回归，但不提供底层 MUMPS 默认值的 readback。

## 6. Resource 与决策

V5 watchdog 的原始 resource facts 是：RSS peak `45432283136 B`、swap `0 B`、all process-tree status readable、wall timeout `21600 s`、hard `64 GiB` 未越过。V10 run summary 的 process-tree peak 是 `54497624064 B = 50.754867553711 GiB`、swap `0 B`；V10 使用的 effective terminate policy 是 `60 GiB`。这是两个 launcher 的资源合同差异，不是已找到的 factor algorithm/config regression，且 V5 peak 低于自己的 hard line。

按 Review V6 §7.3：

* `FORENSIC_CLEAR_REPAIR_OR_PREFACTOR_OVERHEAD`：否。V5 factor 前只有 `972.130735 s`，占授权窗口 `4.500605%`，没有发现具体可修复的配置差异。
* `FORENSIC_IDENTITY_MISMATCH`：不作为 factor-stage 分类。两边底层 explicit-`F` materializer/factor class/source call 一致；但 V10 的外层 Woodbury side operator 与 V5 bare-`F` consumer 不等价，故旧 response packet 只保留为历史 side-action evidence，不能冒充 bare-`F` 数值基线。
* `FORENSIC_TRUE_FACTOR_STALL`：是。V5 factor-stage 按同一 UTC 时间轴已持续至少
  `20621.710410 s`，占 configured wall 至少 `95.470881527778%`，而共享 factor code 和可见选项没有配置回归；V10 同一底层 factor path 已在约 `2967.255 s` 到 ready。

因此满足“不是 factor 前开销主导、也没有明确配置回归”的条件：**是**。依最新执行裁决，V6-1 唯一 factor-only rescue 不应因这次 timing 差异再次启动；下一架构步骤是 V6-2 full-interface Schur/action，但本 V6-0 记录没有启动它，也没有生成新的 heavy root。所有 symbolic/numeric、NNZ/Mat type/block、INFOG/RINFOG 和跨 root numeric matrix equality 的缺口保持 `not_available/not_established`。

## 7. 证据边界

这份 forensic 证明的是一次 factor-stage 的时间/阶段分类，不证明：

* V5 未完成 factor 的数值不正确或正确；
* V10 side-response packet 与 current bare-`F` solution 等价；
* 旧 776-span Route C、trace/lift、full-interface V6-2 或 production solver 已通过；
* 0.7 nm/2 TB feasibility。

V5-2 raw root 与 V10 raw root 均保持原样；没有修改、重跑或删除任何 raw artifact。
