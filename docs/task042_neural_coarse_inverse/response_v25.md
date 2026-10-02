# Task042 V25：必需指标库存修复与八块方向诊断

**已完成 Review V22 §§5–7，结论为 `DIAGNOSTIC_COMPLETE / EIGHT_DIRECTIONS_WEAK`。** 对两个已消费冷终态，八个局部解方向的最佳复数组合只能使当前原 trace 残差降低约1.68%／1.01%。这支持关闭“仅学习这八个方向的系数”路线；不是新的物理解、神经收益或所有域分解方法的否定。没有续跑 V24 第5周期。

## 身份与执行范围

| 项目 | 实际核验／证据 |
|---|---|
| branch／upstream | `task42_neural_coarse_inverse`／`origin/task42_neural_coarse_inverse` |
| canonical worktree／common Git | `/home/fenics/Projects/NN-Lab`／`/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；开始无Task042 actor、工作树干净，安全fetch后已包含 `8e23b9f4620510c5f578c334faa63a06b4c410a3` |
| 冻结base | `ccd357885f7f9be84efe3be07868cc94f13d93fc`；未reset、改dot／master、操作其他worktree或改共享Git配置 |
| 实际run source | `bc88fe5a81d086059dec705db333b9cf9bf2921e`；实现提交clean后运行，结果文档HEAD不冒充该source |
| 物理／离散 | 原0.7nm、1.4×1.05×1.4nm三维缺口micro、384hex/p3/h0.175nm/q15、双Floquet、40端口；trace18144、完整z18184；材料canonical用户表未改 |
| physical／packet | `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`／`9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454` |
| one-run | `python scripts/run_case.py input/task042_neural_coarse_inverse/v25_block_residual_diagnostic.dat`；一个diagnostic actor，三份固定输入，不是求解器扫描 |

开始及交付Git核验见[交付回执](outcomes/records/delivery_receipt_v25.json)；完整input／mode／材料／map／矩阵／LU／pivot／父状态及成员hash见[input inventory](outcomes/records/input_inventory_v25.json)和[run index](outcomes/records/run_index_v25.json)。原V24来源仍为03fd7874190c33a837879d76312d9911223314e0，其ledger、raw及失败未改。

## 先修checker，保留0/5

checker现在明确要求六个正式场误差和四个功率差，缺项、空表、NaN／Inf／负误差均拒绝。40个幅度行的完整原mode对象、极化、side／m／n及参考面逐项核对；功率行没有完整original_key列，按实际schema核对同一40项显式键与参考面。原方程、独立total-native、恢复和每通道功率分别保留，saved status不能补齐数据。

52项库存回归通过；含新复数代数／deadline／读取边界及原V24准入回归的最终focused suite为 **93 passed**。V24原始记录重算仍 **0/5**。例如LZ4原Schur为0.08137666790（限1e-6）、散射E差0.56888827794（限1e-4）、最大通道功率差0.007245973616（限1e-6）；旧失败没有被本次修复改写。[checker证据](outcomes/records/checker_inventory_v25.json)。

## 三残差与八方向的实测

局部方法原来把八个块各自给出的修正直接相加。本轮把它们分开，用完整原方程测每一块的全域响应，再求这八个响应能达到的最佳线性组合：区别“统一幅相不合适”与“这些方向本身缺乏消除当前残差的能力”。这多付出每状态8次原作用；方向仍来自原有八块，没有新增自由度或神经训练。

eta是一次诊断修正后剩余的原trace残差范数除以该状态的原trace残差范数。1代表无下降，大于1代表增大；它不是相对于准确场的误差。unit为统一系数1，eta1允许一个最优复数幅相，eta8允许八个独立最优复系数。

| 固定已消费状态 | eta_unit | eta1 | eta8 | eta8范数下降 | 已分辨rank |
|---|---:|---:|---:|---:|---:|
| V24-LZ-INITIAL（仅对照） | 2.0283184653 | 0.8776402575 | 0.8641444186 | 13.585558% | 8 |
| V24-LZ-CYCLE4 | 2.8176911544 | 0.9999995996 | 0.9832369898 | 1.676301% | 8 |
| V24-LCZ-CYCLE4 | 3.9247610154 | 0.9999978273 | 0.9899246286 | 1.007537% | 8 |

固定complex128、列范数均衡、nonpivoting economic QR和小GELSD／cond1e-12；没有正规方程、阈值扫描或用空residues冒充零残差。两个终态eta8均≥0.9，触发预登记弱方向分流。最佳组合对残差**平方范数**的覆盖分别为3.324502%／2.004923%，不得与1.676301%／1.007537%的范数下降混用。

三组秩均8，均衡后最小／最大奇异值比约0.735／0.657／0.737，QR／正交、局部对角作用、复线性重组及LS驻点Gate通过。新一次原A(q)和原A(Σq_j c_j)复核薄预测；最大差/norm(b)=1.42436e-15，按当前norm(r)最大2.72383e-15。驻点缺陷最大7.39952e-17，原保存残差映射最大5.99820e-17；40端口重闭合与18144／40／18184拼接核验通过。初始port实际为零，是原b闭合所得；没有强行置零，两个终态port非零。

[指标](outcomes/records/direction_metrics_v25.csv)、[独立缓存重算](outcomes/records/cached_array_checker_v25.json)、[数值Gate／系数](outcomes/records/numerical_gates_v25.json)、[8×8来源响应](outcomes/records/block_response_v25.csv)、[复交叉项](outcomes/records/complex_cross_terms_v25.csv)保留全部结果。交叉项是范数分账，没有用于正规方程求解。目标块相消比约0.304–0.568，只描述这些方向，不能由此推全谱、条件数或唯一根因。

本轮没有调用真实field recover、uncondensed或REF7，不产生新native／E/H／RTA资格；独立齐次复数小测试确认方向不混入物理端口常数，生产恢复函数不变。所有保存量仅为方向／响应／系数／诊断残差，不登记新的solver终态。旧五态完整资格仍FAIL，神经20%仍 `NOT_DEMONSTRATED`。

## 成本、停止与未运行

| 对象／口径；全部shared-workstation | 实际值 |
|---|---:|
| 整个诊断actor监督wall／launch wall | 25.665227／27.057488 s |
| 只读factor hash／reload | 14.426483 s（actor内，非另加费用） |
| 三状态八方向计算／其中薄LS | 0.967305／1.461940／1.932287 s；薄LS合0.068425 s（嵌套） |
| 原S／SH | 39／0（总上限64） |
| 局部LU solve／L-U pass／reader | 40／80／1（含16个独立重载见证；上限96／192／2） |
| 原40端口小factor／solve | 1／37；端口解计时0.005154 s |
| 同时整树采样峰／自身swap／VRAM | 1,832,550,400 B，约1.707GiB／0／0 |
| 事前同时规划／已有A+LU | 5,813,108,752 B（derived）／1,354,430,592 B，pivot另计 |
| 有监督辅助wall，包括失败 | 26.429976 s；未另量的读取／实现／工具探针在总elapsed内，辅助历史RSS未知不补造 |

现场选核为CPU0，实时检查其物理核／SMT和邻worker、监督器／loader；MPI1、实际数学线程1、Loader0、不加载Torch、不用GPU。旧factor只读复用，**LOCAL8_DENSE_LU_PRESENT**；原packet内部消元及40端口小LU也计费。没有新local factor／assembly、global p4 LU、T/U/R／D_L、私有audit CSR或隐藏fallback，不能称factor-free。

0.5s整树监督与自有锁，warn12/hard16GiB sampled停止、ownswap0、系统reserve及邻增长余量和原PSI保持。无可写delegated cgroup，不伪称内核连续硬限额。没有压力停止或资源重入，已清理自身后代；邻任务阶段指标不具可比性，因果影响 `INCONCLUSIVE`，不承诺零干扰。

总start为2026-10-02T23:01:15Z，heavy-stop为2026-10-03T00:16:15Z，交付截止00:31:15Z；UTC／monotonic／boot_id窗口不刷新，monotonic起点是首次UTC与随后现场配对读数的保守对齐，未冒称同时采样。一次辅助无空闲核拒绝后，一次有限复核通过；没有后台等待／自动重启。两次开发最小接线修复及全部失败保留，正式作用重放0、factor重入0。[费用／窗口](outcomes/records/resource_costs_v25.json)、[失败／未运行](outcomes/records/failures_and_not_run_v25.json)。

V6起formal研发下界从77,102.629289增至77,128.294516 s；历史辅助及每个暖链完整成本仍unknown，不清零，不把25秒诊断当48小时求解。新增数组／正式provenance／辅助证据约18.88MB；另一次保守库存把独立TMP、缓存、辅助日志和紧凑records也纳入，为27,368,703 B（约27.37MB），仍低于128MiB。完整Task042 artifacts约17.54GB低于20GiB。最终elapsed、HEAD／upstream及实际交付时刻以[回执](outcomes/records/delivery_receipt_v25.json)为准。

Ruff未安装，记录NOT_RUN，未升级环境；compileall、93项focused与原记录checker通过。full pytest、MPI2/4、FE后处理、新参考、训练、V24追加周期、旧空间试验及更大模型均按范围未运行。精确GitHub页Cache miss，无视觉证据，标 `NOT_VERIFIED`；本地公式／表格检查单列。

## 唯一下一建议

仅建议下一个review预登记**一个跨y=0的块5／7联合局部方向资格试验**，不扫描或自动实施。两个终态中块5响应进入相邻块7的范数占该源全域响应约0.76210／0.77827，支持针对这个实际耦合检查一种不同方向；不证明该接口是唯一困难或联合方向必有效。两块共3888行，单独联合矩阵＋LU显式载荷32×3888²=483,729,408 B，另计原packet、40port、旧因子重叠和装配／LAPACK workspace；设置与端到端耗时unknown，需先批准新存储／容量Gate，再以有限原作用检验新方向是否增加可消除残差，最终仍缺完整原方程／场资格。

V5测试另一p4／重叠PC，V9定位已有场误差，V23测p1作用像，V24测四周期求解；本轮新增的是当前0.7nm/p3八个完整主子块的同残差、分块最小残差上限。它排除了“在这两个末态上，仅改八个系数就能大幅削减残差”的有限假设，不能越过同空间精确LS。若以后引入NN仍需相对最佳合格非神经完整N=1成本改善20%，保留八LU时不能归功于网络内存节省。

全部授权路径完成即收口；只推送本执行分支，然后等待审阅，不merge或开始下一试验。
