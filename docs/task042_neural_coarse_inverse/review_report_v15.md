# Review V15：V17审查、GMRES端口闭合修复与原残差达标推进

## 0. 审阅决定、仓库快照与本批目标

**接受V17已经保存并独立验证的全空间求解进展，不授予完整有限元或神经加速资格。下一批首先修复已定位的GMRES端口返回值接线，完成两库真实GMRES64对照；若短重启确实无效，执行一次预登记的GMRES256后备；仍未合格时，从原V17完整递推独立继续LSQR。不得又把全部时间用于元数据修复，最后留下一个已知的一行接线错误而没有完成主求解。**

本批要消除的blocker是：当前已有接近参考的有限元场，但原方程残差仍比1e-6大约490–594倍；已授权的GMRES校正尚因实现错误而没有可审核结果。目标是进一步降低原方程残差并保持场准确性，不是再训练一个新网络、修改材料或重建p4强逆。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42_neural_coarse_inverse
worktree                   = /home/fenics/Projects/NN-Lab
review_date                = 2026-10-01
reviewed_HEAD              = 546236ae26a30cc71d5ba5a966a5e3ec8f525d65
reviewed_commit_UTC        = 2026-09-30T21:25:24Z
reviewed_commit_Singapore  = 2026-10-01T05:25:24+08:00
reviewed_latest_commit     = Task042 V17 record exact-page publication and delivery receipt
original_base_SHA          = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review            = review_report_v14.md
previous_review_commit     = f834c008110131433de0f269195de394a6856871
latest_response_reviewed   = response_v17.md
V17_final_solve_source     = 59feb6570a74d72aa501853807013711d89279cd
next_batch                 = V18_GMRES_REPAIR_AND_RESIDUAL_COMPLETION
response_required          = response_v18.md
decision                   = ACCEPT_WITH_LIMITATIONS_CONTINUE_RESEARCH
old_p4_inverse_route        = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate        = NOT_QUALIFIED
master_merge               = NOT_APPROVED
```

最终目标仍是：约2 TB整机物理内存资源内，对新的真正非可分三维周期单胞，端到端48小时得到合格的0.7 nm有限元解。本批继续384-cell micro和单核16 GiB研究预算；研究预算不是最终资源配额，micro通过也不代表目标规模、离散收敛或48小时通过。ChatGPT本次审查远程合同、回应、原始记录、实际GMRES/续算代码和提交；没有SSH运行工作站、读取全部ignored数组或测量其当前资源。历史为measured/recorded，倍率与公式为derived，新路径为planned/not_run。

## 1. V17证据、真实进展与尚未通过项

依据：[Response V17](response_v17.md)、[完整结果](outcomes/resumable_full_trace_campaign_v17.md)、[候选CSV](outcomes/records/candidate_comparison_v17.csv)、[checkpoint](outcomes/records/checkpoint_inventory_v17.json)、[G失败](outcomes/records/gmres_interface_stop_v17.json)、[修复记录](outcomes/records/repair_journal_v17.json)、[资源](outcomes/records/resource_costs_v17.json)。

| 同一0.7nm/384hex/p3/40端口；无量纲measured | GPOLY末态 | GNN末态 | 本轮解释 |
|---|---:|---:|---|
| LSQR逻辑更新数 | 6347 | 6119 | 均因预留G的时间边界结束，不是已证实停滞 |
| 原Schur相对残差；限1e-6 | 4.9022046887e-4 | 5.9447708168e-4 | 仍需约490/594倍降低，不能称只差最后几位 |
| 原native相对残差；限1e-6 | 1.9010935164e-4 | 2.3054046034e-4 | FAIL |
| 独立total-native；限1e-6 | 6.5967828368e-5 | 7.9997398281e-5 | 与上一行归一化对象不同，均FAIL |
| 散射E/curl误差；各限1e-4 | 2.6516217370e-4 / 2.6311959972e-4 | 2.4920378681e-4 / 2.4591845604e-4 | 约2.5倍场门限，已有实际场改善 |
| total E/curl误差 | 2.7747849e-5 / 2.7534627e-5 | 2.6077886e-5 / 2.5734582e-5 | 单项达到1e-4，不代替散射场和方程 |
| 最大功率差 / 能量闭合 | 8.35242984e-7 / 3.32081350e-7 | 3.51814857e-5 / 3.53192755e-5 | POLY相关单项过门限，GNN仍失败；均无official R/T/A |
| 完整GMRES周期 | 0 | 0 | IMPLEMENTATION_FAILED，不是GMRES数值不收敛 |

GPOLY散射E误差从V16已保存256步的0.146997降到0.000265162；GNN从原0步0.766071降到0.000249204。当前不再是仅loss降低。两库共同逻辑4096步的Schur约0.0010247/0.0011714，之后仍有下降；不能把预留时间导致的停止改写为停滞。最终逻辑步不同，不能仅凭末态数值宣布同工作量优胜。

V17新增正式监督wall16284.035028 s，采样同时进程树峰2577092608 B，own swap0，PSI资源重入0；formal历史下界37508.426009 s，旧辅助unknown保持。该累计是多轮研发和不同路线的账，不是已完成某个目标模型的单次耗时；未来单次部署仍必须计入所需建基、目标相关训练、设置、求解及审核。没有hidden训练，也没有独立神经加速资格。

## 2. 这次先修明确错误，不换数学问题

源码：[GMRES数值周期](../../src/solvers/resumable_trace_gmres.py)、[实际stage调用](../../src/solvers/resumable_trace_study.py)、[原BarAction](../../src/solvers/augmented_trace_lsqr.py)。

`BarAction.close(t, rhs)`返回的是完整`z=[t;alpha]`，而旧`gmres_route`把它赋给`port`后再次拼接`t`，使长度从18184变为36328。原action拒绝输入，故两库都没有保存首周期候选。这个错误位于GMRES之后的装配/审核链，不能由小型`correction_cycle`单独通过证明已修复。

新调用必须明确：`z = bar.close(t, rhs)`；`port = z[nt:]`。检查`trace.shape==(18144,)`、`port.shape==(40,)`、`z.shape==(18184,)`、`z[:nt]`与输入trace一致，拒绝二维广播和重复拼接。保持`BarAction.close`原公共语义，不为救这个caller改变其余合格调用者。同时核对原Hhat闭合残差、`b-Sz`与消端口残差的恒等式。

**已知修复及其回归是本批计划内主工作，不占用后述意外修复的根因次数，但全部耗时/调用仍计入总预算。** 先完成从真实dat解析、stage、GMRES、close、保存到原audit的端到端检查，再长时间运行；不先把两库都跑到同一个已知shape错误。

## 3. 冻结身份、数据隔离和成功定义

先读根/目录AGENTS、仓库原则、原task、全部补充合同/review、最新response/summary。本报告在同一分支明确授权新的7小时窗口、有限GMRES256和LSQR延长，覆盖旧批次相应上限；不回写旧失败/旧费用/旧判据。沿用已明确的受控共享CPU授权，其他heavy存在不是自动阻塞，真实资源压力仍必须保护。

| 冻结项目 | 身份 |
|---|---|
| 物理 | Full3D，真空0.7 nm，grazing1度/azimuth0/s，原三维缺口/背景/RHS，双Floquet和Fourier-DtN |
| 离散与数量 | 原384hex/p3/h0.175 nm/q15；full34050，trace18144，内部13824，slave2082；top20+bottom20端口 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1 |
| Si与alias | n=0.999885140474+4.32477054e-6i，epsilon=n*n；0.699999988原行alias到nominal0.7，不插值 |
| material / physical SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 / 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| mode / action SHA256 | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 / 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 SHA256 | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |
| GPOLY起点NPZ SHA256 | e4b8495c6cd9fdc1e2f0723b64ecbc0732f911e62cb74c04307f13678e1d8602；逻辑6347 |
| GNN起点NPZ SHA256 | 4006c7946e318f86e5fd785ccdc078fb819b70be5b32b3ef97743eeeabcecd32；逻辑6119 |

从V17 checkpoint_inventory/run index解析实际路径、滚动generation和Q/U/R身份；不猜目录、不使用失败G未保存向量、不从参考重建状态。每库Q保持3098列，NN补空间仍只取共同前1538列。G只需完整trace/原action/Hhat，缺Q或某份image不应阻塞已经可做的G；R需要完整可信GK与对应image。

新V18使用独立artifact、ledger、滚动槽和窗口，旧V17只读。算法`G64/G256/R`和库`GPOLY/GNN`分开登记，不靠未经验证的stage字符串截取确定库。所有新入口都做实际schema解析回归，避免重复前缀/key错误。

严格通过继续沿原门限：原Schur/native/增广及规定端口残差各<=1e-6；恢复/identity<=1e-10且slave-zero；total/scattered E/H、curl、selected复场、40复通道误差<=1e-4；R/T/A/A_volume绝对差<=1e-5、单通道功率差<=1e-6、能量闭合<=1e-5。内部求解可追求rho<=1e-8作为余量，**它不是新的强制成功门限，也不是场误差保证**；首次1e-6通过点单独保存，不因后续抛光失败而丢失。

## 4. 自动队列：修复之后必须推进真实求解

| 阶段 | 工作及目的 | 后续分流 |
|---|---|---|
| F0 | 修close接线、保存/计数与真实stage回归；复用已有ABI/恢复资格 | 合格后直接G64，不只交测试报告 |
| G64 | 两库分别从固定V17末态完成原barS的GMRES64校正 | 先8周期，进展充分再8；未合格才G256 |
| G256 | 每库至多一个长重启对照，检验短周期丢失搜索信息是否限制进展 | 先4周期，进展充分再4；不扫更多restart |
| R | 尚无原方程合格候选的库，从原V17 GK独立继续到共同里程碑 | 8192后按进展延长，最多逻辑16384及新增更新预算 |
| V | 全部无标签求解和选择冻结后，独立完整FE审核 | 保存单项与完整资格，不能验证后再回训 |

G64先两库到周期8，再执行各自已准入的9–16；G256先两库到4，再执行已准入的5–8。一库失败只隔离依赖项，另一库继续。G与R是从同一V17起点派生的不同求解路径，不把G的新trace塞进旧GK递推而仍称连续续算。某库已有原方程合格候选，优先冻结并在本方法剩余预算内少量抛光，不再为填表强制运行它的后备R。

## 5. F0：端到端回归及不再丢失GMRES成果

### 5.1 必测的完整调用链

使用已有的复数非Hermitian小packet，包含非零t_b、非零port RHS、40维可逆Hhat、非互伴C/F，调用真正BarAction和拟修复的stage候选构造函数。验证close返回完整z、端口提取、原残差恒等式、原audit及保存/读取。加入旧重复拼接的反例，要求在执行原action前明确shape报错；不能只mock一个永远返回预期shape的close。

覆盖零校正RHS、一个周期非收敛info=1、提前收敛info=0、callback内迭代数、两个周期分进程恢复、返回trace后close/audit/writer故意失败、半写/错hash/非有限、真实V18全部dat到库名和算法名映射。复用原子writer/rolling协议，不重建整个日志框架；不升级SciPy。现场确认已记录1.11.4或实际合格版本，`tol/rtol`自适应沿已验证逻辑，不能重复以关键字不同中断。

真实F0只用两个固定V17向量复核close、原audit和基线残差；固定b归一化残差向量差<=1e-8，端口小solve运算差<=1e-12，恢复/identity沿旧门限。新增真实预检总作用<=256，不重跑R1的32步配对、全部制造问题或旧FD。

**每库G64的第1个真实周期兼作端到端smoke，并计入该库8周期，不另跑一遍丢弃成果。** 第1库发生共同接线错误时先修复/复核共同调用，再启动第2库，不能复制已知失败。

### 5.2 保存顺序、异常恢复及计数

每周期开始写入parent trace/hash、输入rhs/算子身份、cycle/restart与started计数。在`gmres`返回后，**先原子保存proposed trace、inner计数和info，再调用close**；close后保存完整z/port/residual和audit_pending，原audit结束才写committed周期。audit_pending的数值可用同一个原审核器补审，不必重新做Arnoldi；补审前不用于后续迭代。

一个cycle的单调commit标记最后切换。失败返回proposed只表示数值候选，不是已接受解；未返回的cycle只能从最近完整周期边界重新计算，绝不从callback标量拼回向量。R继续每16 GK保存递推、每64保存完整场并审核。旧滚动槽不覆盖。

callback记录内步，原action包装器记录实际started/completed S/SH；周期调用结束立即落盘，修复close不能再丢已经完成的Arnoldi计数。未完成cycle的计数保守预留restart+16个原作用；若现场实现可能超出则在开始前以小测试建立更大安全上界并扣预算，不猜填实测。R沿16步未落盘预留64作用；计数、失败、重复计算和I/O费用不回滚。

## 6. G64/G256：完整原方程的残差校正

以下H是凝聚Hhat，不是未凝聚Hp；只使用原作用，不构造barS全矩阵：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\quad
\bar S=K-CH^{-1}F,\quad \bar b=b_t-CH^{-1}b_p.
```

```math
r_b=\bar b-\bar S t_b,\quad
\bar S\Delta t=r_b,\quad t_{new}=t_b+\Delta t,\quad
\alpha_{new}=H^{-1}(b_p-Ft_{new}),\quad z_{new}=\begin{bmatrix}t_{new}\\\alpha_{new}\end{bmatrix}.
```

每次一个周期，从当前完整t构造校正rhs、delta初值为0；下一周期从已提交的新t继续。数学上这是原barS的重启GMRES，不是向带结构零空间的双投影M直接套普通GMRES。G进程不加载Q/U/R，只保留原action、Hhat因子和trace。

使用现场SciPy LinearOperator/gmres：`M=None`，`callback_type='pr_norm'`，每调用`maxiter=1`，相对容差0，`atol=1e-8*norm(原完整b)`；固定物理分母不随校正rhs变小而刷新。info=1是周期用尽，不能当bug；info=0也必须做原完整audit。每周期记录原Schur/native/port、actual correction residual、callback终值及实际作用，最终只看原审核。接口参考：[SciPy 1.11.4 GMRES](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.gmres.html)。

G64最多8基础周期；若未过原方程、8周期rho较其G起点降低>=10%，且数值/资源可信，允许再8周期。若已过1e-6但未达1e-8，可在原16总周期内至多额外2周期抛光；无需因此启动G256或R。连续两个周期原Schur上升超过`max(1e-10,100*观测重复作用差/norm(b))`时，保存异常并做一次有界接线/复算检查；不能根据更好看的callback接受。合法范数之间变化不自动等于代码错误。

G64完成基础/扩展预算或确认停滞后、仍无原方程合格状态时，准入**唯一restart=256后备**，从该库最后可信G64周期开始；若G64始终因接口不可信而没有周期，先修公共接口，不能用G256绕过。除restart外所有设置不变。先4周期；rho较G256起点降低>=10%且未合格，才再4周期，合计<=8周期。若已过1e-6，至多1个剩余周期抛光到1e-8。这检验重启长度影响，不是证明短重启就是根因；不能再添加128/512/1024、LGMRES、ILU或其他扫描。

较长重启会保存更多搜索方向并增加正交化成本，可能改善也可能无效；SciPy文档明确该取舍。仅Arnoldi基的derived内存为18144×(m+1)×16 B：m64约18.0 MiB，m256约71.2 MiB；不是全过程RSS。旧Q/U/R在G中没有必要驻留，更长restart也不等于新的全局FE直接分解。

## 7. R：不丢掉已经有效的LSQR进展

若两种G的可执行队列结束后，本库仍无原方程合格候选，独立恢复**原V17末态GK**，不是从G终态恢复旧递推。V17收口主要来自时间预留，不能将其当作停止延长的数值证据。原Q/U/R、Pt/Pr、M/MH和完整恢复沿Review V13/V14不变，不重新造基或权重。

```math
M=P_r\bar S P_t,\quad f=P_r\bar b,\quad
v=P_t y,\quad c=\operatorname{solve}(R_A,U^H(\bar b-\bar S v)),\quad t=v+Qc.
```

先两库按共同逻辑7168、8192推进；此后按1024步里程碑交替。到8192及以后，最近1024逻辑步原rho下降>=10%、gap/identity正常且有本库时间，才允许下一块，绝对逻辑上限16384、新执行GK<=10300/库。统计包括修复后重算，正常slice不是重启；一库blocked则另一库继续。第一段不要求先出现新的参考场正信号。

若rho连续三个256步区间均下降不足1%，可提前收口本R；不能因单点小波动或达到旧8192上限就停止整批。每64步原audit和投影恒等式、每16步完整递推保存保持。估计与真实投影残差gap>0.1连续两次且原作用正确时，每库最多一次明确的残差校正重启，沿Review V14公式，base trace/epoch入档；不以重启掩盖原恒等式失败，不清零预算。

记录首次原方程1e-6通过点；可在同一剩余预算内再最多512 GK求更小残差，目标1e-8，无进展则保留已通过点收尾，不要求必须达到内部更严目标。缺/坏GK时允许从真实V17完整trace作上述一次校正重启；G结果不能混入这条连续LSQR对照。若另行报告G→R组合将超本批范围，不自动实施。

本批不重跑空Q4096负结果，不重新比较所有旧基，不训练hidden。比较G与R时同时报告起点、逻辑步、真正新增工作、原作用、wall和历史建基成本；不同链不能伪称同初值连续递推。

## 8. 验证、达标推进及本批终点

所有求解、选择和hash冻结并退出后，独立FE进程一次读取原REF7；参考不进入预检权重、方向、停止、restart、初值或路径选择。先只依原rho和数值Gate指定候选；验证后不回训、不校幅相、不用参考误差挑新的最优点。

最多12个去重状态：两个V17起点；每库G64末态、G256末态、R末态（至多6）；每库首次原方程通过点（至多2）；每库实际选择的最终候选（至多2）。缺某路径不影响其余验证；相同z去重。全部指标按第3节，原REF7非零残差与native重新记录，无新LU。

| 观察 | 分类与后续 |
|---|---|
| G接线/保存失败 | IMPLEMENTATION_FAILED；修复与依赖隔离，不称GMRES方法失败 |
| G合法运行但残差停滞 | GMRES64或GMRES256具体受控负结果，后续R仍可做 |
| LSQR原残差继续下降、场未过门限 | FIELD_AND_EQUATION_PROGRESS_NOT_QUALIFIED；不称成功或放宽标准 |
| 原残差过门限、场仍不合格 | EQUATION_PASS_FIELD_FAIL；保留全部状态，后续需要独立误差/离散研究，不用R+T+A替代 |
| 原残差和全部同离散物理量通过 | MICRO_DISCRETE_PASS_ONLY；核算该链完整时间/RSS，不宣称0.7nm目标规模或网格收敛 |
| 所有可信路径到限仍无实质进展 | 完成一个残差/场/代价原因表，收口这套固定无PC延伸；不无限增加步数或新算法 |

若取得micro离散通过，利用已有数据另写下一阶段容量/精度Gate清单；本批不自动新p4参考、不放大几何、不换MPI/GPU或解最终大模型。最终目标仍需accuracy-qualified网格、通道库存、分布式/streaming存储与可扩展PC，不能将每步稠密Q/U投影直接当成最终生产架构。

## 9. 连续执行、修复优先级与资源保护

本轮用户明确要求多做工作、不要轻易中断。F0通过后自动完成已授权队列，不逐小步等待回复。**原求解链错误优先于非关键格式整理；可读日志中缺少一个展示字段不应打断正确的活跃slice并改变HEAD。** 数值身份、真实预算或安全监督缺口则必须修复，不能延后到会造成不可信计算。

除计划内F0外，最多6个根因级意外修复循环，每次<=900 s、累计<=3600 s，同根因最多2轮；一次根因修复可包含数次短命令，不将每个拼写修正单独算成一次新研究失败。每轮记录定位证据、修改范围、起止时间、测试与受影响重放。修复额度不得用来扫数值参数；数值不收敛不是bug。共同接口错误先修公共根因，不在另一库重复已知失败。超出修复范围时只隔离受影响项，继续独立可做项及交付。

从Codex接手开始记录新UTC/Asia-Singapore/单调start：总elapsed<=25200 s，start+23400 s停重负载，最后1800 s收尾。实现/测试/修复/冷却/计算/验证/提交全部计时，窗口不因上下文、重入或版本刷新。继承独立进程树watchdog，不依赖对话保持在线。

正式数值队列开始前冻结相同单库上限B=min(10000 s, floor((heavy_remaining-900 s)/2))；不得后调B偏向某库。每库全部G64/G256的设置/加载/求解/写盘合计<=1800 s，R使用本库剩余；900 s总余量用于验证及意外开销。B很小时先完成可做的真实G周期与冻结验证，不谎称已跑完整长路线。某库提前成功/blocked，另一库可用自己的剩额，但不自动继承被取消库的B。

同时生效的数值上限：每库G64<=16周期/1024 Arnoldi、G256<=8周期/2048 Arnoldi；每库新GK<=10300且逻辑<=16384；单库在线原S/SH<=28000，全批含设置/检查/修复<=66000；新A列<=6196、image QR<=2（仅确实缺失时）；原audit<=512，独立场状态<=12；新增持久artifact<=3 GiB。所有callback、close、审核、丢失周期上界、重复加载和重放计费，不把“组合调用一次”冒充所有底层S/SH只一次。界限以最早到达者为准，不要求跑满。

沿用共享CPU：现场选空闲物理核并避开忙SMT，MPI1、数学/Torch线程1、DataLoader0、GPU不使用；计划常驻<=8 GiB、整树warn12/hard16 GiB、own swap0，磁盘自由>=50 GiB、Task042 artifact总量<=20 GiB；旧系统余量及邻增长规划保持。一次只驻留本任务一套数值heavy，不修改邻任务、其进程/锁/环境/亲和性/watchdog，不升级ABI/BLAS/CUDA，不改系统swap或把原生Ubuntu当WSL。

原memory full PSI avg10>=0.1且连续三次5 s观察的停止规则不放宽；PSI数值是停顿时间百分数，不是RAM百分比，见[Linux PSI](https://docs.kernel.org/accounting/psi.html)。触线只停止自身后代，先持久化安全点的请求不得延误硬停止。压力停止后释放大对象，冷却至少120 s；最多600 s轻量观察，full avg10<0.05连续60 s且所有资源Gate恢复，才准入。每库资源重入<=2、全批<=3、累计等待<=1800 s；计入窗口。压力不安全时不能通过换G/R逃避保护，持续不安全就做真正轻量工作并收尾。

旧formal下界37508.426009 s和unknown费用保持；新formal、整批elapsed、累计方法lineage分别报告，不把不同stage峰值相加，不把父子嵌套计时重复加总。无cgroup委派时准确写0.5 s采样监督，不宣称连续内核限额或零邻任务干扰。

## 10. 实现、提交与正式入口

只改本Task必需数值/adapter/测试/输入/记录；数值核在src/solvers，复用原action、BarAction、LSQRState、rolling、原子writer和验证器。新GMRES restart参数显式opt-in，旧默认64与旧records语义不改。优先参数化已有薄driver，不复制另一套大型campaign脚本。所有真实新dat解析及stage注册需进回归。

先小测试、提交clean实现再正式运行，source绑定实际运行提交。下面是待实现入口，不是本review发布时已经存在的命令：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v18_gmres_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v18_gmres64_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v18_gmres64_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v18_gmres256_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v18_gmres256_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v18_continue_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v18_continue_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v18_verify.dat
```

按队列与条件执行，不能盲跑八条；每个slice/resume有明确的one-run dat和共同campaign预算。前置Gate通过即连续推进；阶段提交仅在本任务活跃受检数值退出后，不修改运行中的HEAD。shell使用set -e，对普通数值停止由已登记driver显式分流，不吞异常继续假装通过。

每run保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/material/mode/数组hash、source_sha、环境/ABI/MPI/线程、run_summary和全过程资源。新保存协议变动须故障注入回归；checker从原值重算分类，不信status字符串。旧task/review/response/raw不变，negative和unknown不可回填PASS。

## 11. 交付与停止

提交`response_v18.md`、`outcomes/gmres_repair_residual_completion_v18.md`与紧凑records：input/lineage与两个起点、close端到端/保存故障回归、阶段配额/分流、G64/G256逐周期/真实Arnoldi计数、R逐审核/recurrence gap、checkpoint库存、repair/reentry journal、同工作量比较、原场/40通道/功率与Gate、资源/生命周期、run index/changed_files/tests/publication。大型矩阵/向量保留ignored artifact及hash，不进Git。

同步summary、最新任务导航、development_progress、development_model_registry。GMRES接线修复、有限长重启、旧LSQR连续进展、物理资格和神经贡献分开说明；GMRES省内存不等于省掉所有前期建基，不能只报末段求解时间。对失败保留一个有依据的下一建议，不自动开启新预条件器、任意网络训练、强逆或最大模型。

按仓库Markdown规则检查math围栏/表格/链接及精确GitHub页面；未取得真实渲染如实标NOT_VERIFIED，不伪称视觉通过，也不为无关页面问题取消已经合格的数值队列。

只推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。总截止、安全/修复上限或全部可执行队列完成后，清场并报告完整HEAD/base/upstream/worktree、真实运行source、实际执行/未执行路径、原方程与完整场资格、工作量/RSS/时间、残余blocker，停止等待review。未经最终review及用户授权，不merge master或其他分支。
