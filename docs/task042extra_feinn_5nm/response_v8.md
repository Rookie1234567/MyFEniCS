# Task42extra Response V8

本批 A–E 完整执行。p4装配瓶颈通过有独立核验的等价原方程装配解决，唯一新增参考合格；p3/p4变化显著。两条从零C路线均未解出原p3方程：phase的终态散射场误差约0.2135，而plain约0.9989，但phase的native残差1.3193大于plain1.0554，不能将较低loss当求解通过。条件D自动完成；phase三项场误差仍略高于1%，plain约2.5%，均未达部分表示门限，表示与拟合优化仍未决。本轮没有真正安全/权限/资源阻塞，也没有候选故障重启。

## 1. 实际完成与验收

保持原M5/5nm/Si-air三维缺口、384hex/h1.25nm、双Floquet、40完整端口、原材料/背景、体和DtN q15。A仅p3→p4；B–D保持p3全部31968独立复FE、8966实网络参数。结果表数值为measured；容量预测以predicted另列，未运行的大模型为NOT_RUN。

| 新路线 / measured、功率diagnostic | native | G误差 | 散射E L2 | 散射curl | R | T | A_balance | A_volume | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V8-PLAIN-DUAL | 1.055409537 | 0.9989650389 | 0.998945184 | 0.9989655403 | 0.837397101 | 0.1132687865 | 0.0493341125 | 0.4650227017 | PDE_OPTIMIZATION_NEGATIVE |
| V8-PHASE-DUAL | 1.319288666 | 0.2145123712 | 0.2134667998 | 0.2145387128 | 0.7784899564 | 0.04143373838 | 0.1800763052 | 0.2070765764 | PDE_OPTIMIZATION_NEGATIVE |
| V8-PLAIN-REFERENCE-FIT | 3.524097926 | 0.02509159227 | 0.02572950659 | 0.02507527061 | 0.8154647648 | 0.03390513729 | 0.1506300979 | 0.1552334771 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V8-PHASE-REFERENCE-FIT | 0.7662824909 | 0.01040885398 | 0.01005721383 | 0.01041758155 | 0.8125474719 | 0.03261911224 | 0.1548334159 | 0.155181753 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |

上表native以原rhs范数归一；G误差是电场及其旋度组成的内积相对误差，散射L2/curl分别用原p3准确散射场范数作分母。R/T/A归一于原入射功率；候选原方程未过，因此功率均为diagnostic，非official。所有total/scattered E/H/curl、六点复场、四类40级复通道、逐级功率、R00_s/p/total与原材料/界面区域见[PDE原比较](outcomes/records/PDE_comparison_v8.json)和[D原比较](outcomes/records/representation_comparison_v8.json)。

p4的native/augmented/独立total残差约4.29e-12/4.29e-12/4.35e-12，体吸收/能量差约1.11e-12；一次symbolic/numeric/solve各1，完整恢复75264独立复FE。p3/p4散射E L2/curl相对差0.0149860/0.0190206，R绝对差0.0037268，超过1e-3场和1e-4功率门限，分类 **P3_P4_SENSITIVITY_OBSERVED**。不宣称连续、h或端口收敛；不据此把旧NN同p3失败归因于网格。

## 2. 自行解决的根因与边界

| failure → hypothesis → change → test → retry | 实际处理及成本归属 | 未扩大授权 |
| --- | --- | --- |
| profile复数写JSON失败 | 序列化转换修复后定向test及一次新有界profile；失败日志保留 | 不改变算子或重跑长超时 |
| 原装配没有细分完成标记 | form/JIT在已有cache下0.00168s返回；MPC双线性assemble_matrix在300s剖析内未返回，内部细分仍unknown | 没有无证据指称JIT或MUMPS故障 |
| 长MPC装配 | 原局部张量/展开映射按有界cell组装准确全局CSR；独立Basix原积分、小网格/M5、非零内部/复port/伴随及原p3参考残差核验 | p4 CSR 75304行/32891168 NNZ；不删内部、无shift或截断 |
| Ruff不在ML环境、局部import/format错误 | 切换既有pure静态工具与ML测试环境，修改局部代码并定向复测 | 无安装或共享ABI/BLAS/CUDA修改 |
| C预算内未收敛 | 保留全部试探费用及final committed；串行执行另一C与条件D | 不是工程bug，无延长/调参/优化器重置 |

每类根因重试≤3，p4新增numeric仅1次，四条NN故障恢复均0次。profile所有尝试累计<10min；A整体远低于2h。准确CSR/rhs排序/hash先原子保存；解出后最小恢复packet→释放factor/KSP/无用矩阵，RSS约3.08GiB降至0.24GiB后才完整后处理。见[装配与authority](outcomes/authority_recovery_v8.md)、[repair log](outcomes/records/repair_log_v8.json)、[原剖析](outcomes/records/assembly_profile_v8.json)。

## 3. 公平、相位资格与标签隔离

相位在物理nm积分点乘入点值，早于完整边/面/内部矩与Piola，MPC只展开一次；k=0回归、非单位Floquet、独立相位积分、3非零实方向VJP、batch1/8和q15→30→60都通过。两条共同保留q15，初始实参数逐位相同、零散射。C白名单只含native/G/矩，不含reference_state、旧监督模型、Phi/Q或p4场。冻结后才独立ML重建、FE只读参考审核。

C各4000计费完整closure，final committed为plain3997/phase3986；closure是一次完整loss+gradient，线搜索试探也计费，不等于epoch或外层step。原Adam500＋L-BFGS配置不改，每步同步匹配参数/optimizer/buffers/RNG与预算原子保存，然后才发布审核。每100closure在持久态审核，最后未返回试探独立保留，不冒充final。C strict方程1e-6、场/复通道1e-4、功率/能量1e-5、逐级功率1e-6均不放宽。

D每条另有2次setup非零batch loss/梯度资格检查及18次中心差分值评估；它们没有参数更新，也不计为优化器callback closure，但全部计入路线wall和G/VJP调用。每条实际VJP1502、Gmatvec1538、原方程稀疏审核16次，均原样披露。

D各1500closure，从同seed零末层重新开始，只有G乘法与完整矩VJP；没有逐步A/A*、Gsolve或Gram factor。三项≤1e-3/1e-2分别是正/部分表示见证。本次phase相对plain的G误差改善约2.410600851倍，但D有标签，不能为C、旧路线、Task042或0.7nm提供warm start。

| 数据政策 | C | D |
| --- | --- | --- |
| reference_used_for_training / features_reference_exposed | false / false | true / true |
| pde_only_solve / benchmark_previously_seen | true / true | false / true |
| production_initialization_allowed | false | false |
| pde_only_solver_qualified / official_candidate_results | false / false（实际未过） | 固定false / false |

phase在Adam500共同点原残差及散射场均改善，但原残差仅约1.35倍，且散射误差>0.1；终态原残差更大。因此预登记 **PHASE_RESEARCH_SIGNAL=false**；有限场近似/监督表示改善保留，不能升级神经增量。共同closure和共同wall最近持久审核（含时间间隔）见[公平记录](outcomes/records/common_work_comparison_v8.json)，不补造未保存历史或同秒物理场。

## 4. 全成本、来源与可复核性

| 用途 | 实际运行源码完整SHA |
| --- | --- |
| 独立装配资格 | a48add6cbb7d553ffeb7245c1e66e734e042d21d |
| 有界原路径剖析/JSON修复 | d11209490a144679ec2e91525d18915cfef8583f |
| 唯一成功p4参考 | d0b82d7a165be89d9fa90b03be3151db9a9c3869 |
| 跨阶比较、B FE/ML、全部C/D及独立复验 | bc052a3744528277f00a7a9a5566aa4a6d7393ed |

| 正式阶段 / measured | 全wall / s | 树RSS峰 / B | 现场CPU | 自身swap峰 / B | 监督结果 | source前缀 |
| --- | --- | --- | --- | --- | --- | --- |
| v8_authority_assembly_checks | 80.49323953 | 2974027776 | 12 | 0 | COMPLETED | a48add6cbb7d |
| v8_authority_profile | 305.2326474 | 1280425984 | 12 | 0 | COMPLETED | d11209490a14 |
| v8_p3_p4_compare | 257.3178789 | 6054567936 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_p4_reference_recovery | 57.86233273 | 3888418816 | 12 | 0 | COMPLETED | d0b82d7a165b |
| v8_pde_compare | 37.69804058 | 598687744 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_pde_reconstruct | 19.55728108 | 542285824 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_phase_checks | 220.8908263 | 1557737472 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_phase_dual | 8747.323512 | 1441140736 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_phase_moment_checks | 165.017042 | 795566080 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_phase_reference_fit | 2956.519787 | 777183232 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_plain_dual | 9294.1348 | 1508184064 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_plain_reference_fit | 2850.139041 | 759963648 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_representation_compare | 37.74554687 | 596570112 | 12 | 0 | COMPLETED | bc052a374452 |
| v8_representation_reconstruct | 19.66022395 | 541335552 | 12 | 0 | COMPLETED | bc052a374452 |

| C辅助Gram / measured | setup / s | 全部solve / s | solve次数 | 最大真残差 | 总Gsolve | A/A*计数 |
| --- | --- | --- | --- | --- | --- | --- |
| v8_plain_dual | 65.53665724 | 853.4240118 | 4043 | 6.101763504e-13 | 4043 | {'A': 4042, 'AH': 4000, 'audit': 41, 'port_solve': 8125} |
| v8_phase_dual | 67.54169239 | 857.7650341 | 4043 | 1.194084663e-12 | 4043 | {'A': 4042, 'AH': 4000, 'audit': 41, 'port_solve': 8125} |

B还有一次Gram资格因子，setup约71.47s/solve约9.20s；C两条各fresh因子，均已释放。D/所有ML重建/FE compare-only新Gram与Maxwell factor均0；唯一新增Maxwell factor只用于REFERENCE_ONLY p4。以上setup、Gsolve、线搜索、审核、原子IO已在各wall中，不再相加。内存是约0.5s同时进程树采样峰，非数组bytes或内核连续限制；全部自身swap0和清场记录逐项核查。tmux外部管理进程稀疏启动RSS另列，墙钟已包含。

发布前已关闭阶段记录的V8费用约25228.9746s，旧保守49007.27663535159s及失联3284s、全部重放费用永久保留。后续浏览器、checker和Git尾段纳入[最终完整资源账](outcomes/records/resource_costs_v8.json)；本文成本表为第一次发布的关闭阶段截面，不将后续文档HEAD冒充运行source。新增上限43200s独立于旧16h，A/B/C/D/E分别≤7200/3600/21600/7200/3600s，无预算转移。每阶段重新选空闲物理核、CPU-only/MPI1/数学Torch线程1；系统max128GiB或10%、至少384GiB邻增长、自身16GiB余量都保留，未修改其他项目。

定向测试/source/log/hash见[tests](outcomes/records/targeted_tests_v8.json)，[独立checker](outcomes/records/gate_decisions_v8.json)从原复场、真实分母、功率/能量、G范数恒等式及持久状态/资源字段重算；不相信status。无full pytest、环境重装或CI通过声明。[本地Markdown](outcomes/records/markdown_check_v8.json)与[GitHub实际DOM/抽样视觉](outcomes/records/render_check_v8.json)分列，只查新Review V7及必要新页，不重渲染历史。

分支task42extra_feinn_5nm；canonical linked worktree不变；frozen base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff、release cee68ef5e8219858e3a9b733ffe454334683836b、reviewed baseline64e945b386e4c2608450c78a7d9dec9328c691da均保留为祖先。upstream声明指向origin本分支；共享fetch不映射，所以以显式refs/remotes/origin/task42extra_feinn_5nm及准确SHA/ahead-behind核对，不把未解析的@{upstream}当通过。最终HEAD和clean状态在本轮推送报告列明；文件级依赖和实际source见[publication manifest](outcomes/records/publication_manifest_v8.json)。只推送本分支，无amend/强推/merge。

## 5. 排除项、未决因素和下一轮建议

监督 phase 的 G/L2/curl 三项分类为 **REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED**，plain 为 **REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED**。相位在相同参数规模和1500完整closure内的G误差改善约2.410600851倍，说明它在这个固定G目标和预算下更容易拟合；C的原方程优化仍未通过，不能把D监督结果等同于无标签求解。两条拟合均使用参考，因此结果只能限定本架构、目标、预算，不能独立证明网络表达能力的数学上限。

已经排除本轮相位符号/单位/完整矩、非单位Floquet、非零实方向VJP、batch一致性、冻结参数重建、求积漂移、标签混入C、资源超限和匹配状态丢失等已测问题。剩余因素包括有限网络对反射/衍射/界面细节的表达、非凸残差目标的优化、G度量与原方程误差的差别，以及p3连续精度；p4对照仅说明离散敏感性，不解释NN未解出同p3。

后续只建议一项设计：在原M5/p3和同8966参数的plain/单相位表示上，预登记受控的网络参数空间Gauss–Newton信赖域对照。它用局部线性近似决定一次参数更新，并限制更新范围，检验当前非凸残差优化是否为瓶颈；仍从零、无标签，保持原Riesz目标/严格验收，不用Maxwell逆或监督权重。先核定JVP/VJP、A/A*、Gsolve、工作内存和完整成本上限，再由新review授权；本批没有实现或启动新优化器、PDE微调、多载波、p5/h细化或更大模型。

目标尺寸5nm尚需冻结几何/网格、独立精度参考和可扩展Riesz容量；[既有目标计划](outcomes/target_5nm_scale_plan.md)保留，本批未启动。当前障碍包括NN未求准同p3及p3/p4敏感，不能仅凭本轮相位近似改善晋级。

本批授权矩阵已完成，旧V1–V7负结果、e4_p4 not_run与旧Task042历史未修改；不自动p5、h细化、多载波、目标尺寸5nm或0.7nm。提交并停止等待review。
