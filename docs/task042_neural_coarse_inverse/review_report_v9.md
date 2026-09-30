# Review V9：V11审查与真实残差驱动的隐藏层分块下降

## 0. 审阅决定、最终目标与本批 blocker

**接受V11的固定空间数值记录，不授予求解器资格。M2制造回收与实际头的原1e-8检查仍为FAIL，不提高该阈值、不回写为PASS。下一批不再把“输出头必须足够接近最优”作为一切隐藏训练的前提：改做固定输出系数时的真实原残差分块下降，随后有条件重求输出头。它不是精确变量投影，必须用自己的真实梯度和下降检查取得研究准入。**

要消除的障碍是：V10/V11均没有实际执行新的隐藏层更新，当前仍未回答网络改变表示后是否有用。V11的约4e-8头残差一致性缺陷与约0.798物理残差平台需要分开处理。前者妨碍直接使用精确VarPro驻点推导，但不能仅据此否定固定头目标的普通偏导。后者仍然是必须通过真实求解改善的核心问题。本批以实际隐藏更新和完整原方程验证为主，有限浮点分账是短入口，不单独再开一轮诊断campaign。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42_neural_coarse_inverse
worktree                   = /home/fenics/Projects/NN-Lab
review_date                = 2026-09-30
reviewed_HEAD              = db479ec0b55b498d851d46ed972fcc9b9873054a
reviewed_commit_UTC        = 2026-09-29T23:54:21Z
reviewed_commit_Singapore  = 2026-09-30T07:54:21+08:00
original_base_SHA          = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review            = review_report_v8.md
previous_review_commit     = 38a68de138fc01537dc8a63f122e25c64b820a37
latest_response_reviewed   = response_v11.md
V11_MAIN_source             = a2cba71533edafb4fa1c701eae503e7ab526eac4
V11_REPLAY_VERIFY_source    = 036e36ec637488b1baddd9b061c80c6f34cde254
V11_checker_source          = c6c650ad18f278aa1a33cddd9395f899104b3bc2
next_batch                  = V12_ACTUAL_LOSS_BLOCK_DESCENT
response_required           = response_v12.md
review_decision             = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
old_p4_inverse_route         = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate          = NOT_QUALIFIED
master_merge                = NOT_APPROVED
```

最终目标保持：约2 TB工作站资源内，对新的真正非可分三维周期单胞，端到端48小时以内得到合格0.7 nm有限元解。当前384-cell micro不是目标规模，2 TB不是本研究可占满的RSS。本批仍为16 GiB上限、单核受控共享CPU试验，不能以材料波长标签、低RSS或有限隐藏更新冒充最终通过。

ChatGPT实际读取了远程V11合同、回应、summary、制造与稳定头原记录、相关源码和最近提交；未SSH重跑，未取得工作站全部ignored数组。本文measured是仓库记录；公式是代数推导；新路径均为planned/not_run。本轮ChatGPT只新增本报告，不替Codex修改实现或运行PDE。

## 1. V11的结果与审查判断

依据：[Response V11](response_v11.md)、[详细结果](outcomes/stable_head_varpro_v11.md)、[制造回收](outcomes/records/manufactured_recovery_v11.json)、[稳定头](outcomes/records/stable_head_checks_v11.json)、[原物理对照](outcomes/records/candidate_comparison_v11.csv)、[费用](outcomes/records/resource_costs_v11.json)。下表均为同一固定micro，残差与误差无量纲，分母保持原记录。

| 检查／measured | V11实际值 | 原门限与本次判断 |
|---|---:|---|
| M1稳定头制造残差／已知z相对差 | 1.23470e-14／5.53650e-13 | 分别1e-8／1e-6，PASS；raw也通过 |
| M2初始稳定头／唯一修正后制造残差 | 3.11751e-7／2.89518e-8 | 1e-8，仍FAIL；不是资源停止 |
| M2修正后已知z相对差 | 4.09879e-10 | 1e-6，PASS；不能单独覆盖残差FAIL |
| 物理头实际残差对薄预测之差 | 3.95983e-8 | 固定原b分母、原1e-8，FAIL |
| 物理头实际Uᴴr／原b范数 | 9.62240e-9 | 1e-8，PASS，但不等于所有头检查通过 |
| 原Schur／native残差 | 0.797721737837／0.309359506591 | 各1e-6，FAIL |
| 散射E／scaled-curl相对差 | 0.734256809／0.734361587 | 各1e-4，FAIL |
| 固定RHS端口／内部恢复 | 2.051e-19／6.104e-13 | 分别1e-6／1e-10，通过；slave-zero为0 |
| 真实VarPro FD／隐藏试探／接受更新 | 0／0／0 | 未运行，不是隐藏学习已被证伪 |
| 三正式阶段监督wall／采样同时树峰 | 574.980116768 s／4668329984 B | 约4.347 GiB、own swap0；非目标规模性能 |

P的奇异端点20.2000462与8.02752e-10给出条件数约2.52e10；正交后A的995.708484与0.00547401给出约1.82e5。这是两个薄矩阵的derived比值，不是原Maxwell算子S的条件数。实际网络与Pγ trace相对差2.461e-11，大系数约1.278e5，说明表示坐标仍存在敏感性。[源码](../../src/solvers/stable_head_varpro.py)中的原S、QR、三角回写与[梯度模块](../../src/solvers/stable_head_varpro_torch.py)必须分别看待。

残差向量差约4e-8不能直接解释0.798的残差范数：在相同固定b归一化下，两范数之差不超过两向量差。这只约束这两个已测计算结果，不证明真实连续最优或全局条件数。不能据此承诺隐藏训练会成功，也不应继续把所有算力用于把2.9e-8压到1e-8，而不验证真正的隐藏下降。

V11按旧合同停止是正确执行。需要修正的是后续算法与准入设计，不是把Codex的合规停机写成失职。MAIN数值`physical`键被身份元数据覆盖的封装问题和后续修复保留；不得以元数据缺项重新进行整轮分解。V11有载总账含已核对下界11734.145535666961 s，辅助工作未独立精确计时，不能把下界当全历史精确总成本。

## 2. 权威、冻结身份和明确覆盖

先读根／目录AGENTS、[仓库原则](../repository_work_principles.md)、task、全部已有review／补充合同、最新response和summary。旧task与review不修改。本报告明确覆盖Review V8中“S1/S2未达到1e-8就禁止所有隐藏更新”的条款，**只对本批不依赖头驻点的分块目标及有界函数值备选有效**。精确VarPro的旧Gate仍FAIL，本批不把近似头导数冒称精确VarPro，不恢复旧p4逆、普通ILU、列尺度扫描或监督代理。

| 冻结对象 | 本批值 |
|---|---|
| 物理／离散 | Full3D complex128；Nédélec H(curl)；原三维缺口384hex/p3/h0.175 nm；真空0.7 nm、grazing1度/azimuth0/s；双Floquet/Fourier-DtN |
| 自由度 | full FE34050；独立trace18144；内部13824；slave2082；完整top20+bottom20复端口；reduced18184 |
| 网络 | 原3×64 tanh、8载波、FP64、q15、batch8；8576 hidden实参数、1560复输出系数 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1；source0.699999988明确alias至nominal0.7 |
| 材料SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| mode SHA | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action packet SHA | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 NPZ SHA | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

Si继续n=0.999885140474+4.32477054e-6i、epsilon=n*n，air/mu与旧物理不变。不重新索要或联网替换材料。其余输入、master顺序、q15矩、背景、RHS、端口键和实际参数hash从原manifest核对。

本批主起点是V11唯一修正后的**物理**网络参数和输出头；其hidden仍是seed420906随机初始化，头由原方程求出，不读NN7或参考fit。历史算头成本计入方法lineage，不能宣称新方法从零只花本轮训练时间。缺该state时，可从原seed与已存P/A重求一次物理头；不要用M2制造头、旧参考、D1拟合或另一候选替代。缺失部分只阻塞对应依赖项，不重跑V7–V11整个campaign。

参考只在本批求解队列全部冻结后独立验算。它不参与梯度、步长、头选择、停止时机、幅相校准或选最佳checkpoint。历史已经看过诊断，称同pilot续研，不称fresh blind study。旧seed420620继续封存。

## 3. 执行队列：一次短分账后，实际尝试改变隐藏层

| 阶段 | 内容及准入 | 之后的动作 |
|---|---|---|
| T0 | 读取身份、保存状态和原预算／资源；复用已有接口 | 不重建F0，不重跑长参考 |
| T1 | 对固定M2与物理头作一次残差来源分账，最多600 s | M2原Gate失败本身不阻止独立T2 |
| T2 | 真实网络、固定γ、原端口闭合的loss／偏导检查 | 通过则直接T3；没有可信梯度但函数值稳定可进F |
| T3 | 每块最多20个接受hidden步，共至多3块；块间至多一次头建议 | 以真实loss接受／拒绝，有进展才延长；不要求先取得物理P+ |
| F | T2导数不合格或首块无下降时，一次有限函数值poll | 至多8个试探、1个接受状态，不伪称梯度训练通过 |
| T4 | 全队列冻结后一次FE环境验算；记录收口原因 | 不回训、不扩大模型，交付response_v12 |

T1只是诊断，不再以“进一步拆误差”作为唯一新增工作。若原算子、MPC、符号、参考身份或资源安全实际失败，则停止受影响路径；不能为避免all-not-run而使用错误算子。若T2不通过且函数值也无法分辨，允许有证据地结束，而不是强迫产生接受步。

## 4. T1：只对既有大系数做一次误差分账

复用V11保存的P、A、R或可重建的同一QR，以及M2／物理γ、c和实际网络状态。每个状态区分：t_Z=Zc、t_P=Pγ、t_N=真实网络经原矩映射的trace。对任一t均用相同rhs闭合端口，以原作用计算r(t)=bar b-bar S t；薄预测为r_hat=bar b-Ac。

```math
r(t_N)-\widehat r=
\bigl[r(t_N)-r(t_P)\bigr]+
\bigl[r(t_P)-r(t_Z)\bigr]+
\bigl[r(t_Z)-\widehat r\bigr].
```

分别报告网络回写、三角坐标／QR重建以及列作用组合的差向量范数和重组缺陷；范数不能直接相加冒充向量恒等式。已存c不可得时可使用c_diag=Rγ，但明确为新诊断坐标，不假称还原旧LS的c。没有足够数组则输出partial并继续T2，不为填表重复1560列原作用或新全局分解。

M2的rhs/相对分母必须用其原制造rhs；物理头用原物理b。默认recover含内部特解，误差用F(z1)-F(z2)或F(e)-F(0)。最多32次等效S/Sᴴ、一次可复用的P economic QR；不新增随机制造RHS、精度扫描、rank阈值扫描或新高精度库。原1e-8失败保留。不把本分账指标改名为求解器资格。

## 5. T2：固定头目标的偏导，不使用精确VarPro驻点假设

### 5.1 方程与真实计算对象

继续原40维Hhat精确端口闭合，H不是原Hp。以下bar S只用于作用，禁止物化完整矩阵：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\quad
\bar S=K-CH^{-1}F,\quad \bar b=b_t-CH^{-1}b_p,\quad
\alpha(t)=H^{-1}(b_p-Ft),\quad
\bar S^H=K^H-F^H H^{-H}C^H.
```

设γ_k是本hidden块固定的输出系数，ψ为hidden实参数。t_N来自**实际网络前向和原Nédélec矩映射**，不是从存下的P估算新hidden输出。优化的是：

```math
r_N(\psi;\gamma_k)=\bar b-\bar S t_N(\psi;\gamma_k),\qquad
J_k(\psi)=\frac{\lVert r_N(\psi;\gamma_k)\rVert_2^2}{2\lVert b\rVert_2^2},\qquad
\frac{\partial J_k}{\partial\psi_j}
=-\frac{\operatorname{Re}\!\left[r_N^H\bar S\,\frac{\partial t_N(\psi;\gamma_k)}{\partial\psi_j}\right]}{\lVert b\rVert_2^2}.
```

这个公式是**固定γ的普通偏导，对任何有限γ都成立**，不要求Pᴴbar Sᴴr=0、不忽略一个本应存在的dγ项。它不是消去γ后的Phi梯度。端口始终随t精确重算，因此Hhat的共轭转置链仍必须包含；端口不是冻结变量。内部场仍用原局部仿射恢复。

复用`PortBlocks.adjoint`及batch8 VJP，只取8576个hidden实参数梯度，不对QR/SVD自动微分，不构造全hidden Jacobian/Hessian。新记录使用`FIXED_HEAD_PARTIAL_GRADIENT`，不要沿用`scalar_envelope_only=true`冒称VarPro。现有`set_hidden()`会清零输出层：**每次赋值hidden后必须重新assign_head同一个γ_k，并检查该块γ的hash不变**，否则测试和训练会悄悄变成另一个目标。

### 5.2 数值准入与有限差分

原算子／MPC和40维H的符号、shape、finite、cond(H)≤1e10、小solve≤1e-12、共享矩映射等未变证据可复用，新增路径进行非零配对。正常原作用身份目标1e-10不放宽。T2无需重新求出最优头，也无需把M2的旧FAIL改成PASS。

在实际非零γ和端口状态下，比较同点两次batch8前向及一次原batch1前向的**完整原loss**，并检查实参数梯度、端口闭合和完整原S审核。设delta_eval为这些同一参数／相同数学函数求值的最大绝对loss差与100倍机器epsilon乘max(1,J)的较大者。它是观测分辨率，不是严格的全部前向误差界。若delta_eval>1e-6*max(1,J)，记FUNCTION_VALUE_UNRESOLVED，只作有限分账；不能据此作可靠训练／poll。以后每个块边界重复检查。

小型复数非Hermitian测试先验证：γ显著非最优时，本固定头偏导仍正确；不要拿固定头FD去资格化VarPro。真实方向为seed421201、421202两随机单位hidden方向及非零解析梯度单位方向；梯度为零用seed421203替代，但不能三方向近零充数。h依次1e-3、1e-4、1e-5、1e-6、1e-7，可取得稳定区后停止，最多30个扰动前向。

**本次FD固定γ，不重建P/A、不重求头，每个扰动只重算真实网络与端口。** 每方向至少一个非零稳定区relative≤1e-5，且相邻h趋势支持而非噪声偶合；近零absolute≤1e-10，差分信号应明显高于delta_eval/h，报告实际比值，不在分辨率以下宣布通过。T2通过直接进入T3；不能再用旧驻点条件或散射误差0.5门槛阻止第一块。

## 6. T3：有界真实下降与头重求，分别提交状态

唯一主候选`ACTUAL-LOSS-PORT-CLOSED-BLOCK-DESCENT`。不改网络宽度、载波、激活、q15、材料或loss范数。每hidden块固定γ，最多20个接受步；用仅针对hidden的L-BFGS，history≤5，初始负梯度，曲率对和非下降退回规则沿V11。头改变时**清空L-BFGS历史**，因为固定头目标已改变，不能混用前一目标的梯度差。

初始步长限定hidden相对变化，最多8个回退试探：

```math
\alpha_0=\min\!\left(1,\frac{10^{-4}\max(1,\lVert\psi\rVert_2)}{\lVert d\rVert_2}\right),\qquad
\alpha_j=\alpha_0\,4^{-j},\quad j=0,\ldots,7.
```

各试探保持γ_k并重算t_N、端口和原loss，**不重建或求解线性头**。令m=max(1e-12,20*delta_eval)。接受需真实下降满足Armijo并超过分辨率：

```math
J_k(\psi+\alpha_jd)\le J_k(\psi)+10^{-4}\alpha_j g^Td-m.
```

接受点立即复算loss并核对参数hash，差超delta_eval时重新计算分辨率并拒绝不可分辨点，不以thin-predicted loss选步。端口固定rhs残差≤1e-6、全部finite、资源和原身份检查同时满足。每个接受点做一次原audit，体场仍可未合格；每5个接受步及块末保存完整一致的网络／端口事务。8个试探都拒绝则结束该块，不无限缩学习率。预算中断恢复最近接受的ψ/γ/α/z/优化状态，成本不回滚。

**块末头建议：**如果hidden实际改变，允许在当前ψ上重建一次P/Z/R/A并用原稳定头算法重求γ（至多一次同分解残差修正）。这只是一个候选头，不要求在浮点下成为精确最优。保留旧γ作为零改变量选项；新γ必须回写真实网络、重新闭合端口，并按同一实际loss下降超过m且native不超过块末旧γ的1.05倍才接受。拒绝头建议时保留已经接受的hidden与旧γ，不能丢弃此前真实改进。

QR／原作用配对错误、非有限、rank异常阻止该次头建议，不自动否定仍可信的固定头hidden路径。数值满秩与原1e-8头Gate分别记录；1e-8仍未通过的新头可以作为有限的非最优参数建议，但只能在真实loss验证下降后采用，不能使用精确VarPro导数声明。输出系数范数超过10倍本批初始max(1,norm(γ))则拒绝，标COEFFICIENT_GROWTH_GUARD，不裁剪权重或改正则项救场。

第一块数值准入后直接尝试。若块末（含可接受头）相对该块起点J下降至少1e-4且超过20*delta_eval、native≤该块起点1.05倍、端口合格，则自动第二块。第三块还需累计J较初始下降至少1%、第二块自身仍满足上述进展条件。最多3块／60个接受hidden步／3次块末头建议。这里是研究继续阈值，不是物理通过。每次接受新头后，在当前点再做一个非零固定头方向FD；不过则停止依赖梯度路径，保留已有候选。

若已达到所有原方程Gate，可提前T4；否则不得只因有一个小loss下降就扩大模型。若梯度很小但原残差大，记录STATIONARY_BUT_NOT_SOLVED，不把它当收敛成功。最终使用last committed，不凭参考选最好状态。

## 7. F：一次函数值备选，不使用未经验证的梯度定理

仅当T2梯度无法资格化而完整函数值可分辨，或首块全部步长拒绝且没有接受hidden步时准入。复用同一个当前ψ/γ和精确端口，不增加网络，不重建头。

两个方向固定为：有限非零负梯度的单位向量（只作方向建议，不称梯度可信；不存在则seed421204随机单位向量），以及seed421205的随机单位向量。每方向试正负号与两种步长，hidden步长分别为1e-5和1e-6乘max(1,norm(ψ))，合计最多8个实际前向。所有值使用真实网络与原S，最小loss点重新评估确认，仅下降超过max(m,1e-4*当前J)且native不恶化超过5%、端口通过才接受；否则均负结果。

最多1个接受hidden状态，准确标`FUNCTION_ONLY_POLL`，不能算梯度检查通过。允许随后至多一次同T3规则的头建议，计入全批头预算；之后直接T4，不开展新的poll、随机方向搜索或回到长训练。本路径是有限零阶试验，不是全局优化保证，也不得用它掩盖T2失败。

## 8. T4：冻结后独立验算和研究取舍

全部求解、FD、头建议和F结束并冻结hash后，单独验证进程才读REF7。一次FE环境比较初始状态、每块hidden结束状态和接受头后的状态、F接受状态；最多8个，重复向量去重。不为每个trial重建FE，不重复V9区域积分或V10 curl/mass诊断。参数、端口、t均通过原映射恢复，误差内部特解正确抵消。

严格标准保持：原Schur/native/完整增广及规定端口残差≤1e-6；恢复≤1e-10、slave-zero；同离散total/scattered E/H、scaled-curl、selected复E/H及完整复通道≤1e-4；R/T/A/A_volume绝对差≤1e-5；逐通道功率差≤1e-6；能量闭合≤1e-5；近零absolute1e-12及原分母不改。只在全部合格时授予该micro的同离散资格，仍非p/h收敛或目标48小时资格。

以本批真实起点定义rho=max(Schur,native,固定rhs端口残差)。研究正信号要求rho至少减半、散射E及scaled-curl误差各≤0.5且各较初始改善至少25%。只降loss、场不改善标OBJECTIVE_ONLY_IMPROVEMENT；实际接受hidden步但未过研究阈值标BOUNDED_HIDDEN_UPDATE_NEGATIVE，不改写为未运行。梯度／函数值／预算阻塞则分别记录，不能统称“NN无效”。

即使只剩有限误差，也不修改原精度标准。本批不进行新的p4参考、p/h/MPI/通道扫描、最大模型、GPU训练或旧p4 PC。独立参考验证开始后不回传任何优化信息、不重开求解队列。最后只给一个有证据支持的下一步；没有进展则明确本固定架构短试验负结果，不再自动追加一批相同设置。

## 9. 时间、作用次数、资源和无人值守边界

从Codex接手登记新的UTC、Asia/Singapore及单调时钟start，总elapsed最多14400 s（4小时，含实现、测试、设置、训练、验算和交付），最迟start+13500 s停重负载，最后900 s收尾。它是停止预算，不是预计耗时。复用独立deadline／整树watchdog，确认BLAS/JIT子进程也受控；不用旧V11已结束的时戳，不因重试、上下文或分支刷新重置。

上限同时生效：T1≤600 s及32次原作用；全批真实loss前向≤900、VJP≤240；完整P/A构建≤4次（含必要初始重建）、薄头求解／同分解修正≤8次；S与Sᴴ总等效单向量作用≤15000；原完整audit≤100；F≤8试探／1接受。测试、FD、拒绝试探、头建议和失败修复均计费。达到更早上限就安全停止，不要求跑满。预计阶段不能留出300 s安全清场余量时不启动大QR/SVD。

保留V11有载下界与辅助费用未知的原口径；本批elapsed、正式整树wall、算法子项和lineage成本分列，不把不同层级嵌套时间重复相加，不把历史下界包装成精确累计。初始V11头及共同FE/moment设置成本列入该方法从零成本。若新增成本可精确测量则如实报告，不能补造旧辅助秒数。

继续已有受控共享CPU授权，其他heavy存在不自动阻塞Task042；现场选空闲物理核避忙SMT，MPI1，数学/Torch线程1，DataLoader0，自有锁与独立环境／缓存，仅降低自身nice/I/O优先级。只监督、停止自己的后代，不修改邻任务、HEAD、锁、环境、亲和性、优先级或watchdog。无GPU、ABI/CUDA/BLAS升级、OOC或swap。

整树hard16 GiB／warn12 GiB，事前同时常驻规划≤8 GiB；系统reserve=max(128 GiB,effective_total的10%)，另留128 GiB邻增长及本任务预算。磁盘自由≥50 GiB，Task042全部artifacts≤20 GiB。无cgroup委派时0.5 s采样不称内核连续上限；warning不新分配大矩阵，hard／own swap／持续压力／监督失效停止自身重负载。最多两次间隔5分钟的只读资源复核，不永久等待或后台重启。

T1后不让无用P/Z/A与网络图全程共驻留；块内只需原packet、network、固定矩映射与工作向量。块末单套头工作区，保存参数和结果而非全部trial薄矩阵。可释放可重建临时工作区，不删除旧负结果或已发布证据。工程成本和算法改进分别汇报，不能把少做头重建的时间收益冒充物理解通过。

## 10. 实现、正式入口和提交

复用已有`stable_head_varpro.py`、`stable_head_varpro_torch.py`、`neural_trace_batched.py`、端口、事务、runner与checker。数值核新增明确分块名字，不能把原VarPro函数静默改义；新核心进入`src/solvers`，不要继续在911行runner里堆另一套算法。普通默认、原材料和数值核不受影响。

先提交必要实现与小测试，运行前clean，绑定source；一个`.dat`表示明确stage／同一物理operator及预登记块／FD库存。建议新建以下research入口（**本报告提交时尚不是可运行文件**），复用`python scripts/run_case.py`：

```text
input/task042_neural_coarse_inverse/v12_roundoff_audit.dat
input/task042_neural_coarse_inverse/v12_block_descent.dat
input/task042_neural_coarse_inverse/v12_verify.dat
```

T1结束可先保存证据，继续已授权T2/T3而不逐步等确认。实现错误最多两次最小修复及针对性重放，数值停滞不算bug；不因此重复V7–V11。所有运行必须保存input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json、环境／MPI／线程／资源和artifact hash。

最少交付`response_v12.md`、`outcomes/actual_loss_block_descent_v12.md`及紧凑记录：

```text
plan_and_input_identity_v12.json
roundoff_decomposition_v12.json
fixed_head_gradient_checks_v12.json
block_descent_progress_v12.jsonl
head_proposals_v12.json
candidate_comparison_v12.csv
qualification_and_dispatch_v12.json
run_index_v12.json
resource_costs_v12.json
```

每条状态列出算法类型、ψ/γ/z/hash、gamma冻结标志、delta_eval、步长、真实loss、原审核、接受原因、头是否刷新、L-BFGS是否重置、剩余预算。固定头梯度、函数值poll、头建议和VarPro资格分别标记，不能用一个PASS覆盖。独立checker从原字段重算，含坏gradient、gamma意外改变、loss不降却被接受、错port和缺通道等反例。

同步本任务README最新导航、summary/test_summary/changed_files和development_progress、development_model_registry；旧task、Review V1–V8、Response V1–V11和旧raw保持。Markdown按fenced math／表格列数／相对链接检查；本地渲染与GitHub实际页分开，页面不可取则如实未核验，不伪称通过。

只推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`；不amend、强推、merge/rebase或改其他worktree。阶段边界可安全提交后继续授权队列，不在活跃run中改变其受检HEAD。结束报告完整HEAD、upstream/worktree、真实source、实际hidden接受数、是否只改头、原物理资格、全部成本和唯一下一建议，清场后停止等待review。

## 11. 方法依据和限制

[Dong与Yang的VarPro神经PDE研究](https://arxiv.org/abs/2201.09989)区分线性输出与非线性隐藏参数。本批不是复制其配点算法，也不继承其精度保证；本文固定头偏导由链式法则直接推导，与精确消去输出层后的导数明确区分。

[Netlib线性最小二乘误差分析](https://netlib.org/lapack/lug/node83.html)说明小后向误差与解的前向敏感性不同；数值满秩不是精确最优证明。该分析不能替代本任务原网络／原作用的实测。

**本批不宣称神经网络能够绕过Maxwell求解困难。它只把“先把头解到极高精度才允许动hidden”的逻辑，改为“对当前真实函数验证偏导，并只接受可分辨的实际下降”。旧严格VarPro Gate不改；最终物理标准不改；隐藏层改进若仍无效，必须如实收口。**
