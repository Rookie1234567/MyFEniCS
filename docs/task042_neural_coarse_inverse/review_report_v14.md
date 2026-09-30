# Review V14：V16审查、可靠续算与条件GMRES校正

## 0. 审阅决定与本批目标

**接受V16的全空间校正进展，不授予求解器资格。GPOLY的已保存256步场确有改善；GPOLY/GNN因全局持续内存PSI停止，不能把它们当作完成同预算的数值负结果。下一批先补齐递推状态持久化与恢复，再连续推进两条配对路线；正常不收敛转入一次固定GMRES备选，资源中断在安全恢复后允许有限重入。不得仅完成checkpoint测试就结束已授权数值工作。**

本批消除的blocker是：有用的全空间校正被资源中断截断，最近解和部分计数未保存，因而无法继续或公平判断方法；同时要检验LSQR实际停滞时，另一种原方程Krylov更新能否进一步改善。最终仍是约2 TB整机资源内、端到端48小时得到新的0.7 nm非可分三维单胞有限元解；本批仍是micro续研，不是目标规模资格。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42_neural_coarse_inverse
worktree                   = /home/fenics/Projects/NN-Lab
review_date                = 2026-09-30
reviewed_HEAD              = c6cca7187c0d6d21f68b46bdb49435f213c1da68
reviewed_commit_UTC        = 2026-09-30T14:26:26Z
reviewed_commit_Singapore  = 2026-09-30T22:26:26+08:00
original_base_SHA          = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review            = review_report_v13.md
previous_review_commit     = 399c6a0f2568261c4dcaf7cdfb29499986e577bb
latest_response_reviewed   = response_v16.md
V16_solve_source           = ef60675dada2556a5527101f90fc83540d60e242
V16_GPOLY_image_source     = 01ed98655c9eb2949ea29a35fd82d1881a5a2508
next_batch                 = V17_RESUMABLE_FULL_TRACE_CAMPAIGN
response_required          = response_v17.md
decision                   = ACCEPT_WITH_LIMITATIONS_CONTINUE_RESEARCH
old_p4_inverse_route        = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate        = NOT_QUALIFIED
master_merge               = NOT_APPROVED
```

本轮用户明确要求增加工作量、避免轻易中断并允许自行修复。本报告据此授权以下有限自动队列和新的7小时总窗口，覆盖旧V16“停止后不得重启／不得换算法”的批次限制，不追溯修改旧结果、旧预算或安全规则。ChatGPT只读远程文档、原始记录与代码并新增本报告，没有SSH运行工作站，也未取得其全部ignored数组或实时资源状态。历史为measured/recorded，公式为derived，新路径为planned/not_run。

## 1. V16证据：必须区分最新标量、最近向量和完整终态

依据：[Response V16](response_v16.md)、[详细结果](outcomes/augmented_full_trace_lsqr_v16.md)、[停止快照](outcomes/records/controlled_stop_snapshot_v16.json)、[运行索引](outcomes/records/run_index_v16.json)、[费用](outcomes/records/resource_costs_v16.json)、[LSQR递推](../../src/solvers/bounded_complex_lsqr.py)、[保存调用](../../src/solvers/augmented_trace_study.py)。

| 同一0.7nm/384hex/p3；无量纲measured | 实际完成与最后原审核 | 真正保存的向量／场 | 判定 |
|---|---|---|---|
| CLOSED-LSQR-0 | 4096更新；Schur0.0694190731、native0.026920979 | 4096步散射E/curl约0.999924826/0.999905525 | 原精度失败，停滞收口；本批不原样重跑 |
| AUG-LSQR-GPOLY | 最后完成标量816，原审核768：0.0126178958/0.00489326771 | 仅256步向量：Schur0.0469482476、native0.018206708、散射E/curl0.146997030/0.147016298 | 资源停止，不是完成816步场审核 |
| AUG-LSQR-GNN | 最后完成标量85，原审核64：0.122363732/0.0474531179 | 仅0步向量：散射E/curl0.766070574/0.766240878 | 不能用0步场代表85步终态 |
| 全流程 | 新增正式监督wall下界4447.81145 s | 同时采样树峰4003057664 B，own swap0，GPU0 | 非全部研发elapsed；旧未知费用仍未知 |

GPOLY256相对V15同基起点的散射E误差从0.283235368降至0.146997030，约改善48.1%；相对G0则更大。这是实测场进展，但远未到1e-4。768步的场没有保存，不能根据较小残差推断其场误差。GNN还没有可比工作量的场证据；现阶段不得宣布局部神经基最终劣于GPOLY，也不能宣称其优于非神经方案。

两次外部监督清场由全局memory full PSI达到原阈值触发，非本任务16 GiB耗尽：记录含avg10=0.1/0.19与连续三次每5秒health观察；自有RSS、swap及MemAvailable另列。PSI表示停顿时间占比，不是内存使用百分比；0.1表示0.1%，不是10%。其规范见[Linux内核PSI文档](https://docs.kernel.org/accounting/psi.html)。阈值是本项目保守保护规则，不是内核宣告OOM的统一阈值。仅此不能归因于Task042或某邻任务，也不能因尚有可用RAM就绕过保护。

原代码已经通过state_callback捕获x/u/v/w/alpha/beta/phibar/rhobar等GK状态，但只有0/256/1024/2048/正常结束才落盘，且尚无resume入口。这是应修复的具体缺口。GNN的部分接口标量随kill丢失，控制流走过不等于有可复审PASS；下一批短复核并先保存。首次大幅随机状态恒等式1.1125765e-7的旧FAIL及后续物理响应尺度见证1.0282828e-12分别保留，不把后者包装为任意幅值的普遍精度证明。

## 2. 冻结对象与授权范围

完整阅读根/目录AGENTS、仓库原则、原task、全部补充合同与review、最新response/summary。旧文档原文不改。共享CPU授权继续：其他heavy存在不自动阻塞；真实系统压力则必须停止自身数值负载。新任务仍同一分支，不新建执行分支、不合并master。

| 冻结项 | 值 |
|---|---|
| 方程 | 原Full3D complex128、三维缺口、0.7nm、grazing1度/azimuth0/s；双Floquet和完整Fourier-DtN |
| 离散 | 原384hex/p3/h0.175nm/q15；full34050、trace18144、内部13824、slave2082、top20+bottom20端口 |
| 辅助基 | V15两库各3098列＝原G0的1560＋共同1538；NN补空间文件虽1544列仍只取前1538 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1；不再索要或联网替换 |
| Si | n=0.999885140474+4.32477054e-6i，epsilon=n*n；source0.699999988明确alias到nominal0.7 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA256 | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| mode SHA256 | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action NPZ SHA256 | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 SHA256 | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

原Q/U/R、Hhat、canonical顺序、rhs与初值从V16实际manifest/hash读入；U/R已写到IMAGE目录，缺最后汇总时可解析该目录的image_checks及文件hash，不重复3098列装配。若确实缺失，每库最多一次原A/image-QR重建，计入setup；旧Q本身缺失则阻塞该库，不重造新特征。

本批不训练hidden、不改Q维数、不扫描权重/PC/rank/波长/网格、不做新p4参考、不启用GPU。GPOLY和GNN都有神经G0；本批只比较固定方向辅助求解，不能称hidden训练贡献。准确参考与旧参考拟合权重不进入resume、初值、算法分流或停止规则。

## 3. 连续队列：普通失败不结束整批

| 阶段 | 必须完成的工作 | 自动后续 |
|---|---|---|
| R0 | 状态/算子盘点、原压力记录单位复核、持久化与恢复实现 | 不重做环境安装；缺一库只隔离该库 |
| R1 | 小型杀进程/恢复测试，真实短递推配对，补存两库接口 | 可信即执行R2，不只提交测试报告 |
| R2 | GPOLY/GNN恢复到共同逻辑检查点，优先补齐512/1024/2048证据，再按进展到4096 | 稳定下降允许R3；停滞或预算保留余额转G |
| R3 | 4096后仍有明确原残差进展时，有限延长到最多8192 | 无进展不盲跑，进入G或冻结 |
| G | 每库至多一个GMRES(64)原方程校正，先8周期，有进展才16 | 没有变换矩阵或预条件器扫描 |
| V | 全部求解冻结后一次FE完整验证与成本比较 | 不回训；仍失败时作有限原因表并收口 |

这里的“继续”以实际安全和数值可信为前提。某条路线数值负结果不取消另一条；资源停止后有限安全复核允许恢复；原算子/身份错误必须先修复受影响路径。不要为跑满时间重复相同失败，不把本批限制理解为永久禁止之后研究其他方案。

## 4. R0/R1：恢复协议必须先可靠

### 4.1 两级保存：递推先落盘，原审核与候选随后落盘

沿用V16递推和已安装BLAS，仅添加显式初始化/单步/导出/恢复接口。新schema至少包含：iteration、x（即y）、u、v、w、alpha、beta、rhobar、phibar、rhs norm、终止标志、算法与dtype版本、原rhs/Q/U/R/action/master hashes、构建和执行source、计数账及窗口身份。所有量对应同一个完整GK更新边界；不能保存半更新的u与旧x组合。

每16个完整GK更新先写完整递推，每64步必须再保存由该y恢复的t/c/port/z和原残差；先保存数值与audit_pending元数据，再算原audit并原子补齐。正常暂停/退出也保存最近完整状态。使用两个滚动generation槽，NPZ与manifest通过generation/hash配对、临时文件flush/fsync后rename、最后切换commit标记；新槽不完整时旧槽仍可恢复。不得每64步复制Q/U/R，更不得将向量转JSON。

递推存储约若干个18144维复向量，是MiB级而不是基矩阵级；实际写入时间/字节计入。本批新增滚动槽可轮换，原V16快照与所有失败证据不删除。每512步里程碑另外保留最小场状态；如果audit被kill，至少已有向量能稍后独立核验，不能再仅有标量。

计数单调：记录started/completed原S/SH、审核、setup与写盘；先登记准备工作与上界，再执行。kill发生在两次持久化之间，保留精确下界与保守上界，预算按上界扣减。每次checkpoint前的最大未落盘工作需有确定上界（例如16步32作用加一个审核/写盘段，预留64次原作用）；不能以清零进程计数掩盖重算。计时未知继续unknown，不补造叶计时。

### 4.2 旧状态迁移不是凭标量重造终态

GPOLY优先读真实ITER_256.npz：若其GK_*完整、finite、源递推字段语义和算子身份一致，恢复接口资格通过后可继续同一逻辑GK序列。GNN只有0步候选，初始化原f的GK序列；不是从64/85步恢复。819/816或85等日志数字不进入初始向量。无法恢复旧GK时采用下面明确的correction restart，不把重新开始的序列编号伪装成未中断续算。

新字段同时保存：legacy_observed_iteration、legacy_persisted_iteration、logical_iteration、new_updates_executed、recomputed_updates、resume_mode。GPOLY256之后旧已花但未保存的计算仍在历史费用里；新一轮重算这些步同样计费。V16中断时源为ef60675d...，本轮实现source另列，算法一致性不是source相同声明。

### 4.3 必做小测试与真实短核验

用同一初值的小型复数非Hermitian系统，含Q空/非空、结构性投影零空间、非零端口rhs，比较不中断80步与32步保存、独立进程读取再48步的完整递推/解/原残差，差<=1e-12（合适运算尺度），不以最终loss相近代替状态相符。覆盖写一半被kill、manifest损坏、错rhs/Q/hash、已终止alpha/beta为零、Mapping/NumPy/complex元数据、一次中断计数上界和回滚。不能人为将零alpha/beta加epsilon继续。

真实原点最多作每库32步的一次短配对（16+16对32），仅作为恢复接口测试，随后丢弃测试进展、不用它改选生产初值。先保存两库原M/MH dot、Pt/Pr、Hhat、恢复及原残差恒等式；补齐V16 GNN丢失的标量。必要真实测试原作用<=400，总R1数值<=900s；不重做整个旧preflight、所有FD或旧随机压力campaign。一次可复现实现错误最小修复后重测受影响项，合格就直接R2。

## 5. R2/R3：同一全空间方程的可恢复继续

原算法沿Review V13及V16的已验证BarAction。H是凝聚Hhat，不是Hp；一个bar S或bar S^H当前可用一次底层S或SH，必须按实际调用计数。

```math
\bar S=K-CH^{-1}F,\quad\bar b=b_t-CH^{-1}b_p,\quad
A=\bar S Q=UR,\quad P_t=I-QQ^H,\quad P_r=I-UU^H,\quad
M=P_r\bar S P_t,\quad M^H=P_t\bar S^H P_r.
```

```math
My=P_r\bar b,\quad v=P_t y,\quad
c=\operatorname{solve}(R,U^H(\bar b-\bar S v)),\quad
t=v+Qc,\quad\alpha=H^{-1}(b_p-Ft).
```

每64步核对真实原残差与投影残差，固定原b归一化identity<=1e-8；其余原MPC/恢复identity<=1e-10、端口及finite保持。估计残差仅监控；物理Gate不因restart重新归一化。原大幅随机压力FAIL仍单列。

只有旧递推损坏/缺失，或已验证原作用正确但估计与真实投影残差相对gap>0.1持续两次审核，才允许每库一次残差校正重启。设真实已保存全trace为t_b，以下是新方程，不是凭norm恢复旧递推：

```math
r_b=\bar b-\bar S t_b,\quad M\delta y=P_r r_b,\quad\delta v=P_t\delta y,
\quad\delta c=\operatorname{solve}(R,U^H(r_b-\bar S\delta v)),\quad
 t=t_b+\delta v+Q\delta c.
```

该重启从delta y=0开始，记录base trace/hash与epoch，所有比较仍用物理b分母。gap不是随意重启许可；原残差恒等式本身失败则先定位实现/精度，不把它当普通递推漂移。严禁参考、阻尼、row/column scaling或新基进入重启。

调度按里程碑串行：先两库到逻辑512，再两库到1024、2048，之后每512步交替推进；每次只驻留一套大基。已有完整GK可无损恢复，正常slice结束不是算法restart。checkpoint频率16/64保持。为减少反复加载，可在同一进程完成本库本次slice，但每库到下一里程碑前须给另一库机会；一库真正blocked则继续另一库可做工作。

基础上限每库逻辑4096；correction restart存在时按全批该库实际新增GK总量扣预算，重启不清零上限。逻辑8192为绝对扩展上限，新执行更新<=8192/库。2048之后若连续三个256步区间真实rho下降均不足1%，记LSQR_STAGNATION并转G；rho=max(原Schur,native,固定rhs端口)。不因单次原残差小波动就停整个实验。

到4096且原方程未合格，最近512步rho下降>=10%、无gap/identity问题、剩余本库时间>=600s时，允许每512步续至最多8192。后续同一进展规则每块复核，下降不足转G，不无限加步。两库的扩展判断只用各自原残差、不读场参考；不要求散射误差先达到旧0.5才继续。已达到原方程Gate则冻结通过点，优先V，不增加备用求解。

## 6. G：一条固定的不同算法备选，而非无限LSQR重试

LSQR停滞、breakdown但原方程不合格，或到其迭代上限后，可从该库最后已审核的完整trace做一次原方程GMRES校正。预算到期本身不授权超时；必须已为G留出配额。因PSI停止不能立刻换GMRES绕过资源Gate，必须先通过第7节重入。可信checkpoint/算子缺失时不启用G。

目的：检验LSQR双对角化的搜索进展不足时，直接按非Hermitian原方程残差构造Krylov空间是否有帮助；它不是更好的结果保证，也不是学习型PC。对每库至多一次：

```math
\bar S\Delta t=r_b,\quad r_b=\bar b-\bar S t_b,\quad
 t=t_b+\Delta t,\quad\alpha=H^{-1}(b_p-Ft).
```

使用已安装SciPy的complex LinearOperator及gmres，固定restart=64、M=None、无阻尼。直接作用bar S，**不把奇异的Pt/Pr双投影M随意传给普通GMRES并假定等价**。新t不再受Q约束；Q/U/R可在G前释放，仅保留t_b及原action/Hhat，实测RSS下降。V16不改方法，本批显式命名GMRES64-AFTER-GPOLY/GNN。

参考：[SciPy GMRES契约](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.gmres.html)。执行前核对现场版本/函数签名，不升级环境。采用每次maxiter=1个restart周期的封装，明确callback_type='pr_norm'，而非legacy计数；循环外恢复完整t并原审核。callback仅记内迭代，不能把它当全向量checkpoint。用rtol=0和固定atol=1e-8*norm(原物理b)控制内层目标，零校正rhs显式处理；整体通过仍看原完整audit。info=1在一个周期用尽时是预期非收敛，不当成实现错误；负状态/nonfinite另报。

先最多8周期/512 Arnoldi步；若未严格通过且8周期rho较该G起点下降>=10%、资源可信，才再8周期，总16/1024步。每周期完整向量先原子保存再写audit；外部kill最多丢当前未完成周期，不伪称精确恢复周期内部Arnoldi。下一次从最近周期边界继续校正，重算费用入账。两个连续完整周期rho上升超过1e-8相对（扣除已测浮点差）则做一次小型实现检查后收口该G，不通过扫描restart长度救场。

必须先验证复数小系统、非零t_b/rhs、周期边界恢复、callback/计数与explicit residual。不要重写未经测试的复Givens，不形成正规方程。本批不把GMRES改进归给神经训练；它仅是继承不同起点的确定性校正对照。

## 7. 资源压力、有限恢复与自主修复

**不改原PSI触发规则以换取不中断。** 保留整树hard16GiB/warn12GiB、own swap0、原有效MemAvailable与邻增长余量、独立0.5s watchdog；现有full avg10>=0.1且连续三次每5秒health观察规则保持。确认实际源码与冻结配置的单位、比较符和计数，不凭文字猜造实现。若发现单位换算bug，以小fixture证明后最小修复，保留旧raw，不能因结果不方便改阈值。

可以增加提前的合作式保存请求，但硬停止时限不后移：收到警告仅请求完成安全点，不阻塞现有清场；不能为临时保存大数组拖延硬停。滚动checkpoint是对SIGKILL也有效的主要保障。自身swap/RSS触线、监督失效、身份混乱先停止受影响重负载，禁止借用户“多做些”越过这些边界。

一次PSI停止后立即释放自身大对象/进程，不保留大基常驻等待。最少冷却120s，然后只读轻量pressure/MemAvailable；最多观察至600s。只有full avg10<0.05连续60s（每5s）且所有原余量/own-lock/空闲物理核检查通过，才可从最后合法checkpoint重入。该0.05只增加重入滞回，不降低原停机敏感度。每库最多2次因资源停止的重入、全批最多3次，全部冷却/等待总计<=1800s并计入总elapsed；超限则保存RESOURCE_ENVIRONMENT_BLOCKED，完成可安全做的轻量检查与交付，不无限守候。

全局压力未消退时另一条heavy也不得启动；一库数据错误则可继续另一库。有限重入不是等待用户确认，也不是对工作站其他进程做自动管理。不得暂停/kill邻任务、修改其nice/亲和性/锁/watchdog、清全机cache或关闭swap策略。

普通实现问题允许全批最多4个有编号的最小修复循环，每个诊断/修复<=1200s且同一根因最多2次。范围为Task042新恢复、计数、序列化、runner接线和已定位数值实现；失败source/test/raw全部保存，只重放受影响短测试/最后checkpoint之后，不能把整条成功前缀重跑。数值不收敛不是bug，不以修改容差/基维数/材料/算法参数称修复。损坏核心算子或未知ABI时停止所有依赖路径，独立轻量工作仍可完成。

## 8. 成本、时间与阶段预算

用户本轮增加工作量，授权**新start起总elapsed<=25200s（7小时），包含读取、实现、测试、设置、求解、冷却、验证和交付；start+23400s停止全部重负载，最后1800s收尾**。这是上限而非运行时间承诺，不要求跑满。UTC/Asia-Singapore/单调时钟与不可刷新deadline入journal；上下文压缩、修复、重启或换stage都不得刷新。

R1结束、两库数值队列开始前，按剩余重负载时间T冻结统一每库wall上限B=min(9000s,floor((T-900s)/2))，含该库加载/必要重建/所有slice/失败重算/LSQR/GMRES及相关审核；冷却另列但仍耗总时间。B<900s则仅做能完成的短状态核验，不仓促宣称完成两库对照。每库先为G预留min(900s,0.2B)，LSQR不得消费这部分；无需G或原方程已合格时余额不用硬花。不可因为一库暂时blocked就自动把双倍额度转给另一库。

同时生效：每库新增GK<=8192（含重算），原S+SH<=24000；全批原S+SH<=56000，含最多6196列必要重建、测试、审核/失败预留。image重建每库最多1次、QR各最多1次；GMRES每库<=1024 Arnoldi步；原audit<=420；独立FE状态<=12；新增持久artifact<=3GiB、总Task042 artifact<=20GiB、自由磁盘>=50GiB。达到任一上限按最近合法状态收口，不清零预算。

一套Q/U/R常驻，A完成hash/QR后释放；Q和U用BLAS共轭转置不复制大矩阵。真实同时峰、共享page cache/allocator、加载和写盘均报告，不把derived数组体积当RSS。已有库与参考不复制进Git。初始规划<=8GiB，现场空闲物理核避开忙SMT，MPI1、数学/Torch1、DataLoader0、GPU不用，自身nice10/idle I/O、独立环境/cache/自有锁；不升级ABI/BLAS/CUDA，不使用WSL专属marker作为原生Linux硬Gate。

V16 formal新增4447.81145s仅是下界；历史账保持原下界/未知，不根据本report补造精确累计。新账区分冷setup lineage、增量继续、回放、等待、审核、失败和总elapsed。跨库同逻辑迭代对比仅在递推未restart时成立；有restart/GMRES时另列同新增作用/同wall比较。不用估计曲线插值编造场或原残差。

## 9. 最终独立验证和停止结论

全部求解/分流/状态hash冻结并退出后，独立FE进程才读REF7。一次环境最多12去重状态：V16-GPOLY256、GNN0两个真实起点；每库新的逻辑1024/2048（存在才取）、最后LSQR及最后GMRES各一；有首个原方程通过点时优先纳入而不突破12。不使用未持久化的V16标量对应场，不按参考选最优checkpoint。参考本次native与hash记录，未新增LU，验证后不再回训。

严格Gate不变：原Schur/native/原增广/规定端口<=1e-6；恢复/identity<=1e-10、slave-zero；同离散total/scattered E/H、scaled-curl、selected复场及40复通道<=1e-4；R/T/A/A_volume绝对差<=1e-5、每级功率差<=1e-6、能量闭合<=1e-5；近零沿旧定义。所有未合格功率仅diagnostic。一次micro通过仍非p/h收敛、更非目标2TB/48h通过；本批不启动p4新参考或更大模型。

分别判断：可靠resume是否通过；全空间残差是否继续下降；场是否改善；原严格资格；GPOLY/GNN及GMRES增量；成本。可比较同逻辑512/1024/2048原审核，但资源环境不同仍需限定。均未通过只报告进展和代价，不报同精度加速倍数。两库仍含相同随机神经G0，不称神经训练成功。

若普通求解失败但队列尚有授权路径，继续；所有可做路径结束或安全/总限额触发则交付。资源blocked、checkpoint数值不合格、LSQR停滞、GMRES无改善、原方程通过但场未过必须不同状态。最终只提出一个基于证据的下一步，不把同一路线永远续跑。

## 10. 实现、正式入口与交付

数值核进入src/solvers，复用bounded_complex_lsqr的state_callback、ProjectedTraceOperator、BarAction、ThinBasis、原writer/audit/监督；保留旧调用行为的回归，不复制另一套巨大runner。新增跨阶段scheduler只是有界调度，不是后台永久监控。先通过小测试并commit clean，再启动正式one-run dat；每个slice/resume均有独立dat/resolved身份与继承的campaign预算，不把多个物理参数扫描藏进去。

以下为待实现入口，不是本report已经运行的命令；slice依赖与resume路径写进resolved，不在shell盲跑全部：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v17_checkpoint_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v17_continue_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v17_continue_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v17_gmres_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v17_gmres_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v17_verify.dat
```

R2/R3按共同里程碑调度，不是把一条一次跑满再理另一条。重复slice可由同一profile生成具名one-run输入，保持单dat单stage和继承budget；恢复不改旧文件。实际source、input_original/resolved/run_manifest/input_sha/physical/source/environment/MPI/资源/artifact hash齐全，summary HEAD不能替代执行source。活跃程序受检HEAD不得为推文档而改变。

建议commit：C1恢复/原子writer/计数及pure测试；C2真实接线和冻结计划；C3配对继续与有界G实现（首次使用前clean提交）；C4结果/checker/docs。普通预授权阶段可在无活跃受检运行的边界安全提交并继续，不需每小步等待新review。修复的最小回归、compileall、dat validate、原方法不变及监督故障测试必做；Ruff/CI/全库pytest/MPI2/4未做即说明，不破坏环境补工具。

提交response_v17.md、outcomes/resumable_full_trace_campaign_v17.md及compact records：checkpoint_inventory、resume_qualification、resource_reentry_journal、repair_journal、projected_operator_checks、iteration_history、recurrence_gap、gmres_cycles、candidate_comparison、field_channel_checks、run_index、resource_costs、qualification_and_dispatch、publication_checks。大递推/Q/U/R/场只存ignored；更新summary/test_summary/changed_files、任务导航、development_progress、development_model_registry，旧task/review/response/raw不改。

按markdown_rendering_standard检查源码与GitHub渲染；未拿到像素不伪称完整视觉PASS。末尾先确认自身数值后代清场、预算关闭，再只推送本分支，报告精确HEAD/base/upstream/worktree、source、实际恢复模式/更新/重入/修复次数、原方程和场、资源与唯一下一建议。未经最终review及用户授权不merge master或其他分支。
