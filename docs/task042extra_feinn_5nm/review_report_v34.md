# Review V34：停止同类长训练，量化现有神经空间的可达精度与投入边界

## 0. 本轮裁决

**接受V34真实复波矢学习、工程修复和完整负结果；M5数值资格、神经资源收益、0.7nm及原尺寸资格全部不通过。现有“全局稠密波库＋单块回拟合”的生产候选予以关闭，不再自动追加实/复波矢、seed、窗口、优化器或列数扫描。下一轮不是再猜一个网络变体，而是用已经保存的两个神经空间，完成一次有限的“方程最佳读出—场最佳表示—完整成本”判别。**

“不要被bug卡住”要求修好实现、保存和验收链，不等于把已经完成的科学负结果当成bug无限续训。前几轮已连续完成多尺度、旧波矢回拟合和衰减参数试验，却没有取得联合数值门。本次审阅必须作出投入决定，而不是仅给下一种调参方法命名。

```text
repository            = Rookie1234567/MyFEniCS
execution_branch      = task42extra_feinn_5nm
canonical_worktree    = /home/fenics/Projects/NN-Lab-V2
original_base_SHA     = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD  = 16eecb8dc915592e3b8420e84f690e00f28cb9a7
result_commit_time    = 2026-10-09T06:28:46Z / 2026-10-09 14:28:46 +08:00
review_date           = 2026-10-09 Asia/Singapore
previous_review       = review_report_v33.md
reviewed_response     = response_v34.md
next_campaign         = V35_NEURAL_SPACE_FEASIBILITY_AUDIT
required_response     = response_v35.md
new_continuous_cap_s   = 14400
new_nonlinear_training= NOT_AUTHORIZED
ordinary_default      = UNCHANGED
merge                 = NOT_APPROVED
```

最终目标仍为真空0.7nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet/Fourier-DtN、完整E/H/衍射/吸收，十进制2e12B整机内存且留系统余量、ownswap/OOC=0，单场必要准备到独立检查≤172800s。本轮4h是新增诊断研发上限，不是目标48h成绩。目标原尺寸50×25×140nm尚未资格化。

**本支保持神经研究身份，不接管W0/W1、原尺寸全口面、模式恢复、主线接入、传统PC、存储重构或另一套Full3D引擎。** 不修改或安排Task42、主线、dot、master及其他工作树。必要的原算子、矩阵内积和独立参考仅供本神经空间审计。本报告明确覆盖旧“数值未过就继续换表示训练”的准入习惯；旧原始文件、科学门、负结果和费用不变。

## 1. 仓库快照和已证实结果

审阅端读取了最新branch、Response V34、summary、成本记录、目录规则、仓库原则、Markdown标准，比较上次review发布后5次提交的变更清单。上版完整review从会话挂载文件读取；当前原task/目录规则沿未变blob与已读原文复核。没有SSH或工作站新运行，没有取得/重算完整大型原始数组。下表的measured来自仓库，不是本端新测量；代码与字段阅读不能替代执行端独立重算。

| M5/5nm/384hex/p3/31968独立复FE/40端口，measured | 确定性复波控制 | 梯度学习复波 | 原门 |
|---|---:|---:|---|
| 固定复线性槽/块 | 1377/246 | 1377/246 | 无新增容量 |
| 实际访问/接受 | 38/36 | 40/37 | 不是精度 |
| 非零q/kappa接受更新 | 29/35 | 37/37 | 真实学习，非仅物理种子 |
| native/augmented相对残差 | 0.144406937789 | 0.143187704283 | 各≤1e-6，FAIL |
| 独立total原残差 | 0.0684058207612 | 0.0678282677020 | ≤1e-6，FAIL |
| 散射E L2相对差 | 0.0196062878330 | 0.0180687044393 | ≤1e-4，FAIL |
| 散射H/scaled-curl相对差 | 0.0197167792543 | 0.0181871468678 | ≤1e-4，FAIL |
| 独立体吸收能量闭合 | 0.00522906780337 | 0.00483197020387 | ≤1e-5，FAIL |
| 最大逐级功率绝对差 | 0.00317414690233 | 0.00289648662723 | ≤1e-6，FAIL |
| 原点值到完整矩重建 | 6.98224054976e-14 | 1.40231035046e-13 | ≤1e-10，PASS |
| 新路线完整跨度/s | 10293.0450271 | 8368.39508737 | 含加载/失败/暂停/保存 |
| 前缀/共同资格/本轮/终验保守归属/s | 22652.7707697 | 20728.1208300 | 已加载packet口径，非冷N=1 |
| 路线同时树采样峰/B | 4196245504 | 4197736448 | 自身swap0，非连续硬峰 |

证据：[Response V34](response_v34.md)、[当前summary](outcomes/summary.md)、[全部Gate](outcomes/records/full_numerical_gates_v34.json)、[指标](outcomes/records/full_metric_index_v34.csv)、[成本](outcomes/records/cost_and_capacity_v34.json)、[修复账](outcomes/records/repair_journal_v34.json)。两候选终态source=`e1e9eaa4238d33a88a2b3adbc356d5a5f7cbcee5`，最终独立FE/保存数组checker source=`b035eea4c6fb6d697743569ecc158be356c0abc5`。发布HEAD不当数值source。

两条在预登记确认节点科学停止，随后已完成全部场/通道/功率验收。空秩SVD、分母分类、资源准入和网页问题均有保全；不应再将约0.143的原残差解释成“最后一个writer bug没有修好”。学习首节点E误差0.0180128936238，终态0.0180687044393，原残差降低时场误差仍可能变大。新增衰减不是足够的解决方案。

历史边界必须一起保留：V31学习散射E差约99.9%，V32多尺度约4.23%，V33梯度回拟合约2.615%，V34约1.807%；机制、起点与成本不同，这不是一条公平的加速曲线。V33确定性控制约1.691%，又优于V34学习终态。没有证据把当前改进归为稳定的NN净收益。

## 2. 为什么不直接安排另一次训练

当前已满足“软件链实际运行、真实参数更新、完整验收”，未满足“原方程和物理场准确”。继续只增加优化量，不改变已证实的成本/表示障碍，缺乏投入依据。本轮关闭具体生产候选是工程决策，不需要先证明所有NN在数学上不可能。

同时，现有记录尚不能精确分开两个原因：

1. 最终冻结的1377列空间，连最有利的场组合也不够准确；
2. 该空间能更好表示场，但原系数残差最小化选择了不同组合，或者数值读出仍有条件性影响。

**没有证据就不把其中任何一个写成唯一根因。** 下一轮只回答这两个问题，并检验是否有必要设计一种真正不同的神经结构，而不是把已有负结果继续包装为接近生产。

原残差最小与场误差最小是不同问题。如果同一固定空间的准确最小原残差仍约0.14，那么在这个空间里换成Galerkin、另一个loss或再调幅值，不可能使相同原残差低于其最小值。改变度量可能改变场误差，但不能绕过这个事实。必须先核实“最小值”的数值资格，不将旧一次优化的终态直接当严格下界。

## 3. A：冻结两个V34空间，先作无标签读出核验

仅取V34两个最终committed状态，按[run index](outcomes/records/run_index_v34.json)和[原数组索引](outcomes/records/raw_artifact_index_v34.json)确定实际文件及hash。不得挑best、回V32或误用V33/监督状态。两个空间各1377槽，分别冻结其q、kappa、窗口、T、原保留列掩码、owner/MPC和单位。

用U表示**当前冻结点值网络经过完整Nédélec矩得到的线性幅值列**，不是全FE空间，也不是该神经函数族的所有可能参数。c=Ua。

A不读取reference_state。复用已保存U/AU/QR和健康重建证据；核查3个非零复数组合的实际网络/完整矩/原A作用≤1e-10。无需重新生成所有指数或重复4h学习。逐列原A刷新只在已证实旧QR失效时进行一次，不能因为换版本号默认刷新。

```math
 a_r=\arg\min_a\|AUa-f\|_2,\qquad r_r=f-AUa_r.
```

使用原秩揭示QR/小R SVD、固定rcond=1e-12。报告全部奇异值范围、保留秩、列尺度、实际a范数、小/全作用配对以及一阶最优性。原残差仍必须重新作用A计算，不只读QR预报。小系统之外不形成全局Maxwell矩阵、不求逆、不生成Krylov完成器。

必须写清原1377列、稳定保留空间、截断方向的区别。截断子空间里的最小残差是对更大空间最小值的**上界**，不能反过来当全1377列的排除证据。若满秩与误差界无法可靠确认，标`RANK_OR_OPTIMALITY_UNRESOLVED`，保留旧数值FAIL但不宣称数学不可能。

若发现真实读出错误，同批最小修复、定向测试，再从同一个无标签U/A/f重算一次a_r并冻结；不能借机继续q/kappa训练、增加列或更换rcond。错误诊断、旧费用和旧状态全部保留。只有这条无标签读出有可能获原M5数值资格，不能让后面的标签投影冒充它。

## 4. B：独立参考暴露的最佳场表示审计

### 4.1 这项工作能回答什么

在q/kappa/窗口全部固定后，直接问“即使知道准确参考，最有利的幅值能表示多准确”。这是一个线性最佳逼近诊断，不是又一次NN训练，也不提供PDE-only求解成绩。它与旧V5的195维tanh末层问题不同；此处检查V34各1377槽的复指数空间，不重新做旧V5。

只读取已验证V1同p3散射参考，SHA256=`0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7`。不得重算MUMPS参考、读取p4/p5替换基准或把total场当散射标签。原参考、mesh/MPC/moments及场内积身份共同校验。

沿用本任务原正定H(curl)内积G，ell=5nm，与原物理单位一致：

```math
 \|v\|_G^2=\|E_v\|_{L^2}^2+\ell^2\|\mathrm{curl}E_v\|_{L^2}^2,
 \qquad a_G=\arg\min_a\|Ua-c_{\rm ref}\|_G.
```

```math
 \epsilon_G^2=\frac{\|Ua_G-c_{\rm ref}\|_G^2}{\|c_{\rm ref}\|_G^2}
 =\frac{d_E^2\epsilon_E^2+\ell^2d_C^2\epsilon_C^2}{d_E^2+\ell^2d_C^2},
 \quad d_E=\|E_{\rm ref}\|_{L^2},\ d_C=\|\mathrm{curl}E_{\rm ref}\|_{L^2}.
```

本M5的mu_r=1，原H_code和scaled-curl的相对误差相同。上式直接说明：若完整冻结空间的可靠最佳epsilon_G大于1e-4，则不可能同时使其E与curl相对误差都≤1e-4；反过来epsilon_G很小也不自动使每个场、样点、通道都过门。仅在满足完整空间与最优性限定后才能作这个判断。

### 4.2 算法和防止伪证明

只需G乘法，不需要G逆或全局G因子。优先复用已有冻结特征G投影组件；可用带列归一化、两遍重正交的G-QR配合小R的SVD。严格complex128，保存可逆的列变换和幅值反映射，不直接求逆U*GU正规方程，不形成N×N投影。参考只进入投影右端项；基、选列和秩规则不能由参考误差挑选。

G-QR的正交基记V。以下恒等式为精确算术下的最优性核验依据：

```math
 M=V^*GV,\quad e=c_{\rm ref}-Vb,\quad s=V^*Ge,
 \qquad e_{\min}^2=e^*Ge-s^*M^{-1}s.
```

若有可信的rho=norm(M−I)_2<1，可用norm(M−I)_F作为上界，未完成最优化最多还能减少norm(s)_2^2/(1−rho)的误差平方。这里只允许解小M，不是全局G逆；禁止把e*Ge与接近相等的两个大数相减作为唯一误差计算，必须独立形成场差再积分。

最小资格：G正交缺陷≤1e-9，原U与保存变换的重构≤1e-10，归一化最优性缺陷≤1e-9，独立q15/q30场内积复核≤1e-8；近零量另报绝对值/分母。3个复组合和小型独立白化QR/SVD验证必须通过。

这些是浮点数值资格，不是区间算术的严格证明。需要报告最优性缺口、积分/重构误差估计与距离1e-4门的余量。误差与门过近、截断丢掉可能有效方向、反变换严重相消或无法控制误差时，一律`INCONCLUSIVE`。不得把“截断后拟合失败”叫作原网络数学上无解；不通过降低秩门、强制高精度生产或加ridge来制造明确结论。

每个空间仅一个固定G投影，不新增L2-only/curl-only/加权网格扫参，也不做非线性监督拟合。两份投影的实际幅值重新写回独立diagnostic模型，用原点值→完整矩路径复核；q/kappa/窗口/T的hash必须不变。

### 4.3 标签隔离和依赖顺序

A的无标签终态必须先冻结并封存，B之后不能再更新或调参A。B和其输出目录、manifest及检查器必须标：

```text
reference_used_for_coefficient_fit=true
reference_used_for_training=true
pde_only_solve=false
production_initialization_allowed=false
pde_only_solver_qualified=false
official_candidate_results=false
scope=FROZEN_NEURAL_SPACE_ORACLE_DIAGNOSTIC
```

即使B得到很好的场，也不是无标签神经求解、不能接回旧C、Task42或0.7nm。禁止把c_ref、误差场、oracle幅值加入U作为“新学的方向”。

## 5. C：一次独立审核，给出有限且明确的结论

复用原FE compare-only，不重求参考。对A无标签新读出及B oracle分别完成实际模型/producer重建、全native/增广/独立total残差、total/scattered E/H/curl、原六点、四类完整40通道、R/T/A_balance/A_volume、逐级功率、材料/界面区域、MPC/端口恢复和独立求积。

A若与旧c/r逐位一致，复用旧完整Gate并仅核对身份/新增最优性证据；不为重复报告再跑完整后处理。B的新场须实际比较。各空间分别消费、清场，不叠加常驻数组。

严格门保持：原方程各1e-6；E/H/curl/六点及每一类完整复通道向量1e-4；R/T/A/A_volume误差和独立能量1e-5；逐级功率1e-6；模型重建/MPC/端口1e-10；求积1e-8。不要发明所有近零单通道逐项相对1e-4门。功率只有A通过联合资格才可能official；B永久diagnostic。

| 实际结果 | 允许结论 | 不允许结论 |
|---|---|---|
| 满空间最佳场误差可靠大于门 | 当前冻结波形连最佳幅值也不足；今后必须改变表示或有效空间 | 所有NN、所有q/kappa均不可能 |
| 最佳场显著更好，但最佳原残差仍不合格 | 当前目标与场误差存在显著差异；同一空间换loss不能低于原残差的最小值 | 换个loss就能让原M5自动通过 |
| A发现并修复真实读出错误，联合Gate通过 | 仅对该无标签保存空间授有限数值资格；完整前缀成本继续计入 | oracle是solver；小模型是原尺寸0.7nm |
| 秩/稳定性/数据不够 | 数值归因尚不能定，但已有失败与停止生产投入的决定仍成立 | 无限续训直至诊断变得有利 |

所有输出都不自动解除当前生产候选关闭。本轮不再设置“修好bug后追加4h训练”的隐含分支。数值通过与有竞争力是两个决定。

## 6. D：把0.7nm/2TB/48h改成真实准入约束，不再自动消耗下一轮

从现有记录生成一页candidate decision，不建设新Full3D组件。明确三个事实：

- 目前没有M5联合通过的该类学习结果，也没有0.7nm三维神经pilot；原尺寸目标未通过。
- 必要固定前缀10186.178641493432s不能从新流程里消失；V34学习路线保守加载packet总归属20728.120829955675s约5.76h，完整冷N=1仍UNKNOWN。历史合格传统672.462895s/1245822976B只是旧参考，不据此虚构新的同精度倍率，但不能把当前多小时未合格流程宣传为更省资源。
- 全局U/Q基础存储为32Nm B。N=1e7、m=1377时为440640000000B，N=1e8时为4406400000000B；两者只是形状推导，不是实际目标DoF/RSS。不能仅因前者小于2TB就忽略原算子、暂存、端口、因子和系统余量；也不能据后者虚构实际目标N=1e8而宣布所有NN容量no-go。

下一种神经生产候选必须在训练前同时说明：它实际删除哪一块已测成本；必要数据/训练对单场N=1如何计费；为什么不重复已否决的固定空间优化/神经校正/压缩；其常驻对象与未知量规模如何增长；何种最小试验能否决它。不能借“未来大量反演查询”摊掉当前单场训练，也不能把传统迭代器成功计成NN收益。

本批**不授权新的神经架构实现或长训练**；最多提交一个依据A/B结果的明确候选概念和计算图/成本条件。没有证据支持时写`NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE`，不要编一个新名字续跑。本支保持神经方向但当前求解族冻结；一般Full3D主线由其自身任务推进，本review不向它分配工程工作。

本轮不运行0.7nm、p4/p5/p6、h细化、端口扩展或新材料case，也不注册空的0.7nm输入以造成推进印象。未来重新开放神经计算须针对明确不同机制，而不是修改文件版本号继续原扫参。

## 7. 连续执行、修复与资源

新总窗14400s从首项实际准备起计；A/B的正式数值合计不超过7200s，最终至少留1800s审核/交付。各空间不超过1377列，单个活动块/流式读取≤8列。软时间不足先完成学习空间，再完成强控制，未完成明确not_run；不能用原16h余额或另一窗口续上。

这是一次有数值内容的决策审计，不在接口测试、首次异常、一个commit处交棒。schema、路径、复数序列化、QR、映射、角色分类或保存错误同批最小修复、定向测试并续接健康数据，不设“第三个bug必须停”的规则。预算/容量/不可恢复的数据/ABI权限/安全硬条件仍须收口；没有无上限重试。不要把数值停滞或不利结论叫作bug。

CPU-only/MPI1/math及Torch线程1，一个现场合格物理核；数值warn12/hard16GiB，含临时规划≤12GiB，轻检查≤2GiB，ownswap/OOC=0。保留原系统余量max(128GiB,10%有效总内存)+384GiB邻增长+本任务预算、原PSI60s/cpuset/SMT和最新样本规则。成功准入计总墙钟，不套旧1200s观察池；真正拒绝后额外前台等待≤900s，不后台抢跑或改邻任务。启动磁盘自由≥50GiB，本批新增artifact≤8GiB，旧健康数据不删除。

复用持久launcher/watchdog/one-run入口，不重写调度框架。QR/场内积阶段明确numeric角色，不能误配2GiB轻树；整个进程树受监督，150s前收口、至少120s安全保存。断连先识别同一作业，不启动副本。缺数据先在原索引声明的本任务副本寻找，找不到就如实受限，禁止为补标签重新训练或重算大参考。

## 8. Git、证据和一次性交付

开始先确认无活跃本任务run、branch/HEAD/worktree/锁，再只对本分支精确fetch和ff-only。不新clone/分支，不reset/stash覆盖不明修改，不amend/强推/merge。读取根及目录AGENTS、仓库原则、task、上版review/response和本报告；原task/readme历史“当前”不凌驾于本裁决。

先实现最小opt-in审计入口、定向测试，clean实现commit后运行。数值核心在合适src模块，runner只是编排；可复用旧冻结特征投影，但不得复制另一套网络训练器。建议新输入如下（先实现/validate，不声称当前已存在）：

```text
input/task042extra_feinn_5nm/v35_space_audit_checks.dat
input/task042extra_feinn_5nm/v35_unlabelled_readout_audit.dat
input/task042extra_feinn_5nm/v35_labelled_field_oracle.dat
input/task042extra_feinn_5nm/v35_space_decision_compare.dat
```

逐项使用`python scripts/launch_task42extra_durable.py <one-run.dat>`，由现有wrapper选择正确FE/ML/纯数组环境并调用`scripts/run_case.py`；每项清场后再下一项，不能并发启动全部。

所有run绑定input_original、resolved_config、run_manifest、input/physical/source hash、run_summary、环境/MPI/线程/资源和artifact hash。大列库、正交基和场留ignored；Git只交紧凑数值、分子/分母、秩/稳定性、输入身份、修复和资源记录，不复制多份万行JSON。

必交`response_v35.md`、`outcomes/neural_space_feasibility_v35.md`和`outcomes/neural_route_decision_v35.md`；records至少包括design、snapshot_identity、unlabelled_optimality、field_oracle、rank_stability、joint_gates、cost_capacity、repair、run_index及tests。README/summary页首明确`CURRENT_DENSE_WAVE_SOLVER_FAMILY_CLOSED`和oracle标签，旧结果全保留；同步本分支progress、模型总账、tests/changed_files。

执行端必须回答：当前固定波形的最佳场精度究竟多少？原残差最优性是否可靠？数值秩是否让结论受限？失败主要能排除什么、仍不能排除什么？在单场成本条件下是否有证据支持新的神经生产候选？不能只交测试通过数量或一个“仍待研究”。

发布端只检查文本和小型合成投影公式，不能代替工作站实际资格。GitHub视觉失败如实保留；有限补查关键新页，网页服务错误不阻断数值，不重渲染所有历史。只推`git push origin HEAD:refs/heads/task42extra_feinn_5nm`。完成有限审计及投入裁决或触发真实硬出口后，一次报告精确HEAD、显式tracking/ahead-behind、clean与自身清场。

## 9. 方法依据和边界

[原FEINN论文](https://arxiv.org/html/2411.04591v2)是历史方法来源，不为本问题授收敛保证。本轮QR/SVD秩处理参照[LAPACK线性最小二乘](https://www.netlib.org/lapack/lug/node27.html)及[SciPy lstsq](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.lstsq.html)。SciPy的cond决定有效秩；依赖版本现场记录，不升级到网页版本。文档并不证明本列库满秩，必须实测。

**最终结论边界：当前数值配置失败且不具备已验证资源竞争力；没有证明所有FEINN/NN无解。这次实质任务是结束无依据续训，拿到可复核的表示与目标差异判断，而不是再用一种未经验证的新方法维持计算。**
