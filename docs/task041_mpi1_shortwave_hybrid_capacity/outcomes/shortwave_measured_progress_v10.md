# Review V10-r2：W0.7 reduced-p6 warm consumer受控停止

**分类：`controlled_stop / absolute_memory_limit`。** 这是一个真实MPI8 consumer已经深入setup、在顶侧P4因子构造阶段越过process-tree cap后受控终止的记录；不是“setup未到达”，也不是数值残差失败。它尚未运行fixed-H6反馈门、outer solve、五项残差、recovery或physics。

## 身份、结果与服务终态

| 字段 | 实际值 |
|---|---|
| Review / branch | V10-r2；`codex/20260902-task41-mpi1-shortwave-hybrid-capacity` |
| 文档同步HEAD | `174ad73a78dcb8a584ea9739007ddbd1e2ef39cc`；运行数学source `5025fdd31a1edc4ce34a8df3150a12ca90009c01` |
| Invocation / unit | `10d761079d90473dadce79d3f7eb6457` / `task041-v9-w0p7-matched-cell-p6-fixed-h6-warm-sorted-map10-11-12-14-15-16-17-18-20261007T174630Z.service` |
| 数值输入 | W0.7 reduced `10×5 nm`、`z=-2..26 nm`、Hybrid接口`2/22 nm`、p6/h0.70/M400/MPI8；fixed-H6，matched local/global `h=20/29 nm`、`L=20 nm/N=29`；复用已有packet，本Invocation QEP=0 |
| CPU与线程 | MPI8×1，rank CPU `[10,11,12,14,15,16,17,18]`，node0；六个线程环境变量为1（含BLIS） |
| 终止/计费 | `absolute_memory_limit`，service finalizer=`controlled_stop`；唯一public-to-finalizer wall`2350.819163285 s`，V5 ledger 160项且本Invocation一项 |
| finalizer | 普通检查7/10；false=`pre_exit_members_clean`、`public_result_completed`、`service_terminal_normal`；controlled-stop绑定与清场/RSS下降检查通过 |

该研究运行仍`performance_not_isolated`。同宿主Task039计算未被干预。旧cold失败与此次warm受控停止分别保留，不拼成一次cold成功。

## 外层监督记录与consumer内部进度必须分开

外层service runroot为`results/task041_w0p7_matched_cell_warm_consumer_run_map10_11_12_14_15_16_17_18_20261007T174630Z`。其`markers.jsonl`只有public command开始/结束记录，SHA256为`7f2e6e335b2b9a91c6c0ba97f0fb2cf0a7262522c1a1486be5ea5d75ffd19378`。consumer内部结果在该运行绑定的真实W0.7 result tree：

`results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261007T180353.062546Z/consumer/markers.jsonl`

此文件284,367 B、44条内部阶段事件、SHA256=`b1f338ca12f9abf8c6fd5f8e9e03112086b29c4d2007a8f73e18074989121996`。内部阶段顺序如下；时间是consumer marker的elapsed wall，不与service完整wall重复累加：

| 内部阶段 | elapsed s | 事实 |
|---|---:|---|
| `one_cell_factor_ready` | 702.914996 | one-cell exact factor已ready |
| `one_cell_factor_destroyed` | 973.611411 | 该临时factor已销毁 |
| `system_ready` | 1804.320732 | coupling侧setup完成，随后进入bottom side |
| bottom `full_action_ready` | 1869.288052 | bottom full action已生成 |
| bottom `p4_condensed_trace_ready` / `p4_condensed_port_ready` | 1943.747304 / 1946.384603 | bottom P4矩阵与port项已形成 |
| `bottom_factor_ready` / `bottom_woodbury_ready` | 2262.026595 / 2262.069679 | bottom factor已ready并仍驻留；bottom Woodbury action已就绪 |
| top `full_action_ready` | 2279.518989 | top full action已生成 |
| top `p4_condensed_trace_ready` / `p4_condensed_port_ready` | 2317.395731 / 2329.365189 | top P4矩阵与port项已形成；之后进入顶侧factor构造 |

因此，service报告`controlled_stop`与“已完成多项setup”并不矛盾。feedback gate和outer尚未开始；所有正式数值及physics门均为`not_reached/not_evaluated`，不是通过，也不是失败值。

## 因子矩阵、驻留样本和下一项预算

| 对象 | 已有实测结构 | lifecycle/资源未知 |
|---|---|---|
| bottom cell-condensed P4 matrix/factor | matrix `64,966×64,966`，NNZ `27,929,686`；active trace `64,320`、interior `77,760`、port `646`；factor created=1、solve=0、live=true | factor bytes/fill未持久化；不从NNZ按比例估算 |
| top cell-condensed P4 matrix | matrix `64,966×64,966`，NNZ `39,242,250`；trace/port marker存在 | 矩阵已形成；factor-ready事件未出现；top factor bytes/fill/symbolic估计未知 |
| one-cell exact factor | factor-ready `702.914996 s`；destroyed `973.611411 s` | 独立factor字节数未知；已在bottom/top侧factor前释放 |

consumer内部sample在顶侧最后marker附近（elapsed `2329.231413 s`）为process-tree RSS=`46,439,280,640 B`、dedicated cgroup current=`44,137,930,752 B`；当时相对tree cap还余`6,781,882,368 B`。停止前最近普通sample（`2347.906314 s`）为tree RSS=`52,890,804,224 B`、cgroup current/peak=`50,623,971,328/50,624,233,472 B`，tree cap余量只剩`330,358,784 B`。supervisor所记完整run tree peak为`53,541,888,000 B`，超cap`320,724,992 B`；dedicated cgroup历史peak=`51,229,249,536 B`。RSS/cgroup及其各自采样时刻分列，不能把全过程树RSS增量全归于顶侧factor。

源码`src/solvers/physical_balanced_physical_operator.py::_build_p4_condensed_from_physical`在`p4_condensed_port_ready`后立即调用`ResearchExactFactorInverse`。该构造器在`src/solvers/hybrid_local_dtn_woodbury.py`执行`ksp.setUp()`，普通PCLU setup含symbolic与numeric；当前P4 builder的内部factor lifecycle callback只追加到本地`events`列表，没有向consumer marker转发。于是峰只能定位到顶侧factor构造区间，不能精确确定已到symbolic或numeric哪一步，也不能称top factor完成。根级`factor_inventory.json`的`{"status":"not_run"}`是旧/空占位；consumer的真实`bottom_factor_ready`及top matrix marker保留为更具体证据。

下一项若要安全测量，必须先取得top P4 factor的symbolic/工作区估计或可审的受控分配计划。顶侧矩阵已有NNZ，但`Delta_next`、pivot/workspace margin和可释放的并存对象仍未知；因此下一numeric分配目前没有可证明预算。不要重跑同一路径探下一次cap，也不应把全tree峰减某个对象字节臆造为factor占用。运行峰和停前样本足以确认当前精确cap被触发；未得到MUMPS fill/RINFOG等原始因子统计。

## workflow、ledger与绑定证据

| 文件 | SHA256 |
|---|---|
| `summary.json` | `b3bcec419161df8088756ee764ae72397680404438c743724fcdc4e4f8d50e08` |
| `service_parent_summary.json` | `b81db090e4ea6831a449362602cdde26a581b0e5d6324fc01d42c695e0f01a1a` |
| `finalizer/finalizer_summary.json` | `669e3ee0349725ec1ef1057c253b8c6b2195b29df43070abccf619c5304bdbc6` |
| `finalizer/artifact_hashes.json` | `822dec2079590117f9e4fae384666c3e688c16bef2351c6a47f11dd433b8af82` |
| outer `memory_stages.jsonl` | `592de00a7d693770fe095d231f3ff995440e73f3ee6ed1abf4b9903d110b201d` |
| consumer inner `memory_stages.jsonl` | `1519477ff8d8f31f246295c0505a3e0dbacc7ec5d22ba2aa7493727018056fb7` |
| consumer internal `markers.jsonl` | `b1f338ca12f9abf8c6fd5f8e9e03112086b29c4d2007a8f73e18074989121996` |
| V5 ledger（160 entries） | `a7022ccc177cf604dea1e0bff4bcd96735e2e82aded33645016455163927abd4` |
| compact record（仓库） | [`task041_v10_controlled_stop_20261007.json`](records/task041_v10_controlled_stop_20261007.json) |

## 后续只读/小阶段

匹配轴向步长的真实FE控制selector已有serial raw：父wall`237.46574084204622 s`；测试代码对MPI size≠1明确`skip`，没有MPI2 pass。下一步只审原helper是否能保持同一oracle和残差门并通过既有分布式trace/坐标路径运行MPI2，不新建测试框架。另从公开PETSc C API与当前native headers定位可执行symbolic-only最薄桥；不得把生产`ksp.setUp()`当symbolic-only或用大矩阵numeric试探。W0.7下一场和W2 numeric均不在本阶段启动。
