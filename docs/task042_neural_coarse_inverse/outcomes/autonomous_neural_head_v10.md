# V10：自主输出头与端口试验完成，未取得有限元资格

| 对象、范围与最终状态 | 实际结果 | 证据入口 |
|---|---|---|
| V10_AUTONOMOUS_NEURAL_HEAD_AND_PORT | N0→A→B1→B0→C→D1/D2→F完成；四候选均NOT_QUALIFIED、NEGATIVE | [独立资格与分流](records/qualification_and_dispatch_v10.json) |
| 固定micro-pilot | 0.7nm、384hex、Nédélec p3、h=0.175nm、原三维缺口、双Floquet/Fourier-DtN、完整40复通道 | [数据与物理身份](records/data_source_provenance_v10.json) |
| 规模 | FE34050／独立trace18144／内部13824／slave2082／port40／reduced18184；本批不改变p/h/MPI/通道库存 | [原action身份](records/data_source_provenance_v10.json) |
| 薄输出空间 | B1/B0各1560复输出系数＋40端口，有效rank1600；C约束端口后rank1560 | [矩映射、秩及容量](records/head_mapping_and_rank_v10.json) |
| 条件后续 | E两轮隐藏层更新、P同网格p4参考均未准入；最大0.7nm／48h仍NOT_QUALIFIED | [条件与未运行项](records/continuation_checks_v10.json) |
| 正式资源 | 12次launch共650.093757705s；整树采样同时峰2376962048B＝2.213718GiB，自身swap0；CPU-only | [run index](records/run_index_v10.json)、[全部费用](records/resource_costs_v10.json) |
| 历史 | V1–V9负结果、task/review/旧response/旧records不改；旧p4逆路线CLOSED_RESEARCH_NEGATIVE | [进度journal](records/progress_journal_v10.jsonl) |

网络先生成一组空间函数，有限元边／面上的积分把它们变成原Nédélec自由度。本批固定隐藏层，直接由原方程求这些函数的组合系数，检验过去用优化器学习线性输出层是否浪费了工作。收益是免去这部分长训练；代价是显式保存两张薄矩阵、进行一次稳定最小二乘分解。网络仍为原3×64、8载波、FP64、batch8；没有变成节点值或采样点PINN，也不声称此薄矩阵办法已能扩大到最终模型。

## 身份、总截止与资料边界

起始本地HEAD为120161581b69741e3e059582c3f7179b7036c337。核实分支、upstream、canonical linked worktree、自有锁空闲与无活跃Task042运行后，仅fetch本分支并安全快进到Review V7提交fe2d3f6730080e629daa712e99a096605bcbf947。common Git directory为`/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`，只在NN-Lab开发，不改其他worktree的HEAD/index/源码/环境/运行文件。

本轮用户与Review V7授权明确覆盖旧“只能诊断／不得续研NN或新增求解”限制，以及仅Task042的heavy独占要求。总start为2026-09-29T13:42:33Z（Asia/Singapore 21:42:33），heavy最迟20:12:33Z停止，总deadline20:42:33Z，最后1800s留给低负载交付。原start＋单调时钟绑定不重置；没有用每分支上限相加换取额外时间。所有可执行路径已结束，按合同提前收口，不为了跑满七小时重复失败设置。[预登记计划](records/branch_plan_v10.json)给出阈值、范围与原窗口；阶段开始/结束、source、余时及分流持久化到[journal](records/progress_journal_v10.jsonl)。压缩上下文后实际重读完整Review V7和进度，未重新启动队列。

材料继续离线读取唯一canonical表`input/materials/si_optical_constants_v1.json`，ID为SI_OPTICAL_CONSTANTS_USER_20260929_V1，SHA256为55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2。源标签0.699999988明确alias到nominal0.7，n=0.999885140474+4.32477054e-6i，epsilon=n*n；Si各区域、下端口一致，air n=1、mu=1。四波长登记不是四波长扫描。

physical SHA为2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de；mode SHA为93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262；原action NPZ SHA为9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454。完整库存为上20＋下20，原键、极化及参考面随mode manifest绑定；不沿用旧80通道。[160条新候选通道记录](records/channel_observables_v10.csv)保留全部复total/scattered振幅、参考及功率，原键入口见provenance。

A/B/C求解进程只读取S、b、几何、矩包和授权NN7参数；B0只使用seed420906原随机隐藏初始化、输出与端口从零开始，不读取NN7隐藏权重。每个候选先保存状态/hash，独立验证进程才读取REF7（既有p3 NPZ SHA a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355）。V7接受状态UNKNOWN保持，未猜造optimizer状态。D1之后建立不可逆reference barrier，本夜未再回到A/B/C/E。研究设计已看过V9诊断，不称全新blind study；旧seed420620池仍未生成／读取。

| clean实现及用途 | 完整source SHA |
|---|---|
| C1代数、窗口、薄矩映射 | e4dff00adb3233e9a7e31397d193c8e2e6c72d12 |
| A、B1/B0及其独立验证 | 1fb8a949bbed81f34645d96e80c7025a3b22ef4d |
| 三见证补核、C、C验证、D1及原D2 | 6e564a66868374560dae66321564f3e767f5639c |
| D2元数据最小修复／保存向量重放 | 6cbaec7848936b81bf2c34c862358a38090c58c0 |
| 最终raw Gate及反例测试 | b6546d762f5749ceca24b28e60ad4c380adc6741 |

全部正式stage经`scripts/run_case.py`独立one-run dat；dat、resolved、manifest、source、参数/数组及状态hash见run index。文档提交HEAD不替代这些运行SHA。E1/E2/P4 dat只是预登记入口，未实现或启动对应未准入工作，不是运行证据。

## 原方程求解的四条路线

A只调整NN7 trace的一个复倍数与40端口，其系数完全由原S/b的41列最小二乘求出。得到c=1.0549130385431194+0.032258837734582824i；没有使用参考相关系数。内部恢复仍为固定内部特解＋trace/port响应，没有把特解跟完整场一起缩放。

B1固定已训练隐藏函数，B0固定随机隐藏函数；原边／面矩、Piola、orientation、canonical owner/MPC把1560输出系数变成trace。两者各构造18144×1560的P和18184×1600的W=S Q，用现有SciPy1.11.4 `gelsd, cond=1e-12`，不形成WᴴW、SᴴS或完整S，不扫rank/阈值。每次最多16列构造W，1560次列作用逐项计费；40端口列复用A的无标签原作用。解出的输出头写回真实Torch层，再经原packet_forward重新生成trace，不能只保存Pγ。

C在B1空间中以原凝聚Hhat精确求齐全端口，消去40个边界未知量后重求同一输出头；它解决端口关系的代数闭合问题，不提高port loss权重。Hhat不是原Hp，亦不是p4逆；完整40端口仍保存和验算。

| measured／相对量 | A幅相＋端口 | B1已训练隐藏 | B0随机隐藏 | C精确端口闭合 | 原限值 |
|---|---:|---:|---:|---:|---:|
| 原Schur残差 | 0.912888118 | 0.797693967 | 0.797324192 | 0.798257630 | 1e-6 |
| native残差 | 0.687417356 | 4.381516135 | 10.964503374 | 0.309567327 | 1e-6 |
| 原增广残差 | 0.354021464 | 0.309348737 | 0.309205337 | 0.309567327 | 1e-6 |
| 原total增广残差 | 0.122845231 | 0.107343822 | 0.107294062 | 0.107419673 | 1e-6 |
| 固定RHS端口残差 | 0.004582820 | 0.006954733 | 0.005822466 | 6.5094e-17 | 1e-6 |
| 恢复残差 | 2.2133e-13 | 6.0320e-13 | 6.1260e-13 | 6.1422e-13 | 1e-10 |
| 散射E L2差 | 0.634722559 | 0.700726410 | 0.732080199 | 0.697842386 | 1e-4 |
| 散射scaled-curl/H差 | 0.634717994 | 0.700809929 | 0.732146052 | 0.697931617 | 1e-4 |
| total E L2差 | 0.066420430 | 0.073327392 | 0.076608404 | 0.073025594 | 1e-4 |
| total scaled-curl/H差 | 0.066421213 | 0.073337523 | 0.076616749 | 0.073036317 | 1e-4 |
| 完整total复通道差 | 0.066132339 | 0.050212579 | 0.049566248 | 0.050260577 | 1e-4 |
| 完整scattered复通道差 | 0.632708044 | 0.480398893 | 0.474215258 | 0.480858108 | 1e-4 |
| 有效秩／复列数 | 41/41 | 1600/1600 | 1600/1600 | 1560/1560 | 固定阈值 |

L2及curl来自完整有限元体积分；H_code=curl(E)/(i k0 mu)。参考total E范数1.915154517、scattered E范数0.200411007，背景会使total相对误差看起来更小，故严格分开。恢复、slave-zero、原Schur/native身份通过不代表原方程通过。selected total E/H复采样也独立重算；scattered采样点没有另存，完整散射E/H范数确已检查，四候选因原方程与完整场失败无需宣称所有资格证据齐全。

原loss从NN7的0.417024786降到B1的0.318157837；随机B0为0.317862935，略更低，但B1散射误差略更小。因没有重复随机试验，不能推断一般优劣，更不能称已学习隐藏层带来合格神经增量。B1/B0系数范数176304.205／129585.368，未截断一阶残差relative为1.183e-8／9.056e-9。保留奇异值范围分别[9.0824e-9,298.5212]／[2.1955e-8,349.8170]，没有数值截断。raw字段`exact_full_space_optimum_claimed`只按“数值rank完整”解释；浮点分解和报告的一阶差不能证明精确全局最优，更不能证明整个非线性网络的表示下限。

真实输出头重写的相对差B1/B0为2.925e-11／2.490e-11，C为2.868e-11。最初每次B仅核一个非零见证及真实回写；随后独立HEAD_CHECK补核每个P的三组固定seed421011/421012/421013非零见证，最大6.265e-16，保存trace再生差0，不重建P、不重分解或跑S。**三个见证补核晚于两次B冻结**，不追溯称三个均在正式B前通过；本批结论保留此Gate时序偏差。[详细记录](records/head_mapping_and_rank_v10.json)。

C的cond2(Hhat)=13284.1630≤1e10，三次小solve最大operation差1.284e-20，三次实际S块重组最大1.371e-18。非零真实梯度三方向、h=1e-4/1e-5/1e-6全部通过，最大relative1.088e-8≤1e-5；包括FᴴHhat⁻ᴴ链式项。C把native从B1的4.3815降为0.3096、端口闭合到舍入量级，却未改善Schur或真实体场到资格。它只消除了端口未闭合引出的native放大，体方程／全局困难方向仍未解决。[端口与梯度检查](records/port_closure_checks_v10.json)。

所有candidate的rho=max原Schur、native、固定RHS端口残差；独立checker从原字段、selected复E/H、完整total/scattered复通道和逐通道功率重算，不相信saved PASS/status。A/B1/B0/C的rho为0.912888／4.381516／10.964503／0.798258；进入基线分别0.913263／0.913263／1／4.381516。C虽将rho减半且native改善，scatter E=0.698>有限进展0.5；其余均无P/P+或F。故E没有新增50步续训；P没有新p4参考。不是因为一条路线失败即停，而是先完成不同机制和两个独立D子项后收口。

## 功率检查：全部只作未资格化诊断

| 状态 | R_total | T_total | A_balance | A_volume | 能量闭合绝对差 |
|---|---:|---:|---:|---:|---:|
| 既有同mesh p3参考 | 0.117645819 | 0.877047783 | 0.005306398 | 0.005306398 | 约2.91e-12 |
| A | 0.088983597 | 0.835104788 | 0.075911615 | 0.005028116 | 0.070883500 |
| B1 | 0.084509484 | 0.796652311 | 0.118838205 | 0.004842476 | 0.113995729 |
| B0 | 0.085119390 | 0.798195116 | 0.116685495 | 0.004854407 | 0.111831088 |
| C | 0.084369679 | 0.796538269 | 0.119092052 | 0.004842482 | 0.114249570 |

R/T由原DtN边界参考面的出射复振幅计算；A_balance=1-R-T，A_volume由原总场材料吸收体积分得到。A_balance与A_volume相差约0.07–0.11，远大于1e-5，不能以接近某个体吸收值称成功。完整R00_s、R00_p、selected E/H、原40通道与所有门限差保留在[候选CSV](records/candidate_comparison_v10.csv)、[通道CSV](records/channel_observables_v10.csv)、[独立Gate](records/qualification_and_dispatch_v10.json)。没有任何新official R/T/A或正式场结果。

## D：参考只用于结束后的失效定位

D1用固定P一次拟合既有参考的canonical trace，并显式用参考port恢复。它检查“同样隐藏函数能否表示参考”，不是从原方程求解；拟合系数不发布为在线候选、不进入训练、无新初值。

| reference-assisted diagnostic，非求解 | trace欧氏相对差 | 散射E L2差 | 散射curl/H差 | native残差 | rank |
|---|---:|---:|---:|---:|---:|
| B1固定隐藏 | 0.001156720 | 0.001024521 | 0.003201747 | 0.334956520 | 1560 |
| B0随机隐藏 | 0.001152351 | 0.001028788 | 0.003199274 | 0.338246562 | 1560 |

相同空间能得到远优于无标签方程拟合的场，但这两项仍超过1e-4，且B1/B0接近。因此有固定空间不足的证据，同时有方程目标／优化／数值稳定性与真实场误差之间落差的证据。**trace欧氏最小二乘不等于FE物理L2最小二乘**，这些数值不是物理场最小误差的证明，也不是整个非线性网络的上限；唯一根因INCONCLUSIVE。[D1完整秩、原审核与边界](records/representation_diagnostic_v10.json)。

D2只分解原未凝聚V在参考散射场、LSQR8误差和最低原rho的新候选C误差上的作用。误差恢复使用F(z_ref)-F(z)，与零内部载荷方式配对；保存背景与内部特解的正确抵消。curl-curl与负epsilon质量项先组装共享单元贡献再求范数，不独立凝聚、没有新谱／Krylov／factor。原pilot体内无PML/Robin项，体边界项为零；DtN耦合仍由原packet单独保留。

| 固定场／误差方向 | curl-curl范数 | 负epsilon质量范数 | 相加后的原V范数 | 相加范数／两项范数和 |
|---|---:|---:|---:|---:|
| REF7散射 | 10.418225131 | 10.416192241 | 0.218514056 | 0.010488129 |
| LSQR8误差 | 10.401837271 | 10.401735538 | 0.047449547 | 0.002280836 |
| C误差 | 7.269038105 | 7.268860259 | 0.070173321 | 0.004826923 |

分项重组与原V的最大operation-relative差1.69745e-14；强抵消后的result-relative差最大7.4592e-12仍保留。齐次恢复配对最大3.8265e-16，保存field配对0。复交叉项、平方恒等式、运算尺度和数组hash见[D2记录](records/volume_balance_diagnostic_v10.json)。这些固定方向可以产生弱体响应；强抵消不证明全系统奇异、条件数或唯一病态。

原D2计算三套向量已完成保存，最终嵌套`mappingproxy`元数据JSON序列化失败。仅一次递归元数据最小修复，单独D2_REPLAY读取已保存向量核验；不重装FE、重装配、重跑分项作用或LU。原失败source/log/run/费用保留，保存向量的hash首次在重放前锚定，未冒称原失败JSON已发布hash。D2分项计时未能持久化，明确UNKNOWN_NOT_PERSISTED；原全stage与重放费用均计入。

## 全过程成本与共享运行边界

| 正式路径 | 含launcher、设置、保存的wall秒 | 同时整树采样峰GiB | 新S／Sᴴ调用（含审核） |
|---|---:|---:|---|
| A | 11.136939 | 0.459633 | 43／0 |
| B1 | 204.376510 | 2.213718 | 1564／0；40端口列来自A |
| B0 | 190.492807 | 2.211979 | 1564／0；40端口列来自A |
| 三见证补核 | 20.268766 | 0.882545 | 0／0 |
| C | 53.061701 | 1.671535 | 47／2 |
| 四独立FE验证合计 | 63.489001 | 0.624249最大值 | 合计8／0 |
| D1两固定空间拟合及场审核 | 90.466510 | 1.253971 | 3／0 |
| 原D2失败＋保存向量重放 | 11.326094＋5.475427 | 0.422180／0.387970 | 原curl/mass/V各3次derived，重放0；原总计数未持久化 |

B1/B0的矩映射耗时10.5146／8.6967s，薄S列作用137.4500／128.0427s，薄LS34.1774／30.2922s；C薄LS29.1549s，D1两次LS29.5086／33.6095s。费用分解不是新增父时间，网络重写、原审核、I/O、设置和未细分控制时间均包含launch/worker wall，不能把子S或LS再次加进总账。完整计数和计时见run index；网络没有本轮隐藏训练／optimizer更新。

不能把B1“新增204秒”当作从零求解成本：它继承NN7路线7142.986080s（500Adam＋48L-BFGS外层、1611closure、完整前反向费用）。必要共用原FE设置196.425794s、真实梯度28.238506s、V6 q15矩包1.473339s及其接口／辅助旧费用保留。B0不继承NN7训练，但使用同一资格化FE/moment，以及A构造的40个无标签port列；这部分为共享设置，A整个11.136939s可作其增量保守上界，端口列单独wall没有另测。C另依赖B1的P/W构建成本。按方法列出这些继承与设置，历史累计仅加本夜新launch费用，不再次叠加已在carry内的旧训练。[全账](records/resource_costs_v10.json)。

V6–V9 carry10209.145962639828s不重置；V1–V5的更早ledger独立保留。新有载费用包括全部失败、测试、辅助和发布，并另收180s明确保守短命令/收尾占用；最终新账和累计值以resource_costs_v10.json为准。预算elapsed还包括实现／阅读／等待／交付，单独由原总start约束，不能用650秒求解wall冒充全夜elapsed，也不要求把上限跑满。

P/W载荷452874240B＋465510400B≈0.855GiB；构建前保守resident规划6383926888B≤8GiB，gelsd查询workspace B1/B0为3283816B，所有稠密复制、file-backed resident pages、ML/SciPy子进程、BLAS/JIT与launcher纳入整树采样RSS。P/W留ignored、退出释放RAM，没有OOC因子，不只报告参数内存。没有构造候选global p4 LU、完整S/global FE CSR、WᴴW/SᴴS、ILU/Riesz逆、私有audit CSR或hidden fallback；复用局部恢复packet、小Hhat40和薄LS被完整披露。

每stage实时选核：A CPU11、VERIFY_A CPU13，其余正式CPU0，均核查SMT/邻worker与监督器/加载线程；不是硬编码CPU0永久空闲。MPI1、数学/Torch intraop/interop1、DataLoader0、nice10/idle I/O只作用于Task042。FE `.venv`与CPU-only `.venv-ml`分离；SciPy仅在资格化FE/pure子进程，原FE ABI complex128/int64，原生库前缀只读复用；缓存、JIT、TMP、bytecode、模型、输出都在NN-Lab，不升级安装或污染邻环境。

没有独立cgroup委派，16/12GiB限额是独立0.5s整树采样watchdog，不能称连续内核cap。监督进程覆盖所有后代、父监督丢失保护及原总截止；低成本超时和128MiB整树触线测试先通过，保存独立兄弟进程仍存活证据。全部正式后代清场，own swap0，无Task042 GPU工作。[线程probe](records/post_thread_probe_v10.json)为额外post-run安装配对检查，不伪造in-run时间；BLAS/LAPACK包装库数量不是独立线程池数量。

初始/末次MemAvailable约945.3/947.4GB，系统reserve216.3GB＋邻增长137.4GB，disk自由仍约3.444TB，artifact低于20GiB。原heavy继续运行，没有邻任务改绑核、环境/优先级/watchdog/锁或信号操作。没有资源触线或持续memory PSI压力；可比邻阶段速率不足，所有性能／影响只标shared-workstation observed／INCONCLUSIVE，不承诺绝对零干扰或正式加速。[资源观测](records/resource_observations_v10.json)。

## 测试、异常与下一最小建议

最终25项相关pytest通过（完整action、复数非Hermitian、原恢复特解、薄LS、端口闭合、时间窗、整树清场、材料、raw Gate反例），ML原矩/输出头三见证通过；真实三组pilot补核及真实C梯度另外分列。Ruff/compileall/one-run输入、本地表格/公式/链接、authority/历史byte保护见[静态记录](records/static_checks_v10.json)。未运行full repository pytest、MPI2/4和CI，未因无关旧checker重跑F0或旧campaign。

一项正式最小修复是D2序列化；辅助probe固定库数量断言、compact helper单个括号错误及其错误嵌套选核位置各作一次局部修正，首次失败费用均保留。后者在已绑核helper中把自身监督器算成占用，并非证实整台主机无空闲核；改在未绑核只读收尾入口核验，数值阶段未重跑。另FE ABI预检首次CLI不支持`--mode`，随后正确调用资格化通过。既有输入/ABI/训练环境未改。

Review V7实际GitHub richText为3表／5 math-renderer，列一致、原review未改；结果文档发布检查见[publication](records/publication_checks_v10.json)。HTML渲染核验不冒称浏览器像素截图。

**唯一下一建议，未实施：**在冻结随机P及原action中做一个固定、非零、已知系数的制造RHS回收试验，用同一薄LS阈值与真实输出头重写核对是否能回收空间内的z。它可以把“大系数／薄分解／回写数值稳定性”与“原入射解不适合该空间／原残差目标弱响应”进一步区分；不读取目标参考，不加载波/宽度/rank，不宣称真实入射有限元资格。需下一review明确其RHS及审核合同，本夜未自动实施。

最终0.7nm／48h仍缺合格micro原方程与完整场、独立离散精度证据、目标规模通道/存储/单步费用和所需步数；目标放大成本unknown。当前没有合格神经增量，没有自动扩大几何、运行p4 enrichment/F5/p6、GPU或旧p4路线。推送唯一执行分支后清场停止，等待review，不merge。
