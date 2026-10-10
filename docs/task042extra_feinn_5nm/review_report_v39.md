# Review V39：接受结构加速与完整负结果；用必要秩和轴向函数证据决定神经路线去留

## 0. 裁决、目标与执行范围

**接受 V39 已完成的等价计算加速、原定有限优化流程和独立全场验收；M5 求解及神经资源收益仍 FAIL。现在不能再用“实现太慢、没有进入 L-BFGS”解释当前结果，也不应原样续训。下一批只批准一次有界的 FTT 容量判别：利用已有准确离散场的内部积分矩，检查秩限制与轴向函数限制；不换名字再启动一轮长训练。**

本次要消除的 blocker 是：**不知道固定 r8 和每轴 16 个隐藏特征是否足以达到所需精度，却反复投资同一参数化的优化。** 本批必须给出实际奇异值、误差界及限定，而非另一份“需要实验数据”的准入文档。它是神经表示的资格诊断，不是新的前向解；研究完成不能标成 0.7 nm 目标完成。

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task42extra_feinn_5nm
canonical_worktree     = /home/fenics/Projects/NN-Lab-V2
original_base_SHA      = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD   = 45e6656a4ba55be77404b84681de07be16a2401f
result_commit_time     = 2026-10-10T08:26:36Z / 2026-10-10 16:26:36 +08:00
review_date            = 2026-10-10 Asia/Singapore
previous_review        = review_report_v38.md + review_report_v38_execution_addendum.md
reviewed_response      = response_v39.md
campaign               = V40_FTT_CAPACITY_DECISION
required_response      = response_v40.md
new_total_window_s     = 14400
new_PDE_or_training    = NOT_AUTHORIZED
production_or_merge    = NOT_APPROVED
```

最终目标保持：0.7 nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双 Floquet、Fourier-DtN、完整复 E/H/衍射/体吸收；十进制 2e12 B 是整机内存并须保留余量，自身 swap/OOC=0；单场必要准备至完整验收不超过 172800 s。原 50×25×140 nm 目标尚未通过。本批 4 h 是一次研发上限，不是新的目标算例预算。

**本支只做神经研究。** 不恢复旧稠密波库、W0/W1、全口面、模式恢复、传统 PC、主线接入或存储工程；不修改或给 Task42、主线、dot、master 及其他工作树分派工作。V39 的执行补充已经完成使命，不因其“继续到 V39 完成”的历史语句再启动同一批。新报告仅授权下面的诊断；不扩大秩、宽度、波长、几何或误差门。

## 1. 仓库快照与已证实结果

实际回读分支、Response V39、相关数值与实现，比较执行补充之后 5 次提交。前版完整 review 和执行补充从本会话原件读取，Git blob 分别为 e73731251c6ca3ec574c4065c84f99388aeb156c、f2afd149476dbbf4cf7bfdadf01f68efbcd3aac5；目录身份和未改动的原任务/规则与既有原文衔接。审阅端没有 SSH、工作站运行或大型数组复算。下面的 measured 是执行端已提交证据，不是本端新测量。

主要依据：[Response V39](response_v39.md)、[summary](outcomes/summary.md)、[全部数值与原分母](outcomes/records/full_numerical_gates_v39.json)、[完整工作性能](outcomes/records/complete_performance_v39.json)、[恢复及优化记录](outcomes/records/resume_and_training_v39.json)、[费用](outcomes/records/resource_costs_v39.json)。实际数值 source 为 962de40947413b5c4c383f62189e951b92e5ecaa，发布 HEAD 不替代数值源码。

| measured，M5/5nm/384hex/p3/31968复FE/40端口 | native FTTNN | native Cheb-TT | 隔离拟合 FTTNN | 隔离拟合 Cheb-TT |
|---|---:|---:|---:|---:|
| 累计完整调用 | 1000 | 1000 | 500 | 500 |
| 累计 Adam / L-BFGS 外层 | 500/22 | 500/23 | 100/17 | 100/18 |
| native / augmented 相对残差 | 0.948212215045 | 0.989534468620 | 29.0452399133 | 7.41014885414 |
| 散射 E 的 L2 相对误差 | 0.999458825608 | 0.999989164225 | 1.02905566935 | 0.0364842100106 |
| 散射 H/curl 相对误差 | 0.999478716178 | 0.999989122038 | 0.943064621233 | 0.0210012376785 |
| G 场相对误差 | 0.999478226190 | 0.999989123078 | 0.945276943861 | 0.0215169175885 |
| 独立能量闭合误差 | 0.415308648558 | 0.414113890953 | 1.32888792479 | 0.00378541570949 |
| actual / producer 联合门 | FAIL/FAIL | FAIL/FAIL | FAIL/FAIL | FAIL/FAIL |

模型、MPC、端口和求积检查已通过。两 native 都完成 Adam500 和原定累计1000调用；“OPTIMIZATION_SCHEDULE_COMPLETED”只表示有限预算流程执行完，不表示到达全局最优。参考拟合同样不是最佳秩8 oracle，不能从其失败证明整个函数类不可能。

| measured，等价完整工作与资源 | FTTNN | Cheb-TT | 正确含义 |
|---|---:|---:|---|
| 旧完整工作均值/s | 39.7815866893 | 47.6840944683 | 相同状态的完整梯度、更新后场及保存 |
| 新完整工作均值/s | 0.618107247244 | 0.607903906687 | 不是只计热 forward |
| 上述均值比 | 64.3603304551 | 78.4401842852 | 实现收益，不是同精度胜过 FEM |
| native 新增正式 attempt/s | 556.216935188 | 545.834501735 | 继承前缀另计，含准入等开销 |
| native 同时进程树采样峰/B | 496128000 | 516124672 | 自身 swap0，不是整个历史研发峰 |

原材料/A/f/边界未换。V39 把成本问题实质解决了，却没有恢复准确散射场；两 native 的误差仍约100%。Cheb 在参考拟合中明显优于 NN，但仍不合格，也不能将监督结果当作传统前向求解通过。本配置停止原样续算是数值投入决定，不是因 bug 放弃。

## 2. 为什么下一步检查容量，而不是再追加优化器

[FTTField](../../src/solvers/ftt_field.py) 的每个分量是三个核的连乘：

```math
 E_s(x,y,z)=X_s(x)Y_s(y)Z_s(z),\quad
 X_s\in\mathbb C^{1\times8},\ Y_s\in\mathbb C^{8\times8},\ Z_s\in\mathbb C^{8\times1}.
```

这带来两种不同限制。第一，x 对 yz、xy 对 z 的矩阵展开秩至多8；第二，每个神经核的最后隐藏层宽16，所有输出都是同一组16个标量特征加常数的线性组合，因此每轴核心函数跨度至多17。中间核有64个复输出，不等于64个独立的一维函数。Cheb 控制使用19个固定函数，也不是无限容量。

这些是结构推导，**不是已经证明失败的原因**。尤其不能从“r8”直接推出需要r16；也不能把保存场的拟合误差当作整个 r8 类的最小误差。现在要测量一个与优化器无关的必要条件，然后决定该改秩、轴向特征，还是停止此路线。

原始数学依据：[FTTNN v1 §2.1](https://arxiv.org/html/2510.13386v1)、[Oseledets, Tensor-Train Decomposition, 2011](https://doi.org/10.1137/090752286)。本报告的内部矩/Bessel判别是针对当前兼容插值的推导，不声称论文已经证明本 Maxwell 案例。论文的高波数例子使用低波数模型初始化，不提供本案从零冷单场保证。

## 3. A：构造与真正 FE 输出对应的内部矩张量

### 3.1 不直接给节点值做SVD后宣布FE不可能

本任务验收的是插值后的 FE 场，不是原始网络点值。一般插值、MPC或几何映射可能改变张量结构。因此主判别使用**被完整 Nédélec 插值精确保留的内部积分矩**，避免把原网络的秩无依据地套在最终FE节点数组上。

M5 为8×6×8个轴对齐仿射六面体。先按原mesh/owner/interior索引确认；不得硬编码cell排列、Piola为单位阵或内部系数顺序。对各cell建立物理L2正交归一的张量Legendre测试函数。p3预期分量测试空间为：x分量Q(2,1,1)，y分量Q(1,2,1)，z分量Q(1,1,2)，合计每cell36个内部矩。**这是待现场核验的dual空间，不直接假设Basix存储已经是这些矩。**

必须从原interpolation/方向/Piola推导其线性转换，并证明这些测试泛函在原内部DOF行空间内；转换不得混入未知的边/面值、重新求PDE或改变原插值。通过后，用已有同p3参考得到：

```math
 T_s(i_x,i_y,i_z)=\langle E_{{\rm ref},s},\psi_{s,i_x,i_y,i_z}\rangle_{L^2},\qquad
 i_a=(\hbox{该轴cell编号},\hbox{一维测试次数}).
```

预计三个张量的shape为(24,12,16)、(16,18,16)、(16,12,24)，合计13824个复数，即221184B；仅为derived，不是RSS。内部矩张量不是完整FE场，不得用它代替最终E/H或端口输出。

### 3.2 两条独立计算和退路

一条从原参考FE内部自由度经已推导变换取得T；另一条用原FE basis/几何对同参考做cell内积分取得T。原散射E范数约4.924968765995545，来自V39原记录；必须回读其实际分母并独立复核，不以矩张量范数替代全场范数。参考文件SHA256沿0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7，不重求MUMPS。

同时证明同一泛函施加到FTT点值后，能按各轴的线性泛函分别收缩，且与实际FE内部矩一致。使用全部三分量、axis permutation、orientation、MPC内部独立性及非零合成函数验证，不只用一个已训练态自比。

**只凭几次随机配对，不足以证明任意FTT的秩保持。** 需要保存矩定义的代数分解、cell轴索引的可分性和完整映射依据。实际浮点几何存在小非对角量时，不可直接置零后授“原空间排除”。先保留真实J及分量混合，推导其适用秩界；若只能验证规范Cartesian数学模型，则结论必须限定于该模型，另报原实现的缺陷，不能推广到所有权重下的原FE输出。

若完整分量空间不能稳定抽取，可自动使用三分量共同Q(1,1,1)内部测试子集；仍须正交、保留矩和轴可分证明。缺少上述桥接时，照常交参考谱和实现检查，但标RANK_BOUND_NOT_TRANSFERABLE_TO_FE，不假造原FE误差下界，不因此开展全局张量化工程。该退路使普通排序/归一化bug可以同批修复，科学假设确实不成立则如实限定。

## 4. B：一次SVD取得秩必要条件，不训练多个rank

正交测试函数使任意场误差满足Bessel不等式：

```math
 \|E_{\rm ref}-E_h\|_{L^2}^2
 \ge \sum_s\|T_s-T_s(E_h)\|_F^2.
```

在A已证明适用的坐标与泛函下，r8的每分量展开秩上限为x:8、z:8、y:64。对当前宽16神经参数化，y上限进一步为17；控制y上限19。分别计算“无限轴函数的纯r8限制”和“原宽度/基数的结构限制”，不能混为一项。

令sigma(s,a,j)为参考T_s沿轴a展开矩阵的奇异值。对一组已证明的秩上限R_a：

```math
 B_R^2=\frac{\sum_s\max_a\sum_{j>R_a}\sigma(s,a,j)^2}
                    {\|E_{\rm ref}\|_{L^2}^2}.
```

它是完整散射E误差的必要下界，不是实现出来的场误差；x/y/z三种切分约束可能相关，所以取max，不将三种尾能量相加。三个物理分量的能量可以相加。仅做E必要门已足以否决联合Gate；**E下界很小则不表示H/curl、通道、原方程可通过。** 不对curl直接套相同r8上限。

矩阵最大只有几十行。用原complex128 SVD直接获得完整谱，不形成Gram特征值近似，不只保留前8个值、不平方后丢小奇异值。记录重构、正交及后向误差。尾范数减去可证/可量化的输入和SVD扰动后才作保守数值下估计；超过1e-4需同时超过max(1e-8,10倍归一化数值缺陷)的裕量。这里是浮点数值判别，不是区间算术证明。

从同一份谱推导达到E误差1e-2/1e-3/1e-4的必要切分秩，不跑rank8/16/32训练扫描。给出的rank是**必要值，不是足够值**。若观测内部矩不敏感，下界可能为0；写RANK_NOT_EXCLUDED，不写PASS。

## 5. C：固定轴特征的廉价判别，不再训练一次oracle

对V39最终native FTTNN与最终隔离fit FTTNN，分别冻结实际隐藏层。每轴取16个最后隐藏特征和常数；用A的同一一维矩构成小矩阵F(a,s)。Cheb控制只需对固定T0..T18计算一份，不能按每个旧终态重复。

固定隐藏函数后，任意末层系数和TT组合产生的内部矩，都属于这些一维空间的张量积。令P(a,s)为其正交投影。放宽TT秩约束后，容易计算：

```math
 B_{\rm feature}^2=
 \frac{\sum_s\|T_s-T_s\times_xP(x,s)\times_yP(y,s)\times_zP(z,s)\|_F^2}
      {\|E_{\rm ref}\|_{L^2}^2}.
```

这是固定隐藏函数的必要下界；不是所有可重新训练隐藏层的下界，也不是最佳H(curl)场。它与B_R相互重叠，只取较强者，不将它们相加。所有一维特征从真实模型读取，不从目标场选择或补列。参考只参与隔离诊断，不提供新训练方向。

近相关特征必须完整报告数值秩/奇异值。**删掉很小但非零方向后的投影误差是更小空间的误差，不能当完整空间下界。** 全列不能稳定覆盖时给出限定/UNKNOWN；允许一次更稳定QR/SVD实现及小矩阵高精度核查，不扫描截断门、不加ridge凑结论。不形成N×P或N×m列库，不用全局G逆/A逆，不回到V36的1377列oracle。

本阶段只取两个已保存隐藏状态及一份固定Cheb函数库；不做Adam/L-BFGS、TT-SVD场压缩、核预训练或从参考构造下一轮权重。拟合态和参考相关输出永久标reference_exposed=true、pde_only_solve=false、production_initialization_allowed=false。

## 6. 同一轮资格、决定及停止条件

A–C前先完成小型complex tensor、已知秩、Bessel配对和错误轴/共轭/归一化/截断负控。原实际内部矩与独立FE积分相对差≤1e-10；矩定义代数转换≤1e-12；SVD后向误差≤1e-12；至少一个高秩制造例应触发排除，一个精确秩8例不应被误排。不得只检查最终status字段。

| 本轮实际结果 | 决定及允许解释 |
|---|---|
| 适用桥接通过，纯r8必要下界超过门及裕量 | R8_CAPACITY_EXCLUDED_NUMERICALLY；当前r8不值得续训，报告必要秩，不自动增秩 |
| 纯r8未排除，但宽16结构或冻结轴函数下界超过门 | 只排除相应宽度/固定特征；修改哪个容量已有依据，不宣称增加rank单独能解决 |
| 两类下界均小，桥接合格 | REPRESENTATION_NOT_EXCLUDED_OPTIMIZATION_UNRESOLVED；不是r8已足够，不自动续跑旧EUC |
| 桥接/正交/数值秩无法可靠建立 | 输出原始谱、已通过部分和准确限定；NO_VALID_FE_CAPACITY_CERTIFICATE，不因测试数量宣称完成容量证明 |

本批必须完成有限数值判别或明确科学/硬出口；不能只交设计待授权，也不为同一诊断自动开V41。最终最多提出一个与所得证据直接相符的后续神经实验设计，写清输入、输出、改变哪一步、要删除的成本、必要rank/宽度及一个否决门。没有依据则NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE，不以换优化器或网络名称制造进展。本批不批准该后续训练。

**这不是0.7nm晋级Gate。** V39原M5三残差1e-6、场/六点/完整复通道1e-4、功率/吸收/能量1e-5、逐级1e-6、模型/MPC/恢复1e-10及求积1e-8全部保留。参考诊断不算无标签成功。0.7nm、p/h、端口或目标规模本批不注册、不运行。

## 7. 资源、修复与成本

新连续窗口14400s；准备/接线/资格软5400s，A–C正式数值软3600s，独立复核/决定/发布软3600s，剩余修复机动；软额度可登记转移，最终至少留1800s。只读取声明索引中的必要参考、末态、矩/mesh，不全盘找文件、全仓重复hash或重新封存健康大数组。

核心张量和小矩阵规划≤256MiB；FE读取/验证沿原数值warn12/hard16GiB角色，不误派2GiB元数据runner；pure矩阵处理和文档≤2GiB。CPU-only/MPI1/math及Torch1，单个现场空闲物理核，ownswap/OOC0。原PSI、系统max128GiB或10%余量、至少384GiB邻增长及durable身份监督不放宽。成功准入计总墙钟，不回旧V30观察池；真正拒绝后额外前台等待≤900s。不得用整机2TB为本小任务放开资源。

普通索引、API、类型、方向、矩规范、保存、角色错误：同批定位→最小修复→定向测试→健康边界继续，不设bug次数交棒卡。接线可修复与数学假设不成立要分开；不为了通过下界Gate把非可分映射改成可分、不改物理或分母。保存应在T构建、谱计算及特征空间三个完整阶段后立即落盘；checker/writer/网页错误只补受影响步骤，不重算健康数值。

已有加速核不做第三轮优化/性能benchmark。V38与V39前缀继续保留于各自路线和历史账，不把本次参考诊断并入无标签求解成绩。FTT物理单场的完整冷成本仍UNKNOWN；约64/78倍仅为旧新神经映射的等价工作比，不能说FEM被加速64倍。本轮诊断不承诺产生新合格前向解。

## 8. Git、入口与一次交付

只在canonical本分支核对HEAD/worktree/锁/合法作业；活跃计算中不改HEAD、不盲kill。安全后精确fetch/ff-only；不新clone、reset/stash覆盖、不改共享Git配置。若仅同分支纯审阅文档与本地未推送实现发生分歧，沿执行补充的受限普通merge规则保留历史，不merge master/其他任务。

最小数值核放src，wrapper复用既有FTT/独立FE/pure流程。先实现/validate、targeted测试和clean实现commit，再依赖串行执行：

```text
input/task042extra_feinn_5nm/v40_capacity_checks.dat
input/task042extra_feinn_5nm/v40_interior_moment_tensor.dat
input/task042extra_feinn_5nm/v40_rank_and_feature_bounds.dat
input/task042extra_feinn_5nm/v40_capacity_decision.dat
```

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

包装选择正确环境并调用scripts/run_case.py；每项清场后再下一项，不为新stage重写调度/传输系统。绑定原input_original.dat、resolved_config.json、run_manifest.json、物理/源码/环境/MPI/资源及artifact hash。原方案没有新前向求解，所有状态字段应明确DIAGNOSTIC。

交response_v40.md、outcomes/ftt_capacity_decision_v40.md，以及紧凑的内部矩规范/桥接、真实张量shape、SVD谱、尾能量、原分母、数值裕量、固定特征秩、负控、费用、修复和source记录。只在summary/README当前入口与本分支progress/模型总账增加结论，历史保留；不复制巨型JSON，不full pytest、不重装或全量重渲染历史。

发布端尚未取得本报告GitHub完整视觉证据。有限补查新关键页，网页问题不阻断数值；不授未经确认的视觉PASS。完成有界包后报告完整HEAD、tracking/ahead-behind、clean及自身清场，只推本分支，不amend/强推/merge production。

**最终底线：工程加速已经成立，当前求解配置已经失败；下一份结果要给出容量限制的数值证据，而不是把“可能再训练好”当作0.7nm、2TB、48小时的方案。**
