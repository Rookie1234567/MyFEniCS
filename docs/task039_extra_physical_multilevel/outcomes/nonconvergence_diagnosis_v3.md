# Task39extra：D5最新收口——原A4数值Gate拒绝，7次PC诊断完成

| 项目 | 最新结果与适用边界 |
|---|---|
| 来源与模型 | clean source `bf8e0c1d16c9c86677e866cdf29fd5491f076e32`；原始13.5nm、1°、s、Full3D p6/h10、MPI1/线程1、80 DtN modes；无参考D1/D3诊断 |
| 数据/作用 | 3份历史快照原A6残差复现，最大绝对差2.77556e-16；native独立系数逐位匹配，分项和与A作用一致 |
| 调用计数 | 8 started / 7 completed；第8次JOINT448→LIGHT未完成，不能记为完整PC；已知误差/投影/互补/D4均not_run |
| 终止 | 原A4残差1.0086968840613509e-10>1e-10（超限0.8696884%）；worker DIAGNOSTICS_FAILED，watchdog/launch WORKER_FAILED，outer exit2 |
| 资源/清场 | 同期树RSS峰3777171456 B<实际cap8367992832 B；reserve4294967296 B、最低available9252577280 B；3324样本无违规，swap0；父进程及20个已观测后代清场 |
| 时间 | watchdog mono866.072315784 / BOOTTIME866.072315245 / UTC945.518512242 s；逐段保守收费945.519546580 s，outer含pre/post952.495114811 s |
| 规模 | p6存储173802/独立164592行、252cells；p4存储53084/独立48960、增广53164行、allocated NNZ24730144、factor NNZ53417584 |
| 物理输出与比较 | 无新R/T/A、A_volume、R00_s/p/total、衍射级、复E/H或full solve资格；无p/h/M/MPI/Hybrid扫描、非可分或短波资格 |
| 后续范围 | 数学根因仍未完成；唯一优先是补存同一失败p4输入，核对增广系统与原A4残差差别/可靠性，再补缺失表示与响应诊断；本轮不重跑或精化 |

这是在同一真实方程上比较三个既有PC的有界诊断。PC为外层求解提供近似修正；本轮保存相同残差输入q及其修正z、原A作用Az，用`rho=norm(q−Az)/norm(q)`看一次修正消掉多少残差。rho越接近1，单次减少越少；这不是实际场误差，也不能直接预测完整FGMRES轨迹。M0最佳投影原本要把“p4表达不了的误差”和“虽能表达但修正不准”分开，需要真实有限元质量作用及合格求解；此次未到达该阶段。

## 三次执行事件分别保留

| 事件 | source / root | 结果 |
|---|---|---|
| 原strict诊断 | 24b3dbb67540a4cc2ec3e70ba381ab8a3e41d650；v3_d1d3_no_reference下同SHA/mpi1 | TIMEBASE_INCONSISTENCY，0完整PC；旧raw、初始launch及缺失worker终态的结论保持 |
| 工程修复后启动失败 | bf8e0c1d16c9c86677e866cdf29fd5491f076e32；v3_d1d3_no_reference_v2下同SHA/mpi1 | ABI预检导入MPI的orted子进程违反干净父进程前提；worker未启动，LAUNCH_OR_FINALIZATION_FAILED，0.995213941 s扣账 |
| fresh attempt2 | 同bf8e0c1；同目录attempt2/mpi1 | ABI在独立子进程完成退出后启动；7完整PC与第8次数值拒绝，终态齐全，无重复heavy |

用户明确授权继续修复非数值/非资源工程阻碍，因而在同分支恢复一次诊断；没有改写旧review或给旧strict运行补PASS。`conservative_realtime` version1仅由诊断显式启用，strict仍为默认。UTC可调整，所以新政策保留三时钟原值、记录UTC相对增量，逐相邻采样累计`max(Δmonotonic,ΔBOOTTIME,ΔUTC,0)`，向前跳计费、回拨不退款。单调缺失/非有限/倒退或彼此超过原max(5s,1%)仍保护，UTC不放大阈值。A6、物理、三个PC、数值门槛、动态内存/4GiB余量/swap0均未改。

本次watchdog UTC正向额外增量79.446333729 s已扣账，独立从3324条raw复算费用945.519546580 s一致；不能称strict UTC一致性通过或精确系统时钟因果已查清。Windows Stopwatch独立对照因当前Interop socket失败未启动，没有安装或改系统。外层按不重叠pre/watchdog/post收费，未把PC时间再次加到父账本。原14:44:51+08四小时锚点继续扣账，attempt2启动前8759.911903548 s，正式额度5640.088096452 s；含旧诊断及false-start的诊断额度也先扣除。审计采样时总账9865.346017767 s、余4534.653982233 s；后续只读收口继续消耗时间，该历史余额不授权新求解，未重置四小时。

## 身份复现与相消

| 样本 | fresh相对真残差 | 与旧值绝对差 | 三个分项范数和/合成向量范数 |
|---|---:|---:|---:|
| A2R160 | 0.18250767622880479 | 2.7755576e-16 | 373.034048737 |
| LIGHT448 | 0.098145911603049502 | 1.110223e-16 | 378.722372633 |
| JOINT448 | 0.10713326900483634 | 2.0816682e-16 | 298.080962745 |

从保存的b、x、Ax、r与分项向量独立复算：x与历史快照的native独立系数逐位一致，r=b−Ax逐位一致，分项相加与Ax一致，Gram复内积矩阵差为0。相消比约298–379意味着此三场上curl项与负质量项都较大而相互抵消；它依赖系数范数及这些样本，不是完整条件数、最小奇异值、近共振或粗离散色散测量。

## 七次同输入PC响应与成本

| 输入 | PC | rho（独立重算） | raw monotonic（s） | raw UTC（s） |
|---|---|---:|---:|---:|
| A2R160 | S6 | 0.999949824758905 | 22.316357739 | 25.259098050 |
| A2R160 | LIGHT | 0.944132338863247 | 10.029635178 | 10.029636242 |
| A2R160 | JOINT | 0.937065421422212 | 12.176587570 | 15.097589135 |
| LIGHT448 | S6 | 0.993946941622935 | 21.269595479 | 24.232399971 |
| LIGHT448 | LIGHT | 0.999263262751356 | 10.626360492 | 10.626362126 |
| LIGHT448 | JOINT | 0.999011783054599 | 11.203418100 | 11.203417756 |
| JOINT448 | S6 | 0.99922531805235 | 22.966341863 | 22.966342813 |

每个q均与保存实际r除以其Euclidean范数逐位一致，rho从保存q/Az重算匹配，累计packet计数恰为1–7。各PC的时间是其起止raw区间，不是已消除UTC调整的精确成本；正式预算以父进程逐采样累计为准。A2R160上LIGHT/JOINT比S6单次效果较好；LIGHT448上三个方向都只带来很小改善。不能用7个样本推断固定线性PC谱，或宣布某方法在全部FGMRES输入上失效。保存的M0修正能量有hash绑定，但未保存M0z，本次只读未重新执行质量作用，不能称该能量已独立重算；真实remaining-field-error仍无参考。

## 第8次原A4拒绝的准确含义

| 核查项 | 证据与结论 |
|---|---|
| 精确失败位置 | JOINT448→LIGHT，positive_pre后physical_middle；LIGHT桥calls_started3/completed2，S6为3/3、JOINT为2/2 |
| 标量残差 | 原A4作用后差向量范数1.166232072202645e-10；p4 RHS范数1.1561769354407092；相除1.0086968840613509e-10>1e-10 |
| 前7次p4 | 最大6.0667549382889e-11≤1e-10；第8次不计为完成，不因仅超0.8696884%改PASS |
| 输入/归一化 | fine dual r仅归一化一次；原H6/MR后残差经原P^H形成p4 RHS；分母为该p4 RHS范数，非fine归一化前/后范数，tiny floor未激活 |
| 别名/约束路径 | PC residual/correction、限制输出、增广b/x、提取solution及A4 applied均有独立存储；原finite/slave-zero检查执行到残差阶段；首个成功bridge输入不变和输出slave-zero检查通过 |
| 源码身份 | reference、PC组合、runtime/transfer、MUMPS包装、physical action、H6 setup六文件与旧F3 source60b8df2a24cbcd96e49e018be22fb64f06eeae3f逐字节相同 |
| 证据限制 | 失败p4 RHS/solution/residual向量未持久化；代码路径和标量比值核对不等于独立A4重算，也不是失败调用的完整运行时alias追踪 |
| 因果边界 | 所审路径未发现可唯一归因的工程错误；保留数值Gate miss，不宣称病态、舍入或增广映射是唯一根因；这个0.87% miss不是历史约0.1外层停滞的因果证明 |

共享p4数值前提在该输入未闭合，按主任务裁决不追加refinement、不放宽Gate、不重跑，不启动条件D4。D2仍为缺可信完整MPI1峰值上界的安全预审未资格化；未构建fine参考，不能据此证明16GB普遍不可能。资源方面，本次实测峰值低于本机8.367GB安全cap且保留4GiB余量，但明显不能据此授予2GB资格，更不代表0.7nm容量结果。

## 原因矩阵与唯一后续对象

| 原因类别 | 状态 | 支持与限制 |
|---|---|---|
| 输入、作用、尺度与参考 | MIXED | 三份x与历史独立系数逐位一致，r=b−Ax、原A分项和及历史残差均复现；失败p4向量未存，不能独立复算其A4作用，未发现所审接线错误。 |
| p4空间表示不足 | UNRESOLVED | 没有已知误差或合格M0最佳投影，η_space未测；不能由较弱残差收缩或p4 Gate miss推断空间不足。 |
| 实际粗响应/投影失配 | UNRESOLVED | η_G、coarse identity、表示/响应误差分解未运行；相消比298–379仅提示三个场上的大项抵消，不是条件数或色散/共振证据。 |
| fine互补能力不足 | UNRESOLVED | e_perp尚未取得，独立H6/S6互补0次；完整PC的单次残差比例不能替代该项。 |
| 局部逆精度与全局耦合 | MIXED | 本次p4前7次≤1e-10，第8次1.0086968840613509e-10拒绝；精度前提在该输入未闭合。0.8696884%越限不是历史约0.1外层停滞的因果证明，也不证明所有p4作用失效。 |
| 已测样本单次PC改善较弱 | SUPPORTED | 七份同输入q/Az已独立复算：LIGHT448三种rho为0.993947/0.999263/0.999012，JOINT448的S6为0.999225；仅限这些dual输入，不构成FGMRES或field-error定理。 |
| restart/非正规影响 | UNRESOLVED | 仍缺足够Hessenberg/正交性数据；原有reported/explicit差很小只削弱monitor漂移解释，不确认restart或非正规唯一原因。 |
| 实现成本、容量、时钟 | MIXED | 新政策已运行并独立复算保守扣账，纯UTC偏移未再阻断；不是strict UTC一致性通过。3324样本RSS峰3.777GB<8.367GB cap、swap0；不代表2GB或短波容量资格，系统时钟原因仍未定。 |

唯一优先后续对象是**同一失败p4输入上的参考逆可靠性**：先有界重建并保存JOINT448→LIGHT的那个p4 RHS（当前没有该文件），在冻结输入上同时保存增强系统求解残差、原A4残差和映射/范数身份，查清二者差别能否解释该Gate miss；未解决前不把准确参考逆当无条件前提。此对象复用原空间、原A和既有factor，不引入增长型全局方向库；代价是一次有界setup与少量同输入作用，仍受原资源/时间Gate。该前提闭合后再补已知误差、M0投影及粗响应/互补的缺失证据；七份已资格数据继续复用。本轮不执行这些后续操作，不据现有证据跳到新PC、p5或PML，也没有h/波长缩小时的成本或任意三维生产保证。

## 验证、交付与依赖组

工程修复唯一合并focused批次19 passed（5.50 s），ABI及编译/diff通过；Windows对照失败单独保留。最终D5只作一批JSON/hash/链接/表格/历史保护检查，无新pytest、代码或PDE，无CI声明。指标独立复核入口为ignored `diagnostic_audit.json`与`reference_gate_readonly_review.json`，详细路径/hash见[中心JSON](records/nonconvergence_diagnosis_v3.json)。

| selective merge依赖组 | 最终建议与证据 |
|---|---|
| production numerical/core | 旧A/PC定义未改，不提升研究默认；原物理验收仍未通过 |
| reusable runner/watchdog | strict默认+诊断opt-in计费与terminal接线；19小测试和fresh费用/清场支持；先审通用依赖，不称strict UTC一致 |
| checker/benchmark | 复用既有packet接口；3identity/7PC的数组和hash独立核对，失败p4 raw缺口保留；依赖对应研究接口 |
| compact evidence/docs | 本次8文件及旧负记录可保留；证据区分TIMEBASE、启动失败和数值拒绝，随后审文档 |
| research-only | 诊断runner/metric/projection/PC probe；真实7probe部分资格，known/projection/complement未运行，不提升production |
| do-not-merge | 大型raw/cache/矩阵/场及未资格化默认提升均不入Git；无master merge授权 |

## 历史：首次D5收口及此前D0设计

以下保留原时刻的结论，“当前、0次、未启动、等待”等只指相应历史阶段；最新执行状态与后续优先项以上文为准。

# 不收敛诊断 V3：D5 证据收口，数学定位未完成

后续用户已明确授权修复工程阻碍并恢复诊断：新增仅诊断显式启用的`conservative_realtime`政策（version 1），原`strict`默认和本页旧TIMEBASE停止证据不变。UTC是可调整的日历时钟；为避免其单独跳变反复中止数学测量，新政策保存三时钟原值和UTC相对增量，逐相邻区间累计`max(Δmonotonic, ΔBOOTTIME, ΔUTC, 0)`，前跳扣账、回拨不退款，不宣称strict一致性通过。两种单调时钟缺失、非有限、倒退或彼此超原阈值仍保护；UTC不放大该阈值，A6、物理、三个PC、数值Gate、动态内存/4GiB余量/swap0均不变。父watchdog累计值是整体预算权威，外层另加不重叠pre/post；PC单次endpoint仍只是raw区间，不称精确UTC成本。原四小时账本继续扣除准备、失败和测试，不重置余额。终态落盘保留监督原分类，收尾异常不能冒称成功。Windows Stopwatch只读对照因当前Interop报`UtilBindVsockAnyPort: socket failed`未启动，不安装或扩展环境调查；合并focused tests为19 passed（5.50 s），日志`benchmarks/artifacts/task39extra/v3_clock_policy/focused_tests.log`，SHA256 `14e7553168ff8fdb3a0a171b2b947df16151f4c9f378c18ddf32bdc9f32d3c73`。本段是工程修复记录，尚未提交或恢复heavy；以下为a8ca702收口时的历史状态。

| 当前项目 | 实际结果与边界 |
|---|---|
| 正式源码 | `24b3dbb67540a4cc2ec3e70ba381ab8a3e41d650`，task39extra，启动前clean；原Task base `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee` |
| 本轮模型/用途 | 原始13.5nm、1°、s、Full3D p6/h10、MPI1、线程1、80 DtN modes；唯一D1/D3无参考诊断启动，不是新的R3完整求解 |
| 终止 | `TIMEBASE_INCONSISTENCY`；最后阶段`s6_transfer_cycles_started`；watchdog摘要为终止权威 |
| 已完成 | D0文件/配置盘点、小接口测试；S6内p6作用与对角、p3/p1装配、p1 symbolic/numeric setup |
| 未运行 | fine原A身份/残差复现、canonical资格、p4 factor、已知误差、M0投影、粗响应及互补诊断；完整PC探测0、独立互补0、投影0；D4 not_run |
| 数值/物理资格 | 没有新solver PASS/FAIL；R/T/A、A_volume、R00_s/p/total、衍射级、复E/H均not_run；历史未收敛结论保持 |
| 资源 | 245次同期进程树RSS采样峰639950848 B；动态启动cap8417038336 B、reserve4294967296 B；最低effective available12219453440 B；树swap最大0、资源违规0 |
| 清场 | parent969901和六个已观测后代均不存在；leader exit−9、parent exit1；global pswpin/out增量均0 |
| D5范围 | 只读证据与文档闭环；代码冻结、无重试、无系统/时钟改动、无新PC或heavy |

此诊断原本要把“粗空间能表达的误差”和“修正实际消掉的误差”分开，避免因某种PC失败就猜下一种方法。PC是为外层求解提供近似修正的辅助步骤；M0投影通过真实有限元场能量寻找p4可表达的最佳部分，需要额外质量方程求解和精度检查。本次在这些测量前被时钟保护停止，因此不能给出数学根因或新算法选择。

## 时间证据与终止一致性

| 同一区间 | monotonic / BOOTTIME / UTC（s） | 解释 |
|---|---|---|
| 首次违反Gate | 61.410906241 / 61.410906659 / 67.359115896 | 差5.948209655>容差5；保持max(5s,1% interval)原规则 |
| watchdog完整区间 | 62.736509435 / 62.736509163 / 68.684718348 | 原始时钟分别保留，不混成可信wall |
| 外层CLI区间 | 64.532228366 / 64.532230605 / 70.480439729 | watchdog返回后cache收尾的interval检查再次报错 |
| 相邻样本113 | 0.256313902 / 0.256313889 / 3.284363831 | UTC相对额外3.028049929 s；p3装配期间 |
| 相邻样本239 | 0.256923946 / 0.256924245 / 3.177083595 | UTC相对额外2.920159649 s；transfer cycles阶段 |

245个样本形成244个相邻区间：2次离散UTC相对跳变、242个普通区间；普通区间UTC与monotonic差绝对值最大2.34702e-6 s，monotonic与BOOTTIME差最大2.58605e-6 s。worker自身阶段区间也留下第一次约3.028 s偏移。这里观测到离散跳变，不是这批样本持续均匀速率漂移；系统原因仍`UNRESOLVED`。

已保存只读检查未发现父/子时钟混减、秒与纳秒混算或Python时钟函数重赋值。当前clocksource为tsc，当前进程内time函数是内建函数；这只是补充采样，不能替代已终止进程的完整追踪。`timesync_status.txt`在2026-09-08 16:17:08 CST记录`NTP=yes、NTPSynchronized=no`，不能称已同步。限定运行时间的timesync journal无条目；启动参数隐式Hyper-V同步、9月4日TSC调整与早前journald倒退只是历史线索，不能归因9月8日这两次跳变。没有进一步调查或修改系统。

watchdog在monotonic569672.854667733、UTC ns1788854894845545752记录停止并硬停完整后代树。worker被终止，`diagnostic_summary.json`缺失，worker.log为空；外层在返回后再次触发时间检查，故`launch.json`只保留初始manifest。三者不是三个相互替代的最终状态：以watchdog summary和原始采样确定终止，派生audit解释缺口，绝不补写/覆盖raw。

批次上限14400 s；从Review V3提交时刻14:44:51+08保守扣账，启动前已计4936 s，包含准备、失败及测试，正式只给min(7200,剩余额度)。termination audit时外部时间累计5190.29133 s；这是有时间限制的历史采样，不能当最终精确wall。停止并非4小时预算耗尽，余额不授权重试。首次可选psutil导入失败发生在正式启动前，保留preflight_attempt1；改用已有stdlib /proc完成预检，没有安装依赖。

## D2参考容量结论

11份非测试run_manifest中无匹配已解full-p6场。旧Task37同p6/h10但10°/MPI8：同期树RSS15.059223175 GiB；209772680个factor非零元仅复数负载3356362880 B，allocated CSR推导852715492 B。这两项之和不是MPI1全生命周期峰值上界，尚缺fill/pivot、工作区和装配/恢复同时存活量。`REFERENCE_UNAVAILABLE_ON_16GB`只表示本轮安全合同下该路径未资格化；direct assembly/symbolic/numeric均not_run，不能证明16GB普遍无法求参考。

## 原因矩阵

| 待检验解释 | 状态 | 支持、反证与置信边界 |
|---|---|---|
| 输入/作用/尺度或参考 | UNRESOLVED | 五份文件身份核验通过，80-mode配置重读匹配；fresh canonical映射、原A作用和r=b-Ax重算未到达。primal场与dual残差角色已分开，不能据文件hash宣称算子资格。 |
| p4空间表示能力 | UNRESOLVED | 没有合格参考误差或实际M0最佳投影；η_space未测，不能证明p4遗漏了多少误差。 |
| 实际粗响应/投影 | UNRESOLVED | 旧LIGHT中间MR系数模中位0.0552983、563/582个未缩放方向使残差增大；尚无η_G、coarse identity或误差分解，不能归因为色散/共振。 |
| fine互补处理 | UNRESOLVED | 已知误差与e_perp未构建，独立H6/S6作用0次；没有互补能力结论。 |
| 准确局部逆足以保证完整收敛 | NOT_SUPPORTED_ON_TESTED_SAMPLES | 旧LIGHT/JOINT的p4最大backward residual分别7.05816e-11/7.87060e-11≤1e-10，fine残差仍0.0791360/0.1053582>1e-6；不等于证明forward correction精确，也未诊断未来DD。 |
| 局部联合收益保证全局改善 | NOT_SUPPORTED_ON_TESTED_SAMPLES | 旧joint/seq局部残差比中位0.9794794，14共同步中11步JOINT更差、3步更好；各自Krylov输入不同，不能推导同输入因果。 |
| restart/非正规影响 | UNRESOLVED | 缺少足够Hessenberg/正交性数据；65个旧monitor的reported/explicit最大差6.58917e-14，不支持monitor漂移解释约0.1残差，但不能排除所有实现问题。 |
| 实现成本/容量/时钟 | MIXED | 旧完整PC成本是实际限制；本轮TIMEBASE_INCONSISTENCY实测成立，系统根因未定位。RSS639950848 B<cap8417038336 B、swap0，不支持本次因内存触顶停止；D2缺完整MPI1峰值上界。 |

## 历史同一步曲线与成本（derived，不是fresh同输入实验）

下表为原始cycles离线读出，相对真残差无量纲，正式阈值1e-6。共同step不意味着共同误差或PC输入；不能仅由这些曲线证明restart因果。

| step | LIGHT | JOINT |
|---:|---:|---:|
| 32 | 0.442569421212451 | 0.506958215778298 |
| 64 | 0.412734994686349 | 0.412032506033339 |
| 96 | 0.328567997800525 | 0.36741510375884 |
| 128 | 0.280142764887768 | 0.321125895767315 |
| 160 | 0.240263477311882 | 0.267343662346305 |
| 192 | 0.22093647978683 | 0.239948396124944 |
| 224 | 0.18261021521683 | 0.190304468787501 |
| 256 | 0.157526623955088 | 0.152316913777565 |
| 288 | 0.141943918514062 | 0.13933890332556 |
| 320 | 0.126673635511641 | 0.132716309473393 |
| 352 | 0.120588201602656 | 0.122245354647888 |
| 384 | 0.113626856820043 | 0.11670482210432 |
| 416 | 0.106600203133506 | 0.111698206944368 |
| 448 | 0.0981459116030494 | 0.107133269004837 |

第448步累计cycle monotonic为5598.169199291/6374.491841535 s（LIGHT/JOINT），不是完整workflow，也未消除旧时钟限制。LIGHT最后安全576步残差0.0791360407785889；JOINT476步0.10535820013809101。旧LIGHT完整PC中位10.293892394 s；JOINT11.460344589 s，额外A作用累计694.874209920 s、QR5.928539213 s。旧packed S6配对中位比0.938459327>0.75速度Gate，作用等价不等于提速合格。以上保留原测量边界，不将本次离散跳变原因倒推到旧运行。

唯一下一优先项是恢复可解释的时间资格，然后补齐冻结同输入诊断最小证据：原A/映射与三个旧残差复现，再做预定已知误差和三个旧PC的有限调用。收益是让原因可判，代价是既定setup和有界探测；仍需动态内存/4GiB余量/swap0。尚无依据提出新数学PC，更不能承诺随h或波长缩小的成本、非可分三维或0.7nm资格；本轮不执行该后续项。

## 验证、证据与依赖分组

V3已有tiny/代数/微型FE批次依次6、7、8、8 passed，后两次窄修分别1与2 passed，短检查累计预算13.183744896 s。它们验证接口，不代表原尺寸诊断完成。ABI为资格化activation、仓库.venv、PETSc3.19.6 complex128/int32、SLEPc3.19.2、DOLFINx0.10.0.post2、MPI1/线程1。编译与diff检查已通过；D5只作JSON、链接、hash和文档检查，不再pytest/PDE、无CI声明。

| 依赖组 | 数值行为/依赖 | 测试、fresh证据与建议顺序 |
|---|---|---|
| production numerical/core | 不提升新默认；原A/旧PC定义保持 | 旧资格按来源保留；新接口没有fresh完整资格，不单独宣称production通过 |
| reusable runner/watchdog | workflow_timebase与subreaper时钟保护，默认关闭 | tiny通过，fresh保护停止/清场；外层最终manifest缺失限制保留；先审通用依赖 |
| checker/benchmark | probe packet依赖metric/runner，复用已有向量 | 微型packet读回通过，原尺寸packet未产生；随研究接口审阅 |
| compact evidence/docs | 本次中心JSON、八份文档/索引与旧证据入口 | hash/JSON/链接检查；可独立保留负结果，随后审文档 |
| research-only | physical_diagnosis/worker、physical_error_metric/diagnostics及相关接线 | tiny通过、fresh探测0；保持研究用途，依赖现有A/transfer/p4/PC |
| do-not-merge | 大型raw、cache、矩阵/field和未资格化默认提升 | raw留ignored；无master merge授权 |

完整命令、raw路径、环境、source与artifact hash见[中心JSON](records/nonconvergence_diagnosis_v3.json)，运行根为`benchmarks/artifacts/task39extra/v3_d1d3_no_reference/24b3dbb67540a4cc2ec3e70ba381ab8a3e41d650/mpi1`。终止audit SHA256为`d4ae363508b6d2b67fdffe9dceea6882f6adcb1e74a4d32ec3dda53bbe879a8a`。

## 历史：正式运行前的D0设计与验证快照

以下“当前、待审、尚未执行”仅指提交24b3dbb之前；实际执行及D5结论以上文为准，保留历史计划而不重新授权运行。

# 不收敛诊断 V3：D0 盘点与待审执行设计

当前状态：D0 文件身份盘点、双时钟 tiny 验证、D1-D3 最小数值接口和参考容量预审完成；原始尺寸 canonical/Floquet 重建、原 A 作用、参考求解、投影和 PC 诊断均为 `not_run`。本页不代表 D0-D5 已完成。源码 HEAD 为 `97e82eeb08b6c2faef6457356cdc643832a75eb8`，当前改动未提交，正式诊断需使用随后审阅的 clean source。

## 已读取的证据

| 样本 | 角色 | 历史显式真残差（无量纲） | 本次文件核验 |
|---|---|---:|---|
| A2R160 | 默认 S6 路线 checkpoint | 0.18250767622880507 | 通过 |
| LIGHT448 | 默认顺序 LIGHT checkpoint | 0.09814591160304939 | 通过 |
| JOINT448 | 默认联合接受 checkpoint | 0.10713326900483655 | 通过 |
| LIGHT576 | 仅离线终点补充 | 0.0791360407785889 | 通过 |
| JOINT476 | 仅离线终点补充 | 0.10535820013809101 | 通过 |

“通过”仅指读取实际 solution、manifest、dat、resolved_config 和 source 文件后核对 SHA256、大小、shape、complex128、finite、MPI1、solution-only 角色及物理身份。表中残差为旧记录，本轮未重算。五个向量均为 173802 个系数；历史 setup 标记其中 9210 个为 Floquet 从属行、164592 个为独立行。对应文件完整路径与 hash 见 [结构化盘点](records/nonconvergence_diagnosis_v3.json)。

共同物理 SHA 为 `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`，setup 中 mode SHA 均为 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。已对 T3 v2 实存 mode_manifest 文件计算 hash 并匹配五份 setup；尚未重建当前模式。三个来源源码不同，operator hash 的定义包含 source SHA、physical、modes 和 volume quadrature；不能仅由 hash 不同判物理算子不同。

原 checkpoint 未附 canonical 映射，不能仅凭向量长度直接宣称映射资格通过。下一块须用原网格/同 ABI 重建独立行、orientation 与 Floquet 关系，核对实际系数排序和原积分，再重算 `r=b-Ax`。共享数值文件的源码比较是线索，不代替作用验证；不匹配的样本隔离。x 是电场的有限元系数（primal），r 是方程残差（dual）；本轮没有把 r 当电场能量。

## 参考解盘点与安全路线

| 搜索对象 | 实际发现 | 结论 |
|---|---|---|
| results 与 benchmark artifact 的非 test/tmp run_manifest | 11 份，已逐份保存索引和 hash | 未发现可复用的合格同模型 full-p6 已解场 |
| Task038 T3 formal v1/v2、p6-h10 MPI1 record | 同物理、80 modes；保存 source/action/reference_action/recovery | reference_action 是算子对比结果，不是物理解 |
| Task038 T5 authority | 保存 RHS/canonical 对比且有旧 dual extractor 不合格记录 | 不能提升为已解参考或直接借用旧 dual 映射 |

盘点结论为 `NO_MATCHED_SOLVED_FINE_REFERENCE_IN_INSPECTED_INDEXES`。随后的容量预审见下表；不声称 16GB 上普遍无法求参考。

| 容量依据 | 数值与口径 | 对本轮的含义 |
|---|---|---|
| Task37 direct authority v2 | p6/h10，252 cells，10°、MPI8，51272 augmented rows | 阶次/网格规模相同，但角度、MPI、源码不同，不是当前场参考 |
| 原始同期 process-tree RSS | 15.059223175 GiB | 高于当前 cap；不能除以8当作 MPI1峰值 |
| 历史 factor NNZ | 209772680；仅 complex128 数值负载推导3356362880 B | 不含索引、工作区和分解临时峰值，不是 factor RSS 上界 |
| 历史 allocated matrix NNZ | 42625520；int32/complex128 CSR 推导852715492 B | 不含 PETSc/allocator 额外存活对象 |
| 本次只读 memory envelope | MemAvailable12735438848 B，reserve4294967296 B，cap8440471552 B | 启动时仍须重读动态值 |
| 安全结论 | MPI1 fill/pivoting、assembly/recovery 生命周期和额外工作区无可信峰值上界 | `REFERENCE_UNAVAILABLE_ON_16GB`，仅指本轮所审路径在该安全合同下不可资格化；不启动 assembly/symbolic/numeric |

完整旧记录路径、hash、未知量与本次 envelope 已写入中心 JSON。没有用存储下界冒充整体预测，没有把旧 MPI8 峰值当当前 MPI1 实测。此预审后优先走无参考路线：三个真实 residual 各调用三个旧 PC 一次，已知误差另作 field-error 诊断，避免容量研究拖延原因定位。

待审路线：从原 dat 派生一次显式 Full3D direct reference 输入，走现有 `scripts/run_case.py`、`src/runners/task038_full3d_direct.py` 与现成凝聚能力。凝聚是先消去单元内部未知量以减少全局分解行数，代价是保存局部恢复数据；不得新造求解器。先读已有同阶资源记录，分列矩阵/局部恢复/因子/工作区的同时存活内存；无可信上界时不进入 numeric。assembly 与 symbolic 分级受 watchdog 约束，symbolic 估计连同当前 RSS、临时量及不确定性必须低于动态 cap，否则停止。预算最多 3600s，系统余量 max(4GiB,15%)、cap≤12e9 B、树 swap=0。此处尚未完成安全资格化或启动 assembly/symbolic/numeric。

若允许一次求解，恢复 full p6 后用原 A 检查残差≤1e-10，并在三个预定合法向量（两种不同周期谐波分量及其和）上比较原/参考作用。至多一次同 factor 残差修正，记录场范数/固定采样点稳定性与 `Ae-r`；只有参考不确定性远小于待测误差才形成三份 `REFERENCE_ESTIMATED_ERROR`。随后释放 direct 矩阵和 factor，再建 PC 栈。不能安全完成时按 review 保留 `REFERENCE_UNAVAILABLE_ON_16GB`，继续已知误差与残差诊断。

## 最小 D1-D3 接口（已实现，原始尺寸尚未运行）

| 接口/复用位置 | 问题、输出与限制 |
|---|---|
| `component_diagnostics(action, x)`；复用 `fullspace_physical_action` | 返回 Kx、负质量项、边界项范数与复内积，查大项抵消；不推断完整条件数或谱 |
| `LosslessFEMetric` / `cell_energies`；`physical_error_metric.py` | 用实际无损 FE L2 质量 M0 测电场大小，以缩放 curl 测变化；独立约束空间和原积分，从属 identity 行不计能量；输出 cell 积分及材料/坐标标签供分区汇总 |
| `project_error(P, M0, e)`；同一小模块 | 仅一次固定对角 CG 解 p4 质量方程，rtol1e-10/max256；输出最佳可表示部分、剩余部分、正交与 Pythagorean 缺陷；不闭合则 `PROJECTION_UNRESOLVED` |
| `coarse_diagnostics`、`evaluate_profiles`、`evaluate_residual_profiles`、`homogeneity_check` | 复用原 transfer、p4 solve 和三个 PC；返回单位 coarse/MR coarse、coarse identity、互补应答、场误差或真实 residual 收缩；无参考时 remaining-field-error 明确 unavailable |
| `DiagnosticActions` / `supervise_diagnosis`；`physical_diagnosis.py` | 借用一个 S6/A6/P64/p4 栈，另建原 LIGHT H6，三个 PC 共享 p4 factor；桥接立即复制借用缓冲；父进程 diagnosis/reference 两路径均显式 `timebase_guard=True` |

预定已知误差的解析式已在 JSON 冻结：令 u、v、t 为 x、y、z 的归一化坐标，用横向 Floquet 因子乘 `sin(pi*t)`，内部为向量 a 乘 `(u+v)` 谐波，加向量 b 乘 `sin(2*pi*t)` 与 `(2u-v)` 谐波；a=(1,i,1+i)，b=(1-i,2,-i)。两组不同横向谐波和 z 依赖使其不是单个可分乘积，三个分量均非零。经合法 p6 Nedelec 插值和约束后得到 e_test，使用真实全模型 q=Ae_test；按 norm(q) 同比缩放 e、q，冻结后不根据 PC 结果选更容易的样本。此控制不等于非可分材料 full solve。

| 调用计划 | 默认数/最大数 | 时间约束 |
|---|---|---|
| 样本 | 有参考时三份实际误差+一份已知误差；无参考仍测三份实际 dual residual，仅已知误差解释 remaining-field-error | D1/D3 合计≤7200s |
| 三完整 PC | 每样本各一次；最多4×3=12；已知误差同比缩放复查再3次 | 默认最多15，硬上限36；不为用完预算追加 |
| H6/S6 互补 | 本次无参考路线仅已知误差：各一次+同比各一次 | 默认4，投影不闭合则跳过；不补满硬上限18 |
| M0 投影 | 本次仅已知误差一次 | 累计≤1800s，计入 D3 |
| 可选 fine reference | 一次 | workflow≤3600s |
| D4（本块不做） | 仅原因证据需要时≤4个小特征问题 | ≤900s |

p4 backward residual≤1e-10 不自动证明 forward correction 精确。投影闭合且 dG 属于 range(P) 时，复用已有向量计算 `norm(e-dG)^2 ≈ norm(e_perp)^2 + norm(e_parallel-dG)^2`（均为 M0 范数），不增加 p4 solve。这把空间无法表示的部分与粗修正偏离最佳表示的部分分开。再用 coarse identity control 检查实现/近似逆；通过后也不能立即把误差归因于色散或共振。

最终四类原因分别处理：①粗空间表示能力；②实际粗响应/传递与求逆；③细层对互补误差的作用；④实现成本、时钟与 restart 证据。每类允许 `SUPPORTED`、`NOT_SUPPORTED_ON_TESTED_SAMPLES`、`UNRESOLVED` 或 `MIXED`。没有 Hessenberg/正交性记录时，曲线拐点不能证明 restart 因果。最多提出一个由证据支持的后续改动，不在本轮执行新 PC。

## 本块验证与边界

新增时钟 helper 和 parent/worker 接线，保持默认关闭；启用后同边界保存 monotonic、BOOTTIME、UTC、clock_info。预算用两种单调时钟较大值；未知差异超过 max(5s,1% interval) 保存 `TIMEBASE_INCONSISTENCY` 并停止，用户停止与资源硬门仍优先。没有改写旧 raw 或解释旧差异原因。

轻量 ABI preflight 通过；6 个 focused tests 通过，pytest 4.37s，外层双时钟预算 4.544520168s，UTC 间隔 4.544520362s。覆盖容差、缺少 BOOTTIME、倒退、worker 写入后报错、父进程两种停止与清场及旧生命周期相关路径。日志位于 `benchmarks/artifacts/task39extra/v3_d0_clock/tiny_tests.log`；未运行 181/全仓/MPI sweep/PDE。

D0 metadata 脚本第一次直接从 /tmp 执行因 `src` 不在模块路径而失败（0.237s 命令记录），未加载模型；改为仓库入口后读取成功（脚本双时钟 0.122330350s）。该失败保留，不作为环境或算法失败。V3 上限14400s，当前已测 tests+D0 成功部分约4.667s，另保守计该失败1s；尚不把它称全阶段完整 wall。后续正式执行必须连续扣账，包含失败/构建/释放。

第二块实际测试：先7 passed（2.00s，双时钟2.276431524s）；追加预定已知误差插值/同比检查和投影累计预算接线后，最终8 passed（1.15s，双时钟1.720125310s），无失败。测试只包含新代数/18-cell p2 FE及两项 finally 时钟分类回归；没有原始 p6/h10 PDE。日志为同目录 `diagnostic_tests_1.log`、`diagnostic_tests_2.log`；中心 JSON 保存命令、clock、hash 和当前实现文件 hash。编译/diff 检查通过。

细节修正：finally 在 workflow 超时或已有 stop_signal 时不再覆盖 `TIMEBASE_INCONSISTENCY`。`DiagnosticActions.project` 将固定对角构建及每样本唯一 CG 纳入共同1800s；用尽即 `PROJECTION_UNRESOLVED`，不启动另一种投影。粗误差分解复用 dG 与已有投影向量，不为分解新增 p4 solve。

固定薄入口现已实现：`python -m src.runners.physical_diagnosis`。在一个 clean-SHA MPI1 worker 内读取中心样本、按原 dat 构造同 mesh/ABI/order，保存 p6/p4 native constraint map、canonical mesh witness与metric hash；核对原 operator hash、三个历史残差和 component sum 后，逐次落盘真实 r 的9个PC结果，再执行已知误差3个PC与3个同比检查。投影和粗作用仅作用于已知误差；先测一次原始 p6/p4 M0 Galerkin关系。投影超时/不闭合只锁定相关结论，三个实际残差探测已先完成。共享一次S6/p4栈，独立互补默认4次；无长外层FGMRES或新PC。

入口固定 `timebase_guard=True`，工作流≤7200s、树swap0和动态cap。D2因安全预审不通过不启动。既有cache可通过 `--cache-path` 复用，启动/结束记录逐文件hash和本次ABI；没有新增cache平台。每个完成probe立即保存ignored JSON/NPZ、hash、时钟成本和完成计数。首调用实测输入不变及输出slave-zero，不通过就停止；不是先丢弃slave再宣布合法。所有已有 z/Az、normalized q/e 与尺度、原误差/单位剩余/MR剩余 M0 能量均保存，可离线复算ratio；同比probe保存已有scaled correction，无新增A作用。

端口接线已按真实内存类型修正：`beta` 为 complex，排序直接取其模。一次无网格的原始配置读取得到80 modes且hash匹配；选定incident之外的三个branch为bottom(0,0)、bottom(-1,-1)、bottom(-1,1)。完整mode manifest按原编码保存，packet中也保留复数k分量，不用绝对值替代物理定义。

最后验证：入口整合后同一8项小批次通过（1.52s），复数packet/hash读回通过；beta修复与bridge首调用检查后，仅复验1个tiny FE检查（0.90s）及80-mode配置读取；最后raw能量/Az字段只复验2个原有代数检查（0.12s）。未扩展回归集合。日志分别为 `diagnostic_tests_3.log`、`bridge_mode_check.log`、`raw_evidence_check.log`。移除了不必要的库路径前缀断言，保留activation、repo解释器、complex128/int32、MPI/线程资格与真实模块路径/version记录。最终编译/diff检查通过。

待主任务提交并批准完整源码SHA后，精确调用模板如下；该命令本块尚未执行，artifact目录必须尚不存在：

```bash
source scripts/activate_myfenics_wsl.sh
export GIT_DIR="$PWD/.git-codex" GIT_WORK_TREE="$PWD"
python -m src.runners.physical_diagnosis \
  --input input/task39extra/original_13p5nm_p6h10_p4_reference.dat \
  --inventory docs/task039_extra_physical_multilevel/outcomes/records/nonconvergence_diagnosis_v3.json \
  --directory benchmarks/artifacts/task39extra/v3_d1d3_no_reference \
  --cache-path "$PWD/results/euv_grazing1_phi0/original_13p5nm_p6h10_light_p4ref_jointmr3_v2__full3d_iterative__mpi1__Mna/20260908T034629.980337Z/jit_cache" \
  --expected-sha APPROVED_FULL_40_CHARACTER_SHA \
  --remaining-seconds 7200
```

上面的7200还须与本轮14400s批次剩余额度取小；不借用V2余额。诊断完成后再只读形成原因矩阵，D4保持条件项。本轮tiny结果不等于原始模型资格。

本块未 commit/push。按主任务要求暂不原始尺寸 action/reference/PC；等待其读取 diff 后进入 clean-source 测量，不启动或续跑旧 R3/F3。
