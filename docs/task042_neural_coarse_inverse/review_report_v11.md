# Review V11：V13审查、正交trace直接输出与有限步长输出层重求

## 0. 审阅决定、快照与最终目标

**接受V13的独立切向核验及一次真实联合更新记录，不授予求解器或神经增量资格。关闭在原始大输出系数上继续重复固定头／一阶联合补偿与缩步的默认队列。下一批以同一批已保存的隐藏参数位置为对照：直接在正交有限元trace坐标中求值，并在每个有限隐藏变化后重新求线性输出系数与完整端口，不再把一阶补偿当作有限步长的最终头。**

本批要消除的blocker是：高相关神经特征及大系数回写，使隐藏变化的局部补偿只能取得极小下降；尚不知道在相同有限隐藏位置重新求头，能否产生实质改善。原固定空间的约0.798残差平台不会因换坐标自动消失。本报告授权的是有终点的实际求解对照，不是再做一轮导数表或无限训练。

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task42_neural_coarse_inverse
worktree                  = /home/fenics/Projects/NN-Lab
review_date               = 2026-09-30
reviewed_HEAD             = a81c5e49e37c0c3623f77565af448b40bb9fb296
reviewed_commit_UTC       = 2026-09-30T05:15:12Z
reviewed_commit_Singapore = 2026-09-30T13:15:12+08:00
original_base_SHA         = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review          = review_report_v10.md
previous_review_commit   = fb994b337960c89d2e70afc93707595258b3bb60
latest_response_reviewed  = response_v13.md
V13_accepted_source       = 33f7d613b1341fa585f0324ead6039bf28211fff
V13_record_verify_source  = 7615baae2f0d75fbc47c05be392b35ef2878c431
next_batch                = V14_ORTHONORMAL_TRACE_REPROFILE
response_required         = response_v14.md
review_decision           = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
old_p4_inverse_route      = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate       = NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

最终目标不变：约2 TB工作站资源内，从一个新的真正非可分三维周期单胞出发，端到端48小时内得到合格0.7 nm有限元解。本批仍是384-cell micro，继续16 GiB研究预算；低RSS、材料标签或一次接受更新不能代替目标资格。ChatGPT本次读取远程合同、回应、原始记录、相关源码与最近提交，没有SSH运行工作站，也未读取全部ignored数组。既有记录为measured，公式与比值为derived，新路径均planned/not_run。

## 1. V13结果和针对性判断

依据：[Response V13](response_v13.md)、[summary](outcomes/summary.md)、[详细结果](outcomes/tangent_scale_head_compensation_v13.md)、[实际试探](outcomes/records/coupled_step_history_v13.jsonl)、[切向核验](outcomes/records/tangent_identity_checks_v13.json)、[候选比较](outcomes/records/candidate_comparison_v13.csv)、[费用](outcomes/records/resource_costs_v13.json)。

| 同一0.7 nm／384hex／p3模型；无量纲measured | V13实际值 | 本次解释 |
|---|---:|---|
| 固定head三个方向的独立JVP／向量核验 | 三方向通过；h=1e-4的向量差约1.82e-10、2.40e-10、3.47e-10 | 保留新的切向资格，不追溯改V12标量FD失败 |
| 固定head最大线性预测下降 | 1.32e-17至1.82e-16；准入要求2.03e-11 | 不值得在这三个方向继续无限缩步 |
| 联合更新数 | 5试探、1接受；hidden变化3.26022e-6 | 已经实际更新，不能再写成全程hidden未运行 |
| 原loss | 0.3181799855089551→0.31817975803965803 | 相对下降7.14908e-7，即约0.00007149%，不是7.15e-7的物理误差 |
| 原Schur／native | 0.797721453／0.309359396 | 原1e-6门限失败 |
| 散射E／scaled-curl误差 | 0.734256339／0.734361116 | 原1e-4门限失败；几乎未改善 |
| 40复通道／能量闭合误差 | 0.049415129／0.112132933 | 原1e-4／1e-5门限失败；无新official R/T/A |
| head-only twin的loss | 282.766917 | 只改head严重恶化；同步补偿必要不等于有用的神经收益 |
| 六正式stage监督wall／同时树峰 | 243.725626 s／2852761600 B | 约2.657 GiB、own swap0；非全部研发elapsed或目标模型成本 |

V13较大步长的实际loss为230.4461、1.21706、0.321687、0.318193，最后小步才降到0.318179758。相邻共同步长缩至1/4时，Taylor残差范数近似缩至1/16，支持有限步的一阶补偿误差显著这一解释；不证明唯一根因是浮点误差。原P条件比约2.52e10，也不等于整个Maxwell算子的条件数。

需要区分两个问题：其一，同一hidden空间内，正交解再转回巨大原始head会丢失稳定坐标优势；其二，hidden已经有限改变，却仍使用旧点的一阶head补偿。V14分别控制这两项，不把坐标重写本身宣称为扩大空间或改善物理解。

V13一次额外联合Taylor尺度复核及writer失败后的记录恢复保留。旧小实LS系数未保存仍为unknown，不能猜造。当前可用的是已保存的实际hidden/head/z；据两个已存hidden作新差向量是新derived数据，不能称找回了丢失的原LS系数。

## 2. 权威、范围覆盖和冻结身份

先读根／目录AGENTS、仓库原则、原task、全部补充合同／review、最新response/outcomes。本报告明确覆盖旧合同“候选必须由原始MLP输出层gamma回写产生”的限制，仅用于下述新家族。旧方法、旧1e-8头Gate、旧FD失败及V13结果都不变；不降低原物理门限。

新家族称为`ORTHONORMAL_NEURAL_FE_BASIS`：神经网络生成空间特征，确定性有限元矩映射与QR组成输出decoder，原方程求组合系数。它不再是单靠原3×64网络及原始输出层就能重建的场；必须保存decoder身份。不能称纯MLP推理、通用代理、精确VarPro梯度已通过或已形成可扩展生产求解器。

| 冻结项 | 值 |
|---|---|
| 方程／离散 | Full3D complex128；原Nédélec H(curl)；384hex／p3／h0.175 nm；full34050、trace18144、内部13824、slave2082 |
| 物理／边界 | 真空0.7 nm，grazing1度／azimuth0／s；原三维缺口；双Floquet／Fourier-DtN；完整top20+bottom20复端口 |
| 特征生成器 | 原3×64 tanh、8固定载波、FP64、q15、batch8；8576个hidden实参数，1560个复特征方向，不增宽／增层／增载波 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1 |
| Si／alias | n=0.999885140474+4.32477054e-6i，epsilon=n*n；source0.699999988→nominal0.7原行，不插值 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| mode SHA | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action NPZ SHA | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 NPZ SHA | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

原空气／mu、材料tags、master顺序、背景及入射RHS不变，现场从manifest核实全部数组hash。不再索要材料、不联网替换、不做四波长／网格／MPI扫描。旧p4强逆、ILU/Riesz逆、seed420620及其他任务工作树继续禁用。

可用于构造的是原S/b、原矩与几何、无标签生成的V13已保存hidden和原action数据。REF7、参考误差、D1拟合、参考幅相都不得用于选hidden、选步、求头或初始化。研究已消费历史诊断，只称同pilot续研；所有新求解冻结后，独立进程才读参考。

## 3. 新输出方式：直接得到原有限元系数，不再退回大head

设P(psi)由原网络隐藏特征、载波和全部Nédélec边／面矩组成。它的行是18144个canonical独立trace，列是1560个复特征。使用完整非pivoting economic Householder QR，不形成18144阶方阵：

```math
P(\psi)=Q(\psi)R(\psi),\qquad Q^HQ=I,\qquad t=Q(\psi)c.
```

在精确算术且满列秩时，Q和P张成相同空间，gamma=R^{-1}c可给出同一个t。但**新家族的主正向、loss、端口、恢复和交付都直接使用Qc**，不求R逆、不通过三角解回写gamma后再由raw MLP评估。原MLP head只可在独立历史对照中读取，不成为新decoder的必经环节。

这里Q组合的是合法独立Nédélec系数；slave仍由原MPC展开，内部仍按原局部方程恢复，因此仍交付原有限元空间中的解，不是节点PINN、另换弱形式或只输出边界外场。Q不是外部DtN模态，也不是沿z可分离的Hybrid空间。

保留40维凝聚端口Hhat的精确代数闭合，以下H不是原Hp：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\quad
\bar S=K-CH^{-1}F,\quad \bar b=b_t-CH^{-1}b_p,\quad
A_\psi=\bar S Q(\psi),\quad
c_*(\psi)=\arg\min_c\lVert\bar b-A_\psi c\rVert_2.
```

```math
t_*=Q(\psi)c_*,\qquad
\alpha_*=H^{-1}(b_p-Ft_*),\qquad
z_* = \begin{bmatrix}t_*\\\alpha_*\end{bmatrix},\qquad
\Phi_\perp(\psi)=\frac{\lVert b-Sz_*\rVert_2^2}{2\lVert b\rVert_2^2}.
```

bar S只作原作用，不物化完整矩阵。不同hidden点必须重建该点P/Q/A；不能沿用旧P/A、旧c或一阶gamma补偿。每个点独立用既有SciPy的GELSD、cond=1e-12求薄LS，无正规方程、无正则／rank扫描、无参考数据。有限精度记录为数值最小二乘，不声明精确全局最优。

**本批只做有限个hidden位置的profile（每个位置重新消去线性系数），不计算其全hidden梯度，不宣称训练了完整8576维非线性优化器。** 换坐标不改变精确空间，预期作用是改善前向数值路径；真正可能改变可达物理解的是有限hidden变化及其头重求。这两项贡献分别报告。

参考依据：Dong与Yang的[VarPro神经PDE论文](https://arxiv.org/abs/2201.09989)讨论线性输出系数与非线性隐藏参数分离；本批只是借鉴这一组织，不外推其配点数值结果。QR与LS按[SciPy QR](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.qr.html)、[SciPy lstsq](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.lstsq.html)的定义，执行使用现场已资格化版本，不升级环境。

## 4. 执行队列及不可混淆的比较

| 阶段／planned | 实际工作 | 分流 |
|---|---|---|
| O0 | 原点与五个已保存hidden的身份、解码schema、writer回归、资源 | 不重做F0或V13切向全套 |
| O1 | 同hidden正交trace基线、两个新decoder制造见证、一次基底敏感性对照 | decoder可信即O2；不要求物理解先变好 |
| O2 | 原点与V13五个有限hidden位置，逐点重求c/port，原方程独立审核 | 完成固定对照，不因第一点负而停；不可信点隔离 |
| O3 | 只有预登记的原方程进展才做最多两次同射线细化／延伸 | 不从参考选点；没有进展直接O4 |
| O4 | 全队列冻结后一次FE环境核查至多10个状态；收口 | 不回训，不扩大模型，不重复旧诊断 |

O1/O2都必须实际求解原物理RHS，不能用“QR通过”代替。若无法取得可信decoder，完成已有数组的有限原因记录后结束依赖路径；不强行降低Gate，但也不把材料、正常邻heavy或某个缺失trial误作整批阻塞。

### O0：身份和重复出现的记录失败

从V13 run index与coupled_step_history读取实际文件，不根据示例路径猜测。核对原点及C1_trial_0..4的hidden/head/z/hash；正式reprofile只取其中hidden，旧gamma只用于说明对应的历史对照。不要恢复已丢失的原小LS系数。

在现有Task042统一记录边界修一次嵌套Mapping／mappingproxy的JSON转换：小元数据递归转换，非有限量显式报错或标记，复数明确real/imag；大型数组只保存文件和hash，不能用default=str把结构藏成字符串。原始numeric与physical_identity分开命名，先原子保存候选参数／c／t／port和最小接受记录，再写派生汇总。用含mappingproxy、NumPy scalar、complex及异常中断的纯小测试覆盖，不重跑V13来修历史。范围只限本任务共享writer及其调用，不改系统或无关runner。

### O1：直接decoder数值资格，不再拿raw回写失败卡住新家族

复用原点hidden相同的已保存P和A时，先重建同一QR，并以三列加两个非零列组合与原bar S配对。若hash／QR坐标不匹配，只允许重建一次原点A并计费；不得混用不同Q的A。保持H条件数≤1e10、小solve operation residual≤1e-12、完整端口和原符号。

P重建与Q正交缺陷各≤1e-10；P与A按固定阈值均要求rank1560。实际t=Qc经原S得到的残差与thin预测，用固定原b归一化差≤1e-8；实际残差对A经济QR列空间的驻点缺陷≤1e-8。可用同一已核A作至多一次实际残差修正，修正c并直接重算Qc；禁止转回gamma。数值满秩只记numerical_full_column_rank。

新制造见证明确命名ORTHO-M1与ORTHO-M2，分别用seed421401的非零归一化c/port、以及由本次物理LS得到的c配上同seed的非零port。由原action.apply(z_known)生成各自完整b_m，再用同Q/A及正确的b_m端口常数回收；原制造残差≤1e-8、已知z差≤1e-6、齐次恢复配对≤1e-10。它们只测试新decoder；旧V11-M2的目标不是这两个向量，旧FAIL不能改成PASS，也不再重放旧M2。

正交化不消除P本身的子空间敏感性。因此原点只做一次独立的**逆序行QR**对照：临时对P行逆序作相同Householder QR，得到的Q必须先恢复canonical行顺序，再重新作原S列作用和相同LS。它没有改变物理行、MPC或列库存，不允许用其更低loss替换主非pivot基线。记录两套实际t、原残差、Phi的差、各自P重建与rank。两个正交Q逐元素不同不构成失败，要比较生成的场系数和原方程，不误把基底相位自由度当误差。

该对照只量化浮点实现敏感性，不能作为严格全部误差上界。若Q重建／原作用恒等式失败则停对应路径；若两种正确实现有明显差异，将其纳入下文比较余量，标BASIS_ROUNDOFF_SENSITIVITY，不挑好看的实现。禁止新高精度库、SVD阈值扫描或更换物理来救场。

## 5. O2：在相同有限hidden位置重新求头，真正检验旧一阶补偿

固定库存为原点psi0，以及已保存的五个C1_trial hidden。先解原点，然后按trial_4、trial_3、trial_2、trial_1、trial_0顺序。每个点从自身hidden生成P/Q/A，独立解相同物理b；不带入旧gamma、不依次warm start、不把旧点的Q/c搬来使用。

| 已有hidden身份 | V13 hidden改变量约值；仅导航，精确数组为准 | V13 raw头实际loss；历史measured | V14比较目的 |
|---|---:|---:|---|
| 原点psi0 | 0 | 0.3181799855089551 | 同空间直接Qc是否改善数值一致性，不声称改变表示 |
| C1_trial_4 | 3.2602241e-6 | 0.31817975803965803 | 在已接受小步上重求完整头 |
| C1_trial_3 | 1.3040896e-5 | 0.3181925772753522 | 检查原来轻度恶化是否来自有限步补偿 |
| C1_trial_2 | 5.2163586e-5 | 0.3216867803115054 | 同上，更大的有限hidden变化 |
| C1_trial_1 | 2.0865434e-4 | 1.2170618932558823 | 头重求能否避免严重过冲 |
| C1_trial_0 | 8.3461737e-4 | 230.44614448201773 | 不是重试旧头，计算该hidden空间的新最小残差候选 |

每个新候选记录c范数、P/A数值秩及奇异端点、Qc与原残差、完整native/port/恢复审核、构造与求解wall、RSS、source/hash。对比相同hidden处V13 raw候选与V14新家族；同时对比V14各点与V14原点，区分“稳定decoder/头重求”与“hidden空间改变”。高损失旧trial也可以产生新的好profile，但这只是待验证的假设。

五个旧hidden来自无标签原方程的试探，可以作为新实验输入；历史已消费，不声称独立终测。缺一个trial就标MISSING_FROZEN_STATE并完成其余库存，不重做V13小LS、切向和试探以补齐。如果所有有限hidden状态均缺失，至少交付可信原点decoder结果及具体缺项，不新扫随机方向。

每个点重新做同参数的完整残差重复检查。令delta_i为同点两次原作用诱导的Phi差、实际与thin残差差诱导的Phi尺度、100倍epsilon乘max(1,Phi)中的最大值。原点逆序行QR的Phi差记delta_basis，标为观察值而非误差定理。比较两个新点用margin=max(1e-10,100*max(delta_i,delta_j,delta_basis))；这个余量只控制研究选点，不是改变原物理通过标准。不能把小于此尺度的差说成可靠优化进展。

## 6. O3：一次有限profile继续，不重启完整训练

O2完成后，按**原实际Phi**选合格decoder库存中的最小值；并要求native不高于原点的1.05倍、全部port/recovery/identity通过。只有Phi较V14原点下降至少1e-4（相对）且下降超过margin，才准O3。若严格原方程已通过，跳O3优先O4。参考场此时不可访问。

用v=psi_trial0-psi0定义已观察的同一hidden射线psi(s)=psi0+s v。核对五个保存点对应s=1/256、1/64、1/16、1/4、1，允许舍入误差但不得用此推算替代原O2的已保存数组；v及配对只称新derived数据。若射线不一致或trial0缺失，O3不运行，O2结果有效。

只允许最多两次新profile评估。若O2最好点在最右端s=1，先试s=2；继续改善达到同一阈值才可试s=4。若最好点为内部正s，在它与已有左右相邻点之间各取一个中点，按先右后左顺序；不作新的多维搜索，不添加方向或seed。新hidden变化总量不得超过1e-3*max(1,norm(psi0))。每点仍完整重建并求头，没有一阶预测接受。两次都计费，不用参考选择区间。

已测试同一s时复用其证据，不能偷偷以新的seed再跑；没有合格进展直接O4。不为了“持续工作”跑满时间，不继续补偿gamma、单纯减学习率或扩大网络。此profile仅覆盖一条已观察方向；负结果不能证明所有hidden子空间变化无效。

## 7. O4：原有限元验证与明确结束规则

全队列及选择冻结，保存参数/c/t/port/Q身份后，独立FE进程才读既有REF7。一次环境比较V13原点和接受点两个历史状态、六个新固定profile、至多两个新点，共最多10个去重状态。逆序QR只在原方程坐标中做数值敏感性对照，不另复制一轮全场验证。参考不回传构造，不再训练或按参考改选候选。

严格门限保持：原Schur/native/完整增广及各规定port残差≤1e-6；恢复与identity≤1e-10、slave-zero；total/scattered E/H、scaled-curl、selected复场和完整40复通道差≤1e-4；R/T/A/A_volume绝对差≤1e-5、每通道功率差≤1e-6、能量闭合≤1e-5；近零沿原规则。新家族也必须用原未凝聚方程与独立DOLFINx审核，不仅用thin LS或Qc内部自检。未资格化功率只记diagnostic。

| 实际观察 | 收口分类／下一判断 |
|---|---|
| Qc前向仍不能通过原作用一致性 | STABLE_DECODER_UNQUALIFIED；记录失败点，不将它用于更大求解 |
| Qc通过但同hidden物理平台仍在 | EXPECTED_SAME_SPACE_LIMITATION；不能把换坐标称为物理进展 |
| 较大hidden经reprofile显著优于旧一阶头，且相对新原点也有进展 | FINITE_HEAD_REOPTIMIZATION_SIGNAL；仍要独立场合格，才讨论后续优化 |
| 只降Phi、散射与curl无实质改善 | OBJECTIVE_ONLY_IMPROVEMENT；不宣称神经有效 |
| 本射线所有profile均无实质改善 | FROZEN_RAY_PROFILE_NEGATIVE；关闭这条大头／同射线继续试验，不默认再开相同诊断 |
| 原残差与完整场均严格通过 | MICRO_DISCRETE_PASS_ONLY；本批不作新p4参考/目标放大，下一步先独立离散精度及容量资格 |

研究正信号另需rho=max(原Schur,native,固定RHS端口)较V14原点至少减半，散射E与scaled-curl各≤0.5且各改善≥25%。小的代数继续门限不等于这一研究正信号，更不等于最终通过。

若无进展，response应对当前“高相关全局神经特征＋同一残差目标”的具体方案给出收口建议，不再自动延长缩步/QR/切向循环；可提出一个明确不同的局部／自由度表示或求解设计，但本批不实施。保留全部有用的原算子、切向、端口和验算组件，不扩大为所有NN或Full3D iterative均不可行。

## 8. 资源、成本、实现与交付

新start起总elapsed最多14400 s，包含实现、测试、设置、求解和交付；start+13500 s停止重负载，末900 s收尾。独立deadline与整树watchdog先通过低成本清场测试，覆盖BLAS/JIT/FE/ML后代。历史V6起可核有载下界12160.139323 s保留，旧辅助未知仍未知；文档时间与监督wall分列，不清零方法lineage。

全批同时受限：完整P/Q/A求值最多10套（含逆序QR、新点及失败重建）；薄LS调用≤24、RHS总数≤28；原S/Sᴴ单向量等效作用合计≤18000；原完整audit≤80；两个制造RHS；新profile点≤2；全场验证≤10状态；不进行新的JVP/VJP或标量FD campaign。每列作用、测试、拒绝、失败与修复计费。未用完额度不是继续计算的理由。

一套18144×1560的complex128薄矩阵载荷452874240 B，P/Q/A三套合计约1.265 GiB，**只是derived数组载荷**，不是RSS；QR/LS副本、workspace、旧基、端口、验证及进程运行时全部入事前≤8 GiB规划和同时树峰。最多一套大基分解驻留，参数点顺序执行。初始和最终选择的Q/c可保留，其余新trial必须保存hidden/c/t/port、数值记录和全部hash，P/Q/A只作预先声明的可再生临时workspace；不删除既有negative artifacts。新持久大数组总量≤8 GiB，并遵守现场磁盘余量；不得把每个trial完整基入Git。

继续Task042既有受控共享CPU授权：其他heavy存在不自动阻塞；现场选空闲物理核，MPI1、数学/Torch线程1、DataLoader0、GPU不使用；自身swap0，整树warn12 GiB/hard16 GiB，保留系统及邻任务增长余量、自有锁和隔离cache。不改邻任务、锁、环境、亲和性、watchdog或系统ABI/BLAS/CUDA；无cgroup委派如实标采样监督，不能称连续内核cap或绝对零干扰。

新decoder与profile核放src/solvers，复用原数值／FE验证／监督，runner薄调度；不得再复制近千行runner或每点一整套程序。最多两次明确实现错误的最小修复，先提交clean source再正式运行；普通默认、材料、原方程和旧合同/records不变。每个新family显式opt-in，不把旧raw模型的checkpoint无标识加载为新decoder。

拟新增入口在本review提交时尚未实现，须由Codex先接线并验证：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v14_orthogonal_decoder.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v14_finite_head_profile.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v14_verify.dat
```

一个dat一个明确stage；第二项的固定hidden库存是同一物理RHS下已登记的算法对照，不是隐含几何/波长扫描。前置Gate通过后直接推进已授权O2/O3，不逐点等待用户；缺失或失败隔离到对应依赖路径。

建议commit序列：C1共享writer最小修复与schema/小测试；C2正交decoder与profile核/输入/测试，clean后正式O1/O2/O3；C3独立验证/原字段checker；C4compact结果与回应。证据即时保存，不在活跃运行中改变其受检HEAD。checker从raw重算，不只读status；测试故意错Q行序、旧A配新Q、制造RHS混物理常数、reference反馈、元数据覆写和缺通道等反例。

交付response_v14.md、outcomes/orthonormal_trace_reprofile_v14.md，以及records中的plan_and_input_identity、decoder_checks、basis_sensitivity、profile_points、candidate_comparison、channel_observables、run_index、resource_costs、qualification_and_dispatch、static/publication_checks等紧凑文件。每条正式run绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA与环境/资源/数组hash。大数组ignored；同步summary、tests、changed_files、任务导航、development_progress和development_model_registry，旧章节标历史但不删。

Markdown独立公式用fenced math，表列一致，本地结构及GitHub rendered view均检查；网页／大总账被截断如实标未验证，不复制全库文档或伪称通过。外部论文只是方法参考，不能替代本模型证据。

仅推送git push origin HEAD:refs/heads/task42_neural_coarse_inverse。最终报告精确HEAD/base/upstream/工作树、实际运行source、六点实际数量与缺项、主输出类型、decoder资格、每点原残差与场、真实神经贡献、全部构造成本及唯一下一建议。完成或达到边界后清场停止等待review，不merge master或其他分支。
