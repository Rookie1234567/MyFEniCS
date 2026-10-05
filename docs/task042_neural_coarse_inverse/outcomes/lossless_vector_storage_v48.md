# Task042 V48：完整系数无损存储对照，神经额外收益为负

把历史向量压成字节，使用时恢复一条，能省下多少驻留空间、又要付出多少时间？本轮让网络预测下一个有限元系数，再把预测与真实值的逐位异或全部保存，因此预测错误只增加码流，不允许改变场的一位。比较RAW直接视图、四条BYTE/shuffle-zstd、PREV/FCM/DFCM、同特征LIN与唯一NN，并做真实两遍内积/向量更新。

**P1–P4已完成。20个路线×数据族对照全部逐位通过；NN与LIN均真实256更新，却都由validation码流选step0。NN没有超过强传统控制，本冻结神经压缩候选关闭。** 这只是FINITE_LOSSLESS_STORAGE_COMPONENT_ONLY；没有新前向求解、原A作用、FE/mesh/JIT/LU/QR/Krylov/MPI或GPU。旧V42恢复FAIL、V44/V45场资格失败与V47删系数负结果均不变；原尺寸0.7nm/2TB48h/NN20仍未资格。

## 对象、数据与冻结

旧64hex/p6/q15的数据是三维振荡制造系数，不是合格散射场：45000 native槽、42624 canonical独立量，其中13824 trace和28800内部；旧A无完整DtN。train16/val4只读canonical及实体map，不读生成方向/偏振/振幅/相位/center/width。NN/LIN训练退出和FREEZE后才消费heldout8；首次heldout读取发生于保留的失败迁移入口，仍晚于冻结。随后读公开V45 prefix/residual各8条，包SHA `37535eaef0eb9bd33552e0be0e5f730c0e44917dbf1925cf4a39c42f0b5844bd`，只作迁移诊断，没有读sealed标签或调参。

实体全矩按类型/方向分六块，80/80/64个边实体与64/64/80个面实体，每块≤256实体，6/60矩不拆。每实体前4个已解码复系数加四个静态特征共12维，因果尺度为max(1e-30,max复abs)，首项/全零前项raw anchor；非有限位模式显式raw fallback。NN为12→32→32→2 tanh FP64、1538实参数，LIN26参数；seed428001，Adam1e-3、4096位置、16问题固定循环，每个只保留一问题的因果训练位置。部署编码/解码都用同一NumPy内核，XOR为uint64，不做浮点差值恢复。

zstd现有1.5.5单线程、库SHA `0a2128bc10841fb29e76d08d945864dfb0b6a66da5df6df5d8299197439e54bb`；BYTE/shuffle仅固定3/19级，预测后编码仅3级；4096项整数FCM/DFCM表重启于块边界。没有安装或升级环境。

## 真训练与选择

| 模型 | 实际更新/参数 | 9项FD最大操作误差，门1e-6 | 参数变化范数 | checkpoint0/64/128/256完整val码流字节 | 选中 |
|---|---|---|---|---|---|
| LIN | 256/26 | 6.74960087821e-13 | 0.424393789 | 937723 / 938272 / 938570 / 939236 | 0 |
| NN | 256/1538 | 1.66202372698e-09 | 0.492960806 | 952163 / 953158 / 952855 / 953210 | 0 |

容量预检的乐观下界565264B小于旧准备账RAW80%的4304208.8B，故没有盲目取消训练。最终RAW释放不需要的格式索引/映射后，train20原向量payload4423680B，乐观565264B仍低于其80%约3.72MB，准入结论不变。训练/模型加载的整树峰计费，不只看1538参数。完整码流而非MSE选择模型；没有读取heldout择checkpoint。

## 真正的驻留bank与消费

准备、训练、各consumer和CHECK分别进程；consumer只读部署bank、模型和静态map，原科学NPZ不进入解码进程。RAW加载后释放不必要codec元数据，get返回驻留视图；压缩路线只恢复一条完整trace，加当前向量和有界块，没有解码整库缓存。完整consumer固定先升序后降序，逐向量vdot后分256复数块axpy；不改RAW运算顺序或加拷贝。

以下字节分三种口径：码流是磁盘格式；resident是Python-owned bank载荷/metadata/model/map；complete是它加当前/解码及保守块工作区规划，**不是实测RSS**。内部不计入主trace bank；全独立向量情景另加每条28800×16B内部原始字节。解释器/allocator/library及训练均另看整树采样。即使把NN解码工作区设为0，其resident也已大于RAW complete的80%，所以20%拒绝不依赖压缩工作区保守上界。

| 数据族 | 路线 | 码流B | bank resident B | complete规划B | 两遍完整消费s |
|---|---|---|---|---|---|
| heldout | RAW | 1856591 | 1771179 | 1996715 | 0.002941586 |
| heldout | BYTE:3 | 1799313 | 2395885 | 4026349 | 0.033343093 |
| heldout | BYTE:19 | 1801081 | 2397653 | 4028117 | 0.032048727 |
| heldout | SHUFFLE:3 | 1751530 | 2348102 | 3978566 | 0.034928467 |
| heldout | SHUFFLE:19 | 1692164 | 2288736 | 3919200 | 0.036401890 |
| heldout | PREV | 1794789 | 2391361 | 4021825 | 0.246592264 |
| heldout | FCM | 1819347 | 2415918 | 4079150 | 0.351369827 |
| heldout | DFCM | 1797756 | 2394328 | 4057560 | 0.373872001 |
| heldout | LIN | 1801687 | 2399130 | 4029594 | 0.197221411 |
| heldout | NN | 1817934 | 2417133 | 4047597 | 0.276324358 |
| migration | RAW | 3639816 | 3540651 | 3766443 | 0.004589673 |
| migration | BYTE:3 | 3403793 | 4017820 | 5648540 | 0.063520051 |
| migration | BYTE:19 | 3342616 | 3956643 | 5587363 | 0.067518665 |
| migration | SHUFFLE:3 | 3196175 | 3810202 | 5440922 | 0.069533389 |
| migration | SHUFFLE:19 | 3055144 | 3669174 | 5299894 | 0.069185502 |
| migration | PREV | 3364600 | 3978627 | 5609347 | 0.532771340 |
| migration | FCM | 3444907 | 4058933 | 5722421 | 0.746727169 |
| migration | DFCM | 3389556 | 4003583 | 5667071 | 0.826394847 |
| migration | LIN | 3510922 | 4125772 | 5756492 | 0.401307358 |
| migration | NN | 3539118 | 4155724 | 5786444 | 0.640264360 |

heldout完整RAW为1996715B，NN4047597B，比例2.02713；迁移RAW3766443B，NN5786444B，比例1.53632。NN仅resident2417133/4155724B已大于RAW80%1597372/3013154B。BYTE-shuffle19码流最小1692164/3055144B，NN1817934/3539118B又分别大7.43%/15.84%；不能把通用压缩收益归NN。RAW完整消费0.002941586/0.004589673s，NN0.276324358/0.640264360s；这是一次shared-workstation现场消费，不宣称独占加速或三次性能置信。最小字节文件与最快/最小在线bank不同，保留全部正确控制的Pareto记录。

CHECK不只相信status：从上游heldout canonical与公开migration原字节重新映射，对全部24条、10路线逐位比较trace；拼回28800内部后全部42624个复系数的二进制位也相同。checker另写相同顺序的原始vdot/axpy，全部标量/输出字节相同。共331776个不同trace复系数×10路线，原完整canonical1022976个/数据全集；这是存储/消费资格，不能替代原方程、场、功率或连续精度。

## 失败、身份与费用

一次保存的真实入口失败：独立ML环境缺SciPy，冻结后的EVALUATION_DATA_001先保存heldout后在迁移导入失败。bc1d2f16改为原CSR映射数组的literal共轭转置累加；加非Hermitian小配对，独立CHECK另用逐行显式累加核对原字节，不安装环境、不重新生成数据或重训。旧失败/partial heldout/费用保留。RAW准备时多余codec metadata释放只改变生命周期，没有改变编码规则/权重/模型选择；旧准备账保留，消费使用新账。

正式数据/传统/两次真训练/FREEZE为`2bdcac4ecb299077858de01c730e72c97b6a0257`，修复后的评估编码为`bc1d2f16badadc68c4cb725d38d1ce3a52f657cc`，全部20consumer/独立CHECK/P4为`f5822a63fe28c527ee7edf58511d56bc79524fbe`，最终collector/focused为`5c262ca2b57ab763a3df5cdb36db34bd781c77cc`。每次读科学数组前核对clean、启动HEAD、实际file hashes及committed blobs。V47 aux_ANALYSIS_constraints另登记为启动e7a0b1d2+未提交五文件快照、后匹配4d914a38；原9c167a54四阶段及旧manifest不回写、不重放FE。

首次窗口2026-10-05T00:15:02.759409342 UTC，monotonic1084297.62、boot fd8f4b00-1e17-46af-a6fa-da3a32dbeba3；24h固定、末1h交付。CPU现场准入逐阶段选核、数学/Torch intra+interop1/Loader0、GPU/swap0，warning1.5/hard2GiB自有整树采样保护；共享cgroup无写权限，不冒称内核hard限制。截止及进程清场小回归实际通过。

最终费用及最大采样间隔以resource_costs_final_v48.json为准，不能用collector未结算快照冒充全集。主科学队列各CPU/PSI/MemAvailable/磁盘准入均通过，未调邻任务。早期缓存均在NN-Lab旧Task042 ML前缀，worker禁止写bytecode；后部已显式启用v48缓存，旧科学/closed未改。不得把本轮已知研发总费用当新引擎完整冷N=1；旧已知下界88656.94151362307s继续加本轮已知费用，冷FE/CSR、manual/Git/未监督IO仍unknown。

## 目标必要条件与关闭

目标每条trace1684779264B，32条53912936448B，两组107825872896B仅条件payload，没有实际目标bank分配/观测。即便全部免费消掉也只占2TB的5.3913%，若完整峰近2TB，单此杠杆达不到20%。必要条件V_best−V_NN−W≥0.2M_best，还必须检查准备/训练峰；最乐观全删除时M_best≤539129364480B。本有限NN相对RAW净节省为负，没有正的实测M_best机会界。

本分支旧restart32由PETSc管理，尚无真实VectorBank adapter；dot冻结发布是表面/有限引擎组件，不证明有同一trace bank。目标内部恢复/class cache/factor/port/通信/审核同时性与实际完整读取次数均unknown，不给dot归属虚构节省。完整时间T=C+H+r*d+其他；r上限为floor(max(0,172800−C−H−其他)/d_target)，目标C/r/d_target未知。本有限消费可计算的N=1/8/100训练+编码+加载摊销见conditional_cost_bounds_v48.json，明确其遗漏共同准备/审核及非目标尺度，不能据此授48h。

已保存按两数据族、kind/axis/moment的768组预测平方误差、XOR真实整数位长、sign/exponent/mantissa变化，说明浮点预测loss与实际后编码字节并非同一目标；不以本样本字节熵作理论下界。只选step0、传统shuffle更小、在线RAW更小更快，故关闭本冻结神经压缩部署候选；不调seed/lr/width/codec、不开三次计时或新FE/训练。唯一下一建议：仅当代表性匹配完整引擎的真实成本/向量生命周期显示另一可核算20%学习空间时，集中制定新研究合同；不要求先完成原尺寸才能开展有限试验，也不自动追加本codec。

## 证据与边界

[候选](records/candidate_comparison_v48.json) · [真训练](records/model_training_v48.json) · [独立checker](records/lossless_checker_v48.json) · [位诊断](records/prediction_bit_diagnostics_v48.json) · [容量/寿命](records/capacity_and_lifecycle_v48.json) · [完整成本](records/resource_costs_final_v48.json) · [冷费用必要条件](records/conditional_cost_bounds_v48.json) · [source勘误](records/source_snapshot_correction_v48.json) · [run/source](records/run_index_v48.json) · [数组/bank](records/array_and_bank_inventory_v48.json) · [raw](records/raw_evidence_index_v48.json) · [测试](records/tests_v48.json) · [selective](records/selective_merge_manifest_v48.json)。大数组/模型/码流留ignored artifact，不上production默认。GitHub精确页Cache miss，视觉NOT_VERIFIED；本地合同不冒充CI。

最终结算：38次监督、249样本，整树采样峰365150208B，ownswap/GPU0，最大实际采样间隔1.02457537199s；新已知有载下界218.747402798850s，含180s保守尾部扣费的账单395.945545315975s。P2/P3/P4监督合计23.965740360/69.565212163/6.498780314s，probe39.355026203s；最终ledger closed、active null、后代清场/锁释放。历史加本轮已知下界88875.500085371970s，未知冷/人工/Git/IO不补造。归档481原始版本（含闭合后纯文档验收及费用版本），所有旧版本保留。

180s尾部保守扣费内已实测metadata及末次纯文档测试2.801857483s，已计入上述已知下界；其余尾部费用unknown，不声称180s全部实测。
