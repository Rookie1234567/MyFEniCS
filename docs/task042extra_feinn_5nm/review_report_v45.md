# Review V45：结束原坐标续扫，检验一次冻结基场的神经残差增量

## 0. 裁决、目标与身份

**接受V45三路线实际完成与联合FAIL；不批准原样续训、继续调tau、增宽或提高内层迭代上限。参数右变换降低了原残差，却使实际散射E/H和能量误差变大，未取得联合数值收益。本轮批准一个不同且有边界的神经表示试验：冻结一份读出稳定的已存神经基场，另加且只加一个完整FTT神经修正场，解精确的残差方程；用同态冻结隐藏层控制检验新增学习的贡献。**

本轮要消除的blocker是：单个乘积型FTT的现有参数更新已停滞，新增输出系数出现强相消、隐藏参数几乎不动，却尚未实际检验“保留基场、增加独立修正函数”能否产生有效场更新。该假设尚未被证明；不是认定rank8必然不足，不是保证新的修正更容易求解，也不是把低残差等同准确场。

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task42extra_feinn_5nm
canonical_worktree     = /home/fenics/Projects/NN-Lab-V2
original_base_SHA      = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD   = 9b4832e79cc57e852c7a70f32c527d7b41e2b348
result_commit_time     = 2026-10-12T01:05:39Z / 2026-10-12 09:05:39 +08:00
review_date            = 2026-10-12 Asia/Singapore
previous_review        = review_report_v44.md（含0A执行澄清）
reviewed_response      = response_v45.md
campaign               = V46_FTT_ONE_RESIDUAL_BRANCH
required_response      = response_v46.md
new_total_window_s     = 43200
production_merge       = NOT_APPROVED
```

最终目标仍是原尺寸0.7nm、任意非可分三维周期单胞、complex128 Nédélec H(curl)、x/y Floquet、z Fourier-DtN、完整复E/H/衍射/体吸收；十进制2e12 B为整机物理内存，保留系统余量、ownswap/OOC=0，单场必要准备至验收≤172800s。**当前没有合格神经方案可承担该交付。**本批12h是新的研究预算，不是目标48h成绩，不重开已耗尽的V45窗口。

本报告显式覆盖旧合同中“不得增加表示容量/不得开启下一批”的限制，仅授权本报告的一份加性修正及控制。仍不恢复旧稠密波库、W0/W1、全口面、模式恢复、传统Maxwell PC、存储系统或主线接入；不修改或向Task42、主线、dot、master及其他工作树派活。不得把本任务转成预训练局部逆、低阶trace修正或第三方传统完成器。

## 1. 远端证据与当前判断

本次读取Response V45主体、完整费用/修复/发布说明、summary当前段、原始Gate关键字段、原坐标末态/PT记录、特征变换和FTT实现；比较Review V44执行澄清后7次提交。根规则/仓库原则已复核，原task仍为a0d3606aedbbce37066338de3763fe802590dedb；目录规则与本对话已读原文衔接。前版完整review由本对话挂载原件读取。目录未见Review V45。未SSH、未查看工作站实时PID、未在审阅端重算M5或逐数组复算全部大产物。

主要证据：[Response V45](response_v45.md)、[summary](outcomes/summary.md)、[完整Gate](outcomes/records/full_numerical_gates_v45.json)、[路线与PT](outcomes/records/conditional_core_routes_v45.json)、[内层](outcomes/records/conditional_inner_solver_v45.csv)、[谱](outcomes/records/operational_coordinate_spectra_v45.json)、[费用](outcomes/records/resource_costs_v45.json)、[发布尾段](outcomes/records/publication_tail_v45.json)、[特征坐标实现](../../src/solvers/ftt_feature_coordinates.py)、[FTT结构](../../src/solvers/ftt_field.py)。正式三路线source为bda2ef6c5164a59390479662955e8cef358841db，不以发布或merge HEAD替代。

| measured；M5/5nm/384hex/p3/N31968/完整40端口 | 原坐标冻结 | 缩放冻结 | 缩放学习 |
|---|---:|---:|---:|
| 末态总轮次/新增核心访问 | 14/6 | 14/6 | 14/6 |
| 原native及augmented相对残差 | 0.358564816894 | 0.308415863303 | 0.307111294905 |
| 散射E相对误差 | 0.0824876972998 | 0.0951988658107 | 0.0954707719011 |
| 散射H/curl相对误差 | 0.0825378133302 | 0.0952137619547 | 0.0954861502846 |
| 独立能量闭合误差 | 0.0265752297173 | 0.0337764856799 | 0.0337863331068 |
| 实际网络重建相对差 | 3.9452e-14 | 3.9820e-12 | 4.0935e-12 |
| q30/q60原A作用漂移 | 3.9465e-11 | 5.8103e-9 | 7.0188e-9 |
| 最大实际核心增量范数 | 2.83551715532 | 3502.65678465 | 3502.65678465 |
| 新LSMR迭代/仍未充分核心数 | 5928/4 | 7200/6 | 7200/6 |
| 新attempt秒/同时树采样峰B | 2759.38275311/945602560 | 3223.55754785/945508352 | 3315.34105774/1018208256 |
| actual/producer联合门 | FAIL/FAIL | FAIL/FAIL | FAIL/FAIL |

缩放学习相对共同第12轮起点，原残差约降15%，散射E误差却增约13.96%；隐藏参数总变化约2.04905e-11，只有9次隐藏调用。参数变化范数依赖坐标，不能单凭它证明梯度错误；结合消融与实际loss/场变化，确实没有有效隐藏学习净收益。tau=1e-6稳定性资格失败，失败具体数值NOT_RETAINED；tau=1e-4后备通过，不能追写前者的数字。

**残差下降而场变差，并不自动证明方程写错、loss必须更换或网络容量已经耗尽。** 对固定线性问题，误差与残差由原A联系；有限近似中的残差范数下降不保证场范数单调下降。完整读出/求积已通过，不能拿已修writer解释8%–10%的场误差；内层未充分、近相关特征、TT耦合和非线性优化仍未完全分离。继续扩大P增益或追加同样内层不是有证据的生产方案。

V45数值尝试已完成；但发布接续时旧43200s窗口已耗尽，末次发布超窗。接受有来源的数值证据，不授整批时间预算PASS；日历空档不是训练用时，保留NOT_RETAINED。以后先发布必要数值及compact证据，网页呈现不得成为拖延正式结果的前置条件；不得删除呈现要求或虚称已验证。

## 2. 新试验改变什么：固定基场，另学一份修正场

这里不是第一次使用残差——旧训练一直使用残差。真正的变化是**不再修改已有基网络，而让一个独立完整神经场承担修正**。它与旧波greedy的逐列全局U/Q库、Task042低阶/trace逆均不同；仍由神经网络给出全部边/面/内部矩，不用传统FE完成器。

冻结基网络E0及其完整插值c0。仅由原方程计算g，不读取准确场：

```math
A c=f,\qquad g=f-Ac_0,\qquad
c_\theta=c_0+d_\theta,\qquad d_\theta=\mathcal I_h^{\mathrm{curl}}\Delta E_\theta.
```

```math
A d_\theta-g=A(c_0+d_\theta)-f,\qquad
J_\Delta(\theta)=\frac{\|A d_\theta-g\|_2^2}{2\|g\|_2^2}.
```

g是原方程残差的相反数，**不是已知的场误差c_ref−c0，不是监督标签**；网络输出仍是修正电场，不是把残差当电场直接相加。g固定一次，不能每个核心后更新g却保留累计d。原物理验收分母仍为原f及原总场载荷，不能改成g。训练常数归一化有利于一致量级，但不改变原目标的最小点，也不改善A本身的条件数。

```math
R_{\mathrm{original}}
=\frac{\|g\|_2}{\|f\|_2}\,R_\Delta,
\qquad R_\Delta=\frac{\|A d_\theta-g\|_2}{\|g\|_2}.
```

基场冻结只保证旧结果可保留，不保证相加后的场更准确。新候选必须重新验全场，不能用“修正方程是等价的”省略验收。

两个rank8函数相加的连续FTT表示可有不超过16的TT秩上界；本轮保留两支分别计算，不构造rank16的全耦合大核心。它是受控的容量增长和重新参数化，**不是保持原rank8空间不变，也不是纯rank因素消融**。新增支线仍宽32/r8/19200实参数；合计持有两份网络38400实参数，其中基网19200全冻结。不得自动加入第二份修正、串联无限阶段或构建全局N×m库。

多级神经修正的概念可见[Han与Lee](https://arxiv.org/abs/2112.01254)及[Wang与Lai](https://arxiv.org/abs/2307.08934)。本审阅核实了原始摘要，未把全文试验或机器精度结论搬入本任务；它们不证明当前有损Maxwell问题的适用性。本文精确残差恒等式由原线性方程直接推导，不依赖文献的经验结论。

## 3. 唯一基场与零修正初态

取V45 **原坐标冻结路线的最终第14轮完整状态**，而不是缩放路线的大系数末态，也不从历史按参考误差挑best。选择依据是非放大参数路径及其更大的读出/求积稳定裕量；当前benchmark已见，选择有历史诊断参与，不称盲测。

```text
base_route             = W32_R12_IDENTITY_FROZEN
base_checkpoint        = committed_000010.pt
base_checkpoint_sha256 = 0121d04be3ae7c8fdaed1fefe23462c378dc81fa841ee0751040c7800d2b4978
base_checkpoint_bytes  = 2029380
base_source            = bda2ef6c5164a59390479662955e8cef358841db
native_sha256          = 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
moments_q30_sha256      = 22715fac468c4e364c3947e99672117f0f855dfe424914f9fce16be090a693f5
phase_sha256           = 32824e3063679681f77f6bb103fbb1ec9264f09f3441201407f6d0144cdc2ecc
```

真实路径从V45 run/index解析。核对基网14轮/42核心/25758累计内层迭代/137隐藏调用、全部参数/buffers/c/r/RNG；原mapping/A恢复配对≤1e-10。基网权重及相位全程逐位固定，requires_grad=false，不复用.grad当学习证据。旧parent/停止/费用全部留存。

新修正网络深拷贝基网的全部隐藏层、x/y输出及buffers，只把z输出层的权重和偏置清零。因此初态Delta E严格零，而首个z输出方向不恒零。不得把三个核都置零；不得将基网和修正网参数做内存别名。两条新路线的修正初态逐位相同，不再搜索seed、加入新相位或初始化频率。

这不是旧优化器恢复：新修正分支的计数从0开始，父训练只记继承前缀；旧基场不参加更新。每轮隐藏L-BFGS按原策略fresh，不能把基网历史动量塞入新网络。

## 4. 最小实现与资格：训练方程、原物理审核必须分开

复用现有FactoredMomentMap、ConditionalCoreAction、两段LSMR、durable、parent读入和独立检查。新增小型显式residual-training视图及加性场封装，不复制调度系统。**原action.f与原physical_model身份不可原地修改。**训练视图的f_train=g、bnorm_train=norm(g)；原审核必须计算c0+d并使用原action。

需要分开命名和保存c_base、c_delta、c_combined、g、r_original以及training_rhs_sha256；不能让既有action.audit(c_delta)被标为原完整方程。g由原完整c0经原A一次生成，训练用A保持线性作用，背景仿射项不再加一次。

端口恢复尤其不能把两个含背景的结果相加：

```math
\alpha(c)=D_p^{-1}(g_p-C_pc),\qquad
\alpha(c_0+d)=\alpha(c_0)-D_p^{-1}C_pd.
```

实际验收优先直接对合成c恢复完整alpha。总电场只加一次原背景；H由合成FE电场的curl得到。相位在每个物理网络内只乘一次，加和外不能再乘chi；MPC仅沿原完整系数约束展开一次。原始神经场可以光滑，最终场仍是完整H(curl)插值，不删内部矩。

至少完成以下定向资格，然后直接进入两条数值路线，不为“设计/接口通过”交棒：

- 复数非Hermitian小系统的残差恒等式、原/训练范数比例、符号与错分母负控；有非零背景的端口仿射恢复负控。
- 基网冻结、深拷贝无别名、严格零修正、首个z方向非零；非零新输出后新隐藏FD/VJP及纯虚/三分量伴随。
- 原积分点先加两网再完整插值，与两份完整矩之和配对≤1e-10；真实三轴非零K/K*、原A作用及MPC配对≤1e-10，FD稳定段≤1e-5。
- 缓存绑定branch identity与参数版本；修改修正不污染基网缓存。wrong-base/g/hash/phase、错误旧RHS、重复背景/相位/端口、partial恢复均拒绝。
- 从磁盘重开真实双网络后独立旧逐点q30/q60重建；恢复不重复加入已提交修正。零修正不是新候选PASS。

小资格允许固定非零synthetic见证，但必须恢复正式零修正再分叉；不以参考场初始化。旧健康A/f、参考、基场验收和V45谱不重算。缺失基件只有限查找声明的副本，不重新训练14轮补文件。

## 5. 两条实际数值路线与有界工作量

| 路线 | 基网 | 新修正隐藏函数 | 新修正输出核心 |
|---|---|---|---|
| RESIDUAL_FTT_R8_FROZEN | 全冻结 | 固定在共同初态 | 交替求解 |
| RESIDUAL_FTT_R8_LEARNED | 同一全冻结基网 | 每轮按原策略学习 | 相同交替求解 |

两路线都继承旧学习，冻结控制不是从未训练的传统基线。它们检验同一加性修正空间内的后续隐藏学习；与历史单网比较只能说明组合机制的变化，不能纯归因为TT秩或优化器。先学习路线，冻结控制随后；设计/初态/Gate在首次训练前冻结，不根据先跑路线的参考误差改控制。

共同仍为M5/5nm/384hex/h1.25nm/p3/N31968/完整40端口，原Si/air非可分缺口、材料/背景/A/f、双Floquet和DtN不变；体/DtN q15、网络q30/独立q60。仅新修正使用同一已知chi、宽32、rank8、19200参数，核心末端792/中间6336复未知量。两条禁用V45特征缩放，P=I；不再调tau，不新增左右PC、全局A/G因子、全FE完成器、N×d库、A*A或B*B。

训练子问题仍是一个修正核心上的B=A K/norm(g)，b=(g−A d)/norm(g)。每核第一段最多300次tol1e-8，stop7或真实伴随比>1e-3时在安全预算内仅补900次tol1e-10；damp0/conlim1e12/零增量不变。真实写回新网后重算合成c和原r；线性配对及原loss不增才提交。补足更坏用已验第一段，所有费用保留。

新支轮1为z→x→y，轮2反向，交替。LEARNED每轮后只更新修正网3360隐藏实参数，输出固定；fresh原L-BFGS lr1/history10/strong-Wolfe/max_iter10/每轮实际调用≤20。不称精确VarPro；记录真实参数变化、loss变化及梯度计算，不用保存.grad冒充学习。

每条最多6个新轮次、18核心访问、21600计费LSMR迭代、10800s；学习隐藏最多120实际调用。默认完成这份有限矩阵，不因第2/4轮没到0.1而过早筛掉。第2/4轮隔离返回R/E/H标量记录趋势；正确性、非有限数、资源和预算仍可停止受影响候选。不会因一条失败取消另一条及最终验收。

每个完整核心/隐藏步骤保存双网络manifest、修正状态、c_base/c_delta/c_combined/r、g身份、RNG、计数/预算，成功落盘后才记committed。第一段存盘只表示线性增量已保全，未代表模型更新；未保存的LSMR内态不能声称可恢复。

原R首次≤1e-8即完整联合审核；未过场门可在原剩余上限内将原R目标收至1e-10，不回传参考误差向量。第6轮之后不自动加第三个网络或再开窗口；没有合格/明确强信号则关闭本具体加性配置。科学负结果也是本有界包的有效结束，不能承诺一定PASS。

## 6. 完整数值、神经增量与成本Gate

原参考SHA256 `0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7`只由独立FE compare-only读取，不重求。独立点值路径加载两网并求和，再走旧完整矩；不能只检查producer的c_base+c_delta。只将规定标量/布尔值回传继续逻辑，参考向量、误差图、目标通道不能用于训练或选方向。

| actual复合网络与producer分别审核 | 原门限 |
|---|---:|
| native、augmented、独立总场原方程（原RHS） | 各≤1e-6 |
| total/scattered E/H/curl、六点复场、四类完整40复通道向量 | 各≤1e-4 |
| R/T/A/A_volume误差、独立体吸收一致性及能量闭合 | ≤1e-5 |
| 逐衍射级功率绝对差 | ≤1e-6 |
| 双网络实际重建、MPC及端口恢复 | ≤1e-10 |
| q30/q60完整矩及原A作用、FE独立积分 | ≤1e-8 |

原残差FAIL时所有功率仅diagnostic；原分母/近零规则不改，不拟合整体复相位。correction_residual_pass不等于full_original_equation_pass，更不等于全场PASS。用途false贯穿raw/manifest/PT/compare/reopen；保留validation_used_for_stopping、benchmark_previously_seen及design_informed_by_reference_diagnostics。

正式PASS与研究强信号分开：强信号至少要求合成场的原R≤1e-3、散射E/H各≤1e-3，并且完整稳定性检查通过；只降低loss或场改善几个百分点不够。冻结与学习均通过但后者无成本优势，只记表示/核心算法有效，不能把全部收益归隐藏学习。没有同严格精度的时间或同时树峰比较，不授20%NN资源收益。

两个rank8相加可增加跨轴表示容量，但仍可能受共同一维特征、原A条件性和内层求解限制。失败不证明所有FTT或所有神经网络无解；成功也不证明任意三维都低秩。不要再把rank/容量证明作为新前置任务。

基场必要prefix暂按V45原逻辑前缀10029.01257516597s加原坐标路线2759.38275311s，即约12788.3953283s；执行端从原账精确核对，共享研发账不得重复收费。基网准备、A/native/moments、修正训练、复合网络读取/输出和审核均要计入候选冷单场；只用checkpoint之后的秒数不是冷N=1。旧无关波库费用不强加新部署，却保留研发历史。缺失冷准备仍UNKNOWN。

## 7. 条件0.7nm与最终目标边界

仅LEARNED合成M5场通过所有原门、控制已冻结验收、现场资源安全且本批剩余≥10800s，允许一次已定义的长度整体×0.14的真实0.7nm非可分三维pilot，总pilot≤7200s，之后留≥3600s交付。使用正式0.7nm材料，重新绑定网格、模式、背景、chi和原参考，不硬套40端口、不直接缩放FE系数。可迁移合格双网的归一化核作初值并计前缀；不得再增加第三支网络。未准入不建立空输入。

该缩放保持近似电尺寸，不是原50×25×140nm目标，不证明p/h或端口收敛。当前p3只是同离散authority链；达到原尺寸仍需准确离散、随电尺寸增长的实际表示容量、原算子/DtN/全场O(N)存储与全过程RSS/时间。冻结基网和新增网络没有消除这些成本。2TB显著放宽容量，但不能只靠加内存解决0.7nm任意三维；主线需要可扩展、分布式、matrix-free求解，本支不接管主线工程。

## 8. 连续执行、修复、Git及交付

新唯一总窗43200s从首次实际准备持久登记；A实现/资格软7200s，两路线各硬10800s，最后至少3600s完整验收发布。旧V45超窗不追改，新消息不重复发放额度。可登记转移未用软预算，不扩大各路线或总上限。日历空档、CPU活动、正式数值attempt、发布费用分开；未保留细分则NOT_RETAINED。数值完成后优先提交必要response与compact证据，不先做耗时网页工作而拖过发布窗。

CPU-only/MPI1/math/Torch intra/inter-op1、一个现场合格物理核；numeric warn12/hard16GiB、含临时规划12GiB、双网合计新增cache/AD≤1GiB、轻任务2GiB、ownswap/OOC0。原PSI/SMT、系统max(128GiB,10%有效内存)与384GiB邻增长保护不变。一个本任务数值阶段串行运行，不能抢邻任务CPU或更改环境。已有短tmux socket和正确V45观察策略复用，不重复旧接线错误。

普通API/schema/符号/仿射项/alias/梯度/缓存/目录/角色/恢复/保存错误：保留failure→hypothesis→minimal change→targeted test→resume；同批修复，无普通bug次数交棒卡。健康producer、参考、基网和g不因writer/网页错误重算；相关数学变化另commit并复验。安全、不可恢复数据、ABI/权限和总成本硬出口仍须保全并报告，不绕过保护，不保证必过数值Gate。

启动前只读核对branch/HEAD/worktree、锁、PID/start_ticks及已有本批run。合法运行不改源码/HEAD、不kill、不启动副本；已有合格步骤按身份复用。无活跃run且clean时精确fetch/ff-only；若仅本任务review文档与本地未推送实现分歧，沿已有受限普通merge规则保留双方历史。不得reset/stash覆盖、rebase/amend、强推或merge master/其他任务。

建议提交C1为最小实现/输入/定向资格，clean实现SHA后再正式运行；C2提交两路线与原Gate compact证据；C3收口response/summary/总账。正式算法进src，runner只参数编排，不复制每个版本一套数值核心。

```text
input/task042extra_feinn_5nm/v46_residual_branch_checks.dat
input/task042extra_feinn_5nm/v46_residual_branch_prepare.dat
input/task042extra_feinn_5nm/v46_residual_branch_learned.dat
input/task042extra_feinn_5nm/v46_residual_branch_frozen.dat
input/task042extra_feinn_5nm/v46_residual_branch_compare.dat
```

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

先实现/validate、targeted tests、clean commit，wrapper选择合格FE/ML/pure activation并调用scripts/run_case.py，逐项清场。每run绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、环境/MPI/线程/资源与artifact hash；另列base/g/双模型/训练分母身份，不篡改原物理身份。

交response_v46.md、outcomes/ftt_one_residual_branch_v46.md，以及base/g恒等式、初态/深拷贝、全矩/端口负控、内层/隐藏更新、合成原R/E/H历史、完整Gate、成本/修复/source紧凑证据。更新本分支summary、README当前入口、progress、模型总账、tests/changed_files，旧结果全部保留；不full pytest、不重装、不全仓反复hash。

最终必须回答：新分支是否产生非零且可独立重建的修正；原R和实际场是否同时接近/通过门；隐藏学习相对同态控制有无增量；额外容量与完整成本是否值得；0.7nm是否实际准入。不能只交接口、更新次数或更漂亮的残差曲线。完整有界包或真实硬出口后一次交付，准确报告HEAD、tracking/ahead-behind、clean及自身清场，只推本分支。

审阅端只可声称已完成的源文/小型复数代数检查，不替代工作站M5。GitHub真实呈现无法取得时记NOT_VERIFIED，有限补查关键新页，不把源文/本地解析当视觉PASS，也不阻断健康数值工作。
