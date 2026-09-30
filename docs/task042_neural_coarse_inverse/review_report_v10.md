# Review V10：V12审查、独立切向导数与输出头补偿试验

## 0. 决定、快照与要消除的障碍

**接受V12作为有边界的数值负结果，不授予求解器资格。下一批先独立核对“参数变化如何改变trace及原残差”，再按实际方程响应确定步长；固定输出头方向无可分辨收益时，继续尝试少量隐藏方向与输出头补偿的联合局部更新。不能再次只做一张导数检查表便结束所有已授权工作。**

本批针对的blocker是：当前神经trace表示尚未产生合格的0.7 nm微型三维解，且大输出系数下的参数敏感性使先前差分与固定头搜索难以解释。目标仍为约2 TB工作站资源内，端到端48小时获得一个新的、真正非可分三维周期单胞的合格0.7 nm有限元解。本批是求解器／表示研究，不是参数扫描代理、p4强逆或目标规模运行。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42_neural_coarse_inverse
worktree                   = /home/fenics/Projects/NN-Lab
review_date                = 2026-09-30
reviewed_HEAD              = 0b81d4cdad2dd2e3c21a68e60b14c35fdc897337
reviewed_commit_UTC        = 2026-09-30T01:45:20Z
reviewed_commit_Singapore  = 2026-09-30T09:45:20+08:00
original_base_SHA          = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review           = review_report_v9.md
previous_review_commit    = f81e9301d98c7e0a7006ae34981ecc27e11dd2dc
latest_response_reviewed   = response_v12.md
V12_successful_run_source  = d9df7068ca3310a0499164251a57841dbdfbc7f5
next_batch                = V13_TANGENT_SCALE_AND_HEAD_COMPENSATION
response_required         = response_v13.md
review_decision           = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
old_p4_inverse_route      = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate       = NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

ChatGPT审查的是远程文档、原始标量记录和源码，没有SSH运行工作站、读取全部ignored数组或验证当前邻任务实时状态。下列结果属于measured，步长趋势分析属于derived/inference，新算法与预算属于planned。约2 TB不是本任务可占满的RSS；本批仍受16 GiB研究上限。

## 1. V12接受哪些事实，不作哪些推断

依据：[Response V12](response_v12.md)、[summary](outcomes/summary.md)、[方向差分](outcomes/records/fixed_head_gradient_checks_v12.json)、[真实试探](outcomes/records/block_descent_progress_v12.jsonl)、[分账](outcomes/records/roundoff_decomposition_v12.json)、[费用](outcomes/records/resource_costs_v12.json)、[固定头实现](../../src/solvers/actual_loss_block_descent.py)、[分块矩与VJP](../../src/solvers/neural_trace_batched.py)。

| 同一micro；无量纲measured，分母沿原记录 | V12结果 | 审查解释 |
|---|---:|---|
| 原Schur／native相对残差 | 0.797721738／0.309359507 | 原1e-6门限失败 |
| 散射E／scaled-curl相对误差 | 0.734256809／0.734361587 | 原1e-4门限失败 |
| 固定头梯度三个方向最小h的相对差 | 0.06346／0.07599／0.17425 | 旧差分Gate失败，不等于已证明解析导数错误 |
| 同点batch8 loss／batch1 loss | 0.3181799855089551／0.31817998550895316 | 重复性好，不是所有扰动点的严格前向误差界 |
| F八次函数值试探的最低loss | 2.804607898 | 高于初始0.318179986，0个接受状态 |
| hidden接受数／头建议数 | 0／0 | T3未运行；F确实运行并为负，二者分开 |
| 正式监督wall／同时树峰 | 182.268 s／2322427904 B | 约2.163 GiB、own swap0；不包含全部研发elapsed |

在解析梯度单位方向，中心差分斜率随h=1e-3、1e-4、1e-5，约为-4.6371e6、-4.6371e4、-463.465，而解析斜率约0.252912。前几档偏差约按h平方缩小。F的正负试探均值减去起点，在相对步长1e-5与1e-6间也约相差100倍。这与显著截断／二次变化相符，但不证明导数正确，也不证明只要无限缩h就会成功。

V11输出系数范数约1.278e5，P的奇异值比约2.52e10。固定这些系数改变hidden可能破坏大项抵消；这是待量化机制，不是已测全局Hessian或S条件数。约4e-8的旧头一致性缺陷不能解释约0.798的全部物理残差平台。V11的1e-8头Gate、V12原差分Gate和既有负结果全部保留。

此前由ChatGPT规定的固定差分／试探尺度没有充分利用实际残差敏感性，后续应改进检查与局部模型，不应把Codex按合同停机写成失职。也不再把“重复性好”解释为扰动处无相消误差。

## 2. 合同覆盖、冻结身份和数据隔离

先读根／目录AGENTS、仓库原则、原task、全部补充合同和review、最新response/outcomes。原task及旧review不改。本报告明确用下述独立切向核验和小规模局部模型，替代Review V9的固定标量FD步长准入、固定头L-BFGS及两档F扫描；不把旧FAIL追溯改为PASS。它既不是精确VarPro，也不是全hidden Gauss–Newton。

| 冻结项 | 值 |
|---|---|
| 模型 | 原Full3D三维缺口，0.7 nm，grazing1度／azimuth0／s，双Floquet／Fourier-DtN |
| FE／规模 | complex128，Nédélec p3，384hex，h0.175 nm；full34050／trace18144／内部13824／slave2082／完整40复端口 |
| 网络 | 原3×64 tanh、8固定载波、FP64、q15、batch8；8576 hidden实参数、1560复head系数 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1 |
| Si／alias | n=0.999885140474+4.32477054e-6i，epsilon=n*n；source0.699999988明确alias至nominal0.7 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| mode SHA | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action NPZ SHA | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| 既有REF7 NPZ SHA | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

起点使用V12保存的INITIAL_V11_CORRECTED物理状态，等价于V11唯一修正后的物理网络；从manifest核对实际文件、hidden/head/z/hash、master及通道顺序。不得使用M2制造头、NN7或D1参考拟合替代。材料ready，不再索要／联网替换；不做四波长扫描。读不到当前state时，只允许回读其V11父state并核对同一参数身份，缺失则阻塞依赖项，不重新跑历史campaign。

原S/b、moment、P/Z/R/A及无标签求出的参数可作为本批输入。REF7、参考误差、拟合权重或参考幅相不能参与方向、尺度、补偿、初值、选步或停止条件。求解队列全部冻结后才允许独立验证读取REF7；之后本批不回训。研究设计已消费历史诊断，只称同pilot续研，不称fresh blind或新几何泛化。

## 3. 有限自动队列

| 阶段／planned | 要回答的问题 | 分流 |
|---|---|---|
| A0 | 冻结状态、原算子、资源与预算身份是否一致 | 复用原环境，不重做F0 |
| A1 | 独立前向切向与现有反向链是否一致，向量线性化是否可信 | 真实链路错误先最小修复；可信方向直接进B/C |
| B | 固定head的方向按实际响应选步长，有没有可分辨下降 | 至多1个接受点；收益不可分辨或试探失败转C，不无限缩步 |
| C | 同起点下，让head补偿hidden变化是否能获得有效方向 | 初次最多6个试探；有实际进展才继续，最多3个接受联合步 |
| D | 冻结后完整原方程和场审核，区分实现、方向、成本、物理资格 | 一次FE环境，最多8个去重状态；收口不回训 |

B与C从相同起点独立比较，B的结果保留，但不作为C的warm start。B失败不是C禁入条件；C不要求旧1e-8头驻点Gate或旧P/P+先通过。A1的可信导数与原算子身份仍是必要条件，不能为了产生一个接受步使用已知错误链路。可用方向不足3个时做其余方向，标明库存，不无限添加随机方向。

## 4. 原方程、独立JVP与核验对象

H以下均为原凝聚40维Hhat，不是Hp。S及bar S只作作用，不物化完整矩阵；H条件与小solve继续沿用cond2≤1e10、operation residual≤1e-12。

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\quad
\bar S=K-CH^{-1}F,\quad \bar b=b_t-CH^{-1}b_p,\quad
\alpha(t)=H^{-1}(b_p-Ft),\quad r=\bar b-\bar S t_N(\psi,\gamma),\quad
J=\frac{\lVert r\rVert_2^2}{2\lVert b\rVert_2^2}.
```

JVP是“给一个参数变化方向，算全部trace的一阶变化”，不构造完整Jacobian。必须实现独立于现有`.backward()`的逐层切向递推，批量不超过8，沿用全部原矩、Piola、orientation和MPC。可在已安装版本支持时另用torch.func.jvp配对；不为此升级Torch/ABI，也不能把双反向AD包装成独立手推见证。

```math
h_\ell=\tanh(W_\ell h_{\ell-1}+b_\ell),\qquad
\dot h_\ell=(1-h_\ell^2)\odot
\left(\dot W_\ell h_{\ell-1}+W_\ell\dot h_{\ell-1}+\dot b_\ell\right).
```

固定head时输出切向由gamma乘hidden切向；联合切向还须包含head变化乘当前hidden项。八载波本批固定，不求其导数。输入坐标不是本批可训练量。实现读取冻结权重，不能意外清零输出头；每次set_hidden后重新assign_head并核对hash。

```math
\dot t=J_\psi d+P\dot\gamma,\qquad
\dot\alpha=-H^{-1}F\dot t,\qquad
S\begin{bmatrix}\dot t\\\dot\alpha\end{bmatrix}
=\begin{bmatrix}\bar S\dot t\\0\end{bmatrix},\qquad
J'[d,\dot\gamma]=-
\frac{\operatorname{Re}(r^H\bar S\dot t)}{\lVert b\rVert_2^2}.
```

切向端口是齐次式，不能调用带原b的闭合后把常数项混进导数。误差恢复用两场之差或F(e)-F(0)，不能默认recover(e)再加内部特解。复数loss涉及共轭，不得对它套用要求全纯的complex-step公式。

### A1准入：验证向量导数，而不是只比较两个loss相减

先做小型复数、非Hermitian、非零端口、非最优head和同时变hidden/head的独立测试，阈值operation-relative1e-10。真实原点复用V12的seed421201、421202单位方向及归一化原解析梯度方向；重算梯度须与同一参数绑定。梯度近零用seed421203，不能用零方向充数。

每个方向依次核对：手推前向与原network trace重建≤1e-10；独立切向对原边／面矩的线性传递；完整端口切向恒等式≤1e-10；两组固定随机复dual（seed421301/421302）和真实loss dual的JVP/VJP配对。配对检查以下实内积，分母用两边可计算运算尺度的较大者，不用抵消后接近零的结果作唯一分母。

```math
\operatorname{Re}(q^H\dot t)
=\left\langle\operatorname{VJP}(q),\,(d,\dot\gamma_R,\dot\gamma_I)\right\rangle_{\mathbb R}.
```

配对分母明确为max(norm(q)*norm(dot t), norm(VJP(q))*norm(实参数切向), tiny)。配对operation-relative≤1e-9，并报告未归一化差、结果相对差和相消比例；真实dual必须包含bar S共轭转置及Hhat链。随机配对通过不能覆盖真实dual失败。明确错误先修，最多两次全批针对性修复，不重跑历史。相消导致标量符号不确定时标DIRECTIONAL_SCALAR_UNCERTAIN，不伪称该方向可靠下降。

向量中心差分比较dot t，不要求旧标量loss FD先过。每方向最多6对扰动：先用h=1e-4、1e-5、1e-6、1e-7中的最多4对；没有稳定区时，再由观测到的向量截断/相消和dot t尺度预登记相邻两点，不扫无限h。相邻两点的向量相对差均≤1e-5、相互差趋势一致，且参数和trace差实际可分辨，授予TANGENT_VECTOR_VERIFIED。保存t+/t-的范数、差、Taylor余项、loss+/loss-和实际参数步，不能只保存斜率。

A1通过不改V12标量FD的旧FAIL，也不授予精确VarPro资格。手推链和向量FD仍不能共同核验的方向不进入B/C；其余合格方向可继续。不可因“max error很小”省略量纲、分母和非零见证。

## 5. 函数值分辨率与统一接受规则

起点及任何拟接受试探，用同一数学函数的batch8重复、batch1和原完整S直接审核，核对参数、head和端口。记录loss差及残差向量差。以残差差delta_r估计对应的loss差尺度：

```math
\delta_J=\max\left(
100\epsilon_{64}\max(1,J),\;\text{observed loss differences},\;
\frac{\lVert r\rVert_2\lVert\delta_r\rVert_2+\tfrac12\lVert\delta_r\rVert_2^2}{\lVert b\rVert_2^2}
\right).
```

这是观测分辨率与保守地板，不是严格全部浮点误差界；不将Pgamma、Zc不同向量的loss冒充相同目标重复求值。起点delta_J不能无条件代替扰动点delta_J。明显失去重复性、原作用身份失败或非有限时停止受影响路径。

对实际更新p及可信切向v，模型预测下降pred=(Re(rᴴv)-0.5 norm(v)^2)/norm(b)^2；步长缩放时v也同比缩放。先要求pred>max(1e-12,100 delta_J)。小于此限标PREDICTED_GAIN_UNRESOLVED，不继续无限缩步来追逐接受数。

拟接受点必须满足：实际下降ared>max(1e-12,20 max(delta_J_old,delta_J_trial))；ared/pred≥0.1；重新前向确认；原恢复≤1e-10、identity≤1e-10、slave-zero、全部端口原审核≤1e-6；native≤起点的1.05倍。预测/实际比仅是局部模型质量，不是全局收敛证明。保存Taylor残差差；正增益若只来自计算不可分辨变化不得接受。

完整方程仍可未合格，以上只是接受一个研究步的条件。不得在接受时按参考场选点、校相位或改归一化。拒绝或异常要恢复psi/gamma/alpha/z及状态hash，消耗不回滚。

## 6. 路径B：一次按原作用选步长的固定head对照

它不是再扫学习率，而是量化当前方向的最优线性步及可能下降。对合格单位hidden方向d，计算v=bar S J_psi d及下式；s为正代表沿d下降，必要时同时翻转d和v。

```math
s=\frac{\operatorname{Re}(v^Hr)}{\lVert b\rVert_2^2},\quad
c=\frac{\lVert v\rVert_2^2}{\lVert b\rVert_2^2},\quad
\alpha_{lin}=\frac{s}{c},\quad
\Delta J_{lin}=\frac{s^2}{2c}.
```

报告s与反向梯度给出的负方向导数之差，以及点积逐项绝对值和。符号需至少大于20倍观测导数差与100 epsilon点积绝对和构成的尺度，否则不把alpha当可信下降建议。c=0、不可分辨参数步或非有限均单独记录。

初始试探alpha=min(alpha_lin, 1e-4 max(1,norm(psi)), 0.1 norm(r)/norm(v))；这些是单位d的上界，不代替模型计算。按截断后pred选至多一个最有希望方向，最多alpha、alpha/4、alpha/16、alpha/64四次实际试探、1个接受点；gamma固定，端口每次重算。没有可分辨pred时跳过试探，直接C。

需输出每方向的s、c、alpha_lin、pred及uncertainty，即使全无可用更新，也能说明为何不值得继续缩步。只否定这些测过的方向／固定头设置，不宣布所有隐藏方向都无效。

## 7. 路径C：少量隐藏方向加输出头补偿

### 7.1 为什么不同于固定头，以及付出什么代价

改变隐藏函数时，让输出系数同步补偿，以免只破坏原来大系数间的抵消。它只构造至多3个联合切向，不建立8576列Jacobian，也不求全局p4逆。代价是当前hidden下的薄P/Z/R/A、少量薄最小二乘与JVP；最终候选必须仍由真实network生成。它不是“精确VarPro梯度已经通过”，也不是对所有变量做完整Gauss–Newton。

首次C从与B相同的V12原点开始。P=ZR、A=bar S Z沿用V11稳定坐标：同hidden可以复用保存的P/A，重建QR后以至少三列原作用核验；hidden改变后必须重建该点P/A，禁止继续用旧缓存。QR重建和原作用配对≤1e-10，H安全、P/A按既有cond1e-12完整数值秩1560才进入依赖的补偿。只做三角solve，不显式构造R逆；不形成SᴴS/WᴴW、不扫rank或正则。

### 7.2 先生成补偿方向，再用实际联合JVP修正局部模型

D由当前至多3个合格hidden方向构成，T=J_psi D。对每一列v_j=bar S T_j，解一个输出头作用的薄最小二乘：

```math
k_j=\arg\min_k\lVert v_j-Ak\rVert_2,\qquad
R\,\dot\gamma_j=-k_j,\qquad
\dot t_j^{joint}=J_\psi d_j+P\dot\gamma_j.
```

所有系数来自原算子，不读参考。可一次3-RHS GELSD或复用已核验经济QR，阈值沿用固定1e-12。未达到旧1e-8驻点不阻止将结果作为有限方向建议，但必须报告实际LS残差、秩、输出补偿范数，不能称精确消元或精确VarPro。

**核心限制：不能仅用v_j-Ak_j这个相减后的数作为最终模型列。** 独立逐层切向同时输入hidden方向d_j和head方向dot gamma_j，经过原矩映射得到实际dot t_joint，再用原bar S计算v_joint。报告与投影表达式的向量差及抵消；后续用实际v_joint，不能用更好看的投影值。

联合切向须与J_psi d+P dot gamma在运算尺度上≤1e-9，并核对包含head实虚通道的VJP实内积。对联合扰动做向量Taylor配对；因抵消无法分辨的模型列不得靠小分母伪称通过。补偿不准确可以是方向选择问题，但确定的符号／排列／导数实现错误必须修正后才能试探。

### 7.3 至多三实变量的局部最小二乘与有限步长

令V_joint包含实际联合列，只求实系数a，因为hidden参数是实数：

```math
\min_{a\in\mathbb R^k}
\left\lVert
\begin{bmatrix}\operatorname{Re}V_{joint}\\\operatorname{Im}V_{joint}\end{bmatrix}a
-\begin{bmatrix}\operatorname{Re}r\\\operatorname{Im}r\end{bmatrix}
\right\rVert_2^2,\qquad
\Delta\psi=Da,\quad\Delta\gamma=\dot\Gamma a,\quad k\le3.
```

小问题用QR/SVD，不做正规方程。确定性单位列坐标均衡允许，但须准确反映射；小问题cond1e-12截断列时逐项报告，不外推全系统秩。不得让复a更新实hidden，不把补偿系数当新独立物理未知量。

先将联合步乘共同tau，满足norm(Delta psi)≤1e-4 max(1,norm(psi))、norm(Delta gamma)≤0.1 max(1,norm(gamma))，tau≤1；随后最多tau/4^j、j=0..5六次实际试探。真实候选是t_N(psi+tau Delta psi, gamma+tau Delta gamma)，不是t_old+tau dot t。端口用新trace闭合，内部特解不缩放。实际与线性模型二阶差必须记录，接受沿§5。

初次C无需先有物理正信号。接受第1个联合步后，只有该步J相对下降≥1e-4且native未恶化超过5%，才允许第2步；第3步还需累计J下降≥1%。最多3个接受联合步，任轮6次均拒绝则结束C，不无限加方向或缩半径。后续原点重算JVP与实际参数身份，并对拟用联合变化补一组两尺度向量Taylor复核；复用已通过的模块资格，不重跑初始全部差分表。不沿用旧模型梯度或已经失配的P/A。

每个接受联合步另算一个**同gamma更新、hidden不变**的head-only twin并保存，作为贡献对照，不用它warm start或取代联合路径。若全部收益都可由head-only达到，不称隐藏学习增量；成本也必须包括补偿设置。B、C和这些twins在同一参考进程中比较。

## 8. 失败分流、验收与停止取舍

真实算子／端口／导数链错误先做针对性定位和最多两次全批最小修复，所有失败保留。A1可信但B不可用应继续C；C数据缺失不抹掉B；没有可用切向、头补偿接口不安全或步长不可分辨时完成原因表再D，不强制产生接受状态。

D在全部求解冻结后，一次FE环境验证原点、B接受点、最多3个C点及其3个twins（至多8个，重复去重）。复用REF7，不重新LU／p4 enrichment。原严格门限保持：Schur/native/原增广及全部规定端口残差≤1e-6；恢复≤1e-10、slave-zero；total/scattered E/H、scaled-curl、selected复场及完整复通道≤1e-4；R/T/A/A_volume绝对差≤1e-5、每通道功率差≤1e-6、能量闭合≤1e-5；原近零规则不改。未资格化功率只能diagnostic。

研究正信号：rho=max(原Schur,native,固定RHS端口)较原点至少减半，散射E与scaled-curl各≤0.5且较原点各改善≥25%；这仍非严格pass。只有loss下降标OBJECTIVE_ONLY_IMPROVEMENT；有hidden变化但无实质收益标BOUNDED_COUPLED_STEP_NEGATIVE；纯derivative/数值/资源停止分别标注。不能把核验PASS覆盖为solver PASS。

如果可信方向及补偿均无进展，本次应收口“大系数头下这组有限方向的固定／联合局部更新”，不自动再开同配置诊断循环；报告唯一有证据支持的表示或求解器调整建议。任何micro正信号都不自动外推2 TB目标规模或48小时，不扩大几何、阶次、MPI、通道或波长，不复活旧p4路线。

## 9. 时间、内存和共享工作站

从Codex接手登记新UTC、Asia/Singapore与单调时钟start，**全批elapsed最多14400 s，含实现、测试、计算和交付；start+13500 s停止重负载，末900 s收尾**。复用独立deadline与整树watchdog，覆盖BLAS/JIT/ML/FE子进程；原时钟不因修复、上下文或阶段刷新。旧累计有载下界11916.413697 s保留，辅助未知仍未知，本批费用与总elapsed分账。

同时生效上限：全批完整前向≤400；JVP等效单方向≤48；VJP≤24；向量FD扰动≤60；完整P/A构建≤3（含缺失初始重建）；薄LS分解≤6，RHS列总数≤18；小实LS≤3；原S/Sᴴ等效单向量作用合计≤8000；原audit≤60；B≤4试探/1接受；C每轮≤6试探/最多3接受。不按矩阵批处理隐藏列作用成本，不要求跑满。A1诊断数值部分最多1800 s，缺可信导数则转有界定位和D。

继续Task042既有受控共享CPU授权，其他heavy存在不自动阻塞；现场选空闲物理核，MPI1、数学/Torch线程1、DataLoader0、GPU不使用。整树hard16 GiB/warn12 GiB，事前常驻规划≤8 GiB，own swap0；系统及邻任务增长余量、自有锁、独立环境/缓存保持。只降低自身nice/I/O并监督停止自身后代，不改邻任务、其锁/环境/亲和性/watchdog，不升级ABI/BLAS/CUDA/系统配置。无cgroup委派时如实标采样监督，不称连续内核限额。

P/Z/A及分解workspace按实测生命周期记账，至多一套完整基分解常驻；方向仅3列。旧大数组不复制入Git；新失败点保存参数、标量与必要诊断数组，避免每个trial存一套P/A。不得为了找工具安装重型库；缺pytest/Ruff如实区分，通过已存在解释器的小断言测试不能冒称pytest通过。

## 10. 实现、正式入口与交付

数值核心进入可复用src/solvers，薄runner复用原action、矩、端口、验证与watchdog；不继续复制近千行runner。保持普通默认、原Maxwell/Floquet/DtN及旧方法不变；新JVP与联合局部模型显式opt-in。合成测试必须覆盖实hidden/复head、齐次切向端口、非最优头、补偿正负号、真实非线性更新与线性预测不等、拒绝回滚和错误reference访问。

先提交clean实现再正式运行。拟新增入口在本report提交时尚未实现：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v13_tangent_check.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v13_response_step.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v13_head_compensation.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v13_verify.dat
```

一个dat对应一个明确stage，内部最多3个原点是冻结算法的迭代，不是隐藏几何扫描。某stage依赖失败时保存not_run原因而非盲目执行；B数值负结果不能自动取消独立C。前置Gate通过即继续授权队列，无须逐小步再向用户确认。

每正式run保存input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json、环境/MPI/线程/资源及artifact hash。source必须为真实运行SHA，文档HEAD不能替代。状态必须含psi/gamma/alpha/z、方向库存、JVP来源、当前rank、真实r/J、delta_J、pred/ared/ratio、实际参数变化、接受／拒绝及停止原因。

最少交付response_v13.md、outcomes/tangent_scale_head_compensation_v13.md，以及紧凑的plan_and_input_identity_v13.json、tangent_identity_checks_v13.json、directional_scale_v13.csv、coupled_step_history_v13.jsonl、candidate_comparison_v13.csv、qualification_and_dispatch_v13.json、resource_costs_v13.json、run_index_v13.json。独立checker从原字段重算，必须拒绝复系数更新实hidden、错符号、旧head被清零、linear-only伪候选、无真实下降却接受及缺通道等反例。

同步本Task README最新入口、summary/test_summary/changed_files、docs/development_progress.md及development_model_registry.md。原task、Review V1–V9、Response V1–V12和旧raw不覆盖。Markdown按仓库fenced math和表列规则，实际GitHub页面核验与本地源码检查分开；不可取时标未核验，不伪称通过，也不因此取消已授权数值工作。

只推送git push origin HEAD:refs/heads/task42_neural_coarse_inverse；不amend、force、merge/rebase或改其他worktree。阶段提交时不能改变活跃run受检HEAD。完成／安全停止／预算截止后报告精确HEAD、upstream/worktree、实际source、切向资格、固定及联合接受数、head-only对照、完整物理资格、资源与唯一下一建议，清场后停止等待review。

## 11. 方法来源与范围

前向JVP概念与接口可参见PyTorch官方torch.func.jvp文档；本批指定独立逐层递推，不依赖安装新版本。非线性最小二乘中使用残差Jacobian作用及实际／预测下降的思路可参见SciPy官方least_squares文档；本批只实现至多三方向的明确局部模型，不继承其整套TRF/LSMR或默认正则化。标量有限差分同时受截断与相消影响，参考SciPy官方differentiate.derivative说明。查阅版本不等于本机运行版本，实际环境照原manifest。

```text
https://docs.pytorch.org/docs/2.7/generated/torch.func.jvp.html
https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html
https://docs.scipy.org/doc/scipy/reference/generated/scipy.differentiate.derivative.html
```

本文的端口切向、一步残差模型、补偿式与实系数小最小二乘由原方程直接推导。它们没有证明当前NN会收敛；本批要取得的是可复现的实际下降或可解释的有界负结果，而不是又一个与物理解脱节的接口PASS。
