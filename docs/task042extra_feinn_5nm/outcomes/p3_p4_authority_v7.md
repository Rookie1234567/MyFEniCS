# V7 p3/p4 authority：跨阶资格通过，唯一参考装配受控停止

本轮完成了同网格 p3→p4 的完整场/旋度嵌入、原算子配对与数组容量资格，但唯一 p4 参考在装配阶段耗尽数值工作窗口，状态 **P4_REFERENCE_TIME_BLOCKED**。没有获得 p4 参考场，因此未启动 p3/p4 比较，不能判断阶次变化大小。已按预算主动请求自有 watchdog 停止，原因明确；这不是 OOM 或 p4 精度失败证据。

提高阶次让同一个单元内的电场能表达更多细节，几何和网格都不变。准确 p3/p4 场的差可检查离散敏感性，不能直接当连续误差上界；代价是更大的有限元系统及一次独立准确参考。原 NN 对同一 p3 方程的失败与这个精度审计是不同问题，旧结论不改。

## 冻结身份与U0

| 模型 / measured身份 | p3原只读参考 | 本批p4 |
| --- | --- | --- |
| M5波长 / geometry / h | 5nm / 原Si-air三维缺口 / h1.25nm | 相同 |
| cell / FE / 积分 | 384hex / N1curl p3 / volume与DtN q15 | 384hex / N1curl p4 / volume与DtN q15 |
| 含slave / slave / 独立复FE | 34050 / 2082 / 31968 | 78936 / 3672 / 75264 |
| 独立边 / 面 / 内部 | 3744 / 14400 / 13824 | 4992 / 28800 / 41472 |
| 增广rows / 完整端口 | 32008 / 40 | 75304 / 40；rows现场核实，完整CSR未取得 |
| 材料表SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 | 同字节，只读 |
| native packet SHA256 | 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215 | 062137c4c5be83b62be6a5373cfa24244f203f0b37244aeb4fb0b8feb75eb9ad |
| p3 reference SHA256 | 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7 | p4参考packet NOT_RETAINED_NO_SOLVE |

只有N1curl阶次变化。体与原DtN面q15均冻结，原默认p4 DtN会给17，本批显式opt-in固定15并资格化，普通路径默认不改。实际tags/coords/模式hash与p3相同；另一离散的packet/master/background/rhs hash不同正常，不要求历史physical_model_sha256相等。

| 跨阶非零复场 / measured | E operation-relative | curl operation-relative | MPC恢复相对差 | 要求 |
| --- | --- | --- | --- | --- |
| small_transfer | 4.63720219433e-16 | 4.82654968846e-16 | 5.94382871167e-16 | ≤1e-10 |
| M5_transfer | 4.58598982543e-16 | 4.86625426167e-16 | 3.34063704495e-16 | ≤1e-10 |

三组非零全FE/port随机向量的原独立组装/native作用最大差2.21234051786e-15≤1e-10；A/A*共轭点积、增广/端口、非零载荷与内部矩均通过。小8cell与真实M5均含多分量、orientation和非平凡MPC相位。兼容嵌入后公共点E/curl比较，不直接相减不同长度的系数。

## 容量、唯一参考和停止

| 容量 / derived或measured | 值 | 含义 |
| --- | --- | --- |
| 数组/转换同时上界 B | 4447112320 | derived，不是RSS/factor |
| 全cell 300×300复tensor B | 552960000 | derived直展；实际8类tensor payload 11520000B |
| 实际native packet payload B | 23295240 | 数组体积，不是RSS |
| NNZ预检上界 | 40581160 | derived；实际完整CSR NNZ NOT_RETAINED |
| p4 preassembly转换上界 B | 3308140672 | derived，12GiB规划线通过 |
| MUMPS symbolic estimate / numeric workspace | NOT_RETAINED / NOT_RUN | 没有symbolic容量完成记录，不能称factor容量通过 |
| symbolic是否进入 / 完成次数 | NOT_RETAINED_NO_START_MARKER / 0 | 日志无进入点，不冒称真实开始次数 |
| numeric / solve开始次数 | 0 / 0 | 位于未取得的symbolic容量记录之后；未完成因子 |
| 新Gram matrix / factor / Gsolve / NN训练 | 0 / 0 / 0 / 0 | 历史所有成本保留 |

launcher在 3450.00074385s 到达原3600s的150s收口边界时，由Codex按用户预算请求停止。先核对自有PID/start_ticks和one-run命令，再只向launcher发SIGTERM，由既有watchdog终止/回收自身后代。原分类USER_CONTROLLED_STOP、worker exit−15，descendants_cleared=true；完整退出wall 3452.53531242s，剩余 147.464685061s≥120。本批全部数值阶段树峰 1586601984B（1.47763824463GiB），自身swap0，没有内存硬线、监督失效或OOM证据。

最后保留事件reference_pre_assembly_capacity在worker相对3.036846925s；没有装配完成、symbolic容量、numeric、solve、残差审核或恢复packet。符号是否进入没有开始标记，保持NOT_RETAINED，不把无完成记录推成一个已测启动次数。numeric/solve位于symbolic容量记录之后，未运行；没有合格p4，也没有factor释放后后处理资格。程序的solve→true residual→原子恢复packet→释放→RSS下降→完整后处理链本批没有走到，不能记通过。

| 原方程/功率 / measured、原rhs或入射功率归一 | p3原参考 | p4本轮 | 验收 |
| --- | --- | --- | --- |
| native_relative | 6.78883619212e-12 | NOT_RUN | 参考各≤1e-10 |
| augmented_relative | 6.78883897883e-12 | NOT_RUN | 参考各≤1e-10 |
| original_total_augmented_relative | 3.514516446e-12 | NOT_RUN | 参考各≤1e-10 |
| independent_DOLFINx_total_native_relative | 3.26041877377e-12 | NOT_RUN | 参考各≤1e-10 |
| R_total | 0.812426499057 | NOT_RUN | 不能比较 |
| T_total | 0.0324623960953 | NOT_RUN | 不能比较 |
| A_balance | 0.155111104848 | NOT_RUN | 不能比较 |
| R00_s | 0.812256818464 | NOT_RUN | 不能比较 |
| R00_p | 1.25634444139e-26 | NOT_RUN | 不能比较 |
| R00_total | 0.812256818464 | NOT_RUN | 不能比较 |
| A_volume | 0.155111104847 | NOT_RUN | 不能比较 |

本批c_scattered、alpha_scattered、alpha_total均NOT_RETAINED_NO_SOLVE。设计schema分别是独立master散射系数、原alpha(c)、background_alpha+alpha_scattered（含已知top入射）；没有用旧p3状态填入p4。p3只读复用，不重新MUMPS；p3/NN/Phi/Q均未作为p4初值。

## U2未运行与保留的结论

| U2要求的比较量 | 本批实际状态 | 分母与结果边界 |
| --- | --- | --- |
| total/scattered 全场L2、scaled-curl/H_code | NOT_RUN | 无合格p4，不能生成p4对应范数或相对差 |
| 原六点复E/H / 实际cell与参考点 | NOT_RUN | 原点定义保留，未拟合相位 |
| 四类完整40级复通道、逐级功率 | NOT_RUN | 原p3数据保留，没有p4复向量 |
| R/T/A_balance/A_volume及R00_s/p/total差 | NOT_RUN | 无p差异，不以旧p3数值填p4 |
| air/substrate/grating/interface-near区域 | NOT_RUN | 不直接相减不同长度系数 |
| 差值积分一次q30复核 | NOT_RUN | 没有差值场，不重复求PDE |

p4自身未资格化，独立compare-only没有启动，新U2 namespace/index不存在；没有P3_P4_SMALL_CHANGE_LIMITED或P3_P4_SENSITIVITY_OBSERVED信号。没有将NN q15/q30当跨阶测试，没有连续/h/端口截断收敛声明。旧NN对同p3方程的失败结论、旧e4_p4 DISCRETIZATION_NOT_QUALIFIED/not_run及监督标签血缘原样保留。

## 中断provenance与运行保护修正

C1的中断manifest仍把physical_model_sha256/actual_operator_packet_sha256写成p3依赖packet；p4实际hash只会在正常worker结果后更新，中断没走到该处。原manifest/physical_model_sha256.txt保留原字节，不能当p4算子hash。实际p4输入062137c4c5be83b62be6a5373cfa24244f203f0b37244aeb4fb0b8feb75eb9ad由U0原始packet、失败run冻结依赖和degree4 physical_model事件核清；C1程序顺序是先加载该packet，再生成这个事件。compact binding明确标raw_manifest_hash_valid_for_p4=false，没有重定义历史hash。C2已在worker启动前绑定p4身份，并让V7 watchdog直接约束长原生调用到150s边界，避免只靠Python阶段间检查。新增10项原字段/截止/身份定向tests与Ruff/compileall通过；修正后的入口本批没有正式重放，因此没有fresh p4完成证据。

## 全账、边界与后续

| 阶段 / measured | 完整launcher wall / s | 同时树RSS峰 / B | CPU | 自身swap峰 / B | 实际结果 |
| --- | --- | --- | --- | --- | --- |
| v7_p_transfer_checks | 158.807494071 | 1586601984 | 12 | 0 | U0资格通过 |
| v7_p4_reference | 3452.53531242 | 1289834496 | 11 | 0 | 预算受控停止 |
| v7_p3_p4_compare | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | p4参考未资格化 |

本页冻结前新增全账 3762.8175588s，含正式阶段、全部已完成辅助失败与直接/最终120s保守额度；旧45161.81665198447s及失联3284s/旧Gram/重放费用全部保留。原累计 48924.6342108s，剩 8675.36578922s。浏览器与发布后检查继续补入[最终资源账](records/resource_costs_v7.json)。U0含轻检查181.809311786s≤1200，唯一p4≤3600，新批≤7200/原≤57600均未越线。未取得装配完成timer，写NOT_RETAINED，不重放补计；父wall已包含这段CPU费用，不能重复相加或删除。

CPU-only、MPI1、数学线程1；数值warn12/hard16GiB、自身采样swap0，轻测试/浏览器≤2GiB。启动时逐次选空闲物理核，U0 CPU12、参考CPU11；保留系统max(128GiB,10%effective)余量、至少384GiB邻增长及本任务预算。未改其他项目的进程、环境、亲和性、锁或watchdog。约0.5s同时树RSS采样，无cgroup委派，不宣称连续内核限额或零干扰；tmux管理开销是外部稀疏样本，wall计费，不能当数值树连续峰。

已排除所测跨阶嵌入、orientation/MPC、完整未知量遗漏、原算子作用/端口配对和实际物理身份变化；没有数据排除p3/p4差异、连续精度、h/端口截断误差，也没测得p4求解精度或因子容量。瓶颈明确是当前独立装配路线在本次工作窗口内未完成，不能外推整个p4模型或2TB系统不可计算。没有新增神经增量、无标签/生产资格。

唯一下一步建议：review先决定如何在既定小型authority约束内解除p4装配预算阻塞并冻结比较基准，再决定是否授权[同规模单载波复包络方案](phase_representation_plan_v7.md)的最小完整矩/VJP资格与同预算对照。本批只交计划，不实现训练器、不训练、不自动第二次factor。目标尺寸5nm和0.7nm、p5、h细化、更多端口均未启动；小型p4未完成不能推广为模型不可计算。

[design](records/discretization_design_v7.json)、[U0/实际p4身份](records/p_transfer_checks_v7.json)、[停止与p4状态](records/p4_reference_v7.json)、[未运行比较CSV](records/p3_p4_comparison_v7.csv)、[Gate](records/gate_decisions_v7.json)、[run/source/hash](records/run_index_v7.json)、[最终资源](records/resource_costs_v7.json)、[新渲染](records/render_check_v7.json)。大数组、部分装配对象和日志留ignored，旧Task042与V1–V6结果不覆盖。
