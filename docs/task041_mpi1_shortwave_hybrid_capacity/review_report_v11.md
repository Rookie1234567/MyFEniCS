# Task041 Review V11：解除继承的50 GiB容量瓶颈，交付0.7 nm实算并闭合5 nm单通道误差

## 0. 审阅决定与身份

**本轮直接阻塞已定位：0.7 nm缩减pilot多次在p4构造阶段触及从旧小案例继承的53,221,163,008 B上限，最近一场甚至在top numeric之前仅因预算筛查超292,157,069 B而退出。它不是2 TB硬件容量已耗尽，不是Schur逐列构建又变慢，也不是已测的0.7 nm不收敛。继续为跨过这条约50 GiB人为边界反复重建，不符合当前“先取得真实短波长结果”的目标。**

**执行决定：仅对已注册W0.7 reduced pilot，明确提高受控作业上限到80 GiB、warning到72 GiB；保留384 GiB node0 floor、全树监督、分阶段预算与原数值门。沿最新PORD、compact transfer、identity-sharing版本直接完成一次pilot，不再把释放Bi或新缓存作为启动前置。另行关闭W5唯一显著衍射级配对超限，优先复用已存解作有界原方程修正；真实W2继续阶段容量和安全条件下完整求解。**

```text
repository                = Rookie1234567/MyFEniCS
branch                    = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date               = 2026-10-09, Asia/Singapore
reviewed_base_SHA         = ff59891ebf8d596c172eb266afd9f44a27fe2ed7
base_latest_commit        = docs: record W0.7 PORD warm terminal audit
latest_runtime_source     = 6ffa7768329b637d96a9dccc2eb5aa00d510bb28
latest_runtime_invocation = 12180bdec9824ec49d60b26aefe3655b
previous_review           = review_report_v10.md (V10-r2)
reviewed_response         = response_v12.md
response_required         = response_v13.md
batch                     = task041_v11_deliver_shortwave_fields
primary_solver            = fixed-H6 modal GMRES + cell-condensed p4/BAL_H sides
swap_policy               = task041_v8_swap_observe_continue
execution                 = MPI8 x 1, frozen socket0/node0 map
master_merge              = NOT_APPROVED
```

V10已经有Response V12回应，本次新建V11保留历史。本次ChatGPT仅提交review，不宣称执行了停机、代码修复或计算。用户本轮要求实质推进，授权本报告范围内必要实现、测试及连续计算，不要求用户重复批准同一个小步骤；主控—执行内部审核仍遵守仓库规则。

**明确覆盖**V10对本pilot“不得提高53.22 GB case cap”的限制，以及需要先完成所有存储微优化才进入下一次pilot的解释。只放宽这一项资源预算，不放宽数学精度，不取消安全保护，不改变W5/W2既有cap，不启用node1。旧task的MPI1/exact-only/禁跑0.7与swap硬门继续按V8–V10的明确覆盖处理。健康运行中的任务不为新review重启或热改源码。

最终目标仍为0.7 nm、50×25 nm目标单胞、约2 TB整机物理内存、有系统余量、48 h从QEP到恢复核验的完整计算。当前Hybrid仅适用满足内部模态传播假设的结构，不代表任意非可分三维Full3D已通过。

## 1. 已读证据与当前裁决

依据base下的[Response V12](response_v12.md)、[summary](outcomes/summary.md)、[V10进度](outcomes/shortwave_measured_progress_v10.md)、[V9 W5 record](outcomes/records/task041_v9_fixed_h6_public_5nm.json)，以及原task、V10-r2、适用AGENTS、仓库工作原则。任务目录未列其他补充任务书；旧task和V10的同blob内容复用已核读版本。

| 对象 | 最新事实 | 审阅裁决 |
|---|---|---|
| W5 fixed-H6 | 16.643 h，49 outer、7732侧区内部步、完整Schur列0；旧逐列场56.146 h、30296内部步 | 保留实测提速和自身五残差/物理通过；非隔离比较不宣称单一改动的严格因果加速 |
| W5新增离线比较 | R/T/A/A_volume、E/H、canonical和normal flux通过；600 keys一致；26显著级中1项超门 | **完整同离散等价性尚未通过**，不能沿用“全部衍射对照已通过”的泛化结论 |
| W0.7 producer | 已有完成的可复用packet，后续各warm场QEP=0 | 不因consumer或报告错误重新求模；现场核验原生命周期与分片 |
| W0.7 latest PORD | one-cell完成并销毁；bottom p4 numeric完成；top symbolic完成，numeric未调用 | 没有进入fixed-H6反馈、outer或物理输出；不是迭代发散 |
| PORD top预算 | fresh B=38,544,203,776 B；INFOG(17)一份9,647,000,000 B；W=5,322,116,301 B | 筛查合计53,513,320,077 B，比旧cap高292,157,069 B；这是预测拒绝，不是实测峰 |
| PORD实际资源/终态 | tree峰40,494,215,168 B，job cgroup峰37,709,873,152 B；wall3241.567376339 s；public rc3，finalizer 8/10 | 原raw为IMPLEMENTATION_FAILURE/service_boundary_failure，controlled_stop=false；保留raw，派生标注资源预算拒绝 |
| W2 | 尚无本轮新后端完整结果；既有TOAR packet可供验证复用 | 缺当前后端阶段数据，不将旧约650 GB峰当新后端结论，也不无限停在unknown |

Response V12明确列出的六场warm Invocation，service wall合计13,784.821245757 s，约3.829 h；不含其他开发、测试或producer费用。它们主要重复构造后退出，并非完整PDE已经运行了一周。先前确有一次tree RSS达到53,541,888,000 B触发旧cap；后面的几次是numeric前筛查失败。这两类停止不可混称OOM或数值失败。

## 2. 为什么一直没出场：三个不同问题必须分开

### 2.1 资源范围没有随任务目标重新设定

当前代码 `_task041_w0p7_stage_budget_projection()` 使用：

```math
B_{\rm fresh}+10^6\,\mathrm{INFOG}(17)+(B_{\rm cap}-B_{\rm warning})\le B_{\rm cap}.
```

B已经含bottom活因子、top pending对象和其他驻留；不能再加bottom INFOG(19)。INFOG(17)是全rank内存估计总和，只取一份，不能乘MPI8；不是RSS严格上界。post-symbolic已占量与INFOG(17)是否有重叠尚未被分离，不能臆测扣掉。W是政策缓冲，不是统计误差上界。

这个筛查本身在执行已定合同，并没有仅因292 MB超限而算错。**不合理的是在目标预算约2 TB时，仍把第一场短波长pilot必须压在49.566 GiB当不可调整的研究目标。前版review过于坚持继承cap，本版承担并纠正该决策。** 不通过放松残差、少报内存或无视预算来解决，而是先明确调整本case授权预算，再执行同一筛查。

### 2.2 新代码与审计已经有收益，但不能再变成无限前置研究

现已完成symbolic/numeric薄桥、PORD选项、compact方向表示、单位矩阵只读共享和numeric前清理。保留这些代码及其测试。PORD与AMD来自不同Invocation，不能将估计差直接称排序的净RSS收益。

Bi-only释放的全rank唯一buffer量未知；其校验/别名合同仍依赖Bi。暂不为它增添新接口或再重建一场测能否省292 MB。Di、xiB、p6 Schur及恢复数据更不能删除。取得第一场之后，再以实测最大对象选择存储优化。

### 2.3 W5存在一个独立的弱显著级精度缺口

该比较失败不否定16.64 h已完成解，也不能用R+T+A或整体E/H通过将它抹去。它需要单独的数值定位/修正，不应阻止一个不同波长pilot进行有明确资格边界的原方程实测；在修复前不批准通用生产或完整同离散等价性。

## 3. P0：资源合同一次贯通，随后直接出pilot

### 3.1 仅W0.7已注册reduced pilot的新预算

| 字段 | 本轮值 |
|---|---:|
| hard cap | **80 GiB = 85,899,345,920 B** |
| warning | **72 GiB = 77,309,411,328 B** |
| numeric政策W | **8 GiB = 8,589,934,592 B** |
| node0 floor | **384 GiB = 412,316,860,416 B，不变** |
| swap | 只观测，不单项拒绝/停止 |
| 48 h | 冷流程目标，不新增自动强杀线 |

按最近PORD样本重新代入，筛查为56,781,138,368 B，比新cap低29,118,207,552 B；这是新政策下的**历史数据演算**，不是未来准入或RSS保证。即使按前一AMD场的B与INFOG(17)，也得到73,100,889,792 B，说明80 GiB不是只把旧cap抬高292 MB、再次贴线运行。仍选最新PORD，不另做排序扫描。

启动实际有效cap须不高于新case上限、node0可支付量及真实专属/父cgroup限制；留住上述floor。启动时冻结总cap，运行中核当前余量与**新增**需求，不重复扣本job已占内存。真实OOM、RSS越界、node0 floor失守、硬件错误和磁盘不足仍停止。不得把2 TB当作单节点node0可用内存，更不得改动父级或邻任务限制以取得空间。

### 3.2 不制造新的packet封套循环

按现有单`.dat`/profile/public入口修改本pilot的execution资源字段和对应注册值，或使用已有显式资源policy机制；只选择一条现成实现，不并行维护两套入口。新增policy建议命名 `task041_v11_w0p7_pilot_80gib`，普通默认、W5、W2和旧artifact不变。

只改变资源字段时，input/resolved哈希可以不同，原数值定义必须不变。授权已有validator/binder进行**窄范围资源差异绑定**：逐字段核对几何、W材料、波长、p/h、真实mesh、M、Floquet/DtN、传播/traction、模式排序、ABI/MPI及分片哈希；资源cap/warning、review标识与run_id差异单列。保留producer原source/input/resolved哈希，不伪造与consumer相同，不因80 GiB资源更新重新求QEP。存在其他数学差异则不能按此例外复用。

把有效cap/warning/W贯通dat解析、service、supervisor、consumer阶段筛查、cgroup配置及finalizer。不得在某一层仍按旧53.22 GB取min，导致新政策实际失效。先以最近top样本作fixture：旧政策拒绝、新政策通过；真实超80 GiB、节点不足、未知/非有限关键量仍拒绝；旧case策略不变。再做一次真实公共命令validate-only/worker参数链检查，不用重型FE验证字段透传。

预期资源拒绝的新运行应记录明确stage/resource_budget_blocked，而非笼统ImplementationFailure；可复用现有停止分类做最薄适配，旧raw不重写。分类修复若暂时不影响安全判断或实际执行，不另起一场PDE只为获得exit0。

## 4. P1：一次warm构造跨到outer，再得到真实0.7 nm场

冻结当前注册几何：10×5 nm、z=-2..26 nm、接口2/22 nm、p6/h0.70、M400、MPI8、complex128、W来源派生材料；matched_uniform_axial_cell使用L20/N29及h=20/29 nm。fixed-H6、p4内部target5e-13/最多2次精化、原A4验收1e-10保持。保留最新PORD及其真实ICNTL读回；不启用全列Schur或p6直接因子。

先核对现场运行：旧PORD Invocation已在已推送记录中结束，不能假装其bottom因子仍在内存。新的healthy匹配作业则继续，不为换review重启；没有时启动本轮一场warm consumer。复用已有W0.7 producer（记录source `2708214386d38bd69f73e6b196c8ed843bb53d81`，manifest `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2`，identity `73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6`），实际文件/生命周期仍须验证。QEP保留不等于p4/Krylov可恢复。

执行：packet读取 → 原one-cell阶段 → bottom/top symbolic与numeric分级 → 双侧驻留检查 → 固定反馈检查 → 原Hybrid FGMRES → 五真实残差 → 最小恢复包 → release-before-recovery → E/H、R/T/A、体吸收、全部衍射 → finalizer。不要在top factor ready时主动结束作业、交一张表后再重建。下一阶段新增缓冲/Krylov/输出仍须盘点，80 GiB不意味着后续自动可支付。

前8步和一个restart窗口是同一作业内的观察点，不是强制终止点。有实质原残差下降、资源安全即继续；没有依据不能因日志安静重启。若出现真实数值错误，保存最小失败输入/输出与原算子残差；有限修复后只重做受影响阶段。必要时按既有V9授权使用一次固定物理BAL_H模态反馈备选，但不能仅因未知性能先切换；不提高max_it掩盖停滞。

已完成matched-h serial/MPI2与薄桥证明直接复用。资源policy变更只测受影响合同，不重新开展正入射oracle、材料研究、13.5 nm回归或全W5测试。后处理/schema失败优先从封存恢复包修复；不自动重算QEP/线性解。

首场必须报告真实的outer/inner轨迹、五残差、selected复E/H、R/T/A/A_volume、显著和全部通道、阶段RSS/时间、各因子统计及最大驻留对象。没有参考时标“该离散原方程/物理通过”，不得称网格或50×25 nm目标合格。

## 5. P2：关闭W5单通道差异，不盲目再跑16小时

### 5.1 明确失败量及当前假设

唯一失败key为`["bottom",-15,0,"s"]`：复幅相对差1.0880143757234042e-6、功率相对差2.074050200051092e-6，门均1e-6。复幅绝对差2.4738743521870602e-11，功率绝对差4.6498267516462735e-14；参考功率2.2419065611486787e-8超过显著floor1e-8。不得提高floor、删级、改分母或做phase fit来获得PASS。

整体E/H约5.7e-10、bottom canonical约1.7e-8、当前bottom原残差约4.87e-9，说明可优先检验较弱输出对剩余代数误差的敏感性；**这是可检验假设，不是已经查明的roundoff结论**。右侧explicit-Schur也是candidate，不是exact-side真值。先用原始复幅、归一化、功率系数和同一投影定义复算该行；复用现有exact-side工件交叉核对（可读时），不得只看报表差值。

### 5.2 首选原方程残差修正

若原始后处理计算正确，优先读取fixed-H6已保存的全解/active traces/modal coefficients或足够的恢复packet，在合法同布局/已证明canonical映射下重建x0。不能把只有selected planes的输出当成全解，不能直接按新mesh数组编号套旧向量。缺什么字段准确列出，不新造通用checkpoint框架。

```math
r_0=f-\mathcal A x_0,\qquad \mathcal A\delta x=r_0,\qquad x_1=x_0+\delta x.
```

复用原QEP并在一个独立polish作业内重建一次所需PC/factor，随后同一生命周期最多两次残差修正。解向量不是因子checkpoint，重建成本必须明报。可用非零初值继续求原问题，或显式解上式；PETSc默认会清零初值，必须核验实际KSP设置，不只传CLI。[S1]

若缩放小残差RHS以避免近零判断，要显式记录比例并还原delta；最后仍按**原f及原分块分母**验收，不用修正方程的相对残差替代。首个polish目标为原五残差各<=5e-10；该级仍未关闭通道且证据支持代数误差时，同一因子内最多再到5e-11。目标收紧不保证输出一定通过，最终仍复核600 keys及全部26显著级、原E/H/RTA/canonical/flux门。

不要求把小修正方程按新RHS又盲目求到1e-9相对精度；以组合解的原残差和预先设定的停止目标控制工作。若达到更严原残差后仍不一致，区分reference误差、提取/恢复和真实实现问题，不能继续无界加精度。不可恢复x0时，才允许一次有理由的W5 fresh tighter run；不重跑旧1920列方法。

旧16.64 h结果保留自身PASS和单通道comparison FAIL。polish成功后另列原run、重建、修正、恢复的全部新增时间；不能只报polish秒数冒充一次完整散射的耗时。P1与P2重负载串行；W5这一项不再成为不同波长pilot的循环前置，但完整方法等价性/生产资格必须等它闭合。

## 6. P3：W2用现成阶段桥取得实测，不重新研究8×8接口

W2仍为原50×25 nm、2 nm、p6/h1.5/M1200/MPI8、cell_condensed/fixed-H6、原材料和独立TOAR packet；W0.7 matched长度不静默迁入W2。保持原W2规划/硬cap及384 GiB node0 floor，不借用本pilot的80 GiB或旧650 GB作为新预测。

symbolic/numeric桥已在本机小矩阵及W0.7真实矩阵上实际使用，接受其已绑定ABI/实现证据，不从头再证明接口存在。W2只扩展已有注册scope和实际N/NNZ/P的源计数模型，不能把W0.7固定64966行及硬编码NNZ塞到W2。预先检查生产调用链能进入W2分级；纯guard修复用小fixture。

在可预算范围依次形成真实mesh/constraints、one-cell/侧区矩阵，取得当前矩阵symbolic统计；numeric前按fresh B、该因子的INFOG(17)、已知调用方新增workspace与缓冲判断。不重复加已活因子，不将全局INFOG求和两次，不拿一次8×8测试的RSS作大型预测。估计有不确定性仍保留stage watchdog及实际floor，不以“没有严格数学上界”拒绝任何可约束的装配/分析阶段。

每个阶段给出实际rows/NNZ、source矩阵字节、MUMPS estimates、已完成numeric的allocated bytes、同时间树/cgroup/节点量和下一缺口。两侧可支付后同进程进入原方程求解，避免退出重建。仍超预算则保存实际最大对象/差额，选一个有量化价值的生命周期或分布式存储修复，不再只交`new_peak=unknown`。

当前只用node0，不能声称已使用全部2 TB容量；其可用量不足不等于整机2 TB no-go。本轮不恢复CPU1/BIOS排障、不使用未资格node1、不拆DIMM，不为了W2启动误停其他任务。

## 7. 继续贴近0.7 nm、2 TB、48 h的判据

这次提高pilot cap仅是解除不适当的早期实验限制，**不是最终算法内存优化，也不是证明大单胞可行**。先得到一个可信场和全过程分项，再优化实测最大的时间/驻留项；不继续凭可能节省的几百MB驱动整个项目。

```math
T_{\rm cold}=T_{\rm producer}+T_{\rm consumer},\qquad
T_{\rm consumer}=T_{\rm setup}+T_{\rm outer,inclusive}+T_{\rm recovery/check/cleanup}.
```

QEP与consumer严格不重叠时workflow峰取两者最大，不相加。已有packet下的warm时间单列；把不同历史run组合得到的cold成本标为组合观测/派生，不能称一次fresh实测。48 h=172800 s；开发/失败成本另报且不隐藏。继续swap observe-only，驻留下降伴随换出增加不算算法省内存，也不以swap扩充2 TB预算。

本轮不撤销已成功的无逐列路线：目标仍是减少昂贵侧区总工作，再降低单次成本。记录全部side apply、内部步、p4回代/精化、H6/C作用及non-overlapping wall，不能只报outer步数或某个kernel倍率。P1没有新数值瓶颈时先完成；额外route-plan/leading-PH/Bi优化不得成为P1–P3共同前置。

pilot通过后，才按当前注册能力与预算做相邻h/M：p6/h0.70/M400 → p6/h0.525/M400 → 条件p6/h0.525/M600。每个独立dat，实际轴向N与L/N重新派生，不能复用N29；改变横截面网格或选模身份时生成对应QEP，不能沿用不兼容packet。比较沿V10工程门，RTA/体吸收绝对变化<=1e-4、selected复E/H及显著复幅相对变化<=1e-3，原每场守恒<=1e-5；相邻稳定不等于严格误差界。

目标50×25 nm的通道、M、FE/trace、one-cell、p4因子、模式基和DtN耦合均按实际生成器逐对象预算。不按pilot RSS乘125便宣布峰值。尤其不能将32,056个external keys当内部M，或把显式trace×channel存储忽略。目标预算采用min(实际MemTotal,2,000,000,000,000 B)减真实系统余量，并遵守更严节点/父级限制；目标容量和48 h分别裁决。

本轮核心交付是P1真实0.7场、P2弱显著级问题的关闭或明确根因、P3真实W2阶段数据并在安全时完整求解。没有这些时，不能只凭注册测试宣称完成。更大规模若确实尚不可支付，交缺哪一个对象、多少bytes/时间、何种变换可能消除它，而不是泛称blocked。

## 8. 执行与停止收束

执行顺序：现场只读快照 → 一次资源policy/实际入口定向检查 → **P1完整pilot** → P2有界W5修正与P3真实W2（准备工作可穿插、heavy串行）→ 条件相邻精度。已健康运行的授权任务优先自然完成。普通metadata/schema、fixture、CLI、empty-owner、编译脚手架错误：留attempt、局部修复、受影响测试通过后继续，不整轮交回。相同错误两次出现必须用最小fixture解决，不第三次原样支付大型setup。

原生activation、MPI8 complex128/IntType、BLAS含BLIS的单线程、词法解释器、CPU map和source身份由同一现有准备函数产生。不要每次手写新的runner再漏`BLIS_NUM_THREADS`、路径或变量。已有public执行包重用字段结构，不创建更多按小时命名的编排工具；新runroot仅用于新的真实attempt。

新数学错误、缺失物理输入、nonfinite、原残差或物理门未通过必须修复再继续；保留精确失败向量/通道，不通过降低精度处理。容量/节点/磁盘/硬件真实限制仍受控停受影响作业；healthy慢运行超过目标只报告，不自动归零重来。已有解和packet先保全，不删除负结果。

本轮修复次数不是无界计算授权：先一场P1，修复明确新缺陷后只做一次受影响formal重试；另一个独立问题可以继续局部修复/其他工作，不能不停原样dispatch。W5一次重建后的有界polish（最多两次修正）和W2一次连续阶段构造优先，不额外重跑13.5 nm或旧W5基线。若旧cap是唯一阻塞，不再提出另一轮微内存研究替代执行本review的新预算。

新增`response_v13.md`及一个中心`outcomes/shortwave_delivery_v11.md`，必要轻量record含旧/新resource policy、数值源、stage、实际量、缺口和artifact hash；原大文件留results。更新summary、test_summary、development_progress及model_registry。首次与每个阶段关键变化及时推送当前runroot、运行SHA、unit/InvocationID、phase、迭代/残差/计数、wall、RSS/cgroup/node0/swap；长阶段沿已有状态至少每小时更新。不要只提交代码、不提交运行状态。

commit按最小policy/接线、必要数值修复、运行证据分别普通提交。同一Task分支、不amend/force-push、不覆盖保护stash、不改master；最终待review，master_merge=NOT_APPROVED。

## 9. 来源与审阅边界

固定基准为本报告§0的SHA。最新终态和W5失败行均来自Response V12及其hash-bound原始索引；没有把工作站ignored文件当作在本次已逐字读取。代码重点核对`benchmarks/task041_exact_side_workflow.py`的stage projection/cleanup和最新PORD提交；规则与V10-r2同blob复核。数字演算不代替fresh资源采样。

- [R1 固定Response V12](https://github.com/Rookie1234567/MyFEniCS/blob/ff59891ebf8d596c172eb266afd9f44a27fe2ed7/docs/task041_mpi1_shortwave_hybrid_capacity/response_v12.md)
- [R2 固定summary](https://github.com/Rookie1234567/MyFEniCS/blob/ff59891ebf8d596c172eb266afd9f44a27fe2ed7/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)
- [R3 阶段预算代码](https://github.com/Rookie1234567/MyFEniCS/blob/ff59891ebf8d596c172eb266afd9f44a27fe2ed7/benchmarks/task041_exact_side_workflow.py)
- [S1 PETSc非零初值](https://petsc.org/release/manualpages/KSP/KSPSetInitialGuessNonzero/)：默认零初值，实际设置需核验。
- [S2 PETSc MUMPS接口](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)：排序与工作区控制，版本以本机3.19.6/5.6.2证据为准，不升级环境。
- [S3 PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：允许非线性PC，原方程和最终残差不随PC近似被替换。

S1–S3于2026-10-09核对公开机制；MUMPS具体INFOG语义采用本机5.6.2已封存手册审计，不把新网页版本当本机。Markdown围栏、表格和字节一致性执行静态核验；GitHub网页若无法视觉验证如实标未核，不因此触发PDE重算。
