# Task041 Review V12：分清预条件子解与原方程，停止8步失败重建循环，推进0.7 nm实算

## 0. 决定、身份与覆盖关系

**当前阻塞已经改变。80 GiB资源合同生效，0.7 nm缩减pilot的两侧p4 numeric已经完成；最新失败不是OOM，也不是逐列Schur构建，而是模态辅助GMRES达到固定8步后尚未达到1e-3，由包装器直接抛错并清场。与此同时，原侧区BAL_H求解多次跑满128步、残差仍为约2.3%–25.3%，表明短波长下预条件质量也是实质问题。不能继续把所有失败都称为bug，也不能在尚未试过合理有界工作量前宣布这条路线不收敛。**

本轮保持无逐列Schur路线、原物理与精度，允许调整的是**预条件器内部的求解预算和不精确返回合同**。优先用较便宜的fixed-H6、最多32个模态步推进真实外层；严格区分内层目标是否达到、返回值是否可作为PC，以及最终原方程是否通过。只保留已经实现的fixed physical BAL_H作为一次条件备选，全部使用同一份存活侧区因子。W5弱显著级修正继续按用户决定延期，不占本轮计算资源；不处理node1硬件。

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                = 2026-10-10, Asia/Singapore
reviewed_base_SHA          = 623ded3ad75214f2251c7cee7779fffe56524e31
latest_commit              = docs: clarify V11 modal failure accounting
latest_commit_time         = 2026-10-10T01:44:19Z (09:44:19 UTC+8)
latest_runtime_source      = 598596b029ce9d952e3587837b3b217320909182
latest_runtime_invocation  = 45a94a21808643a0b446c357c39fa48c
previous_review            = review_report_v11.md
reviewed_response          = response_v13.md
response_required          = response_v14.md
batch                      = task041_v12_w0p7_bounded_inexact_pc
primary                    = fixed-H6 modal feedback + original right FGMRES
conditional_backup         = fixed_physical_balh_once (already implemented)
W5_weak_significant_fix     = DEFERRED_BY_USER, historical comparison FAIL retained
swap                       = observe_only, no swap-only launch/stop/final veto
ordinary_default           = unchanged
master_merge               = NOT_APPROVED
```

本轮消除的blocker是“已付出构造成本，但预条件子解的过窄工作合同反复终止原方程计算”。本轮属于求解器、性能与执行治理；不是已经取得0.7 nm收敛或网格资格。长期目标仍为**0.7 nm、50×25 nm目标周期单胞、约2 TB整机物理内存且有系统余量、48 h完整计算**。当前Hybrid仅适合内部满足模态传播假设的结构，不代表任意非可分三维Full3D已通过。

本报告明确覆盖V9–V11在当前注册W0.7研究分支中“模态max_it=8、9/10次作用且任何内层未收敛均终止”的合同；授权§3的有界不精确PC及§4的单次条件恢复。**不覆盖原全局五残差、原A4物理/增广残差、接口和物理门，不将旧FAIL改成PASS。** V11的80/72/8 GiB与384 GiB node0 floor保留。用户最近的W5延期指令高于V11第5节；P2/polish本轮不做。Response V13已回应V11，故新增V12，不改旧review。

## 1. 最新证据审阅

固定来源：本base的[Response V13](response_v13.md)、[summary](outcomes/summary.md)、[交付进度](outcomes/shortwave_delivery_v11.md)、原task和适用AGENTS。任务目录未列独立补充任务书。原task、V11及根/docs规则的已读版本以同blob核对复用；不把早期段落的“尚未实现”覆盖后续已执行事实。下列是已推送记录，不是实时SSH监控。

| 对象 | 实际事实 | 裁决 |
|---|---|---|
| W5成功基线 | fixed-H6 warm consumer 16.643 h；原逐列版本56.146 h；自身原五残差/物理/finalizer通过 | 接受固定案例已有进展；非隔离时间差不是单一修改的严格因果收益；弱显著级比较负项保留并延期 |
| 0.7 nm H6场 `797ae388…` | 两侧numeric及8次fixed反馈检查通过；outer记录到1；当时global真残差约0.14385 | 不再是容量前置停止；尚无完整解 |
| 该场modal第2次solve | max_it=8，reason=-3，raw相对残差0.005653709235402098 > 0.001；solver/total作用8/9，budget_exhausted=false | 是迭代上限未达目标，不是独立MatMult额度耗尽；8步不能排除更多有限步能够有效求解 |
| H6场side记录 | 1项exact zero；5项非零各128步，原D残差约0.08550/0.02315/0.10982/0.25341/0.23442，均为INNER_APPROXIMATE_RETURN | 1%的side目标未达，是预条件质量风险；不是已经通过side严格门，也不是最终原方程误差 |
| 中间method selector事故 | candidate helper漏传modal_feedback_method，factor_setup前拒绝；已做一行生产修复与定向测试 | 工程错误已关闭，不再重做相同诊断 |
| 中间fixed-Q计数事故 | raw记录backsolves=0，与旧“所有Q必有两次回代”断言冲突；缺失败Q向量，具体零来源未持久化 | 已修正数学修正次数与实际回代次数的区别；只能凭该调用exact-zero证据跳过实际solve，不能回填旧根因 |
| 最新physical BAL_H场 `45a94a21…` | 两侧numeric/admission、固定物理反馈线性样本通过；modal第1次solve失败 | 不是p4因子失败，也不应继续称top cleanup故障 |
| 最新modal | rhs=0.09648882926540421；residual=0.0018492374693352754；raw relative=0.01916530113811127；reason=-3、8步、budget_exhausted=false | 独立目标1e-3未达；没有证据证明该输出不能作为有限近似PC，也没有证据保证外层可收敛 |
| 最新side/资源 | top另一side RHS 128步，原D residual=0.08801306313790089；tree峰46,405,410,816 B，最终cgroup历史峰43,664,695,296 B；wall3697.345224675 s | 有实际side弱收敛信号；资源低于72/80 GiB。本次约1.027 h是失败warm时长，不是成功或cold时长 |
| 全局结果 | 最新outer仅iteration0；失败modal RHS/iterate未保存；无最终五残差、E/H、R/T/A、体吸收 | 首个完整0.7 nm结果仍缺。W2本批未运行，不能宣称短波长鲁棒性 |

H6的0.00565与physical BAL_H的0.01917来自不同辅助算子/求解调用；不能仅比这两个数宣布物理反馈更差或更好。应在同一原方程、相同真实输入和总成本下判断。

## 2. 源码诊断：两个不同层次被混在了停止逻辑中

[`hybrid_fem_modal_block_ldu.py`](../../src/solvers/hybrid_fem_modal_block_ldu.py)中的 `_FixedH6ModalKrylovSystem` 把rtol=1e-3、max_it=8、solver/total MatMult=9/10设为类属性；实际内层是RIGHT GMRES、UNPRECONDITIONED norm、零初值，restart也为8。`_solve_once()`在独立残差计算后，只要status不为converged就抛RuntimeError。这个错误经PC退出到consumer并释放p4因子；它不是原全局Maxwell算子的线性失败证明。

写成一般符号，原系统及模态PC为：

```math
\mathcal A u=f,\qquad
S=C-L_bD_b^{-1}G_b-L_tD_t^{-1}G_t,\qquad
\widetilde S_B=C-L_bB_bG_b-L_tB_tG_t.
```

原全局A与f保持不变。内层求的是预条件器里的替代块，不是把真实Schur替换进原方程。H6或一次固定BAL_H是B的两种选择。判断层次如下：

| 层次 | 衡量什么 | 本轮处理 |
|---|---|---|
| 固定作用/数据 | P/PH、J/JH、A4、G/L、normal/phase、MPI、固定反馈线性与重复 | 保留原严格检查，不准状态污染或非线性作用伪装线性MatMult |
| 模态辅助求解 | eta_m=norm(g−S_tilde*m)/norm(g) | 1e-3仍为目标；允许有限预算后以明确状态返回可用近似PC，不能假称内层收敛 |
| 原side近似逆 | eta_s=norm(b_s−D_s*x_s)/norm(b_s) | 1e-2仍为目标；现有approximate-return原样记账，不冒充已达目标 |
| 原全局解/输出 | 原f与原分块分母下五真残差、恢复及物理量 | 全部通过才有正式结果；不受内层返回策略放宽影响 |

PETSc说明FGMRES可以使用非线性/内迭代PC，默认达到max_it对应DIVERGED_ITS；负reason不自动等于非有限或实现错误。[S1–S3] 这支持**有界近似PC**，不保证任何差PC都有效，也不允许在原A的MatMult内塞自适应求解。

当前side已经采用有限迭代近似返回，而modal仍坚持8步严格结束，是需要重新审查的策略不对称。过去这项严格门适合小案例资格，不应成为跨波长永远不变的数学定律。本轮先给原外层一个有界且可信的试验机会，而不是继续每次付setup后在第1/2次PC销毁。

## 3. A1：一次实现完整的W0.7有界模态策略

### 3.1 先增加合理内层工作量，不从8、16、32零初值各跑一场

只对注册W0.7 pilot增加一个显式opt-in策略，建议名 `task041_v12_bounded_inexact_modal`；采用instance参数，不能改变类属性以污染其他solver实例。W5/13.5/ordinary及其历史资格保持原样。统一一份解析后的policy对象透传public→worker→candidate helper→factory→solver，记录requested/actual；不再复制多套略有不同的断言。

```text
modal target rtol           = 1e-3 (unchanged)
modal GMRES max_it/restart  = 32 / 32
solver S_tilde action cap   = 34 per modal call
total action cap            = 35 including one independent final check
PC approximate-return eta  = <=0.1, only under the conditions below
primary feedback           = fixed-H6
backup feedback            = fixed_physical_balh_once, at most one switch per run
```

32是本轮有限工程预算，不是预计迭代数。KSP能提前收敛就提前结束；第8/16/32步仅保存已有monitor的标量，不能各自从零重跑。最终必须独立重算未缩放残差。新增向量是800维模态向量，不是完整FE向量；24个附加800维complex128向量裸payload约307200 B，实际GMRES工作区/复制另记，不能称其为RSS。不得仅改KSP max_it却仍保留旧9/10动作门、restart或registry拦截。

初始默认H6，是因为它单次便宜且已在5 nm闭合，并非根据跨场残差值排名。已健康运行且取得有效进展的physical BAL_H作业不为本报告重启；已结束的旧因子不能恢复。

### 3.2 有界不精确返回：不是把1e-3偷偷改成0.1

以下须同时满足，才可在32步耗尽后返回当前模态近似：只有PETSc运行时确认的DIVERGED_ITS（或正reason但独立残差尚未达目标）；MatMult/PC没有异常、非有限、breakdown、layout/identity或固定作用检查错误；输入未被修改；有可用当前iterate；独立未缩放eta_m有限且<=0.1。正常>=目标的情形保留raw_residual_pass=false、原负reason与次数；明确另记 `INNER_TARGET_NOT_MET_APPROX_RETURN`、`pc_usable=true`。eta<=0.1意味着相对于零初值RHS至少下降10倍，只是工程接纳线，不是最终误差保证。

eta_m>0.1、未执行独立终检、预算异常中断无可信iterate或任一真正错误，均不能返回成功/近似。零RHS必须走正确exact-zero分支，不能通过norm阈值把非零输入当零。**不得设置converged_maxits或把负reason改成正值以满足旧checker。** 外层仍RIGHT FGMRES且原A固定；内层状态在最终summary/service中与原问题资格分列。新策略不把原A4>1e-10、错误G/L或坏PC数据变成“允许不精确”。

34/35作用额度要以本机测试核对包含关系；不在Python MatMult回调预算已耗尽、MPI可能不同步时随意捕获任意异常再继续。可用近似返回发生在KSP正常返回后的集体一致决策点，不是吞掉PETSc callback错误。最后一次独立残差作用必须预留。

### 3.3 最小测试后直接实际运行

复用test350/test351和现有fixed-Q fixture：真实小复数非Hermitian问题覆盖“8步不够但32步达到目标”、正常迭代数耗尽且有限近似返回、eta>0.1拒绝、非有限/PC失败拒绝、zero/empty-owner、MPI一致终态；小型外层FGMRES最终仍须用原A验证正确解。再以实际candidate helper覆盖所有policy/selector透传，而不仅检查shell argv。fixed-Q继续分清数学修正次数与实际非零回代次数。

上述属于本次必要变化测试，不重跑13.5 nm/W5完整场、matched-cell oracle、symbolic桥证明或全部历史资格。scalar监控新增字段缺省兼容旧结果，不为一项计数字段再启动真实FE。

## 4. A2：同一因子生命周期里观察真实外层，有限恢复而非无限续算

### 4.1 一场主作业与一次条件备选

复用已验证W0.7 producer；保持0.7 nm、10×5 nm、p6/h0.70/M400/MPI8、接口2/22、matched L20/N29、W材料、PORD、compact transfer与identity sharing。普通P4 target5e-13/最多2次修正、原A4物理及增广检查1e-10不变；fixed physical action仍每Q固定一次数学精化，保持线性。禁止逐列完整Schur或全局p6直接分解。

两侧numeric完成后连续执行fixed反馈、原外层、恢复与输出。外层max_it不提高。首先取得至多8步的原方程轨迹；能提前达到全部原门则直接收尾。第1/4/8步、随后每个restart边界复用或补充一次完整原残差，记录额外A作用成本；不要每个side/modal步都输出全场。

若modal在预算内不可用，或原外层/side工作显示持续低效，允许**最多一次**切换到已实现的fixed physical BAL_H（同样32步/同样PC返回合同）。先在当前实际modal RHS上做必要小范围对照，按全局进展与加权成本选择，不只比不同S_tilde的残差。切换仅在完整modal调用/outer安全边界，不能在一次内层GMRES中途改变MatMult。原side p4因子、QEP和所有可复用数据保留；新包装器销毁不得销毁借用因子。

优先由FGMRES后续PC调用使用新策略。若现有接口只能安全重启outer，则保存当前可信x，显式设非零初值，继续原f，保持累计wall/迭代/工作账，不能把重启后的相对分母偷偷换成小残差来报原问题通过。无需跨进程保存p4，也不要求跨PC切换保留整套Arnoldi基。

### 4.2 side 128步不达标必须被看见

目前非零side多次128步仅到2.3%–25.3%，不可以仅修改modal return然后隐藏这些成本。记录每次side的原目标、实际残差、KSP reason、步数、P4精化和耗时；原approximate-return合同不放宽，最终五残差仍独立裁决。

若连续真实side在restart32后无明显下降，且原外层没有可用进展，允许**一次定向数值稳定性对照**：选择一条已捕获的困难side RHS，借用同一因子，将该side GMRES改为restart64、max_it仍128，并使用本机支持的modified Gram-Schmidt或条件再正交化之一，不能同时扫多种组合。[S4] 对比原D真实残差、同口径时间及整个PC成本；更好才固定到后续side调用。不新增p4因子，不改其精化门，不扫描ILU。

增加side Arnoldi基可能增加内存，须按新增V/Z向量实际全局行数、ghost和两侧同时驻留计量，在80 GiB及节点余量内才做。必要时只为被测side分配；释放旧基后再切换，不重叠两套KSP向量。若128步后仍停滞，不能再把max_it扩大到数千掩盖预条件失效。

### 4.3 有进展就完成，没有进展就给真正的数值负结果

8步、一个restart窗口是观察点而非自动退出点。原残差持续下降且资源安全则继续到原门；超过48 h目标本身不自动强杀。若完成一次备选及必要side对照后，连续两个8步观察窗的最佳全局真残差各改善不足10%、关键分块也停滞，或出现明确数值增长/非有限，则保存当前原场/残差与失败小输入，作为收敛/成本负结果收口，不无界耗时。10%是预定工程停滞触发线，不是收敛定理，单次尖峰不得误判。

本轮不得再交“又在第1/2次modal solve按8步退出、未保存RHS”作为同样的结论。一次健康新作业应先完成有限真实外层再判断；只能因真正的新安全/数值错误提前结束，并保留足够证据。主目标仍为**首个完整0.7 nm场**，8步记录不等于完成任务。

## 5. 最小失败证据与bug处理：不再开发一整套诊断工具

本base的两次modal失败均未持久化g/iterate，因此不能离线补算它们；不要求“用旧失败向量定位完再开机”形成循环。下一次在solver的正常返回边界保存首个目标未达的modal RHS、当前m、原始residual及标量历史，另保留至多一个成功对照。M400对应800个复数，每组三向量裸数据仅38400 B；由modal owner写ignored NPZ及小hash索引，不保存全部FE矩阵/所有Krylov向量。文件中写明method、actual policy、solve/outer编号和向量布局；若有异常无法信任iterate，明确缺失原因。

side仅捕获一条必要困难输入的分布式owned向量及布局，不全局gather大场。保存已有原解/恢复包可用于后处理重试，但旧factor不在packet中，不声称跨进程免构造。

freeze首次异常stage/type/reason，cleanup_stage另记，避免把modal错误覆盖为top_construction_cleanup。数值max-it、接口bug、资源拒绝分列；允许沿已有服务状态最薄适配，旧raw不重写。非关键文档/计数问题以派生说明收口，不跑一场PDE仅求exit0。

固定一次native activation、全部数学线程含BLIS=1和冻结CPU map的准备函数。新增参数必须同时走真实helper/factory测试；精确零的两层分支以实际fixed action测试覆盖。普通路径、fixture、schema、empty-owner和selector问题：保存attempt，最小修复，受影响测试通过后继续，不结束整轮任务。相同错误两次出现后先最小fixture解决，不第三次原样重建。已关闭问题不因新文档重新认证。最多一场主warm；确需修复新实现错误后的一次正式重试必须明确root cause及受影响证据，不能每个参数值各新启一场。

## 6. 安全、物理验收与48 h成本

保留V11：hard=85,899,345,920 B、warning=77,309,411,328 B、政策W=8,589,934,592 B，node0 floor=412,316,860,416 B。有效cap取case与实际node/父cgroup限制中更严者；冻结启动总cap，运行中只按新增需求核余量，不能重复扣本job已占内存。最新版已完成numeric峰约46.4 GB是本次前段实测，不保证新增Krylov/输出的完整峰。one-cell、side p4与modal C因子分别计量；INFOG全局量不再跨rank求和。

swap继续只观测，不单独拒绝、停止或判最终失败；RSS下降伴随换出不能称算法省内存。真实OOM、节点余量失守、磁盘/硬件错误、MPI/ABI不一致、非有限或输入污染必须停受影响作业。一次一个heavy，默认socket0/node0及已核物理核map，保留保护stash、不干扰Task039/042等邻任务；不为了2 TB利用率而擅自启用未资格node1或改BIOS。

正式输出门不变：reported/global/bottom/top/modal五项真实残差各<=5e-9；traction和projection<=1e-8；external-q<=1e-10；能量闭合及A−A_volume各<=1e-5；完整复E/H、全部外部key、复幅/功率、法向通量与官方输出身份。原更严要求从严。近似PC可用不等于输出可用，只有最终合格场产生official R/T/A。W5延期项不影响本轮pilot开展，但方法总资格保留限定。

```math
T_{\rm cold}=T_{\rm QEP}+T_{\rm setup}+T_{\rm outer,all\ work}
+T_{\rm recovery/check/cleanup},\qquad 48\,h=172800\,s.
```

累计包括setup重试、inner continuation/备选、side对照、独立残差作用；实际fresh、warm、跨历史组合的cold估计分别报告。失败约1.027 h不是成功ETA。QEP不重叠时producer/consumer峰取最大，不相加；全部费用另列且不归零。

观察到side128步饱和后，不再用5 nm的16.64 h乘简单比例承诺0.7 nm性能。给出每原外层步的实际成本、所有side步和p4回代/精化、两类反馈次数，以及到最终门还剩多少数量级的残差下降。只能将稳定阶段的外推标predicted/区间，停滞时ETA为未知而不是盲线性外推。

## 7. 从首场pilot推进到目标，而非永久停留小模型

本轮重负载顺序：必要policy/实际调用链测试 → **同生命周期0.7 nm实算及有限恢复** → 五门/物理/输出 → 准备最小相邻资格与目标资源表。首场成功后，按既有阶梯做一个网格变化点和一个模式变化点：p6/h0.70/M400 → p6/h0.525/M400 → 条件p6/h0.525/M600，每个独立.dat。actual N和L/N重新派生、改变横截面/模式身份则生成对应QEP；不能把guard直接去掉、盲复用N29。

继续沿V10/V11相邻精度门：R/T/A/A_volume绝对变化<=1e-4、选定复E/H和显著复衍射幅值相对变化<=1e-3；原守恒门保留。相邻稳定只是工程资格，不是严格误差上界。未收敛pilot可以作为原离散方程结果，但不标accuracy-qualified。

目标50×25 nm、100 nm传播段需独立列：真实FE/trace拓扑、W外部通道、内部M、p4 factor填充、one-cell构造、QEP左右基/shift因子、模态C、DtN与各rank复制及恢复并存。不得把pilot峰乘125当统一预测，external keys也不等于内部M。根据两个实测尺度/对象模型选择一个可支付的放大点，而非直接开最大模型。2 TB是整机预算不是当前node0预算；保持系统余量的前提下才评估目标容量。当前架构的全局p4因子仍可能在目标尺度成为瓶颈，必须报告而非假定p4可无限扩展。

W2继续低优先级：不为绕过本轮W0.7数值问题而新开另一场heavy；只有不延误0.7、已有资源问题需要独立尺度校准时，才沿V11现成阶段桥补真实W2容量/求解。W5弱显著级、GPU、新PC大扫描、node1维修、本轮无关NN和普通默认切换均不做。

## 8. 提交与完成要求

只在原Task041分支普通commit/push：一次policy/selector/小测试提交、必要数值修复提交、运行证据与response提交，不amend/force-push、不merge master、不覆盖dirty/stash。开始先只读核对健康作业；已有授权健康运行不因review更新而被杀。本次ChatGPT只交文档，不宣称已执行工作站任务。

产出`response_v14.md`、一个中心`outcomes/w0p7_inexact_pc_progress_v12.md`和必要小record；同步summary/test_summary/development_progress/model_registry。source/runtime、unit/InvocationID、producer身份、requested/actual PC策略、每层target/pass/usable、全局残差轨迹、已测资源和时间完整绑定。短波长新物理结果尚未取得时直接写not_run/failed，不以路线测试通过替代。

阶段启动、因果明确的阻塞和终态及时推轻量状态；长阶段沿既有状态至少每小时保存一次，避免只见新代码不见运行。不得为了推文档改变正在运行的数学代码；运行前后source与artifact绑定分开。真正完成应有首个完整W0.7原方程/物理结果，并尽可能继续必要资格点；若仍失败，应有超出原8步的真实外层轨迹、有限恢复的对照、明确PC/side/资源原因和最小缺失物理信息，而不是又一份同样的起步失败或无向量审计。

## 9. 来源与校验边界

- [R1 固定Response V13](https://github.com/Rookie1234567/MyFEniCS/blob/623ded3ad75214f2251c7cee7779fffe56524e31/docs/task041_mpi1_shortwave_hybrid_capacity/response_v13.md)：已执行事故、残差、stage、资源和原始artifact索引。本次未把工作站ignored文件当作已直接逐字读取。
- [R2 固定summary](https://github.com/Rookie1234567/MyFEniCS/blob/623ded3ad75214f2251c7cee7779fffe56524e31/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)。
- [R3 当前modal源码](https://github.com/Rookie1234567/MyFEniCS/blob/623ded3ad75214f2251c7cee7779fffe56524e31/src/solvers/hybrid_fem_modal_block_ldu.py)：固定8步、RIGHT/UNPRECONDITIONED、raw final check与status拒绝路径。
- [S1 PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：允许非线性/内迭代PC，不保证任意PC的收敛。
- [S2 PETSc 3.19.6 KSPConvergedDefault](https://web.cels.anl.gov/projects/petsc/vault/petsc-3.19.6/docs/manualpages/KSP/KSPConvergedDefault.html)：max-it与原默认残差判定。
- [S3 PETSc KSP_DIVERGED_ITS](https://petsc.org/release/manualpages/KSP/KSP_DIVERGED_ITS/)：迭代数达到上限但尚未满足收敛准则，不等于矩阵非有限。
- [S4 PETSc GMRES](https://petsc.org/release/manualpages/KSP/KSPGMRES/)：restart、正交化/再正交化。以本机PETSc版本可用API验证，不升级ABI。

公开机制于2026-10-10核对；所有新参数和10%停滞/PC接纳线均为本review的工程试验政策，不是已有实测或理论精度界。输出文档检查围栏、表格、引用和字节；GitHub网页视觉渲染不可访问时如实标未核，不虚构通过或因此重跑PDE。
