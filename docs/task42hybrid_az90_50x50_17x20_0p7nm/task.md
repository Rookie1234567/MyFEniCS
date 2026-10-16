# task42hybrid：90°方位角、50×50 nm周期、居中17×20 nm柱状光栅

## 0. 任务决定与身份

**这是新物理模型的独立任务，不是Task041旧M400失败的继续重试。复用Task041代码、已验证组件与工程经验，重新建立新模型的直接法参考，再验证相同模型上的Hybrid迭代法。执行顺序为13.5 nm直接法 → 13.5 nm耦合/迭代验证 → 0.7 nm；不把5 nm、2 nm或旧模型四次B捕获设为共同前置。**

```text
task_name       = task42hybrid_az90_50x50_17x20_0p7nm
repository      = Rookie1234567/MyFEniCS
working_branch  = task42hybrid_az90_50x50_17x20_0p7nm
base_branch     = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
base_SHA        = 94700f95f2bef02e2359e6ca89872c11e65978fb
base_review     = docs/task041_mpi1_shortwave_hybrid_capacity/review_report_v19.md
base_response   = docs/task041_mpi1_shortwave_hybrid_capacity/response_v19.md
created_date    = 2026-10-16 Asia/Singapore
response_first  = response_v1.md, in this new task directory
public_entry    = python scripts/run_case.py <one-case.dat>
MPI             = 8, math threads per rank = 1
Codex_project   = KEEP_EXISTING_NAME_AND_ROOT
merge_approval  = NO
```

本轮用户明确要求ChatGPT从Task041新建分支并写任务书；这是仅对本次建分支操作的显式授权，覆盖仓库通常由Codex建分支的规则。不是从master重新起步，不整体合并其他研究分支。ChatGPT本次只创建分支和任务文档，未修改求解器、生成正式结果或操作工作站。

**消除的blocker：**旧入射方向及y贯通几何不是用户现在要计算的物理问题；本任务先建立正确入射、真正二维横截面与可比较的数值参考，防止继续优化错误案例。最终目标仍是0.7 nm、约2 TB物理RAM并保留系统余量、48 h完成一次必要QEP/构建/求解/恢复/核验/清理。此Hybrid模型的中段仍沿z可模态传播；它不能代表任意非可分三维Full3D已通过。

## 1. 原项目不改名，旧任务不覆盖

Codex继续使用用户当前已打开的项目、目录、环境、账户与主控/执行协作方式；**任务名、Git分支名与Codex项目显示名是三件不同的事**。不得要求用户新建空目录、重新clone、重装环境或改Codex项目名。

先核对canonical工作树、HEAD/upstream/dirty、已有stash以及实际运行的unit/PID。已清洁且没有读取该工作树源码的活动作业时，在原项目根安全fetch并切换到本分支、建立tracking。若新分支尚无本地tracking，可用`git switch --track origin/task42hybrid_az90_50x50_17x20_0p7nm`；已存在本地分支则核对upstream后正常switch，不重复创建。

不得`reset --hard`、`clean -fd`、删除旧结果、弹出或覆盖保护stash。若旧工作正在运行，先只读核对并报告；不为切分支热改运行源码，不擅自杀掉作业。必要的旧任务保存/交接由现有主控在当前项目处理。Task041文件和旧分支保持原历史，不把其FAIL改成PASS；其2/2与专用四B额度都不转移。本任务新建账目，旧累计费用只引用，不归零或重复追加。新分支上的直接任务权威是本目录task/后续review，旧Task041任务专属禁令和额度不是新任务的执行入口。

## 2. 冻结新物理模型：只改变用户指定项

“其他不变”按原完整目标模型解释，**不是把旧10×5 nm缩减pilot放大x/y而保留24 nm高度**。采用仓库现行坐标[0,Lx]×[0,Ly]。

| 项目 | 本任务冻结值 | 说明 |
|---|---|---|
| 周期 | Lx=50 nm，Ly=50 nm | 用户明确变更 |
| 光栅截面 | x宽17 nm，y宽20 nm | 矩形、居中，不沿y填满 |
| 中心与边界 | 中心(25,25) nm；x=16.5..33.5，y=15..35 nm | 不用旧y贯通材质判定 |
| 光栅高度 | 120 nm，z=0..120 nm | 原完整目标保持 |
| 基底与计算域 | W基底z=-10..0；z域=-10..130 nm | 底部仍用开放端口，不是10 nm悬空薄膜加真空背面 |
| Hybrid接口 | bottom z=10，top z=110 nm | 两侧各20 nm，中段长度100 nm |
| 入射 | 从上方入射，掠入射角1°，方位角90° | 极角若从向下-z量起则为89°，不能把1°当法线角 |
| 偏振、幅度 | s，归一化电幅1 | s基随方位角旋转，不能保留旧Cartesian向量 |
| 材料 | 空气n=1；光栅与基底保持当前短波长主线的W；mu_r=1 | n随波长取相应数据，不能跨波长复制数值 |
| 边界 | x/y Floquet；z Fourier-DtN；layered background；无PML | 原波动符号、向外法向和功率归一化保持 |
| 离散族 | complex128，Nédélec H(curl)，p6起步，boundary-fitted hex，assembly-time condensation | 调h/M是离散试验，不改变物理尺寸 |

材料具体约定：0.7 nm暂沿用Task041已注册的W数据`n=0.9995903781323069+0.00012887909720587614i`及其原source-derived candidate出处/标签，不因换任务名升级材料资格。13.5 nm必须取得**W在13.5 nm**的可追溯光学常数，沿相同密度/来源/符号规则计算并保存n、epsilon、delta/beta和原表hash。旧13.5 nm Task041模板使用Si，不能静默继承它充当本W模型参考。现有合格材料文件可复用；缺W13.5值时优先现有数据源或CXRO，冻结材料记录后才启动物理PDE，不随意插值跨吸收边或使用0.7 nm数值。材料准备期间几何/入口轻量验证可继续。[R3–R5,S1]

### 2.1 入射、偏振和Floquet必须一起修改

以alpha为掠入射角、phi为方位角，上方入射的目标方向为：

```math
k_0=2\pi/\lambda_0,\qquad
\mathbf k_{inc}=k_0(\cos\alpha\cos\phi,\;\cos\alpha\sin\phi,\;-\sin\alpha).
```

```math
\phi=90^\circ\quad\Longrightarrow\quad k_x\simeq0,\quad k_y=k_0\cos1^\circ,\quad k_z=-k_0\sin1^\circ.
```

在通常s基约定中E_s=(-sin phi,cos phi,0)，此时沿-x；以项目实际约定为准，必须验证E·k=0、H由同一Maxwell符号产生、入射Poynting指向负z。不要任意翻转E/H其中一个或在对照中作自由phase拟合。x周期因子接近1并不表示可以删除x周期约束；y周期因子应由实际ky生成且只施加一次。代码使用约化Bloch波矢时要连同倒格矢偏移和衍射索引保存，不能丢失入射的物理方向。

**kx=0只说明入射没有x向相位变化，不说明散射场与x无关。** 新材料分布同时依赖x、y；禁止y-invariant、n=0-only、二维等效或只保留一个衍射指标。中段z=10..110截面不随z变，所以仍可用完整二维截面QEP沿z传播；不能继续用原一维条纹的模式简化。

### 2.2 外通道与内部M分开核算

上方空气的解析传播级满足：

```math
(k_x+2\pi m/L_x)^2+(k_y+2\pi n/L_y)^2<k_0^2.
```

按上式、50×50 nm、1°/90°直接枚举，13.5 nm得到42个空气传播空间级，0.7 nm得到16031个；各有两个偏振时分别为84、32062个通道标签。**这是任务编制时的解析derived inventory，不是程序已测出的DtN维度，也不含基底/边缘判别/额外倏逝级。** Codex必须独立核算并与实际external key生成器对齐，差异先解释；浮点边缘统一原Rayleigh规则。尤其不能沿用旧±25范围、143级或n=0剪裁。

内部M是每个传播方向保留的QEP模态数，与外部传播级数不是一一相等。新周期、横截面、Bloch条件和材料改变后，旧M120/M400的充分性都失效；M必须在每个正式dat中明确给定，求解过程中不得静默改变。边界trace是否足以表达端口数据、源投影与alias/rank检查必须在大factor之前完成；不靠删合法通道来适配过粗网格。

## 3. 继承什么，不继承什么

| 可复用 | 不可直接复用或宣称 |
|---|---|
| 原生ABI、complex128、MPI、通用网格/Floquet/DtN/QEP与恢复代码 | 未核验新ABI、未测新模型却称已资格化 |
| p6装配期凝聚；p4准确cell_condensed逆与完整恢复 | 旧geometry-bound因子、Schur、mesh/MPC、source或模式packet |
| BAL_H、同一固定B/S_B候选、RIGHT FGMRES、资源监督和销毁前捕获 | 旧5 nm耗时或旧M400失败作为新90°模型的数值结果 |
| V16 MemAvailable、default/unbound、swap observe-only机制 | 旧model_id白名单、80 GiBpilot cap、旧2/2和诊断停止额度 |
| 小型公式和生命周期测试在相关源码不变时的证据 | 以旧y贯通几何测试替代新17×20 nm横截面测试 |

Task041截至base有未解释的PC模态行失败和e_K余项。改变物理模型不保证这些风险消失，旧失败仍保留；但**不要求先完成旧模型四B诊断才允许新模型直接法**。不自动在旧物理上启动新heavy。新模型相关错误优先用13.5 nm直接参考及同次捕获定位。

所有新dat/model_id、QEP路径、比较组、结果根与预算都用本任务身份；已有Task041文件不改名冒充新场。更改几何/入射后重新生成QEP、source、矩阵与配置hash；只有同一新物理/离散/模式身份内的direct/iterative可验证复用packet。固定p或参考单元kernel缓存仅在其真实数学cache key相同后复用。

## 4. 路线与执行顺序

### A0：一次轻量物理/入口检查

先生成本任务的独立输入和冻结材料记录，验证边界拟合网格确实包含x=16.5/33.5、y=15/35、z=0/120及Hybrid接口；材料体积、中心、基底和中段截面一致。至少核对实际k/E/H、x/y周期复因子、完整external keys和新二维截面。沿现有入口做最小正/负例：phi0与90不可混同、y20不可退成y50、旧packet不可被新model接受。保留实际argv而不只测dict。

不得为新任务复制service/supervisor/validator全栈。沿已有参数入口和少量case注册扩展；共享资源公式参数化，旧Task041行为保留。不先做新的监控或账目框架，不要求旧测试全量重跑。

### A1：先交付13.5 nm Full3D直接法参考

完整50×50×140 nm计算域，W材料、1°/90°/s，p6/h10起步。用已有**Full3D assembly-time static-condensed direct/MUMPS**路径，MPI8×1；它不依赖内部M，是检验新几何、源和物理输出的独立参考。全过程资源准入通过后，连续求解、原残差、恢复与完整输出；先得到此结果再作Hybrid性能评价。

首场只是该h/p的离散参考，不宣称网格收敛。直接法资源不足时先列具体装配/填充/工作区对象，不能静默降低p、改角度、删级或以近似PC冒充直接法。本阶段cap见§7，h10若不满足边界分辨/端口alias则在同物理下改为更细的合法h，写新dat和变更理由。

### A2：同13.5 nm建立Hybrid直接参考，再上迭代

使用相同几何/材料/边界/p6及可比网格，生成新二维截面QEP，初始M=120。中段长度保持100 nm，传播模型沿已有full3d_uniform_cg；局部traction单元必须与本次实际轴向离散一致，不能沿用旧pilot的20/29 nm。用现有Hybrid直接路径解该M的同一Hybrid方程，不把exact-side迭代一步称为直接法。与Full3D比较用于检验Hybrid近似；与下阶段比较则隔离线性求解器差异。

M120仅是起点。如Hybrid–Full3D或相邻M未达到§6的离散比较门，允许按120→180→240各一次继续，且候选空间必须足够；不要为换M重复Full3D。仍不满足时给出模态截断、传播/traction或FE分辨的具体差异，不把线性残差小包装成参考已闭合。新几何h10→7.5的一次必要p/h检查可在首轮闭合后执行；它不要求把13.5 nm做成无限收敛研究。

### B：13.5 nm验证继承的迭代思路

主候选沿Task041最新的一致固定BAL_H块预条件器：p6和p4双层准确凝聚；B借用p4/H6/A6，所有LDU位置使用同一定义；构造近似S_B=C-LBG并用小型LU；外层RIGHT FGMRES仍解原Hybrid A/f。它改变预条件器而非物理方程，双凝聚本身不保证步数下降。[S2]

```math
y=Br_s,\quad S_Ba=r_m-Ly,\quad z_s=y-BGa,\qquad Lz_s+Ca=r_m\quad(\text{exact arithmetic}).
```

普通p4 owner保留target=5e-13、最多两次精化；固定B中的每次Q仍采用继承的一次固定数学修正及原exact-zero审计，不用按容差变次数的求解冒充固定线性作用。

同13.5 nm Hybrid direct共用新合格packet和同离散身份，保存原A残差、完整场、逐级复幅和时间/RSS。原V15逐分量行门与A4/owner检查保持，不在新任务中悄悄移除；若失败，先与同一方程直接参考区分算子/捕获问题与PC舍入问题。外层先restart32、max_it=600；到上限不算成功。仅有完成周期的重启损失证据时，可在同一factor生命周期安全返回后一次改restart64，总累计上限1200；不扫描更多PC或把side128/modal32嵌套自动加回。

首个受测PC作用就具备最少销毁前现场：本次r、y/q覆盖前副本、g/a/z、原A与PC独立C、S_B、完整side分界和mode映射；失败时保存本次最坏行及控制行的实际L系数。使用现有捕获机制薄扩展，限定取证额外驻留，不在每步保存全场或额外调用B。旧行259不是新任务固定错误行。因子活着时完成受限真实分析，不能因字段或日志错误先清场再取证；捕获失败与数值失败分列。

**A/B必要门通过后，直接推进C，不再向用户申请相同范围。** W5弱级旧问题延期、旧4B捕获以及5/2 nm均不是前置。

### C：直接进入0.7 nm，但不盲用旧h/M

物理几何仍为50×50、17×20、高120、接口10/110，方位90°。**不得自行缩成10×5或10×10 nm，不改变y宽/高度来获得通过；粗网格的同物理诊断也不得称精度达标。**

先把13.5 nm实测对象尺寸与0.7 nm解析/实际通道盘点用于容量规划。允许一场本几何的分阶段mesh/空间/trace及symbolic sizing；不要求先知道整场实测峰才做所有准备，但每笔大分配前须有当前驻留、新增对象和余量。禁止h0.70/M400从旧pilot直接copy；按端口分辨、实际二维QEP维度/候选谱和预算选择首个h_0/M_0，并在独立dat与admission记录中明确冻结。

候选h可从2.0、1.5、1.0、0.7 nm的粗到细有序集合中选择，**集合不是四场自动计算授权，也不保证最粗点可满足端口分辨或精度**。先排除不满足trace/alias的点，再选资源可支付者。M_0由实际新横截面候选和所需模式覆盖决定，不按外通道数直接相等，也不能用“M还未知”无限停工；提交候选维度、拟选M、模式质量与bytes后由主控在本任务范围冻结首场。若无候选可同时满足数值准入与容量，给出具体瓶颈对象和缺额，不盲factor。

对准入通过的首场：新QEP producer → packet验证 → 新迭代consumer → 原残差 → recovery → E/H/R/T/A/A_volume/全部衍射 → cleanup连续执行。有效新QEP不因consumer字段/后处理失败重求。S_B前少量列直接计入最终构建；完整各块ready后不主动结束。0.7 nm不得全局p6/Hybrid直接factor；允许已有准确p4凝聚因子且须实测填充成本。

首场原方程通过后，允许分别一个M加密点（约1.5M并满足模式库存）及一个h细化点（约0.75h、边界拟合），每次只改一个离散变量并独立dat。这些变化会产生新QEP/矩阵身份。精度未达到时保留best available discrete reference，不宣称2 TB/48 h目标通过。

## 5. 新物理意味着通道/资源显著变化，不承诺自动变容易

新y宽有限使x/y双向模态耦合真实存在；方位角改变可能改变PC表现，但没有证据保证更快。旧5 nm16.64 h、旧pilot约50 GB只能作历史经验，不能作为新50×50模型的预测或预算。

0.7 nm首场前至少列：两侧p6/trace和p4凝聚rows/NNZ；local/traction与global p4的symbolic/numeric估计；DtN辅助行与耦合载荷；QEP工作空间、选择模式与MPI复制；C/S_B及LU；FGMRES基；恢复包及全过程并存。S_B为2M×2M，仅一个complex128数组是64M² bytes，LU工作和副本另算；不得只报告小S_B而忽略端口/QEP。

如旧显式数据路径在完整二维外通道下成为明确最大对象，可提出针对该对象的streaming/matrix-free等价改动；本轮不预先重写全栈，也不借“0.7 nm困难”退回原y贯通物理。新数学方法、近似材料或删通道需要后续明确review。

## 6. 数值、物理与对照Gate

Gate分层，防止把不同离散之间的差异当线性求解bug：

| 检查 | 要求与口径 |
|---|---|
| 原方程 | direct独立原Ax-f相对残差≤5e-9；Hybrid的reported/global/bottom/top/modal五项各≤5e-9，沿原已定义分母；非有限或原A不一致直接拒绝 |
| 组件 | 原A4 physical/augmented与owner原S_B残差≤1e-10；V15行合同≤1e-10不变；不能用整体eta_2替代逐行判定 |
| 接口/端口 | 原traction/projection门≤1e-8，external source/端口一致性≤1e-10；采用全部合法外部keys，无旧单向捷径 |
| 物理 | 归一化能量闭合与A-A_volume绝对差≤1e-5；输出复E/H、canonical、模态与端口幅度、R/T/A、体吸收和全部级 |
| 同Hybrid离散direct–iterative | R/T/A/A_volume绝对差≤1e-7；完整E/H与canonical相对L2≤1e-6；参考功率≥1e-8的级，复幅/功率相对差≤1e-6；低于该线的级仍输出绝对误差，不删除 |
| Full3D–Hybrid及相邻h/M | 作为离散资格而非同矩阵等价：R/T/A/A_volume绝对差≤1e-4；显著级复幅/功率相对差≤1e-3；E≤5e-3、H≤1e-2；独立记录端口截断和网格差异 |
| 近零与相位 | 原比较定义不临时加max(norm,1)或任意atol；明确绝对/相对与相位基准；无自由phase fit、删弱行或抬显著floor |

以上是新任务验收计划，不是已测精度。直接参考若自身网格/端口未通过资格，不能用其差值判迭代一定错误。13.5 nm同矩阵对照通过后可进入0.7 nm首场研究，同时保留未完成的连续体精度边界；最终目标通过必须同时有必要h/M/端口资格。

普通实现缺陷允许保存失败后最小修复、定向测试再继续；**原数值门失败不能因“想快点出结果”改成成功**。如新模型V15失败，利用已存或现存因子的四B/投影现场与直接参考定向定位，不先重算整场；判据合同更改须另行论证。首场直接法输出不因此作废或重跑。

## 7. 资源政策与48小时

继续MPI8×1、原生一致ABI、complex128、system_default_unbound；不修BIOS、不拆DIMM、不更改未资格硬件设置。显式请求8个不同物理核并核验，不从旧map推断当前可用CPU。一次一个heavy，不干扰邻任务。swap仅观测，不单独拒绝或判失败，不以swap充当物理RAM。

本任务不沿用旧80 GiB pilot上限。设宿主保留R=384 GiB，新任务总作业上界为：

```math
C_{\max}=\min(1.5\,\mathrm{TiB},\;\mathrm{MemTotal}-R),\qquad
J=\max(\mathrm{RSS}_{tree},\;\mathrm{memory.current}_{job}).
```

有效祖先cgroup独立约束，不与host空闲相加。13.5 nm默认作业cap取min(256 GiB,C_max)；0.7 nm每场根据对象预算冻结cap≤C_max，不能自动按上界全占。warning=0.9cap；不确定性缓冲W=max(8 GiB,0.05cap)，额外工作区有实际估计时显式计入Delta，不用W替代未知大factor。各阶段要求：

```math
J+\Delta+W\le C,\qquad
\mathrm{MemAvailable}\ge R+\Delta+W,\qquad
\text{each finite ancestor headroom}\ge\Delta+W.
```

这是一份明确的新任务预算授权，不修改Task041旧记录。作业启动时不要求无条件预留全部C闲置；按初始已知新增需求与余量准入，所有大分配继续分级。J内已有对象不重复扣除；MemAvailable用内核字节口径，MemFree、页分布和swap仅记录。RSS不是derived bytes、symbolic估计不是实测numeric峰；分开报告。80 GiB、2 TB、2 TiB不得混用；C_max按实测MemTotal算而非宣传容量。

```math
T_{cold}=T_{QEP}+T_{setup}+T_{S_B}+T_{outer}+T_{recovery}+T_{check/cleanup}\le48\ \mathrm{h}.
```

48 h为成功目标而非到点强杀线。保存warm consumer、实测fresh cold、用原producer加本次warm的组合估计、研发重试费用四种口径；失败producer消耗不伪装成成功运行。若外层有有效下降可继续取得结果，但超48 h须明确未达；未下降时不无界跑数千步来拖延结论。

## 8. 授权、停止与重试

新任务允许主控按上述条件连续执行，不逐项再向用户申请同一范围：A0；A1一个Full3D直接场；A2初始M120及至多两个必要M提升；B一个主迭代场与一次有证据的同factor重启调整；C一个分级容量实例、一个对应fresh producer及一个完整主consumer；成功后各一个必要M/h确认点。各物理实例独立dat与预算。实际不需要的试验标not_run，不为凑数运行。

每个主物理实例最多另一次已定位实现bug后的必要重建，必须先有失败现场和轻量复现修复；没有大型装配/分解的脚手架错误不消耗科学实例次数，但相同根因两次后禁止第三次原样dispatch。资源不可支付、未知原数值错误、ABI失败、磁盘/OOM/真实硬件异常停止受影响大阶段，其他独立安全工作继续。PC未收敛不是目录bug；旧二维假设导致的方程错误更不能靠放宽残差跳过。

若有原行拒绝，当前所有中间量必须在销毁前保存；不知道该数据是否足够就先保存一次有界的原C/S_B、L关键行、side ranges和r/y/q/g/a/z，再释放。后处理/字段修复优先读恢复包，不能重新QEP/factor/solve。没有真实误差闭环，不把“单次捕获完成”报告为PDE PASS。

## 9. 文件、提交和交付

只在本分支普通commit/push，不amend、force-push或merge master，不修改旧review或全局工作原则。本轮允许新task opt-in入口及必要通用参数修复，不改ordinary默认、不把算法写在一次性runner里。

Codex生成的计划输入根为`input/official/task42hybrid_az90_50x50_17x20_0p7nm/`：13.5 nm Full3D direct、Hybrid direct、Hybrid BAL_H分别独立dat；0.7 nm文件名必须包含实际h/M。kind和参数用现有合法schema，确需接线就先最小实现/测试，不能在dat写不存在的选项后称已就绪。不要仅靠改Task041 model_id绕过其白名单；新task注册保持独立来源。

任务结果位于本目录`outcomes/`；大工件进入独立ignored `results/task42hybrid_az90_50x50_17x20_0p7nm/`。必须绑定input_original、resolved_config、input/physical/numerical SHA、run_manifest、runtime source、环境/ABI、MPI/线程、全阶段资源、artifact hash；相同物理不同求解器的身份与相同求解器不同网格的身份分别定义。

建议提交分为三组：新物理注册/材料/入射与网格测试；13.5 nm直接与迭代结果；0.7 nm准备/阶段容量/完整结果。按阶段及时推轻量状态，不等整轮结束才告诉用户哪一步；沿现有状态机制更新，不新增或重启已停用提醒timer。

首份`response_v1.md`必须优先展示：新几何坐标与k/E/H；13.5 nm直接法的复E/H、R/T/A/A_volume、衍射、DOF/资源；Hybrid与迭代对照及差异；0.7 nm实际到达阶段、h/M/通道数、连续原残差与主要成本。若尚无场，写唯一具体阻塞和数值，不以“测试通过很多”代替进展。同步本任务summary/test_summary及仓库development_progress/model_registry，但不覆盖旧Task041事实。

**最终边界：**新任务从物理参考开始，不是从零重写程序；改入射不使旧数值失败自动消失。先产出正确13.5 nm直接解，再让同一方法在正确0.7 nm模型上接受实际检验。没有相应证据，不宣称2 TB、48 h、网格收敛或任意三维能力通过。

## 10. 固定来源与技术参考

- [R1 Task041原完整目标与高度](https://github.com/Rookie1234567/MyFEniCS/blob/94700f95f2bef02e2359e6ca89872c11e65978fb/docs/task041_mpi1_shortwave_hybrid_capacity/task.md)。
- [R2 Task041最新回应](https://github.com/Rookie1234567/MyFEniCS/blob/94700f95f2bef02e2359e6ca89872c11e65978fb/docs/task041_mpi1_shortwave_hybrid_capacity/response_v19.md)与[Review V19](https://github.com/Rookie1234567/MyFEniCS/blob/94700f95f2bef02e2359e6ca89872c11e65978fb/docs/task041_mpi1_shortwave_hybrid_capacity/review_report_v19.md)：原e_K与4B诊断边界。
- [R3 旧13.5 nm输入实际为Si](https://github.com/Rookie1234567/MyFEniCS/blob/94700f95f2bef02e2359e6ca89872c11e65978fb/input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_cell_condensed.dat)。
- [R4 旧0.7 nm缩减W输入与材料值](https://github.com/Rookie1234567/MyFEniCS/blob/94700f95f2bef02e2359e6ca89872c11e65978fb/input/official/task041/side_balh/w0p7nm_p6h0p70_m400_mpi8_cell_condensed_pilot.dat)。
- [R5 坐标和极角约定](https://github.com/Rookie1234567/MyFEniCS/blob/94700f95f2bef02e2359e6ca89872c11e65978fb/src/common/config_3d.py)。
- [S1 CXRO折射率查询](https://henke.lbl.gov/optical_constants/getdb2.html)：化学式、密度、能量/波长条件需固定；不代表本任务已经取得W13.5正式数据。
- [S2 PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：保持RIGHT FGMRES；允许不精确PC不等于保证收敛，在线文档不授权升级本机ABI。
