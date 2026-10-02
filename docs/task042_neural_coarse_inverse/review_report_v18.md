# Review V18：V20负结果收口、精确作用批量化与有界循环空间校正

## 0. 审阅决定、快照和本轮障碍

**接受V20已保存的固定ILU(0)负结果和独立物理验算；不批准完整求解、神经加速、合并或总时限合规。暂不执行Response V20建议的另一种ILU排序。下一批将两件事分开：在不改变原方程的前提下，减少每次原算子的重复张量展开；再比较一个固定容量的GCROT循环空间校正与短LGMRES对照。不是把优化算子实现当成收敛保证，也不是继续无界增加迭代次数。**

本批消除的障碍是：当前原Schur残差仍约1e-5，逐级功率未通过；自然排序ILU及40端口修正均未有效解决，而现有无矩阵作用存在明确的重复分配候选。目标是在可审核成本下检验新的残差修正空间，并保留原独立验算。最终目标仍为约2 TB整机内存内、48小时内完成新的0.7 nm非可分三维周期单胞有限元解；本批仍是micro研究，不是目标规模资格。

```text
repository              = Rookie1234567/MyFEniCS
execution_branch        = task42_neural_coarse_inverse
worktree                = /home/fenics/Projects/NN-Lab
review_date             = 2026-10-02
reviewed_HEAD           = 4636c601bc94809cdea3adc36af178a82d80599d
reviewed_commit_UTC     = 2026-10-01T22:55:09Z
reviewed_commit_Asia_Singapore = 2026-10-02T06:55:09+08:00
original_base_SHA       = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review         = review_report_v17.md
previous_review_commit  = 65726494f63a3fa80906e93f12b5b09a1d99ae99
latest_response         = response_v20.md
V20_actual_source       = d41470d17d2babf29fabb0960886b0f60ae2aceb
next_batch              = V21_EXACT_ACTION_AND_RECYCLED_CORRECTION
response_required       = response_v21.md
decision                = ACCEPT_NUMERICAL_EVIDENCE_WITH_LIMITATIONS
V20_total_elapsed_gate  = FAIL_RETAINED
old_p4_inverse_route    = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate     = NOT_QUALIFIED
master_merge            = NOT_APPROVED
```

本次ChatGPT读取远程快照、规则、任务/最新合同、回应、结果及相关源码；没有SSH运行工作站，没有取得全部ignored数组或实时机器资源。历史为measured/recorded，公式与容量为derived，新队列为planned/not_run。参考结果已参与历轮研究设计，因此本批不称全新blind test；求解进程仍不得读取参考数组。

## 1. V20事实与审阅边界

依据：[Response V20](response_v20.md)、[详细结果](outcomes/fixed_p3_ilu0_port_v20.md)、[候选](outcomes/records/candidate_comparison_v20.csv)、[PC证据](outcomes/records/effective_pc_options_pivots_linearity_v20.json)、[截止记录](outcomes/records/deadline_stop_v20.json)、[费用](outcomes/records/resource_costs_v20.json)。

| 原0.7nm/384hex/p3/q15/40端口；无量纲measured | N无PC | P0固定ILU0 | P40同因子端口修正 |
|---|---:|---:|---:|
| 共同原rho起点 | 9.678334710e-6 | 9.678334710e-6 | 9.678334710e-6 |
| 最终原Schur；限1e-6 | 9.392262197e-6 | 9.652942892e-6 | 9.636716045e-6 |
| 最终原native；限1e-6 | 3.642354798e-6 | 3.743447756e-6 | 3.737154925e-6 |
| 散射E；限1e-4 | 7.946537973e-5 | 7.949932353e-5 | 7.949906395e-5 |
| 最大逐级功率差；限1e-6 | 1.807525273e-6 | 1.785765340e-6 | 1.785937630e-6 |
| 原rho降幅 | 2.95580% | 0.26236% | 0.43002% |
| 已完成周期/Arnoldi步 | 4/1024 | 4/1024 | 4/1024 |
| 路线charged wall，秒 | 193.57554 | 281.79620 | 330.97263 |

完整资格0/5。T迁移与零trace因进展准入不满足而not_run，不能写为冷启动失败。固定因子确实存在；K有3852576个存储非零、CSR载荷77124100 B，三次同规格factor setup约1.21/1.31/1.62秒。PC复线性/重复性通过，但一个诊断输入的norm(r-K B0 r)/norm(r)=40705.56；这是该输入的近似逆缺陷，不是K条件数、全输入误差界或已证明的排序根因。P40小系统条件数约3.1973e6、求解缺陷约4.15e-17，小块可靠并不意味着完整预条件有效。

因此，只收口“这一固定natural ILU0/P40在此输入和预算下无显著收益”，不宣布所有ILU/神经网络无效。Response提出的几何ordering没有被执行；本轮明确暂缓它，避免把后续变成普通ILU参数链。原材料、端口和强精度不改。

V20正式监督wall874.948403421秒、辅助75.529041533秒、采样同时树峰934690816 B、自身swap/VRAM0；formal历史下界67488.474122006秒。数值与清场于2026-10-01 22:28:02+08结束，早于旧总截止2026-10-02 01:33:21+08；后续06:46:42+08核验已超时。**数值负结果有效；端到端时间FAIL仍有效。** 不猜测中间原因，不以数值仅15分钟抵销墙钟超时，不补造缺失时间。后置mutation测试not_run保持。

## 2. 本批为何改这两处，不继续加因子

### 2.1 执行成本：局部类别矩阵不必每次展开成所有单元的副本

[原ActionPacket.apply](../../src/solvers/neural_fe_action_packet.py)每次执行`matrices=a['S'][a['classes']]`，再进行局部乘法；伴随路径还对展开张量取共轭。NumPy整数数组索引生成副本，见[NumPy copies/views](https://numpy.org/doc/2.0/user/basics.copies.html)。这提供了可检验的优化点，但**尚未证明它占主要wall，也没有实测新实现加速**。

把共享同一class的单元按最多64个分块，每块只调用该class矩阵。将局部trace排成行矩阵T，对一般复数非Hermitian S_class：

```math
L_{forward}=T S_{class}^{T},\qquad
L_{adjoint}=T\overline{S_{class}}.
```

两式不是同一个转置规则；后者是行布局下对应S_class的共轭转置作用。每块结果放回原cell顺序，再按原_pullback组装；不改变Floquet相位、orientation、共享贡献累加及端口项。类别必须来自原classes精确标签，不按材料“接近程度”合并，不假设任意三维模型只有少数class。

### 2.2 数值修正：保留一个小的正交作用像空间，而非再求一个更强全局逆

V19的LGMRES相对普通GMRES在同工作量下降残差已有证据，但当前只保留3个修正方向。新试验采用固定GCROT(256,32)：保留至多32个循环方向及其原算子作用像，使后续搜索避开已处理的残差分量。它仍是确定性线性求解，不是神经训练，也不保证比LGMRES好。

令A=barS。循环向量U_r及像C_r满足A U_r=C_r、C_r^H C_r约为I，先有：

```math
\eta=C_r^H r,\qquad x_{new}=x+U_r\eta,\qquad r_{new}=r-C_r\eta.
```

随后按算法在像空间之外构造新的Krylov修正并截断旧方向。U_r/C_r与物理端口C、历史3098列Q/U都不是同一个对象。实现复用现场SciPy `gcrotmk`，不另写未经验证的递推。契约见[SciPy 1.11.4 GCROT](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.gcrotmk.html)及[对应源码](https://github.com/scipy/scipy/blob/v1.11.4/scipy/sparse/linalg/_isolve/_gcrotmk.py)。

本次同时改变循环机制和保留容量，所以成功只归为“这一固定GCROT配置”的收益，不能仅归因于某一个因素；也不是GCROT与所有LGMRES配置的最优比较。原全局ILU因子、K CSR和历史Q/U/R不加载到候选求解进程；上游神经基/LSQR产生暖起点的成本不因此消失。

## 3. 权威、范围与冻结身份

根/目录AGENTS、仓库原则、原task、全部补充合同、最新review/response/summary按原优先级执行。当前目录没有另命名supplement时登记实际清单。旧task的首轮13.5nm/p4与独占heavy安排已由后续micro和受控共享合同覆盖；不能据旧导航回跑。原文不改。

本报告明确授权本批的作用实现opt-in和固定GCROT候选，覆盖上一批“不得新增其他方法”的批次限制；不恢复p4强逆，不做ILU ordering/shift/level扫描。新算法仍限Task042同一micro校正实验，不进入ordinary default。

| 冻结项 | 值/身份 |
|---|---|
| 物理 | 原Full3D complex128、0.7nm、grazing1度/azimuth0/s、三维缺口、原背景和RHS、x/y Floquet、Fourier-DtN |
| 离散 | 384hex/p3/h0.175nm/q15；full34050、trace18144、internal13824、slave2082；完整20+20端口，z18184 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1；ready，离线读取 |
| Si | n=0.999885140474+4.32477054e-6i；epsilon=n*n；source0.699999988明确alias到nominal0.7，不插值 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA256 | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| modes SHA256 | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| original action NPZ SHA256 | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 NPZ SHA256 | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |
| 暖主起点L-GPOLY，V19末态NPZ | 4b07fd9cbf313a2688925f77beb4e46205b2e203e98b2c9f7d2dcde2a91c10c2 |
| 条件另一末态L-GNN，V19末态NPZ | f71378e9aa528f6f6f4eddb3a4a1d53c24a54e71c36c932551011ccfffa45450 |

两个起点与V20对照相同，不选V20稍好N末态，也不继承P0/P40。路径从V19 checkpoint/run index逐项核对；文件hash与z数组hash分别记录。新V21目录、预算、状态槽独立，旧V19/V20只读。求解不读REF7、旧参考拟合头/误差、不选幅相；既有验证可指导本报告设计，不能称完全未看答案的研究。

## 4. A：精确class批量作用资格和小型计时

新增独立opt-in作用对象，原ActionPacket.apply/recover/uncondensed/audit保留不变。oracle与新对象共享只读packet数组，但独立调用/计数；**不能让所谓独立audit因继承/monkeypatch又调用新apply而自证一致**。最终及每个周期的原audit必须显式走旧oracle。

仅将局部S-class乘法按上述公式分块；本批优先保留原Bhat/Dhat/直接B,D/Hhat路径，避免同时重写所有端口收缩。固定batch_cells=64，不扫batch。不得缓存逐cell稠密S副本；额外持久缓存<=32 MiB、临时分块工作区<=64 MiB。大于缓存上限的class共轭按需分块使用；class数等于cell数时也必须正确。记录nc/lt/nclass以及16*nc*lt*lt旧展开载荷（derived），不将它称为RSS节省。

必须测试：复非Hermitian类别矩阵、类别交错与单例、不能整除64的尾块、非零端口、重复Floquet展开条目、复线性、S/S^H配对、输入readonly和维数拒绝。真实见证固定为两个复随机方向(seed422101/422102)、两个暖trace及其原残差，包含非零port和零向量；不得只测相消较少的零trace。

G-action：原/新S及S^H运算尺度差<=1e-10；新barS/barS^H配对<=1e-10；实际两个暖点的残差向量差/norm(原b)<=1e-11；原闭合/恢复/identity/slave规则保持。差分不仅报告相对大输出，还单列物理b尺度残差差，避免原残差很小时被大作用量掩盖。不通过则只隔离新backend，原oracle仍可信时C可用旧backend执行；不放宽门限。

等价通过后作三组固定输入成对微基准，每组交替顺序、一次warmup后10次S+S^H；再从同一暖点各运行一个LGMRES单边界调用，完整含barS/端口/求解/原audit，不把测试进展用于正式初值。该测试可以显示浮点顺序导致的迭代轨迹差异，不能据此要求两算法逐位一致。选择新backend需完整调用中位wall降低>=20%，且无超预算内存；否则求解用旧backend，不阻塞新的数值方法。配置和backend在正式候选前冻结，不每周期切换。

A总数值预算<=900秒、S/SH总调用<=1000。没有足够空闲核时不做性能声明；数学测试及可做轻量工作仍可保留。A速度收益与C收敛收益分别报告。

## 5. B/C：同一暖起点，两条无全局因子校正

H为原40维凝聚Hhat；F不假设等于C的共轭转置。原方程与固定校正问题为：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\qquad
\bar S=K-CH^{-1}F,\quad\bar b=b_t-CH^{-1}b_p,
```

```math
r_b=\bar b-\bar S t_b,\quad \bar S x=r_b,\quad x_0=0,\quad
 t=t_b+x,\quad\alpha=H^{-1}(b_p-Ft).
```

r_b先由旧oracle计算并冻结。所有候选原b分母不变；每周期用旧oracle重算完整b-Sz，不以内部估计残差或新backend自验决定通过。原/新残差向量差/norm(b)>1e-11则隔离该快backend的后续工作，已保存点由oracle补审；不能直接换backend继续旧循环状态而冒称无损续算。

**B：RESET-LGMRES256-K3-CONTROL。** 从t_b重新定义上述x=0、outer_v=[]，不读取V19的3个保留向量。使用已资格化boundary_call/commit，inner_m256、outer_k3、M=None、maxiter1、prepend_outer_v=False、store_outer_Av=False；最多16调用或900秒。这是同一个新残差起点的短对照，不与V19继续旧x/方向混称。

**C：BOUNDARY-GCROT256-K32。** 同一个t_b、r_b、x0=0、CU=[]独立开始。现场SciPy gcrotmk，m=256、k=32、truncate='oldest'、M=None、discard_C=False、maxiter=1；保存返回x和CU后，再进行下一边界调用。tol/rtol=0，atol=1e-8*norm(原完整b)，现场版本适配不升级。不是右ILU，不载入旧Q或参考方向，不求全局逆。

B/C都允许更新全部18144个独立trace，40端口按原方程闭合。不得把校正x直接当物理t，也不得重复加t_b。输出头/网络不参与本批更新，不能宣称新增hidden训练。

## 6. GCROT特殊接口与恢复必须按真实库合同

SciPy 1.11.4源码中CU为**(c,u)**且c=A u，不是LGMRES的(v,Av)。函数原地修改list和向量；调用前深拷贝到trial，成功返回后原子保存x、全部c/u、None掩码和顺序，再close/audit/commit。异常只回滚到上个完整返回边界，消耗不回滚。

源码每次返回附加(None,x.copy())，因此返回库存可有k+1=33对，其中None表示下次按原A重算像；**不得丢掉特殊条目、把None存成零像、硬断言list长度<=32，或将循环像C_r误当物理端口C**。下次仍从保存的原始顺序/掩码调用库，承认库会重排和重新正交化。最多33对是当前实现的返回上界，若现场库语义不同先定位，不静默换规则。

实际内部长度为m+max(k-len(CU),0)，首次可以是288而非256；callback是外层x，不是Arnoldi步。主要按真实A/S调用计费，内部步数没观测就unknown，不把一个返回写成固定256内步。maxiter1封装反复进行入口重正交化，方法明确称BOUNDARY-GCROT，不声称与一次长调用逐位等价。

最小测试用需多于一个周期的复非Hermitian系统，含非零40端口/非零t_b，比较四次连续**边界调用**与两次+独立读盘+两次的x、CU、原残差；运算尺度差<=1e-12。覆盖None条目、k+1库存、首周期288计数语义、半写/kill/错hash、返回后close失败只补审、零rhs/已收敛、info>0但有限更新、库返回不更新或非有限的区分。不能只测一次小系统马上收敛。

每8调用对所有非None回收像作原A配对，运算尺度缺陷<=1e-10，记录C_r正交性及有限性；None像重算费用计入。配对失败先最小定位，不能不断清空CU继续并仍标相同连续路线。旧C/F/Hhat与原close使用已有资格，不重做旧全部制造/FD/teacher。

## 7. 有限自动队列、继续准入与零初值

| 阶段/数据身份 | 必须完成的工作 | 自动分流与上限 |
|---|---|---|
| D0 planned | 实时时钟/预算复核；完成V20未运行reader最小mutation回归；输入和新接口测试 | 不重跑V20 PDE，不把历史not_run改PASS |
| A planned | 上述作用等价和三组成对成本 | 数值可信但不快用旧作用；数学失败只隔离新作用 |
| B planned | 主暖点RESET-LGMRES短对照 | 最多16调用/900秒，不作为C准入条件 |
| C planned | 相同主暖点GCROT | 数值安全先最多32调用，使回收空间有机会建立；随后每16调用rho降>=5%才继续，最多128调用/3000秒 |
| T conditional | 同规格GCROT从L-GNN末态，x0=0、CU=[] | C达到原方程PASS或rho至少降10倍，才运行；先32，后16块5%，最多64/1800秒 |
| Z conditional | 新进程零trace、x0=0、CU=[]，只读原packet/材料/port | 同C进展准入；先32，后16块rho降>=10%，最多128/2400秒；T失败不取消Z |
| V planned | 队列冻结后一次独立FE审核，最多12去重状态 | 参考开始后不再回算，不新LU |

不得因C尚未达到旧表示场误差0.5等门限而拒绝前32调用；它是完整空间求解。但非有限、原作用不可信、资源/预算触线仍立即停止。C低于原方程门限时保存FIRST_PASS；最多再8个调用追求可选rho<=1e-8，受同一调用/时间上限约束，原成功门限仍1e-6。因功率可能滞后，FIRST_PASS与最终抛光点都需验证，不默认小残差意味着全部observable合格。

两次连续原rho上升超过max(1e-10,100*原重复作用差/norm(b))，复核同一保存点一次；非实现原因则停止该路线。到32之前不因单次微小非单调强制结束，但不得掩盖失稳。C完结仍无十倍进展时不启动T/Z，不扩大k/m、不换truncate或加PC。

Z是ZERO_TRACE_FROM_FROZEN_OPERATOR，不是从几何输入的完整fresh run；端口和内部特解不置零。Z不读暖解、旧Q/U/R、任何网络/参考权重或暖CU；其成功才提供“此micro是否需要昂贵神经辅助初值”的独立证据。复用优化backend是算子代码复用，不是复用已求解信息。暖通过而Z失败只能WARM_MICRO_PASS，全部上游准备和求解成本保留。

## 8. 时间、资源和自行修复：避免重现交付超时

总窗口为接手时起14400秒，start+12600秒停止数值重负载，最后1800秒交付；实现、测试、修复、冷却、数值、报告都计入。启动即从实时UTC与monotonic/boot_id写不可重置deadline。**每次上下文恢复、每个新stage、每次commit/push和交付前重新读实时时钟及持久化ledger，不接受摘要中的“剩余时间”。** 跨重启monotonic不能相减，使用已冻结UTC并保守处理，禁止刷新窗口。

增加低负载的自动checkpoint/费用/状态收口入口，数值队列结束立即产出最小response数据包，而不是把所有证据编写留到最后。总截止到达时不启动新pytest/性能测试/数值stage；清场、保存和必要交付可以完成，但实际延迟照录TOTAL_ELAPSED_NOT_COMPLIANT。不能保证外部对话恢复时间，不能因此扣除未知间隔。D0的期限测试只用模拟时钟，不真实等待数小时。

全批S+SH（旧oracle和新backend逐向量相加）<=100000；A<=1000，B<=5000，C<=45000，T<=22000，Z<=42000，但这些子上限不得相加突破全局/时间上限。原audit<=320，场状态<=12；新持久artifact<=2 GiB。按每调用最大384次作用先预留，再按完成实测结算；kill保留上下界并按上界扣预算，不清零。当前GCROT回收库存约2*33*n*16字节，内部双基与副本另计；预估所有Krylov/事务临时对象<=1 GiB才启动，实际RSS另测，不用向量载荷冒充树峰。

继续受控共享CPU：现场选空闲物理核、避开忙SMT、MPI1、数学/Torch线程1、Loader0、GPU不用；规划常驻<=8 GiB、warn12/hard16 GiB、own swap0；系统max(128 GiB,effective_total的10%)、邻增长128 GiB及自有16 GiB余量，磁盘free>=50 GiB。一次一个本任务数值actor；不改邻任务环境/锁/亲和性/优先级/watchdog、全局ABI/BLAS/CUDA/swap。原PSI full avg10>=0.1连续三次5秒保护及0.5秒整树监督保持，无cgroup不宣称kernel连续硬限额。

资源停止后释放负载；最少120秒冷却，最多600秒观察，full avg10<0.05持续60秒且其余Gate通过才重入；最多两次，累计等待<=1200秒，计入截止。方法切换不能绕过资源压力。

计划内实现与D0不占意外修复根因数，但其时间照计。最多四个已定位意外根因级最小修复，每次<=900秒、累计<=2400秒、同根因最多两次。数值无进展不是bug；格式缺项留安全阶段，不打断正确活跃source。公共数值/身份/预算错误先修，失败只隔离依赖路线；不每小步等用户确认，不为了跑满窗口重复失败。

## 9. 独立物理审核、贡献和最后取舍

所有求解/选择/hash冻结并退出后，由独立FE环境一次读取REF7，复用原验证器和旧oracle。最多12状态：两个历史L末态、B终态、C/T/Z的终态及首次PASS、至多两个预登记32调用快照；去重后不超过12，不从参考挑“最好中间点”。原参考非零native保留，误差恢复必须消掉原内部特解。

原Schur/native/增广及规定port<=1e-6；恢复/identity<=1e-10、slave-zero；total/scattered E/H、scaled-curl、selected复场及40复振幅<=1e-4；R/T/A/A_volume绝对差<=1e-5、每通道功率差<=1e-6、能量<=1e-5。原native与独立total-native两列不混用；不能重新校幅相或四舍五入越过门限。未通过原方程的功率是UNQUALIFIED_DIAGNOSTIC。

| 证据 | 允许的结论 |
|---|---|
| class批量等价且完整调用更快 | EXACT_ACTION_ENGINEERING_GAIN；不是收敛通过 |
| 同backend下C优于B的原残差/成本 | 固定循环配置研究正信号；不是神经训练增量、不是最优算法证明 |
| 原残差通过而功率不过 | EQUATION_PASS_PHYSICS_FAIL；保持门限，不能发布完整资格 |
| 暖完整通过而Z未通过/未运行 | WARM_START_MICRO_DISCRETE_PASS_ONLY；上游费用完整保留 |
| Z完整通过 | ZERO_TRACE_MICRO_DISCRETE_PASS_ONLY；p/h、目标规模、48h仍not_qualified |
| 两个新机制均无有效收益 | 收口这一固定配置，说明具体数值/资源失败，不追加相同排序/缩步循环 |

新作用在class很多时未必快；GCROT库存随N增长，固定32并非波长鲁棒性证明。2 TB只放宽预算，主线仍需分布式、matrix-free、可扩展Full3D迭代PC和有界粗空间，Hybrid不能代替任意三维。本批不做新p4参考、全局谱/SVD、Q扩容、其他波长、最大模型或merge。成功时只整理下一阶段p/h与多规模容量方案，不自动执行。

## 10. 代码与交付

复用原packet/BarAction/独立audit、LGMRES与事务writer、已有one-run队列/监督；数值核心进入src/solvers，只新增薄stage配置。不要为每条路径复制一套数百行runner。新快速backend显式opt-in，old oracle/ordinary default不变；GCROT库参数直接记录现场签名，不改已安装SciPy。

先focused测试、deadline/序列化mutation及新输入注册测试，commit clean后validate并按条件运行以下待创建入口：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v21_action_recycling_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v21_lgmres_control.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v21_gcrot_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v21_gcrot_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v21_gcrot_zero.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v21_verify.dat
```

入口在review提交时尚未实现；每个slice是独立明确dat与同一campaign预算，不能盲跑条件T/Z。正式记录input_original/resolved/manifest/input/physical/material/mode/action/backend/parent/x/CU hashes、实际source、环境/ABI/MPI/线程、run_summary和全过程资源。文档HEAD不冒充运行source。

C1提交作用与循环接口/测试；C2有效资格与数值队列；C3冻结验算/compact reader；C4 response与账。活跃run中不改其受检HEAD。将反例测试尽量随实现提前完成，避免再在截止后新增未验证reader代码。

交付response_v21.md、outcomes/exact_action_recycled_correction_v21.md，以及紧凑records：clock_deadline、action_equivalence、paired_kernel_cost、recycle_contract、cycle_history、candidate_comparison、field_channels、checkpoint_inventory、run_index、resource/repair/reentry、lineage及明确not_run。大CU/向量留ignored；不反复复制整套多MB嵌套JSON。同步summary/tests/changed_files/README导航、development_progress和development_model_registry；旧task/review/response/raw不改。

Markdown用fenced math和一致表格，检查精确GitHub页；拿不到视觉证据记录NOT_VERIFIED，不伪称渲染通过。仅推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。队列完成/截止/安全上限后清场，报告完整HEAD/upstream/worktree、实际source、作用等价与速度、循环空间及原方程/物理资格、冷暖/历史成本、真实交付时刻和唯一下一建议；停止等待review，不merge。
