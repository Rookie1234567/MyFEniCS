# Review V8：V10审查、稳定线性头与有限变量投影试验

## 0. 决定、快照和所针对的障碍

**接受V10作为固定特征空间的多路径负结果与有限诊断，不授予求解器资格。下一批先检验线性头的实际回收能力并建立数值稳定的坐标，再直接开展少量隐藏特征更新。取消“固定空间必须先达到物理正信号，才允许改变隐藏特征”的前提；原方程、场、功率和资源的最终门限不放宽。**

要消除的障碍是：当前神经trace方法仍未在0.7 nm微型三维模型上得到合格解。V10固定隐藏函数后，直接求输出系数也未成功；但V10本批隐藏层更新实际为0（不否认V7曾训练过隐藏层）。因此必须区分薄矩阵求解不稳定、固定特征空间不合适和隐藏参数优化无效，不能继续仅在同一空间反复解系数，也不能把未运行的特征更新判成失败。

```text
repository                  = Rookie1234567/MyFEniCS
execution_branch            = task42_neural_coarse_inverse
worktree                    = /home/fenics/Projects/NN-Lab
review_date                 = 2026-09-30
reviewed_HEAD               = 6246b525077779e2f9a538beff3af9df70bdb8bf
reviewed_latest_commit      = docs(task042): bind published rendering and final V10 budget evidence
reviewed_commit_UTC          = 2026-09-29T15:22:24Z
original_base_SHA           = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review            = review_report_v7.md
previous_review_commit     = fe2d3f6730080e629daa712e99a096605bcbf947
latest_response_reviewed    = response_v10.md
V10_AB_source               = 1fb8a949bbed81f34645d96e80c7025a3b22ef4d
V10_C_and_D_source          = 6e564a66868374560dae66321564f3e767f5639c
V10_final_checker_source    = b6546d762f5749ceca24b28e60ad4c380adc6741
next_batch                  = V11_STABLE_HEAD_VARIABLE_PROJECTION
response_required           = response_v11.md
review_decision             = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
old_p4_inverse_route        = CLOSED_RESEARCH_NEGATIVE
material_state              = MATERIAL_READY_USER_SUPPLIED
final_0p7nm_48h_gate         = NOT_QUALIFIED
master_merge                = NOT_APPROVED
```

最终目标保持：约2 TB整机物理内存的工作站资源内，从一个新的真正非可分三维周期单胞出发，端到端48小时内得到合格0.7 nm有限元解。本批是该目标的求解器／表示可行性试验，不是参数扫描代理，也不是最大目标运行。约2 TB不是允许本研究占满的RSS；本批仍用16 GiB硬上限和原受控共享CPU配置。

本报告依据实际远程快照、V10合同／回应／原始记录和已审阅源码；没有SSH重跑工作站，也未读取全部ignored数组。下表measured来自仓库，条件数比例为derived，新实验均planned/not_run。ChatGPT本轮只新增本报告；实现、测试和正式运行由Codex完成。

## 1. V10接受哪些证据，不接受哪些推论

证据入口：[Response V10](response_v10.md)、[完整结果](outcomes/autonomous_neural_head_v10.md)、[候选比较](outcomes/records/candidate_comparison_v10.csv)、[表示诊断](outcomes/records/representation_diagnostic_v10.json)、[线性头与秩](outcomes/records/head_mapping_and_rank_v10.json)、[体算子分解](outcomes/records/volume_balance_diagnostic_v10.json)、[续跑决定](outcomes/records/continuation_checks_v10.json)、[费用](outcomes/records/resource_costs_v10.json)。

| 固定micro；无量纲measured | 原Schur | native | 散射E L2相对差 | 解释 |
|---|---:|---:|---:|---|
| A：NN7一个复系数＋40端口 | 0.912888118 | 0.687417356 | 0.634722559 | 原方程校幅相不足 |
| B1：已训练隐藏特征＋线性头 | 0.797693967 | 4.381516135 | 0.700726410 | 固定空间下未通过 |
| B0：随机隐藏特征＋线性头 | 0.797324192 | 10.964503374 | 0.732080199 | 未证明已训练特征优于随机基线 |
| C：B1空间＋精确Hhat端口闭合 | 0.798257630 | 0.309567327 | 0.697842386 | 端口固定尺度残差约6.51e-17，体场仍失败 |

方程门限1e-6、同离散场门限1e-4均未通过；能量闭合误差约0.071–0.114也不合格。V10的E、P没有准入，隐藏层更新为0，不能说变量投影或隐藏自适应已经失败。

| 诊断／数据身份 | 实际证据 | 结论边界 |
|---|---|---|
| 参考辅助固定空间拟合，measured | B1/B0散射E差约0.001025/0.001029，curl差约0.00320；对应Schur仍0.86366/0.87217 | 场拟合可明显优于方程拟合，但仍非合格解；使用参考ports，不是无标签求解 |
| P奇异值比例，derived | B1约5.13e10，B0约2.52e10 | 是输出系数到trace的薄矩阵条件数，不是整个S条件数 |
| W奇异值比例，derived | B1约3.29e10，B0约1.59e10；输出系数范数约1.76e5/1.30e5 | 数值满秩不等于精确最优；须检验大系数与实际回写稳定性 |
| 原体算子分解，measured | LSQR8误差curl/负质量各约10.402，相加V约0.04745；重组operation差约1.7e-14 | 原波动项平衡，不是可以删除的错误，不证明全系统奇异 |
| V10资源，measured | 12次formal launch共650.093757705s；同时采样树峰2376962048 B，swap0 | 本次不是耗尽7小时或16 GiB；不能推算目标模型已可行 |

保留V8批量化和停机事务。修正新记录中的过强字段：`rank == columns`只能命名为`numerical_full_column_rank`，不能继续生成`exact_full_space_optimum_claimed=true`。旧raw逐字保留，用新解释引用。V10最初只有一个映射见证、三见证补核晚于冻结的时序偏差保留，本批相关前置检查必须在候选前完成。任务README的旧“当前V8”导航不作为权威；允许仅新增最新入口和历史说明，不重写旧任务／review。

## 2. 范围覆盖、冻结身份与数据边界

先读根／目录AGENTS、仓库工作原则、原task、全部补充合同／review及最新response/outcomes。原task与旧review不改。本报告明确覆盖Review V7中“必须P/P+才进入隐藏更新E”的限制，并用下文3–5次变量投影外层更新替代其50步冻结头交替Adam；不重开旧p4 PC、列尺度扫描或全部V10分支。

| 固定项 | 值 |
|---|---|
| 方程与离散 | Full3D complex128，原Nédélec H(curl)，单层静态凝聚，384 hex，p3，h=0.175 nm |
| 物理 | 真空0.7 nm，grazing1度／azimuth0／s，原三维缺口，双Floquet及Fourier-DtN |
| 数量 | full FE34050；trace18144；内部13824；slave2082；40复端口；reduced18184 |
| 材料 | `input/materials/si_optical_constants_v1.json`；`SI_OPTICAL_CONSTANTS_USER_20260929_V1` |
| 材料SHA256 | `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2` |
| physical SHA | `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de` |
| mode SHA | `93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262` |
| action packet SHA256 | `9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454` |
| REF7 NPZ SHA256 | `a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355` |
| 神经结构 | 原3×64 tanh／8固定载波／FP64／q15／batch8；hidden实参数8576，head复系数1560 |
| 本批唯一主起点 | 原seed420906随机隐藏初始化；不使用NN7预训练、D1参考fit或参考场作初值 |

Si仍为n=0.999885140474+4.32477054e-6i、epsilon=n*n；保留source0.699999988→nominal0.7精确别名。材料已ready，不再索要、不联网替换。原空气／mu／上下20+20通道、键与参考面均不变。还有具体master顺序、矩包、背景、RHS和参数hash须现场核实，不能只对物理标签。

本批可读取已有B0的P/W、随机hidden参数及**无标签方程求出的B0系数**作稳定性见证；这些不包含准确解。主候选从随机hidden和原物理b开始。REF7、V10-D1拟合权重、由参考推得的幅相／误差均禁止进入构造、梯度、选步和选择checkpoint。新的求解队列全部冻结并退出后，独立验证进程才读取参考。已看过历史诊断，不能称fresh blind study或未见几何泛化。

## 3. 执行顺序：短入口后实际改变特征

| 阶段 | 工作与准入 | 完成后的动作 |
|---|---|---|
| S0 | 身份／artifact／原端口代数、复数小测试、预算监督 | 复用已合格部分，不重建F0 |
| S1 | 两个空间内制造问题；原B0头与稳定坐标回收对照 | 原头失败而稳定头通过可继续；稳定头失败则转定位 |
| S2 | 随机hidden＋精确端口闭合的稳定线性头基线 | 即使物理残差仍高，也准入导数检查 |
| S3 | 每个扰动点重求头的完整VarPro导数资格 | 通过后直接进入S4，不要求场误差先小于0.5 |
| S4 | 前3次被接受的隐藏外层更新；有原方程进展才允许再2次 | 每个试探点重建该点头；最多5次，不盲目续时 |
| S5 | 队列冻结后独立同离散场／功率审核；失败则有限定位 | 给出一个下一步；不再开启参考反馈训练 |

若S1或S3数值资格失败，不能为“多做工作”使用不可信梯度；但应完成已授权的稳定性／误差闭环并记录原因，不只输出all-not-run。若所有前置数值资格通过，不得以旧P/P+未通过而再次只做诊断收口。

## 4. 方程、稳定坐标与唯一线性头算法

### 4.1 保留精确40维端口闭合

按原action的实际符号分块，H明确是凝聚后的Hhat，不是原Hp。定义只用于作用，不物化整个消元矩阵：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\quad
b=\begin{bmatrix}b_t\\b_p\end{bmatrix},\quad
\bar S=K-CH^{-1}F,\quad \bar b=b_t-CH^{-1}b_p,\quad
\alpha(t)=H^{-1}(b_p-Ft).
```

复用V10的原块重组／非零小solve／梯度证据，仅重验受新增代码影响的接口。cond2(H)≤1e10、小solve operation residual≤1e-12和完整40端口要求不变；只缓存这40维小分解与40列原作用，禁止全局FE/p4逆、ILU、Riesz逆、隐式fallback。H不安全时停止本条依赖路径，不删通道或加移位。

### 4.2 为什么给神经特征换坐标

P的很多列几乎线性相关，直接使用巨大且抵消的输出权重会放大计算误差。本批用同一空间的正交坐标求头，然后返回真实网络权重。它解决表示坐标的稳定性，不添加新物理方向；精确算术下不能凭换坐标降低原空间的最优残差。

对每个hidden参数psi构造原q15矩映射P，做**非pivoting、economic Householder QR**。不构造18144×18144的full Q，不形成PᴴP。R是1560×1560三角矩阵；用R的奇异值记录P的数值秩，固定相对阈值1e-12，不能只看对角线作秩证明。

```math
P_\psi=Z_\psi R_\psi,\qquad Z_\psi^H Z_\psi=I,\qquad
A_\psi=\bar S Z_\psi,\qquad
c_*(\psi)=\arg\min_c\lVert\bar b-A_\psi c\rVert_2,\qquad
\gamma_*(\psi)=R_\psi^{-1}c_*(\psi).
```

R逆只用三角求解。A逐列以原S和小H作用得到；**不得用旧的W乘R逆来替代新的原作用**，否则旧列误差可随病态坐标变换被放大。每列等效S和每次小solve均计费，最多16列一块。40个port列可原样复用，不重新1600次跑MLP。

A的线性最小二乘固定`gelsd, cond=1e-12`，不形成AᴴA、不扫阈值／正则项。P与A都须数值满列秩，才使用下文简单常秩VarPro梯度；若原点掉秩，报告`HEAD_RANK_UNSAFE_FOR_VARPRO`，完成诊断而不静默截断后继续冒充同一算法。试探点掉秩只拒绝该试探并按既定缩步规则处理。

先重算t=Pγ，再将γ写入真实Torch输出层、用batch8原矩映射生成t_net；alpha用t_net和原H重新闭合。**候选和loss以t_net为准**，Zc只作数值中间值。保留Pγ、Zc、t_net的差异；若它们不一致，不能仅报告最好看的Zc结果。

QR重建／正交性、普通三见证映射operation-relative≤1e-10。实际大系数头的物理trace一致性目标为相对≤1e-8，网络原残差与薄LS预测之差按固定原b尺度≤1e-8；这是新增内部数值检查，不替代最终1e-6/1e-4的物理门限。重复同点求值的loss差≤1e-10×max(1,loss)。差异超过限值时允许一次同一分解的残差修正，仍失败则停止该数值路径，不提高阈值。

通过A的economic QR得到U，检查Uᴴr和投影残差`bar b-U(Uᴴ bar b)`，但不得形成UUᴴ大矩阵。对当前实际网络残差，要求`norm(Uᴴr)/norm(b)≤1e-8`；报告原Aᴴr与归一化分母，不用巨大A范数把差掩盖。该驻点检查与完整方向差分一起决定导数能否使用，数值满秩本身不构成最优证明。

每个新psi都须重建其P、QR和A并重求头。初始P0可读取已冻结B0矩阵，但必须与原seed和三非零见证配对。稳定基线相对V10 B0改变了**坐标实现与端口闭合**，不能仅归因为隐藏学习；真正的隐藏更新收益以本批稳定基线作为对照。

## 5. S1：答案在空间内时能否回收

预登记两个无参考见证：M1为seed421101的非零复gamma/alpha，分别规范到欧氏范数1；M2为V10-B0保存的无标签头gamma和port，覆盖已测约1.3e5的大系数组合。M2文件缺失则只做M1并标覆盖缺口，不读取D1参考fit代替。测试不优化真实物理b，不称新的散射算例。

用真实网络回写得到t_m，构成z_m；**b_m必须通过原action.apply(z_m)产生，不能只用缓存W乘系数自己验证自己。** 对b_m分别做既有raw B0薄LS和本批稳定端口闭合头求解。制造问题的b_t/b_p必须全部使用b_m，不能混入物理b的端口常数。

原action packet不覆盖b。新增rhs-aware纯数组审核或显式计算用于制造问题；既有`audit()`硬编码原物理b时，不能直接拿它判制造问题失败。若需要完整未凝聚制造方程，先用齐次恢复R0 z_m得到场，再通过原体／端口作用构造对应全部RHS并核对凝聚为b_m。不重新使用物理内部特解来制造一个不相容的方程。

实际比较已知z_m与回收后的真实网络z：相对原制造残差≤1e-8；trace＋port系数相对差≤1e-6；两种齐次恢复配对operation-relative≤1e-10。已知非零误差的场L2/curl可用原FE轻量积分一次处理，不输出制造R/T/A。gamma差仅作诊断，不因病态坐标下gamma敏感单独判场回收失败。

记录raw和稳定头的原残差、系数／场差、QR重建、有效秩、输出权重范数及实际回写误差。raw失败但稳定头通过，继续S2；稳定头失败时保留真实失败，最多一次有依据的实现修正／受影响重放，之后只作定位。有限见证通过不宣称全部输入鲁棒或目标物理已收敛。

## 6. S2–S3：真正的变量投影目标和梯度

它要做的是：网络隐藏层负责提出空间函数，原有限元方程在这些函数中计算最好的线性组合；外层训练只改变函数形状。不是先固定错误的输出头连续训练50步，也不是用参考场教网络答案。

```math
\Phi(\psi)=\frac{\lVert\bar b-\bar S P_\psi\gamma_*(\psi)\rVert_2^2}{2\lVert b\rVert_2^2},\qquad
r=\bar b-\bar S P_\psi\gamma_*(\psi).
```

当线性子问题足够准确、局部秩不变时，驻点条件使输出系数导数项在**标量目标的一阶导数**中消失。psi是实参数，所有复共轭和实部必须保留：

```math
(P_\psi)^H\bar S^H r=0,\qquad
g_{\psi,k}=-\frac{\operatorname{Re}\!\left[r^H\bar S\left(\frac{\partial P_\psi}{\partial\psi_k}\gamma_*\right)\right]}{\lVert b\rVert_2^2},\qquad
\bar S^H=K^H-F^H H^{-H}C^H.
```

因此可在当前**重新求好的gamma固定**时做一次网络VJP，只取8576个hidden实参数梯度。复用`closed_trace_gradient`的原S/Sᴴ与40维伴随小solve；gamma/head不交给外层优化器，alpha也不作为独立训练变量。无需对整张QR/SVD计算图反传，不构造全hidden Jacobian或Hessian。这里是scalar-envelope梯度，不声称提供了完整残差Jacobian或Gauss–Newton。

**驻点不准或发生秩截断时，不能直接忽略dγ/dψ继续宣称精确VarPro。** 特别是QR本身的坐标变化已包含在完整头重求的目标里；验证时不能只对固定Z或固定gamma的loss作有限差分。

先在小型复数非Hermitian、非零port／仿射RHS例子上验证梯度，并演示跨参数点不重求head时计算的是另一目标。在线性头精确驻点，固定gamma的偏导恰好等于Phi的一阶导数，不能伪造两者在该点必不相等的反例；真实FD仍须重求头，以检验整个实施链。真实原点使用三个实hidden方向：seed421111/421112随机单位方向，以及解析梯度的单位方向；若梯度近零，用seed421113替代并记录。对h=1e-4、1e-5、1e-6逐点重新构造P/A、重求head、回写网络、闭合端口后计算Phi。可先做前两个h，已有稳定证据则不做第三个；真实FD最多18个扰动点。

每方向至少一个非零稳定区relative误差≤1e-5，并报告相邻h趋势、原/试探rank、实际目标复算差；近零用预登记absolute1e-10判断且不能三方向全为零充数。原点梯度已近零且不能给出可靠下降方向时记录驻点未合格，不把它当作解。梯度失败不是增加epoch的理由。

S1–S3通过后**直接进入S4**，无论稳定基线场误差是否≤0.5。本批不使用参考数组作为进入训练的条件。

## 7. S4：3次必试、最多5次的有界隐藏特征自适应

唯一主候选名`RANDOM-HIDDEN-PORT-CLOSED-VARPRO`。初始psi仍来自seed420906，头从S2原方程重求；不从B1/NN7或参考fit暖启动。不改层宽、激活、8载波、求积／MPC和precision。

采用仅针对hidden的有限记忆BFGS下降方向，history最多5；首步为负梯度。只在`dot(s,y)>1e-12*norm(s)*norm(y)`时保存曲率对，否则跳过该对；非下降方向确定性退回负梯度。这是外层参数优化，不是Maxwell全局逆。可复用已有工具／薄适配器，不能把新的数值实现全部塞入超过千行的runner。

每个方向d的初始步长及最多四个Armijo试探固定为：

```math
\alpha_0=\min\!\left(1,\frac{10^{-3}\max(1,\lVert\psi\rVert_2)}{\lVert d\rVert_2}\right),\qquad
\alpha_j=\alpha_0\,4^{-j},\quad j=0,1,2,3,
\qquad
\Phi(\psi+\alpha_jd)\le\Phi(\psi)+10^{-4}\alpha_j g_\psi^Td.
```

每个试探点都完整重求稳定头、重新回写、闭合端口和计算原loss；不在旧P/W上移动psi。内层rank／回写／有限值Gate失败算一次被拒试探及实际费用，不继续沿该错误状态。正常接受还要求下降超过`max(1e-12,10*delta_repeat)`，delta_repeat为同一点重复完整求值测得的**绝对loss差**。差分／降幅在噪声以下时记`NUMERICAL_PROGRESS_UNRESOLVED`，不造成功。

接受后立即提交psi、gamma、alpha、z、有限记忆状态、输入/source/hash及原审核；所有试探保留轻量记录。预算／异常恢复最近完成的**VarPro外层提交状态**，包括与psi一致的线性头与port，不能只恢复网络hidden。原V8事务可复用，已花次数／时间不回滚；试探与接受计数分开。

目标先完成3次接受更新；4次线搜索都拒绝、梯度不可信、秩不安全或预算触发时可提前停止并写具体原因。不得用“暂时没有P/P+”跳过这三次有数值资格的试探。第3次后，若原Phi相对S2至少下降1%，且native≤S2的1.05倍、port固定尺度仍≤1e-6，可再做2次，最多5次。此1%只决定有限延长，不是神经增量或物理通过。

接受点若所有原方程Gate通过，可提前进入S5。每个正常接受点都完整audit；试探点只做头／原Schur／端口及必要映射检查，避免几十次重复全场后处理。最终保存的是last committed，不按准确参考挑最佳点。

## 8. S5：冻结后独立验证、负结果分流

优化队列结束并冻结S2基线、所有接受状态与最终state/hash后，单独验证进程读取REF7。一次FE环境审核基线与最多5个接受点，复用原范数／通道／功率实现和背景；不把物理残差向量当场，不把default recover(e)当齐次误差恢复。不给优化器返回参考幅相、误差方向、梯度或选择建议。本批验证开始后不再回训，也不新增监督拟合。

严格标准沿原合同：原Schur/native/完整增广及规定端口残差1e-6；恢复1e-10、slave-zero；同离散total/scattered E/H、scaled-curl、selected复E/H及完整复通道1e-4；R/T/A/A_volume差1e-5；逐通道功率1e-6；能量闭合1e-5，近零absolute规则沿原1e-12并明确分母。失败场的R/T/A只能标`UNQUALIFIED_DIAGNOSTIC`。

以本批S2稳定随机＋闭合端口基线定义rho=max(Schur,native,port固定RHS)。**研究正信号**为最终rho至少减半，且散射E与scaled-curl误差均≤0.5且各至少比基线改善25%；只降低Phi则标`OBJECTIVE_ONLY_IMPROVEMENT`。这些阈值不是进入S4的前提。即使严格通过，也只取得本micro的同离散资格；本批不做新p4 enrichment或放大几何，保留连续误差和目标48小时unknown。

| 观察 | 本批应做的分流／表述 |
|---|---|
| raw回收失败、稳定头回收通过 | 固定坐标稳定性是实际因素；仍须新物理目标检查 |
| 稳定回收失败 | 限定检查rhs、薄投影、回写／大系数敏感性；不进入不可信隐藏训练 |
| 头稳定但VarPro FD失败 | 记录常秩／驻点精度／重求一致性原因；不伪称梯度正确，也不照常50步 |
| 隐藏更新让rho和散射场一起改善 | 形成有限表示学习正信号；把构造／分解／拒绝试探全部计入收益 |
| 原loss下降但场未改善 | 当前目标／受限表示仍有落差；不能宣称求解能力增加 |
| 数值可信而3–5次无显著下降 | 本固定架构短试验负结果，不继续无限epoch，不外推所有神经方法无效 |

允许使用已有矩阵／状态做有限故障分析：同点重复loss、实际网络与薄映射残差、投影／驻点缺陷、rank及系数增长；不新建全局谱／SVD、Jacobian谱、curl/mass诊断campaign或新PC。S1失败时最多补一个来自原算子与预登记seed421114的非零见证，不用参考错误方向构造“针对性成功”。明确实现bug最多两次最小修复／受影响重放；数值失败不算bug。

## 9. 资源、时间、作用次数和生命周期

本轮是一个新的有界实验窗口，不沿用已结束的V10起始时间，也不承诺再运行满七小时。**从Codex接手记录的新start起，总elapsed最多14400秒（4小时），包括实现、测试、构造、求解、诊断和交付；最迟start+13500秒停止重负载，最后900秒收尾。** 独立deadline/watchdog覆盖BLAS、JIT和全部后代；复用V10监督，只作必要短测试。不得因刷新上下文、分支或重试重置窗口。

V10的V6 onward已计有载11159.165418899036秒继续保留；新账与elapsed、各方法从零成本分开，本批上限替换旧批次窗口但不抹去历史。4小时是停止预算，不是ETA或成功承诺。

P/A的完整重建与线性头评估（含FD和拒绝试探）最多40次；薄LS分解／线性头完整重求总计最多48次；原S与Sᴴ合计最多65000次等效单向量作用（批矩阵按列计数）；任何实际更早预算先停。FD最多18个扰动点，外层最多5个接受点、每点最多4个试探。初始已保存数组复用不虚记为新构造，读写／校验成本仍计。每次重建前预检剩余时间及至少300秒安全清场余量，不能在临界时间启动不可安全中断的大分解。

保留受控共享CPU授权：其他heavy存在不自动阻塞；现场选空闲物理核并避开忙碌SMT；MPI1、所有数学/Torch线程1、DataLoader0，自有nonblocking锁、独立FE/ML环境和缓存，只对自己nice10/idle I/O。不使用GPU，不升级ABI/CUDA/BLAS，不改邻任务、环境、锁、亲和性、优先级或watchdog。一次仅一个Task042重阶段，绝不接管其他运行。

整树hard16GiB、warn12GiB；事前同时常驻规划≤8GiB；own swap0，无OOC。系统reserve=max(128GiB,effective_total的10%)，另留128GiB邻增长及本任务预算；磁盘自由≥50GiB，本Task artifacts总量≤20GiB。无cgroup委派则明确0.5秒采样并非内核连续限制。warning不再新分配大对象；hard/swap/持续压力/监督失效停止自身后代，不能为了保存巨大数组拖延安全停机。

P、Z、R、A、SVD/QR副本、ML图与FE packet、旧接受点／新试探点必须一起做峰值规划。避免同时保留多套完整P/W；初始／当前接受／一个必要失败见证的薄矩阵最多3套，其余试探只保留参数、gamma、port、z、hash与成本，临时工作矩阵按预登记生命周期释放。删除的是可重建临时workspace，不是旧负结果或已发布原始证据。若原旧artifact已接近上限，先采用不持久化新临时矩阵的方案，不擅自删历史。

micro正信号不能外推目标：P/Z/A存储随全局自由度与特征数增长；目标DtN、分布式、streaming／matrix-free作用和误差资格仍需另建模型。低内存失败、较便宜loss评估、满秩或小梯度都不是0.7nm／48h通过。

## 10. 实现、Git与证据交付

ChatGPT只提交本review。Codex复用`neural_linear_head.py`、`neural_linear_head_torch.py`、`neural_port_closed_head.py`、`neural_trace_batched.py`、事务／watchdog和已有验证器；新核心进入合适`src/solvers/`，runner只作薄编排。不复制每个FD方向或trial一套脚本、不重写普通default、不全仓清理。允许针对新功能的schema/profile和focused tests。

正式运行前提交clean实现，绑定实际source。`scripts/run_case.py`的一个dat表示单一stage、同一原物理模型与明确列出的见证／FD／外层库存；不得伪装隐含参数扫描。原始dat、resolved_config、run_manifest、input/physical/material/array/source hashes、run_summary和process-tree资源齐全。已有reader硬编码b的地方只增显式opt-in接口，不改历史语义。

提交计划：C1稳定头／rhs-aware制造审核及小测试；C2完整VarPro导数与接受/回滚；C3有界真实试验、冻结后验证；C4 compact档案。每次运行在clean commit后，不为活跃run的文档发布改变受检HEAD。阶段间可安全提交并继续已授权队列，不需逐步等用户确认。缺少一个历史向量只影响依赖它的见证；不得自动重跑V7–V10或准确参考。

最少交付`response_v11.md`、`outcomes/stable_head_varpro_v11.md`及可适度合并的compact记录：

```text
plan_and_input_identity_v11.json
manufactured_recovery_v11.json
stable_head_checks_v11.json
varpro_gradient_checks_v11.json
varpro_progress_v11.jsonl
candidate_comparison_v11.csv
qualification_and_dispatch_v11.json
run_index_v11.json
resource_costs_v11.json
```

记录各trial的psi/head/z身份、rank、QR／驻点／回写缺陷、Phi／原残差、步长、接受原因、累计重建／S/Sᴴ／LS/QR／VJP数及deadline余额。试探和接受不能混称迭代；分量计时与父进程总wall不重复累计。独立checker从原字段重算资格并有损坏反例，不能只信saved status；保留既往Gate时序偏差说明。

同步本Task的README最新入口、summary、test_summary、changed_files，以及development_progress和development_model_registry。保留task、Review V1–V7、Response V1–V10及旧records，不以导航整理删除负结果。新的强字段替换不回写旧raw。

正式Markdown使用fenced math，表格列一致；本地结构检查不冒充GitHub rendered view。实际页面不可取时明确未核验，并交由Codex补查；不因此停止已经授权的数值工作。无需PDF或整仓文档迁移。

仅推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`；不amend、强推、merge/rebase master或其他分支。结束于总截止、安全停止或所有授权路径完成后，报告完整HEAD、工作树／upstream、actual source、是否真的更新隐藏层、制造回收与梯度、最终物理差、全部费用及唯一下一建议，然后停止等待review。**本报告不批准生产默认、最大模型、p4新参考或合并master。**

## 11. 方法依据与适用边界

[Dong与Yang的神经PDE变量投影研究](https://arxiv.org/abs/2201.09989)提供“消去线性输出系数、优化隐藏参数”的组织方式；本文采用原有限元残差与精确小端口闭合，不继承其配点实验的精度或收敛保证。上述复数标量梯度由驻点条件和链式法则推导，必须经过本任务真实FD。

[Netlib ZGELSD](https://www.netlib.org/lapack/explore-html/d9/d67/group__gelsd_ga7da8d56f14942ae8cb9e0d681f6c4e20.html)定义有效秩及相对奇异值阈值；[SciPy QR](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.qr.html)说明economic Householder分解。使用现场已有合格版本，不为追随在线文档升级库。正交坐标、制造问题通过或数值满秩均不保证隐藏优化或完整Maxwell求解成功。

**本批的关键改变是：先保证计算可信，然后允许网络真正改变表示。固定空间没有好解，是尝试改变它的理由，不再被用来禁止这一项有限试验；但数值接线、导数不可信时，绝不能靠延长训练绕过。**
