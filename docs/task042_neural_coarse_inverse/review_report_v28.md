# Review V28：接受V30轻量资格，修复真实工作流缺口后只作一次固定回流诊断

## 0. 审阅决定

**V30在其授权范围内通过：关闭Review V27的入口编译错误和32个负例误报问题，接受`LIGHT_ENTRY_AND_SYNTHETIC_CHECKER_QUALIFIED`。真实回流仍未运行，且本次静态审阅发现实际工作流调用了未定义的`relative`。下一轮V31先修该缺口并验证工作流接线；只有测试、身份、容量和fresh准入全部通过，才执行一次原定两冷态回流诊断。不得直接把162项合成测试通过当成真实actor可用。**

[response_v30](response_v30.md)已正式回应[review v27](review_report_v27.md)，按AGENTS §15新建v28，保留旧报告和执行记录。以下是下一轮完整授权；旧review只补充被明确引用的数学、身份及资源细节，不恢复旧窗口或旧重试额度。本报告作者本轮只审阅、静态重算和检查文档，不修改求解源码、不读取真实数值载荷、不启动实验；未使用subagents或重置卡。

| 审阅身份／范围 | 核实值与边界 |
|---|---|
| 最新精确远端／本地HEAD | `b9e2d587cec6a2418573faa4e3c87721194914eb`；非交互ls-remote一致，起始工作树干净 |
| V30实际实现／launcher／worker source | `1a18f520dae3ecd702a1369b0d9241ec3e81802a`；22个源码文件逐个对回该提交，不把交付文档HEAD当运行source |
| 分支／canonical worktree | `task42_neural_coarse_inverse`，`/home/fenics/Projects/NN-Lab`；common为`/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| 当前进程 | 主机只读检查未发现Task042 actor／辅助worker；邻任务仍运行，不作干预。相近Task042extra分支不在本次范围 |
| 增量／历史 | 相对上一review共50文件、7个Python变化文件；56份旧review／response字节未改，四份导航／summary历史后缀保持；沿原547文件索引及历轮增量继续核对，不声称全仓逐行语义审计 |
| 独立核验 | 84个规范化路径、1,205,071 B原始文件hash；编译22文件；重算冻结CPU决策、27条整树样本与JUnit库存；对真实worker四模块作静态全局符号检查 |
| 本次没有新数值证据 | 没有重跑162项数值fixture、三小矩阵或真实S/Sᴴ／LU／QR／FE／训练。V30测试是已绑定的执行证据；本次新增缺陷证据是静态符号解析及单个标量表达式NameError复现 |

[本次独立核验记录](outcomes/records/review_v28_independent_checks.json)保存脚本、hash、JUnit、资源重算及缺陷定位。精确GitHub页面访问仍Cache miss，视觉`NOT_VERIFIED`；本地结构与文档检查单列，没有CI／全仓通过声明。

## 1. V30可以关闭的工作

审核器负责检查“结果文件的来源、向量、计数和误差是否相互一致”。它不计算新的三维场。此前是入口无法编译、正确包写不出、错误包因无关IO异常而误报通过；V30修复了这些具体问题。合成fixture只是人为构造的小测试包，其通过不表示真实七套因子或两个真实状态已经通过资格。

| 审核项 | 从源码和原始记录重核的结果 | 接受边界 |
|---|---|---|
| 标签／文件引用 | `snapshot_label`与`snapshot`分开；22/22真正编译通过，完整缓存分析模块经入口执行 | Review V27 P1关闭 |
| 新目录所有权 | collector创建输出目录；fixture故意传入不存在的嵌套路径，公共atomic writer合同不改 | 原8个目录失败关闭 |
| 32变异反例 | 每例先运行未变异正控制，再要求准确ValueError／KeyError及完整Gate消息；专门IO测试证明FileNotFoundError不能满足数据反例 | Review V27 P2关闭，未放宽数值门限 |
| 原样轻量入口 | source1a18f520…，exit0；原始stdout与JUnit一致：最小7、完整162，零失败／skip | 162个不同测试，169次执行；最小7在完整scope中重复 |
| CPU冻结重算 | V28两历史快照候选`[11,22,26]`／`[]`，逐核拓扑、busy与eligible一致 | 静态历史重算，不是未来CPU预约 |
| 固定代数与成本 | 原样入口执行既定三小矩阵、成本模块；误差8.130e-17／1.905e-16≤1e-12，零主块拒绝；hash绑定旧成本保留 | 不增加模型／参数，B_full真实作用仍NOT_RUN |
| 证据不可逆性 | V26–V29 window／ledger的hash不变且closed；V30 closed、active=null、formal run空 | V29 NOT_RUN和Review V27的147/8失败没有倒填 |

| V30费用／资源 | 原始记录核验；单位与口径 |
|---|---|
| 唯一准入 | 2026-10-03 06:45:30.691948–06:45:31.968632 UTC；CPU21，候选21／37；CPU/SMT、内存、磁盘、PSI通过；gzip解压与原快照逐字一致 |
| 受监督有载 | 18.785166596993804 s；entry14.790799552 s、测试启动／执行均嵌套其中，不重复累加 |
| V27起累计 | 39.94901336694602 s；600 s上限未消耗部分为560.050986633054 s，下一轮继续扣费，不重新获得600 s |
| 同时process-tree峰 | 从27条样本重算RSS195,633,152 B、ownswap0，逐样本成员求和一致；请求0.5 s采样，实际相邻间隔约0.575–0.974 s，因此只称采样峰，不称瞬时绝对峰或kernel cgroup硬限制 |
| 环境 | Task042独立native Linux pure环境；NumPy1.26.4／SciPy1.11.4，MPI1/math1、CPU21、三个原生BLAS getter为1；无FE/JIT/Torch/GPU/OOC |
| 新真实消费 | actor／S／Sᴴ／factor reader／局部solve／LU／gecon／真实QR-SVD／FE／迭代／训练均0；fixture的36／35／7是合成证书 |
| 时钟与库存 | 首次工作06:39:09.630103 UTC；06:46:31.384243提前封闭队列；交付前elapsed806.628181 s。V30新增观察8,250,746 B，V27起含review临时目录94,124,313 B，全Task artifact18,024,901,709 B；均为所标时点，不当最终永恒库存 |
| 历史费用 | formal研发下界77,161.557139 s、旧辅助及完整N=1暖链unknown保留；Review V27监督9.043027862 s另列，本次静态审阅费用也不计作actor0成本 |

V30 scope没有改动真实数值工作流。已有source／环境／hash绑定的通过证据无须因本次纯文档审阅再全部重跑；下一轮只重新资格化受其实际代码变化影响的部分。

## 2. P1：真实工作流在保存首个方向前会遇到未定义名称

[return_block_study.py](../../src/solvers/return_block_study.py)第170行构造内部抵消证书时调用：

```python
operation_relative=relative(cancel,cancel_scale)
```

该模块没有定义或导入`relative`。它导入的[return_block_direction](../../src/solvers/return_block_direction.py)虽在自己的模块内导入了这个函数，却不会把该名称自动带入调用者的全局命名空间。标准库`symtable`检查确认`run`作用域引用的`relative`无模块绑定；原表达式在仅提供两个标量操作数时产生`NameError: name 'relative' is not defined`。这不是一次真实actor运行失败，不伪造actor计数。

git blame表明该行源自V27实现`7b0e03f2fbfb504b13a5f5b4c46c52e0e96a5eb9`，**不是V30引入的回归**。22文件编译通过并不检查运行时全局名称是否存在；当前162项主要覆盖方向代数、reader和手工合成的collector包，没有调用真实`run(stage)`走完七bundle、两个状态、抵消证书和写出链。因子加载及前面的原作用可能成功后才撞到这里，不能把真实机器当作发现该缺口的测试环境。

V31应显式导入已有、符合零分母规则的`relative`，不另写一份归一化函数，不改抵消容差。补一份**调用实际study工作流**的受控合成接线测试，走过这行、两个命名状态、原始证据写出及最终消费核对；再连接现有collector验证它能读取工作流产物。可以注入内存级IO、合成算子与reader，但不能直接手填一个“成功actor结果”、跳过该行或只单测另一个helper。若正式18144/40尺寸Gate妨碍小fixture，可用保持接口的桩对象和有限向量，不能为了测试删减正式Gate或构造18144方阵。

新增静态门槛应覆盖实际入口依赖链的未定义名称及语法；可以使用已可用的Ruff F821等工具或等价检查。本次四模块标准库检查只发现上述一处，不据此宣称全仓F821合格，也不要求为此更换环境或重装依赖。

## 3. 原回流诊断仍值得做一次，能回答的问题有限

先在联合区域J求局部修正，再让其余六块处理它引起的外部不平衡，最后回到J补偿外域处理的反作用，这就是本次“回流”。它改变了区域之间的信息传播次序，可能给旧九个方向补充一个有效响应；代价是读入七套已有因子、局部三角解和原方程作用。此前只验证了组件，**尚未在真实micro的这两个状态上测量过它**。

记A为保留全部40端口闭合的原trace算子，B_J为J=[5,7]原主子块逆注回全空间，L_O为外域0/1/2/3/4/6六个原主子块逆。唯一候选仍为：

```math
q_J=B_Jr,\qquad w=L_OAq_J,\qquad
d=-w+B_JAw,\qquad q_{\rm ret}=q_J+d.
```

q_J已在V26九方向中，所以加入d与加入q_ret是同一个扩展空间，不能分成两条路线择优。它与旧p1空间换测试方式、scalar-tau调整、延长迭代均不同；本次新信息是**增加一次固定外域反馈后，九方向剩余残差是否还能实质下降，以及代价是多少**。

精确主块关系给出J内`A d=0`，但要实测抵消和外部变化。B_ret只依赖J内3888个输入分量，rank≤3888<18144，故不能独立作为全空间右预条件器。V30已验的全空间补项满足：

```math
B_{\rm full}=B_J+(I-B_JA)L_O(I-AB_J),\qquad
B_{\rm full}-B_{\rm ret}=(I-B_JA)L_O.
```

这个补项让外域残差有直接入口，仍是传统代数。固定2维反例残差放大6倍已说明：可逆、能表示完整误差、单次修正有效、稳定迭代收敛是不同命题。B_ret正结果不授权B_full；B_ret负结果也不否定未试验的外域输入补项。

| 不可更换的状态／基线 | 要测的新量 |
|---|---|
| V24-LZ-CYCLE4：V26 eta9=0.966205505618 | eta10、g10=eta10/eta9、新响应在旧九方向之外的可分辨部分，以及该部分与e9的对准程度 |
| V24-LCZ-CYCLE4：V26 eta9=0.981968429990 | 同上；两状态都必须报告，不追加第三个状态选结论 |

这是**zero-trace路线第四周期的两个已消费冷末态**，不是重新从零求解，也不是warm-start资格；无新warm／INITIAL／fresh状态。eta的分母是当前trace残差范数，g比较九方向与十方向的剩余残差，不能把它们当作full-b归一的最终物理解残差。

## 4. V31有界执行合同

### 4.1 顺序工作包与资格

| 工作包 | 执行与验收 | 停止边界 |
|---|---|---|
| A：真实工作流接线 | 修§2；复用既有数值核、`DiagnosticWindow`、runner／watchdog／checker，显式加入V31 namespace；准备单个正式dat与plan，运行前核对既有packet／父记录／source的紧凑元数据 | 不复制新数值核；不复活V27/V28 dat，不修改V26–V30 closed窗口或旧结果 |
| A的测试 | 准入前静态编译与未定义名称检查；一次受监督辅助完成最小接线测试和受影响scope，覆盖输出、失败路径、计数、ledger结算、旧namespace拒绝；代码提交并clean后才作正式准入 | 测试出现新错误则本轮停止真实数值推进，保存具体根因；不靠真实actor试错，不为同source无关文档重跑昂贵Gate |
| B：唯一真实诊断 | fresh正式准入通过后，在一actor内顺序处理两冷态；执行原V24/V25数学合同、完整因子／原作用见证、九方向基线和十方向重组 | actor启动后不重启、不增加状态、LU、迭代、回流轮数、tau、块对或训练；无B_full真实apply |
| C：独立审核与交付 | actor结算active=null后，最多一次受监督只读checker，读取hash绑定的新保存数组和必要旧状态／方向；从原字段重算数值与消费，写response_v31及完整成本／失败分析 | checker不做原作用、factor读取／solve、QR/SVD。后处理资格未取得就记CHECK_PENDING／UNRESOLVED，不以actor自报成功替代 |

新namespace必须贯穿loader、正式run_case路由、worker、plan、artifact、records、临时路径、父监督身份与结算。collector现有默认写V28文件；V31显式输出只能进入新namespace，旧默认保持。回归测试须证明V31不会落到旧ledger，旧dat不会被静默路由到新窗口。所有真实worker只能由既有正式`python scripts/run_case.py <V31单个dat>`通道启动，不能直接执行study绕过准入。

当前辅助入口的V30 carry常量21.163846770适用于V30，**不能照搬给V31**。V31必须绑定原记录carry=39.94901336694602 s，把本轮测试、actor、checker和失败耗时都纳入累计；测试验证固定文件名的auxiliary summary不会被只扫描`aux_*/summary.json`的旧逻辑漏计。同一个进程树的内层timer不与外层监督wall重复相加。

### 4.2 真实消费、数值Gate与成本

| 项目 | 冻结合同 |
|---|---|
| 物理／样本 | 原0.7nm micro、384hex/p3/q15、18144 trace＋40port；两固定V24 parent／状态、V25八方向、V26联合方向／九系数／e9逐名hash绑定。材料、MPC、b、端口、原算子不改 |
| 只读因子 | V26 J一套、V24外域0/1/2/3/4/6各一套，共7 reader；每外块加载一次，处理两个状态后释放；不读旧5/7 LU、不复制因子、不重新LU／gecon／装配 |
| 重载见证 | J种子422601/422602；外块b种子422401+2b、422402+2b；解残差≤1e-8、operation≤1e-12，原主块作用／J伴随配对≤1e-10；失败停止依赖工作，不fallback |
| 完整流程的预期消费 | S34＋Sᴴ2=36、reader7、J solve4、外域solve24、显式L/U pass56、薄流程2、40port factor1、单列port solve35。使用V30已验`EXPECTED`，由实际ledger／manifest／结果三方一致证明，不能手工填计数 |
| 保守资源上限 | 仍S＋Sᴴ≤64、J≤8、外域≤24、pass≤64、薄流程≤2且≤10列、port factor≤1／solve及RHS列≤128。上限余量不是额外实验授权；完整CHECKED仍须符合预定36／35等直线消费；偏差先解释，不直接改checker放行 |
| 九→十代数 | 同列均衡、QR＋小GELSD、cond=1e-12；每状态一流程，九列基线由同一分解获得；h超过64eps原操作尺度且h/Ad>1e-12、rank10才称可分辨，不用正规方程或新分解救场 |
| 原作用审核 | 原状态与缓存差/b≤1e-11、端口≤1e-10；内部抵消operation≤1e-10；独立重组差/b≤1e-11、operation≤1e-10并列差/r；QR／正交≤1e-10、驻点≤1e-8，eta10≤eta9+1e-10；完整见证按review v24 §5保留 |
| 真正禁止的消费 | 新局部LU／gecon／assembly=0，新全局矩阵／p1 T/U/R／D_L／Krylov／REF7／teacher／权重=0，FE恢复／新场／official R/T/A／迭代／训练=0 |

记录J和外域各bundle的文件hash读取、数组扫描、mmap、私有pivot、LAPACK副本及释放前后RSS。载荷1,591,420,032 B不是同时RSS；历史设置不因只读缓存而免费。必须分开本轮冷读取资格成本、历史准备依赖、假设驻留复用的derived成本、完整N=1 unknown，以及actor／launcher／checker全程时间。不得只用名义两次A和一次反馈solve当作资格总费用。

### 4.3 不刷新预算与明确停止

| 项目 | V31固定上限／行为 |
|---|---|
| 总窗口 | 首次工作起UTC／monotonic／boot_id冻结；elapsed≤5400 s，start+4500 s停止有载，最后900 s交付；实现、读取、测试、等待、hash、发布都计入，不刷新旧窗口 |
| 有载额度 | 新actor监督≤480 s；新受监督辅助合计≤60 s（前测≤40 s，后checker≤20 s）；V27起actor＋辅助总≤600 s。按上限本轮至多新增540 s，总579.949013367 s；超过剩余窗口时取更小值，不借用结项时间 |
| 准入次数 | 前测最多1次辅助准入、正式actor最多1次fresh准入、后checker最多1次辅助准入；各阶段拒绝即停止该运行链并交付，不轮询、不后台等待、不重试找核。前测失败或拒绝不进行正式准入 |
| actor重复与中断 | 只允许一个actor；任一输入、代码、数值、时间、资源Gate失败保留已消费计数／upper和partial包，本轮不重启。checker拒绝或未运行不回头重做原作用／因子／分解 |
| 资源 | 实际actor事前derived同时规划≤8GiB，整树请求0.5s采样warn12／hard16GiB、ownswap0；前后辅助warn1／hard2GiB。实际采样间隔和峰口径另报；不宣称kernel限制 |
| 环境／共享 | 资格化native pure，MPI1/math1、getter验证；无Torch/GPU/FE-JIT/OOC。维持5%／SMT规则、自有锁、reserve=max(128GiB,10%effective total)、邻增长128GiB及本任务16GiB余量；PSI full avg10≥0.1%连续3次5秒停止自己，不操作邻任务 |
| 存储 | V31新增含TMP≤32MiB；V27起含审阅临时目录累计≤128MiB，全Task artifact≤20GiB，自由盘≥50GiB。V30时点约94.1MB已用，开工前stat重新核算；不删旧失败，不复制因子来满足合同 |
| 历史费用与收口 | 保留全部旧elapsed／研发费用和unknown；actor settled后才checker，最终closed且后代清空。所有原始日志、source／命令／环境／计数／峰／hash绑定；同步README、summary、test_summary、changed_files，正式诊断或资源停止同步模型总账和development_progress |
| 分支／角色 | 同一canonical task42分支；不使用subagents／重置卡，不改dot、其他分支或master。提交并推送完整HEAD、运行source、base、upstream／工作树状态后停止等review；无merge |

V30的CPU21仅是一次已通过的历史准入，足以说明此前资源拒绝不是永久数学结论，不代表V31有资源预约。本轮重新授权的依据是V30已完成准备、真实诊断从未消费且问题仍明确；不是续旧失败迭代的预算。若V31再次因资源而无法运行，等待外部可审计可用条件后另议，不自动递增编号重复同一准入。

## 5. 结果分流与失败后的有效替代

下列分流只有在身份、真实数值、完整消费和独立checker都通过后生效。数值弱、资源拒绝、实现异常必须分开。

| 两状态的实际结果 | 决策及有用交付 |
|---|---|
| 新方向均可分辨且g10≤0.75 | 有限`RETURN_EXTRA_DIRECTION_SIGNAL`，即相对e9剩余范数再降至少25%；报告平方范数消除与完整成本。只提出全空间补足／成本方案并停止，不启动求解或训练 |
| 两者g10≥0.95或均不可分辨 | 关闭固定J→O→J单轮提案，分别说明重复空间还是新方向与e9对准弱；不换顺序、块对、回流轮数或scalar-tau救场 |
| 混合或中间值 | `STATE_DEPENDENT_INCONCLUSIVE`；保持两状态全部记录，不增加样本投票，不称泛化 |
| 抵消、重组、因子或计数不合格 | `NUMERICALLY_UNRESOLVED`／输入失效／partial；明确失败实值和限值，不计算可信的方向增益，不以资源或实现失败否定数学方法 |
| 资源或时间停止 | 保存准入／监督原记录、最后阶段与真实消费上下界；未执行部分NOT_RUN，不能填作负数值结果 |

即使失败，也能用已保存向量区分四个问题：J内抵消是否成立，外域响应是否减小，创新是否脱离旧空间，创新与e9是否对准，以及系数／抵消对可验证精度和费用的影响。只允许从缓存作这些分析，不能追加原作用或新QR/SVD。

若固定回流确实无效，结束这条局部方向序列；有效替代是说明**下一方法必须改变哪一种外域输入通路或接口传递，以及完整成本是否值得**。V30的B_full补项是已知代数候选，其真实稳定性仍未知；不能将B_ret的负结果推广到它，也不能自动执行它。原尺寸参考逆、周期分块和共享存储优先使用dot将来提供的身份匹配证据，Task042不重复其完整求解器／规模实验。没有明确新信息来源就保留关闭状态，而不是继续制造相同空间的测试变体。

## 6. 历史去重、神经20%及原尺寸资格

| 已尝试／否定／未运行 | 目前结论；本次不重跑 |
|---|---|
| V1–V5 p4神经粗逆／13.5nm | 已关闭，不因后续局部代数重新解锁原F5／p6路线 |
| V6–V15 神经FE trace／固定特征 | 实际训练、hidden更新失败与固定特征／仅头部拟合分开；未运行的hidden路线不写成新结果 |
| V16–V21 全空间校正／ILU0／class64 | 曾有残差或算子速度改善，完整物理资格未过；工程加速不是收敛改善或NN贡献 |
| V22–V23 Galerkin／image-QR | 表示误差与消除残差已区分；同p1空间换测试／tau不重复。V23完整0/6 |
| V24 八局部LU与image组合 | warm／zero四路首4周期及overlap已执行，完整0/5；不把它重新列为待执行 |
| V25／V26 八方向与联合方向 | eta8约0.983237／0.989925；联合对e8额外范数下降仅1.732185%／0.803718%，固定联合提案关闭 |
| V27／V28 真实回流 | 尚无真实两态eta10／g10；已有停止是资源／准备问题，不是数学否定 |
| V29／V30 准备与代数 | V29 worker0；Review V27隔离证据另列；V30原样轻量资格通过，本次关闭对应缺陷。B_full真实作用、迭代和NN仍NOT_RUN |

历史完整索引及逐轮证据继续由[review v21](review_report_v21.md#102-历史去重什么已经尝试什么仍没有运行)、[v22](review_report_v22.md)、[v23](review_report_v23.md)、[v24](review_report_v24.md)、[v25](review_report_v25.md)、[v26](review_report_v26.md)、[v27](review_report_v27.md)和[原547文件索引](outcomes/records/independent_review_v21_20261002.json)串联；本次明确只是其后的50文件增量审阅，没有把旧结论改名为新实验。

神经标准仍是：**相同完整正确性下，相对最佳合格非神经N=1路线，完整耗时或完整同时峰内存至少降低20%，另一项仍合规**。完整费用包含数据生成、训练、设置／加载、推理、额外精确校正、恢复／审核和IO，不默认摊销，不沿用早期10%。当前没有最佳合格全流程基线或成对NN测量，收益`NOT_DEMONSTRATED`。学习同九／十方向的系数不能超过该空间精确最小残差；V26两薄LS共0.008964091 s，仅占该诊断actor约0.026949%，免费化也不足同口径20%，但这不是其他神经方案或完整成功单解的理论上限。

原目标仍是50×25nm周期、z=-10..130nm原尺寸、0.7nm、完整非可分三维有限元、同时峰≤2e12 B、端到端≤172800 s。当前micro只有1.4×1.05×1.4nm；V23 warm Schur约2.507714e-6／zero约0.06811318且逐通道功率超限。V24 LW4 Schur2.502117907e-6／功率差1.666968717e-6均超1e-6；LZ4 Schur0.0813766679／散射E差0.568888278／功率差0.007245974超1e-6／1e-4／1e-6。native单项通过、薄空间最优或一次回流有效都不改变V23 0/6、V24 0/5。

固定块稠密A/LU存储32Σn_b²、factor设置Σn_b³，全局image基16nr、R矩阵16r²及QR工作nr²仍须完整计费；micro峰值不能直接外推原尺寸。dot继续`task40extra_dot_parallel_cloud`的参考逆、周期分块、共享存储与规模验证，本任务只作互补的有限方向和学习增量评估，不修改其分支或假定其尚未核实的结果。原尺寸正确性、离散精度、fresh泛化及2TB／48h全部仍`NOT_QUALIFIED`；**无merge approval**。
