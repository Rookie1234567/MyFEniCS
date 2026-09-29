# Review V7：V9审查与七小时自主分支试验

## 0. 决定、目标与授权

**接受V9作为固定误差诊断，不授予求解器资格。下一批不再只重复诊断：根据“NN主导场形状接近、幅值与相位未到位”的新证据，执行原方程驱动的幅值／端口校准、神经线性输出层求解和随机特征对照；必要时进入精确端口闭合、有限隐藏层续训、失败定位或成功后的精度验证。**

用户本轮明确授权约7小时脱离人工监督的持续工作。本报告给出可自动选择的有限路径；一条路线的数值负结果不终止其他已授权、相互独立的路线。安全、身份或算子实现失败仍须隔离处理，不因无人监督而绕过。

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task42_neural_coarse_inverse
worktree                  = /home/fenics/Projects/NN-Lab
review_date               = 2026-09-29
reviewed_HEAD             = 120161581b69741e3e059582c3f7179b7036c337
original_base_SHA         = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review_commit    = 0071b97cc60996010c97671c5a1e620783af412e
previous_review           = review_report_v6.md
latest_response_reviewed  = response_v9.md
V9_run_source             = a1dc3466294c30b6de292468d6dd1aa9b685b193
V9_checker_fix_source     = e21af767d3522af531ad83c45eacc1df252566c9
next_batch                = V10_AUTONOMOUS_NEURAL_HEAD_AND_PORT
response_required         = response_v10.md
old_p4_inverse_route      = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate       = NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

目标仍是：约2 TB工作站资源内，从新的真正非可分三维周期单胞出发，端到端48小时以内得到合格0.7 nm有限元解。本批仍是同一个micro-pilot上的方法试验；没有资格时不得扩大到最大目标，不转成扫参代理。

ChatGPT本次读取了远程V9回应、原始场／方程分量、最新summary、既有合同和实际网络代码，没有在工作站重跑向量。下列数值是已提交的measured证据；新路径及其预算属于planned，不是完成声明。

## 1. V9证据与本次取舍

依据：[Response V9](response_v9.md)、[summary](outcomes/summary.md)、[场分量](outcomes/records/field_error_components_v9.csv)、[方程分量](outcomes/records/equation_components_v9.csv)、[恒等式](outcomes/records/error_identity_checks_v9.json)、[费用](outcomes/records/resource_costs_v9.json)。

| 同一0.7 nm／384hex／p3对象；无量纲measured | NN7 | LSQR8 | 解释 |
|---|---:|---:|---|
| 原Schur残差 | 0.913263145 | 0.068283274 | 均远高于1e-6 |
| native残差 | 0.661163226 | 0.026675036 | 原方程未满足 |
| 散射场L2相对误差 | 0.661250637 | 0.998598491 | 均不合格 |
| 散射场范数／参考范数 | 0.457258801 | 0.003670880 | NN已有可见场，LSQR幅值非常不足 |
| 与参考的复相关模 | 0.999809495 | 0.421460709 | 高相关不是准确幅值、相位或残差资格 |

NN7相关系数为0.843978513-0.536021731i；误差主导y分量且遍及全域，不只在缺口附近。其相关模接近1仍留下非零形状误差，不能承诺一个复标量就达到1e-4场误差。LSQR8误差的Schur残差平方约99.9537%在trace行；只盯端口operation-relative也不够。

V9核实Se=r-r_ref最大差2.925e-12、齐次恢复3.082e-16，未发现足以解释现象的数据／正确恢复错误。错误默认recover(e)会额外加0.001203391的内部特解，已被测试捕获；这不是旧候选场恢复被证实错误。体／端口抵消和方向增益不等于全局条件数或奇异性证明。

保留V8 batch8等价实现及约48.55%的共享微基准降时，保留停机事务。列尺度试验不再扫描。**不接受“再量化一次curl/mass抵消”作为本批唯一工作；这项诊断放到失败分支，主队列必须尝试实际改进求解。**

## 2. 权威、冻结物理与明确覆盖

先读根／目录AGENTS、仓库原则、task、全部既有review与最新response。旧文档不修改。本报告依据本轮用户授权，明确覆盖Review V6的“只诊断、不得新训练／求解”、Review V5的“不得使用旧NN状态续研”、旧批次次数与时间上限中与本批冲突的条款，**仅限下列列出的路径**。原材料、精度、进程隔离、负结果保护和禁止合并仍有效。

| 冻结身份 | 值 |
|---|---|
| 物理与离散 | Full3D complex128；原Nédélec p3；384hex；h=0.175 nm；真空0.7 nm；grazing1度／azimuth0／s；原三维缺口与双Floquet／Fourier-DtN |
| 未知量 | full FE34050；独立trace18144；内部13824；slave2082；40复port；reduced18184 |
| 材料表 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1 |
| 材料SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| Si／alias | n=0.999885140474+4.32477054e-6i；epsilon=n*n；source0.699999988→nominal0.7 |
| physical SHA | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| mode SHA | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action packet SHA | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| 既有p3参考NPZ SHA | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

其余数组／参数／master顺序从run manifest实际核实。不再索要材料、重装ABI、重做F0或原三条长试验。旧p4强逆、POD残差PC、seed420620、其他波长、GPU和最大模型保持不执行。

**数据分层：**S、b、几何、材料、无标签训练产生的NN7参数可作为求解输入。本批明确允许以NN7为一个已知候选重新校准或续研，但V7接受状态UNKNOWN保留；旧optimizer状态不可猜造。REF7和V9由参考得到的误差向量不能成为求解、选方向、系数校准、初始化或训练loss的输入。研究设计已看过V9诊断，不能称全新blind study；每个新候选仍须先冻结，再由独立验证进程读参考。

## 3. 七小时自动调度合同

### 3.1 时间含义

Codex接手后记录批次start UTC、Asia/Singapore时间和单调时钟；**本批总elapsed最多25200秒，含实现、测试、设置、求解、诊断和交付，不是每条路线7小时。** 首次正式子进程前建立独立自有deadline/watchdog，进程退出或对话中断也不能留下无期限worker。

数值重负载最迟在start+23400秒停止，最后1800秒只做允许的低负载核对／保存／提交。不得在剩余时间不足“该阶段实测保守耗时＋退出余量”时启动不可安全结束的BLAS、JIT或参考分解。阶段上限和总截止同时生效，所有失败和重放计费。

V9累计有载账10209.145962639828秒保留。本次7小时是**用户新增授权窗口**，不再因旧10小时累计上限不足而截断本批；同时另记历史累计及每条方法的端到端成本，不能清零历史或把研究预算称为48小时目标已通过。

### 3.2 队列与分流

| 路径 | 默认顺序／准入 | 单路径上限；不是ETA | 结束后 |
|---|---|---|---|
| N0 | 身份、资源、薄调度、最小数值接线 | 准备实现累计优先控制在5400秒内 | 分支接口可用即先执行，不要求所有后备实现完才运行 |
| A | NN7 trace方向＋完整port校准 | 900秒，原S最多48次 | 正／负都继续B；缺NN7则跳A而做B0 |
| B1 | NN7隐藏特征，线性输出层直接求解 | 3600秒，S最多1700次 | 独立验算；继续随机基线B0 |
| B0 | 原seed随机隐藏特征，同样线性头 | 3600秒，S最多1700次 | 与B1对照，不把随机特征收益算成已学习隐藏层收益 |
| C | B未严格通过时，精确40维端口闭合＋同输出空间 | 1800秒，尽量复用B1作用；新增S最多100次 | 正信号进E，负信号进D；H不可安全求解则跳C |
| E | 至少一个新候选有§4进展信号且未严格通过 | 最多2轮，每轮50个隐藏层更新＋一次线性头重求；总5400秒 | 一轮有进展才准第二轮；无进展保存后转D |
| P | 任一新候选严格通过 | 资格复核和至多一次同网格p4参考，最多3600秒 | 记录离散误差；不扩大几何／MPI／目标模型 |
| D | 主要求解分支结束后，负结果或仍有未解原因 | 两个互相独立子项各最多1200秒 | 允许失败后继续另一子项；本路径之后不再回训 |
| F | 无可继续路径或接近截止 | 最后1800秒优先保障 | compact交付、清场、push，不merge |

**各路径上限不能相加理解为全部额外时间。** 正常顺序N0→A→B1→B0；若严格通过优先P，否则B失败仍应尝试C，C/B有进展则E；最后D/F。B0实现复用B1，仅换冻结隐藏参数。已合格对象不反复训练；无信号也不只写一句失败便终止整个队列。

无需逐步骤向用户确认。允许每条路径最多两次明确实现错误的最小修复，全批最多四次，时间仍计入；数值停滞不算实现错误。不允许动态增加网络宽度／载波／seed／loss权重网格。某分支blocked时记录具体原因，执行其余独立可做分支。资源紧张先停止自身负载；最多三次、间隔不少于5分钟的有限只读复核，均在总截止内，不写永久等待器。

## 4. 共同验算与正信号规则

所有正式候选使用同一原S、b；先保存参数、z、source与hash，再由验证进程读取既有REF7。不得用参考挑checkpoint或回填复数幅相。严格资格沿用Review V4/V5：原Schur、native、完整增广及端口各规定残差1e-6；恢复1e-10、slave-zero；同离散total/scattered E/H与scaled-curl、完整复通道1e-4；R/T/A/A_volume差1e-5、每通道功率1e-6、能量闭合1e-5，保持原近零规则。

先定义rho=max(Schur relative, native relative, port fixed-RHS relative)，仍另报全部原门限，rho不是新通过标准。

- **强进展P+：**rho≤0.1，且散射L2及scaled-curl相对误差均≤0.25；未通过严格标准只称研究进展。
- **有限进展P：**rho较进入本路径的冻结基线至少减半，散射L2误差≤0.5，native不比该基线恶化。B0从零开始，其rho基线按真实audit记录；不用任意较差试探点作分母。
- **仅场正信号F：**场误差≤0.25但rho不满足以上要求，只允许C这种不同机制的固定试验，不凭场相似延长同一训练。
- E第二轮还要求第一轮重新校准后的原loss比进入该轮下降≥10%、native不恶化；否则保存该轮证据而不追加相同迭代。

规则由独立checker重算。相同原loss下的最优值不等于最准确场；接受优化step只看原方程目标与finite，阶段分流可看独立验算，但求解进程不能读取参考数组。

## 5. N0：复用与两项必要接线

读取原action/moment/NN7状态、最新batch8与OptimizerTransaction。先核对NN7保存的网络参数重生trace与保存z配对；UNKNOWN接受状态不等于参数不可用，但不一致时只阻塞B1，不阻塞B0。z、t和port不得由相关系数重构。

新增核优先进入可复用src模块，runner只薄调度，input每个dat是一条明确stage；不为每条路线复制完整程序。S正向、边面矩、MPC、齐次误差恢复未变的证据复用。需要新验证的是线性头映射、复系数顺序、port仿射闭合、输出层重写以及新增隐藏层梯度。

用复数小矩阵验证下面所有式子；目标pilot上使用三组固定seed非零见证核对参数→矩→系数、线性头预测与实际网络完整trace，operation-relative≤1e-10。有限差分沿用h=1e-4/1e-5/1e-6的稳定区≤1e-5规则；不能零梯度点独自资格化。

## 6. 路径A：原方程决定幅相，不用参考校相位

它回答“NN现有场方向是否已有用，只是整体系数与端口没有配好”。令t7为NN7的冻结trace，保留全部40个port自由度：

```math
z(c,\alpha)=\begin{bmatrix}c\,t_7\\\alpha\end{bmatrix},\qquad
\min_{c\in\mathbb C,\alpha\in\mathbb C^{40}}
\lVert b-Sz(c,\alpha)\rVert_2.
```

仅41列，用实际S作用、稳定小型最小二乘求系数；参考场的相关系数、最优幅值或相位不得进入计算。可以用对原NN7状态的增量形式，使零增量是可选项。恢复内部时使用原F(z)=u_part+R0z，不能把完整旧散射场简单乘c而错误缩放特解。

保存更新前后原残差、场误差及复c，复c必须来源于S/b。即使严格通过也要核对完整E/H和全部通道；高相关并不保证本路径成功。A失败不阻止B。

## 7. 路径B：固定隐藏特征，直接求网络的线性输出层

### 7.1 为什么这是有效的新对照

当前网络最后一层没有激活，**固定三个隐藏层后，输出层权重／偏置对trace是线性的**。无需继续用Adam学习已经线性的部分。网络隐藏层提供函数，原有限元方程计算这些函数的组合系数；不是求任意残差的p4逆，也不是读取准确场训练。

令h_j(x;psi)是最后隐藏层的64个实特征，h_0=1。八载波、三向量分量共24个复包络。合并原输出层实／虚权重后有24×65=1560个复系数gamma：

```math
f_{\psi,\gamma}(x)=\sum_{\ell=1}^{8}\sum_{a=1}^{3}\sum_{j=0}^{64}
\gamma_{\ell a j}\,h_j(x;\psi)\,e^{i k_\ell\cdot x}\,e_a,
\qquad t=P_\psi\gamma.
```

P由原Nédélec边面矩、orientation、owner/MPC得到，不是节点值。构造实现必须与实际网络的实虚排列配对，不按猜测reshape。

```math
Q_\psi=\begin{bmatrix}P_\psi&0\\0&I_{40}\end{bmatrix},\quad
\eta=\begin{bmatrix}\gamma\\\alpha\end{bmatrix},\quad
W_\psi=S Q_\psi,\quad
\min_{\Delta\eta}\lVert r_0-W_\psi\Delta\eta\rVert_2,
\quad z_{new}=z_0+Q_\psi\Delta\eta.
```

B1以原NN7对应的gamma/alpha为基线，隐藏psi固定；这是明确授权的继续研究，V7原2小时及设置成本计入其方法总账。B0使用原seed420906隐藏初始化，输出gamma/alpha从零，不能读取NN7权重或参考；这是随机特征基线。两者用同样的线性头算法和列库存。B1更好才支持已学习隐藏特征有用；B0胜出必须如实报告。

### 7.2 稳定求解和容量

允许本pilot显式存储薄P与W，不允许完整18184×18184稠密S或全局FE CSR/LU。P的complex128载荷452874240B，W为465510400B，合计约0.855GiB；这是derived，不含QR/SVD副本、workspace、原packet和恢复。逐个特征集运行并释放，常驻规划≤8GiB，整树仍受12/16GiB监督。

从batch8固定隐藏特征和原矩映射批量产生P，不对1560个输出系数分别跑一次完整MLP自动微分。W按至多16列一块使用原S作用构造；每列等效S成本全部计数，不用矩阵批处理隐藏工作量。可缓存40个真实port列在本批复用。

最小二乘固定采用已有SciPy/LAPACK的QR/SVD稳定路径，优先lstsq(gelsd, cond=1e-12)，只用于至多18184×1600薄矩阵。事前检查LAPACK临时内存，保留finite检查和独立显式残差；不得形成WᴴW或完整SᴴS来省事。数值列归一化可作为该薄LS的确定性坐标处理，必须准确逆映射并统一两路线，不是再扫V8尺度。

有效秩、保留／丢弃的奇异值范围、系数范数、原loss与未截断一阶残差都报告。rank截断时不能称原空间上的精确最优或证明网络全局表示下限。固定阈值不扫描；只允许一次用同一分解作残差修正，若原残差没有达到预期下降则记录不稳定。零增量须保留，重算loss不得比基线恶化超过运算容差。

恢复gamma到真实torch输出层并通过packet_forward重新产生t，验证与P gamma一致；不能只得到一个无法回到网络的向量。每个B分支结束释放薄矩阵的无用副本后做原场验算。不得把本pilot的薄矩阵存储办法直接宣称可扩展到最终目标。

## 8. 路径C：精确闭合40维端口，而不是任意提高端口loss权重

若B没有严格通过，优先在B1隐藏特征上做此分支；B1不可用时用B0。它解决“让优化器同时猜trace和port时，端口关系是否妨碍获得正确场”的问题，保持同一原方程，不学习边界条件。

按实际packet（不猜正负号）分块：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\qquad
b=\begin{bmatrix}b_t\\b_p\end{bmatrix},\qquad
\alpha(t)=H^{-1}(b_p-Ft).
```

这里H是**凝聚增广系统的40×40 Hhat块**，不是原Hp，也不是体p4矩阵。先配对四块重组与原S；检查H数值条件和三组小solve残差。固定cond2(H)≤1e10且operation residual≤1e-12才使用；否则记PORT_BLOCK_UNSAFE，跳C，不改H/不加阻尼救场。

```math
\bar b=b_t-C H^{-1}b_p,\qquad
\bar W=(K-C H^{-1}F)P_\psi,\qquad
\min_\gamma\lVert\bar b-\bar W\gamma\rVert_2,
\quad z=\begin{bmatrix}P_\psi\gamma\\H^{-1}(b_p-FP_\psi\gamma)\end{bmatrix}.
```

这是精确代数消元；仅40维小分解允许，完整40端口仍保存并原样审核，不删除port物理。复用B中W的上下分块和40个port列构造barW，避免重做1600次S作用。不得显式形成整个K-C H^{-1}F；只作用在P及工作向量上。统一固定薄LS阈值和一次修正规则。

对于以C进入E的训练，每次t更新后都精确重算alpha(t)，不能冻结旧alpha破坏闭合。梯度要包含该映射的链式项：若原z空间梯度为(g_t,g_alpha)，传回trace的是g_t-FᴴH^{-H}g_alpha。这个40维转置solve必须计时并做真实复数FD；不是全局伴随求解。

即使port残差变小仍须检查native、体场和散射。C是新候选，不把“改变了可行参数集合后的loss”与B相同优化轨迹混为一谈。

## 9. 路径E：出现进展后继续，不停在一次小正信号

从B1/B0/C中具备§4进展信号者，按最低原rho选一个（相同则优先总成本较低者），不得从参考拟合选权重。模型结构、宽度、载波、求积不变。每轮先已有线性头合格求解，再固定该头，仅更新隐藏psi：batch8、FP64、Adam lr=1e-4、50次完整更新，不用500次热身，不扫描lr。非C路径的port在这50步内保持该轮已求出的值；C路径保持解析闭合。

50步后重新构造这一psi的P/W，并按原B或C规则重求输出层／port。每步计入完整loss、S/Sᴴ/VJP和线搜索／检查成本；一次完整外层提交后保存事务状态。隐藏层不优化参考误差；不用隐藏层训练方向的参考投影。

若发生非有限或loss超过轮初10倍，恢复本轮提交边界，标HIDDEN_UPDATE_UNSTABLE并转D，不用更小lr无限重试。每轮完成后原loss不下降则保留原候选而记录失败轮，不能因选回旧值宣称改善。原loss下降≥10%、native不恶化且仍有§4信号时可做第二轮，最多两轮；每轮的建基和线性头成本全算入该方法。

这叫有限交替优化，不声称已经实现严格VarPro梯度或有全局收敛保证。参数增长、增加方向、改激活或局部网络属于以后研究，不在本夜自动扩展。

## 10. 路径D：负结果继续研究原因，但有终点

D在主要无标签候选和E/P全部结束后执行；一旦开始参考拟合子项，**本夜不能把其任何结果回传到A/B/C/E**。允许两个相互独立子项，某项接口不可用不阻止另一项。

**D1 固定隐藏层的表示诊断。** 复用B1和B0已建立的P，在单独进程以原REF7的canonical trace作一次线性最小二乘拟合，报告trace相对差和数值秩，并用参考port（明确标为reference-assisted）恢复后检验场。它只回答固定psi下线性输出空间能否表示参考trace，不是从方程求解；参考trace与port的用法必须醒目标注。不是整个非线性网络的表示上限。不能把拟合后的gamma发布为求解成功、初始化新候选或据此调阈值。

若固定空间可很好拟合而方程拟合差，记录PHYSICS_OBJECTIVE_OR_OPTIMIZATION_LIMITATION_SUPPORTED；若固定空间拟合也差，记录FROZEN_FEATURE_LIMITATION_SUPPORTED；rank截断影响较大则INCONCLUSIVE。两个标签可并存，不由一个数字断言全部NN无效。拟合准度与原场1e-4逐项比较，不自造通过资格。

**D2 原体算子细分。** 只对REF7及LSQR8的原误差（至多再加本批一个冻结候选误差）分解未凝聚V的curl-curl、epsilon质量和必要原边界项，验证重组等于原V。允许本pilot有界operator-only装配／局部张量，禁止新因子、全局谱/shift-invert、独立凝聚各项或新Krylov运行。使用正确齐次误差恢复；保存各项范数、复交叉项、重组及运算尺度。强抵消本身不是bug或唯一病态证明。

D不再次完整复制V9所有区域、40通道、数百个积分，只补未回答的问题。若B/C没有正信号，也应尽量完成D1/D2后给出有依据的取舍，不在首个负结果处机械停止。

## 11. 路径P：成功后自动做严格验证和离散检查

任何候选通过原方程门限后，先运行既有独立p3场／功率比较；通过完整同离散资格才允许P的p-enrichment。释放P/W、网络优化历史等无用对象，保留最小恢复packet。

剩余时间足以覆盖容量预检、设置和清场时，授权**同一几何、同一材料与40通道、同网格p4的一次准确独立参考**，沿已有symbolic Gate与release-before-recovery生命周期。p4只是精度对照，不是重开p4 PC；候选从未读取其解。full FE≤200000、独立trace≤100000、整树预算仍16GiB；不能因“参考”取消资源Gate。不安全／时间不足时标ENRICHMENT_NOT_ADMITTED并继续其他轻量工作。

比较完整total/scattered E/H、scaled-curl、复通道和功率，p-enrichment差目标沿原1e-3。p3通过方程但p3/p4差超标，记录DISCRETIZATION_NOT_QUALIFIED，不降低门限，不用p4场回训。本夜不自动对p4再训练、不改变网格、不放大几何，剩余时间做成本模型和可复现脚本。

即便所有micro Gate通过，最终目标规模0.7nm／48h仍需独立资格。必须按测得P/W构建、分解、隐藏训练、局部恢复、DtN内存及MPI数据量说明放大blocker；未知目标规模与步数记unknown，不能按网络参数少直接外推。

## 12. 无人值守资源与异常处理

继续用户的Task042受控共享CPU授权；已有heavy不是自动阻塞。现场核实邻worker、监督器、加载线程、SMT、MemAvailable/cgroup、磁盘；选空闲物理核，MPI1、全部数学/Torch线程1、DataLoader0；只对本任务nice10/idle I/O。无需GPU，不改CUDA/BLAS/驱动、邻程序及其锁／亲和性／环境。

整树hard16GiB、warn12GiB、own swap0，无OOC；保持系统reserve=max(128GiB,effective_total的10%)及128GiB邻增长余量、磁盘自由≥50GiB、artifacts≤20GiB。本批薄矩阵常驻规划≤8GiB，不意味着可占满整机2TB。无cgroup权限则如实使用独立进程树采样watchdog，不冒称内核连续限制。

deadline/watchdog覆盖launcher、BLAS、JIT和全部后代；先测一次低成本超时与进程清场。资源warning先停止新的大分配；触hard、swap、持续压力或监督失效，终止自身树，保留轻量journal，不为写大checkpoint延迟安全停机。不能kill／暂停邻任务。共享性能只标observed，不承诺零干扰。

跨阶段progress journal至少记录开始／结束、分支选择、实际阈值、deadline余额、source、状态和累计资源；每个长stage定期写轻量心跳，不能依赖用户回复。只允许一个Task042数值heavy在运行。允许一次有总deadline的非交互批次启动／继续，不安装daemon、cron、永久自动重启或跨夜任务。

## 13. 提交、证据与交付

所有正式数值通过python scripts/run_case.py的one-run dat。一个dat只对应已登记stage与单一物理输入，不隐藏任意参数扫描；同stage允许明确列出的输出列／状态库存。运行前clean实现commit，检查原输入、resolved_config、manifest、physical/material/array/source hashes。正在运行时不要为文档改变其受检HEAD；阶段之间提交结果再继续。

提交计划：C1薄调度／线性头与代数tests；C2 A/B及完整验算；C3 C/E/P/D按实际准入的实现；C4 compact结果。不得为取得一个新路径大规模复制runner或重构普通默认。旧负结果、旧review和原task不改；新分支状态用本report覆盖，不改历史说明。

至少交付response_v10.md、outcomes/autonomous_neural_head_v10.md，以及可合并的compact记录：

```text
branch_plan_v10.json
progress_journal_v10.jsonl
candidate_comparison_v10.csv
head_mapping_and_rank_v10.json
port_closure_checks_v10.json
continuation_checks_v10.json
representation_diagnostic_v10.json
volume_balance_diagnostic_v10.json
qualification_and_dispatch_v10.json
run_index_v10.json
resource_costs_v10.json
```

未执行路径记录条件和原因，不为空不冒充PASS。P/W/参数/场等大文件留ignored目录，释放RAM但保留必要hash-bound复现数据；不把同一数据嵌入多份JSON。同步summary/test_summary/changed_files、development_progress和development_model_registry。

单独区分：当夜elapsed预算、实际有载累计、各方法从零／从NN7继续的总成本、微基准。NN7后处理／续训不能只报告新增加几分钟，至少计入原V7约7143秒路线成本及其必要设置。随机特征比学习特征好时明确说，不为了“引入神经网络”标签夸大增量。

原公式／表格按fenced math规范做本地与GitHub rendered检查。文档渲染检查无法取得时如实标未核验，不阻塞已授权的正确数值工作，也不伪称渲染通过。

只推送git push origin HEAD:refs/heads/task42_neural_coarse_inverse。可在安全阶段边界发布阶段证据，但**不因一次push就停止整个已授权队列**；总截止、真实安全停止或所有可执行路径完成后交付并停。无论有无正信号，禁止merge master、强推、amend、删除负结果或自行开展最大目标运行。

## 14. 方法参考与边界

- [Dong与Yang：神经网络PDE的Variable Projection研究](https://arxiv.org/abs/2201.09989)：区分非线性隐藏参数与线性输出系数。本报告B是固定特征线性求解，E是有限交替更新；不继承该论文配点模型的精度／收敛保证。
- [SciPy lstsq官方文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.lstsq.html)：最小二乘driver、有效秩与cond阈值含义。使用本机已有版本，不能为此升级ABI；求解后的原残差必须自行复算。

**本报告授权的是七小时内有限、可分流的研究，不是保证运行满七小时或保证求得目标解。正信号继续到规定验证，负信号进入不同机制或原因诊断；不得在相同失败设置上无限重复，也不得因一项失败就放弃其他安全可做的工作。**
