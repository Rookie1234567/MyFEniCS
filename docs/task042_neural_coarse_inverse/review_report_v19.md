# Review V19：V21审查与p1来源迹空间的Galerkin两层校正

## 0. 决定、快照与消除的blocker

**接受V21的精确class作用优化和已保存的原方程/物理证据；不授予完整求解或神经加速资格。B额外读取旧方向的合同失败保留。下一批不继续ILU排序或循环容量扫描，检验一个明确的p1来源粗空间：用真实p1→p3有限元插值确定trace方向，但粗矩阵从原p3凝聚算子投影构造；保留全部细层校正。数值资格通过后同时做暖起点对照和一个独立的零trace短试验，不把暖尾部必须先成功设为零起点的前提。**

当前blocker：C-FINAL的Schur残差仍为2.5281170328e-6、最大逐通道功率差仍为1.7196446511e-6。新试验检查与低阶有限元场相关的耦合方向能否更有效处理剩余误差，不假定它们已被证明是唯一难方向。最终目标仍为约2 TB整机内存内、48小时内求得新的0.7 nm非可分三维周期单胞有限元解；本批只针对384-cell micro。

```text
repository              = Rookie1234567/MyFEniCS
execution_branch        = task42_neural_coarse_inverse
worktree                = /home/fenics/Projects/NN-Lab
review_date             = 2026-10-02
reviewed_HEAD           = 54d249022429366dfb1028199a1d83cd599b6b28
reviewed_commit_UTC     = 2026-10-02T02:33:34Z
reviewed_commit_Singapore = 2026-10-02T10:33:34+08:00
original_base_SHA       = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review         = review_report_v18.md
previous_review_commit  = 4803449986d64723b5fa353e1bd0a53f1dc5a918
latest_response         = response_v21.md
V21_run_sources         = 97a17aee9a9cc2d91904b4c89f07c4d1cfbd631c,
                          c91954c47d55242fd95ae7efcb44272dcce3a0ec,
                          d7bfcb58632b344f8ed9b9fd1467c6c224df0bc4
next_batch              = V22_P1_TRACE_GALERKIN_CORRECTION
response_required       = response_v22.md
decision                = ACCEPT_EVIDENCE_WITH_LIMITATIONS_CONTINUE_RESEARCH
old_p4_inverse_route    = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate     = NOT_QUALIFIED
master_merge            = NOT_APPROVED
```

ChatGPT审查远程合同、回应、紧凑原始记录及相关源码，没有SSH运行工作站、读取全部ignored数组或实测当前资源。历史数值为measured/recorded，公式和容量为derived，下面数值工作为planned/not_run。研究设计已使用历史参考审核信息，不称全新blind test；本批求解仍禁止读取REF7数组。

## 1. V21审阅：工程收益、数值收益和合同缺口分开

依据：[Response V21](response_v21.md)、[候选CSV](outcomes/records/candidate_comparison_v21.csv)、[作用配对](outcomes/records/action_equivalence_v21.json)、[计时](outcomes/records/paired_kernel_cost_v21.json)、[读取边界](outcomes/records/data_loading_boundary_v21.json)、[截止记录](outcomes/records/deadline_stop_v21.json)。

| 同一0.7nm/p3/40端口；无量纲measured | 暖原点 | B-FINAL | C-FINAL |
|---|---:|---:|---:|
| Schur；限1e-6 | 9.678334710e-6 | 7.730686064e-6 | 2.528117033e-6 |
| native；限1e-6 | 3.753294800e-6 | 2.997989290e-6 | 9.804133464e-7 |
| 独立total-native；限1e-6 | 1.302390987e-6 | 1.040300438e-6 | 3.402028311e-7 |
| 散射E；限1e-4 | 7.950032150e-5 | 7.942374001e-5 | 7.816080389e-5 |
| 最大逐级功率差；限1e-6 | 1.785534642e-6 | 1.888746638e-6 | 1.719644651e-6 |
| 完整边界调用/计费秒 | 历史 | 16 / 393.74354 | 112 / 2939.28866 |

C的native单项通过，不替代Schur；5个冻结状态均未完整通过。C在更多工作量下比原点降低残差约3.83倍，场误差仅改善约1.68%。共同16调用时C的rho约8.2517e-6，高于B约7.7307e-6；不能因最终C更低就宣布同成本加速。C实际停止为TIME_VERIFY_RESERVE_STOP；最后16调用降幅约3.06%只是事后统计，不改写当时停止原因。

class64新/旧作用最大运算尺度差7.02255e-14，暖点残差差/b最大1.40451e-13；完整L调用旧44.53653秒、新23.47187秒，下降47.2975%。完整调用每backend只有一次，不称多次统计稳健估计；kernel另有成对微基准。接受EXACT_ACTION_ENGINEERING_GAIN，但普通默认及独立旧oracle不改变，算子快不等于方程收敛。

B曾额外解压旧x/outer_directions，虽未用于初值/循环空间，仍保留FAIL_RETAINED。新reader已收窄；本批复用并补角色级反例，不重跑V21、不将历史B改成合规。C的实际空CU/零校正路径及已保存向量仍可分析。新暖reader只解压trace/port/z/residual；读取文件/数组元数据不等于允许解压其他成员。

V21正式监督wall3482.12566257秒，辅助61.5086217693秒；采样同时树峰870723584 B、own swap/VRAM0；formal历史下界70970.5997846秒。此为研发累计，不是单个成功模型耗时。截止记录仅证明交付准备时刻在窗口内；不能用准备时刻代替最终push/回复时刻。旧V20超时结论保留。

## 2. 为什么不是简单执行一个“p1物理粗逆”

[Task39extra历史](../task039_extra_physical_multilevel/outcomes/summary.md)已经保存粗细耦合失衡、递归粗逆失败及需精确区分凝聚/传递的教训；[H(curl)基础设施](../../src/solvers/hcurl_multilevel.py)明确只资格化映射/传递/Galerkin等基础组件，不提供成功的通用p多重网格。不得继承其失败solver为生产PC。

本批对Response的建议作明确收窄：不把独立p1重新离散矩阵冒充p3凝聚后的粗矩阵。取真实p1函数在p3空间中的插值，再只取其独立trace，定义稀疏满列秩映射T。端口先按原p3方程精确消去，记A=barS，粗矩阵定义为：

```math
A_c=T^H A T.
```

这叫**P1_TRACE_GALERKIN**，不是独立物理p1 Maxwell解，也不是已证明的p1/p3完整V-cycle。p3内部的齐次恢复通常不同于直接插值的p1内部场，所以不能假定它等于先做完整p1 Galerkin再凝聚的结果。禁止分别凝聚curl和mass后相减。传递源确实是Nédélec p1，不是把旧3098列神经库换名字。

它可能提供更符合有限元耦合的修正方向；也可能因为p1方向不足或粗细耦合困难而无效。它增加一个有硬容量上限的全局粗LU，必须登记GLOBAL_BOUNDED_TRACE_GALERKIN_FACTOR_PRESENT；不是factor-free。粗维数随网格增长，本批的<=2048上限禁止原样无界扩展，不能据micro成功宣称2 TB目标规模可行。

## 3. 冻结物理、数据与读取权限

先核对branch/HEAD/worktree/upstream、根/目录AGENTS、仓库原则、原task、全部补充合同和最新review/response/summary。本报告只覆盖本批新增p1来源粗空间/PC及条件队列；旧p4强逆、ILU参数扫描、网络训练和其他任务仍关闭。不得修改旧task/review/response/raw或master。

| 冻结项 | 身份 |
|---|---|
| fine问题 | 原Full3D complex128，0.7nm，1度/azimuth0/s，三维缺口，原背景/RHS，双Floquet/Fourier-DtN |
| fine离散 | 384hex/p3/h0.175nm/q15；full34050、trace18144、interior13824、slave2082；端口20+20，z18184 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1；ready，不再索要或联网替换 |
| Si | n=0.999885140474+4.32477054e-6i；epsilon=n*n；source0.699999988明确alias nominal0.7 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA256 | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| modes SHA256 | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action NPZ SHA256 | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 NPZ SHA256 | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |
| 新暖原点 | V21 C-FINAL，NPZ 680f58e5e58704fc69f0b539c8c411131ce697b7811445eb9643bbf92a736072 |

从V21 checkpoint/run index核对实际路径、文件hash及成员数组hash，不猜目录。此处文件hash不是z数组hash。暖原点只读4个许可数组，不能自动加载x/CU/旧网络/参考；冷进程禁止解压任何暖状态。V22的artifact/窗口/ledger独立，不能重开旧FROZEN或重置旧配额。

## 4. S：真实p1来源映射与小粗矩阵

### 4.1 先证明映射，不能用自由度序号补零

在原同一个六面体mesh上建立与fine同族/映射约定的Nédélec p1及其双Floquet约束。复用既有经验证的同mesh插值/owner处理，或使用现场Basix的[compute_interpolation_operator](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.interpolation.html)；它要求正确处理DOF transformations，不能只乘参考单元矩阵而忽略方向。禁止升级环境。

先构建/验证完整p1→p3函数插值，再提取p3 canonical master trace行。共享实体只保留一份一致定义，不将重复owner插值相加；周期slave按各自MPC展开检验，不将slave-zero存储当物理场值。对两个固定随机复p1系数及单边见证验证实体矩、场值、curl与独立DOLFINx插值，运算尺度差<=1e-10；复对偶配对同限。必须覆盖非平凡Floquet相位、非identity方向变换、共享边/面和全部高阶矩。

设未归一化映射为T0。仅按非零列欧氏范数作固定列归一化T=T0*diag(1/norm(T0_j))，记录该变换，不截断列或微小项。不要求T正交；用T^H T核对独立列/数值秩，不把不同高阶矩或实体混成节点值。完整p1独立DOF数n1现场实测；n1>2048或秩/映射不安全时只阻塞PC路径，不删粗DOF凑容量。

### 4.2 从原p3局部凝聚块组装，不形成全局fine矩阵

原块符号保持S=[[K,C],[F,H]]，H是40维Hhat，不是Hp，F不假定等于C^H。E_e是packet的原trace展开。构造：

```math
K_c=\sum_e(E_eT)^H S_e(E_eT),\quad C_c=T^H C,\quad F_c=FT,
\qquad A_c=K_c-C_cH^{-1}F_c.
```

局部支撑稀疏累加，合并重复贡献但不丢Floquet相位；只允许物化n1阶粗矩阵，不形成全局K、barS、P^H A_full P或正规方程。C/F使用已核对的原端口提取/注入。另用原barS对8个固定粗见证核验A_c w=T^H A(Tw)，运算尺度差<=1e-10；包含当前暖残差的粗限制和非零端口小模型。

coarse LU使用现有complex128 SciPy/LAPACK部分选主元，不加shift、ILU、drop或排序扫描。矩阵及LU显式总载荷<=256MiB，n1<=2048，T稀疏载荷<=128MiB，新增同时workspace规划<=1GiB。实际matrix/factor/index/workspace/RSS分别报告，不能将数组字节称因子RSS。按LU的gecon估计cond1并记录为估计，要求rcond1>=1e-12；不是完整fine条件数。

粗解采用固定的一次残差精化：LU解u0后再解A_c du=s-A_c u0，返回u0+du；所有PC调用都同样执行，不依RHS改次数。对8个见证要求norm(s-A_c u)/norm(s)<=1e-8及运算尺度缺陷<=1e-12，零RHS返回零。失败隔离此固定粗解，不靠不断精化或换p2救场。该粗解资格不要求单次PC解出fine系统。

## 5. P：全空间右预条件，不使用低秩粗逆作为唯一搜索空间

令Q r=T solve(A_c,T^H r)，不显式形成Q。固定尺度tau=sqrt(n1)/norm(A_c,F)，只从上述列归一化后的粗矩阵得到，需正有限；它只是一个固定的算子尺度，不是最优步长或fine谱估计，不做参数对照。定义：

```math
B r=Q r+\tau(I-QA)r
    =\tau r+Q(r-\tau A r).
```

每次B需要一次fine A作用、一次粗解及稀疏T/T^H，不内嵌迭代。**tau r保留完整fine方向，粗校正不是最终解的表示限制。** 在精确算术、T满列秩且A_c可逆时T^H A B=T^H；若Bx=0，则T^Hx=0且x属于range(T)，因T^HT可逆可得x=0。因此这一定义不会像单独Q那样因低秩永久限制搜索空间；这不是收敛率保证。

用一般复非Hermitian小矩阵（非互伴端口C/F）验证上述恒等式、B满秩、原端口闭合、非零fine补空间解、右侧组合和恢复。真实PC检验复线性/重复性、finite及T^H(r-AQr)运算尺度缺陷<=1e-8，不能把norm(r-A B r)要求为1e-10。原独立ActionPacket.audit不变，不允许新PC或新action自己证明自己。

外层复用已资格化GMRES256返回后事务。每周期原r=barb-A t，解：

```math
(A B)y=r,\qquad y_0=0,\qquad t_{new}=t+B y.
```

用LinearOperator(y -> A(B(y)))且SciPy GMRES的M=None，明确是右预条件；不把B放入SciPy M后仍这样命名（该接口M为左预条件，见[官方文档](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.gmres.html)）。restart256/maxiter1/callback_type=pr_norm、tol/rtol0、atol=1e-8*norm(原完整b)。每个B中的fine作用与外层fine作用都计费，不能只记外层matvec。

返回先保存y/By/实际trace，再由bar.close返回完整z并切出40port，再旧oracle审核/commit。内部恢复含原特解；误差恢复去特解。不得重复加base、把y当trace、把Hhat当Hp或从校正rhs重新定义归一化。原方程门限仍1e-6。

## 6. 有限队列：暖尾部与冷起点分开检验

| 阶段 | 行为 | 上限及继续条件 |
|---|---|---|
| D0 | 角色白名单reader、时钟、schema/预算/事务小回归；核对暖原点 | 不重跑V21，<=600秒辅助 |
| S | 真p1映射、Ac构造/LU、原作用及PC资格 | 总设置/资格<=1800秒；一次T/Ac构造，最多4个独立进程同Ac数值LU |
| N | 同一C-FINAL，无PC GMRES256 | <=4周期/600秒；PC受阻仍可做N |
| P | 同一C-FINAL，固定B，独立于N | 首4周期，原rho降>=10%才每4周期继续；最多16周期/1800秒 |
| Z | 新进程从零trace，用同一固定B | S通过即允许首4周期，不要求P先成功；之后每4周期rho降>=20%继续，最多32周期/2400秒 |
| T | 另一历史L-GNN暖起点，同B | 仅P原方程通过或rho降>=5倍才准入；首4后10%规则，最多8周期/900秒；可晚于Z |
| V | 全队列冻结后的同离散场/通道/功率审核 | 一次FE环境，<=12个去重状态/600秒 |

所有子上限受总截止及全局作用数约束，不相加获得额外时间。N/P/Z允许共用已验证的T/Ac数据，但冷进程只读物理、mapping/coarse和原packet，不读任何暖解、网络/Q库或循环向量。Z名称为ZERO_TRACE_FROM_FROZEN_OPERATOR，不是从几何开始的端到端fresh run；端口与内部特解不强行置零。短冷试验用于区分暖尾部缺少粗分量与总体求解能力，不能由4周期未通过推断永久失败。

每周期用旧oracle保存完整原残差/恢复/端口审核，FIRST_EQUATION_PASS不可覆盖；同路线额度内最多再2周期追求可选rho<=1e-8。数值非有限或原作用/身份失败立即隔离；原rho连续两次显著上升时重审该点一次，仍真实则停止该路线。失败不取消独立合格阶段，不延长m、p1维数、coarse精化次数或尝试另一PC。

P/Z只有原方程门限不代表完整物理通过；小方程精确也不代表离散收敛。若本批无实质收益，冻结此配置负结果，不自动转ILU或又开一批同配置长循环。

## 7. 独立验证、失败定位与神经贡献

全部求解/选点/hash冻结且actor退出后，独立FE环境才读REF7。固定验证历史C-FINAL、N/P/Z/T末态、各自FIRST_PASS及至多两个预登记中间点，去重<=12；不得按参考挑最好点。p1映射/Ac、方向、尺度、停止与参数均不得使用参考数组或旧参考拟合结果。验证开始后不回训。

原Schur/native/增广及规定port<=1e-6；恢复/identity<=1e-10、slave-zero；total/scattered E/H/curl、selected复场、40复振幅<=1e-4；R/T/A/A_volume绝对差<=1e-5、单通道功率差<=1e-6、能量<=1e-5。native与独立total-native分开；所有数值按未舍入值判断。功率由已批准原函数计算，legacy缺数组可从已保存复振幅重算并明确derived，不重新FE求解。

若PC未有效改善，最多对暖起点的一个真实误差作离线诊断：用T的Gram小解求trace欧氏投影、分别恢复其齐次fine场及补空间场，报告相应L2/curl和原A作用、交叉项。此投影只说明此误差在当前trace度量中的表示，不是物理L2最佳投影、条件数或全解空间极限；不能拿投影权重/误差回填任何候选。该诊断<=120秒，零新reference LU/全局谱。

本批没有神经训练。暖起点保留V14–V19辅助基/迭代的必要成本；新p1来源映射不是神经库。Z若完整通过，说明此micro不需要旧神经暖起点，不自动否定跨几何神经方法。最多授予WARM或ZERO_TRACE_MICRO_DISCRETE_PASS_ONLY，目标规模、p/h、MPI可扩展性与48小时仍未资格化。不能把新增coarse factor隐去后声称factor-free生产方案。

## 8. 时间、安全、修复和资源账

接手时从实时UTC/monotonic/boot_id冻结14400秒总窗口，12600秒停重负载，最后1800秒交付；实现、测试、修复、冷却、构造、求解、审核、报告都计入。每次上下文恢复/新stage/提交/交付前重读真实钟与ledger，不依摘要剩余时间，不刷新旧窗口。队列结束即生成最小response/费用包；总截止后仅必要清场/保存/交付，实际延迟如实记录，不能扣除未知间隔。

全批原/新S及SH合计<=40000，B应用<=20000，粗三角解（含固定精化）<=41000，原audit<=160；真实预检作用<=512、验证状态<=12、新artifact<=2GiB。T/Ac原始构造各1次；缺已保存结果不可用全局单位向量法重造fine矩阵。B内部、作用配对、失败、拒绝、返回后恢复与基构造均计费；每个256周期按<=600个fine作用保守预留，结束按实际结算，kill保留上下界。

保持受控共享CPU授权：其他heavy存在不自动阻塞，但实际资源Gate必须满足。实时空闲物理核、避开忙SMT、MPI1、数学/Torch1、Loader0、GPU不用；规划同时RSS<=8GiB、warn12/hard16GiB、自身swap0；系统max(128GiB,effective_total的10%)、邻增长128GiB和自身16GiB余量、磁盘free>=50GiB。0.5秒整树监督及原PSI full avg10>=0.1连续三次5秒保护不改变；无cgroup不得声称kernel连续硬限额。不能修改邻任务、系统ABI/BLAS/CUDA/swap或其锁/亲和性/watchdog。

压力停止后仅清理自身，最少冷却120秒、最多观察600秒，full avg10<0.05持续60秒并过其余Gate才重入；最多两次、累计等待<=1200秒，仍计总截止。数值失败不能通过重入或换方法绕过。

计划内实现不占意外根因数但计时；最多4个已定位意外根因最小修复，每次<=900秒、累计<=2400秒、同根因最多2次。映射/API/shape/计数可修，低阶空间无效、零主元或不收敛不是bug。无需逐小阶段等用户确认；公共数值/身份/监督缺口先修，非关键格式留安全收尾。不能为了跑满4小时重复失败。

## 9. 代码、正式入口与交付

复用原class64/旧oracle、原端口/恢复、右侧GMRES事务及V21窄reader；H(curl)基础设施只复用有证据的映射/验证接口，不整包导入旧失败PC。新数值核心进入src/solvers；配置差异进schema/dat，不能每个stage复制大型runner。旧ordinary default及原audit不变，不加载全局p3 ILU/K、旧3098列库或p4因子。新coarse矩阵是唯一授权的新增全局直接分解对象，参数显式opt-in。

先完成focused复数小测试、实际mapping/PC接线、reader mutation和期限模拟，提交clean源码，再validate及按条件运行以下待实现入口：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v22_p1_trace_setup.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v22_control_warm.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v22_p1_coarse_warm.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v22_p1_coarse_zero.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v22_p1_coarse_transfer.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v22_verify.dat
```

这些入口在review发布时尚未实现，不提前声称可运行；每slice是明确one-run dat与同一预算。绑定input_original/resolved/manifest/input/physical/material/modes/action/backend/T/Ac/LU policy/parent/state的hash及实际source、ABI/MPI/线程/run_summary/RSS；本review提交SHA不冒充数值source。

C1：窄reader/映射及小测试；C2：固定粗层/右PC与正式入口；C3：冻结数值和独立审核；C4：response及轻量reader证据/模型账。活跃run期间不改变其受检HEAD。大T/Ac/因子/向量仅ignored；Git提交紧凑records，不复制整套嵌套原JSON。

交付response_v22.md、outcomes/p1_trace_galerkin_correction_v22.md；records至少含source_inventory、transfer_checks、coarse_identity_capacity、coarse_lu、right_pc_checks、cycle_history、candidate_comparison、field_channels、lineage/cold_access、checkpoint/run_index、time/resource/repair及not_run。同步README最新导航、summary/tests/changed_files、development_progress和development_model_registry，保留旧历史。

Markdown使用fenced math和列数一致表格，核查精确GitHub页；未取得视觉证据如实NOT_VERIFIED，不将源码检查等同渲染通过。只推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。结束清场，报告完整HEAD/upstream/worktree、实际source、粗层的准确名称/容量/因子存在、暖冷原方程与物理资格、全部成本及唯一下一建议，停止等待review，不merge。
