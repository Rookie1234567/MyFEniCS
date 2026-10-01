# Review V16：V18审查、续算末态残差校正与有限跨周期保留

## 0. 决定、快照与本批消除的障碍

**接受V18的GMRES接线修复、完整落盘和独立场证据，不授予完整有限元或神经加速资格。下一批从两库各自的V18-R-FINAL出发，先接通尚未执行的“较准确LSQR场→GMRES256残差校正”；原方程仍不合格时，配对检验一个固定的LGMRES(256,3)跨周期方向保留方案。停止把另一轮数小时的原样LSQR延长作为默认后备。**

本批针对的blocker是：已有场接近或达到同离散场门限，但原方程残差仍约1e-4；此前GMRES处理的是较早V17场，尚未检验它与最新R末态的顺序组合。进一步要区分“需要较好的起点”和“重启时丢失搜索方向”这两种可能。后者只是待检验假设，不是已测得的唯一根因。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42_neural_coarse_inverse
worktree                   = /home/fenics/Projects/NN-Lab
review_date                = 2026-10-01
reviewed_HEAD              = a88326967ffabe7f088dfdd289dc8b66550a7ba4
reviewed_commit_UTC        = 2026-10-01T07:20:03Z
reviewed_commit_Singapore  = 2026-10-01T15:20:03+08:00
reviewed_latest_commit     = Task042 V18 record exact-page publication and delivery receipt
original_base_SHA          = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review            = review_report_v15.md
previous_review_commit     = f86eff1e1ed334e82123c734c60918beaa19dfc1
latest_response_reviewed   = response_v18.md
V18_numerical_source       = d3e5800ee379168ca33bc3dae595de1c8aa71063
V18_checker_source         = eb97b4214d4d0a4969ea4eb0038300f0ab214efa
next_batch                 = V19_POST_LSQR_RESIDUAL_POLISH
response_required          = response_v19.md
decision                   = ACCEPT_EVIDENCE_CONTINUE_BOUNDED_RESEARCH
old_p4_inverse_route        = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate        = NOT_QUALIFIED
master_merge               = NOT_APPROVED
```

最终目标保持：约2 TB整机物理内存内，端到端48小时求得一个新的0.7 nm非可分三维周期单胞合格有限元解。本批仍是原micro、单核16 GiB研究配额，不是最终资源配置或目标规模验证。ChatGPT审查的是远程合同、回应、紧凑原始记录和相关代码；没有SSH运行工作站、读取全部ignored数组或实测当前资源。历史为measured/recorded，数学与容量为derived，新队列为planned/not_run。

## 1. V18结果：哪些已经改善，哪些仍然失败

依据：[Response V18](response_v18.md)、[完整结果](outcomes/gmres_repair_residual_completion_v18.md)、[候选CSV](outcomes/records/candidate_comparison_v18.csv)、[逐GMRES周期](outcomes/records/gmres_cycles_v18.csv)、[R审核历史](outcomes/records/iteration_history_v18.csv)、[费用](outcomes/records/resource_costs_v18.json)、[checkpoint](outcomes/records/checkpoint_inventory_v18.json)。

| 原0.7nm/384hex/p3/q15/40端口；无量纲measured | Schur；限1e-6 | native；限1e-6 | 散射E；限1e-4 | 散射curl/H；限1e-4 |
|---|---:|---:|---:|---:|
| GPOLY：V17起点 | 4.902204689e-4 | 1.901093516e-4 | 2.651621737e-4 | 2.631195997e-4 |
| GPOLY：V18-G256末态 | 1.193131686e-4 | 4.627009796e-5 | 2.639326325e-4 | 2.637992956e-4 |
| GPOLY：V18-R末态，逻辑12831 | 1.463077182e-4 | 5.673868638e-5 | **8.079990122e-5** | **7.981925902e-5** |
| GNN：V17起点 | 5.944770817e-4 | 2.305404603e-4 | 2.492037868e-4 | 2.459184560e-4 |
| GNN：V18-G256末态 | 1.461674116e-4 | 5.668427496e-5 | 2.455494003e-4 | 2.452374442e-4 |
| GNN：V18-R末态，逻辑11903 | 1.995563747e-4 | 7.738871675e-5 | **1.001991308e-4** | **9.874963985e-5** |

GPOLY-R的场项目已有单项通过，但最大通道功率差1.588064029e-6仍高于1e-6，原Schur仍为门限约146倍。GNN-R的散射E略高于1e-4，不能四舍五入为PASS；其最大通道功率差6.306122297e-6和能量缺陷1.080939032e-5也失败。GPOLY-R能量缺陷1.637592699e-6单项通过，不替代方程。完整资格0/8，全部功率仍是UNQUALIFIED_DIAGNOSTIC。

V18两库各完成16个G64和8个G256周期，已不再是接口未运行。G64→G256使相对V17的残差下降约75%，场误差变化很小；独立R明显改善场。R结束于各自冻结wall边界，不是证实停滞。此前按原rho选择G256的过程保持，不因后来看到R场更好而回写选点。

正式监督wall新增19905.129134 s，历史formal下界57413.555143 s，旧辅助unknown保持；同时采样树峰2576646144 B、own swap/VRAM0；意外修复、资源重入、GK重启均0。这个多路线研发累计不是某条成功单次求解的时间。新报告不把“2.4 GiB”当成原始建基全过程或目标规模容量。

## 2. 为什么这次不是再重复上一批

V18的G与R从同一个V17起点分别出发；从未让G处理V18-R-FINAL。现有证据支持做该顺序组合，但不保证降残差时场精度一定保持。故两库都固定使用各自R最终状态，不能只根据历史参考误差挑一库，也不混合两条解或用参考校幅相。

GMRES每次重启只保留当前解，丢弃本周期的多数搜索方向。新备选LGMRES保留少量之前的修正方向，加入下一周期的搜索空间；它可能减少重复搜索，也可能无效。参见[原作者论文](https://doi.org/10.1137/S0895479803422014)和[SciPy 1.11.4 LGMRES契约](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.lgmres.html)。本批只测试inner_m=256、outer_k=3，不扫描长度、保留维数或PC。

这是一项确定性的原方程校正，不是神经训练，也不是给任意残差学习一个强逆。两条起点的历史Q均含共同随机神经G0；本批G/L进程不需要加载Q/U/R，但这些基及上游LSQR的必要成本不能从方法lineage中消失。成功也不能单凭末段很快就宣称神经加速。

## 3. 权威、冻结身份与数据权限

先读根/目录AGENTS、仓库原则、原task、全部补充合同/review、最新response/summary；当前任务目录无另命名supplement时记录实际清单，不猜造。旧原文和负结果不改。本报告明确覆盖Review V15对本批“不得LGMRES”和旧8周期G256上限的限制，仅授权下面固定队列；旧p4路线、loss权重/网络/基扩容扫描继续禁止。

| 冻结项 | 数值或身份 |
|---|---|
| 物理 | Full3D complex128，0.7nm，grazing1度/azimuth0/s，原三维缺口/背景/RHS，双Floquet与完整Fourier-DtN |
| 离散 | 384hex/p3/h0.175nm/q15；full34050、trace18144、内部13824、slave2082；top20+bottom20端口，z18184 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1；离线读取，不再索要 |
| Si | n=0.999885140474+4.32477054e-6i，epsilon=n*n；source0.699999988明确alias到nominal0.7，不插值 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA256 | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| modes / action SHA256 | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 / 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 SHA256 | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |
| GPOLY-R-FINAL NPZ SHA256 | 6bdf82217834cd773540971df152fa2b9a6b97c08817ec8e81eeddea0ad33a85；逻辑12831 |
| GNN-R-FINAL NPZ SHA256 | 873619eb26aeb00c2d8eba333c9b0562456babf7994f0ce5b852ffcaae3867ef；逻辑11903 |

实际路径从V18 checkpoint_inventory/run index与状态manifest核实。NPZ文件hash与z数组hash不能混用。新V19的ledger、artifact、缓存、滚动槽和窗口独立，V18只读；不把历史FROZEN/预算文件改回未关闭。本批不恢复或改写旧GK，不让G/L结果回填旧递推。缺一库起点只隔离其依赖路线；缺旧大Q不阻塞只需完整trace的校正。

本研究已使用历史REF7审核结果来设计下一步，不能声称全新blind heldout test。但本轮求解进程仍不得读取REF7数组、旧参考拟合权重或误差向量；参考仅在所有队列冻结后独立审核。不根据本轮参考结果继续选参数、选点或回训。

## 4. 数学对象与两条校正路线

H是原凝聚40维Hhat，不是未凝聚Hp；只作原作用，不形成全局barS或正规方程：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\qquad
\bar S=K-CH^{-1}F,\qquad \bar b=b_t-CH^{-1}b_p.
```

每库固定原点t_b为该库V18-R-FINAL。定义一个全程不变的校正问题：

```math
r_b=\bar b-\bar S t_b,\qquad
\bar S x=r_b,\qquad x_0=0,\qquad
 t=t_b+x,\qquad\alpha(t)=H^{-1}(b_p-Ft).
```

所有正式选择用实际完整z=[t;alpha]及原b-Sz；分母始终是原完整物理b，不随r_b或阶段改变。内部atol=1e-8*norm(b)、相对tol/rtol=0；正式原方程门限仍为1e-6，不将1e-8升级为强制门限。零r_b只作明确零分支，不能把小而非零r_b截为零。

**P：POST-R-GMRES256。** 复用V18已资格化correction_cycle/close_point与返回后保存。restart=256、每调用maxiter=1、callback_type='pr_norm'、M=None；一次调用是一个重启周期，不是一个Arnoldi步。既有逐周期残差校正与上述固定r_b、累计x的表达在精确算术等价，实施须明确所用形式及原残差配对，不重复加t_b。

**L：POST-R-LGMRES256-K3。** 每库独立从同一个t_b和x=0开始，outer_v=[]；不能由P终态或另一库warm start。使用现场已安装SciPy的lgmres/LinearOperator，inner_m=256、outer_k=3、M=None、prepend_outer_v=False、store_outer_Av=False、maxiter=1，下一调用传入上次完整x和outer_v。所有调用使用同一个r_b。保留向量只来自本路线先前的无标签修正；没有参考、Q列、teacher或另一库方向注入。

```math
\mathcal W_k=\mathcal K_{256}(\bar S,r_k)
 +\operatorname{span}\{d_{k-1},d_{k-2},d_{k-3}\},\qquad
r_k=r_b-\bar S x_k.
```

此式解释方向保留意图，不代替现场SciPy实际算法。outer_v是(v,Av)列表；本批Av=None，由原算子重新作用，不保存可能过期的像。至多3个n维复方向的持久数组载荷为870912 B，约0.831 MiB；内部Krylov向量、库workspace、FE/action与审核的全过程RSS另测，不能只报这三个向量。

LGMRES没有GMRES的callback_type接口，其callback(xk)是外层状态，不能当内Arnoldi计数。查现场签名、版本和源码，保留已验证tol/rtol适配；不得升级环境。采用“单外层调用、携带方向列表”的显式有限驱动，不宣称与一次长lgmres调用逐位等价：例如内部容差控制局部量可能在调用边界重置。方法身份登记BOUNDARY_DRIVEN_LGMRES256_K3，不隐藏这一差异。

## 5. C0：短准备、真实接线和小回归

先复用V18已通过的完整z返回值契约：z=bar.close(t,rhs)，port=z[nt:]；18144/40/18184长度及组成必须相符。每个新起点重算close、原残差、原audit，确认保存的残差和当前作用以norm(b)归一化差<=1e-8，原恢复/identity<=1e-10，port小解运算差<=1e-12、slave-zero。源或ABI确有不一致先修，不用重新生成大基作为预检。

新增小测试必须覆盖真实BarAction的复数非Hermitian、非互伴C/F和非零40-port RHS；校正x到t再到z；错用完整z作port、重复加t_b、混用r_b与原b的反例。至少一项小测试跨多个短内周期，确保outer_v非空；不能只用一周期已收敛的玩具例子认证方向保留。

L测试还覆盖：outer_v原地修改及事务copy、3方向上限、Av=None、不同算子/库/父状态hash拒绝、返回状态与原作用差、info=1、没有实际更新、非finite、返回后close/audit失败补审、进程间保存读取后下一次单调用与同一单调用驱动等价。字段有版本/type检查，不以default=str吞掉结构。small inner_m可缩小以触发多周期，但正式固定256。

在原点仅做短的真实重闭合审核；两库首个正式P周期计入正试验，不另做重复smoke。新L第一个正式外层调用同时验证真实返回与原审核；其失败不取消已可信的P路线。C0新增真实S/SH<=256，不重跑V17完整恢复测试、旧FD、旧随机压力或teacher。

## 6. 自动队列、工作量与进展规则

| 阶段 | 具体工作 | 后续 |
|---|---|---|
| C0 | 读固定起点、最小新接口/保存测试、冻结预算 | 合格就进入P，不只交接口报告 |
| P0 | 两库各完成至多8个POST-R-GMRES256周期 | 普通负结果继续另一库；已过原方程者冻结 |
| L0 | 对P0仍未过原方程的库，从该库相同R原点做8个L周期 | 从空保留列表开始；L实现阻塞不禁止P继续 |
| C1 | 未合格且有进展的P/L按8周期块轮转继续 | 每路线最多64个完整周期/外层更新 |
| V | 全部求解/选择冻结后，独立审核并核算lineage | 不在审核后回训或追加路线 |

每个库的方法配对只使用该库相同原点；两库R逻辑步12831/11903不同，不能宣称它们的上游成本相同。顺序P-GPOLY8、P-GNN8、合资格L-GPOLY8、L-GNN8，再按相同顺序轮转；一条blocked不取消其他独立队列。一次只运行一个本任务heavy。

首8周期不需要新的场参考正信号。第8周期未合格时，最近8周期原rho下降>=5%才再给8周期；后续每8周期同规则，rho=max(原Schur,native,规定固定rhs端口)。若某路线只下降0–5%，记录SLOW_PROGRESS_BELOW_EXTENSION_RULE，不泛化为数学不可能；不按更小门槛反复重启获得额度。另一已授权方法仍可继续。两连续周期原Schur增加超过max(1e-10,100*原点重复作用差/norm(b))，先用同状态复算核对；超出数值可分辨范围且未定位bug，则停止该路线，保留候选，不偷偷线搜索或校幅值。

任何路线首次原方程1e-6通过即保存不可覆盖FIRST_PASS。该库另一尚未运行的后备可记NOT_RUN_EQUATION_ALREADY_PASS，已在安全边界的另一方法可冻结，不强制跑满配对。当前方法至多再2个剩余周期求1e-8余量；没有余量或不下降则保留首过点。原方程通过不保证最终场通过，必须V审核；本批不能在读参考后再重开L。

每路线除了最多64周期，还同时受原作用与wall上限约束。L的256/259只是配置或上界，实际Arnoldi数若现场库不暴露就写unknown；不得拿callback次数或直接写256冒充实测。以原action包装器started/completed次数作主要同工作量比较，G已有真实内步记录继续保留。报告同原S作用和同wall附近的实际审核值，不插值造收敛结果。

## 7. 持久化、恢复和数值资格

复用V18“返回→proposed→closed/audit_pending→audited→commit”协议。P/L均在算法返回后、端口闭合前先原子保存实际x/t；L必须同时保存同一返回边界的outer_v方向、顺序、算法配置及父状态hash。copy待修改列表，未提交调用不得污染最近合法checkpoint；Av=None不序列化成假向量。numeric与完整z/audit共享generation/hash，commit最后切换。

一次L调用info>0仅表示库未报告收敛，不等同可信周期：检查finite、是否实际返回更新、原残差及方向库存。SciPy可能在内部异常时返回原x，不能看到info=1就断言完成256个方向；写NO_RETURNED_UPDATE/原因可知程度。不能从callback标量补造返回状态。调用未返回则回到最近完整周期，费用包括丢失上界和重做；调用已返回但审核失败只补close/audit，不重做该周期。

原残差资格：实际闭合残差与barS校正残差以原b归一化差<=1e-8；原恢复/Schur-native identity<=1e-10，slave=0，端口与finite保持。每周期都用真正的原S审核，不以保留空间的小LS残差或info=0替代。所有原总场/散射场及功率门限沿§8，不以新的诊断归一化降低标准。

每次启动前以小测试确认单调用action上界，默认保守预留320次底层S/SH（256加至多3个保留方向及原残差/闭合/审核余量）；实际可能超出时不得先运行再补账，应收紧调用或在既定全批预算内登记充分上界。返回立即持久化精确计数，未完成调用保持下界/上界，预算按上界扣。这里不是给每周期强制执行320次作用。

## 8. 冻结后验算与结论分层

求解、分流、所有state/hash和预选结果冻结且数值进程退出后，独立FE环境才读原REF7。最多12个去重状态：两R原点、各已执行方法最终状态最多4、各首次原方程通过点最多4、两库P第8周期最多2。各方法最终状态按原rho/合法commit确定，不能查看参考后选择其余更优点；相同z只验证一次。

完整检查原Schur/native/增广及规定端口<=1e-6，恢复/identity<=1e-10、slave-zero；total/scattered E/H、scaled-curl、selected复场与完整40复通道<=1e-4；R/T/A/A_volume绝对差<=1e-5、每通道功率差<=1e-6、能量闭合<=1e-5。近零规则复用原审核，不从功率反推复振幅，不校幅相。参考非零残差及独立native重记，无新LU。

| 结果 | 正确结论 |
|---|---|
| P/L进一步减小原残差且保持场精度，但未全过 | FIELD_AND_EQUATION_PROGRESS_NOT_QUALIFIED；不是成功 |
| 原方程过、场或某功率项目不过 | EQUATION_PASS_FIELD_FAIL；保留first-pass，禁止只发布R/T/A |
| 全部同离散指标通过 | MICRO_DISCRETE_PASS_ONLY；尚无p/h、目标规模或48小时生产资格 |
| L胜过同起点P | 本固定校正的跨周期保留收益，不是NN训练增量或普遍PC资格 |
| P更好、L无用 | 保留L具体负结果，不为NN/新算法标签强选L |
| 合格接口下两方法到限仍失败 | 收口本次固定无PC抛光队列；列剩余残差/场/成本，不继续同设置循环 |

基于历史“场改善而残差仍大”只提出优化假设，不从这些数据臆造全局条件数、缺失模态或唯一根因。若全部失败，仅整理现有周期的下降率、修正范数/原响应和资源对照，不再追加全局谱、监督拟合、新权重或数小时LSQR。后续更强求解机制需下一份review。

## 9. 成本、资源、自主执行与停止

新start起总elapsed最多14400 s，start+12600 s停止重负载，最后1800 s交付；包括实现、测试、修复、冷却、求解与审核，不能仅从第一P周期开始计时。独立deadline/进程树watchdog继续，旧窗口和费用不刷新。队列开始冻结每个(库,方法)相同wall上限B=min(2700 s,floor((heavy_remaining-900 s)/4))；资源/时间不足按实际完成有限前缀，不取消全部可做工作，不转移被取消路线额度制造不公平对照。

全批原S/SH<=80000、单(库,方法)<=19500；每路线完整周期<=64，原audit<=300、独立场状态<=12；新A/image-QR、Q生成和新GK均0；新增持久artifact<=2 GiB。全部前置测试、拒绝/失败/重入和已完成算法的补审计费。数学上的方法储存量只列derived，RSS实测全过程；父子/叶计时不重复相加。

沿既有用户受控共享CPU授权，其他heavy不自动阻塞；每次现场选空闲物理核并避开忙SMT，MPI1、数学/Torch线程1、DataLoader0、GPU不用。规划常驻<=8 GiB、树warn12/hard16 GiB、own swap0；保持max(128 GiB,effective_total的10%)系统余量、邻增长规划128 GiB与本任务16 GiB，磁盘自由>=50 GiB、Task042总artifact<=20 GiB。不得删除旧负结果腾空间；本批不加载Q/U/R，不把缺这些大数组当G/L必然阻塞。

原PSI full avg10>=0.1连续3次5s检查的保护不放宽。压力停止后清理自身负载，最少120s冷却、最多600s观察；full avg10<0.05连续60s且所有余量/锁/CPU检查合格才重入。每库最多2次、全批最多3次、累计等待<=1800s，计入窗口。算法切换不能绕过资源保护；持续不安全完成轻量整理并收口。不改变邻任务、其锁/优先级/亲和性/watchdog或系统swap/ABI/BLAS/CUDA。

复用V18没有新接线失败的成熟部分；不要再整体重写driver和计数系统。允许最多4个意外根因级最小修复，每次<=900s、累计<=2400s、同根因最多2轮；普通不收敛不是bug。公共错误先修一次再继续相关路线，不让另一库重复已知错误。非关键展示字段和格式问题延后至安全阶段，不能为此停止正确活跃slice改HEAD；身份、真实预算和安全缺口必须处理。可信前置Gate通过就完成已授权队列，不逐小步等待用户确认。

单次成本分三层报告：本批增量实测；各完成链实际所需上游基生成/设置/LSQR/当前校正/审核的可核账；所有研发尝试累计下界。不得把本批不加载Q解释为此前不需要Q，也不得把两个库及失败研发的总和称为某一个解的部署时间。无法准确重建的上游部分标unknown，不补造48小时估计。

## 10. 实现、正式入口、提交与交付

新数值adapter置于src/solvers，复用BarAction、close_point、cycle_commit、RollingCheckpoint、原验证器和受控driver；参数化已有薄队列，不复制又一套大型solver。新增L的事务保存作为显式新类型，不静默改旧GMRES/LSQR schema；实际新dat解析、method/library映射和父状态载入进入测试。未授权改变原生产默认。

先小回归、commit clean、validate，再按条件执行下列待实现入口，每个slice/resume对应明确one-run输入且继承同一campaign预算：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v19_post_lsqr_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v19_post_lsqr_g256_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v19_post_lsqr_g256_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v19_post_lsqr_lgmres_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v19_post_lsqr_lgmres_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v19_post_lsqr_verify.dat
```

这些入口在review发布时尚未实现，不得假称已运行。所有正式run绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/material/mode/action/状态hash、实际source_sha、环境/ABI/MPI/线程、run_summary及全过程资源。旧task/review/response/raw不改；不重跑V18 G64/G256或R整个campaign。

提交response_v19.md、outcomes/post_lsqr_residual_polish_v19.md，及紧凑records：输入/父状态lineage、短接口测试、P/L逐周期真实原audit与实际matvec、方向库存/恢复/故障测试、配额分流、first-pass/terminal/checkpoint、完整场/40复通道/功率、same-work、repair/reentry、费用与生命周期、run index、tests/changed_files/publication。不重复将大型嵌套审计复制到多个JSON；向量/方向只放ignored数组，紧凑表链接hash。

同步任务导航、summary、test_summary、changed_files、development_progress与development_model_registry。按Markdown规范检查math围栏/表格/链接和精确GitHub页面；无法取得视觉证据写NOT_VERIFIED，不冒充渲染PASS，也不因页面工具缺失取消可信数值队列。本批不新p4参考、不放大模型、不启用GPU、不merge。

只推送git push origin HEAD:refs/heads/task42_neural_coarse_inverse。总截止、安全/修复上限或全部可执行队列完成后清理自身进程，报告完整HEAD/base/upstream/worktree、实际source、各路线起点/实做周期/原方程和场资格、全过程资源/上游成本缺项及唯一下一建议，停止等待review。
