# Task041 BAL_H transfer：H4 中心结果报告

## 终态先行

本轮把 BAL_H 当作一个明确 opt-in 的研究候选来验证。它把两侧原本需要保存的完整 p6 精确侧区逆，换成“每侧一个准确的 p4 粗因子 + 平衡修正的迭代响应”；全局 Maxwell 方程、全局矩阵和右端项没有改变。这样做的主要目标是降低侧区精确因子的驻留内存，代价是每个侧区响应需要多次迭代求解，因而可能明显变慢。

四个 Task041 正式 case 的数值/物理核对均通过冻结比较合同：13.5 nm 的 exact 与 BAL_H、5 nm 的 exact 与 BAL_H worker 输出在 residual、R/T/A、场、canonical owner-shard、衍射通道和 flux 上均通过。5 nm BAL_H 的 worker 结果已完成，但 public supervisor 父进程在 `2026-09-13T03:06:53.264Z` 附近丢失，约早于 `2026-09-14T13:10Z` 结果落盘 34 小时，导致完整 consumer 资源和正常公共退出证据不完整；结果落盘后另有独立 orphan sampler 的退出竞态。因此最终状态不是“全流程资源通过”，而是：

> **`RESOURCE_COMPARISON_INCONCLUSIVE`**：数值复现通过；5 nm BAL_H 的完整 consumer 内存/退出口径及共同 producer 的完整包络没有被证明。

H3 comparator 原始分类 `TASK041_SIDE_BALH_NUMERICAL_OR_RESOURCE_FAIL`、exit code 1 和资源 false 原样保留；它不是数值失败。`full3d_secondary` 没有运行，也没有把 H3e 的旧 `SETUP_COST_BLOCKED` 改写成通过。

## BAL_H 做了什么

exact 路径在 bottom/top 两侧各建立一个完整 p6 精确因子。BAL_H 路径只建立各侧一个准确 p4 因子，并在固定的 `inner=128, rtol=1e-2`、right FGMRES/restart 32 下，用平衡的侧区响应构成 modal Schur 预条件矩阵；外层仍是 right FGMRES/restart 32、`max_it=2048`、true residual `5e-9`、zero start。p6/global direct factor 在 BAL_H 中为 0，原全局 action/RHS、P/PH 传递和正式 recovery 不被替换。

收益目标是减少精确 p6 因子的内存驻留；代价是 p4 回代、Q/H6/A6 作用和大量 Schur 列响应，5 nm 实测因此远慢于 exact。BAL_H 仍是 `research_only_approximate_candidate`，没有提升为普通 profile 或 production default。

## 冻结比较合同

比较器从两边 raw payload 独立重算，不相信记录中的 `status/pass`：

- 五个 reported/global/bottom/top/modal explicit residual 均须 `<=5e-9`；projection、双侧 traction 均须 `<=1e-8`，external-q identity 须 `<=1e-10`。
- `R/T/A_balance/A_volume` 的两边绝对差均须 `<=1e-8`；各自 `abs(A_balance-A_volume)` 与 `abs(R+T+A_volume-1)` 均须 `<=1e-5`。
- 选定平面的 E/H 用相同 key 的 L2 差，分母 `max(norm(candidate), norm(exact), 1e-30)`，相对上限 `1e-6`；同时记录绝对 L2、max abs 和单位 E=`V/m`、H=`A/m`，不做 phase fit。
- bottom/top 的 `active_trace`、`full_fe` 四个 canonical owner-shard 使用分母 `max(norm(exact), numpy.finfo(float).tiny)`，相对上限 `1e-5`；本次四个 role 实测均为 8/8 非空，count、unique key 和 manifest 一致。这是本次输出事实，不把“所有 rank 必须非空”新增为一般冻结合同。
- 每个 external channel 都保留两边 raw power、complex amplitude、绝对/相对差和 significant 标记。两边 power 的显著并集是 `>=1e-8` 时，power 与 amplitude 相对上限为 `1e-6`，分母分别使用两边 power 或 amplitude 绝对值与 `1e-30` 的最大值；弱通道仍保留为诊断。
- normal flux 使用 `0.5 Re((E cross conj(H))_z)`，按 plane 汇总，分母 `max(norm(candidate), norm(exact), 1e-30)`，相对上限 `1e-4`。

完整 80/600 channel 行以及 canonical 比较指标、manifest 和 hash 均在 compact record 中保留；实际 32 个 canonical 系数 shard 位于 ignored artifact，不塞入 compact。本报告只列最大值，弱通道的较大相对比值不被误读为 gate 失败。

## 四个正式运行

残差顺序统一为 `reported / global / bottom / modal / top`。表中的“保留因子的侧区 rows”只指实际 factor/solve 所保留的侧区矩阵：exact 为 p6 侧区矩阵，BAL_H 为 p4 粗矩阵；它不是全局 FE DoF。全局解向量 size 有实测值（H2 为 `17088`、H3 为 `265560`），canonical packet count 不冒充 DoF。

| case / method | source | p / h / M / MPI | 五个 true residual | R / T / A_balance / A_volume | 保留因子的侧区 rows；global solution size；factor NNZ；因子 | wall / 资源口径 |
|---|---|---|---|---|---|---|
| 13.5 nm exact | `cda7cc8a785c38352c840e6ec2737c08215e7ed7` | p6 / 10 nm / 120 / 8 | `2.208866e-10 / 2.208919e-10 / 1.146400e-11 / 2.804317e-11 / 1.804746e-10` | `0.3656257890942662 / 0.0129906324092463 / 0.6213835784964875 / 0.6213835795011106` | p6 bottom/top `8424/8424`；global `17088`；各 `25,014,456`；p6 `2→0`、p4 `0`、global `0`；modal rank240 | consumer `390.969799208 s`；phase-sum `417.654257394 s`；public `418.095771106 s`；H2 exact public-tree资源已通过 |
| 13.5 nm BAL_H | `49604fd4f7907082642430a12c0bf9de35c58df2` | p6 / 10 nm / 120 / 8 | `2.040522e-11 / 2.040566e-11 / 4.775839e-11 / 6.598210e-13 / 1.498479e-11` | `0.3656257890944596 / 0.0129906324091379 / 0.6213835784964025 / 0.6213835794980666` | p4 bottom/top `8148/8148`；global `17088`；`6,654,800 / 6,022,672`；p4 `2→0`、p6 `0`、nested KSP `2→0`；modal rank240 | consumer/phase `3002.409810985 s`；derived common workflow `3029.094269171 s`；consumer资源通过 |
| 5 nm exact | `db07f1cfb34f0135f636fa96a0a37b29a3a2969b` | p6 / 4 nm / 480 / 8 | `3.568638e-10 / 3.568818e-10 / 5.802525e-12 / 1.389692e-10 / 3.299218e-10` | `0.7331842733882057 / 0.0002200986957320 / 0.2665956279160623 / 0.2665962726235869` | p6 bottom/top `132300/132300`；global `265560`；`1,071,375,336 / 940,902,624`；p6 `2→0`、p4 `0`、global `0`；modal rank960 | consumer `1868.459373641 s`；public `1869.968719222 s`；完整 public tree RSS/PSS/USS=`89,123,696,640 / 87,368,944,640 / 87,121,264,640 B` |
| 5 nm BAL_H | `51694bbc49d90e70eef87c953f07c695f5fc519c` | p6 / 4 nm / 480 / 8 | `4.779230e-11 / 4.779531e-11 / 6.242900e-11 / 6.709147e-13 / 4.427971e-11`（projection 另为 `6.709329e-13`） | `0.7331842733881465 / 0.0002200986957280 / 0.2665956279161255 / 0.2665962726220402` | p4 bottom/top `128952/128960`；global `265560`；`276,913,408 / 298,181,960`；p4 `2→0`、p6 `0`、global `0`、nested KSP `2→0`；modal rank960 | worker consumer `191662.819902868 s`；Schur `183016.742110029 s`、outer `5486.829851053 s`、recovery约`49.39 s`；public parent/summary缺失，资源口径不完整 |

四个运行均为 `outer reason=2`、right FGMRES/restart32/zero start；H2 candidate 5 次外层迭代，H3 candidate 5 次，exact 两个 case 各 1 次。H3 candidate 的 worker full residual 和 physics own gates 已通过，但不能把 worker 成功替换为完整 public supervisor 的退出与资源通过。

### 对照误差

| 对照 | selected E/H（rel L2；abs L2；max abs） | 四 canonical role 最大/逐项（rel；abs L2；max abs） | external / flux |
|---|---|---|---|
| H2 13.5 nm BAL_H vs exact | E `3.554585e-12; 9.020021e-11; 2.572666e-12`；H `3.555244e-12; 2.396006e-13; 5.960546e-15` | rel 最大 `1.019836e-11`；abs 最大 `1.255163e-9`；max abs 最大 `5.342232e-11`；四 role 均 8/8 非空 | 80 channels，12 个 significant；significant amplitude rel 最大 `3.247850e-9`、power rel 最大 `4.796998e-9`；flux rel `4.156801e-12`、abs `5.422286e-17` |
| H3 5 nm BAL_H vs exact | E `2.297500e-11; 1.319897e-10; 5.150522e-12`；H `2.289344e-11; 3.499239e-13; 1.393209e-14` | rel 最大 `3.991963e-10`；abs 最大 `3.470803e-9`；max abs 最大 `6.834821e-11`；四 role 均 8/8 非空 | 600 channels，26 个 significant；significant amplitude rel 最大 `4.740652e-9`、power rel 最大 `9.243100e-9`；flux rel `5.876460e-12`、abs `6.984379e-18` |

弱通道的全行最大 amplitude relative 为 H2 `1.579521`、H3 `1.914900`，power relative 为 H2 `0.999888`、H3 `0.999994`；这些行的 significant 为 false，因此只是保留的弱级诊断，不改变比较 pass。

## 资源、生命周期和耗时

### H2 已完成对照

13.5 nm H2 的 consumer RSS 为 BAL_H `9,159,106,560 B`、exact `9,414,000,640 B`，差 `254,894,080 B`，约 `2.707606%`；对应 PSS 为 `6,652,803,072 / 6,681,214,976 B`，USS 为 `6,280,171,520 / 6,450,995,200 B`。这是同一轮已测 consumer 的描述性差值，不是单独的性能结论；BAL_H consumer 约比 exact 慢 `7.68×`。H2 的共同 producer peak 为 `2,722,349,056 B`，PSS/USS 未测但 producer binding 合格。H2 通过 numerical、consumer resource 和 comparison contract；没有把这一差值升级为跨模型的可信节省规律。

### H3 5 nm 资源分段

5 nm exact 的完整 public parent+descendant 同步峰为 RSS/PSS/USS=`89,123,696,640 / 87,368,944,640 / 87,121,264,640 B`，swap=0，source 为 `db07f1...`。

BAL_H candidate 的旧 public 段和 orphan 接管段必须分开：

| 段 | 原始文件与 hash | 样本/时间 | RSS peak | PSS/USS peak | 语义 |
|---|---|---:|---:|---:|---|
| public candidate（synthetic label；raw 无 `record_type`） | `/home/fenics/Projects/MyFEniCS/results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260912T075551.700563Z/numerical_output/log/memory_stages.jsonl`；`a2fc18414dd6430051ade364a2e1ed870bc4c603a753dd9084c7f30c66648776` | `226484`（preflight `1` + consumer `226483`）；raw last elapsed `69062.26180143608` | `53221163008 B`（RSS pid-sum mismatch `0`） | PSS/USS `50485623808 / 50090246144 B`；同时可读 `2287`、缺测 `224196` | 旧 public 段；min MemAvailable `2023682953216 B`，job swap `0`，global baseline `8192 B`、global used/pswpin/pswpout delta `0`；父覆盖和完整 workflow 未建立 |
| orphan `sample` | 同一个 `orphan_resource_samples.jsonl`；`eda1271c...` | `822`；`05:18:23.703741Z–05:24:08.552793Z` | `53131128832 B` | `50439184384 / 50044362752 B` | 8 次 smaps complete |
| orphan `orphan_sample_read_only` | 同上 | `6284`；`05:33:39.298781Z–06:00:12.614440Z` | `53131554816 B` | `50439526400 / 50044788736 B` | 53 次 smaps complete |
| orphan `orphan_sample_gate_v2` | 同上 | `442921`；`05:57:27.696982Z–2026-09-14T13:10:17.127459Z` | `53162483712 B` | `50472495104 / 50075267072 B` | 3725/3725 smaps complete，442920 healthy、末条1 false |

`orphan_resource_samples.jsonl` 整文件大小 `2024225287 B`，SHA256=`eda1271c5eec3e90eb4b5d69b6d376c65355067c81a29038022f539713c59b7c`。三个 orphan 段不是三个文件；它们按 `record_type` 在这一文件中连续审计。`05:18:23.054949Z` 与 `05:33:38.628629Z` 是 header/恢复边界，不是首 sample；实际首 sample 分别是表中时间。新旧 sampler handoff 有重叠，`05:24:08.552793Z` 到 `05:33:39.298781Z` 是此前恢复间隔，不能和 handoff 重叠写成同一个 gap。

末条 gate-v2 的 rank RSS 已为 0/不可读，root RSS 为 `16203776 B`；job swap 为 `0`，global used 的既有 baseline 为 `8192 B`，新增 used/pswpin/pswpout delta 仍为 `0`，hard memory 未触发、reserve 仍 pass，但 sampler gate 本身为 false。随后实际对全部 9 个专属组发送 TERM，并对 rank0 组发送 KILL，最终无残留；这不是“没有 signal”，也不是已证明的正常 MPI 自然退出。worker 的 marker/summary 说明结果已先落盘并完成内部 cleanup，但 public parent 丢失、最终公共 exit 未验证。

H3 candidate 的 worker 内部 `rss_drop` 是局部 worker 口径：`9698107392 / 8065409024 B`（`9.032066345 / 7.511497498 GiB`），不能当 MPI 全树释放。历史 5 nm producer 只有 worker-tree RSS=`10039554048 B`、wall=`11447.68326334795 s`，public parent 未覆盖，PSS/USS 和完整共同 workflow peak 均 `None/unqualified`；不能拿它和 candidate 组装一个完整内存包络。

### 退出竞态和证据边界

- public parent/outer wrapper 缺失，`run_summary.status=launching`、`exit_status=null`；H3 candidate worker 的数值结果、authority、canonical 和 checkpoint 仍保留。
- 最后一条完整健康样本的 raw 内嵌 UTC 是 `2026-09-14T13:10:16.878597Z`；`authority` mtime `2026-09-14T13:10:15.998426Z`、`final_cleanup` marker mtime `13:10:16.500450Z`、`consumer_summary` mtime `13:10:16.534870Z` 是文件元数据时间，不是样本内嵌 UTC。
- orphan supervision notification 在 `13:10:23.068460Z` 因主控状态 `notLoaded` 失败；后续手工通知才送达。固定 PID sampler 是 research incident、`do-not-merge`、`not qualified for reuse`。
- 初始 gap 由旧 public last elapsed `69062.26180143608`、memory 文件 mtime `2026-09-13T03:06:54.042809Z`、executor failure event `03:06:53.264Z` 到独立 header `05:18:23.054949Z`/首 sample `05:18:23.703741Z`界定；没有插值，也不把 mtime 当样本时间。

### wall 和账本

H3 exact consumer 为 `1868.4593736410607 s`，public supervisor wall 为 `1869.9687192218844 s`。H3 BAL_H worker consumer 为 `191662.819902868 s = 53.2397 h`，candidate/exact consumer wall 比约 `102.578×`；其中 Schur `183016.74211002886 s`、outer `5486.829851052957 s`、recovery 约 `49.39 s`。这些 phase 是嵌套 marker，不相加为多个 job；也不把各 rank 或父子 wall相加。

H3 candidate 的 RHS/Schur 成本原始索引为 `/home/fenics/Projects/MyFEniCS/results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260912T075551.700563Z/consumer/numerical_output/balh_side_rhs_audits.jsonl`，3852327 B，SHA256=`b84de36f3eacd82eab6ff8fad03c689bb49476efb153e7c4096fcdf61b3fc51b`。共 1980 行：cost `8`、modal `1952`（每侧976，含32 sample、1920 formal）、outer `20`（每侧10）。其中 1978 行 `KSP_CONVERGED` reason2、2 行 `ZERO_RHS_EXACT`；inner iterations 合计 `30295`，单 RHS 最大 `112`，最大 explicit inner residual `0.009989594141011119`。逐行 `counts.delta` 合计为 `pc/H6/J/JH=30295`、`A6/P/Q/PH_audit/p4_backsolve=60590`、`PH_total=121180`、`p4_refinement=0`、`side_A=32333`、`checkpoint=183748`；这些是调用次数，不是可相加的 wall。

账本 `/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/task041_compute_wall_ledger.json` 的当前 measured record sum/used scope 为 `203701.83937335422 s`，明确只覆盖已写入的 measured records（含 H3f-C candidate 与 H3h comparator），不是所有未记录等待或解释器间隔的完整批次墙钟。初始 `6000 s` 仍是带 `2008.69 s` 缺失/启动余量的 `derived_conservative_allowance`，不是实测值或数学上界；记录的 measured sum 已超过名义 `172800 s`，H3f-C 的单 candidate 用户授权明确关闭 time-stop，但没有关闭内存、swap、身份或数值 Gate。

## 身份和 artifact

两边的 consumer source、input、resolved、physical identity 分开绑定；H3 legacy packet 只读复用，未改写 Task039 identity。BAL_H 迁移所依据的 Task39extra V5 donor 为 source `094204b7281fe867744fe334e8753d2faebaf89b`，原始 solve source `2bb6770ad00b35881558c576e7296e250656e571`，其审核/结果证据 source `4cbfadc4880c20aea775142168e6dd4e71870fda`；这些是迁移来源，不是本轮正式运行 source。关键证据如下：

| artifact | SHA/事实 |
|---|---|
| H3 legacy descriptor | `175a2463e15e039ff4dec91eed6a1f011d8eca338e1d2cc98cd8e30e37d86c86` |
| H3 selected packet manifest | `306939dda3b70777204c11fbd65beac2db5dc0637bc9b6803f7794d0d7cbad2f` |
| external 600-key identity | `ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a` |
| H3 candidate E/H payload | `411476 B`，`0ca46791e2071db5a9c316005e71be9115ce33e3812f28ffa3837c1511647b16` |
| H3 candidate canonical | 4 manifests + 32 shards，`656803275 B`；每 role 8 个非空 shard |
| H3 candidate checkpoint | 8 owner shards；retained manifest `5d936aa857073b75f1ff3cd5e9e61cf7f507e4e223f0de63f71759a476b363df` |
| H3 frozen comparator | `h3_final_comparison.json` SHA `7c3838fe565c10fac0b880b0fc2d7dce99f8cfcfef88d56e4f820df1f2f6a969` |
| H3 completion audit | `h3_completion_audit.json` SHA 在 compact record 的 evidence index 中绑定 |

compact record `outcomes/records/task041_side_balh_transfer_v1.json` 保留 H2 的完整 80 行和 H3 的完整 600 行 channel；大 memory timeline、canonical/mesh/matrix/factor 数组继续留在 ignored results，不进入 Git。

## 历史负结果和未运行项

- H3e 5 nm BAL_H 曾在 8 个 cost probes 后以 `SETUP_COST_BLOCKED` 受控停止；预测不是数值失败。H3f-C 用户后来明确授权关闭本 candidate 的时间停止，H3e 原记录不因此变成通过。
- H2 首次缺失 main-guard 的工程失败入口为 `/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/h2_13p5nm_balh_20260912_cda7cc8a/h2_candidate_stdout.log` 及同目录 `h2_candidate_invocation.json`；实际 run directory 为 `/home/fenics/Projects/MyFEniCS/results/task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8/task041_13p5nm_p6h10_m120_mpi8_balh__hybrid_iterative__mpi8__M120/20260912T013022.784680Z`，inner exit `0`、wrapper `3`、wall `3.523241758 s`，未产出 consumer/PDE 结果，分类为 `task041_consumer_summary_missing`。另一条 H2 BAL_H admission/MPC-space 工程失败是 `/home/fenics/Projects/MyFEniCS/results/task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8/task041_13p5nm_p6h10_m120_mpi8_balh__hybrid_iterative__mpi8__M120/20260912T014006.920548Z` 的 `Task041ModePrepError`，consumer 已进入 `top_construction_cleanup`；两条记录分别保留。裸 pytest exit139 保留为 `wrong-interpreter invocation`，因果根因未完全确认，不归因为 MPI 工具，也不作为数值失败。
- H3g 的空 parent/监控竞态、terminal false、TERM/KILL、`notLoaded` 通知失败均作为 research incident 保留；不重启 53 小时计算、不修 incident sampler 以制造公共 pass。
- `full3d_secondary`、H3/H4 的 5 nm 新 producer/QEP、全仓 pytest/CI 均 `not_run`。没有更短波长或旧 3 nm schema 兼容扩展。

## Selective merge 依赖分组

| 组 | 本轮主要文件 | 依赖、测试和 fresh evidence | 数值行为/合入边界 |
|---|---|---|---|
| production numerical/core | `src/solvers/physical_balanced_coupling.py`、`physical_balanced_h6.py`、`physical_balanced_mpc_action.py`、`physical_balanced_physical_operator.py`、`physical_balanced_positive_kernel.py`、`physical_balanced_same_mesh_transfer.py`、`physical_balanced_side_inverse.py`、`physical_balanced_trace_bridge.py`、`hybrid_fem_modal_block_ldu.py`、`src/constraints/floquet_3d_high_order.py` | H1c/d/f admission 与组件测试 `test345–350`；H2 两个 13.5 nm roots；H3 exact/candidate raw root | **确实包含本轮 BAL_H 数值组件和 verified empty-rank Floquet collective 修复**，因此不能整体写成 no numerical core change；旧 exact/default 数值路径未改为 BAL_H。尚未获 production default 或 master 合入批准。 |
| reusable runner/watchdog | `benchmarks/task041_exact_side_workflow.py`、`scripts/run_case.py`、`src/runners/task038_launcher.py`、`src/runners/task041_supervisor.py`、`benchmarks/task034_wsl_resources.py` | test344、test351、输入/执行计划回归；H2/H3 public roots；H3g sampler不计 reusable evidence | 增加 opt-in BAL_H 路由、time override、在线资源聚合与 evidence 传递；legacy default保留。H3g 固定 PID 接管脚本不属于可复用 watcher。 |
| checker/benchmark | `benchmarks/task041_balh_workflow.py`、`task041_legacy_native_packet.py`、`task041_side_balh_comparison.py`、test351/352 | H3c packet loader probe、H2 comparison `c8d3c7bf...`、H3 comparison `7c3838fe...` | 从 raw 字段独立重算 80/600 channels、canonical、场和 flux；不改变求解器。结果只绑定列出的 source/input/packet。 |
| compact evidence/docs | 本报告、`records/task041_side_balh_transfer_v1.json`、`response_v2.md`、summary/test_summary、progress/registry | H3 completion audit、ledger、comparator exit1与 raw/hash 索引；H4 只跑文档合同 | 只分类和解释既有结果，不改 raw/checker/source；不表示 master approval。 |
| research-only | BAL_H candidate side inverse / finite nonlinear response Schur 及对应 research profile | H2/H3 candidate numerical evidence；H3 resource/exit不完整 | `research_only_approximate_candidate`；有 p4/nested iterative 成本和不同速度，不能视为 exact-side/factor-free qualification。 |
| do-not-merge | H3g incident-specific orphan sampler、termination/notification artifacts | 单文件 orphan raw 与 incident SHA | 只留审计证据，`do-not-merge`、`not qualified for reuse`；不纳入普通监控框架。 |

推荐依赖次序为 numerical/core → runner/watchdog → checker/benchmark → compact evidence/docs；research-only 与 do-not-merge 永远分开。上述分组不是 master 合入批准。

## 证据索引和限制

- H3h completion audit：`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/h3h_final_20260914_51694bbc/h3_completion_audit.json`。
- H3h comparison 与 exit：同目录的 `h3_final_comparison.json`、`comparator_exit.json`；comparator exit1 的原因是 consumer resource evidence false，numerical/comparison contract 为 true。
- H3g incident 与三段同文件资源：`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/h3f_c_5nm_balh_20260912_51694bbc/orphan_supervision_incident.json`、`orphan_resource_samples.jsonl`。
- H2 final comparison：`.../h3b_legacy_native_validation_20260912_49604fd4/h2_comparison_h3c_final.json`，SHA `c8d3c7bf259d8d78a0b8d1152f7184216156824bf764c8366604fb72d374387d`。

本 H4 文档不宣称 continuum convergence、完整 workflow 内存节省、5 nm BAL_H 的生产资格或 H3 legacy producer 的完整 parent 覆盖；这些限制是结果的一部分，而不是被省略的“通过”。
