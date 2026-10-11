# Review V71：用有界重启与粗层反馈对照，停止原组合的无效续跑

## 0. 裁决、目标与唯一身份

**接受V72的实际执行、完整诊断候选、资源和负结果证据；固定38块RAS＋p2粗层、restart32的求解能力判为FAIL，不是仍未运行，也不是普通bug阻塞。批准V73_RESTART_AND_COARSE_FEEDBACK：复用全部健康准备，只增加一个较长Krylov记忆对照，必要时再用同一记忆长度检验两侧粗平衡。最多两项预登记完整求解，不扫描参数、不先重建波动粗空间。**

本轮消除的blocker是：第32步之后几乎停滞，但尚未区分短重启丢失搜索信息、粗/局部修正的非正规耦合，以及当前局部块/粗空间本身不足。诊断与实际求解同批完成，不把一份分账或新测试作为整轮交付。失败空间的连续准确性、原尺寸容量及48小时资格均不升级。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-11 Asia/Singapore
reviewed_HEAD          = 606965c328ec8dbf0ca682f5f5ddb1863781f22a
latest_commit_UTC      = 2026-10-11T06:52:05Z
latest_commit_local    = 2026-10-11 14:52:05 +08:00
reviewed_response      = response_v72.md
previous_review        = review_report_v70.md
previous_review_commit = 07d3f3d2aa6177cc015ac1a279900f7fbb14f4c7
previous_review_blob   = 5acdfa2e769001b696ef7973e119aef8b6bbd5ed
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V73_RESTART_AND_COARSE_FEEDBACK
required_response      = response_v73.md
ordinary_default       = UNCHANGED
NN_training_PC         = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

目标仍是原50×25nm周期、z=-10..130nm、真空0.7nm、任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet/Fourier-DtN及全部复场/衍射/体吸收；必要构建至完整验收≤172800s。2e12B是整机物理内存，须保留系统余量、ownswap/OOC=0。本批仍是s=7/135、MPI1的有限同离散求解试验。

本报告明确覆盖前版的唯一KSP、restart32、600次作用和不改变PC组合的阶段限制，仅授权本文矩阵。旧V72不延长、不清零、不改PASS；新建独立V73窗口。重复收到本指令不得重复开批。

## 1. 事实、审阅范围及负结果含义

读取冻结HEAD的response全文、summary、实际残差历史、PC资格、根规则、仓库原则、任务身份与五个增量提交；核对本会话已读取的原task/docs规则未变blob。上一完整Review V70由挂载原件读取，其SHA256为512577697347f248ca1568bf6df61d44a3df9c7ad7cd273aeaea2b136c372d71，与已核对远端blob一致。目录未见独立supplement或同名V71。审查当前PC组合、retained FGMRES及既有PhysicalBalancedCoupling的数学组织。未SSH、未检查工作站实时PID、未重算大型场数组；measured指仓库执行记录中的实测。

依据：[回应](response_v72.md)、[summary](outcomes/summary.md)、[残差历史](outcomes/records/residual_history_v72.json)、[PC实测](outcomes/records/PC_qualification_v72.json)、[完整物理](outcomes/records/complete_physics_v72.json)、[最终费用](outcomes/records/resource_costs_final_v72.json)、[独立检查](outcomes/records/scientific_checks_v72.json)、[资产合同](outcomes/records/retained_iterative_contract_v72.json)。REUSE/ITERATE实际source为5564befc97ccb749e1b0e4d5fc909592d130c808，VERIFY为3a4a336e34e433bb673085dea1a72ccae1bd1894，不以最终文档HEAD代替。

| 同一25576tet/p5/828问题；recorded measured | V72结果 | 判断 |
|---|---:|---|
| 完整FE / retained含端口 | 1943745 / 1177293 | 全部767280内部恢复 |
| numeric / KSP / 实际步数 | 39 / 1 / 256 | 已实际求解，不是容量未运行 |
| 独立true / native | 0.998857044302 / 0.998857044302 | FAIL 1e-6 |
| 独立augmented / port | 0.999209905213 / 0.00456299823852 | FAIL 1e-6 |
| retained true | 0.999209919609 | FAIL 1e-11 |
| 39个块最大原残差 / PC复齐次差 | 1.38870485323e-10 / 2.06773995942e-12 | 组件通过，不代表有效逆 |
| 恢复 / Schur-original操作差 | 5.58822515019e-16 / 1.37482027758e-15 | 原代数关系通过 |
| 采样整树峰 / 最大gap | 40.1189613342GiB / 1.81898451899s | 非连续硬峰；ownswap/OOC=0 |
| prepared诊断尝试必要链 | 7699.21752537s | 不是合格解T_N1 |
| 39个numeric子时间 | 243.471794241s | 已含于ITERATE，不重复相加 |
| PC调用 / local三角解 / 原作用总数 | 258 / 9804 / 557 | 不把256步当全部运算次数 |

| 同一曲线上的检查点 | retained true | 原true |
|---|---:|---:|
| 0 | 1 | 约1 |
| 32 | 0.9992099800856654 | 0.998859209781315 |
| 64 | 0.999209919627473 | 0.9988571339433036 |
| 256 | 0.999209919609 | 0.998857044302 |

32→256的retained下降仅约6.05e-8；从初值到末态原true只下降约0.1143%。它不是接近收敛，也没有继续原样追加尾部的依据。另一方面，单凭这条重启曲线不能证明唯一原因就是粗空间缺波，或认为任意Full3D迭代都不可能。

V72的total场范数很小，原比较器以候选作分母时产生约630的total相对差；原分子/分母保留，不能把它不加说明地当成相对准确参照的误差百分比。散射场差约1.05、通道差约1.24和原式近1已足以否决候选。诊断R≈0.9968、T≈2.27e-6不是新物理发现，official=False；不把低内存失败场和正确direct场作同精度加速比较。

历史P6/L5空间FAIL及p5的828→1188有限模式PASS保持。重复restart边界审核已在末次修复中按同iteration/vector缓存，直接复用；它增加了费用，但没有证据说它造成了数值停滞。

## 2. 为什么只做这两个小改动，而不马上另建波动粗层

较长restart保留更多搜索方向，可能缓解反复丢弃子空间引起的停滞，但增加向量库和正交化费用；它不是更准确的物理离散。参见[PETSc restart说明](https://petsc.org/release/manualpages/KSP/KSPGMRESSetRestart/)及[FGMRES说明](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)。本轮128是一次预登记判别，不扫描64/128/256，不宣布它是原尺寸生产默认。

第二个改动保护粗层已经修正的平衡。旧公式先作粗修正，再作局部修正，后一步可能重新引入粗测试空间的残差。两侧平衡增加一个小粗修正将它去掉，不扩大粗空间、不改变38块，也不需要新局部矩阵。它属于已有BAL_H/平衡预条件思想，不是新发明；可复用[PhysicalBalancedCoupling](../../src/solvers/physical_balanced_coupling.py)的代数/拥有权组织，不能因此加载旧全局p4逆或H6。

非对称情形的平衡与deflation已有原始研究：[Erlangga–Nabben, SIAM J. Matrix Anal. Appl., DOI 10.1137/060678257](https://epubs.siam.org/doi/abs/10.1137/060678257)。本报告下述恒等式直接适用于可逆粗矩阵的复数代数；不搬用SPD误差界，也不继承[有吸收Maxwell Schwarz论文](https://arxiv.org/abs/1711.03789)在吸收/网格条件下的波数无关结论。

先完成这两个低接线成本的有限对照，可以避免在尚未区分restart与组合问题时，再支付新波动基、局部谱或新Galerkin的准备费用。若仍失败，本批就关闭这些解释，下一批再有根据地改变波动粗空间/传输，而不是再延长同一参数。

## 3. 冻结身份、准备复用与数学定义

沿V72 physical SHA df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44。保持25576tet/p5、1000个NOTCH tet、网格SHA c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c、828模式、原κ=(8.94046081729244,0.7821889682108057,0)、grazing1度/azimuth5度/s、原材料与完整Cκ；正式Si为n=0.999885140474+4.32477054e-6i、epsilon=n*n、mu=1。配置/method SHA可变，物理与离散不可变。

只读复用V70 local_packet、原q47/q63和V71的38块/Z/E0。指针、父schema、source和hash从现行合同与原清单解析；旧整体solver FAIL不否定健康算子、CSR、映射和Galerkin资格。生产及PC中global fine K/S读取、形成、factor都必须为0。父内部LU允许，38块及7068粗层的因子允许且全部计费。未保存的MUMPS因子不声称可重载；每个独立求解进程实际形成39因子，条件第二条再形成39次，不能漏记。

记原scaled接口算子为A=left*S*right，b=left*b_reduced；Z包含6240个粗FE方向与828个完整端口，E=Z*AZ。星号表示Hermitian对偶，不是普通转置。令B为原restricted additive Schwarz映射，端口分量仍由粗层处理：

```math
C=ZE^{-1}Z^*,\qquad P=I-AC,\qquad Q=I-CA,\qquad
M_1=C+BP,\qquad M_2=C+QBP.
```

M1是V72原组合，M2是本轮唯一新的PC组合。一次M2应用为：

```math
z_c=Cr,\qquad r_c=r-Az_c,\qquad v=Br_c,\qquad
M_2r=z_c+v-C(Av).
```

精确算术下Z*P=0、AQ=PA，故：

```math
Z^*\bigl(r-AM_2r\bigr)=0,\qquad
Z^*\bigl(r-AM_1r\bigr)=-Z^*ABPr.
```

这说明M2保持粗层残差约束，不说明其Euclidean残差必下降。按range(AC)与range(P)分块，AM1和AM2具有相同对角块；AM2去掉一个跨块耦合，但没有创造新的波动方向或保证改善谱。若剩余块PABP本身很差，平衡仍可能失败。这里B为非对称RAS，不能将Q误写成P*；不要求A或C自伴，不调用未资格的A*。

每次M1有1次粗解、38次局部解及1次PC内部A；M2分别为2、38、2。与外层A、显式true和PUBLIC_BASIX审核分开计数。局部/粗矩阵、halo、owner、ordering、shift、吸收、模式和端口缩放均不变。

## 4. 有界残差转移检查，不成为新诊断循环

在R128进程的39个因子建立后，用原物理b及V72最终失败的scaled残差作两份固定输入。后者只用于诊断，不参与新初值、粗基或候选选择。若旧残差文件缺失，用保存的旧retained与当前精确A重算一次；仍不可用则记录部分缺项，物理b检查和主求解继续。

对两输入保存r、Cr、r_c、Br_c、A(Br_c)、粗反馈C A(Br_c)，并保存M1/M2修正后的真实残差和Z*残差；范数同时给绝对值、原RHS尺度与参与运算尺度。可用相同已算Av作一次复数最优标量方向评分，但不把该标量用于正式PC。不要重新做空间界面、240点、mode或谱扫描。

新增pure复数块代数检查M2实现、复对偶和粗平衡恒等式；真实粗投影约束采用原BAL_H的1e-8操作尺度门，完整PDE残差门不变。粗矩阵/解残差、投影缺陷的绝对值必须同时报告，不能以巨大尺度掩盖问题。B128的公式配对不可靠只隔离B128；可信的旧M1/R128继续。诊断大小不作为选择有利PC或取消一个合法对照的规则。

目标15分钟、上限30分钟、最多24次原作用；原合格热作用仅按新加载必要做一对固定见证，不重复三次微基准、旧Galerkin构建或39块完整历史审核。

## 5. 预登记执行矩阵与分流

| 角色 | PC | restart / max_it | 初值与目的 |
|---|---|---|---|
| R128 | 原M1 | 128 / 256 | physical retained零；只检验短重启限制 |
| B128，条件 | M2 | 128 / 256 | 独立physical retained零；同restart检验粗反馈 |

先执行R128，原式及retained联合门通过后取消B128，避免为已达到的代数目标再跑一份。分流只看独立原式/retained/恢复，不读V70场来决定。若R128达到256步或其固定时间上限而未过门，只要B128数学、身份与资源可信就继续B128，不等下一轮review。R128方法性停滞不是阻止B128的错误；公共原式/ABI/身份不可信则先修。

两条均不从V72或另一条候选warm-start，不从直接场造RHS。两条采用相同的现有正交化方法与实际PETSc选项；只改变表中因素，不同时偷偷切换MGS、容差或norm。record KSP view、Gram-Schmidt设置及reported/true差；明显非有限或原式恒等式失败按科学门停依赖。

最多2次正式KSP.solve attempts，含确认后的实现修复；如修复占第二槽则取消尚未运行路线，不追加第三条。每dat只有一条明确的PDE求解；不为共享内存因子新建常驻服务或把两条暗藏在一个dat。两次进程顺序运行、各自清场。数学准备复用不等于跨进程因子复用。

候选结束即保存完整retained/RHS/尺度/原式及恢复包；每条释放KSP与39因子后再完整恢复输出。最后一次独立VERIFY可同批消费两份候选；若R128失败但可恢复，其输出标diagnostic。参考场只在路线分流和候选冻结后读取。旧runner不能在第一条失败后提前写全批scientific_queue_frozen并锁死已授权B128：使用单候选freeze和最终批次freeze分层，旧入口行为不变。

保留同iteration与同vector内容的原式结果缓存，不能仅按iteration缓存不同候选，也不能跨source/尺度/RHS复用；避免restart边界重复审核的已知费用。每32步、首次候选通过及末态保存true/原式，不以中间必须下降多少倍的早筛选截断。

## 6. 数值、物理、成本与安全门

retained显式true≤1e-11；独立true/native/augmented/port各≤1e-6；恢复/MPC/Schur-original等恒等式≤1e-10。独立direct1e-10单列，不替代formal门。始终检查原方程，不只检查投影残差或新粗约束。

与冻结V70同离散场严格比较：total/scattered复E、H、curl、原240点及物理参考面复通道≤1e-6，R/T/A/A_volume绝对差≤1e-8，逐mode功率差≤1e-9，独立能量闭合≤1e-5。原点外推倏逝坐标仅diagnostic。official仅来自原式通过场，不能用旧参照的功率填新结果。

保留原比较器分子/候选分母，同时从已保存参照范数给V70分母的纯数组评分；一次差分积分，不改floor、不重新投影或校幅相。双分母不能择优授PASS，同离散严格判定两种均须满足。旧V72 630比值与失败记录不改写。

整进程planning/warning/sampled-stop仍96/112/128GiB，默认轻量阶段64/80/96GiB；因子双倍symbolic总门仍80GiB，不借旧256GiB或整机2TB扩容。每个factor前继续live RSS+全部未分解双倍估计+future准入。future提高为至少12GiB且逐项核对，容纳较长Krylov库；不得只把旧8GiB原数照抄。

| 仅两组主Krylov向量；derived | 条数 | 当前N=1177293时载荷 |
|---|---:|---:|
| restart32 | 33+32=65 | 1224384720B=1.14030GiB |
| restart128 | 129+128=257 | 4841028816B=4.50856GiB |
| 增量 | 192 | 3.36826GiB |

它们不是实际RSS，还要计X/b/r、PC、独立审核、原FE恢复及PETSc工作区。两个KSP不得共驻留。当前规模的3.37GiB增量不能推广成原尺寸的廉价选择；原尺寸继续要求有界Krylov/recycling/粗空间与分布式数据的独立容量证据。

新总窗12h，科学有载≤10h，最后1h收尾；每条正式迭代累计≤3h，各≤256步，全批≤512步及1600次全域作用，资格诊断≤32次。R128/B128在每步约2/3次A之外，原式和显式true全部计费；接近总上限时为最终保存/审核保留至少40次余额。每个numeric前以实际PC/热作用与至少4500s完整输出审核储备准入，不只预算三角求解。预算不够完成条件B就准确not_run；不得压低门或无限延窗。

预计标准最多78个新局部/粗numeric（两条各39），没有全局fine因子。修复的重复numeric全部入账且占同一两路线配额。完整因子未序列化，不能声称已从上轮重载。

原complex128/int64、MPI1/math/CPU1/GPU0、ownswap/OOC0、PSI/cgroup/宿主/384GiB邻增长/物理核-SMT/机器heavy锁保护保持。逐块读取CSR、留下factor后释放输入。新ignored≤32GiB，Task去重上限664GiB（仅比此前632GiB增加本批储备），free≥50GiB且512MiB证据余量；不复制父大包、不删除负结果。

完整成本分路线：读取、factor、每类PC操作、正交化、独立原式、恢复/积分/写出和VERIFY；父构建与历史失败另列且只计一次。未测正交化只列未分段余额，不把全部step时间归给PC。没有合格解不授速度或内存收益；父V70形成过全局S，prepared-start无S不等于几何起点packet-only已实现。

## 7. 实现、不中断策略与交付

仅窄改现有bounded_trace_pc/study、reused scope和physical_retained_fgmres参数接线；M2作为显式variant。优先复用PhysicalBalancedCoupling的公式和拥有权，或在现有PC中分离coarse/local方法，不能复制整套FEM或误带旧全局p4逆。旧M1默认行为不变。

普通API/dtype/shape/路径/缓存/writer问题同轮最小修复、targeted回归后继续；同根因两次无效换正确实现或隔离，不第三次盲重放。修复累计≤2h并计入总窗。向量已合法返回，后处理或JSON只补消费、不重factor；新B桥失败不取消可信R128，原式/ABI/身份或监督不可信则隔离共同依赖。科学停滞不当bug，不再继续原restart32尾部。

不full pytest/CI、全仓索引、历史hash扫描；不重解FLAT/V70/V72，不重建38块/Z/E0、15表、网格/模式或冷packet。新增资格限复数反馈代数、两路线scope/freeze、缓存键与异常释放，以及实际小PETSc长restart接线；在原资格环境中运行，不能升级系统ABI。

正式入口须实际创建、commit clean和validate后使用：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v73_reuse_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v73_restart128_solve.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v73_balanced128_solve.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v73_compare_verify_cost.dat
```

PRECHECK/VERIFY不暗藏numeric或PDE；B128按明确分流执行。每dat绑定原输入、resolved_config、run_manifest、input/physical/source SHA、ABI/MPI/资源及artifact hash。用V73的新receipt消费旧数学资格，不能把V72的solver FAIL改true来解锁。

提交计划：C1最小variant、scope和定点回归；C2有明确原因的修复（有则独立提交）；C3结果与紧凑交付。数值source与后续文档HEAD分开。交付response_v73.md、outcomes/restart_coarse_feedback_v73.md及records：两条残差/真实次数、反馈分账、原场/模式/功率、全部成本/峰/gap、原式和双分母checker、修复及not_run原因。保留单一路线成功取消B的事实，不造第二份结果。summary/README/两总账仅短追加，不复制旧大payload。

Git仅canonical本分支fetch/ff-only、提交和精确push，不reset/stash/clean/amend/强推、不改旧review或任务。最终核对remote完整SHA、clean/upstream、closed/active null、后代清场与锁释放后交付暂停；不merge、不改邻worktree、不自动开下一窗。

## 8. 决策收口与目标衔接

R128通过：证明当前失败至少可被更长Krylov记忆克服，取消B并形成实际成本；不称PC已有波长鲁棒性。R128失败而B128通过：取得同restart下两侧平衡的实测收益，粗约束改善只是机制证据，非普遍定理。两者都失败：关闭继续加restart/迭代尾部或同组合调参，提交剩余补空间缺陷及真实成本，下一合同再选择一个Maxwell波动/谐波粗空间或传输条件变化；本批不自动开发它。若诊断新桥不完整但完整路线已运行，仍以实际场和原式交付，不追求为了文档完整而重算。

即使本批代数通过，历史P6/L5约1.14e-4/1.23e-4、240点约9.56e-4的连续空间FAIL也不升级。下一步须并行保留物理精度工作，并以已合格同离散解推进packet-only冷构建和有界中间尺度/MPI试验。不能直接跳到最大原尺寸，也不能把restart128的大向量库永久固定为目标方案。

邻支快照：task40extra_0p7nm_engineering@83c4fed6e29ea19f0a70a92a403b867851f3ef35的Review V26接受V25完整30464-cell体积作用/凝聚RHS/恢复证据，继续完整reference-q消费者及条件factor；不是原尺寸场已通过。task42extra_feinn_5nm@7075a2c0d86018c3500dc2815c2bcf9c2cc739ca的Review V43授权V44宽度/内层优化神经对照；本支不训练NN或接管这些工作。NN-V3/dot保持独立，不因远程无新提交推断本机闲置。

**本轮不是用更多内存维持原来不下降的256步，而是用两项可区分、成本可控的完整对照，决定是否值得继续现有局部/粗组件。最终目标仍要求分布式、matrix-free、可扩展Full3D迭代，而非无限放大直接因子或Krylov库。**
