# Review V32：保留多尺度进展，固定容量重学已有波矢，完成神经求解与成本裁决

## 0. 裁决、任务边界和唯一执行入口

**接受 V32 的完整负结果和多尺度场改善；不授予 M5 求解资格、NN 资源收益或原尺寸资格。停止原样从零重复 greedy、继续堆列以及重复覆盖诊断。本轮检验一个不同且可核验的机制：已有波矢不再一经插入就永久冻结；在列数不增长的条件下，轮流重学已有波块，并在每个试探中重新求解全部线性幅值。**

要消除的 blocker 是：当前波动神经空间通过不断增长来逼近解，仍未达到精度，且全局 U/Q 存储随 N×m 增长。先检验能否在固定容量下用非线性特征重学习获得实质精度改善；这比把2TB当作无限列库更接近最终目标。**它不是保证收敛的修复，也不是已经证明的唯一根因。**

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task42extra_feinn_5nm
canonical_worktree     = /home/fenics/Projects/NN-Lab-V2
original_base_SHA      = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_HEAD          = d85532461b04f486a86c678c3eadaf745a442126
latest_result_commit   = 2026-10-08T07:43:53Z / 2026-10-08 15:43:53 +08:00
review_date            = 2026-10-08 Asia/Singapore
response_reviewed      = response_v32.md
previous_review        = review_report_v31.md
campaign               = V33_FIXED_CAPACITY_WAVE_BACKFIT
required_response      = response_v33.md
new_continuous_cap_s   = 43200
ordinary_default       = UNCHANGED
production_and_merge   = NOT_APPROVED
```

最终目标保持：真空波长0.7nm、原50×25×140nm周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet、开放Fourier-DtN及完整E/H/衍射/吸收；十进制2e12 B为整机物理内存且必须留余量，ownswap/OOC=0，单次必要准备至完整验收≤172800s。**本次12h是研发窗口，不是目标单案48h成绩，不清零历史费用。**

本支仍只做神经相关研究。不恢复W0/W1、全口面、模式恢复、传统PC、存储系统或另一套Full3D引擎；不向Task42、主线、dot、master或其他工作树写入/安排任务。只复用本神经案例所需的原算子、数据和验收。旧task/review/response/raw保持不可变。本报告覆盖旧“已有q永久冻结”、每轮从零重建神经库及本批运行配额；物理和严格Gate不放宽。

接口、一次commit、一个模块完成或普通bug不是交棒点。A→B→C→E连续执行；满足联合Gate后才进入条件D。真正的数值/成本否决、无法恢复的数据/权限/ABI、安全条件或总预算耗尽允许失败收口，不能无限占机或承诺必然PASS。

## 1. 仓库快照、已证实进展与未通过项

本次实际读取最新response、summary、专题、成本记录、根规则/仓库原则和相关源码；核对前一review以来8次提交的文件清单。原task与任务目录AGENTS的blob未变，按原文继承；V31报告从已挂载副本完整读取并核对远端目录blob，目录无新补充任务书/Review V32。没有SSH、工作站新FE/训练或大数组复算。数值来自下列已提交证据，不能冒称审阅端新测量；完整大Gate JSON没有在本端逐数组重判。

| M5 / measured | 固定多尺度控制 | 学习多尺度神经 | 原Gate |
|---|---:|---:|---|
| 独立复FE / 端口 | 31968 / 40 | 31968 / 40 | 同384hex/p3、5nm |
| 保留复方向 / 块 | 1377 / 246 | 1350 / 241 | 非完整FE维数 |
| 非零q学习更新 | 0 | 241 | 真实学习，不是强制扰动 |
| native / augmented | 0.157431767049 | 0.111824065796 | 各≤1e-6，失败 |
| 独立total原方程 | 0.0745757053209 | 0.052971256913 | ≤1e-6，失败 |
| 散射E L2相对误差 | 0.0288946898255 | 0.0423218706136 | ≤1e-4，失败 |
| 散射H/scaled-curl相对误差 | 0.0289677399528 | 0.0423056325836 | ≤1e-4，失败 |
| 完整模型→矩重建 | 8.91426760953e-13 | 5.0500950991e-15 | ≤1e-10，通过 |
| 独立体吸收能量闭合 | 0.00984388938608 | 0.00319702129457 | ≤1e-5，失败 |
| 最大逐模式功率绝对差 | 0.00647487128873 | 0.0117979668499 | ≤1e-6，失败 |
| 实际学习attempt / s | 9572.249427650357 | 11982.685080887983 | 并非同精度速度比 |
| 含路线早期审核/修复 / s | 10186.178641493432 | 12180.057795704808 | 共同终验800.492335618008s另列 |
| 同时进程树采样峰 / B | 5290643456 | 2288005120 | ownswap0，非连续硬峰 |

证据：[Response V32](response_v32.md)、[专题](outcomes/multiscale_neural_support_v32.md)、[全部指标](outcomes/records/full_metric_index_v32.csv)、[数值Gate](outcomes/records/full_numerical_gates_v32.json)、[费用/容量](outcomes/records/cost_and_capacity_v32.json)、[run/source](outcomes/records/run_index_v32.json)。最终数值和独立检查source为`a11c3ae2157f42a6874e54ec6cec29ab57fe0b81`；固定前缀和QR修复source分别保留，发布HEAD不当数值source。

**多尺度表示取得了真实的阶段性改善。** 与V31约99.9%的散射场误差相比，V32已降到2.89%/4.23%；但支持、选区、起点和费用均有变化，不能归因于某一处单独代码，更不能把它归为NN净收益。V32同批学习的残差更低而场误差更大，故残差优于控制不等于场优于控制，也不等于资源节省。

旧保存空间没有严格零支持cell，bottom的P·U也非严格零，但原[覆盖记录](outcomes/records/saved_space_coverage_v32.json)给出的固定/学习Frobenius范数仅约5.15e-32/5.01e-32。不能声称已严格证明“完全无覆盖”，也不能用“非零”或相对截断后rank17/19证明存在可稳定利用的底部方向；仍须结合列尺度、幅值和实际输出判断。V32已产生明显不同的透射响应，不再重跑旧覆盖审计。新报告仅撤回未经证明的绝对因果断言，不排除弱可达性/病态性。

固定QR刷新和角色分类bug已处理并保全；学习模型重建与完整物理评分均完成。**当前不合格不能再归咎于writer、渲染或一个尚未完成的后处理。**同样，没有证据证明全部神经方法不可能；本结论仅关闭旧冻结q的具体配置。

## 2. 下一机制：不是再求一次末层，而是重新学习已有特征

### 2.1 为什么有必要，改变哪里

当前[多尺度模块](../../src/solvers/neural_wave_multiscale.py)优化新插入块的q，旧q随后保持不动；[专题](outcomes/multiscale_neural_support_v32.md)也明确所有旧幅值可重组合、旧q冻结。增加新块时的局部最佳q，未必在后来空间扩大后仍最佳。V32没有测量整个最终网络对全部旧q的驻点条件，不能把停止状态称为非线性最优。

新方法称 **固定容量波动回拟合（block variable projection/backfitting）**：一次取一个已有波块，暂时把它从“固定的其余空间”中取出；学习该块的连续q；每个试探都让该块及其余所有块重新决定幅值。只有真实原残差不增且映射/秩合格才原子替换。**列数、波数、窗口/材料/网格均不增长；改变已有函数，而不是又加入几千列。**

这仍可能陷入局部最优，且不会自动改善原残差与物理误差之间的条件性。保留原严格E/H/端口/功率验收，不能只盯住loss。禁止把QR优化包装成NN收益；只有真实q学习及合格数值/成本对照才算。

方法依据：[Dong–Yang的VarPro神经PDE研究](https://arxiv.org/abs/2201.09989)将非线性特征与线性系数分开处理；本报告用的是该一般结构，不移植其问题/边界假设或成功保证。[SciPy QR删除](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.qr_delete.html)可用于维护去除活动列后的经济型QR；仅检查现有环境支持，不升级SciPy/ABI，也不把文档版本当工作站版本。

### 2.2 数学合同：不能用包含活动块的旧Q将其自己投掉

令当前完整矩系数为 c=U_F a_F+C(q)b。U_F包括所有非活动块；C(q)仅包含选中块原先保留的幅值方向。A和f为原M5完整native算子/载荷，n_f²=f* f。

```math
B_F=A U_F=Q_F R_F,\qquad P_F=I-Q_FQ_F^*,\qquad r_F=P_F f,
\qquad Z(q)=P_F A C(q).
```

```math
b(q)=\arg\min_b\|Z(q)b-r_F\|_2,
\qquad a_F(q)=\arg\min_a\|A U_F a-[f-A C(q)b(q)]\|_2.
```

```math
c(q)=U_Fa_F(q)+C(q)b(q),\qquad r(q)=f-Ac(q),
\qquad \phi(q)=\frac{r(q)^*r(q)}{2f^*f}.
```

两个线性最小二乘均用QR/SVD，禁止正规方程逆。活动块最多24个原幅值列；非活动空间最多原1377列。若B_F或Z数值秩亏，以固定rcond=1e-12取得实际保留范围，不把完整QR的无效列当投影空间。秩发生跳变时梯度可能不光滑：保存事件，拒绝不能稳定配对的试探，缩步/换活动块，不宣称光滑梯度保证或改rcond求通过。

**Q_F必须去掉活动块后重新取得，不能直接用当前全空间Q。** 使用全Q会把旧活动方向也投影掉，错误制造退化或无下降；针对这个错误写负控。列顺序、旧归一化、幅值映射和QR置换必须明确保存。

在局部数值秩固定且线性子问题充分求准时，实q方向导数为：

```math
d\phi(q)[\delta q]=-\frac{\mathrm{Re}\{r(q)^*A[dC(q)[\delta q]]b(q)\}}{f^*f}.
```

线性幅值的导数项由最小二乘驻点条件抵消，不是随意停止梯度。等价地可使用P_F后的残差/算子，但应先以原完整式配对。网络q是实参数、物理单位rad/nm；采用q/k0优化时链式因子k0不能漏掉。复幅值及全部边/面/内部矩VJP均按原合同。

活动列必须为原完整点值矩C_raw(q)乘**冻结的旧幅值映射T**：C(q)=C_raw(q)T。一段试探内T、选中的原幅值分量和窗口不变；不能悄悄释放原被丢弃的幅值方向而增加容量。可逆列归一化若更新必须同步正确变换及求导；最小实现优先固定T、由QR处理尺度。

### 2.3 计算和保存，不造另一套大求解器

优先在已有AU/经济型QR上做列删除/插回或准确低秩更新；同一活动块的Q_F在其全部q试探中固定，不能每次objective重建整个QR。若更新不可靠，复用已存在的[原AU QR刷新](../../src/solvers/neural_wave_qr_refresh.py)作等价后备，含临时对象预检并全额计费。不是新全FE因子，不形成A*A、N×N投影、大Jacobian、Gram逆或完整Maxwell逆。

每个接受替换保存q、T、全部幅值、完整c/r、U/QR或准确重建信息、活动队列/RNG/预算和source。旧文件不可覆盖；拒绝须恢复参数与匹配QR/幅值状态，不能仅恢复q却留下trial的线性解。健康V32库不重训、不重建全部全场。按块保存变更，不为每次替换复制所有历史数组。

## 3. A/B：同一非神经起点、数学资格和小范围机制检查

### 3.1 唯一起点

两条新路线均从 **V32最终合格重建的FIXED_MULTISCALE_WAVE_BLOCK** 的1377列/246块启动，不使用LEARNED终态、旧监督库、M3600、best或last_trial。选择固定控制是为了让共同前缀不含神经方向训练，并隔离“在同一现成波动库上加入非线性学习”的增量；不是用较低参考误差动态挑初值。该benchmark已经被看过，仍非盲测。

从[run index](outcomes/records/run_index_v32.json)、[provenance](outcomes/records/provenance_v32.json)定位最终实际实例和最后QR修复，不猜文件名。读取后在design固定committed/state/model/每块地图/QR/native/moments的hash和实际起止source。核对native约0.157431767049、完整模型重建及r=f−Ac。沿用已验收基线字段，不能仅数1377就通过。

原packet hash为`2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215`；材料表为`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。M5几何、5nm Si n=0.99396854453+0.00435380777i、掠角1°/phi0/s、原双Floquet、40端口、384hex/p3、体/DtN q15及网络q30/末态q60均不变。逐项对照[原task](task.md)，不从新元数据重造不同物理。

缺文件先查本任务已声明的封存副本；确实缺关键初态时保留DATA_UNAVAILABLE并完成独立小测试，不从零再训练数小时或用另一条模型替代。不重新求V1准确参考；参考向量不进入A/B/C。启动身份检查/新模块资格不是单独交棒点。

### 3.2 必需资格与准入

| 检查 | 数值/合同 |
|---|---|
| 合成复数非Hermitian、已知波动相位、重复/近相关列 | 活动消元与独立完整最小二乘场/残差≤1e-10；rank变化明确 |
| 删除/更新QR与独立重新QR | 因子和投影配对≤1e-10；包含活动块位于首/中/末及带置换；不得保留活动列在Q_F |
| 真实当前q零变化 | 还原原全系数/残差/网络≤1e-10；发生秩变必须先解释，不能默认新起点 |
| q导数 | 3个非零实方向中心差分，在h=1e-4/1e-5/1e-6的稳定区≤1e-5；报告绝对量，禁止只测零幅值 |
| global/粗/中/细与完整矩 | 点值、Piola、方向、MPC一次展开，及原A/A*配对≤1e-10；反变换含所有内部矩 |
| 保存与拒绝 | 部分线搜索、QR刷新、序列化、断连后恢复一致；committed/trial隔离；1个实际短块闭环 |

允许基于同一起点考察预登记4个活动块：全域、粗、中、细各按原block id最小者，没有该类则明确缺项并按下一类/id补齐。最多4×8次完整q试探，所有参数/幅值/QR恢复后再分叉C。给出原残差对旧q是否仍有梯度、是否出现稳定下降和操作成本；**它只排除“这些方向显然不能动”，不证明整体驻点或唯一根因**。即使一个块无下降，只要共同实现合格仍继续其余预登记块和C，不因一项局部负结果终止整批。

A/B共软分配3h；只做本次数学/数据/事务的targeted测试，不full pytest、重装环境、重渲染旧页或重复V32覆盖/完整场。程序bug在同批定位、修复后继续；不能把测试数量作为数值完成。

## 4. C：定额列库的一对真实对照

| 路线 | 非线性方向改动 | 共同条件 |
|---|---|---|
| DETERMINISTIC_WAVE_BACKFIT | 无梯度的固定坐标pattern search | 同V32 FIXED终态、1377槽、全部幅值重求、相同活动队列规则 |
| LEARNED_VARPRO_BACKFIT | 真正计算上述导数，以有界L-BFGS-B重学已有q | 不强制非零改动；必须记录导数/实际q变化和原方程下降 |

这不是“神经对照一个什么也不做的旧终态”。两条都在同一参数化波动表示里调整q，控制用无梯度确定性搜索；严格说，这不是纯粹“有无NN”的消融，而是梯度驱动特征学习与确定性无梯度优化的算法对照。它能证明的只是这项更新机制的增量；广义NN资源收益仍须相对最佳合格非神经方法验收，不能凭路线名称授予。V32旧LEARNED只作历史背景，不重跑。

### 4.1 固定队列、容量和训练设置

本批seed=4213301，随机性只用于已登记的定向测试或确定性并列处理，正常活动选择不按参考误差选点。每轮选16个不同活动块：先按全部当前q的无标签归一化梯度大小选8个，再按global/粗/中/细及block id持续轮转选8个，去重并补齐；计算梯度使用当前全幅值最小二乘状态和一次公共A* r后分块VJP，不构建全Jacobian。梯度得分为norm(k0*g_q)/sqrt(max(1,3*w))。两路线同规则但各用自己的当前状态；这项公共预选费用两边均计。列数始终不超过1377、波数和原窗口保持不变，不添加新方向列、carrier、复波矢、material网络或嵌入项。

控制每活动块最多32次完整目标评价：在q/k0的坐标上依固定循环顺序考察±delta，delta依第0/1/2/3轮为1/8、1/16、1/32、1/64，坐标过多按block id与visit id循环；每次只保留已经评价且改进的合法点。学习路线每活动块最多20次迭代、32次完整目标/梯度评价，L-BFGS-B、maxls12、maxcor10、ftol1e-12、gtol1e-10，q每分量界±4k0。实际调用显式守卫，seed/零变化/最后核验分别记账；不为result.x额外偷偷调用。无改进保留原q，不施加扰动凑“学习成功”。

每条最多64次活动块访问/2048次试探评价、**新增3h**，取先到者；资格和初始化小试验另列A/B，不重置C的加载/QR/setup/保存/审核时间。对照新增上限相同，串行执行，按同一初态精度评分；共享工作站不构成独占性能实验。

一次活动块试探内固定U_F和投影；接受后更新相应模型列并重新确定全部幅值。新增q不是在旧完整Q上投影的“新列”。每个接受点须原作用残差与约化预测≤1e-10配对，原残差不得超过上一完整状态加1e-10；不能单凭局部loss下降接受。修改q可能改变数值秩，失败先回滚并记录，再减步/换块。最多每路线2次无数学改变的完整AU刷新；若频繁依赖全量重建，应标执行成本无利而不是无限重复。

### 4.2 及时验场与科学分流

30/60/120/180分钟及16次块访问的最近完整状态保存。每条在60分钟或16访问先到时，独立验原方程和散射E/H标量；只有完整边界可审核，不能中断线搜索后把trial当checkpoint。训练不接收参考向量/误差图，只收到预登记的标量继续判定，明确reference_used_for_validation=true和continuation_uses_validation_scalars=true。

若首个60分钟/16访问检查点原残差没有减半且散射E/H都未低于1%，继续到120分钟或32访问先到的下一个完整边界再确认；该条件仍成立则记录BACKFIT_NO_USEFUL_PROGRESS，结束这一候选并完成另一条和终验，不花满3h、不改loss/列数救结果。该阈值是投入控制，不是数学无解证明。未触发早停可在原上限继续。学习梯度正确但找不到合格方向是科学结果；普通保存/导数/QR bug则同批修复，不混淆。

原残差目标1e-8，到达即联合验收；原方程已过而场未过，可仅按原r继续到1e-10，仍不读取参考误差方向。不能用“冻结参考场拟合”替代求解，不能调用传统完成器覆盖c。两条最终均失败则关闭这份固定容量回拟合配置，不自动下一轮换优化器/seed，给明确数值和成本裁决。

## 5. E：联合Gate、同起点成本和部署边界

| Gate | 不变的完整要求 |
|---|---|
| 方程 | full native、原未凝聚增广、独立total原方程各≤1e-6，原RHS分母 |
| 场 | 同p3参考total/scattered E、H/scaled-curl、六点复场、全部40复通道各≤1e-4 |
| 功率 | R/T/A/A_volume误差和独立体吸收闭合≤1e-5；逐级功率≤1e-6 |
| 映射/约束 | 原点值模型→完整矩、MPC、端口恢复各≤1e-10；全部内部未知量 |
| 求积 | 网络q30/q60、其对应原A作用及FE场积分q15/q30相对变化≤1e-8 |
| 标签 | 不读teacher/参考向量/监督模型；reference_used_for_training=false，benchmark_previously_seen=true，验证参与如实声明 |
| 神经贡献 | 同完整精度相对最佳合格非神经控制，完整必要时间或同时峰至少改善20%，另一项合规 |

实际点值网络与producer分别验收，不按参考误差挑best。未过原方程的新R/T/A一律diagnostic。已经合格的原参考和V32完整评分只读复用；每条新终态才重建与独立评分，不重跑历史全链。

研究正信号另设：在m不增长、地图稳定且同成本可比时，学习终态native/augmented≤0.0157431767049（起点十分之一）、散射E/H均≤0.01，且相对于新控制两类误差均不恶化。它仍不是G_NUM通过，也不授目标资源资格。若两方法均改善，单列共同的回拟合收益和学习增量；不得只报更快的QR或更少参数。

两条新流程都继承V32 FIXED必要前缀。已知loaded-packet保守前缀10186.178641493432s，终验及未测准备另列，完整冷N=1仍UNKNOWN；在两种部署路线的归属账中各算一次，在项目实际累计中不重复收费。旧LEARNED的12180.0578s不是本新方法必需前缀，属于保留历史研发费用。相对历史传统672.462895s/1245822976B，不能把只从checkpoint开始的新增秒数说成冷加速。**即使这次数值通过，已付前缀仍不支持单次小案资源竞争力；必须明确NUMERICAL_PASS_NO_VERIFIED_NN_RESOURCE_GAIN，而不是NN20。**

U/Q基存储仍为32Nm字节。固定m是抑制继续增长，不是消除N依赖；N=1e7、m=1377时仅U/Q=440640000000B，尚不含A/R/临时/系统。该N是形状示例，不是实际目标DoF。禁止以此声称原尺寸装得下、训练会在48h内收敛或本架构已可扩展。目标需要的N/精度/完整时间尚未测明。

## 6. D：联合通过后才执行同机制0.7nm缩小三维pilot

只有LEARNED_VARPRO_BACKFIT实际通过M5全部数值门，且剩余至少7200s含独立验收，才自动进入D；否则明确NOT_RUN，不能以5nm低于几个百分点替代。

M5所有长度×0.14，保留真正三维缺口；使用统一表0.7nm n=0.999885140474+0.00000432477054i，exp(-iωt)、epsilon=n²、mu=1。这是新物理身份，重新绑定网格、面积、背景、全部实际模式/参考和自然尺度；不用W1另一Si值，不硬套40模式。[multiscale源码](../../src/solvers/neural_wave_multiscale.py)的±4×2π/5.0限幅应改为实际k0并做5nm回归和0.7nm单位测试；该硬编码在M5本身正确，不解释M5失败。

允许将本批无标签合格模型的原始窗口中心/半径×0.14、q÷0.14作为该pilot的初始化，必须重新积分全部矩并求当前材料下的幅值，不能直接缩放旧FE系数充答案。标TRANSFER_FROM_UNLABELLED_M5并归属全部5nm前缀费用；这是本小pilot一次许可，不是生产初始化授权。采用同一固定容量回拟合机制，独立新参考只用于评分；生成小case所需packet/一次既有直接参考可做，不新建传统引擎。

D的算子/求积/物理门同类重算。0.7nm同离散通过不证明连续解、h/p/端口收敛；已有p3平面波插值误差必须并列，不把神经点值准确冒充有限元场准确。不因D未准入或未过而去跑原尺寸、p6/h扫描、全口面或更多材料。剩余不足时保存可复现数据与明确NOT_RUN，不新开第二窗。

## 7. 执行、资源和bug恢复

新连续43200s，从首项实际准备计入阅读/实现/测试/等待/失败/学习/保存/验收/交付。A/B软3h、C两条各≤3h、条件D软2h、E软1h，至少1800s总终验预留；C的3h不能单边扩大或重置，其他软配额可在同窗调配。研发窗不是目标单案48h。历史成本/旧失联/未保留细分和UNKNOWN不删除、不补0。

没有“第三个bug后交棒”规则。schema/path/序列化/QR更新/复共轭/参数反变换/角色/保存错误，按failure→hypothesis→minimal change→targeted test→resume同批推进；健康初态、已接受替换和原参考不重训/重求。卡在一个模块时完成独立模块、控制及已获许可的验收。不得以正常不收敛冒充bug反复重置算法，也不得更换物理/误差分母凑PASS。

CPU-only、MPI1、数学/Torch线程1，一个现场合格物理核；数值树warn12/hard16GiB，light2GiB，含临时副本规划≤12GiB，自身swap/OOC0。保留max(128GiB,10%有效总量)+384GiB邻增长+自身预算；实际安全不足停止自身受影响链，不修改邻项目、全局库、锁/affinity或PSI阈值。成功必需60s PSI检查计总墙钟，不恢复旧1200s观察次数卡；拒绝后的额外前台等待/重采样合计≤1800s，不后台抢跑。

数值QR删除/刷新/真实梯度必须按数值角色16GiB准入，不能再把它误归2GiB纯元数据而重复触发停止；轻checker不因名字含QR就自动获得重额度。先做角色/真实执行依赖测试，不修共享默认。复用durable launcher/watchdog，全树计时含导入/setup；150s前收口、至少120s保存。断连先识别仍存活的原作业；已退出从完整边界恢复，不重复启动或清零费用。

项目库和Git写入只在canonical。新readout训练可复用NumPy/SciPy解析梯度，不因为没有GPU或Torch导入问题重装系统。数值核心入src，runner薄编排；stage通过正式one-run入口。网页/文档显示错误有限修复，不能阻断科学计算或重做历史渲染。

## 8. 输入、提交、证据和关闭条件

读取当前根/目录AGENTS、仓库原则、原task、最新V31 review、V32 response/summary和本报告。先确认无本任务活跃run、branch/HEAD/worktree/锁；只精确fetch并ff-only同分支，不新clone/分支，不reset/stash覆盖不明改动，不amend/强推/merge其他分支。保留已有参考输入和历史；本review已回应新response，故新增V32，不覆盖旧V31。

建议顺序：C1冻结初态与最小机制测试；C2完整backfit/QR更新和保存适配；C3两条有界真实路线与独立验收；C4条件0.7及一次交付。每个正式数值阶段之前clean实现commit，源码SHA与后续文档HEAD分开。

新stage先实现/validate再按依赖串行使用：

```text
input/task042extra_feinn_5nm/v33_backfit_anchor_checks.dat
input/task042extra_feinn_5nm/v33_backfit_math_checks.dat
input/task042extra_feinn_5nm/v33_deterministic_backfit.dat
input/task042extra_feinn_5nm/v33_learned_varpro_backfit.dat
input/task042extra_feinn_5nm/v33_backfit_reconstruct.dat
input/task042extra_feinn_5nm/v33_backfit_compare.dat
input/task042extra_feinn_5nm/v33_0p7_transfer_prepare.dat  # 条件D
input/task042extra_feinn_5nm/v33_0p7_transfer_backfit.dat  # 条件D
input/task042extra_feinn_5nm/v33_0p7_transfer_compare.dat  # 条件D
```

使用已有`python scripts/launch_task42extra_durable.py <one-run.dat>`选正确FE/ML环境并调用`scripts/run_case.py`；实现最小role/spec注册，不把新输入塞进旧窗口绕过守卫。一个dat一次明确计算，不能将两个候选藏成同一run。每段清场后再下一项，不并发启动全部输入。

交付`response_v33.md`、`outcomes/fixed_capacity_backfit_v33.md`及compact design/anchor/梯度-QR资格/逐次替换/完整Gate/费用/repair/run/provenance记录；一份完整原数组hash索引即可，不向多个JSON重复复制万行。每run保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/source hashes、run_summary.json及环境/MPI/资源身份。README/summary页首先写新结论，历史保持；同步本分支progress、模型总账、tests、changed_files。缺失的实际nit或试探计数标NOT_RETAINED，新轮明确记录，不重演旧学习补日志。

首次出现的方法要解释“重学已有波，不再靠加列；每次试探重求全幅值；成本含QR维护与所有前缀”。最终首先回答：是否改变已有q而非只重求幅值；M5是否通过全门；与同一起点强控制相比NN是否有贡献；固定容量是否仍不足；0.7条件pilot是否运行及精度边界。原样配置失败、前缀成本不竞争、数学不可能是三个不同结论，不混称。

本次审阅端只做小型复数代数/导数/QR删除检查，不是M5资格；浏览器完整视觉未获得就标NOT_VERIFIED。Codex有限检查新关键页，普通显示错误同批修复，禁止以网页错误替代数值停止。

只推`git push origin HEAD:refs/heads/task42extra_feinn_5nm`。授权矩阵完成、联合数值/成本裁决完成或明确科学/硬出口后，一次报告Response V33、准确HEAD/tracking/ahead-behind、clean和自身清场。不得给其他支线安排任务。**若本次固定容量重学习仍无实质收益，关闭该候选，不自动再发同类延时/优化器任务维持支线；原尺寸目标仍未资格。**
