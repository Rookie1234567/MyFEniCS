# Review V25：先补齐真实验收链，再一次完成全端口 W1

> 最新接续见§8：A纯逻辑修复接受；本机未找到原件。本次明确授权一次同hash输入恢复，成功后连续完成B0/B1及独立检查；局部LU/恢复留给主线，不重复A。§0–7保留各时点证据；§8列明覆盖条款，不新增review编号。

## 0. 裁决与实质推进

**接受 V25 的接入实现和如实保留的未运行结果；不接受它已经具备完整科学验收能力。P0仍为 PARTIAL_NOT_NATIVE_QUALIFIED，P1/P2未运行。下一轮集中修好前置凭据、保存checker和物理坐标／载荷三个缺口，随后在真实原件到位时执行同一固定q60批次。不能只把文件补到目录、重试launcher就进入局部求解。**

本次找到了不依赖缺失manifest也能复现的问题：前置检查接受失败监督留下的通过标签；保存checker未检查实际保存的两个端口作用向量；结果内的NumPy布尔标量不能由当前正式JSON写出。另有坐标相位仅做自身往返、真实入射RHS没有消费链。这些一起修复并通过实际消费者的反例测试，才是下一项推进，不再制造单纯确认收信、查同一批路径或重新封存的批次。

唯一最终目标保持**原50×25×140 nm、Si线宽17 nm／高120 nm、λ0.7 nm、完整三维 FE、全部内部场、双Floquet、全端口**，保留非可分三维几何能力。整机十进制 **2e12 B**，自身swap/OOC0，完整冷准备到独立验收 **≤172800s**。原完整残差≤1e−6，同离散总／散射E、H、尺度化curl、样点与完整复通道≤1e−4，功率／能量≤1e−5，逐级功率≤1e−6；积分／恢复等原组件门不变。缩比、制造态、组件、缓存及文件接收都不能替代终点。

维持 **FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED**；无production或merge approval。当前没有证据支持FEINN承担主求解器。这里继续的是可供原尺寸引擎使用的确定性边界组件，不把其收益计为神经增益。

W1要解决的是“完整衍射端口能否正确接到有限元边界上”，还不是求出整个样品里的场。B把端口振幅转成有限元边界载荷，D把边界场投影回端口，端口H是原归一化分母，不是磁场H。q60是这一步固定的数值积分设置。局部消元先去掉单元内部未知量，再从保留的边界未知量恢复内部场；它可以节省全局求解规模，但必须保留全部耦合和恢复误差。保存checker的作用是从原数组重新检查这些等式，而不是相信worker写下的“通过”。这些检查需要额外积分、数组读写和核验成本，全部计费。

## 1. 精确身份、审计范围与实际出口

| 对象 | 冻结身份／实际状态 |
| --- | --- |
| canonical／分支 | /home/fenics/Projects/NN-Lab-V2／task42extra_feinn_5nm |
| 被审阅HEAD | bf3fa49d771fb2517166748c268328049f175be9 |
| 输入Review V24／base | 07bcd6ae2c9118619b2ee6955e39259cd065a313／fbac3d8777fcfd897d93b898cb9f460f79ddd6ff |
| 受测接入实现 | 357748671d1e8106027c0ee680cfdedb874837ec；不是已运行native源码 |
| 数学依赖 | c354afa449fb80cfb5012e7d2ff66a3e3e64e088；19文件／365726B；manifest SHA f03522011c158254144aa8e5ec7112721b7d48daefd4e6c06da18d250ae3a343 |
| 现场Git | 精确远端／显式tracking同HEAD、0/0、clean；字面upstream正确，解析128保留；共享fetch未改 |

已重新读取规则、任务导航与当前合同，快速刷新4922份tracked文件／112772806 B及标题／定义；这不是全仓逐行语义审计。重点完整审阅新增合同、351行receiver、667行payload、296行数值适配器、全部新增测试、公开入口差量、19文件依赖的相关数学与资源源码、V25全部compact记录及正文；历史训练和场归因复用未改变的已审阅证据，不重新训练或积分旧场。

[独立审计收据](outcomes/records/review_v25_evidence_audit.json)保存脚本、输入／输出hash和反例。71处绑定／40文件全部匹配，19份依赖与精确Git blob一致，20份实现／输入与受测commit逐字相同。独立解析三份JUnit及监督记录：27/0/0/0、49/0/0/0、49/0/0/0；中间49测试通过但Ruff使整个worker失败，未合并成全通过。本审计范围50份旧任务权威页逐字不变，summary完整旧后缀不变；不与执行方另一30文件范围混淆。

V25确实完成单dat显式入口、同一manifest/ledger/q60合同、完整原生列的消费者传参、分块保存和有界窗口设计。它没有创建native worker／ABI回执／native raw，没有取得manifest／ledger／checkpoint，没有局部或全局Maxwell因子／solve、Gram、NN调用。原件18个路径、checkpoint三个路径本次复核仍不存在。**这不是q60数值失败，也不是OOM；缺输入与资源拒绝之外，还存在下节实现缺口。**

## 2. 必须一起修好的科学验收问题

### 2.1 前置资格不能只读取通过标签

[prerequisite](../../src/runners/w1_component_receiver.py)只检查control的cleared与component_status；进入p阶段只检查boundary_check/component_result.json的status和coverage。它没有要求该checker的监督成功、退出0、后代清空，也没有把P0/P1及其原数组绑定到当前同一输入、实现和窗口。

本审阅直接调用**未修改的实际函数**：control设为WORKER_FAILED/exit99但保留通过标签；P1 component保留PASS，P1监督设为RSS_HARD_STOP/exit137/cleared=false并使用不同source。prerequisite("p4_top", …)仍返回，不抛异常。此反例没有启动launcher或FE。真实运行中，component JSON刚保存、后续清场／资源监督失败，就可能出现这种组合，不能依赖“正常情况下不会这样”。

修复须验证同一资格链：原输入字节、模式顺序、适配／数学source文件、q与物理身份、P0/P1原结果及原数组hash、监督分类／exit／清场。不同stage的dat SHA本来不同，不能简单要求所有dat hash相等；使用共同科学身份加各stage本身绑定。无关文档HEAD变化允许按相同受测源码blob复用，不强迫重新跑正确原件。错误／缺失／UNKNOWN／未封存凭据必须在native依赖之前拒绝。

### 2.2 保存checker遗漏实际消费者，且正式写出存在类型错误

[check_local](../../src/runners/w1_component_payload.py)重算部分原方程，却未消费保存的qhat_alpha、affine_internal_rhs来验端口约化作用；它用另外几份修正量重新拼出一个表达式。实际被下游使用的保存向量若错误，这个替代表达式仍可通过。约化trace方程及其消元恒等式也没有完整独立验收；p、side、完整内部／trace分区、原mode key/H及见证身份尚未形成同一保存合同。

为隔离checker本身，本审阅使用小型合成数组，并明确stub了Basix及直接面积分前置；**这是检查器逻辑反例，不是FE数值证据**。未修改的check_local对正常fixture和破坏后的fixture都返回P2_SAVED_LOCAL_PASS。破坏仅将实际保存qhat_alpha与affine_internal_rhs改成原alpha的1e6倍／2e6倍，并生成自洽文件hash；保存端口差除以原alpha范数为 **999999.9999999999**，远超1e−11，当前检查没有读取它们。

hash只能证明“现在读到哪份字节”，不能证明“这些字节满足方程”。下一版必须独立重算**实际保存并将被消费的每个作用**，包括原／约化trace、原／约化port、非零内部载荷与完整恢复，保留原分子和分母，拒绝删列、重复内部行、p4冒充p6、错side、错mode/H及错误原数组但更新hash的反例。不能只新增字符串状态检查。

此外，relative_terms的near_zero是numpy.bool_，正式atomic_json没有转换器。本次将上述两个实际返回值交给正式写出函数，均得到 **TypeError: Object of type bool_ is not JSON serializable**。check_boundary的完整分母表也包含该字段。必须统一有限JSON标量转换、保持NaN/Inf拒绝、原子写出/fsync/reopen并测试**实际checker→正式writer→重开→下一门**，不能仅测试一个简单字典或只跑pytest计数。旧V25未运行结果不受此发现反向改写。

checker不必再分解一次局部矩阵：导出原worker已经计算的内部解向量／作用，独立用原块乘它们核对，再组装原／约化方程。若现有冻结API缺少中间量，允许在本支src以最小明确补丁增加导出，记录新source与原c354afa的差量；不静默修改只读闭包，不在runner复制数学算法，不重写整个主线引擎，也不构造32060²矩阵。

### 2.3 坐标、真实入射和独立参照尚未闭合

centered_phase_pair计算相位及倒数，但boundary_worker只检查二者乘积接近1，未把它们接到移位后的面片、模态幅度或真实RHS；control也只做相同自身往返。任意错误平移仍可能满足这个恒等式。因此目前是**公式存在／部分接线**，不是ledger绝对坐标与居中坐标的物理等价验证。V25逐处保留physical_incident_rhs_qualified=False是正确的，但也意味着Review V24要求的真实入射／背景对照尚未实现。

下一版在同一实际面片上独立计算居中与绝对坐标两套原积分，并施加相应模态幅度逆相位，检查原Bα、D/H投影、伴随、入射／背景RHS及物理参考面一致。对本次纯切向平移s=(25,12.5,0)nm，积分/B应乘exp(i k·s)，原D/H和同一物理场的alpha应乘逆相位；原H不变。这是相位关系的验收，不是重新选择几何。用遗失相位、错误平移符号、错误参考面为必要负控，不接受“phase×inverse=1”替代。

P1的qualify_oracle实现了计算独立Decimal对照的路径，但本批没有执行；保存checker目前只读取ORACLE_INTERVAL_PASS字符串，没有从其检查数值／原数组重算，也未绑定这些oracle文件。补存既有参照的数值和必要Decimal字符串、参数及hash，让保存checker核对固定范围和原门；不新增积分阶数扫描。原参照限定实切向频率及既有范围，实际原件超出范围时记UNKNOWN，不能悄悄扩大参数或用共用Gauss节点的两个结果互相授资格。

主线原32060-key物理身份是掠入射1°、φ0°、s、上空气／下Si；W0的φ5°／532模式不是同一入射。局部制造的非零内部／端口载荷必须继续保留，但不得作为真实入射RHS的替代。

### 2.4 生命周期修复放在同一包，不另起微型review

receiver的global-swap停止开关与“自身swap0、全机swap仅诊断”的合同不一致；控制stage的cap计算也没有同样受剩余7200s数值总额约束。修复为原合同语义，保留自身swap、RSS、PSI、邻增长及监督失效门，不能通过放宽CPU阈值抢核。失败后的stage／输出目录不可覆盖；重试与跨stage证据复用要显式关联，旧窗及旧费用不清零。

本次没有V25原生进程，不据源码缺口虚构已发生的越界或错误物理结果。修复后需要一个真正穿过公开入口的原生control及checker写出／前置消费闭环；模拟传参测试只是必要条件。

## 3. 数值历史与最新并行线：不为维持路线而放宽标准

| 已尝试内容 | 保留结论 | 本轮决定 |
| --- | --- | --- |
| V11八尺度、M3600／Mfinal | E约0.0933003→0.122945退化，native约0.885852→0.846542下降；约77%退化为正交叉项 | 两态及轨迹保留，不重复长训练／调权；均不是有效解 |
| 监督表达／弱范数与优化 | phasefit E约0.009558、curl约0.010034、native约0.531472；表达上限与唯一根因未知 | 有监督能力不等于无标签PDE求解；不能归咎单一网络或边界 |
| V18神经与确定性修正 | 两态R−1约1.008e−7／1.790e−7>1e−8；最优性UNKNOWN；额外G改善占总修正0.07695%／0.42375% | 无真正NN净收益；D0成本否决、D1未运行，不重开旧修正 |
| V20–22相位／端口 | 散射E/curl约0.003121/0.003132>1e−3、最坏复模式约479.709；算术成功但物理投影失败，体差只缩小约0.1% | 固定单载波缩减入口关闭，无合格O6参考，不以功率替场精度 |
| V23 q60／V24 W0 | 健康局部q60≤1.9768e−11；解析无20%完整收益；W0原恢复1.50063e−12通过 | 复用已资格部分；W0制造态不是散射解；本批0新NN增益 |

最新远端主线仍为 **8c1a0ce23bd53cf92fffbed7a2daccd58cbf49a5**，dot仍为 **7f03a48d2962dd3ea967a07368b36acb4aae7f57**。主线q30/q60最坏差5.7059093327、原H组件差4.1493038268、作用差0.008663089的失败保留；旧p4上下恢复通过，p6因TIMEBASE_INCONSISTENCY未运行。dot只有选定q0 C1c，不能升级为全q逆／恢复；W2仍不授权。

Task042已推进至 **0217f004a38f109a6253923f83a9a24b19d85362**：[Response V45](https://github.com/Rookie1234567/MyFEniCS/blob/0217f004a38f109a6253923f83a9a24b19d85362/docs/task042_neural_coarse_inverse/response_v45.md)完成全矩分层3×128训练及5×8终测，各路线残差8/8、场门0/8；两份神经head被验证集选回零输出，NN-L/H与R0最终向量相同。[Review V43](https://github.com/Rookie1234567/MyFEniCS/blob/0217f004a38f109a6253923f83a9a24b19d85362/docs/task042_neural_coarse_inverse/review_report_v43.md)安排V46成本／引擎匹配，未授权新数值。这里按实际文件及内容编号，不按commit标题猜编号。

这些并行线仅作只读来源核对，没有取得其新raw并重算FE。Task042没有完整DtN、材料也不同，不能把其residual或成本直接移植。本支W0缩比80/p6/φ5/532端口，旧M5为5nm/384/p3/40端口，原尺寸W1为φ0/32060端口；必须核对几何、缺口、坐标、材料、FE矩／网格、端口／参考面、分母及完整成本。主线Gx784的1%资格不成为本支1e−4参考；NN-V3继续排除。本支不复制传统PC、全目标网格、dot C1／存储或Task042神经训练。

## 4. 原件交付和一份持续有效的执行合同

原manifest仍缺：36244923 B，SHA256 **52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d**；32060 ordered-key SHA **03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec**。还需配套ledger，允许原v5 SHA **8dd917dbb7252bfb0abca81213f3d3cba93cd1f35010a55cbf8c27e2f32ecd4a**或已登记修复版 **92c6a0f458ffa2d84911744cd8d6138f93414e8b850dfae205093e9618e45ae2**。checkpoint若可取得，应为38026664 B／104成员／SHA **a475bba1618abd74981622a66e127b2fd88b43f52a2339f5087115ed9b1a82f8**。

现有证据只能确认主线发布端曾保存原件，不能确认本机存在或提供一个真实可读URL。此前向用户请求位置的答复仍未取得。本审阅可用工具没有Library原文件下载入口；不臆造网络主机，不把摘要还原为AUTO，不反复检查同18路径。主控需要使**已有原字节**可读取；接收方负责下载／复制、hash和身份核验，不让用户手工安装或执行FE。建议目的地仍只是benchmarks/artifacts/task42extra/w1_receiver/inputs/52d7ec80/，不标已收到。

为避免“缺同一文件→新review→再查同一文件”的循环，本报告一次授权下面两段。**A可以立即推进；B只在真实原件和当前安全资源两项同时具备后启动一次，不需要为了提供路径、普通修复或确认收信再申请新review。** 不安排后台自动轮询或定时抢跑。

| 阶段／输入 | 工作与必要对照 | 验收／出口 |
| --- | --- | --- |
| A：被审阅bf3fa49d＋本报告，无需原件 | 修复§2全部问题；真实checker／writer／前置链的正常与破坏反例；增加必要原始中间量导出；不新建算法 | 失败监督／错source／缺hash不能进入native；破坏实际向量和oracle数值必被拒；正式JSON可重开；不把mock当物理资格 |
| B0：A受测clean提交＋真实原件 | 一次公开native control，真实方向、两周期缝及角点展开、实际写出／读取／清场；fresh ABI/source | 原门通过，完整资格链可重用；不能先启动P1/P2再补前置 |
| B1：同一输入和固定q60 | 全32060模式，原面矩／B/D/H／三方向／forward-adjoint及实际入射RHS；独立参照、绝对／居中坐标配对 | 各原相对门≤1e−10，区间矩原门≤1e−12；保存全量分子／分母／近零标记；不得只验总体范数或phase往返 |
| B2：仅B1及保存checker通过 | p4/p6各top-air／bottom-Si四个局部组件；原／约化trace与port、非零载荷、全内部恢复；因子释放后独立复核 | 原方程／B/D≤1e−10，恢复／消元恒等式≤1e−11；实际consumer向量全验；全目标MPC仍NOT_RUN |
| 收口 | 一份可由主线直接消费的输入／source／ABI／布局／raw／原门／完整成本包 | 正负／UNKNOWN并存；无原尺寸全局solve、W2、NN或merge许可 |

A先在同一分支完成代码与真实轻测试，允许阶段提交和保存checkpoint；A阶段提交不视为整批结束，不触发另一轮review／response。如果仍缺外部原件，停止工具等待该外部状态变化，**不再为同一缺项创建另一份归档报告或重新启动资源链**；保留阶段记录和清场状态。B的条件许可保持有效，真实原件到位时按相同报告继续。整个授权工作包收口或出现新的实质失败后，才集中提交response_v26.md、一次通知。若用户明确要求提前结项，真实部分完成照报，不伪造B结果。

本合同对接收数学的范围仍很窄。q60是唯一候选；先区分q30欠积分、坐标／归一化／消费者错误、q60本身不足。旧q30失败和W0通过都不重跑。正确q60在可靠参照下失败，保存负值后停止B2，不扫q/p、删模式、调权或重训。若参照自身不可靠，记ORACLE_ACCURACY_UNRESOLVED；若物理RHS／坐标配对失败，组件即使制造态通过也不得称W1完成。

原H与消元后端口作用分列。32060² complex128稠密矩阵仅本体约16.45GB，不得构建；分块作用保留一般非零内部端口耦合。所有局部LU、solve、小坐标变换、checker工作和保存都计费。最小导出补丁不得引入第二套体积分／MPC／owner／传统求解器。

## 5. 预算、资源与有限修复

本次明确采用**两段各自连续的研究执行窗口**，用于外部文件尚未交付的现实条件：A最多3600s；B在首次为真实输入准备时起最多10800s，其中B的worker＋数值checker最多7200s，最后1800s保留交付。主动执行上限合计14400s；两个窗口之间的真实外部等待单列并计入项目日历费用，**不得声称整个研究交付在14400s日历内完成，也不得拿分段预算证明最终48h目标或成本收益**。B只授权一个窗口，不自动续期；V25旧14400s窗和全部失败费用不可覆盖、迁移或重置。最终目标的172800s完整冷流程仍要求连续计费，未改变。

A是纯代码／轻测试，2GiB整树；B的native control仍2GiB，局部组件warn12／hard16GiB，轻checker／浏览器warn1.75／hard2GiB；需要原生积分的checker按实际数值阶段计费和准入。CPU-only、MPI1、数学线程1、一个实测空闲物理核并避开忙碌SMT，自身swap/OOC0；原系统max(128GiB,有效整机10%)、至少384GiB邻增长、60s数值PSI、至少50GiB空闲磁盘／本批新增8GiB和任务锁不放宽。记录自身与整机资源不同口径，0.5s采样不冒称连续kernel限额。

执行前先确认原件状态及阶段准入，不为重复探测消耗native尝试。一次资源拒绝可以在**有实测变化的新窗口**后至多再准入一次；再次拒绝关闭该窗口，保留可独立完成的代码／证据，不追加轮询。禁止更改邻进程、SMT策略、共享环境或系统限制以取得通过。全机swap变化只作诊断，自身swap仍是停止门。

A/B共用最多两轮有明确根因／实际修改的工程修复池，每受影响数值case至多三次且仍受各窗限额；checker或序列化错误优先复用正确raw，不能重跑正确worker。原数学门失败不能伪装工程修复。达到身份／真实数值／资源／时间／监督停止条件就保存全部正负与未完成项，结束受影响升级。小schema、路径或文档错误同批定向修复，不停下来等待新review。

需要真正有区分力的测试：错误监督仍有PASS标签、跨input／source／旧窗凭据、错hash与更新hash但错误数组、漏qhat_alpha／错仿射项／错trace消元、p4/p6／side／内部重复行、相位符号／载荷错误、oracle数值超门但标签PASS、NumPy标量写出与损坏重开。复用本审阅反例作为起点，测试实际函数和公开消费者链，不加只复述实现的计数型测试。随后运行受影响native资格及Ruff/compile；文档改变不触发昂贵数学重放，不声称full pytest／CI。

V25最终连续交付费用是2846.101466s，最后合格轻检查2.832654745s／111972352 B／swap0；初始12GB cap缺口和Ruff失败保留，原生CPU拒绝单段耗时NOT_RETAINED但包含父墙钟。项目精确累计UNKNOWN、旧失联3284s及历史尾段不清零。本审阅首次纯检查监督1.964329s因返回值封存触发类型错误；规范化**审计收据**后复验1.980977s，峰64544768 B、swap0，未修改生产实现，两个受监督子树均清空。这些是审阅费用，不是新的FE资格或速度比较。

文档选择性合入仍仅是候选分组；所有未资格W1、旧FEINN训练默认及ignored原件不进入production。V25新页原始视觉状态继续保留为NOT_RUN，审阅补验范围另记本次收据，不回写旧执行事实。下一轮只核新页／改变区域，未变历史复用hash收据，不为视觉单项另开数值批次。

## 6. 给主控 Codex 的执行文本

~~~text
在 /home/fenics/Projects/NN-Lab-V2、精确 task42extra_feinn_5nm 接棒。先核对 Review V25 发布HEAD、被审阅bf3fa49d771fb2517166748c268328049f175be9和base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff，完整读 review_report_v25.md 与 review_v25_evidence_audit.json。收到正式通知后你独占工作树，审阅窗口停止工具。

V25实现有价值但验收链有实际缺口：prerequisite会接受失败监督的PASS标签；check_local没有验保存的qhat_alpha/affine_internal_rhs及完整trace消元；正式writer不能序列化near_zero的numpy.bool_；坐标相位仅自身往返，真实入射RHS未接入，oracle保存资格只读status。这些同批修复，不只补文件重试launcher。复用实际函数反例，补正常/损坏/错身份的checker→writer→reopen→下一门测试；最小导出放src并绑定新source，不静默改冻结闭包，不复制数学算法。

A无需外部文件，可立即完成上述代码与轻测试，连续最多3600s。B只有实际52d7ec80…原manifest及匹配ledger、A资格和安全资源都具备后启动一次，连续10800s、数值checker7200s、尾段1800s；不用为提供路径或小修复再等review。中间外部等待单列实际日历成本，不能冒充整批14400s内，更不能证明最终48h。没有原件时保存A阶段和clean状态、停止工具等待真实状态变化，不再发纯归档/确认收信批次，不自动后台重试。

B按真实native control→唯一q60全32060-key及独立参照/原H/坐标与物理RHS→保存checker→条件p4/p6上下四局部完整原/约化方程及恢复，一次完成。正确q60/物理门失败则保留全量负结果并停止升级，不扫q/p、不重新训练。不要重跑W0、旧q30或dot工作。资源、共同两轮修复池及每受影响case至多三次按报告；正确raw优先复用。

原50×25×140nm、Si17/120nm、lambda0.7完整3D FE、decimal2e12B整机、ownswap/OOC0、连续172800s完整冷流程及原精度门目标尚未达成。FEINN主求解器暂停、无验证NN净增益；无W2、原尺寸全局factor/solve、其他分支修改或master merge许可。整个包完成或有新实质失败后集中交response_v26和可消费W1包；一次正式通知并停止工具，不要求确认收信。
~~~

## 7. A阶段复审：接受纯逻辑修复，B仍按原条件等待真实输入

本节回应用户对A阶段的单独审阅请求，**不创建Review V26，不把阶段交接变成整包完成，也不重新启动A窗口。** 被审阅seal为4152f0e1fb4e2a20f65643adc82cee19f66e87b8，实际实现／最终受测source为6e0913810d42450eb0b899b46389b8b014bd8883；接手时远端、显式tracking及HEAD一致，0/0、clean。裁决为 **A_PURE_LOGIC_ACCEPTED / B_NOT_STARTED_INPUT_UNAVAILABLE**。以下是新增结果，§0–6中V25初审时的失败反例和执行合同保留为历史及授权依据。

### 7.1 已关闭的实现问题与独立证据

已完整审阅22份变更中的实现、输入、测试及阶段记录，重点核对真实调用链；[A阶段独立复审收据](outcomes/records/review_v25_stage_A_audit.json)保存核查脚本、原量、资源和文件绑定。62处绑定／60个文件吻合，25份源码／测试／输入与6e091381一致；更新本报告之前，本次检查的437份旧任务文件逐字未改。独立解析原JUnit为81项含1失败、随后81／88／最终92项通过；早期未提交源码未保留的限制不改，也不把这四次运行当同一个受测source。

前置现在同时验证共同科学身份、各stage的dat、原数组／结果hash、成功监督、退出0与清场，允许相同源码blob跨文档HEAD复用。本次直接调用实际函数，两种“仍保留PASS标签但监督失败”的原反例均以W1_PREREQUISITE_SUCCESSFUL_CLEARED_SUPERVISION拒绝。

局部checker现在真正消费qhat_alpha、affine_internal_rhs、原／约化trace和port及内部恢复向量，并从保存的B/D和原块重算；p／side／分区／模式／原H也参与核验。独立复核采用p4/p6、上下两侧的**四个合成非厄米代数对照，各含4个人工模式**；Basix和直接面积分明确stub，绝不当作32060模式或原生FE证据。四态最大检查相对差分别为3.23310e−16、3.21484e−16、4.31328e−16、4.36837e−16，正常态通过；每态分别破坏两个实际端口向量及两个trace消费者并更新文件hash，共16个反例全部返回FAIL。错误qhat相对差约5e5仍被原门拒绝，修好了先前“文件hash自洽但实际向量错误仍通过”的缺口。

有限NumPy标量经统一转换后，实际checker结果能够原子写出、fsync及重开；NaN/Inf拒绝仍保留。最小导出补丁与冻结c354afa源码差量、保存preview逐字相符；原与派生模块均为5处lu_solve调用，只有已有中间量和B/D列导出，不增加另一套求解器。本次没有实际执行这些局部LU，也不以AST计数证明未来原生运行的精度或费用。

坐标核验已从相位自身往返接到实际居中／绝对面矩、模态幅度、B/D及伴随。真实1°／φ0°／s入射的边界载荷通过modal_rhs消费，并有空气／Si平面背景对照；它只覆盖**边界入射源**，完整三维缺口的体源与总前向方程仍未取得新资格。独立参照的数值、Decimal字符串、覆盖及固定范围已保存并重算，不能只靠PASS标签放行。A里的这些测试证明接线／错误拒绝逻辑；B中的实际原件、Basix、积分及保存场才提供物理资格。

资源语义已改为自身swap停止、全机swap仅诊断；control也扣共享7200s数值预算。独立调用公开durable_w1入口，实际返回B_NOT_STARTED_INPUT_UNAVAILABLE，未创建B_window.json、tmux目录或native worker；没有为测试重造manifest。

### 7.2 成本、边界与下一步

A交付收据记录2361.839628s／3600s，含开发、失败、检查、Git和清场；监督测试峰153862144 B，含浏览器的已采样树峰1839824896 B、自身swap0。第一轮载荷把三分量向量传给两切向列，修为traction[:2]后通过，原失败保留；共同两轮工程修复池已用一轮、剩一轮。本次独立复审子进程5.913218s、树峰161132544 B、swap0、后代清空；是审阅费用，不重复加到A父墙钟。全项目精确累计仍UNKNOWN，旧3284s与全部旧费用不变。

A的三张README截图实际同字节；本审阅按**一张有限视图**复核可见的串行命令、独立检查／真实载荷和资源正文，不把重复截图计为三份独立覆盖，也不声称整页历史导航均完成目视。它不影响数学裁决，不需要为此新开修复批次。

**本次不追加训练、参数扫描、重跑W0／q30或新的诊断任务。A无需重复交付或重做已经绑定的92项测试。** B仍缺真实52d7ec80…原manifest及匹配ledger；现有建议接收目录不是可读原件。维持§4–6的单次条件许可：原件到位、相同受测实现和安全资源具备后，直接执行native control→唯一q60全32060-key及真实边界载荷／独立参照→条件四个p4/p6局部恢复，不用为路径到位再等review。源码发生实质修复时，只更新受影响资格和新source，使用剩余一轮有根因的修复机会；不重置A或B预算。

外部等待从A交付记录的2026-10-04T19:40:01.839628Z起另计日历成本；本次阶段审阅费用再单列，不冒称纯文件等待，也不把它摊销成48h目标收益。B尚未开始，原10800s／数值7200s／尾段1800s不变。没有原件时保持clean、停止工具，不反复扫描或排队抢核，不发确认收信或另一份暂停报告；整包完成或新的实质失败再集中Response V26。

可直接转交执行窗口：**A阶段纯逻辑修复已独立接受，读取本节和审计收据后沿用Review V25条件许可。当前不重复A、不启动B；等待真实原件到位，届时在原门和单一B窗口内完成整批。FEINN主求解器仍暂停，原50×25×140nm／Si17/120nm／λ0.7完整3D FE、decimal2e12B、ownswap/OOC0、连续172800s及原精度目标尚未达到，无W2、全目标全局factor/solve或merge许可。**

## 8. 原件接续审阅：一次恢复确定性输入，随后完成真实全模式边界资格

本节回应用户最新要求：核实原件位置；取不到时仍安排有实质推进的工作。被审阅HEAD为 **4659bb427633ea9742cbe7097e60d34268a1eac7**，本次非交互精确远端查询与fetch一致，工作树clean。A已接受，B时钟和worker均未开始；不重新审A，也不新建Review V26。**本节明确覆盖§4–7的“只等旧原件／禁止再次生成库存”、必须旧ledger才能启动的输入分支、B计时起点及B2本轮范围；其他精度、安全、历史保留与非生产边界不变。** 旧正文是原时点记录，执行以本节为准。

### 8.1 原件在哪里，哪些入口现在确实可用

[本次检索及源码审计收据](outcomes/records/review_v25_input_recovery_audit.json)记录完整范围。重新刷新4942份tracked文件／113087227 B及结构标题，重点复读任务、当前合同、接收链和原生成源码；不是声称全仓逐行语义审计。有限检索覆盖本机Projects、可读/tmp、/mnt、/media及Downloads，共209420个唯一文件的元数据，检查准确文件名、已知字节数及相关ZIP目录，**候选0**。未越过权限、未递归符号链接；不可读系统目录、旧浏览器断链和排除环境目录均记入收据。因此结论是**本机指定范围不可取得**，不是“原件已经被删除”。没有重跑AUTO、FE、训练或A测试。

主线最新 **2a67a2423fdd8b670d907ef6f9394a17bff8f2f6** 的[原件审计](https://github.com/Rookie1234567/MyFEniCS/blob/2a67a2423fdd8b670d907ef6f9394a17bff8f2f6/docs/task40extra_0p7nm_engineering/outcomes/records/review_v8_w1_identity_audit_v1.json)和目录规则指向生产端根 /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering。其下 benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/ 保存原manifest与ledger；target_ledger_v5_repair/ 保存同字节manifest及另一ledger。最后发布读取时点为2026-10-04T11:26:18.586819Z；**这些是另一台WSL机器上曾读到的准确位置，本机该根不存在，没有可验证的SSH或HTTP下载端点。** 旧NPZ的相对入口仍为 benchmarks/artifacts/task40extra_0p7nm_engineering/local_w1_wsl/w1_probe_c354afa_retry1_20261004T1654Z/probe/w1_boundary_probe_arrays.npz，不是Git中的38MB正文。

封存时dot已更新至 **3f4fb69b20d33d382975bb96db73b44bba583ebd**，其未变的[Library读取收据](https://github.com/Rookie1234567/MyFEniCS/blob/3f4fb69b20d33d382975bb96db73b44bba583ebd/docs/task40extra_dot_parallel_cloud/outcomes/records/target_AUTO_identity_v1/library_readback_receipt.json)有真实定位符：target_AUTO_complete_inventory.zip，Library ID为libfile_01b478e1d1f48191bea7c9deea966423，file ID为file_00000000602c82079e69fb389f0c8a1c，ZIP SHA为4c3deb139b5eb8c164c1873144685f45869c7f63b971fa05b7e969d8b0b09023。其中物理manifest为36263033 B／SHA 7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e，**不是所需52d7ec80原件**。当前工具没有这个Library ID的通用原文件下载入口；Pages的引用读取不等于任意Library下载。不能把ID编成URL或把dot归档直接塞进本支输入门。

**现在真实可读的交付入口是冻结Git源码、输入dat和完整物理身份正文；不是缺失大文件。** 下节把这些现存字节变成一项可执行恢复工作。将来若生产端提供可读原件，按§4原hash接收即可，不再全面扫盘；若没有，就执行下面的一次恢复，不让用户手工clone、安装、跑程序或重复转述缺项。

### 8.2 为什么可以尝试恢复，以及不能伪造什么

manifest列出每个外部衍射波的波数、极化、牵引及原投影分母，是由固定输入计算的确定性数据。冻结函数build_ordered_mode_manifest只写schema、profile、mode_count和modes，**不含日期、机器路径或运行状态**；所以重现原文件的逐字节SHA是有意义且严格的验收。它仅恢复输入，不增加一个求解算法，也不能证明端口截断、网格精度或PDE正确。

本次独立比较原生成source **19acb46e468eaf5d8fa56e767d391fefbfab49a4**、修复source **24a56962c733b9ae5454000cdae224dae6dda8f0**、W1数学source **c354afa449fb80cfb5012e7d2ff66a3e3e64e088**：modes_3d.py、原目标ledger runner及源dat逐字相同；manifest序列化、mode identity、库存生成、原H、traction、目标配置/身份函数的AST相同。相关整文件另有后续表面装配修改，不能把局部函数一致夸称整棵源码相同。**没有在审阅中运行生成器，跨ABI能否同字节仍待验证。**

配套旧ledger含时间、绝对路径、旧run identity；不应伪造这些字段来碰旧hash。本轮允许一个独立的reproduced-input-receipt分支：保留原ledger两hash作为未取得的历史权威，写本次真实source/ABI/时间/命令与恢复方法，绝不标作旧原件收回。物理身份取自c354afa的docs/task40extra_0p7nm_engineering/outcomes/records/review_v8_w1_identity_audit_v1.json，其16783 B原文件SHA为 **03b5c44136f132d203237211ea1499faec1c25d3c1f47225e0c662d00aca4ea0**。本次已从其中完整对象重算：physical SHA为a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f，inventory SHA为39b457c3f0b9d8db5f85a8f1482734513d48670c017d4c8060cae734bdcd0c12，与旧记录一致。这个小文件可以从准确Git blob读取，不需要猜旧ledger正文。

### 8.3 单一工作包：R → B0 → B1 → 保存checker → 可消费交付

**现在授权执行这整个工作包，不在恢复成功或代码提交后再次等review。** 优先级和条件如下；B2局部因子/恢复改由主线承担，见§8.4。

| 阶段／输入 | 实际工作与必要对照 | 严格出口 |
| --- | --- | --- |
| R，已接受A＋冻结c354afa源码/源dat/身份原文；无需外部文件 | 只读Git对象闭包，调用原目标配置、模式生成及manifest序列化一次；不运行带主线分支/环境写入的顶层build，不伪装主线HEAD；只补实际导入依赖 | 36244923 B、32060唯一有序keys、原52d7ec80完整SHA及03c1965c有序SHA同时相同；正文重算physical/inventory hash；否则不得进B |
| R接收封存 | fsync/reopen原字节；新来源凭据与准确原blob绑定，真实SHA进入各dat/worker/checker；旧原件路径仍保留 | BITWISE_REPRODUCED_INPUT，不是旧ledger恢复或FE PASS；拒绝错来源、假hash标签、篡改物理正文、改模式及失败监督 |
| B0，R通过或真实原件接收 | 现有公开dat链上的真实Basix方向、非单位Floquet两缝/角点、写出/重开/清场；fresh ABI与受测源码 | 原控制门通过；A的stub不得替代；只做一次合格原生控制 |
| B1，B0通过，同身份、唯一q60 | 原(100,1)上下代表面，p4/p6全列、32060输出，B/D/H、三方向、forward/adjoint、坐标和真实入射边界载荷 | 区间矩≤1e−12；逐模式/作用/坐标/载荷各原门≤1e−10；全量分子/分母和失败key保留；仅代表面资格 |
| 保存checker与交付 | 独立进程从原数组/凭据重算，给主线最小输入/ABI/source/布局/原门/成本包 | 正负/UNKNOWN分列；正确worker不因checker写出错误重跑；一次Response V26，不只交“已找回文件” |

R的待实现入口应扩展现有W1 dat/receiver，使用明确的input_recovery阶段；schema和接收判定放src/io，编排沿现有监督/one-run入口。它是本轮新增接线，**当前命令还不能直接执行这个新stage**，执行者完成最小实现与定向检查后立即继续。生成使用c354afa冻结实现，不更换材料库、libm、模式范围、浮点精度或序列化器来试hash；不手调数字、不扫描环境。完整manifest的任意数值/顺序字节不匹配均保存为BITWISE_REPRODUCTION_FAILED，而不是放松为“数量一样”。仅路径、导入、写出等有明确原因的接线错误可用剩余修复池处理；已经生成但hash不匹配的正确执行不重算第二个候选。

接收凭据必须有明确schema及独立分支，不能往原LEDGERS白名单塞任意运行hash。验证器固定检查原manifest字节/大小/keys、上述Git原文及source blob、正文重算physical/inventory digest、实际监督/清场和本次来源；对所有消费者返回相同科学身份。把伪造或缺项凭据挡在native前。新receipt内容SHA在首次R完成后冻结，后续不得换文件重启同窗。旧A中未改源码的资格复用；受影响输入/监督/时间与凭据测试形成新source增量资格，不把旧92项记录重新标成新source通过，也不重做全部A。

B1继续复用本支V23的区间矩实现及Decimal80/110独立参照，不按主线新报告再写第二套Bessel算法。本批实际(100,1)面宽采用原_proportional_axis的90/46/46/90分段，不能沿用旧78/58/58/78计数。把实际manifest和这两个面宽给出的**所有去重一维频率、ell0..6**列为独立参照覆盖清单；复用同频率、同源码的V23资格，缺少的频率用已有固定Decimal80/110路径一次补齐。不能仅凭最大/最小/旧worst几个频率就称全范围参照已验，不能调整已有绝对门或超出固定56rad范围。已保留的所有mode/近零项均参与检查，不裁掉难模式。

R的manifest满足原hash后，本轮新来源凭据可替代缺失旧ledger作**本批输入资格**；不认证旧运行成本、旧NPZ或main/dot的整个物理identity。旧NPZ继续NOT_AVAILABLE，不是本批必须等到的前置，也不允许凭新数据重造其104成员。实际原件以后到位可以一次比对，但不是新q60工作继续推进的额外审批。

### 8.4 最新分工、成本与明确停止条件

主线[Review V9](https://github.com/Rookie1234567/MyFEniCS/blob/2a67a2423fdd8b670d907ef6f9394a17bff8f2f6/docs/task40extra_0p7nm_engineering/review_report_v9.md)已把**旧104成员的q30/q60归因、两个p6局部恢复、保存p4体积复用**分配给主线；仍没有其新Response或可接收raw。故本支本包**不再自动运行原B2四个局部LU/恢复**，也不补造主线旧体积。当前独立贡献是可复现输入和本支已建立的独立参照/实际接收链：主线可消费其全模式结果，避免再实现同类积分；若启动时主线已交付同物理/同面/同列/同原分母的完整新raw，则优先运行本支独立保存checker，不重复正确producer。仅作一次交接时检查，不后台轮询。此处只安排本支，未修改或替主线授权。

dot已完成小型C1a/b/c及后续校准，不能继续按“C1c未运行”安排重复工作。封存时新增3f4fb69b的[六个top/x分量记录](https://github.com/Rookie1234567/MyFEniCS/blob/3f4fb69b20d33d382975bb96db73b44bba583ebd/docs/task40extra_dot_parallel_cloud/outcomes/chunked_surface_mass_v2_zh.md)：原尺寸18cell/p6边界夹具，三个tuple两极化、三个状态共18作用检查，degree160对168/176参考最大操作尺度差3.90869807e−14、参考间1.93952788e−14，监督44.552426s／树峰944046080 B、swap0。它采用明确的辅助常数积分绝对门1e−12，原节点/权重未归一化，原向量1e−11及作用1e−10门保持；这不是一般函数误差定理。本次从compact的分子与操作尺度独立重算两组各18项比值，并核对六组机制向量的已存范数比值；这些标量与发布结论一致，但没有取回NPY重新积分、求范数或验证FE。相关源码/政策差量及收据已只读核对。旧32ε停止、degree27机制结果及更早编译资源停止均保留；不能再称目标selected作用仍未运行，也不能将新局部PASS升级为完整AUTO。

本支不复做dot的分块top/x、调整它的门或接管后端/存储。六个分量与本支两代表面、全部32060输出不同；其操作尺度是逐点绝对积分贡献和，不能替代本支原分母或场误差。两侧Si/λ/角度参数虽可对齐，主线居中网格、本支代表面和dot 18cell/边界参考平面不同，未逐行桥接前不移植误差或速度结论。dot仍缺完整top/bottom、x/y、全模式C/D及目标解，主线1%门也不替代本支1e−4最终门。新证据不改变本包分工和预算。

**不增加原B的10800s额度；改为R/B共用一个连续窗口。** 从执行者本轮第一项恢复接线/准备开始固定唯一T0，含开发、测试、R、B0/B1、独立checker、失败、Git/保存/交付；R及新接线≤1800s，所有实际数值/数值checker累计≤7200s，最后1800s留交付，所有子额度还受总窗剩余约束，不相加扩额。已有A≤3600s与实际2361.839628s不重置。本次审阅和A后的真实外部等待单列，不冒充免费时间或连续14400s完成。

现有prepare_B_window必须最小适配：R起点先持久保存，B输入一经封存再附加binding，**只继承R原deadline，绝不在R成功时新建“现在+10800s”**。相关资格更新不能修改A旧收据。仍只准一个窗口、共同修复池剩一轮；原case最多三次只是绝对上限，必须同时受剩余修复次数和总窗约束。小路径/schema/序列化错误同批定位修好继续，不再请示；真实hash/数值失败则结束依赖升级，保留完整负值和原因。

R/轻检查/B0整树2GiB，B1原生组件及需要原生积分的checker沿原warn12/hard16GiB，纯数组checker/浏览器2GiB；单空闲物理核、数学线程1、MPI1、CPU-only、自身swap/OOC0、原PSI/整机和384GiB邻增长保护不放宽。新增盘仍≤8GiB、启动空闲≥50GiB，不构造32060²稠密矩阵。R只做模式元数据，没有mesh/space/FFCx/FE action/局部或全局Maxwell因子；导入FE库不计为FE运行，但应记录ABI。资源一次拒绝仅在实测状态变化后至多再准入一次，仍计原窗；不抢核或反复等新窗口。

明确出口：R失败是输入重现失败；B0失败是原生资格未闭合；q60真实原门失败是该候选负结果，停止升级、不扫q/p、不换分母。参照不可靠则ORACLE_ACCURACY_UNRESOLVED，不能判q60通过。成功只称全模式**代表面组件**和可消费接入通过，仍不是完整前向解。全部错误和费用与旧M3600/Mfinal、D0否决/D1未运行及未知项目总费一并保留。FEINN主求解器继续暂停；原50×25×140nm／Si17/120nm／λ0.7完整3D FE、decimal2e12B整机、ownswap/OOC0、连续172800s及§0原精度门仍未达成。

### 8.5 给执行 Codex 的接续文本

~~~text
在canonical /home/fenics/Projects/NN-Lab-V2、精确task42extra_feinn_5nm接棒，只读Review V25最新§8及review_v25_input_recovery_audit.json。输入HEAD4659bb427633ea9742cbe7097e60d34268a1eac7；A已接受，不重做A，不只交暂停记录。通知后你独占工作树。

本机原manifest/ledger/旧NPZ不可取得；不要重复扫盘或编造下载URL。按§8新增一次R输入恢复，复用冻结c354afa的原目标配置、模式生成及序列化；明确允许这一次恢复，覆盖旧“禁止再生成库存”。必须逐字节得到36244923B/52d7ec80完整SHA及32060/03c1965c有序SHA，否则禁止B。用固定Git身份原文03b5c441…重算完整physical/inventory对象，生成有本次真实来源的新receipt；不冒充两份旧ledger，不改旧历史。验证器明确分支、实际消费者和负控定向通过后继续，不为新schema另等review。

从第一项R接线准备冻结唯一10800s连续总窗，R及接线≤1800s、数值/checker≤7200s、尾段1800s，R成功不刷新B时钟；A费用、外部等待和本次审阅另列。输入通过即串行完成真实B0→唯一q60/B1全32060模式→独立保存checker和可供主线消费的包。实际两个面宽/全部去重频率的已有80/110位参照覆盖补齐，原门不降。只在整包完成或真实有界失败后交一次Response V26/通知。

主线2a67a242…已负责旧数组归因和p6局部恢复，本支不自动跑B2的四个LU，不代跑主线/dot。dot最新3f4fb69b…已完成六个selected top/x的degree160有限资格，旧规则负态仍保留；它不是本支全模式资格，也不重复其C1c/分块表面。共同修复池剩一轮，正确raw优先复用；身份、数值或资源真失败保留后停止受影响升级，不长训练、扫配置或换标准。其他分支/master、原尺寸全局solve/W2及NN仍不授权，最终0.7nm完整前向目标不变。
~~~
