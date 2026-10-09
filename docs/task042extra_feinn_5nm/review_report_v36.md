# Review V36：接受最终数值判别，停止旧求解族；新神经机制先过单场准入门

## 0. 正式裁决与边界

**接受V36完成此前未完成的最佳场表示审计；关闭该审计，不再重跑。当前两份冻结神经空间的原方程最小残差与最佳场误差均不能达到要求，当前“全局稠密波库＋逐块回拟合”生产候选停止投入。下一步不是延长旧训练或再审一次同一空间，而是只允许一个短的新机制准入说明；没有足够依据就停止新增计算，不编造即将实现0.7nm的承诺。**

“不要被bug卡住”在V36已经落实：修复checker父进程和资源契约后，健康投影与FE场没有重复计算，完整验收最终完成。现在停止旧配置是依据数值证据的投入决定，不是因为一个未修复bug停止执行。不能把负结果当成实现错误无限追逐，也不能把完成审计包装成新的前向求解成功。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42extra_feinn_5nm
canonical_worktree     = /home/fenics/Projects/NN-Lab-V2
original_base_SHA      = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD   = 4543797060bac8f4d8341d8d5d797be285a1cd2d
result_commit_time     = 2026-10-09T13:22:31Z / 2026-10-09 21:22:31 +08:00
review_date            = 2026-10-09 Asia/Singapore
previous_review        = review_report_v35.md
reviewed_response      = response_v36.md
V36_audit_status       = ACCEPTED_COMPLETE_WITH_NEGATIVE_SOLVER_RESULT
next_delivery          = response_v37.md
next_scope             = NEURAL_RESTART_ADMISSION_ONLY
new_work_cap_seconds   = 7200
new_PDE_or_training    = NOT_AUTHORIZED
production_merge       = NOT_APPROVED
```

最终目标保持：真空0.7nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、x/y双Floquet、z Fourier-DtN，输出完整复E/H、衍射与体吸收；十进制2e12 B为整机物理内存，必须保留系统余量且ownswap/OOC=0；单场必要数据准备、构建、求解、恢复、输出和验收全过程不超过172800s。当前原50×25×140nm目标仍未资格化。本次两小时是准入分析上限，不是新PDE预算或目标48h成绩。

**本支仍是神经支线，不接管Full3D工程。** 不恢复W0/W1、全口面、模式hash恢复、传统预条件器、全局因子、存储系统或主线接入；不修改或安排Task42、主线、dot、master或其他工作树。不把已经失败的神经组件包装成另一个任务的成功。没有新神经候选时，本支可以暂停计算，而不是以其他工作填充版本。

## 1. 仓库快照、审阅范围和来源

实际读取当前分支、Response V36、summary、投入决定、完整紧凑oracle记录、根规则/仓库原则及原任务，比较Review V35发布以来4次提交。前一完整review从本会话已挂载文件读取；远端目录列出的review、原task和目录规则沿未变blob核对，未发现新的独立补充任务书或Review V36。审阅端没有SSH、没有工作站训练/FE运行，没有逐数组复算大型原始列库。以下measured是仓库执行端证据，不是审阅端新测量。

主要依据：[Response V36](response_v36.md)、[summary](outcomes/summary.md)、[投影及误差原记录](outcomes/records/field_oracle_v36.json)、[全部物理Gate](outcomes/records/joint_gates_v36.json)、[V35原方程最优性](outcomes/records/unlabelled_optimality_v35.json)、[V36投入决定](outcomes/neural_route_decision_v36.md)、[成本](outcomes/records/cost_capacity_v36.json)、[运行source](outcomes/records/run_index_v36.json)。

| 同M5/5nm/384hex/p3/31968独立复FE/40端口；measured | 学习冻结空间 | 确定性控制空间 | 门限与判断 |
|---|---:|---:|---|
| 原槽数/最终数值秩 | 1377/1377 | 1377/1377 | rcond=1e-12；无删列 |
| V35最佳native原残差 | 0.143187704283 | 0.144406937790 | 1e-6；FAIL，已接受证据复用 |
| V36最佳实际G相对场误差 | 0.00317624280631 | 0.00310153077713 | 1e-4必要门；约31.76/31.02倍 |
| 最优性相对缺陷 | 7.53770161444e-14 | 2.60110871427e-14 | 1e-9；PASS |
| G正交缺陷F | 1.73855719961e-12 | 1.89881487604e-12 | 1e-9；PASS |
| 理想基/实际U幅值映射差 | 6.97059445645e-14 | 7.05871500079e-15 | 1e-10；PASS |
| 独立G/FE误差能量配对 | 2.97023986886e-12 | 4.92680932474e-14 | 1e-8；PASS |
| 实际点值网络到完整矩重建 | 2.00725127960e-13 | 1.23951167651e-14 | 1e-10；PASS |
| 最佳G场的native/augmented | 0.424520919376 | 0.423355066666 | 1e-6；FAIL，区别于残差最优场 |
| 最佳G场的散射E相对差 | 0.00477860366960 | 0.00482030019377 | 1e-4；FAIL |
| 最佳G场的散射H/curl相对差 | 0.00312515346716 | 0.00304558767402 | 1e-4；FAIL |
| 独立体吸收能量闭合误差 | 6.22502264416e-5 | 7.42285144668e-5 | 1e-5；FAIL |
| 最大逐级功率绝对差 | 1.95174995201e-5 | 1.36269810910e-5 | 1e-6；FAIL |

学习投影source为a4e14e889861ea7b3a4725e0f2bfe07490b34baa；控制投影和最终独立验收source为67cca36b3b344afb61943378582483f8f88e7e97。文档HEAD不替代数值source。oracle使用准确参考，只是表示诊断；不能将它的场改善计作无标签求解或神经净收益。

## 2. 现在到底能下什么结论

### 2.1 两个不同的最优问题已经有数值答案

对各自固定的原列库U：

```math
\rho_U=\min_a\frac{\|AUa-f\|_2}{\|f\|_2},\qquad
\epsilon_U=\min_a\frac{\|Ua-c_{\rm ref}\|_G}{\|c_{\rm ref}\|_G}.
```

第一项回答“这些波形最能满足原方程到什么程度”；第二项回答“即使知道正确答案，最能表示场到什么程度”。它们的最优幅值一般不同。不能把第二项较低的场误差说成第一项的残差也降低了。

G采用原ell=5nm的正定H(curl)内积。对于任意一个实际误差场：

```math
\epsilon_G^2=
\frac{d_E^2\epsilon_E^2+\ell^2 d_C^2\epsilon_C^2}
     {d_E^2+\ell^2d_C^2},\qquad
 d_E=\|E_{\rm ref}\|_{L^2},\quad d_C=\|\nabla\times E_{\rm ref}\|_{L^2}.
```

若相同场的E与curl相对误差都不超过1e-4，则其G误差也必须不超过1e-4。当前全1377列空间的数值最佳G误差约3.1e-3，且正交、最优性、原网络映射与独立积分缺陷远小于这一差距，因此可以作**固定空间的数值排除**：只改幅值不可能同时达到原E/curl门。它不是严格区间证明，不是全部可学习q/kappa的全局最优，也不排除所有FEINN/NN方法。

这里“满秩”不能单独替代稳定性证据。本次小投影Gram的cond2约3.87e5，机器epsilon乘条件数约8.6e-11，实际正交与映射检查也通过；这些共同支持本例判定。即便如此，不应把记录中上下估计浮点数相同说成零不确定性。

### 2.2 审计完整，不再为相同问题续开版本

V35未完成B的UNKNOWN在这次获得了实际数值，应该只更新当前汇总，不覆盖旧UNKNOWN历史。接受本次审计闭环，不再安排第三次oracle、重复覆盖诊断、幅值读出或继续优化同一冻结空间。

原方程约0.14与最佳场约0.003的双重限制，足够支持工程停投决定。此决定不要求证明“神经网络普遍无解”。如果未来改变了表示空间、学习对象或成本结构，必须重新给出研究准入依据，不能拿现有空间的排除作普遍否定，也不能用“理论上仍可能”维持原样长跑。

**正式状态分开保存：**

```text
AUDIT_COMPLETED = true
CURRENT_FROZEN_SPACES_NUMERICAL_GATE = FAIL
CURRENT_DENSE_WAVE_SOLVER_FAMILY = CLOSED
NO_VERIFIED_NN_INCREMENT = true
FULL_TARGET_NOT_QUALIFIED = true
GENERAL_FEINN_IMPOSSIBILITY_PROVED = false
```

不授production或merge approval。已有原方程、完整矩、稳定复数累加、导数、监督器等可以留作研究基础，但本轮不发起选择性合并或“完善交接”计算。

## 3. 工程进步与目标成本不能混账

V36两空间都通过Householder加小内积白化的首选路径，无需后备；正式attempt合计1602.11830733s，含失败；日历费用、发布尾段另有快照，不能把某个中间快照冒充最终墙钟。采样同时整树峰4301893632B，自身swap0。每空间U实际704318976B，属于对象体积，不是RSS。

[oracle记录](outcomes/records/field_oracle_v36.json)给出的每空间加载、QR、G作用、小因子、反变换、数值核验及保存的互斥计时约146s。旧V35投影运行5110.947981953854s仍未完成，故不能据此宣称严格同工作量加速比；可以确认的是本次稳定算法完成了旧实现未完成的任务。

checker在有MPI后代的FE父进程下受阻，已用独立pure受监督父进程修复；漏传资源预留也已补齐。健康投影/FE只补checker，不重复运行。这类处理符合用户要求，应保留；没有理由因为同类元数据问题再重跑已完成数值。

当前列库最低对象模型仍为：

```math
M_{U,Q}=32Nm\quad\text{bytes},\qquad
N=10^7,\ m=1377\ \Longrightarrow\ M_{U,Q}=440640000000\ \text{bytes}.
```

这是形状例子，不是目标实际DoF或峰值。N=1e8时同两份列库即4.4064e12B，尚未包括算子、工作空间、端口和系统余量。目标2TB不能消除表示误差；仅把列库塞进内存也不等于48h内完整求解。

保留10186.178641493432s必要旧前缀、V34学习已加载packet保守归属20728.120829955675s及V35失败费用；项目账不重复收费。完整冷单场N=1和项目精确累计仍UNKNOWN。当前没有合格NN解，不能把未达同精度的资源数变成NN胜过FEM的倍率。

## 4. 下一步不是再换优化器：只做一个新机制准入说明

### 4.1 此处授权的工作性质

当前没有证据支持新的神经**生产**候选。这不妨碍研究一个不同机制，但要先解释它为何可能同时改变精度和完整成本。**本批只授权最多两小时的源码/文献/成本准入分析，不授权新训练、PDE、投影、数据集、rank扫描或大型矩阵构造。** 已完成V36不再变成新方案的无限前置任务。

本报告给出唯一优先评估对象：**函数张量列车神经场（FTTNN）**，状态为PROPOSAL_ONLY_NOT_QUALIFIED。它用几个小网络产生矩阵值函数，并通过矩阵连乘表示场，而不是显式存储每个波函数在所有FE自由度上的U/Q列。下面仅是三维复向量推广的设计草图，不是已实现算法：

```math
E_{\theta,s}(x,y,z)=F_{1,s}(x;\theta_1)F_{2,s}(y;\theta_2)F_{3,s}(z;\theta_3),
\qquad s\in\{x,y,z\},\qquad c_\theta=I_h^{\rm curl}E_\theta.
```

矩阵中间维度是张量秩，不要求解或材料可写成单一乘积；但小秩是否足够必须另行验证。真正可学习的是核函数网络参数。仅对已知FE场作TT-SVD是传统分解诊断，不能冒称NN训练、独立求解或生产收益。

**这只是一个有出处的重开申请，不是自动换路线的命令。** 与早期坐标NN一样，它仍可能面临残差优化困难；与当前稠密波库不同的潜在价值是去掉N×m列库与其反复QR，并对振荡结构使用不同的非线性参数化。若其推导最终仍需要等价的N×m Jacobian、稠密读出或大量目标解标签，应直接在准入说明中否决，不实施。

### 4.2 已查来源与必须保留的限制

[Feng等，Functional tensor train neural network for solving high-dimensional PDEs，arXiv:2510.13386v1](https://arxiv.org/html/2510.13386v1)的§2.1–2.2给出神经核函数与物理loss；例子包含标量Poisson/Helmholtz等。§2.2将源项和系数写成FTT形式来分解积分。不能将这项便宜积分直接搬到任意非可分复材料、H(curl)、Floquet与DtN问题，也没有本文目标单场成本证据。审阅端已读取这些方法段与实验目录，不宣称全部实验复现。

[Space-Time Spectral Collocation Tensor-Network Approach for Maxwell's Equations，arXiv:2512.15631](https://arxiv.org/abs/2512.15631)可作方法边界参照：公开摘要使用常材料空间—时间谱配置/TT，不是本项目非可分有损频域Nédélec散射，更不是NN胜过传统FEM的证据。

若需要压缩非可分材料或算子，必须把压缩误差、准备时间和存储加回总账；不得把物理问题偷换成可分材料。保留原材料网格及native作用则仍要承担O(N)级场/残差和体端口操作，不能把网络权重很小写成全过程内存很小。本次只分析这一个候选，不转去收集一长串“可能有效”的算法名字。

### 4.3 Codex必须写清的准入门

| 准入维度 | 必须给出的具体内容 | 不合格或未知时 |
|---|---|---|
| 差异机制 | 与旧tanh、单相位、全局波列、VarPro、已否决神经修正不同在哪里；引用实际接口 | 仅改名字/优化器则REJECT |
| 神经角色 | 输入/输出/参数、从零如何训练；线性代数与NN贡献分开 | 传统TT或精确完成器不能计作NN |
| 任意三维 | 材料非可分、界面、全内部矩、Piola/MPC、真实DtN如何保留 | 依赖z模态/材料可分才能成立则不适合本目标 |
| 单场成本 | 删去哪些实测对象和阶段；增加哪些训练/JVP/VJP/核收缩/后处理 | 只报推理或checkpoint后秒数则REJECT |
| 完整内存 | 按N、秩、参数、积分点写生命周期对象表，含峰值重叠、反传与端口 | 仅给模型权重大小则REJECT |
| 数值路径 | 先验证表示与兼容映射，再做同离散原方程联合Gate，不能只看loss | 无完整E/H/通道/能量门则REJECT |
| 强控制 | 同秩/同物理/同预算的确定性表示，以及合格FEM成本 | 不得只与差的NN基线比 |
| 最小试验 | 一个可证伪pilot的准确输入、输出、预算、停止门；可复用什么 | 本批仅写设计，不自动运行 |

新路线应使用如下冷N=1账式，而不是用未来很多次查询摊销：

```math
T_{\rm new}=T_{\rm retained}+T_{\rm data}+T_{\rm learning}
 +T_{\rm correction}+T_{\rm recovery/check},\qquad
T_{\rm base}=T_{\rm retained}+T_{\rm removable}.
```

在真正同精度比较中，20%时间收益要求新增项之和不超过T_removable−0.2T_base。右边为负时，即使目标模块免费也不够；右边为正仅是必要的成本机会，不是收益证明。内存须按同时峰值算，不能直接把所有对象体积相加当RSS。所需值未测时列UNKNOWN和所需最小测量，不填有利猜数。

FTTNN若能直接流式求c和导数，可能去掉当前N×m波库；但相对于最佳传统FEM究竟删除什么成本、精度需要多大秩、每次训练是否更贵，目前均未测。该状态必须如实保留。所谓“有研究价值”与“已批准实现/生产”分开：最多RESEARCH_DESIGN_READY_FOR_REVIEW，不能标PRODUCTION_READY。

## 5. 对最终目标的执行优先级

本神经支线目前不能承担原尺寸0.7nm、2TB、48h交付，不能继续作为主目标的关键进度依赖。目标路线仍需真实的准确离散、完整原方程求解和全过程资源证据。这里不审判其他分支的最新资格，也不为它们下达命令；本报告只解除当前失败神经候选继续占机的必要性。

如果优先目标是尽快得到合格前向结果，应优先保护已建立物理authority的现有求解主线的资源窗口，而不是继续给已排除的冻结空间追加运行。这个资源建议不授权Codex暂停、改配额或操作任何邻任务。本支已无活跃作业时保持空闲即可。

未来获准的神经试验仍须遵守原严格门：native/增广/独立total各1e-6，total/scattered E/H/curl、六点及完整复通道向量各1e-4，R/T/A/A_volume与独立能量1e-5，逐级功率1e-6，模型/MPC/恢复1e-10，独立求积1e-8。同离散通过不等于网格/阶次/端口收敛；小0.7nm通过不等于原尺寸。新机制未准入前，不注册空的0.7nmstage来制造推进印象。

## 6. 本轮实际交付，不再制造数值待办

Codex按下列顺序连续完成，无需逐小步请示：

1. 确认工作树与无活跃本任务作业，精确同步本review；读取V36紧凑记录及其源文件索引。V36已经做过的hash/字段核验复用，禁止全盘重hash大型数组或重算投影。
2. 在当前README/summary入口明确审计已完成、当前配置关闭、目标未通过。旧段落、模型、原始数组及负结果保持不变，不物理删除或移动历史数据。
3. 基于§4原始文献、现有接口和紧凑成本，完成唯一FTTNN准入说明。没有足够依据就明确REJECT或EVIDENCE_INSUFFICIENT；不得为了继续运行凑PASS。
4. 提交response_v37.md、outcomes/neural_restart_admission_v37.md和一份compact records/neural_restart_admission_v37.json，同步本分支progress及模型总账的决策说明，不另建一套退役报告。说明哪些是新测量（本轮无新PDE）、推导、文献依据或UNKNOWN。

最多新增7200s连续准备/分析/检查/发布预算；最多30分钟用于本地轻量一致性和形状算术，全部进程树≤2GiB、一个空闲物理核、数学线程1、自身swap0。不得申请16GiB数值窗口、启动durable PDE worker、FE assembly、oracle、训练、profile长测、GPU或读取巨大参考数组。无需进行heavy准入来编写文档。确有本任务残留进程时只读识别并报告，不盲目kill、不修改其HEAD。

普通链接、JSON、脚本小错误同批修复后继续；不因首次错误交棒。网页或文献服务不可达时保存已取得的摘要/方法限定，不能把摘要冒充全文，也不重新运行健康数值。数据/权限实质缺失且无法在本地已声明来源恢复时如实交付，不启动无限等待或后台抓取。

没有新source行为变更就不要求full pytest、重新安装环境或重跑已通过数学测试。无需新增one-run dat；正式PDE将来仍只能经scripts/run_case.py，但本轮根本没有新的PDE准入。渲染只有限查看新review和必要结果段，本地结构通过与浏览器视觉分开，不全量重渲染历史。

Git仅在task42extra_feinn_5nm，精确fetch/ff-only，不新clone/分支、不reset/stash覆盖不明修改、不amend/强推/merge。允许的变更只有本任务新交付文档及本分支总账的决策更新，不改src/input、旧task/review或其他工作树。

建议最多两次提交：准入说明与compact依据；最终回复及总账。只推送：

```bash
git push origin HEAD:refs/heads/task42extra_feinn_5nm
```

交付后报告完整HEAD、显式tracking/ahead-behind、clean及自身清场，停止等待新机制的明确审阅授权。若设计被否决，本分支不自动产生下一轮重命名试验。

**最终要交付的是清楚的投入决定：V36数值问题已回答，旧求解族停止；新机制是否值得一个不同的最小试验，依据是什么。不是要求Codex在这一轮保证任何NN收敛，更不是把额外版本号当作0.7nm前向计算已推进。**
