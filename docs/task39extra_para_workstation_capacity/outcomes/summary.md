# 原生迁移与容量任务：执行结果总账

## V6收口后用户追加的p3候选（S3，2026-10-04）

本节只记录用户追加的p6细层/p3准确粗修正候选；这是Review V6之后的补充执行范围，不是Review V7，也不改变下面保存的V6历史结论。正式路线的FGMRES作用于p6凝聚trace加全部port未知量（5 nm 600个、2 nm 3904个），完整未凝聚p6 A6仍用于原残差/相关作用。本次18-cell组件只做固定PC见证，没有运行FGMRES外层步；A3准确MUMPS因子与既有数值门保持不变。

| 阶段 | 结果 | 限定 |
|---|---|---|
| 5 nm p3真实FE/MPC组件 | 18 cells、600 modes；三次完整PC，每次C1/C2均PASS；主审接受 | 组件通过，不是3780-cell完整场或物理资格；保留两次失败attempt |
| 2 nm p3真实FE/MPC组件 | 18 cells、3904 modes；三次完整PC，每次两次C均PASS；主审接受 | 组件通过，不是完整2 nm/P2/收敛资格 |
| setup与小组件PC | build 221.760 s（非完整setup）；2 nm mean PC 5.145069 s | 旧q4比值仅非配对小组件工程对照；不外推完整步数或0.7 nm ETA |
| 唯一5 nm正式回归 | run `20261004T085614.837316Z`；source `2b0a7c1d6e5a20c5d0323469cd018deeb73898c2` clean；真实3780 cells、600 modes、A3/p3；setup同钟 `1117.064241 s`；full workflow `30238.071032 s` | 第544个outer后归类`USER_CONTROLLED_STOP`；信号sender/编号未知；step544无已完成A6检查记录，可能中断于检查期间；最近已完成A6在step536=`0.0038091382027435404 > 1e-6`；`NOT_QUALIFIED_INCOMPLETE_INTERRUPTED_RUN`，不是数值Gate失败结论。见[终态compact](records/p3_full5nm_terminal_compact_v1.json) |
| 原13.5 nm p3模型anchor | run `20261004T235056.532239Z`，source `a1a1e78a74a5497d7929a67f1de686965f30a066`；990 cells、80 modes；361步，原A6 `9.454573485808941e-7` | 主审接受原模型回归；FE L2/scaled-curl约`6.09e-10/6.13e-10`、EH约`6.56e-10/6.11e-10`、mode幅值`5.23e-10`、逐通道R/T功率最大差`3.11e-11`、总R/T/A/A_volume最大差`4.89e-10`；`REFERENCE_AUTHORITY_LIMITED`仍保留。见[anchor compact](records/p3_anchor_13p5nm_saved_field_pair_v1.json) |
| 匹配q4 F5的有限窗口观察 | i0→i120累计`solve_seconds`差/120：p3 `52.973319714 s/step`、q4 `79.389986392 s/step`，观察比`1.49868x` | 同step120 A6为p3 `0.0489090873604`、q4 `1.06532658799e-6`；单步更快没有弥补残差退化，非配对场、非总time-to-solution比较。主审回执绑定于终态compact |
| p3完整2 nm场、0.7 nm场/容量资格 | `NOT_RUN` / `TARGET_0P7NM_48H_NOT_ESTABLISHED` | 与此前V6 q4 P2限域pilot分开；不自动继续，低内存p4逆新增试验0 |
| 0.7 nm规划与精度缺口 | planner轴`100×50×280`，`1,400,000 cells / 32,060 modes`；派生p3/p4保留骨架+ports `63,122,060 / 117,792,060`行；约65个p6维度complex128数组条件payload `288,695,742,400 B` | 非FE网格、矩阵、factor或RSS实测；材料模型/网格精度、factor fill、收敛步数、48 h与2 TB能力均未资格化。planner与mode inventory hash见[anchor compact](records/p3_anchor_13p5nm_saved_field_pair_v1.json) |

本轮原始问题是核实task39extra已成功p3方案的迁移并评判0.7 nm：donor closure `3804ede8acfd120d0d8d312415ec5e7a2c296cd7`、V25 Q3 source `cad282e25ed53cad1f9e4a5a70c14f3dd40e6d32`；同一13.5 nm模型此前已在工作站source `6d989b4b9cbca12fcc35455d7ff381e66ef7ca6d`成功361步。当前a1a1e78a74a5497d7929a67f1de686965f30a066只补V6显式入口和同模型anchor回归。M0确认BAL_H仍为C→A→H→A→C、随后`zc+s-t`，准确A3/MUMPS、restart32；donor ledger只增加诊断/失败分类，几何历史分别为donor round12并重写canonical坐标、工作站`raw_unrounded`、当前V6 round12 group key/未舍入代表坐标。逐项源码blob/行与planner、mode inventory hash见anchor compact。
anchor旧→新setup为`5295.216887→431.617323 s`（12.27x），KSP API为`5521.324173→5076.041082 s`（1.09x），workflow为`10997.372826→5709.358387 s`（1.93x）；两场均361步，非受控AB。budget→numeric完成区间为`6.575→7.866 s`，反而更长且非独立MUMPS API timer，不称A3 numeric/LU提速。新场实际raw geometry仍96类；round12组键/未舍入代表坐标将tensor evaluations/groups由96降为12，oriented Schur/LU仍139类，这是显式近似分组而非几何类减少。资源审计17,924样本全可读、RSS峰`5294153728 B`、task swap0、PSS关闭、清场；global pswpin+1页/out0页归因unknown。日志审计为一遍JSON解析加额外一遍顺序读末行，并非严格单遍IO。主审pair receipt SHA `3c6dc11b5db883a659e0d354ee4b49f57b509572e49a19f3e406571fbfb2af41`。完整证据见[S3结果](p3_mid_order_s3.md)、[S3组件compact](records/p3_mid_order_s3_components_v1.json)、[13.5 nm anchor compact](records/p3_anchor_13p5nm_saved_field_pair_v1.json)、[5 nm终态compact](records/p3_full5nm_terminal_compact_v1.json)、[启动前草案](records/p3_full5nm_p3_regression_launch_draft_v1.json)和[post-V6回应](../response_post_v6_p3.md)。5 nm旧失败、方向原型负例及512 solution-only检查点均保留；本次不表示“p3核心新迁移成功”，也不外推5/2/0.7 nm。

## Review V6历史收口（2026-10-04；下文保留V6当时的结论）

P2在2 nm硅模型上完成预先限定的16步计算，主审按28项检查接受其“范围内完成”记录。它没有收敛、没有通过完整求解器残差门，也没有运行official R/T/A或物理checker；因此状态为 `NOT_SOLVER_QUALIFICATION`。16步是计划停止点，不是收敛证据，不从残差外推总步数，也不续跑。

| 模型与身份 | measured 数值 / 阶段 | 资源与资格 | evidence |
|---|---|---|---|
| 2 nm Si，p6/h1.5 q4；54332 cells、3904 modes；run `20261002T194532.418927Z` | source `584d6e406e6e1ed552fff4fd311b51549c984825`；input `bcd73afb38d750152a028de7b9b4e390d2c5fca688ad28c5352ba8cfe6cbcf12`；physical `fb8d259274ea968deb243ab9fa2b5c360b74f19dd8ebcf606aeba643cb59b6ef`；resolved `cc6c7244c0c72c33aa17062370e2174e705c162861231a2a2030a6f856919532`；mode `4b62741e84970cc5312c88039244ad5ba30065ea92dcf72a949773fef8de6364` | exit0、16/16 planned steps、final original A6 `0.35320202729663724`；process-tree RSS peak `1150080622592 B`，tree swap0；全球 pswpin +24 pages/pswpout +0，归因unknown；332532/332532 samples readable，descendants cleared | [P2 terminal compact](records/v6_2nm_16step_pilot.json)；主审receipt `tmp/review_v6_components/p2_main_terminal_acceptance_20261004_v2.json` SHA `16af3bb771f74e743a45e396adf4f15f24cf1f97a850de04254d80882b8a6554` |
| 同一P2中的准确p4粗修正 | 34/34 logical returns通过完整原A4；最大 `9.0156139e-11`；1 symbolic/1 numeric/49 MatSolve；每次最多1、总计15次额外同因子精化，策略上限每次2 | QA和16步复用同一准确因子。凝聚增广矩阵4,586,288行；输入矩阵stored NNZ `2,070,391,064`（owned-row `getRow`条目），不是MUMPS因子fill NNZ或因子内存。原始backend INFOG[22]记为916713 MB；字节换算与因子NNZ解码unknown | [P2 compact](records/v6_2nm_16step_pilot.json)；实际记录为run根的`physical_intermediate_summary.json`，SHA `b058c56f0f20c90b3d1722962e26245b3448d55af5099fe73a69ff3b24aeae3a` |
| backend 容量字段的条件情景 | P2 `INFOG[22]=916713 MB`；以916.713 GB作表示，若候选值仅按cell数线性缩放则为约23.621 TB | 原始MUMPS字段单列；MB到B换算、真实factor-fill NNZ均unknown。线性乘数情景不是实测、下界、预测或R48容量资格 | [P2 compact](records/v6_2nm_16step_pilot.json)、[R48 capacity record](records/v6_0p7nm_48h_capacity_plan.json) |
| P2时间边界 | workflow `111741.070836 s`；workflow起点到solve开始 `84346.877104 s`；same-object setup检查完成 `84346.872505 s`，相差4.6 ms；MUMPS numeric API `57870.129416 s`墙钟 / `57851.993158 s`进程CPU | 旧的`44111.673835 s`为不同包围区间，不作LU提速比较。末PC的C父计时`1051.014 s`，其中MatSolve `640.645 s`、A4 parent `156.550 s`，不能将整个C叫作LU | [P2 compact](records/v6_2nm_16step_pilot.json)；资源摘要仅来自一次流式审计，原3.38 GB日志未再次扫描 |
| 0.7 nm R48元数据候选 | planner轴计数`100×50×280=1,400,000 cells`；完整external inventory `32,060 modes`（每侧16,030）；7个材料平面与目标间距对齐 | 仅stage4轴planner及生产动态mode inventory。没有创建FE网格、全局矩阵、MUMPS因子或PDE；`54332×27`不是实测网格 | [R48 capacity record](records/v6_0p7nm_48h_capacity_plan.json)；完整10,774,375 B inventory留在ignored路径并以SHA绑定 |
| 周期独立行、保留行与端口 | p6与p4求解空间都对单元内部未知量作静态凝聚，保留周期骨架+端口；完整原A6作用、显式残差和单元恢复仍包含内部场工作。P2运行行数与周期公式控制相符；0.7 nm派生周期独立p6/p4场行`907,560,000/268,960,000`，保留骨架+32060端口行`277,592,060/117,792,060` | 0.7 nm行数来自规则六面体拓扑和Nédélec边/面/单元自由度公式，不是FE离散或容量实测 | [R48 capacity record](records/v6_0p7nm_48h_capacity_plan.json) |
| 向量与工作集边界 | 按约65个`complex128`数组、每个长度等于p6保留+端口行，0.7 nm载荷情景为`288695742400 B`；一个32060×32060复数稠密数组为`16445497600 B` | 都是明确条件下的数组载荷算术，不是已分配内存、RSS或完整峰值。P2的108.004/106.341/91.060 GB三项buffer inventory重叠，不能求和；对象id去重不等于底层buffer去重 | [R48 capacity record](records/v6_0p7nm_48h_capacity_plan.json)、[P2 compact](records/v6_2nm_16step_pilot.json) |
| 48小时目标与下一步 | `TARGET_0P7NM_48H_NOT_ESTABLISHED`；预算示例setup/solve/recovery-output-cleanup为43200/115200/14400 s | 不根据16步残差推断收敛步数或总耗时。没有0.7 nm精度PDE，没有新低内存p4逆试验；R48/Z限于元数据、容量账和文档收口 | [R48 capacity record](records/v6_0p7nm_48h_capacity_plan.json) |

buffer payload、输入矩阵stored NNZ、MUMPS因子内存和同时进程树RSS是不同口径。P2的三项buffer数字有交叠；Hlocal及全局Hp/Hhat可能含mode平方尺寸，但现存证据没有各自shape，故保留unknown。按单元、mode一次项、mode平方项拆分的条件公式见R48 compact；其中示例不是上界、下界或RSS预测。

planner使用P2已验收resolved配置作为基底，只在内存中改 wavelength、h与动态通道策略。候选材料取硅的Henke表行线性插值并按项目约定换算；这只为容量规划提供材料元数据，不是CXRO直接计算，也不是0.7 nm精度或连续体资格。目标48小时仍未建立。

## Review V6 F5 终态：5 nm完整场主审通过（2026-10-03；先于本节P2 pilot）

F5在5 nm硅模型上组装有限元系统、用p6外层迭代求完整场，并用精确凝聚p4 MUMPS因子做修正；检查的是本run完整残差、场、模态和能量，不把较快setup当数值资格。当前正式记录绑定运行时clean source `1828bc675f2862025e0eaed0beccf15982eb09e6`。后续归档文档的提交SHA不替代此运行SHA。

| 项目 | 实测结果 | 结论与证据边界 |
|---|---|---|
| 模型与身份 | 5 nm Si，p6/h4，q4；3780 cells、600个原始DtN模态；input `599017bde2b8bef953939cfd519fb72f97bec5bb6a9667fe5e8b379303dd69c9`、physical `96b548e4cd7fbec7f5397d6be7fa22cf5f9e0faaaeb2f70ff95cf01f0f8af88d`、resolved/mode `24ea2abf0d6212ff6c63f79f25a021a01b2dcd8586beb7ad15d48457b779f427` / `dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645` | run `20261002T153058.967208Z`；[F5终态compact](records/v6_5nm_terminal.json)；运行源码SHA与归档提交分列 |
| 残差与p4 | 121个正式外层步；最终完整原A6相对残差 `8.704501286501755e-7`；244/244 p4返回PASS，最差原A4 `9.604857895562664e-11`；每次C至多1次额外精化、全程额外精化2次 | 过原Gate；精确p4 MUMPS一个symbolic/一个numeric、246次solve；每次C均检查完整原A4。保留`Aq<=1e-10`和最多两次同因子额外精化 |
| 场、模态与能量 | 全场L2/scaled-curl `7.35463e-8/7.31531e-8`；选定E/H相对误差 `1.13057e-7/1.12349e-7`；600模态幅值最大相对差 `5.08874e-8`、功率最大绝对差 `2.86881e-8`；official `R00_s/R00_p/R00_total=0.7325626994/1.63965e-23/0.7325626994`，`R/T/A_port=0.7331835098/0.000222439625/0.2665940506`，`A_volume=0.2665940349` | 完整场、E/H、600-mode与旧同物理离散参考通过；端口与体吸收差 `1.56590e-8`。不是continuum convergence证明；诊断EH Fourier通量不替代official R/T/A |
| 时间 | workflow `12534.182499 s`；同单调时钟setup `1696.196008 s`；solve含最终检查 `9952.023125 s`；KSP API `9830.705350 s`，折算121外层步 `81.245499 s/步`；solve折算 `82.248125 s/步`（含检查/输出） | `iterations.jsonl`有125条记录，32/64/96各重复；正式步数仍为121，不能用124个callback求均值。checker `176.390309 s`，physical intermediate summary `12349.965614 s`。阶段定义见下表与compact |
| 资源与清场 | 整树RSS峰 `38082981888 B`，低于 `1300000000000 B` hard线；任务swap峰0，global pswp增量0；36145条资源样本可读，最大相邻间隔 `0.544715086 s`，末样本距watchdog clock_end `0.068841 s`；4个样本含已消失PID条目；watchdog COMPLETED、后代清场 | 主审按同一资源文件hash单次流式核验，PSS全程关闭；不把4个消失条目写成零，也不把终态后时间增长判作运行中stale。资源原文件不入Git，hash/范围见compact |
| 与旧V5工程比较 | setup `11263.075601→1696.196008 s`，旧/新比 `6.6402x`；solve `10671.215508→9952.023125 s`，`1.0723x`；workflow `22680.911776→12534.182499 s`，`1.8095x` | 同case非受控工程比较：实现、几何分组、NUMA、PSS和缓存条件不同；不作单因素因果归因，不据此承诺2 nm耗时 |
| 后续状态 | F5 `F5_FULL_REGRESSION_ACCEPTED`；此后唯一P2 pilot已按包批准并由主审接受限域终态 | P2对应source与归档文档HEAD分列；16步计划停止不是收敛资格，不报告official R/T/A，也不自动续跑。最新结果见本文件顶部P2/R48表 |

| F5阶段 | 相邻marker实测秒 | 计时边界 |
|---|---:|---|
| retained runtime准备 | 605.609374 | workflow开始至runtime build complete |
| reference symbolic | 8.076159 | symbolic started→complete |
| reference numeric | 376.282022 | budget evaluated→numeric complete |
| p4 retained factor阶段 | 25.312807 | numeric complete→retained p4 factor complete |
| H6原对角窗口/packed action | 110.275482 | 对角setup阶段；不是solve阶段 |
| BAL_H bridge | 18.146809 | retained bridge marker间隔 |
| native Aq投影检查 | 79.315851 | Aq projection marker间隔 |
| same-object setup checks | 473.089887 | 同对象检查marker间隔 |
| setup结束 | 1696.196008 | workflow开始→solve开始的同单调时钟边界 |

全run的C/PC父记录122条，包含一次setup apply及121次正式outer apply；对应244次C及244条通过的p4决定。run总体C parent为4470.977117 s、p4 logical child ledger为4122.425117 s；其余分项和父子重叠范围保存在compact中，不将嵌套timer相加。最后两次C合计36.0696 s，其中MatSolve 15.06384 s、局部恢复4.12764 s、A4 parent 6.78377 s；这组末段计时不能替代全程均值。

主审终态回执为 `tmp/review_v6_components/f5_main_terminal_review_20261003.json`（SHA `b06c8044736c06b6db00bd792f83e1b075493d8e8869ac3813b6b500212cabd3`）；资源单次审核回执为 `tmp/review_v6_components/f5_resource_main_terminal_audit_20261002T190922Z.json`（SHA `1866be1343fc97cec4c920d05a33743ed20c71ae9bd8c0e79fcaf1b6b1ee4a53`）。资源log SHA `a4bf28a10c75fcc88adb0d087b97e739c3f965af1618d68a69a66c71c672fd04`，398061029 bytes；没有再次扫描。旧V5工程比较回执SHA为 `93914a10d778a9151b408cfe258a94bd490bb8abd3a743cbac6f6a57dde3ef6d`。

## F2 异常终态交接 2026年10月2日

| 项目 | 同run实测或派生结果 | 证据 |
|---|---|---|
| 状态与首因 | `WORKER_FAILED / exit137`；内核node1 memory-policy OOM杀worker341839；触发分配的是另一PID1172428，其任务归属unknown；后代清场 | [终态报告](f2_terminal_oom_20261002.md)、[内核摘录](records/f2_kernel_oom_20261002_excerpt.txt) |
| run与运行源码 | `20260924T104936.107285Z`；`64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa`，启动/终态clean；文档HEAD不代表运行SHA | [compact](records/f2_terminal_oom_20261002_compact_v1.json) |
| 进展与资格 | 完成228步Schur `9.373049823814199e-5`；最近独立原A6第224步 `9.758316562442362e-5`，未到1e-6；RTA/checker NOT_RUN；224步解检查点仍在 | [全部A6检查CSV](records/f2_a6_residual_history_20261002.csv) |
| 时间 | workflow `666232.838509 s`；setup `184388.380644 s`；最后228步callback solve `479635.727603 s`，非纯KSP API timer | compact.time |
| 资源 | 整树采样RSS峰 `1154381864960` B，低于1.3e12 B硬线；任务VmSwap峰 `8574500864` B；global pswp增量3138800/5146004页，归因未决 | compact.resource与evidence.watchdog_summary |

本条记录冻结于 `2026-10-02T04:49:18.771814+00:00` UTC / `2026-10-02T12:49:18.771814+08:00` UTC+8。内核OOM发生时node1 Normal free448.629 MiB低于min451.973 MiB、swap free0，全机尚有derived887.976 GB free；不能把本场允许回落的preferred策略直接认作严格node1绑定，也不能将全机换页归因到邻近项目。只追加文档交接，未优化、重启、另跑或merge master。下面9月28日及更早段落是原时刻历史快照，保留不改；当前终态以上表为准。

## Review V6 E3 阶段收口时状态（2026-10-02；随后F5已通过）

| 项目 | 实测结论 | 证据与边界 |
|---|---|---|
| 固定工作量 | 5 nm 与 2 nm 各一个 18-cell FE fixture；math1→math4→math4→math1，共四场。每场每个 fixture 一个 p4 factor，三次固定 PC 输出；各场及 AB/BA 比较通过 | [线程选择 compact](records/v6_thread_selection.json)；全部运行绑定 clean source `41bd6afa0be4e6ff242025f3730a3e458d3717e7` 与 launcher SHA |
| PC 对照 | 首次调用单列；warm 仅取第 2、3 次调用均值。5 nm math1/math4 warm 比值 AB/BA=`1.384866/1.717097`；2 nm=`1.047754/0.975515` | 2 nm 未显示稳定收益，不能以 factor API 单独耗时替代完整 PC 结论 |
| 冻结配置 | MPI1、math1、worker CPU24、parent CPU9、NUMA interleave node0/1；不做 8 线程 | math4 数值等价与组件 PASS 证据保留；math4线程设置4、`openblas_get_num_threads()`=4、OS线程数6；报告`parallel_runtime=1`是`openblas_get_parallel()`返回的`OPENBLAS_THREAD`类型枚举，不是线程数。MUMPS共享内存能力 unknown |
| 下一门 | 当时计划为唯一 F5；此后已按批准完成并由主审通过 | [F5终态compact](records/v6_5nm_terminal.json)；运行SHA `1828bc675f2862025e0eaed0beccf15982eb09e6` |

此 E3 只证明限定小网格、固定工作量组件上的比较，不是完整场 PDE 资格，不替代 F5 的 A6、物理量、同离散参考与资源 Gate。邻近任务未被修改；CPU与背景进程快照不代表整机独占。


## Review V5 运行中交接（2026-09-28 02:34:15.838437 UTC / 10:34:15.838437 UTC+8）：F2 RUNNING

唯一2 nm Si、p6/h1.5、q4、3904通道run `20260924T104936.107285Z` 仍在solve，启动source为 `64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa`；文档提交HEAD不代表运行源码。最后完成outer iteration64，独立原A6相对残差 `0.022358747111508717`（iteration64、solve_seconds130416.063935、physical_residual_pass=false），尚未收敛；不记录正式数值/物理/RTA PASS。bridge sequence65含setup一次，实际已完成64次outer PC；logical131已返回，当前完整PC与outer65完成记录未写。

同一冻结快照：worker workflow总 315878.685780 s，setup 184388.380644 s，实时KSP阶段 131490.305148 s（含检查/输出；最终直接KSP timer unknown）。任务树RSS当前 1151172259840 B、既有前缀峰 1154356473856 B，task swap0；global pswp当前0/229页，基线0/0，仅全机诊断，不归因到任务。固定整树实测RSS硬线1.3e12 B、无时间截止，未改watchdog/CPU/NUMA/参数。

本场p6/p4实际54 raw geometry→6 tensor groups、87 oriented classes，FFCx kernel约292.124/33.861 s；p4 numeric完整marker区间44111.673835 s，H6 diagonal118597.092899 s。最近完整PC两次C1371.435401 s，p4 ledger占1319.492162 s，外围51.943239 s；因子求解/恢复/native A4验算内部份额unknown，不能全叫LU回代。当前PC A6为分开的curl/mass快速作用，原A4验算仍native，局部tensor仍FFCx，非blocked Gram。

完整时间边界、source/ABI、近期PC/精化、采样峰、PSS观察局限和文件范围/hash见[本次运行中交接](f2_running_handoff_20260928.md)及[compact](records/f2_running_handoff_20260928_compact_v1.json)。原9月24日“F2 fresh准入待核”段与更早失败均保留为历史，当前状态以本带时间戳交接为准。


## Review V5 当前阶段（2026-09-24）：F5 通过；5 nm setup-only 通过；F2 fresh 准入待核

H0/H1、M/C 与四输入合同已完成所需资格。R13 Q4/Q3 由同一 V5 retained-condensed 路径与数值 source `6d989b4b9cbca12fcc35455d7ff381e66ef7ca6d` 完成；离线 checker source `515b0c653fc25bc1da2f319da9b7e658de049a2e` 的 attempt4 为 `NUMERICAL_PAIR_PASS`，全场 L2=`3.5063e-8`、scaled-curl=`1.9531e-8`、80模态幅值=`2.2629e-8`、R/T/A/A_volume 均过限值，故记录 `R13_PAIR_RELEASE`。详见 [R13 pair release](records/r13_pair_release_v1.json)。

性能差异的主解释限定为凝聚 setup 的 class 工作量：现有几何按冻结源 `rounded_12` 规则推导为12组，冻结源正式调用未覆盖该规则；这12组是从已存几何派生，不是源 run 实测。当前 `raw_unrounded` 为96个 p6 tensor classes，即8倍 distinct-kernel 工作单元，不等于8倍墙钟。实测 Q4/Q3 p6 kernel 分别4721.61/4680.91 s；H1配对、990-cell FE对照及两场持续 thermal-throttle=0 未见本次测试负载下旧 node1 严重异常，忙频 MSR/APerf/MPERF 仍 unknown。raw geometry 身份策略不更改；Aq与每次原A4额外审计成本按现有操作记录说明，不伪造完整秒数拆分。

F5 正式 run `20260923T231207.264441Z` 已完成（source `b468907cf54d04280b461cae5fc9078186302d54`）：121步，显式 A6 residual=`8.60422e-7`；244次 p4 logical return 全通过 `1e-10`（最多1次 refinement）；`BALANCED_OUTPUT_PASS`、`MATCHED_REFERENCE_PASS`；全场 L2=`7.20455e-8`、scaled-curl=`7.16517e-8`、600模态幅值相对差=`4.94559e-8`；R/T/A/A_volume 与能量闭合通过。整树 RSS 峰=`38,934,622,208 B`、swap0，watchdog completed/cleared。身份和原始 artifact hashes 见 [F5 terminal compact](records/f5_5nm_q4_terminal_compact_v1.json)。

F5 setup 实测 `11263.076 s`（p6/p4 tensor kernels `8571.805/988.356 s`；Schur `29.46/2.23 s`）；p6/p4 各175个 raw 几何类，`round(width,12)` 从已存 geometry 派生6组，仅是派生计数，不能据此外推提速。组内实际宽度最大差约`1.42e-14`，完整 F5 仍使用 `raw_unrounded`。

随后在同一5nm Si物理/材料输入上完成105-cell真实FE/MPC候选组件：每阶18个raw几何类→9个tensor组，Schur/LU/recovery键仍是raw float64 widths+orientation，MPC expansion仍逐cell。全体raw类与代表tensor最大相对差 p4=`6.29475e-16`、p6=`4.34826e-16`；p6 action差=`3.13911e-13`、独立原A6残差行动差=`3.01989e-13`；Aq体积/DtN投影差=`4.10e-15/1.08e-14`；p4原A4返回rho raw/candidate=`2.38159e-11/1.65771e-11`。显式非零端口RHS仅另以增广矩阵残差核验，未声称该RHS通过原A4恢复检查。构建计时 p6 tensor `892.56→447.23 s`、p4 `43.45→21.26 s`；额外逐raw类tensor复算另耗 p6=`1434.48 s`、p4=`64.51 s`，不得混入生产构建计时。该组件只覆盖105 cells和4个真实零阶mode，不是完整3780-cell setup、600通道或资源资格。原始记录、命令及各项限制见[105-cell组件compact](records/v5_5nm_geometry_105_component_v1.json)；测试时基于 `b468907cf54d04280b461cae5fc9078186302d54` 的未提交工作树，精确相关源文件hash记录在compact中。

独立5 nm setup-only run `20260924T092250.568977Z` 以exit 0、`SETUP_ONLY_COMPLETED`、setup checks PASS自然完成。完整workflow=`2028.390414 s`，setup-only=`2023.440526 s`；整树RSS峰=`37236830208 B`，6192/6192样本可读、最大间隔`0.653519 s`、swap 0、后代清场。p6/p4各175个raw几何类在本次run实际聚为6个tensor组，kernel分别`292.039/33.847 s`。正式完整F5 setup=`11263.076 s`，约为当前setup-only的`5.57×`；旧F5的6组数来自保存几何推导，且旧完整场使用raw类。本次近似分组是新候选路径，不能据此宣称新的完整解或物理PASS。身份、阶段、资源、哈希和比较边界见[setup-only compact](records/f5_setup_only_v5_compact_v1.json)。

主审已批准在fresh prelaunch Gate全部通过时运行唯一F2：2 nm Si、p6/h1.5、q4、3904通道。正式输入为[`v5_node1_2nm_p6h1p5_q4.dat`](../../../input/task39extra_para_workstation_capacity/v5_node1_2nm_p6h1p5_q4.dat)，合同input SHA=`e3febbe6a785d3866e37fd3353565111952fbfe0926ee0b2c5a42eaef32149e1`、physical SHA=`fb8d259274ea968deb243ab9fa2b5c360b74f19dd8ebcf606aeba643cb59b6ef`。启动前须再次核实干净源码、完整输入/物理/3904通道身份、CPU24/CPU9、MPI1/线程1、preferred node1允许回落、旧任务树清场、有效可用内存`>=1437438953472 B`、原生heavy lock可得及15秒只读observer。运行中唯一资源硬门为整树实测RSS=`1300000000000 B`，无时间截止；任一准入失败则不启动。Q4 attempt1序列化失败记录继续保留：[原始 compact](records/v5_r13_q4_attempt1_failure_v1.json)。

## 终态：2026-09-20 04:47 UTC，2 nm h1.5 stopped by global-swap attribution Gate

| 项目 | 终态事实 |
|---|---|
| run / source | `20260918T035017.294454Z` / `41caf5141493ad6c5d6c518a64ee74fda8d7a7db` |
| 终态 | `exit=-9`、`GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED`、`descendants_cleared=true` |
| 原 watchdog stop | global `pswpout` `2→73`，delta `71` 页；任务树 swap peak `0`；整树 RSS peak `635625377792 B` |
| 内存边界 | stop sample 的 `MemAvailable=836791996416 B`、reserve=`324465062092 B`；未形成全机 RAM 耗尽证据 |
| numeric / outer / RTA | 无 `reference_numeric_complete`；未进入 outer；RTA 未运行 |
| 1300 GB guard | 独立 attachment peak=`640141377536 B`，后因 `monitoring_failed`/worker RSS unreadable 停止；不是原始换页 stop 原因 |
| compact | [2 nm h1.5 terminal snapshot](records/2nm_h1p5_measured_terminal_snapshot_v1.json) |

71 页按宿主 page size `4096 B` 为 `290816 B`（284 KiB）。原规则对任一全机 swap 计数增量即停止；在共享工作站上只能记为全局诊断归因未决，不能归因到本任务，也不称 OOM 或数值不收敛。未来 cgroup v2、`memory.swap.max=0`、任务级 `memory.swap.current/events` 方案仅作后续审核建议，本次未实施。

以下为终止前的 RUNNING 快照，原内容保留，不替代上述终态。

## 终止前快照：2026-09-20 01:35 UTC，2 nm h1.5 RUNNING

| 项目 | 当前事实 |
|---|---|
| run / source | `20260918T035017.294454Z` / `41caf5141493ad6c5d6c518a64ee74fda8d7a7db` |
| input / physical | `1f54c3429625eefcdc65e4ec7dec356a8475e4249fe179d1f2957381701fb76b` / `fb8d259274ea968deb243ab9fa2b5c360b74f19dd8ebcf606aeba643cb59b6ef` |
| 当前阶段 | `reference_numeric_preflight` marker 后；按现场事实正在 p4/MUMPS numeric，尚无 numeric complete marker |
| symbolic | `INFOG1=0`、`INFOG7=4`、`INFOG16=1222577`、`RINFOG1=1100362818940466`；symbolic 1 次已完成 |
| numeric / outer / RTA | numeric 未完成；outer 未开始；RTA 未运行 |
| 最新资源 | RSS `477900079104 B`（约477.900 GB十进制）、swap `0`、global pswp `0/2`基线；阶段峰值未从完整 resources 聚合 |
| 监督 | 原1537.5 GB watchdog + 独立1300 GB measured-RSS guard；guard当前未触发 |
| compact | [2 nm h1.5 running snapshot](records/2nm_h1p5_measured_running_snapshot_v1.json)；详见 [Response V4](../response_v4.md) |

该表是运行中快照，不替代终态或数值/物理 Gate。root/MPI/worker为三个进程；worker内部观测3个OS线程，数学库配置1。`stages.jsonl` SHA256=`f6baa2db169fd07258a26095cf71149bf07f51ee9d50d3f1eaa28ab213429f81`，`run_manifest.json` SHA256=`c2d05d59fdeaae5194cd635ec58fa79d8889a7c3d6183233a1e4e90257f28fe4`。

以下旧节保持为历史记录，不覆盖当前 RUNNING 快照。

## 上一阶段历史：2026-09-18 按实测内存重启准备

| 项目 | 当前事实 |
|---|---|
| 2 nm h1.5 PORD64 run `20260915T210201.504107Z` | symbolic成功；预测峰2716.777 GB超过原门限1537.541 GB而停止；实测采样峰277.716 GB，swap0；没有numeric/outer/RTA |
| 用户新授权 | 一次新h1.5运行，以整个任务实测RSS达到1537.5十进制GB作为停止条件；预测只记录；系统reserve、swap和监控检查保留 |
| 实现 | 独立measured输入/profile；新profile不设置预测扣减的ICNTL(23)上限；旧profile保持原行为 |
| 资格和运行身份 | [Response V3](../response_v3.md)、[本轮compact](records/2nm_h1p5_measured_retry_v1.json)；提交时尚未启动，实际启动身份见ignored `benchmarks/artifacts/native_capacity/measured_retry_20260918/launch_check.json` |
| 后续监督 | 独立watchdog持续执行；按用户要求停止主动查询/通知，由用户按需询问 |

以下为历史记录；不以旧文档的“待启动”状态覆盖上述终态和本次授权。


| 范围 / 阶段 | 状态 | 主要证据 |
|---|---|---|
| R0 native环境与隔离 | NATIVE_ENVIRONMENT_PASS | [环境与硬件](environment_and_migration.md)、[ABI](records/native_abi.json) |
| R1 attempt1，13.5 nm Si p6/h10，MPI1 | 身份检查失败，未outer | [原始负结果](records/r1_attempt1.json) |
| R1 retry1，同一模型 | PERFORMANCE_CONTROLLED_STOP；筛选未通过 | [复现/阶段资源](reproduction_13p5nm.md)、[完整compact](records/r1_attempt2.json) |
| R1 attempt3，13.5 nm Si p6/h10，550步 | own数值 Gate 通过；`BALANCED_OUTPUT_AUTHORITY_LIMITED` | [attempt3 compact](records/r1_attempt3.json) |
| R1 native direct matched reference | NATIVE_OWN_PASS_MATCHED_REFERENCE_WSL_ARRAYS_PARTIAL | [reference compact](records/r1_native_reference.json)、[80通道](records/r1_native_reference_80_channels.json) |
| R2 notch、条件native reference | `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED`；已清场，待审 | [R2负结果 compact](records/r2_notch_attempt1.json) |
| 5 nm formal p6/h4 | own数值/物理 Gate 通过；`REFERENCE_AUTHORITY_LIMITED`；资源连续资格不追认 | [5 nm compact](records/5nm_formal_attempt1.json)、[600通道CSV](records/5nm_dtn_600_channels.csv)、[tracked checker](records/5nm_checker_recheck.json)、[资源记录](records/5nm_resource_coverage.json) |
| 2 nm Si h1.5 formal attempts 1–2 | attempt1 affine geometry失败；attempt2完成P2前装配后 PORD/MUMPS `INFOG(1)=-9999, INFOG(2)=4`，未numeric；同一PORD64组件小资格通过，正式retry待本轮审核 | [失败/阶段compact](records/2nm_h1p5_formal_failure_compact_v1.json)、[PORD64记录](records/2nm_h1p5_pord64_qualification_v1.json) |
| S5 / S3 / S2 / G | R2独立未决负结果；5 nm own已完成但资源连续资格不追认；2 nm h1.5 formal仍未通过、PORD64组件已资格化；3 nm/G未解锁 | [运行总账](records/run_index.json) |
| 性能/检查修复 | 性能修复后13.5 nm R1与native reference通过；5 nm checker修复后独立recheck通过，R2归因仍未决 | `f124679e75915758076d9240bd4bef2f5c772752`；checker `d64398cb1fecd90867071688dca94e501235cf7a`；[测试](test_summary.md) |

## 2 nm Si h1.5 formal attempt 1：setup affine Gate 负结果

run `20260914T013346.036155Z` 在 source `296afa6a6c231b6ab067ad928c9f827ee72f5e98` 下完成 workflow/shared-mesh/H6 setup marker，约 `5175.8977 s` 后 exit4；worker 明确报 `only affine geometry is qualified`，未进入 P2、numeric、outer，无 iterations/residual。watchdog sampled tree RSS peak=`5115244544 B`（约 `5.12 GB`）、swap peak=`0`、global pswp delta=`0`、descendants cleared；`effective_available_bytes_at_launch=2074612776960 B`。该 run 是 `WORKER_FAILED`，不写成 OOM、数值失败或 P2/LU 结论。

实际 h1.5 规则扫描在 `54332` 个 Q1 cell 上使用同一 DG0 `mu=1/mass=2` 的 p6 original/action `ReferenceCellBasis`，两个 audit 相同；默认 NumPy 求和下 raw 绝对坐标误触发 `25432` 个 cell，centered `x-x[0]` 为 `0`，最坏 raw/centered 均用生产逐 cell 表达式复核，det 范围=`2.9761904761904217–3.3088235294118395`。早先 synthetic `1156` 计数不代表正式 kernel 触发；失败日志无 traceback，partial 与 PositiveCellBasis 两候选点保持如实记录。

三处局部修复和 translated-affine/non-affine 回归已完成；用隔离 `.venv/bin/python3 -m pytest` 跑既有 357/362 为 `16 passed, 1 skipped`。独立只读 observer 的无 PDE 自测和实际主控 SELFTEST notify-v2 ACK 也已完成。主控已放行唯一根因 retry；失败目录保留，新 run/新 observer 独立启动，h2 不启动。

## 2 nm Si h1.5 formal attempt 2：PORD/MUMPS组件阻塞与64位资格

run `20260914T061139.551088Z` 在 source `9da01fb0402bc5f7da1cdaf4cc543bb53162deea` 下完成 H6、p4体矩阵和增广装配，随后 symbolic 返回 `INFOG(1)=-9999`、`INFOG(2)=4`、`INFOG(7)=4`，未进入 numeric/solve/outer；exit4，分类 `WORKER_FAILED`。实际体矩阵为 `10604228` 行、`4752199344` NNZ，增广为 `10608132` 行、`4899800920` NNZ。该结果不是 OOM 或数值不收敛；正式图的 `NEDGES8` 未记录，保留“`-51/-2147`边界早退可能被 `NCMPA` 覆盖为 `-9999/4`”的强证据推断，不冒称正式图实测。

对 `watchdog/resources.jsonl` 已完成一次流式归并：330197行、坏行0、不可读样本0；整树RSS峰 `277758349312 B`、swap峰0、global pswp delta 0。资源样本的首末跨度与 `stages.jsonl` 相邻 marker wall 已分开记录；其中 `reference_volume_pattern→reference_volume_complete` 为数值体装配 `88431.120501188096 s`，`reference_volume_complete→reference_augmentation_complete` 为增广构造 `239.752949750982 s`，symbolic调用 `154.872576898895 s`。详见 [`2nm_h1p5_pord64_qualification_v1.json`](records/2nm_h1p5_pord64_qualification_v1.json)。

旧混合PORD边界 probe：`NEDGES8=2147483648` 返回 `INFO(1)=-51, INFO(2)=-2147`，预置 `NCMPA` 未写回；旧查询为32位。独立 `/tmp/task39extra-pord64` 仅以 `-DPORD_INTSIZE64` 重编14个PORD对象和 `mumps_pord.c`，不使用全局 `-DINTSIZE64`，复用旧 `libzmumps.a`/PETSc对象并重链任务专属 `libpetsc.so.3.19.6`。最终 activation [`scripts/activate_task39extra_pord64.sh`](../../../scripts/activate_task39extra_pord64.sh) 明确同步 `PETSC_DIR`、`PYTHONPATH`、`LD_LIBRARY_PATH`，旧 [`activate_task39extra_int64.sh`](../../../scripts/activate_task39extra_int64.sh) 不变；新prefix没有 `.pc` 文件，因此 `PKG_CONFIG_PATH` 明确 unset。完整有效argv、对象参数文件/`petscvariables`哈希、库替换和 cfg 复制步骤见 [`2nm_h1p5_pord64_build_recipe_v1.md`](records/2nm_h1p5_pord64_build_recipe_v1.md)。

同一8-cell、1944行、701496-NNZ p4/MPC fixture 在同一新prefix下通过：`petsc_int=int64`、`complex128`、query=64、唯一新PETSc map，临时 `PETSc.Options()["mat_mumps_icntl_7"]=4` 后 `INFOG(7)=4`、`INFOG(1)=0`，symbolic/numeric/solve各1次，原矩阵相对真残差 `2.922259846318588e-11`。最终 activation 另做了 imports/query/maps 轻检；组件资格不等于整张h1.5 symbolic/numeric通过，也不改变正式默认排序或主求解器。

独立 [`scripts/task39extra_2nm_h1p5_pord64_launch.py`](../../../scripts/task39extra_2nm_h1p5_pord64_launch.py) 已准备为 `CPU9 + stdin=DEVNULL + start_new_session + 单一run_case入口`，但尚未执行；h1.5正式retry与h2均保持未启动，等待本次diff/记录审核。

## 5 nm formal attempt 1（用户授权跳过未通过 R2）

用户明确覆盖执行顺序后，按原正式入口完成同一 5 nm Si p6/h4 离散解；这不把 R2 写成通过，也不解锁 3/2 nm 或 G。run 为 `20260911T065955.813489Z`，source `85a681b9bd61104466888546b83df87c27806169`，zero start、restart32、max2048、screen128，时间模式为显式 `none`。

数值结果：iteration `698`，full explicit true residual=`9.986638454029182e-7`，screen128 通过；p4 为 `1396` RHS、`1419` MatSolve、`23` refinement，terminal p4 relative residual max=`9.989282114125241e-11`。official DtN 共 `600` 个 channel，复振幅/功率与 E/H 均有限；R=`0.7331834812424759`、T=`0.00022243948430485038`、A_balance=`0.26659407927321926`、A_volume=`0.26659407694262094`，独立能量误差=`2.33059826992843e-9`。

独立 recheck 的 tracked 副本：[5nm_checker_recheck.json](records/5nm_checker_recheck.json)（来源仍为 ignored `recheck/checker.json`）具有 `independent_output_gates_passed=true`、`gate_failures=[]`、分类为 `BALANCED_OUTPUT_AUTHORITY_LIMITED`。完整 600 条 mode key/复振幅/边界振幅/逐通道功率字段已进入 [5nm_dtn_600_channels.csv](records/5nm_dtn_600_channels.csv)，并保留来源 SHA。`REFERENCE_AUTHORITY_LIMITED` 仅表示没有 5 nm matched fine/continuum 精度参考；`official_result.diffraction_channel_count=150` 是 diagnostic Fourier 计数，不替代或削减 DtN 的 600 channel。

资源与生命周期单列：[资源记录](records/5nm_resource_coverage.json)。原 parent watchdog 有监督断档，旧 wait 退出码 `UNAVAILABLE`；不能追认连续 `RESOURCE_PASS`。原始失败/launching summary、V2 recovery、原始 checker 均保留。观测整树 RSS 峰为 `50161172480 B`、swap peak=`0`；这只是外置采样可观测峰值，不填补断档。

## 最新正式 original run（attempt3）

本次是用户授权后的 clean-SHA、zero-start formal retry；旧 attempt1/attempt2 仍作为历史失败保留，未被覆盖。run compact：[records/r1_attempt3.json](records/r1_attempt3.json)。

| 项目 | measured 结果 |
|---|---|
| source / run | `9b1e8d4a1b2be9fca5b126a1ec3893e3af295e5e` / `20260909T130326.291096Z` |
| lifecycle | `exit=0`、`COMPLETED`、`descendants_cleared=true`、workflow `12560.042750451947 s` |
| numerical Gate | iteration `550`，true `9.998974191134654e-7`，solve `11589.4608165932 s`，outer `567` matvec / `550` PC |
| checker | `independent_output_gates_passed=true`，`gate_failures=[]` |
| authority | `BALANCED_OUTPUT_AUTHORITY_LIMITED`; `WSL_FULL_FIELD_COMPARISON_PARTIAL`，不是完整 R1 |
| field/modal evidence | 80 通道 relative amplitude difference `1.339354498931458e-9`；own R/T/A 与能量记录已保存 |
| p4 assembly | `491.016220843 s` vs old `1818.610 s`，`3.703767661438x`，降低 `73.000466%` |
| final enclosing-tree resources | RSS peak `3631751168 B`，swap peak `0`，watchdog samples `36437` |
| release lifecycle | RSS before=`3078565888 B`，after=`3078565888 B`，delta `0 B`；不声称发生 OS/allocator 回收 |

阶段资源峰值也已在 compact 中逐项保存：setup `3404267520 B`、solve `3085901824 B`、recovery/final peak `3631751168 B`、checker `3558637568 B`、complete `3202437120 B`，均 swap `0`。绑核证据只说明 CPU23/CPU9 affinity，不推出共享内存带宽或功耗无竞争。

因此旧 own run 的 authority 仍单独标为 limited；native direct matched reference 已完成全部本机 R1 比较资格，但不改写“完整 WSL 全场未提供”的边界。R1 不重跑 550 步；R2 attempt1 已因全局 swap 归因未决清场，暂不重跑或进入5 nm。（这是顺序覆盖前的历史状态；后续用户明确授权后执行5 nm，见上。）

## R2 notch attempt1（独立负结果）

原 V5 notch 输入以 clean source `f21a33914765a10adfa43735fb2e1ac3013ff905` 启动，input SHA=`b7ba606a5bf056d06e13065c6500c99301c7e6e4a0ec8eec1ad20797c28185c3`、notch physical SHA=`7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec`。run `20260909T191201.621471Z` 在 iteration3、outer matvec/PC=3 时由既有 watchdog 因 `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED` 受控停止：全局诊断 `pswpout delta=2` 页，进程树采样 `VmSwap peak=0`；leader=`-9`、`descendants_cleared=true`、remaining children 为空，RSS peak=`3406852096 B`。该结果不称 OOM、数值失败或邻居归因，且没有自动 retry。

早期 solve 计时与 p4/PC 证据见 [R2 compact](records/r2_notch_attempt1.json)；R2 未取得数值资格，5 nm 继续锁定。（后续用户明确覆盖顺序后已执行5 nm，见上。）

## R1 native direct matched reference（最新 Gate）

run `20260909T175256.839514Z` 在 clean source `125c383f9ec7027bd9c6528b4cafc669dd16ea6f` 下经唯一 `run_case.py` 入口完成。hard32 GiB/planning24 GiB admission 实测使用 `dynamic_cap_bytes=25769803776`、ICNTL23=`22646 MB`、symbolic estimate=`4858 MB`；symbolic 1 次、numeric 1 次、solve 2 次、factor release 通过。阶段边界与逐阶段 RSS 峰见 [compact](records/r1_native_reference.json)，80 项复振幅/逐通道功率见 [80-channel carrier record](records/r1_native_reference_80_channels.json)。

R1 资格结果：`REFERENCE_PASS` residual=`1.4427687662062765e-11`；`MATCHED_REFERENCE_PASS`，L2=`1.335826588236277e-8`、scaled-curl=`5.5945316967861595e-9`、selected E/H=`4.08219975785664e-8`/`8.908964399790286e-9`、80 模式=`5.171739887720538e-9`、功率 max absolute=`2.206432703211192e-9`，R/T/A/A_volume 差均在合同限值内，无相位拟合。watchdog `COMPLETED`、清场、swap=`0`、RSS peak=`7304724480 B`。标签保持 `NATIVE_OWN_PASS_MATCHED_REFERENCE_WSL_ARRAYS_PARTIAL`，不宣称完整 WSL 场复现。

本轮仍使用原V5 BAL_H + accurate global p4 LU，没有新迭代算法、子域法或预条件器。worker独占逻辑CPU23、监督器CPU9，隔壁CPU0–7进程未修改；缓存、venv、Git、结果全部属于独立worktree。共享socket的缓存/带宽不可能仅凭绑核证明完全零影响，未作这类承诺。

## 正式结果（measured；GiB=2^30 B）

| 模型 / attempt | p6 storage / independent | p4增广rows / NNZ / factor NNZ | outer / fine true | p4 worst true | workflow / s | 同期RSS峰值 / GiB | swap |
|---|---|---|---|---|---:|---:|---:|
| 13.5 nm Si p6h10 / 1 | 173802 / 164592 | 53164 / 24730144 / 53417584 | 未运行 | 未运行 | 2731.775 | 2.787 | 0 |
| 13.5 nm Si p6h10 / 2 | 173802 / 164592 | 53164 / 24730144 / 53417584 | 62 / 0.019433158954790204 | 4.893382586118271e-11，124次，修正0 | 3997.651 | 3.163 | 0 |

两次均无official R/T/A/A_volume、R00_s/R00_p/R00_total、80通道复幅值或selected E/H。它们是“未取得”，不是零。第二次完整true尚未达到1e-6；screen同时未满足0.01或足够完整周期趋势，不能因曲线继续下降而越过筛选。第32步native/WSL完整残差绝对差3.13e-13支持当前迭代轨迹一致，但不替代场/能量Gate。

## 已查明的性能问题与解决范围

| 问题 | 已实现处理 / measured效果 | 尚未证明 |
|---|---|---|
| 初次parent与worker抢CPU8 | parent9、worker23分离 | 与隔壁零共享带宽影响 |
| p4生成内核跨行访问、寄存器spill | 独立元素改按行访问；真实单元CSR装配6.935→1.929 s，逐位一致 | 完整252单元正式装配时长；约8.2分钟只是预测 |
| curl内核重复扫描独立系数 | 合并12个独立循环，原生成C单元p6约2倍、p4约1.4倍；真实FE逐位一致 | 完整外迭代加速倍数及R1通过 |
| PSS逐次读取增加开销 | RSS安全采样保留、PSS降频；单次采样约0.09→0.034 s | 大容量case监督开销 |
| 释放后RSS未显著下降 | 完整记录释放前后3.0787/3.0745 GB和最终清场 | 未证明allocator具体滞留或回收改进 |

物理矩阵、载荷、积分、复数精度及Gate均未改变。CPU23实测约3.6GHz；CPU2的外部限频/内存90°C是另一个已记录硬件异常，本轮没有解决它，也没有绕过热保护。变慢的可修复内核和监督开销已有实证；不能把诊断提速当正式求解成功。

## 身份、边界与下一步

base为`450255f4575792d052c1bac29837d39955ee1039`；R1 retry1运行SHA为`b2e132a7b1f1078eb3359c87a336123b3c7dfbdd`，input SHA为`eb18ecd70d49cccb1564c8c3a93d8f89d25b8734ff448b16929de5d65fd273b9`，physical SHA为`9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`。运行前后clean source与全部hash见compact。历史移交提交`72a0f58899dc5d98aa4c170edffb573ed50067c7`只读使用，没有向task39extra/task41/master写入本任务结果。

任务书§11要求screen/solve性能失败后停止主阶梯，不能把该负结果当迁移bug重复抽签。本轮交付状态为fail / PERFORMANCE_CONTROLLED_STOP；性能修复作为可审阅的显式native实现保留，额外formal retry须有明确例外授权。当前没有最短own-pass波长、没有精度资格或G网格一致性结论。具体后续blocker是单核生成内核成本与原screen预算之间的矛盾，不是开发新PC的授权。

两次formal累计wall约6729.43 s；先前准备、测试及诊断另有分项日志。尚未构造覆盖整个会话每条命令的完整campaign计费总表，不声称已完成该项完整记账；所有已知计算远低于864000 s总上限。性能诊断是同机单核小测试，不把人工等待或并行诊断父子时间重复叠加为formal wall。

## Selective merge建议

| 依赖组 | 内容 | 建议 |
|---|---|---|
| production core / numerical | native模式身份桥、严格浮点FFCx调度模块和显式接线 | 数学等价小测试通过；完整R1未重新资格化，暂不提升普通默认或合入master |
| reusable runner/watchdog | native隔离、RSS/PSS降频、身份异常分类 | 定向进程/MPI测试通过；与profile一起审阅 |
| checker/benchmark | native比较器、性能/模式/监督测试 | 依赖对应实现；不从compact状态直接推导成功 |
| compact evidence/docs | 本目录outcomes、response、总账和progress | 可独立审查正负证据，保留旧失败 |
| research-only | 本次native容量profile、CPU硬件/内核诊断 | 未资格化完整PDE；保持显式opt-in |
| do-not-merge | results、benchmarks/artifacts、tmp、venv、JIT/C/SO/矩阵/场 | ignored；只提交必要hash索引 |

未获merge approval，不合并master。证据入口：[response](../response_v1.md)、[运行索引](records/run_index.json)、[测试](test_summary.md)。
