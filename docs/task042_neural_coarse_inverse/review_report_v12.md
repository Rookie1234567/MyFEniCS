# Review V12：V14审查与几何局部trace表示的配对试验

## 0. 决定、快照与本批消除的障碍

**接受V14的正交decoder资格和有限位置重求头结果；不授予求解器或神经增量资格。停止继续沿V13/V14同一hidden射线追加点、重复大head补偿或缩步。下一批保持原Maxwell有限元方程，改变候选场的表示：先比较容量匹配的局部神经特征与局部多项式，再按明确条件各做一次全局＋局部组合。**

本批要消除的blocker是：全局tanh特征经稳定解码后，原方程残差仍约0.797、散射误差约0.734。需要检验局部独立系数是否比全局共享形状更有效，同时区分“局部化／增加空间的收益”与“神经特征独有的收益”。这不是寻找任意残差的强逆，也不是另开p4 PC；仍从本次物理RHS求一个有限元候选解。

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task42_neural_coarse_inverse
worktree                  = /home/fenics/Projects/NN-Lab
review_date               = 2026-09-30
reviewed_HEAD             = 61947232a135bd9d7ab168c8d88bf849b918c733
reviewed_commit_UTC        = 2026-09-30T08:21:45Z
reviewed_commit_Singapore  = 2026-09-30T16:21:45+08:00
reviewed_latest_commit    = docs(task042): bind final checks and publication evidence for V14
original_base_SHA         = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review           = review_report_v11.md
previous_review_commit    = 52bfe9ca622481df8f686a92cbb632885610d0e8
latest_response_reviewed  = response_v14.md
V14_numerical_source      = 87940891c12ccdec35fca39cd453ab9a29eeeda5
next_batch                = V15_LOCAL_TRACE_REPRESENTATION_COMPARISON
response_required         = response_v15.md
review_decision           = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
old_p4_inverse_route      = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate       = NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

最终目标保持：约2 TB物理内存的工作站资源内，对新的真正非可分三维周期单胞，端到端48小时内得到合格0.7 nm有限元解。本批为表示／求解可行性试验，仍受单核16 GiB研究预算；不是最终资源配额，不是0.7 nm目标规模运行。ChatGPT读取了远程最新合同、回应、原始结果、相关代码和提交；没有SSH运行工作站或读取全部ignored数组。下文历史数值为measured，公式与容量为derived，新的队列为planned/not_run。

## 1. V14接受哪些证据，关闭什么继续方式

证据：[Response V14](response_v14.md)、[完整结果](outcomes/orthonormal_trace_reprofile_v14.md)、[候选CSV](outcomes/records/candidate_comparison_v14.csv)、[decoder](outcomes/records/decoder_checks_v14.json)、[基底敏感性](outcomes/records/basis_sensitivity_v14.json)、[费用](outcomes/records/resource_costs_v14.json)、[实现](../../src/solvers/orthonormal_trace_reprofile.py)。

| 相同0.7nm/384hex/p3；无量纲measured | V14原点 | 最终s=4 | 判断 |
|---|---:|---:|---|
| 原Phi | 0.318179987294 | 0.317897054833 | 相对下降约0.088922%，不能用旧trial的230作为收益分母 |
| Schur相对残差 | 0.797721740074 | 0.797366985564 | 原1e-6失败 |
| native相对残差 | 0.309359507458 | 0.309221932317 | 原1e-6失败 |
| 散射E／scaled-curl误差 | 0.734256828／0.734361605 | 0.733565775／0.733670474 | 原1e-4失败，约0.0941%的相对改善不足 |
| 40复通道／能量闭合误差 | 0.049415153／0.112132957 | 0.049365073／0.112062042 | 原1e-4／1e-5失败 |

正交主输出的实际残差对thin差约1.03e-12、驻点缺陷约1.77e-12，两个新ORTHO制造见证的已知z差约2.31e-13／3.52e-13；新decoder通过。逆序行QR的Phi差8.99e-10只是观察到的数值敏感性，不是全误差界。不能再把约0.797的求解平台全部归罪于旧raw gamma回写。

六固定点与两个新点都执行了，10个冻结状态严格通过0个。正式监督wall2510.272780 s，最大同时采样树RSS3243409408 B，own swap0；不是研发总elapsed或目标规模成本。旧V11头、V12标量FD、V13负结果不改写。V14已经完成所授权队列，不继续s=8/16或重新扫描同一方向；也不据一条射线宣布全部tanh网络不可能。

保留已验证的Qc decoder、原S/Sᴴ、40端口闭合、原矩／MPC、恢复、JVP和writer。参考native未持久化这一缺项，在下次独立VERIFY中顺手补记，不重做LU或整轮历史审核。V6起已知formal成本下界14670.412103 s保持下界口径，历史辅助unknown不猜填。

## 2. 权威与冻结范围

先读根／目录AGENTS、仓库原则、task、全部补充合同／review、最新response和summary。本报告在同一Task042正式授权新的表示对照，覆盖旧“全局8载波及其原始head必须保持不变”“只能同射线profile”的限制；不改变方程、有限元空间、完整通道、最终精度、共享安全或旧结果。局部化是新参数化，不是对旧算法等价性的声明。

| 冻结对象 | 精确身份 |
|---|---|
| 物理 | Full3D complex128；真空0.7nm；grazing1度/azimuth0/s；原三维缺口、layered background、双Floquet、Fourier-DtN |
| 几何nm | x=[-0.7,0.7]，y=[-0.525,0.525]，z=[-0.175,1.225]；原材料界面及缺口不变 |
| 离散 | 8×6×8=384hex，h0.175nm，Nédélec p3，FE与特征矩求积q15 |
| 数量 | full34050、canonical独立trace18144、内部13824、slave2082；top20+bottom20复端口 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1 |
| Si | n=0.999885140474+4.32477054e-6i，epsilon=n*n；source0.699999988明确alias至nominal0.7 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| mode SHA | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action NPZ SHA | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 NPZ SHA | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

其余背景、RHS、完整键／极化／参考面、master顺序、网格／矩数组hash从manifest核对。材料已ready，不再索要或联网替换。参考仅在全部求解及组合选择冻结后进入独立验证进程；禁止用参考场、误差、D1拟合、幅相或高精度样本选择分区、特征、维数、初值或组合。研究已消费历史诊断，不称fresh blind或新几何泛化。

## 3. 新表示是什么，不是什么

先用空间上局部的函数生成Nédélec积分系数，再让不同区域拥有独立的组合系数，避免一个全局包络的改变同时牵动全域。两条路线共享相同局部范围、载波、维数上限、端口及求解器：一条用固定神经特征，一条用确定性多项式。**本批不训练hidden；线性组合系数由原方程求得。** 神经路线准确命名为随机神经特征求解，不能声称已经学会局部hidden自适应。

局部分组作用于**已有独立FE系数**，不是把网格拆成互不通信的PDE，不引入DG、界面惩罚、局部逆或Schwarz PC。所有组通过同一个原S耦合。可不连续的辅助函数不直接当作最终E；最终E仍由唯一共享的Nédélec系数和原内部恢复组成。适用性必须以实际canonical/MPC和切向迹配对核验。

参考只提供设计背景：[随机特征PDE方法](https://arxiv.org/abs/2207.13380)、[界面随机特征方法](https://arxiv.org/abs/2308.04330)使用局部／多尺度表示；其配点和惩罚边界并不是本项目原FE方程，性能不能照搬。[Basix 0.10插值／DOF变换](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.interpolation.html)用于确认矩与方向语义，不升级现有ABI。

### 3.1 唯一几何分组，不按残差或参考调patch

在x=0、y=0、z=0.525三个网格面划分2×2×2=8个盒，按(ix,iy,iz)词典序编号。它们只用于坐标归一化和canonical边／面实体归组；材料mask不变，不把每个材料区域单独重建PDE。

每个独立trace行先还原其完整edge/face实体和原方向。以canonical master实体的几何中心归组，同一实体全部高阶矩同组，切面相等时归低侧。x/y周期实体先用原master代表，不给slave另分组；中心恰在上周期边界时按该master的周期等价位置决定组，但积分仍沿原master实体、仅由原MPC处理slave复相位。不得根据owner单元随意拆同一实体，禁止按行号分段当作几何局部。

生成唯一metadata表：canonical row、entity维数及id、矩编号、master、方向、实体中心、patch id。检查18144行无遗漏／重复、8组非空、slave未成为新增unknown。需要补几何metadata时，只加载同一小网格和空间一次；不装配新的全局S或重新建参考。

### 3.2 两个匹配特征库

每个盒用其中心与半宽将坐标写为局部xi。两路线都使用一个已知入射载波exp(i k_inc·x)，k_inc读取原几何／入射约定并保存完整向量，不猜角度或z符号。**这与旧全局8载波不是纯单因素局部化对照**；新两路线之间才是同设置的神经／多项式配对。不能把一载波当成删掉其他物理传播通道；40个DtN通道全部保留，其他振荡必须由表示及原方程解析。

- LOCAL-NN：复用原seed420906的3×64 tanh隐藏初始化，只取最后hidden的64个实函数，再加常数1，共65标量特征。每个patch查询同一固定网络的局部xi；不读取NN7、s4隐藏权重或参考fit，不训练／调seed。
- LOCAL-POLY：64个张量Legendre函数L_a(xi_x)L_b(xi_y)L_c(xi_z)，a,b,c=0..3，再加L_4(xi_x)，共65个；固定词典序，不按结果换额外项。额外四次项只是辅助特征，**不是p4 FE、p4逆或新p4参考**。

每个标量特征分别乘三个物理向量方向和同一载波，故每组名义195列、全域上限1560复系数，与旧全局特征的名义容量相同。两路线系数都由方程独立求解，不用另一候选warm start。

令ell_j为原canonical Nédélec矩泛函，E_b为向全局独立trace行的注入：

```math
(B_b)_{j,(a,m)}=\ell_j\!\left[e_a\,e^{i k_{inc}\cdot x}\,\phi_m(\xi_b(x))\right],\quad j\in I_b,
\qquad t=\sum_{b=1}^{8}E_b Q_b c_b.
```

先对完整实体作原边／面矩、Piola及orientation映射，再按I_b取行。**不是在积分内乘一个跳变mask，也不是把NN点值当作系数。** 实体积分不能截半，不能删除面高阶矩或法向跳变许可。独立见证用原DOLFINx全局延拓函数插值后选择同样行，比较两种矩路径。

### 3.3 稳定、稀疏decoder及实际容量匹配

每组非零列先单位范数归一化，记录缩放；这仅换列坐标，不改原loss。零列明确登记，不用默认数填充。以thin SVD（固定GELSD/GESDD类现有实现，阈值sigma>1e-12 sigma_max）产生左正交方向，不通过巨大raw系数回写。固定该阈值，不扫描或人为补齐秩。

在任何原物理LS前，按每组两库的数值秩取r_b=min(r_b_NN,r_b_POLY,195)，两者都保留各自前r_b个左奇异方向。因此实际容量与支持匹配，r=sum r_b≤1560。报告名义195/1560与实际r_b/r；若发生秩损失，禁止仍称两者都是1560维。任一组r_b=0则停止该配对的依赖路径并报告，不用随机补列。仅一库实现失败时可完成另一库，但标UNPAIRED、不能得出神经优于多项式。

分组行互不相交，故组合Q_L的列正交；以块存储和块乘法实现，不常驻全是零的大Q_L。随机复系数的block forward/adjoint与小显式拼接配对≤1e-10；原MPC双周期、实体旋转／反射以及切向共享必须另核验≤1e-10。

满容量时decoder载荷上界为18144×195×16=56,609,280 B，约54.0 MiB；旧全局18144×1560×16=452,874,240 B，约431.9 MiB。**这只是decoder数组的derived减小，不是全过程RSS下降8倍。** 原作用矩阵A=barS Q_L仍可能稠密、同样约431.9 MiB，端口和LS工作区不因分组消失。

## 4. 原方程求解与数值Gate

继续原40维Hhat闭合，H不是未凝聚Hp。以下只定义作用，不物化全局S或barS：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\quad
\bar S=K-CH^{-1}F,\quad \bar b=b_t-CH^{-1}b_p,\quad
A_Q=\bar S Q,\quad c=\operatorname{lstsq}(A_Q,\bar b),\quad
t=Qc,\quad \alpha=H^{-1}(b_p-Ft).
```

所有物理行参与，主目标仍为原完整残差平方除以2 norm(b)^2，不引入row scaling、loss权重、Riesz/ILU/p4逆或正规方程。薄LS固定cond=1e-12/GELSD，精确40端口solve计费。允许一次同A实际残差修正c；不修改阈值以获得通过。

复用V14的原残差/驻点检查，扩展成接收块decoder的通用接口，不复制求解器。每库做3列＋2个随机非零组合的原barS配对≤1e-10；Q正交≤1e-10，H条件≤1e10、端口solve≤1e-12。A要求数值列秩等于实际r；若不满足，保留最低残差结果但标HEAD_NUMERICALLY_UNQUALIFIED，不继续组合。实际与thin固定RHS残差差及range(A)驻点缺陷各≤1e-8。数值满秩不是精确最优声明。

每库只做一个新LOCAL制造见证：seed421501归一化复c＋非零40端口，经原action.apply得到完整制造rhs，恢复z误差≤1e-6、原残差≤1e-8、齐次恢复≤1e-10。它不修改物理b，不替代物理求解，不回写旧M2失败。方向／矩原见证通过后立即运行相同真实物理RHS，不能只交付局部QR表。

## 5. 有限执行队列与一次全局＋局部配对

| 阶段 | 明确工作 | 分流 |
|---|---|---|
| L0 | 核对数据，建立8组与两库，容量匹配及矩／decoder资格 | 一项真实阻塞只影响其依赖项；不重建F0 |
| L1 | LOCAL-POLY、LOCAL-NN各一次原方程LS及审核 | 两者都完成，不因首个数值负结果取消另一个 |
| L2 | 两个局部候选都未过原方程Gate时，按下文最多各一次G0＋LOCAL组合 | 不需先取得物理正信号；不进行容量／patch扫描 |
| L3 | 全部队列冻结后，独立参考验算及最多两项新空间表示诊断 | 不回训、不继续扩大或转监督求解 |

G0固定为V14 ORIGIN保存的Q，不选s4、不用参考重造基。它来自原随机hidden；读取完整hash并核对canonical顺序。缺G0仅跳L2，不重跑八个profile。全局基与局部基组合只改变求解空间，**不是Hybrid，也不是给不同残差求逆的粗PC**。

若两局部库数值资格通过且均未达到原Schur/native/port≤1e-6，执行以下配对。若有一条已过原方程Gate，完成另一条基本对照后直接L3，不为跑满预算构造更大组合。

```math
Y_X=(I-Q_GQ_G^H)Q_{L,X},\qquad
Q_{U,X}=[Q_G,U_X],\qquad X\in\{POLY,NN\}.
```

投影分块计算并重正交一次，不形成18144阶投影矩阵。U_X取Y_X的左奇异向量，奇异值绝对大于1e-10（输入Q_L单位列，这里是固定角度／重合判据）。两者保留共同补空间维数q=min(q_POLY,q_NN)，得到相同实际维数1560+q≤3120。不扫阈值，不能把q的不同上限解释为NN优势；只保留一个库时标UNPAIRED。q=0则记NO_NEW_INDEPENDENT_DIRECTIONS并跳组合，不重新选patch。

必须完整保留Q_G；可能丢弃与G0近重合的局部方向，逐项记数。检查Q_U正交≤1e-10，以及旧G0候选可被新空间重建≤1e-10。每条组合重新用原作用建立A_U、独立GELSD求同一物理b；禁止简单相加两份已有解。合格数值LS的实际Phi不得比G0恶化超过max(1e-8,100倍同点／thin诱导观察余量)；否则先归为组合／LS数值检查失败，不能称局部物理方向有害。不要用“扩大空间一定降残差”替代实际审核。

一套组合只做一次，不再进一步3120→更多维数。组合比G0好还可能只是维数增加；只有UNION-NN与同维UNION-POLY才用于比较神经特征。局部NN也可失败，多项式胜出必须如实保留。本批不改变或训练hidden，不重做V13导数，也不生成新的teacher。

## 6. 冻结后验证与表示诊断

L0/L1/L2全部终止并冻结schema/hash及决策后，独立FE进程才读取REF7。一次环境最多10个去重状态：G0、V14最终点（仅历史参照）、两局部、两组合、至多两参考投影诊断；无效候选明确缺项，不伪造完整表。

严格门限沿原合同：Schur/native/原增广及规定port≤1e-6；恢复/identity≤1e-10、slave-zero；同离散total/scattered E/H、scaled-curl、selected复场与40复通道≤1e-4；R/T/A/A_volume绝对差≤1e-5、逐通道功率差≤1e-6、能量闭合≤1e-5，近零沿原规则。补记既有REF7的本次独立native审核值及数组hash；若参考身份审核失败，只保留候选自身原方程诊断，不给同离散资格，不重新LU。

只有新局部候选尚未严格合格时，允许各自一次参考trace的正交投影t_proj=Q_L Q_Lᴴ t_ref，并用原Hhat闭合其端口、原仿射恢复算场。这是REFERENCE_ASSISTED_REPRESENTATION_DIAGNOSTIC，不是无标签解；不能把其系数作为后续初值。它最小化的是已计算子空间中的trace欧氏误差，不是物理L2最优，不是全部NN能力下界。缺参考不阻止L1/L2，投影缺项也不重跑求解。

| 结果 | 必须给出的判断 |
|---|---|
| 两局部都改善 | 局部表示有作用；再看神经与多项式同容量差异，不能都算NN增量 |
| 仅组合改善 | 需要全局与局部共同表示的迹象；更大维数及稠密A成本必须披露 |
| 神经与多项式都未改善 | 收口本组局部结构／容量，不能继续改patch/seed直到通过 |
| 参考投影也有较大误差 | 新子空间仍未充分表达参考trace；只是此固定子空间的证据 |
| 参考投影场接近、原方程解场仍差 | 表示限制与残差最小化度量的差异仍需区分；不再自动追加同类空间扫描 |
| 仅小loss下降 | OBJECTIVE_ONLY_IMPROVEMENT，不授予神经或物理资格 |
| 原方程与全部场／功率通过 | MICRO_DISCRETE_PASS_ONLY；本批不运行新p4参考或最大模型 |

研究正信号保持rho=max(Schur,native,固定RHS端口)较G0至少减半、散射E与curl各≤0.5且各改善≥25%。配对中的神经特征优势单列实际同维误差／完整成本；局部化、QR、端口消元、增加维数不归给hidden学习。本批没有hidden训练，所以绝不写HIDDEN_TRAINING_GAIN。最后只建议一个与实测对应的下一步，不自动开启新的架构。

## 7. 资源、成本、源码与停止条件

从接手新start起总elapsed≤14400 s，含实现、测试、设置、求解和交付；start+13500 s停止重负载，最后900 s收尾。独立deadline与整树watchdog覆盖纯数组、ML、FE和BLAS子进程，时钟不因修复或阶段刷新。局部两库是主要任务，L2仅在剩余时间与容量合规时执行；不得为组合挤掉所有独立验证／收尾时间。

全批上限同时生效：新局部原始基2套、组合基2套；新A总列数≤10000；等效S+Sᴴ≤12000（测试/制造/审核全部计）；薄LS／修正≤12调用、RHS≤12；每组局部SVD共≤16次、组合补空间SVD≤2次；原audit≤60；独立场状态≤10。主物理候选最多4个，不能拆版本重置。新artifact≤3GiB且继续原Task042总量／磁盘余量要求；不删旧负结果给新试验腾额度，必要时只保存可重建小输入及最终decoder。

单核受控共享继续：其他heavy存在不自动阻塞；现场选空闲物理核及避开其SMT同胞，MPI1、数学/Torch线程1、DataLoader0、GPU不用。own swap0；事前同时常驻规划≤8GiB，整树warn12GiB/hard16GiB；系统余量max(128GiB,有效总量10%)、邻增长规划128GiB和本批16GiB保持。无cgroup委派时明确0.5s采样停止不是连续内核cap。只监督停止自身后代，不动邻任务、其锁、环境、亲和性、watchdog或系统配置；不升级ABI/BLAS/CUDA。

局部decoder稀疏不表示A稀疏；组合decoder也可能变稠密。L2分解、P/Q/A/U副本和LAPACK workspace先计容量，至多一套大分解常驻。超预算只跳对应组合，不偷偷降低物理分辨率、通道或计算精度。全部费用记shared-workstation，无邻任务可比速度则不宣称零干扰或无争用加速。历史formal下界14670.412103 s保留，研发elapsed、方法lineage设置、部署单次、数组bytes与实测RSS分别记账。

最多两次明确实现错误的最小修复与受影响重放；秩不足、场误差大、没有神经优势不是bug。身份、原作用、参考隔离、监督失效或持续资源压力则停止对应依赖工作。没有真实进展不要求跑满四小时。

## 8. 实现、入口、commit与交付

复用原moment／owner／MPC、块decoder协议、bar_action、GELSD、审核和writer；新特征与块表示数值核心进入src/solvers，配置／路径放src/io，runner只编排，不再复制近千行脚本。原求解默认不变，research显式opt-in；不要静默改变V14对象中expected_columns或门限来伪造旧资格。

至少测试：实体整组及周期代表、无丢行／重复、局部归一化、全部边／面矩与独立插值、复相位与orientation、两库容量匹配、块forward/adjoint、局部rank缺陷、全局补空间保留、原制造非零port RHS、仿射误差恢复、禁止reference参与构造、原子记录与异常清场。改动后跑相关小回归与compileall；Ruff/pytest缺失如实报告，不能为此重装ABI或冒称CI。

以下是待实现入口，不是在本报告提交时已可运行。实现／接线测试通过并提交clean源码后按Gate逐一执行：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v15_local_basis_setup.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v15_local_polynomial.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v15_local_neural.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v15_union_polynomial.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v15_union_neural.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v15_verify.dat
```

一个dat对应一个明确stage；L2准入失败时生成not_run记录，不盲目运行命令。L0 metadata含两个特征库是同物理构造资格，不是隐藏波长扫描。正式run绑定input_original.dat/resolved_config/run_manifest/input_sha/physical_model_sha/source_sha/run_summary及环境、线程、资源和artifact hash。运行source不得用最后文档HEAD替代。

commit顺序：C1局部metadata/特征/块decoder与小测试；C2原物理求解及条件组合入口，clean后正式运行；C3独立checker/验算与紧凑结果；C4 response与导航/总账/渲染。已有source白名单只作本任务必要opt-in扩展，不修改邻任务。任何失败原文保留，旧task/review/response/raw不改。

交付response_v15.md、outcomes/local_trace_representation_v15.md，及records中的local_entity_map概要、basis_inventory、local_basis_checks、matched_capacity、local_candidate_comparison、union_checks、representation_projection_diagnostic、qualification_and_dispatch、run_index、resource_costs、reference_audit、publication_checks（均v15后缀）。完整逐行map和大数组在ignored artifact，Git只存hash/少量例子/统计，避免再堆入几千行无关环境快照。同步summary、test_summary、changed_files、Task042 README、development_progress和development_model_registry，不整本重排历史总账。

按markdown_rendering_standard检查公式／表格／相对链接；实际GitHub rendered view与本地检查分开，拿不到页面如实标未核验，不伪称视觉通过。只推送本执行分支，不merge；全部可做路径结束或安全／总预算触发后，清场、报告精确HEAD/upstream/工作树与唯一下一建议，等待review。
