# Task041 Response V12：Review V10-r2现场进度

**状态：进行中。** 本次仅同步Review V10-r2并读取已完成的W0.7 reduced-p6 matched-cell warm-consumer原始记录；没有重跑、重启或新增QEP/FE。运行源码仍为`5025fdd31a1edc4ce34a8df3150a12ca90009c01`，review同步后的文档HEAD为`174ad73a78dcb8a584ea9739007ddbd1e2ef39cc`。保护stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976`保留。宿主另有Task039计算，本轮没有干预；当前没有活动Task041计算。

## 本轮唯一W0.7运行：受控内存停止

| 项目 | 已核事实 | 状态边界 |
|---|---|---|
| 身份 | Invocation `10d761079d90473dadce79d3f7eb6457`；unit `task041-v9-w0p7-matched-cell-p6-fixed-h6-warm-sorted-map10-11-12-14-15-16-17-18-20261007T174630Z.service`；MPI8 CPU `[10,11,12,14,15,16,17,18]`；复用已验证producer packet，本次QEP运行数为0 | 单次warm consumer；不改写早先cold失败或其wall |
| 终止 | service reason=`absolute_memory_limit`，分类`controlled_stop`；public return code `-15`，finalizer terminal exit 3 | 数值失败不是已证明结论；资源门先终止 |
| 资源 | process-tree RSS峰`53,541,888,000 B`，比`53,221,163,008 B` cap高`320,724,992 B`；专属job-cgroup峰`51,229,249,536 B`，是另一口径；PSS/USS峰`43,305,919,488/42,881,789,952 B` | cap/warning/reserve仍为`53,221,163,008/47,899,046,707/412,316,860,416 B`；swap仅观察，job swap为0 |
| 服务收尾 | finalizer状态`controlled_stop`，常规检查7/10；false项为`pre_exit_members_clean`、`public_result_completed`、`service_terminal_normal`。进程组清场和RSS下降检查通过 | 这是受控停止的后处理记录，不是正常完成 |
| 工作量/计费 | 唯一public-to-finalizer wall`2,350.819163285 s`；V5 ledger 160项，此Invocation恰一条 | 不把public phase、consumer内部marker或rank时间重复收费 |

外层runroot的`markers.jsonl`只有public command开始/结束记录，不能据此说setup没有执行。consumer自己的`markers.jsonl`共44条内部事件，284,367 B，SHA256=`b1f338ca12f9abf8c6fd5f8e9e03112086b29c4d2007a8f73e18074989121996`。实际已到达：one-cell因子ready `702.915 s`；底侧P4因子/woodbury ready `2262.027/2262.070 s`；顶侧full action ready `2279.519 s`；顶侧P4凝聚trace/port ready `2317.396/2329.365 s`。固定H6反馈门和outer迭代均未到达，五项真实残差、recovery与physics门未评估。

底侧P4矩阵为`64,966×64,966`、`27,929,686`个非零项；marker同时给出active trace `64,320`、interior `77,760`、port `646`。底侧因子创建数1、solve数0，ready时因子仍live。顶侧已形成的P4矩阵为相同维度、`39,242,250`个非零项；这证明矩阵形成，不证明顶侧因子完成。逐因子字节数、MUMPS fill/INFO统计及精确numeric完成点均为unknown。根级`factor_inventory.json`中的`not_run`占位不能覆盖consumer内部真实ready marker，也不能据此声称因子字节已测。

`p4_condensed_port_ready`之后，源码立即构造顶侧`ResearchExactFactorInverse`。该构造器调用`ksp.setUp()`，其中包含LU symbolic与numeric设置；本路径的factor lifecycle callback只把事件加入局部列表，没有转发到consumer marker。因此可把超cap峰定位在顶侧P4因子构造区间，不能从末marker断定峰对应symbolic还是numeric，更不能称顶侧factor ready。接近最后内部marker的consumer采样（elapsed `2329.231 s`）为tree RSS`46,439,280,640 B`、job-cgroup current`44,137,930,752 B`；接近停止前的外层样本（`2347.906 s`）为`52,890,804,224/50,623,971,328 B`。两者是全consumer进程树与cgroup样本，不能把其增量全部归因于该因子。

## 当前阻塞和下一步

顶侧P4输入矩阵规模已知，但factor fill、symbolic估计和下一步numeric新增字节未知。最后内部marker附近cap余量约`6,781,882,368 B`，而停止前最近常规样本余量约`330,358,784 B`，最终tree采样超过cap。当前没有可审的`Delta_next`与工作区余量，不能原样再次跨入该因子numeric阶段。先从现有符号分析调用链和已安装PETSc接口找可在numeric前停下的最薄方法；在获得因子估计或有界分配计划前不启动下一场。W2仍按V10真实对象阶段推进，不用该pilot的RSS代替W2容量资格。

匹配轴向步长控制仍只有serial证据：`test_proposed_normal_incidence_homogeneous_w_matched_h_stitch_control`在source/test SHA绑定的attempt中通过，父wall`237.46574084204622 s`；该测试在MPI size不等于1时明确`skip`，所以MPI2资格为`not_run`，不能把skip记作通过。下一步只审原节点现有分布式trace收集、坐标映射和空owner合同如何扩到MPI2，不另建oracle或fixture框架。

该matched-h结果只支持均匀W、正入射、常切向场下同轴向离散的拼接方向，不资格化光栅QEP模态或本pilot物理解。当前pilot尚未到反馈/outer/五残差/recovery/physics；0.7 nm完整目标、2 TB容量和48 h冷启动目标都未达成。更细内部marker、内存阶段与文件SHA见[本轮实测进度](outcomes/shortwave_measured_progress_v10.md)和[hash-bound record](outcomes/records/task041_v10_controlled_stop_20261007.json)。
