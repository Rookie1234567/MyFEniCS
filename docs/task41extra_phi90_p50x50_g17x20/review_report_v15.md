# Task41extra Review V15：有条件准入一次全域两列验收

## 0. 裁决与固定身份

**接受V14两个完整保存star、八个唯一RHS的局部候选和独立Decimal补充复核。技术上批准同一个候选进入至多一次必要的全域action/recovery验收，不继续扩大局部归因。此批准是受控实验准入，不是全域PASS或立即启动许可：先补齐真实合同、终态审核、完整内存/时间/证据预算；新固定窗口由用户一次明确批准后才能运行。**

本轮消除的blocker：局部RHS校正已有效，但尚不知道它能否使原两列完整向量同时通过。全域owner已退出，保存包不能代替全域LU/K/J，因此在准入成立时重建一次有明确必要性；不是重复旧失败方法或再做局部筛选。原完整场、最终精度、2 TB/48 h目标仍未通过。

| 身份 | 固定值 |
|---|---|
| 仓库／执行分支 | `Rookie1234567/MyFEniCS`／`task41extra_phi90_p50x50_g17x20` |
| 本次被审结果HEAD | `de2353b9ce46fbbb2c6fd4498ea24139b39d162f`；开始审阅时远端一致 |
| 最终生产接线source | `eb57f88f26fb3cbbe0d7c34ebb725f9a6b310fe1` |
| 上份review | `5707187055d79083879b69f41fc2c9c084f70ff0`／Review V14 |
| 原全域失败 | V9 source `59722cca5e35eac65efead9fd27f7d7fc0c70419`，run `20261022T052401.200732Z` |
| 日期／问题类别 | 2026-10-25，Asia/Singapore；数值一致性、资源与正式执行接线 |
| 物理冻结 | 原0.7 nm、50×50×140 nm域、居中17×20×120 nm Si、方位90°、掠角1°、S、无缺口、p6、10×200×14、64,120模式 |

已核对response、证据与成本索引、最新summary、相关测试记录、V14→结果与科学source→结果差异、实际核心/reducer/recovery/dispatcher/compact验收源码；根AGENTS、docs规则、工作原则、task及V14继续有效。科学source之后只有一笔文档/证据收口提交；不能把先前科学运行重新署名为最终接线source。原始大数组、服务日志及部分checker报告留在工作站ignored目录，本Chat没有重读它们；本次接收依据是远端结果、明确hash索引及源码交叉核对，不声称重新执行科学检查。[R1][R2][R3][R4][C1][C2][C3]

## 1. 接收结果与仍未证明的事项

| 保存star／列 | 原目标行绝对d | 校正后绝对d | 原值/新值，派生 |
|---|---:|---:|---:|
| 360/446，0 | 4.714842990596683e-9 | 2.038566996070134e-10 | 23.13 |
| 360/446，1 | 1.018211453698345e-8 | 4.684649807421053e-10 | 21.74 |
| 23352/23493，0 | 8.305744689149506e-10 | 8.745466676409231e-11 | 9.50 |
| 23352/23493，1 | 1.7692662680591898e-9 | 2.8094269677463915e-10 | 6.30 |

这些是两个完整star目标行的自身误差，不是各cell独立全域误差。四cell×两列共八个唯一RHS，8次初解＋16次校正；j0/j3复用RHS。全部内部行的Decimal独立残差支持可信下降；原wide INCONCLUSIVE、attempt05身份不等式错误及补检结果分别保留。Decimal没有参与生产校正，也没有重复求解。[R1][R2][R3]

四个cell覆盖两种tag和两种方向；八代表键缺candidate LU/pivots及原始内部RHS映射，不能转授资格。**不再为了补齐这八键单独积分或分解；接受其覆盖局限，把全域原两列作为下一层正式否决试验。**这是有限风险下的实验裁决，不是统计外推。仍可能出现其他类别、累加或矩阵一致性问题，局部改善不能保证全域1e-11。

V9完整action仍约2.67497706372e-10／5.61359812004e-10，门1e-11；V9恢复NOT_RUN_ACTION_GATE_FAILED，V6历史初次恢复FAIL与donor恢复PASS分列。两组star、旧八键evaluator资格、A1/A2、carrier生成及64,120模式验收均不重跑。

五个有回执service父段合计221.4241482896236 s；窗口提交前快照10771.817644471404 s包含实现、等待、测试、服务等，不能相加。最大tree RSS667,795,456 B、最大task cgroup497,860,608 B不是同一口径；task swap0；发布后及无收据工程费用仍UNKNOWN。最终7项测试证明窄接线回归，不是工作站全域资格。[R2][R3]

## 2. 本次唯一算法与需要补齐的P0

### 2.1 算法冻结，不再提出第二候选

沿实际V14核心：`same_lu_rhs_solve`、`refinement_max_steps=2`，原actual/oriented K、同一LU、binary64实虚乘积＋`math.fsum`残差、complex128更新；零RHS/精确零残差/更新不变的既有停止规则不改；最终返回真实z及完整−Jz。S/R/T/J、evaluator、native、原known/RHS、积分、MPC顺序、材料和全部误差门不改。宽算术/Decimal只用于独立审核，不进入生产校正。[C1]

生产`reduce_rhs`使用返回correction，Di消费同一个最终z；`recover_storage`的内部RHS也使用相同策略。现有最多三次独立native内部恢复修正仍是另一层，不增加次数、不把每次恢复修正再递归套两次RHS精化。旧stored_T与未精化same-LU默认、旧缓存和历史报告继续只读兼容。[C2]

### 2.2 三项必要接线，不能只改一个full_owner布尔值

**P0-A：真实全域合同。** 当前dispatcher仍只允许V9/V14窗口，二次校正又只绑定V14 saved-candidate scope；worker明确拒绝该scope创建full owner。该守卫正确保护旧授权，但意味着当前代码不能直接用于新全域运行。由现有prepare/service/dispatcher/worker统一接入一个新、明确获准的全域scope与窗口实例；绑定模型、DAT、source、refinement策略、次数、实际K/LU身份、输出根和收口路径。新scope与旧saved-only scope分开，拒绝拿V14合同或任意`full_owner=true`绕过校验；不复制一套V15服务框架、不写死attempt号。[C3]

旧producer/source/window/数组hash不改；新consumer引用它们。旧window用于数据来源审核，不要求它现在有效，也不追加旧账。实际运行读取新window。首次imports、ABI、必要输入读取等正式准备均计入新T0；纯开发/小fixture费用另记工程账。

**P0-B：完整产品及终态checker。** 复用现有compact volume验证和失败补审能力，明确保存本次`refinement_max_steps=2`、残差策略、K/LU来源及实际计数；只写`same_lu_rhs_solve`不足以区分旧未精化结果。不要错误要求checker source一定不同于producer，也不能默认相同source便是同一科学产品。

正式service对action FAIL、recovery FAIL、PASS以及部分产品都能选取本run真实manifest/summary/compact执行受监督终态审核，不要求先存在成功的物理场目录，不借旧snapshot、不造官方输出。`audit_completed`、`data_integrity`、`action_passed`、`recovery_passed`和`official_result=false`分列；验收成功仍不是完整场official PASS。独立checker从数组重算原分母与门，不只读status。

**P0-C：同一owner生命周期。** 已实现并通过测试的原K/J只读共享、K-LU身份、target/reference/recovery传播与borrower清理不重新开发。补一个最小真实调用链fixture：新合同→dispatcher→实际owner/action构造参数→两列验收→终态路由→借用/释放；仅昂贵内核替身化，不mock掉修改的身份传递。检查合格owner交接不会先释放再调用builder；失败也不因checker读取问题启动第二次构建。

最终只重验修改相关节点与V14直接受影响的7项，不全仓pytest、不重装环境、不做目录整理。准备阶段允许普通工程bug定向修复并继续；源码冻结、实际命令、资源/证据准入及窗口批准缺一不可。

## 3. 一次全域验收的唯一顺序

### A. 准入与一次owner构建

先核旧产品完整性和实际全域缓存库存。当前没有live owner；若没有完整可重开缓存，允许一次必要`mesh_actual_exact + actual_qmetric_blocked_gram`的28,000键构建，保留同一张量产生的K/J/LU/R/T/S。FE/MPC/native volume对象按实际需要新建，不重复surface/carrier准备，不走完整模式积分前缀。

旧八键资格继承；构建中遇到这些键时，只核身份/数值绑定并复用正常生产结果，不另做八键资格运行、不调用慢FFCx oracle。每键raw/oriented临时张量及时释放，K/J不能用view意外持有整个882² backing；相同key只一份。构建过程记录新增键数、阶段父钟和kernel/LU/Schur/映射/身份/IO子时钟，定期刷新真实RSS和剩余工作预算。不能再把全部owner时间笼统归于LU或张量生成。

本次首批正常构建结果就是正式owner的一部分，不能为测速建一遍、销毁再建。既有V6/V9准备成本差异较大，沿途实测更新预测；预测不是RSS或完成时间保证，不设置新的600秒等任意阶段强杀。

### B. 原两列完整action门，先于恢复

用原known active trace，实际新生产体积S作用与`reduce_rhs`分别求y/g；不是直接把旧y复制为新体积输出。旧端口作用、port RHS和当前Bi/Di支持资格可严格继承，仅读对应两个B帧／已保存Bα，MPC、Bα、全局b_t各处理一次，不再做64,120模式验收遍历。

完整两列布局保持[5,752,120,2] complex128；原D0=2225.481253487629、D1=2225.4807123031883。每列完成即持久化或以带完成列标记的原子记录保全；不在第二列失败时丢第一列。完整两列门判定前保存两份y/g并回读hash：

```math
\frac{\lVert y_j-g_j\rVert_2}{\max(\lVert y_j\rVert_2,\lVert g_j\rVert_2,\mathrm{tiny})}\le10^{-11},
\qquad \frac{\lVert y_j-g_j\rVert_2}{D_j}\le10^{-11},\quad j=0,1.
```

完整向量有限、maps相同、port输出不变，trace/port各自误差与最大行同时记录；新y与既有同S/input输出作绑定核查。有差不能直接归因于RHS校正，保持真实结果并查最小身份/实现变化。不能用局部改进倍数、candidate/reference gap、known答案或保存差向量补y/g。

任何一列真实超门：保存两列产品及明确FAIL；recovery标NOT_RUN_ACTION_GATE_FAILED，200q及所有依赖不运行。可在仍live的owner中按已准入的小额空间保存最多4个主导关联cell的现有K/J/LU/R/T/S与映射/输入，**只取证、不新积分、不新候选**；没有保存的G/L不反推冒充原块。随后独立审核和清场，不启动第二个全域owner。

### C. 同一owner的candidate恢复门

仅action两列通过后，按原trace、alpha和full RHS恢复两列本候选场。原内部RHS初解最多两次补偿残差校正；后续按已有独立native volume残差作最多三次全场内部恢复修正，保持原停止规则。known场仅作forward检查，不能驱动更新或择优选状态。

保持forward≤1e-11、独立native volume residual≤1e-10、active trace不变、slave及残差slave约束。原相位、分母和端口内部支持不变。每列在最终判门前保存实际终态及独立native作用或可复算残差、真实迭代计数/阶段记录；超门同样保存，不借donor PASS转授。必要的独立native体积作用允许执行，禁止用candidate局部K作用作为唯一oracle，也不为此读取全carrier。

### D. 独立审核与产品状态

复用同一native对象的已有独立核验接口及受监督的保存终态checker。前者对实际新恢复场作独立体积作用，后者重读新产品核范数、门、身份和计数；不再次求解或重新建立owner。保存完毕的数值产品遇普通checker/输出错误，修读取路径再审核，保留原producer source；科学核心改变才会使相关资格失效。

两列action、candidate recovery和独立核验全部通过时，只给`FULL_ACTION_RECOVERY_QUALIFIED`；仍`official_result=false`，因为没有真实目标入射场。随后按第7节的预先授权与对象账交接，不能凭这一标签自动运行200q。

## 4. 完整共驻内存准入

保留的局部数值载荷推导为526,373,172,000 B，其中新增原K为90,720,000,000 B。它不是RSS，不包括全部FE/MPC、缓存元数据、端口页、临时工作、输出与checker。V9旧峰值约450.37 GB也不能简单加90.72 GB就作为保证。[R1][R3]

启动前按生命周期给对象账：原K/J/LU/R/T/S及身份/映射；必要native与FE/MPC；donor当前驻留页及checksum缓冲；端口偏移/两个B帧；新y/g、恢复、native作用、工作缓冲、保存和checker。共享backing只计一次，mmap触页计内存；严禁整体复制旧363.79 GB carrier或因便利保留全raw张量缓存。独立checker与live owner共存的峰值必须计入。

阶段A账不需要假造尚未批准的200q因子空间；若计划同进程进入下游，则另列参考FE/映射/local caches、逐q CSR/PETSc输入/转换/因子、Krylov、端口action及输出的联合账。未知对象不得填零，不能把q0×200当实测。

同时满足真实host余量、task cgroup和所有ancestor限制；cap≤1,649,267,441,664 B，host reserve≥68,719,476,736 B，task reserve按既有0，task tree/cgroup swap0。仍沿已修正的分域资源规则，不再次从更紧cgroup余量扣host reserve；其他工作站任务和磁盘实时读回，不停止邻任务或提高cap。

## 5. 时间预算：两列action与恢复都要计补偿残差

每个非零内部RHS两次补偿残差合计实测0.117–0.183 s，不能拿GETRS时间代替完整成本。下表只是按28,000个cell均有非零RHS的容量情景，不是全域实测上/下界；实际受内存、布局、验证等影响可超出。[R1][R3]

| 工作 | 情景推导 |
|---|---:|
| 一个全域RHS的一对补偿残差 | 3,276–5,124 s |
| 两列action的两轮RHS缩减 | 6,552–10,248 s，即1.82–2.85 h |
| 两列action加两列初次恢复，共四轮 | 13,104–20,496 s，即3.64–5.69 h |
| 仅V9 owner父成本18.95 h加上述四轮 | 约22.59–24.65 h，尚不含本轮其他新增工作 |

还要加入必要准备、K保留/校验、S作用、GETRS/J/scatter、最多三次恢复校正、native体积作用、保存hash、独立checker与清场；不能用旧19.44 h workflow再加已包含的旧子阶段。构建中的strict-LU、多RHS R/T构造另计，不能混入本次RHS GETRS账。

全部非零且无提前停止的情景中：action两列最多168,000 GETRS，初次恢复两列最多168,000，三次全场内部恢复修正两列另最多168,000；真实为零RHS和提前停止按实际记录，不强凑计数。恢复修正没有自动嵌套两次RHS校正。

**建议新36小时窗口**：总129,600 s，数值128,400 s，收口1,200 s。24小时按上述已知成本已可能不足，不能靠压缩检查来凑数。36小时是验收包的上限提案，不是完成承诺，更不改变最终冷流程48小时目标；旧carrier生成、必要JIT等生产首算费用仍计入最终cold账，不能被本次warm复用隐藏。

无需再做独立前缀性能试验；在这唯一owner构建和正式两列处理内分阶段计时、分批记录进度，动态判断剩余构建及验收是否可完成。真实准入拒绝或受控停止与数值FAIL分开。普通接口修复不刷新本窗T0，也不能因为旧阶段已完成便把其费用从账中删除。

## 6. 启动前解决证据配额，不能在长算结束时才失败

现有compact函数把预留固定为2,144,274,944 B（含既有保守元数据预留），并强制等于该常量；这是两份完整action数组加最多六份full-storage向量。当前累计证据已增加，必须实读余量，不从旧快照猜测。正式full_rows=18,501,024，单份complex128全场纯载荷296,016,384 B。[C4]

优先复用已有布局。若累计16 GiB容不下原预留，允许在同一compact/checker内加入一个明确的**终态充分证据布局**，不改变数值门：原known/native RHS/maps全部引用旧hash；新y/g两份纯载荷368,135,680 B；每列新最终恢复场及相应独立native作用各一份，总四份full-storage载荷1,184,065,536 B。合计1,552,201,216 B，另计NPY头、manifest、日志和失败取证。这是布局推导，不是已存在的存储文件。

残差由保存native RHS减新native作用独立重算，不再额外保存同一全长残差/差向量。初态与中间修正记录保留原范数、实际次数、hash和时间；最终／提前失败的实际状态在判门前保存。此布局不宣称独立重算未保存的每个中间场；终态forward、native残差、trace/slave等正式门仍由完整数组复算。旧六向量布局及旧报告保持兼容，不删除原证据或偷偷放宽16 GiB。

如果新最小布局、必要日志/失败缓冲也不能在当前配额与2 GiB磁盘底线内准入，重型运行不启动，明确实际字节缺口并请求针对性存储授权；不能默许删负结果。新布局的PASS、数值FAIL和中途异常保存必须在小fixture里走通，再启动owner。对结束时仍live的owner，不向每个cell永久保留每次fsum中间向量；汇总计数与有界诊断已足够。

## 7. 窗口授权与成功后的owner去向

V14 T0是2026-10-25T08:47:53Z，数值/总截止是2026-10-25T14:27:53Z／14:47:53Z（新加坡22:27:53／22:47:53）。审阅时间快照为2026-10-25 20:03:12新加坡时间；彼时墙钟尚未截止，但已经收口且scope仅允许保存包，**不能用其剩余时段启动本次全域任务**。不得误写为“当时已超时”，也不复活或刷新旧窗。

新36小时窗状态`PENDING_USER_APPROVAL`。本review给的是单次全域验收技术许可，执行仍需用户一次明确批准。先完成P0、实际DAT/prepare/service命令、source冻结和预算；获准后从首项必要正式准备开始新T0，绑定旧费用链。准备开发账另留，旧工作不重署名。主机仍为`fenics-ws:/home/fenics/Projects/laptop_share`，项目名和对话不变。

为避免通过后才临时讨论、最终丢掉live owner，**重型启动前必须选择并记录成功出口**：

- 仅获准验收：完成独立产品后按合同释放，明确这是授权边界内的必要收口，不假称owner可持久复用。将以后重建的费用风险写入后续计划。
- 一并明确批准条件下游：在同一窗口内，action/recovery/checker全部PASS且target/reference共驻账、时间与已有物理身份资格均准入时，现有交接直接消费同一owner，才可依序200q CSR/native、exact因子两RHS、完整参考及条件原尺寸target。57个空端口q保留FE；逐级原门不省略；未知下游账不填零。

**本次默认scope止于全域验收，不自动批准下游。** 用户可在这一次启动授权中同时选择条件下游，不能由Codex自行解释为已批准。未获准下游不为了保留内存无限等待或跨截止；已获准则不无谓destroy/rebuild。此处是复用已有owner接口，不开发新后台运行／通用checkpoint系统。

## 8. 失败出口与提交要求

身份/ABI/资源/证据/时间未准入：`NOT_ADMITTED`，不宣称新数学失败。开始构建后安全门触发则受控停止，保全已完成产品并如实说明owner是否仍有效；一次全域重建额度不因改attempt名自动重置。

真实action/recovery失败：保留完整向量、原分母、实际修正次数及局部库存身份，结束依赖链；不回退stored_T制造PASS、不追加第三次RHS校正或第四次恢复修正，不更换native／积分／网格／模式／精度，不串行尝试第二算法。

checker/JSON/path故障：优先保存数值产品并只读修复；可在同一有效窗内对普通工程问题继续，不重跑已完成数值。源码改变科学核心或进程丢失且无合法完整缓存时，不假称可复用live owner；若需要第二次完整构建，需新的明确决策。

提交计划：先一笔窄P0及必要定向回归、冻结；正式运行后提交`response_v15.md`、compact、独立审核、真实source/window/输入身份、每阶段产物与资源时间账，更新summary/run_index/test_summary及两级总账。各次科学source原样保留，正式场未有就不写R/T/A。ChatGPT只新增本review；Codex实现/测试/执行，主控集中推本分支；不改master、其他任务或自动合并。

首屏应回答：一次owner是否完成；两列动态/冻结误差；candidate恢复及终态checker状态；K/J实际库存和同时RSS；完整父成本及fsum/GETRS/native分项；是否已获准并进入下游。不要再以测试数或局部改善替代本轮全域结果。

## 9. 给Codex的执行摘要

```text
读取同分支review_report_v15.md。结果base=de2353b9ce46fbbb2c6fd4498ea24139b39d162f，最终接线base=eb57f88f26fb3cbbe0d7c34ebb725f9a6b310fe1。
接受V14两个完整保存star、8 RHS及独立Decimal复核，不重复局部筛选/归因。
技术上准入至多一次必要全域验收；不等于全域PASS或已批准新窗口。

先补真实全域scope：现dispatcher仍锁V9/V14窗口，refinement=2仍只绑定saved scope。
在现有prepare/service/dispatcher/worker贯通新授权实例，绑定ref2、原残差策略、
K/LU身份及实际输出。保留旧scope拒绝full owner的规则，不能改布尔值绕过。
补compact实际策略记录、完整PASS/FAIL终态路由和同进程owner交接测试。
不要复制V15框架或重做已通过的K/J/Di/清理设计；只跑受影响定向测试。

P0完成、源码冻结、新窗口获准且三账准入后，至多一次actual-qmetric owner构建。
原S/R/T/J/native/积分/输入/RHS/MPC不变，K/J只读同源共享，raw工作区及时释放。
复用旧known/native RHS/maps/carrier资格和未改port输出，仅读两个B帧；
不重跑A1/A2、旧八键资格、carrier生成或64,120模式验收扫描。

同一owner先实际求原两列完整y/g并判门前保存，动态及冻结分母均<=1e-11。
两列通过后才验candidate自身恢复：RHS至多两次fsum同LU校正，原native内部
恢复至多三次；forward<=1e-11、native volume residual<=1e-10、trace/slave门。
独立终态checker读取本run产物，不要求成功物理输出目录、不借旧snapshot。
任何真实数值失败保全并停止依赖；普通checker/输出错误只读修复不重建。

提前核全对象账：526373172000 B是局部纯载荷推导，不是RSS。原cap/reserve、
ABI/线程/swap0不变。fsum在action和初次恢复都要计费；不能只按GETRS估时。
按真实累计证据准入；原compact约2.144GB预留不足时，按review终态充分布局
保存新y/g、两列终态及新native作用，纯载荷约1.552GB，另留日志和失败空间。
旧数据只引用，不删除历史；16GiB仍不足就明确缺口，不先长跑后丢证据。

建议新36h窗129600/128400/1200秒，待用户一次明确批准，不刷新V14旧T0。
首项必要正式准备开始计新窗。重型启动前明确成功出口：默认仅全域验收；
若用户同时批准条件下游且完整共驻账/余时准入，全部门通过后直接交接同owner
到200q/准确因子/完整参考/条件target，57空端口q保留FE。
没有下游批准不自行启动，也不跨截止无限保留owner。

提交response_v15、完整向量hash、独立审核、真实分项成本与失败出口，
保留UNKNOWN，不合并master、不提前宣称完整场或最终2TB/48h及精度通过。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/de2353b9ce46fbbb2c6fd4498ea24139b39d162f/docs/task41extra_phi90_p50x50_g17x20/response_v14.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/de2353b9ce46fbbb2c6fd4498ea24139b39d162f/docs/task41extra_phi90_p50x50_g17x20/outcomes/v14_closeout/evidence_index.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/de2353b9ce46fbbb2c6fd4498ea24139b39d162f/docs/task41extra_phi90_p50x50_g17x20/outcomes/v14_closeout/timing_and_adjoint_ledgers.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/de2353b9ce46fbbb2c6fd4498ea24139b39d162f/docs/task41extra_phi90_p50x50_g17x20/outcomes/summary.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/de2353b9ce46fbbb2c6fd4498ea24139b39d162f/src/solvers/hcurl_assembly_time_condensation.py#L169-L485
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/de2353b9ce46fbbb2c6fd4498ea24139b39d162f/src/solvers/p6_cell_condensed_action.py#L3249-L3590
[C3]: https://github.com/Rookie1234567/MyFEniCS/commit/eb57f88f26fb3cbbe0d7c34ebb725f9a6b310fe1
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/de2353b9ce46fbbb2c6fd4498ea24139b39d162f/src/solvers/task41_v4_volume_only_audit.py#L1757-L2190
[C5]: https://github.com/Rookie1234567/MyFEniCS/blob/de2353b9ce46fbbb2c6fd4498ea24139b39d162f/src/runners/task40_v10_worker.py#L11550-L11810

文档提交前完成静态结构与固定引用核对；线上可视渲染未能确认时单列，不把原文回读称作rendered检查。此文不声称任何新科学运行或工作站测试已发生。
