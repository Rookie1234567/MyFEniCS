# Review V4：接受完整重放终态，转入固定隐藏层的线性输出层诊断

## 0. 决定、仓库身份与本批 blocker

**接受 Response V4 的完整检查点、独立场复验和固定预算未达标结果；保存预留不足作为执行偏差保留，不授予 solver、生产或合并资格。下一批不追加长时间 L-BFGS，也不扩网；只在 V4 最终隐藏层固定后，做一次参考已暴露的线性输出层最小二乘诊断。**

本批回答：现有隐藏层生成的特征，是否已经允许比当前约1.4%误差更好的场，而联合优化尚未找到合适的最后一层？它把**固定特征下的线性优化**与**隐藏特征本身的改进**分开。属于表示/优化诊断，不是新 Maxwell 预条件器；不把 FREE 成为强求解器设为无限前置要求。

```text
repository               = Rookie1234567/MyFEniCS
execution_branch         = task42extra_feinn_5nm
worktree                 = /home/fenics/Projects/NN-Lab-V2
review_date              = 2026-09-30
reviewed_HEAD            = 653acdf15e8484ce3df211ca2dfb8114a107f315
latest_commit            = docs(task42extra): bind GitHub rendered view and final V4 resource ledger
original_base_SHA        = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review          = review_report_v3.md @ 4dc7c38b60acf2a5ee3d9c6b9770b084a874fb04
latest_response_reviewed = response_v4.md
V4_training_source       = 538c6320679d9a3ce3efe5e6d6ebef062963f601
V4_postprocess_fix_source= c8a057a46645542aaa17a38b78e64c6add80cb68
next_batch               = V5_FROZEN_HIDDEN_LINEAR_READOUT_DIAGNOSTIC
new_route                = FEINN-FROZEN-HIDDEN-READOUT-G
response_required        = response_v5.md
solver_qualification     = NOT_QUALIFIED
master_merge             = NOT_APPROVED
```

最终目标仍为约2 TB整机物理内存内、0.7 nm、任意非可分三维周期单胞的准确 Maxwell 解。当前为小型5 nm M5上的监督研究，不替代通用 Full3D、matrix-free 与可扩展 iterative 主线，也不证明目标尺寸5 nm或0.7 nm/48h。

本次实际读取最新目录、task/review/response/summary、逐检查点CSV、资源及run索引、网络与边界装载代码，并核对上次review后的4个提交。未SSH核查工作站、未重新下载ignored数组或运行M5。本文measured指仓库记录，公式和bytes为推导，下一批全部not_run。本地小型复数代数检查不是M5资格证据。

先读根/目录AGENTS、[仓库原则](../repository_work_principles.md)、[task](task.md)、Review V1–V3、[Response V4](response_v4.md)、[summary](outcomes/summary.md)及本review。目录未发现其他补充任务书。本review仅授权下述固定隐藏层输出层重求及新增stage，覆盖旧合同对此操作的限制；其余物理、标签隔离、历史保护和资源规则保留。旧task/review/V1–V4证据不改。

## 1. 最新事实与审阅边界

依据：[逐检查点曲线](outcomes/records/durable_audits_v4.csv)、[详细结果](outcomes/durable_replay_v4.md)、[run index](outcomes/records/run_index_v4.json)、[最终资源账](outcomes/records/resource_costs_v4.json)。误差均无量纲；RSS为采样同时整树，物理量是同p3参考比较。

| measured量 | Adam500锚点 | V4最终已提交状态 | 判断 |
|---|---:|---:|---|
| G场误差 | 0.2008211341 | 0.01387169130 | 明显改善，仍未达部分见证0.01 |
| 散射E L2 / scaled-curl | 0.1620127280 / 0.2017046510 | 0.01325124766 / 0.01388700270 | 仍远高于严格1e-4 |
| native / augmented残差 | 14.2634632 / 14.2634632 | 1.608844720 / 1.608844720 | 严格1e-6失败 |
| 能量闭合 / 最大逐级功率差 | 0.0417012 / 0.0130081 | 0.001183989956 / 0.0003513448473 | 严格1e-5 / 1e-6失败 |
| 参数→完整c / q30→q15 | 0 / 2.8584e-12 | 0 / 8.5141e-13 | 仅支持身份和求积，不是p/h收敛 |

V4执行2129次新完整closure，final恢复到2122次已提交边界，93个完整L-BFGS外层step；7次未接受试探仍计费。第94号持久文件是终态保存编号，不代表完成第94次优化step。旧V3中断/丢失历史继续原样保留。

曲线在新closure1509、1801、2122处的E_G分别约0.017775、0.015652、0.013872，仍下降；不能用时间停止证明达到表示下限。也不能因为接近1%就降低预登记阈值或承诺再跑一段必然达到0.1%。场误差约1.4%而native约1.61同时成立，不是矛盾；不同范数与分母下不能用二者比值冒充条件数。

执行保全在所测路径成立：参数及匹配优化器落盘、原子写入和独立复验均有证据。但C1从worker导入后计时，侵占原至少120s保存预留；整launcher为10690.413s，未超10800s，退出后剩109.587s不能冒称满足原预留。C2改为launcher单调时钟及150s收口，仅经targeted测试。接受数值终态，**不追认预留规则通过**；下一批在短任务中验证时间传递，不为此重跑三小时训练。

R1峰764751872 B，含浏览器全批采样峰2054807552 B，均为自身swap0的已测范围；不能把前者叫整个会话峰。新fit无G因子/Gsolve/Maxwell因子。共享工作站时间不用于宣称方法加速，tmux管理开销继续单列。

## 2. 下一方法：固定特征，直接求最后一层

### 2.1 它改变哪一步

[CoordinateField](../../src/solvers/feinn_torch.py)使用三个64宽tanh隐藏层和最后一个64→6线性层。冻结V4最终隐藏层与坐标buffers后，64个实特征函数固定；加常数1表示bias，共65个特征。每个电场分量用65个复系数，合计**195个复未知量，等价390个实输出层参数**；其余8576个实隐藏参数全部冻结。

```math
 h(x)=(h_1(x),\ldots,h_{64}(x),1),\qquad
 E_s(x)=\sum_{j=1}^{65}a_{sj}h_j(x),\quad s=1,2,3.
```

原Nédélec矩、Piola、orientation和MPC映射为复线性，故存在固定矩阵Phi，使完整散射系数c=Phi a，Phi大小31968×195。最后一层6行按现有reshape规则两两组成每个分量的实/虚部，bias不可遗漏；不能错按前三行实部、后三行虚部。

这不是训练一个更大的网络，不是自由优化31968个复FE系数，不是从准确场提取POD基。Phi只由**已有隐藏权重和原插值规则**构造，禁止把参考场、参考误差或A逆的输出额外塞成一列。

以V4末层系数a0和场c0为锚点，求一次线性修正：

```math
 d=c_{\rm ref}-c_0,\qquad
 \delta a=\arg\min_b\frac{(\Phi b-d)^*G(\Phi b-d)}{2d_{\rm ref}},\qquad
 a_1=a_0+\delta a,\quad d_{\rm ref}=c_{\rm ref}^*Gc_{\rm ref}.
```

c_ref仍是已暴露的同p3准确散射标签。这一目标没有PDE残差A，没有G逆；只需原G的稀疏乘法及小型线性代数。用修正形式保留原场作为可行点，避免数值截断时把原场也丢掉。不得将重求后的a1与旧L-BFGS历史混装为可续训checkpoint；本轮没有任何非线性optimizer step。

线性/非线性系数分开处理可参考[Dong–Yang的VarPro研究](https://arxiv.org/abs/2201.09989)，但本轮只做固定特征的一次线性子问题，不实现完整VarPro或引用其算例为本模型保证。兼容插值仍来自[原FEINN论文v2](https://arxiv.org/html/2411.04591v2)；这是独立诊断扩展，不是原样复现。正定矩阵内积下的QR方法可参考[Imakura–Yamamoto](https://arxiv.org/abs/1703.10440)；这里的complex128/Hermitian实现必须独立验证。

### 2.2 为什么有判别力，也有哪些局限

若稳定求得的最优输出层显著改善场，说明**这份隐藏特征内还有可利用的线性组合**，V4末层尚非该子问题最优。若改善很小且子空间最优性检查成立，说明仅调整此隐藏层的最后一层不足；仍不能否定改变隐藏层后的同一网络架构，更不能否定全部FEINN。

存在秩截断时，只能称“已声明、可数值分辨的固定特征子空间中的投影”。实际达成误差是网络可实现误差的见证，不是整个网络类的误差下界；若数值秩/权重还原不可信，则不作容量结论。禁止以参数数量小于FE自由度作为不可表示证明。

## 3. 冻结数据、物理与标签

模型不变：M5，真空5nm、Si/air、grazing1°/phi0/s、384hex、h1.25nm、p3/q15、31968独立复FE、2082slave、完整40端口；双Floquet、layered背景、Fourier-DtN、材料表与约束顺序不变。原G使用ell5nm；不改权重，不引入V2的D作为新的FE变量，不做p4或目标尺寸计算。

V4末态只作为本次特征和原输出层锚点。核对文件字节hash，实际路径从[run index V4](outcomes/records/run_index_v4.json)取得；不用last_trial代替final，不回Adam500、不选最佳历史checkpoint。

```text
V4 frozen_checkpoint.npz = e33a2c9eafb50639a36555e159895d62617feda7e4831238a7868887700f9363
V4 durable final .pt    = e09b94364837bdb72714f7c229d19993836072dd035c85249bfc19376a44a790
native packet          = 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
Gram file              = 2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9
moments q15            = 0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e
reference state        = 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7
material table         = 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
```

只用本任务hash验证的本地checkpoint；不反序列化任意外部pickle。加载durable模型/buffers并与NPZ参数及c配对，分别锁定hidden、末层、buffers、master顺序、参考标签和新Phi的hash。缺失/损坏则ARTIFACT_BLOCKED，不重训或重新MUMPS求参考填补。

所有新输入、checkpoint、result和表格保留：reference_used_for_training=true，pde_only_solve=false，production_initialization_allowed=false，pde_only_solver_qualified=false，official_candidate_results=false。只重求最后一层也属于标签训练。新权重不接回旧无标签路线、Task042或0.7nm；独立代码审核不等于独立数据验证。

## 4. S0：最小资格及列构造

先复用V4的环境、算子、求积和保全证据，做当前changed paths的定向检查，不重跑E0/E1/P0/R0整套。新计时协议在小dummy阶段验证launcher起点、模拟导入延迟与收口，覆盖“启动时已没有保存余量就不开始数值工作”；无需真实三小时求解。所有自身进程仍走已合格持久launcher/监督链。

在独立ML进程加载V4 final，重新生成c0、E_G及原native并配对原记录；隐藏参数与buffers不得改。取最后tanh后的h64，按最多8个cell及有界特征列批量计算，应用原完整矩映射得到Phi。允许缓存这一次固定特征，禁止重复195次完整网络前后向来伪装必要训练成本，也不建立全域autograd图。新增提取函数独立实现，原CoordinateField/CompleteMomentMap默认数学不变。

Phi只需99,740,160 B（约95.1MiB，derived），不是31968平方的全局矩阵。允许有界Phi、G Phi及Q等工作数组；统一预估/监测，不能把这一个payload当整树RSS。不形成稠密G、global Maxwell矩阵、全Jacobian或A* A。

必须检查：原a0、至少3个固定非零复系数向量及纯虚方向，Phi a与原网络真实forward→完整矩的c相对差≤1e-10；原a0配对目标≤1e-12。系数测试种子421501，不更新真实锚点；包含bias、全部三分量和内部矩。对一个非零向量在batch1/8配对≤1e-10。缺相位、共轭、owner或实虚顺序问题先修复，不启动优化碰运气。

另做小型复数SPD G的最小二乘测试：满秩、重复列、近相关列、不同列尺度、纯虚系数；用小型Cholesky白化后的独立QR/SVD解核对所得场。允许小合成矩阵factor，仅作验证；实际M5禁止新增G因子。测试不能只验全零或只比较同一实现两次。

## 5. S1：一次稳定的G加权线性投影

### 5.1 不能再次把问题恶化成盲解正规方程

不直接形成并求逆Phi*G Phi作为正式求解路径。隐藏特征可能接近相关，正规方程会放大数值秩判断困难。首选**列归一化、带确定性选主元和两遍再正交的G内积QR**，随后在最多195列的小矩阵上作SVD/秩揭示最小二乘；这里的完整向量是FE场系数，内积用原稀疏G，非原始欧氏内积。

```math
 s_j=\sqrt{\mathrm{Re}(\phi_j^*G\phi_j)},\quad
 U=\Phi\,\mathrm{diag}(s_j^{-1}),\quad U\Pi\simeq QR,\quad Q^*GQ\simeq I.
```

零列显式记录；非有限/负范数不得用abs或随意epsilon掩盖。归一化列按G剩余范数选主元，同值取最小原列号；至少两遍再正交，候选剩余范数用实际G作用核查，不能只用易抵消的范数差。固定QR可分辨门限1e-12（归一化列尺度），小R的SVD截断固定rcond=1e-12，不根据参考误差扫描门限，不加ridge凑稳定。

若小R的SVD还截去方向，投影Q相应乘保留的左奇异向量，得到Q_eff；记录两阶段rank、奇异值、丢弃列/方向、归一化与置换，所有最优性陈述只针对最终保留空间。解小问题R z约等于Q*G d并反变换得到delta a；实际保留空间内的目标场修正为Q_eff Q_eff*G d。**最后必须写回原网络末层的实/虚权重和bias**，不能只交付Q空间中的FE向量而跳过网络可实现性。

这是一项固定规则的线性代数求解，不是新一轮Adam/L-BFGS或full-FE Krylov。允许这最多195列的诊断basis及小型分解，不推广为目标规模存储策略。总G作用计数按作用列数统计，包含构造/正交/验证，≤2500；批量matmat不能计作仅1次以隐去工作量。达到预算或数值不稳停止，不切换新分解路线继续试到通过。

### 5.2 最优性和回写检查，必须独立重算

以下为本批研究实现Gate，不替代物理Gate。设范数G由实际G作用计算，d_ref仍是原参考场能量。

| 检查 | 预登记要求 |
|---|---|
| 保留空间正交性 | norm(Q_eff*G Q_eff−I)_F≤1e-9 |
| QR表示缺陷 | 归一化U的G-Frobenius相对重构差≤1e-9；秩截断另报告实际尾部 |
| 最优性 | norm(Q_eff*G(d−delta c))/sqrt(d_ref)≤1e-9；另报所有归一化原列的残差相关性 |
| 回写网络 | 原网络重建c1与c0+Phi delta a、与投影场的G相对差各≤1e-9，欧氏相对差≤1e-10 |
| 不增性与勾股配对 | E1²≤E0²+1e-10；abs(E0²−E1²−norm(delta c)_G²/d_ref)≤1e-8 |
| 冻结规则 | hidden/buffers字节hash完全不变；只有390个实末层参数允许改变 |

投影field与实际权重产生的field不一致时标READOUT_RECONSTRUCTION_UNSTABLE，不接受“线性代数中误差很好”的假网络结果。记录delta a/末层权重范数、最大幅度、列尺度和取消误差；不能通过改变q、裁剪权重或放松分母掩盖。

报告gamma=norm(delta c)_G²/norm(d)_G²，即该保留空间能去掉的当前误差能量份额；只有上述配对成立时才解释。gamma不是整个网络类的表达能力指标。浮点rank不清楚时标NUMERICAL_SPAN_UNRESOLVED，保留可实算输出，不说得到数学全空间最优值。

## 6. S2：冻结后独立复验与如何决定下一步

S1产生一个最终候选，保存末层、完整模型、hidden/buffer/Phi/rank/参考身份和c1，独立目录不覆盖V4。新模型是parameter-only监督诊断状态，旧L-BFGS optimizer不得随它标成一致恢复点。

复用ML参数→q15/q30重建及独立FE compare-only。只复用V1准确参考，不新增MUMPS symbolic/numeric/solve、G factor或全局Maxwell CSR。原q30仅最终一次复核（相对q15≤1e-8）；不改q15后重求。检查原背景、材料、端口与master顺序，按原标签策略固定official/PDE-only为false。

至少比较V4与新末层：E_G、total/scattered E与scaled-curl、完整H_code及六点复E/H、原total/真实出射/scattered各40级复值和明确分母、R/T/A_balance/A_volume、能量与逐级功率，原air/substrate/grating/interface-near区域误差。物理评价必须来自**回写网络真实重建的c1**，不是稳定性检查没通过的理想投影场。

严格数值诊断标准继续为：native/augmented/total原方程≤1e-6、场及复通道≤1e-4、R/T/A/A_volume与能量/吸收差≤1e-5、逐通道功率≤1e-6、MPC/恢复≤1e-10。不能用A_balance定义制造守恒；不能拟合全局相位。所有结果即使达标也只是监督重构，不是新无标签solver。

| 最终观察 | 允许结论与下一步边界 |
|---|---|
| E_G、散射L2和scaled-curl均≤1e-3 | REPRESENTATION_WITNESS_POSITIVE；本固定网络存在该精度的已验参数，后续PDE训练需另审 |
| 三项均≤1e-2但不满足上行 | PARTIAL_REPRESENTATION_WITNESS；不把1%当物理合格 |
| 稳定投影显著降低误差但未到门限 | 记录实际gamma/降幅，说明原末层还非固定特征最优；不据此自动继续VarPro |
| 稳定投影几乎不改善 | 此可分辨特征空间中仅调最后一层空间有限；不证明改hidden/架构无用 |
| rank、正交、回写或求积不可信 | NUMERICAL_SPAN_UNRESOLVED或对应失败，不作容量结论，不扫描截断/正则化 |
| 场变好但native更差 | 同时保留，不按拟合目标挑有利指标；原物理约束仍是独立障碍 |

这是原监督表示试验的一个受控分解诊断。即便有正信号，本批也不授权更新hidden、从新末层再跑L-BFGS、PDE loss微调、更多seed/宽度/载波或给新物理工况提供预训练权重。

## 7. 资源、时间与运行保全

**本批全部新增有载及有界辅助≤2h，同时受原16h剩余约束；S0≤20min，唯一真实列构造/投影主阶段≤1h，其余用于复验与交付。** V4最终保守累计44119.848638203344s，原16h剩13480.151361796656s；现场补计后续费用，不以summary早期快照重置。旧中断3284s和全部重放费用保留；复用G装配/参考的新实耗为0，历史归属另列。

数值仍CPU-only、MPI1、数学/Torch intra/inter-op1、空闲物理核、warn12/hard16GiB、自身swap0；轻tests/浏览器≤2GiB。系统余量max(128GiB,effective_total×10%)＋邻增长至少384GiB＋本任务预算；自由磁盘≥50GiB，artifacts总量≤20GiB。No OOC、无GPU，不修改邻任务环境、进程、锁、affinity、watchdog及全局swap/BLAS/CUDA配置。

小矩阵SVD的workspace、Phi/G Phi/Q、原G CSR、临时cell特征和进程树均计入；列/核/矩阵payload不等于RSS。预计主工作数组可有界，但不能把预测写成测量。无cgroup委派继续约0.5s整树采样，tmux服务器单列管理口径，不承诺零干扰。

使用当前已修正的launcher单调时钟，从准入/启动起传递deadline，包括导入与加载。主阶段至少150s前停止新增长算子工作，保留至少120s安全收口；记录实际起点、cutoff及退出余量。已超安全窗口不开始下一QR步骤/分解。硬资源紧急停止优先，不为完成audit越限；未存最终态就如实controlled_stop/blocked。

持久终端承载整个launcher＋watchdog＋worker，不把worker移出监督。阶段锚点、完成的Phi及最终参数原子保存、hash绑定，长分解有heartbeat。只准一次真实主阶段启动；客户端断开时重连同一受监督作业，不重复运行或无限续启。权限/安全策略不绕过，资源不足完成可做的轻工作后交付。

## 8. 改动、证据与Codex收口

可新增`src/solvers/`中的固定特征提取、G加权QR/小型读出诊断模块，及最小one-run opt-in接线、测试与checker。原网络forward、完整矩、A/G/材料/背景默认含义不改；新数值算法不塞在benchmark脚本里。FE进程禁止因共享helper顶层import Torch。只读取本工作树必要artifact，不扫描邻任务大日志，不重装环境或full pytest。

同分支安全fetch/fast-forward；共享origin.fetch未映射本分支时使用命令级精确refspec与显式tracking ref，不能将无法解析的@{upstream}当通过，也不修改共享配置。没有本任务活跃数值作业才提交/变更HEAD；先clean实现commit再运行，后续文档HEAD不冒充运行source。不新clone/分支、不amend/强推、不merge master或其他支线。

建议新stage输入（实施前不存在，Codex先实现并资格化）：

```bash
python scripts/run_case.py input/task042extra_feinn_5nm/v5_readout_checks.dat
python scripts/run_case.py input/task042extra_feinn_5nm/v5_frozen_hidden_readout.dat
python scripts/run_case.py input/task042extra_feinn_5nm/v5_readout_reconstruct.dat
python scripts/run_case.py input/task042extra_feinn_5nm/v5_readout_compare_only.dat
```

按既有FE/ML分环境activation运行，不把四条放进一个未切换环境的裸shell。每个dat是一项明确阶段，新index/输出不覆盖V1–V4；正式manifest保留输入、resolved、source、物理/模型/材料/模式/Gram/标签/检查点和资源hash。

最小交付：`response_v5.md`、`outcomes/frozen_hidden_readout_v5.md`，及`records/readout_design_v5.json`、`readout_checks_v5.json`、`readout_projection_v5.json`、`readout_comparison_v5.csv`、`run_index_v5.json`、`resource_costs_v5.json`、`gate_decisions_v5.json`。大Phi/Q、模型及场留ignored；Git只提交紧凑统计和hash。summary追加V5、保留历史，同步本分支进度、模型总账、test_summary和changed_files。

提交计划：C1冻结身份/计时测试/线性映射与合成核验；C2真实有界投影与独立回写复验；C3原始字段checker/结果与Response V5。明确实现bug允许一次最小修复及受影响重试，费用照计；数值秩不稳或拟合无改善不是擅自扫参数的理由。原V4计时偏差不删，新短stage验证不能追认旧run通过。

Response V5首先给准确branch/HEAD/source/worktree及资源准入，再回答：究竟固定了哪些参数；195复列是否覆盖原末层；是否用了参考构造额外特征；秩/正交/回写与最优性是否成立；G误差能量下降多少；真实网络场及原方程是否改善；是否只是监督重构；目标规模与0.7nm仍有哪些not_run。给一个基于结果的下一最小建议，不自动实施。

新Markdown遵守fenced math与表格规则。检查本地结构及新review/必要新增页的GitHub渲染，浏览器费用入账；不可访问如实blocked，不重渲染全部历史。本次发布端的容器无法直接访问GitHub渲染页，不能以文本回读代替视觉PASS，需Codex补查。

只推送`git push origin HEAD:refs/heads/task42extra_feinn_5nm`，随后停止等待review。新拟合参数不能变成production默认，本轮没有merge approval。
