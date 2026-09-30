# Review V13：V15审查、固定空间残差下限与全空间校正

## 0. 决定、快照与要消除的blocker

**接受V15的局部／组合表示证据，不授予求解器或神经增量资格。下一批不再要求最终解完全受限于已有神经／多项式基，而以这些基辅助原有限元全空间求解。固定空间上的loss行尺度试验暂不执行：它可以改变近似场的取舍，却不能突破同空间已经求出的未加权最小残差。**

本批消除的是“表示空间已经数值求到最小残差，却仍把所有精度寄托在同一小空间”的障碍。网络可以提供有用方向，但不能成为准确有限元解的硬性表示上限。最终目标仍是约2 TB工作站资源内、端到端48小时获得新的0.7 nm非可分三维单胞有限元解；本批只是相同micro上的有界求解实验，不承诺达到目标规模。

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task42_neural_coarse_inverse
worktree                  = /home/fenics/Projects/NN-Lab
review_date               = 2026-09-30
reviewed_HEAD             = 74fdd6346829c8b66a8dd4a95baa7b4c710dd1cd
reviewed_commit_UTC        = 2026-09-30T11:15:28Z
reviewed_commit_Singapore  = 2026-09-30T19:15:28+08:00
reviewed_latest_commit    = docs(task042): bind compact V15 identities publication and final cleanup
original_base_SHA         = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review           = review_report_v12.md
previous_review_commit    = c0a759c29c08cc377a3fde3b81c5f4c34c24710a
latest_response_reviewed   = response_v15.md
V15_numerical_source       = db0e68e519767554412c960af14b3c185012f9de
next_batch                = V16_AUGMENTED_FULL_TRACE_LSQR
response_required         = response_v16.md
review_decision           = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
old_p4_inverse_route      = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate       = NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

ChatGPT实际审查远程合同、回应、raw结果、现有块decoder、端口消元、LSQR和最近提交；没有SSH运行工作站或读取其全部ignored数组。历史数字为measured；下限关系与新算法公式为代数推导；新队列为planned/not_run。旧失败保持，不将未执行的训练说成失败，也不把checker通过说成solver通过。

## 1. V15的结果及其真正含义

证据：[Response V15](response_v15.md)、[summary](outcomes/summary.md)、[完整结果](outcomes/local_trace_representation_v15.md)、[候选CSV](outcomes/records/local_candidate_comparison_v15.csv)、[组合检查](outcomes/records/union_checks_v15.json)、[参考审核](outcomes/records/reference_audit_v15.json)、[费用](outcomes/records/resource_costs_v15.json)。

| 同一0.7nm/384hex/p3；无量纲measured | 复基维数 | Schur／native残差 | 散射E／scaled-curl相对误差 | 判断 |
|---|---:|---|---|---|
| G0 | 1560 | 0.797721740／0.309359507 | 0.734256828／0.734361605 | 未合格 |
| LOCAL-POLY | 1544 | 0.824104524／0.319590851 | 0.578751074／0.578743743 | 场改善但残差更差 |
| LOCAL-NN | 1544 | 0.823698718／0.319433478 | 0.628221107／0.628213879 | 没有神经优势 |
| UNION-POLY | 3098 | 0.517713838／0.200771384 | 0.283235368／0.283293409 | 有实质场改善，仍远未过门限 |
| UNION-NN | 3098 | 0.579985792／0.224920683 | 0.766070574／0.766240878 | 同容量更差；不能只看残差下降 |

原方程门限1e-6、同离散场门限1e-4均保持。局部共同秩为195×6+187×2=1544；组合完整保留1560维G0，加共同1538维补充。UNION-POLY的残差较G0降低约35.1%、散射E误差降低约61.4%，未满足原“rho减半”研究判据，但不能把这项实际改善抹掉。

**UNION-POLY并非完全无神经特征：共同的G0也来自固定随机神经特征。** UNION-POLY与UNION-NN只隔离局部补充库的差异；不能据此把全部收益都归给多项式，或反向归给hidden训练。V15没有hidden训练。已有参考投影只属于诊断，不是新的求解结果或完整网络的能力下限。

四候选decoder数值合格、8个独立状态严格通过0个；REF7本次native约1.43744e-12。正式监督wall2106.167431 s，采样同时进程树峰4175888384 B，own swap0；不是整次研发elapsed。历史formal可核下界16776.579534 s及辅助unknown继续保留。

## 2. 为什么不把行尺度调整作为下一轮唯一求解主线

记端口消去后的原方程为bar S t=bar b，固定候选空间为t=Qc。V15已经用稳定薄LS求此空间内的未加权残差。若A=bar S Q=UR、U列正交，则精确算术下：

```math
\eta_Q=\min_c\frac{\lVert\bar b-Ac\rVert_2}{\lVert b\rVert_2}
=\frac{\lVert(I-UU^H)\bar b\rVert_2}{\lVert b\rVert_2},\qquad
\frac{\lVert\bar b-Ac_D\rVert_2}{\lVert b\rVert_2}\ge\eta_Q,
\quad c_D=\arg\min_c\lVert D(\bar b-Ac)\rVert_2.
```

因此，同一Q下改成H(curl)测试范数行尺度，不会把原最小残差约0.518降到1e-6。浮点下不能把已有小数称严格认证下界，但原作用配对／驻点误差很小，与这一数量级差距必须区分。新setup仅用实际QR核对下限，不重新做全局谱研究。

行尺度仍可改善场误差取舍；它不是无用方法，也不能由本推导否定未来完整空间预条件。但若本轮唯一工作仍是固定空间加权LS，严格原残差不可能因此获得数量级突破。本报告据最终目标暂缓该旁支，不为得到较好场而降低残差Gate。

## 3. 冻结身份与明确改变的方法边界

先读根／目录AGENTS、仓库原则、原task、全部补充合同／review、最新response与summary。旧文件不改。本报告在同一Task042明确覆盖“最终trace必须完全等于固定小基乘系数”的限制，只授权下述全空间校正对照；旧p4强逆、任意RHS粗PC、loss权重扫描、新hidden训练仍不执行。

| 冻结项 | 值 |
|---|---|
| 物理／离散 | 原Full3D complex128；0.7nm、grazing1度/azimuth0/s、三维缺口；双Floquet/Fourier-DtN；384hex/p3/h0.175nm/q15 |
| 数量 | full34050；独立trace n=18144；内部13824；slave2082；完整top20+bottom20复端口 |
| 几何nm | x=[-0.7,0.7]、y=[-0.525,0.525]、z=[-0.175,1.225]；材料mask、背景、RHS不变 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1 |
| Si／alias | n=0.999885140474+4.32477054e-6i，epsilon=n*n；source0.699999988明确alias至nominal0.7 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| mode SHA | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action NPZ SHA | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 NPZ SHA | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

G0及两个V15补空间从union_checks/run index核对路径、hash和canonical顺序，**NN补空间文件存1544列，但本配对只取原来共同的前1538列**，不能悄悄改变3098维库存。G0 SHA为a60fa21eae281049db72f3b27989f31f2a9d0fdd89820e35a3011c05c23dfc36；POLY补空间SHA为4f879b18460a4987f8627c7ccedecb86692505274277d56a972f179046960cc7；NN补空间SHA为6d853ae086b8b2a33df010c93b3bd09e3ea77aa96f70ff3922f0a4f0e4366c1d。

本批不训练网络。新角色是“表示空间辅助完整有限元迭代”：网络提供部分方向，空间外系数由原方程求解，不再是纯神经场代理。也不是Hybrid或z可分离方法。最终交付完整t、port及原局部恢复场，不只交Qc。所有旧基生成成本仍是方法lineage的一部分。

## 4. 全空间校正：保留已有方向，不锁死解空间

### 4.1 端口与两套正交空间

保留原40维Hhat闭合。以下H不是未凝聚Hp；S及bar S只作作用：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\quad
\bar S=K-CH^{-1}F,\quad \bar b=b_t-CH^{-1}b_p,\quad
\alpha(t)=H^{-1}(b_p-Ft),\quad
\bar S^H=K^H-F^HH^{-H}C^H.
```

对固定Q（18144×3098）建立A=bar S Q的economic Householder QR：A=U R。Q是trace空间的基，U是其**方程作用像**的基；二者不可混用。R是此A的QR三角块，不是旧P=QR中的R，也不是Maxwell完整因子。

```math
P_t=I-QQ^H,\qquad P_r=I-UU^H,\qquad
M=P_r\bar S P_t,\qquad M^H=P_t\bar S^H P_r,\qquad f=P_r\bar b.
```

两个投影都按向量作用，不构造18144阶方阵。LSQR从y=0解M y=f。M在全坐标中有已知零空间，**这是投影产生的结构，不是发现原Maxwell奇异**；使用复数Golub–Kahan，零阻尼，正确共轭转置。

### 4.2 每次审核必须恢复完整候选

```math
v=P_t y,\qquad
c(y)=R^{-1}U^H(\bar b-\bar S v),\qquad
t(y)=v+Qc(y),\qquad z(y)=\begin{bmatrix}t(y)\\\alpha(t(y))\end{bmatrix}.
```

R逆只是数学符号，实现使用三角求解；不显式求逆。精确算术下：

```math
\bar b-\bar S t(y)=P_r(\bar b-\bar S v)=f-My.
```

若原方程有解t_star，取v=P_t t_star即可满足上述补空间问题并恢复t_star。因此这条路线不再受到3098维固定表示误差上限；但不保证LSQR在有限预算内收敛。原n-r=15046维补空间不能再截断为几十个随机或网络方向。

这与“给NN输出一次，然后普通LSQR随便接着跑”不同：迭代在已处理方程方向的正交补上进行，审核时同步重新求Q分量，避免重复消耗工作。没有重建强p4逆，但确实保留3098阶三角求解和大薄基，不能称完全没有直接分解或自动可扩展。

参考：[LSQR原作者实现与定义](https://web.stanford.edu/group/SOL/software/lsqr/index.html)、[Baglama等的augmented LSQR研究](https://digitalcommons.uri.edu/math_facpubs/1/)。文献只说明这类矩阵作用／子空间增强思路；本报告给出的双投影公式需独立测试，不把其harmonic Ritz实验外推为本项目资格。

## 5. 三条固定路线与数值准入

| 路线 | 计算对象 | 对照意义 |
|---|---|---|
| CLOSED-LSQR-0 | Q为空，直接从零解bar S t=bar b | 完全无神经基控制；与旧V7增广端口LSQR不是同一个迭代算子 |
| AUG-LSQR-GPOLY | V15 UNION-POLY的3098列Q＋完整补空间 | 当前较好表示能否帮助完成精确方程 |
| AUG-LSQR-GNN | V15 UNION-NN的3098列Q＋完整补空间 | 同G0、同容量、同迭代法的局部神经补充贡献 |

各路线独立y=0，不读取其他路线的y/t作warm start。增强路线y=0时的t0由当前Q/A及物理b算出，应与V15固定空间解配对；这不是把准确参考作为初值。Q和U在整条路线内冻结，不进行在线改基、学习率／rank／damping扫描。

F0仅复用身份／环境与资源检查，不重跑旧campaign。新增准入必须覆盖：

1. 小型非Hermitian复数系统、有非零端口RHS、Q空/非空和明显非零Q外分量；显式小M与作用式/Mᴴ配对；复LSQR解后恢复原方程≤1e-10；与小直接参考配对。故意交换Q/U、漏P_t或共轭应被反例抓住。
2. 实际Q正交、A=UR重组及U正交≤1e-10；H条件≤1e10、solve operation≤1e-12；沿原1e-12数值秩标准，不剪掉“不方便”的方向。每库三列和两个固定seed421601/421602复组合核对原bar S，≤1e-10。只有A/QR可重建，旧Q缺失不重跑V15造新空间。
3. 实际M/Mᴴ至少两个非零复向量dot test≤1e-10（运算尺度，另报绝对差）；P_t/P_r幂等和各自消去列空间≤1e-10；真实r与f-My按固定物理b归一化差≤1e-8。不得用迭代器估计残差代替此检查。
4. 实际只作一次无参考代数见证：seed421603生成非零Q外v、Qc及40端口，以原S作用制造完整rhs；直接代入已知v核对投影/恢复恒等式≤1e-8。它是接口测试，不要求再迭代求一个难随机RHS，不标制造问题收敛；原物理b不被覆盖。含内部特解的误差恢复仍用F(z1)-F(z2)或F(e)-F(0)。

至少一条增强路线与空Q基线合格即可推进相应正式求解；某库缺失或数值不安全仅阻塞该库。不能为了全队列都有结果而使用错误伴随。reuse原bounded_complex_lsqr的数值递推，用接口/计数适配，不悄悄修改旧证据。

## 6. 完整有界执行，不在固定空间结果处停机

执行顺序：预检／基身份与短代数资格 → CLOSED-LSQR-0 → AUG-LSQR-GPOLY → AUG-LSQR-GNN → 全队列冻结后VERIFY。增强库的A、U、R在对应路线开始时构造/加载，按单路线计费，不同时常驻两库。V15未持久化A/U时允许每库重建一次，不把它误报成原数据丢失；不得重跑局部库或补空间SVD。

每路线最多4096次Golub–Kahan更新，零阻尼、无行/列缩放、无额外PC。各使用同一递推和预登记规则；每64步以及起点/结束重算真实恢复候选与原audit。保存0、256、1024、2048和最终状态的最小packet；参数/预算中断只能保存最后完整迭代状态，不能以参考选最好点。估计残差仅用于监控。

正常结束条件为原Schur/native/增广及规定port均≤1e-6，并通过恢复/identity/slave检查；否则到时间/次数上限为controlled_stop。精确零的alpha/beta导致递推结束但原方程不合格时记BREAKDOWN_NOT_SOLVED，不人为加epsilon或阻尼继续。先跑满授权的基础预算，不因旧固定空间没通过或第一条普通负结果取消其余配对。

可避免不必要的尾部空转：2048步后，若最近连续三个128步检查区间的真实rho下降均不足0.1%，允许记STAGNATION_CONTROLLED_STOP；只用本路线原残差，不能读参考。明显非有限、原作用恒等式失效、资源触线随时停止对应路线。预估残差变小而真实不变时保留gap，不自动换算法或重启；所有重放和失败计费。

本批不新增loss行尺度、不训练hidden、不继续增加Q的列、不计算全局谱、不运行新p4参考/最大模型。若增强失败且空Q也失败，结论是这个有界求解方案还不具备所需鲁棒性，不再归咎于“网络没有输出全部系数”。

## 7. 独立验证、神经价值与停止取舍

全部求解队列/状态/hash冻结后，独立FE进程才读既有REF7。一次环境最多10个去重状态：V15两个组合基线、三条最终向量、三条1024步向量，以及至多两个已冻结的首个原方程通过点。缺少某检查点如实not_run，不补跑。参考native与hash再次记录，不新LU；验证开始后不回训。

严格标准保持：原Schur/native/增广/规定port≤1e-6；恢复/identity≤1e-10、slave-zero；total/scattered E/H、scaled-curl、selected复场、40复通道≤1e-4；R/T/A/A_volume绝对差≤1e-5、逐通道功率差≤1e-6、能量闭合≤1e-5；近零沿原规则。功率不合格只能diagnostic。micro通过也不代表p/h收敛或最终48小时通过。

必须报告固定空间分量Qc、空间外分量v的系数范数，以及完整场误差；这些分量非物理正交，不能把场能量简单相加。若空间外修正恢复了精度，应明确精度来自完整方程校正，而不是网络独自准确预测。

比较至少包含同迭代数、同原S/Sᴴ作用数、同实际时间三个口径，先列冷设置/数据加载/投影/三角解/原作用/审核各成本。只有相同严格资格下，含本方法必要建基与setup的总成本较另一条减少≥20%，才记本pilot性能研究正信号；单次shared测量不是通用速度保证。均未通过时只报告真实收敛曲线/场趋势，不报“加速倍数”。

GNN对GPOLY仅隔离局部神经补充，G0为共同神经成分；二者对空Q比较不能单独证明全部神经贡献。没有hidden训练，不写HIDDEN_TRAINING_GAIN。参考投影、参考幅相或原解不得进入Q、初值、停止、挑状态或解算。

若只有空Q成功或它更经济，接受NO_BASIS_PREFERRED，不为NN标签保留昂贵模块；若增强成功而空Q不成功，先报告本pilot子空间辅助有效，分清局部NN与POLY；全失败则收口这次增强对照，只提出一个后续方法改动，不自动反复扫描同设置。

## 8. 时间、内存与共享安全

新start起全批elapsed≤14400 s（实现/测试/设置/求解/验证/交付全部包含），start+13500 s停止重负载，末900 s收尾。独立deadline和整树watchdog不可因版本/上下文/失败重置。数值队列开始时按剩余重负载时间T登记统一单路线wall上限B=min(2700 s, floor((T-600 s)/3))，留600 s作验证；B<300 s时不强启三路线，记录TIME_BUDGET_INSUFFICIENT。未用余额不用于新参数扫描，路线wall包括其A/QR加载或重建。

同时生效：每路线迭代≤4096、迭代/复算原S+Sᴴ≤13000；全批原S+Sᴴ≤50000（包含最多6196个A新列、见证和所有审核）；两套image QR，固定阈值秩检查至多各一次，不循环重分解；原audit≤240；独立FE状态≤10；新增持久artifact≤3GiB且总量遵守原20GiB/自由50GiB约束。这些是停止上限，不要求跑满。

现有PortBlocks.adjoint一次bar Sᴴ可能包含两次原Sᴴ，必须如实计数，不能将一次封装调用记成一次底层作用。若使用等价的单次原Sᴴ作用公式，应单独小配对、三路线一致使用、仅新adapter opt-in，不修改旧算法语义。

只一套Q/image U/R/A/workspace常驻；Q和U各约899 MB（decimal，3098列），不是完整工作集。A=UR合格并保存必要hash后可释放A，不留多份同量级矩阵。禁止每次投影显式复制整张共轭矩阵；使用已安装BLAS共轭转置作用或有界块实现，并验证伴随。不存全LSQR迭代基，只保留短递推向量和有限checkpoint。所有allocator/page cache/子进程峰如实记录，不把derived载荷当RSS。

继续受控共享CPU：其他heavy存在不自动阻塞，现场选空闲物理核并避开忙SMT；MPI1、数学/Torch线程1、DataLoader0、GPU不使用；own swap0，事前常驻规划≤8GiB、整树warn12/hard16GiB，系统余量max(128GiB,有效总量10%)+邻增长128GiB+本批16GiB。独立环境/cache/ownlock保持；无cgroup委派时明确0.5s采样而非连续内核限额。只监督停止自身后代，不修改邻任务或系统ABI/BLAS/CUDA。shell用set -e避免preflight失败后继续。

目标规模仍需重构分布式/streaming基和有界维数：本pilot每步有O(nr)投影与r阶小三角解，不能把“没有全局FE LU”当成2TB/48h可行性证明。历史formal下界16776.579534 s保留；新建基成本与复用lineage分别记账，不只报告热启动迭代时间。

## 9. 实现、Git及交付

新数值核心放src/solvers，复用local_trace_decoder、bar_action/PortBlocks、bounded_complex_lsqr、原审核与原子writer；IO/配置/监督分层，不复制整套runner。所有正式计算仍经one-run dat。先小测试、提交clean实现，再按Gate执行下列待实现入口：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v16_complement_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v16_closed_lsqr_zero.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v16_augmented_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v16_augmented_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v16_verify.dat
```

这不是当前已实现命令清单；Codex须创建并validate入口后执行。一个dat是一条明确运行/路线，不隐藏参数扫描。前置Gate通过后连续完成授权队列，不逐小步等用户确认。最多两次明确实现错误最小修复及受影响重放；普通不收敛不是bug，全部失败保留。

先原子保存最小迭代向量/系数/端口/计数及核心结论，再写派生JSON。checkpoint身份包含Q/U/R、原物理、实际source和迭代状态；若不可恢复递推，只称终态证据、不称可续跑checkpoint。运行保存input_original.dat/resolved_config/run_manifest/input_sha256/physical_model_sha256/source_sha/run_summary和环境/线程/资源/artifact hashes；文档HEAD不冒充数值source。

提交response_v16.md、outcomes/augmented_full_trace_lsqr_v16.md及compact records：space_floor、basis_identity、projected_operator_checks、iteration_history、candidate_comparison、field_channel_checks、reference_audit、run_index、resource_costs、qualification_and_dispatch、publication_checks。同步summary/tests/changed_files、任务导航、development_progress和development_model_registry，旧task/review/response/raw不改。无CI或Ruff如实标不可用，不安装破坏ABI的依赖。

review和结果按markdown_rendering_standard核验。GitHub rendered view未取得时标未核验，不伪称视觉通过；页面问题不代替数值结论。只push本分支；结束清场，报告精确HEAD/base/upstream/工作树、实际source、运行路线/停止原因、是否突破固定空间残差、完整资格和唯一下一建议。未经最终review与用户授权不得merge。
