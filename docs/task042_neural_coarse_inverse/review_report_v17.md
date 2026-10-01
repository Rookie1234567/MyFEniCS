# Review V17：V19审查、固定p3不完全分解与端口感知校正

## 0. 审阅决定与本批要消除的障碍

**接受V19的原方程抛光、方向保留和独立场证据，不授予完整有限元或神经加速资格。下一批改变校正机制，而非再次默认延长无预条件迭代：在同一个p3微型算例上，只构造一种固定的稀疏体块ILU(0)，比较它及同一因子的40端口修正。数值可信且有明确进展后，继续同配置求解、另一已冻结起点和零trace初值检查。禁止变成ILU参数扫描或重开旧p4强逆任务。**

本批要回答：已经接近参考场的候选，为什么仍需要大量无预条件作用才能压低原残差；一个有明确存储上限的耦合预条件作用能否改善它。进一步检验改善是否依赖数小时的旧辅助基/LSQR初值。ILU(0)用近似三角分解把残差转换为耦合修正，保持固定稀疏填充级数；它不是准确逆，可能零主元、失稳或无效。端口修正仅把原有40通道纳入同一近似因子，不改变原方程。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42_neural_coarse_inverse
worktree                   = /home/fenics/Projects/NN-Lab
review_date                = 2026-10-01
reviewed_HEAD              = 2b75bf94941a6fab007498657fbc188249d51b5e
reviewed_commit_UTC        = 2026-10-01T12:41:08Z
reviewed_commit_Singapore  = 2026-10-01T20:41:08+08:00
reviewed_latest_commit     = Task042 V19 record bounded polishing and failed full physical gates
original_base_SHA          = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review            = review_report_v16.md
previous_review_commit     = 5b489b7264b75a9461577303ff0f6bc8907c19dd
latest_response_reviewed   = response_v19.md
V19_numerical_source       = b58919a4a0dcd677b915eb7d9bbd314520aef0e0
next_batch                 = V20_FIXED_P3_ILU0_PORT_QUALIFICATION
response_required          = response_v20.md
decision                   = ACCEPT_EVIDENCE_CONTINUE_BOUNDED_RESEARCH
old_p4_inverse_route        = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate        = NOT_QUALIFIED
master_merge               = NOT_APPROVED
```

最终目标不变：约2 TB整机物理内存内，48小时内完成新的0.7 nm、非可分三维周期单胞有限元解。当前仍是384-cell micro、MPI1、16 GiB研究配额。本报告授权的是**带额外装配/全局不完全因子的微型机制对照**，不是factor-free生产路线；其成功不能替代分布式、matrix-free、可扩展Full3D架构。ChatGPT实际读取远程最新提交、合同、回应、紧凑结果和相关代码，没有运行工作站或读取全部ignored数组。历史数字为measured/recorded，公式和容量为derived，新工作为planned/not_run。

## 1. V19：改善真实，但不能把接近门限当作通过

依据：[Response V19](response_v19.md)、[完整结果](outcomes/post_lsqr_residual_polish_v19.md)、[候选CSV](outcomes/records/candidate_comparison_v19.csv)、[同工作量](outcomes/records/paired_same_work_v19.csv)、[周期](outcomes/records/polish_cycles_v19.csv)、[checkpoint](outcomes/records/checkpoint_inventory_v19.json)、[费用](outcomes/records/resource_costs_v19.json)。

| 相同0.7nm/384hex/p3/q15/40端口；无量纲measured | P-GPOLY | L-GPOLY | P-GNN | L-GNN |
|---|---:|---:|---:|---:|
| 原Schur；限1e-6 | 2.233584995e-5 | 9.678334710e-6 | 3.248817978e-5 | 1.443938385e-5 |
| 原native；限1e-6 | 8.661927077e-6 | 3.753294800e-6 | 1.259903898e-5 | 5.599647663e-6 |
| 独立total-native；限1e-6 | 3.005683382e-6 | 1.302390987e-6 | 4.371858789e-6 | 1.943074296e-6 |
| 散射E；限1e-4 | 7.990971686e-5 | 7.950032150e-5 | 9.763896902e-5 | 9.707930475e-5 |
| 散射curl/H；限1e-4 | 7.989388591e-5 | 7.951016691e-5 | 9.760393565e-5 | 9.708300991e-5 |
| 最大逐级功率绝对差；限1e-6 | 1.656411228e-6 | 1.785534642e-6 | 6.379231972e-6 | 5.647060646e-6 |
| 能量缺陷；限1e-5 | 1.837310175e-6 | 1.960331680e-6 | 1.088700628e-5 | 9.656013793e-6 |

四条均完成64次调用，停止于预登记次数而非证明停滞；完整资格0/8。L相对P在相近作用/时间下将残差进一步降低约2.3倍，但场误差几乎不变；GPOLY逐级功率误差反而略增。尚需原Schur约9.68/14.44倍降低，且必须同时满足功率门限，不能只追求一个更小的norm。

L-GPOLY第56到64周期rho从1.066610876e-5降至9.678334710e-6，约降低9.26%。这不是完全停滞，也不是再给固定次数就必过的证据。残差降低并不单调保证所有场/功率误差降低；本次不能宣称发现了唯一坏模态、全局条件数或数值误差下限。

新增formal监督wall9199.970576 s、辅助监督102.206160 s截至记录快照；formal累计下界66613.525719 s，旧辅助unknown保持。采样同时树峰796585984 B、own swap/VRAM0。该0.742 GiB不包含即将新增的K/因子，也不是历史建基全过程峰。不同路线研发总和不是单个成功解的部署时间。

原算子/恢复/端口及返回后保存继续复用。C0和证据测试中的失败、MPI socket权限重放原样保留，不因最终检查通过删除失败。V19没有隐藏训练；GPOLY/GNN上游都含相同随机神经G0。L的收益首先属于确定性跨周期方向保留，不属于神经训练增量。

## 2. 范围覆盖、禁止事项与方法定位

先读根/目录AGENTS、仓库原则、task、全部补充合同、最新review/response/summary。当前任务目录未列出另命名supplement时按实际清单记录，不猜造。旧task中的13.5nm/p4首轮及独占heavy约束已被后续micro和受控共享授权覆盖，不能据旧导航回跑；旧正文保留。

本报告只对本批覆盖“不得装配任何全局p3块/不得新增PC”的限制：允许**原凝聚trace体块K的单一稀疏装配与固定ILU(0)**。明确记GLOBAL_P3_INCOMPLETE_FACTOR_PRESENT，不能继续写完全无全局因子。它不是原p4准确逆，也不要求对任意rhs返回1e-10；但仍含全局三角依赖，不能直接推广为目标规模生产PC。

不允许：完整S/barS的稠密化或全局准确LU；p4/p6因子；ILU填充级数、ordering、drop_tol、shift、restart扫描；正定/加吸收替换原方程；新网络/patch/Q扩容；参考误差喂入PC；新p4参考、放大网格、GPU或master合并。本批不追加另一轮数小时的原样LSQR/LGMRES，不读取旧L方向列表来污染新配对。

## 3. 冻结物理和起点

| 冻结项 | 值/身份 |
|---|---|
| 方程/边界 | 原Full3D complex128，0.7nm，grazing1度/azimuth0/s，三维缺口、原背景/RHS，x/y双Floquet，完整Fourier-DtN |
| 离散 | 384hex/p3/h0.175nm/q15；full34050、trace18144、internal13824、slave2082；top20+bottom20，z18184 |
| 材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1；离线读取不再索要 |
| Si | n=0.999885140474+4.32477054e-6i；epsilon=n*n；source0.699999988明确alias到nominal0.7，不插值 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA256 | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| modes SHA256 | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| original action NPZ SHA256 | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 NPZ SHA256 | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |
| L-GPOLY末态NPZ SHA256 | 4b07fd9cbf313a2688925f77beb4e46205b2e203e98b2c9f7d2dcde2a91c10c2 |
| L-GNN末态NPZ SHA256 | f71378e9aa528f6f6f4eddb3a4a1d53c24a54e71c36c932551011ccfffa45450 |

路径由V19 checkpoint_inventory/run index解析，NPZ文件hash与z数组hash分开。V19只读，V20独立artifact/ledger/cache/窗口。主配对固定L-GPOLY末态；另一L-GNN只用于条件迁移检查，不依据本轮参考结果更换起点。历史参考报告已参与任务设计，故不称新blind heldout test；所有求解进程仍禁止打开REF7数组及旧参考拟合/误差。

## 4. 原算子、唯一K装配与额外成本

沿用原BarAction的符号，H为凝聚Hhat而非未凝聚Hp，F不假定为C的共轭转置：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\qquad
\bar S=K-CH^{-1}F,\qquad \bar b=b_t-CH^{-1}b_p,\qquad
\alpha(t)=H^{-1}(b_p-Ft).
```

原[ActionPacket](../../src/solvers/neural_fe_action_packet.py)的trace-trace作用为以下精确装配，E_c就是原_expand的局部Floquet展开：

```math
K=\sum_c E_c^H S_c E_c.
```

从packet的S/classes及erows/eids/evals构造K；保留所有原cell Schur贡献、方向和复周期相位。不得分别凝聚curl与mass再相减；不得另用节点坐标猜约束；不得只取class矩阵或重复master。结构模式先按局部耦合与约束合并，数值零不凭经验阈值删项；结构对角可明确预留但不能以1替代零主元。使用有界chunk累计、合并重复贡献，CSR的排序/合并规则冻结。禁止构造n阶稠密矩阵或18144次单位向量探测来生成K。

容量先算再分配：K结构nnz<=20000000；压缩CSR实际数组载荷<=512 MiB；额外因子显式载荷上界<=1 GiB；全过程规划峰<=8 GiB、树warn12/hard16 GiB。索引位宽使用当前PETSc.IntType，记录CSR、PETSc副本、symbolic、numeric、workspace和审核对象重叠。后端allocated memory不等于独立RSS；无法独立分离因子RSS写unknown，不能用空闲RAM替代上界。容量不合格只跳依赖PC路线，保留短无PC对照和已完成证据，不OOM探容量。

K只作PC/setup，正式外层仍使用原packet/BarAction，不以新CSR悄悄替换原作用。用两个固定复随机向量(seed422001/422002)、实际基点trace和其原残差方向验证K乘法及K^H对照，operation-relative<=1e-10；闭合后与原barS向量之差/norm(原b)<=1e-8。原C/F的直接端口作用另与完整packet配对。已有40端口列可按hash复用；确实缺失时只重建40列，不重建Q或teacher。

## 5. P0：只准一种真正的ILU(0)

采用现有complex PETSc栈：COMM_SELF/MPI1、SeqAIJ、native PETSc PCILU、levels=0、natural ordering、shift_type=NONE、无数值drop/附加排序/对角救援；零主元容差记录现场默认，不作扫描。使用独立options prefix并记录PC.view和有效配置，不让外部全局options覆盖冻结值。优先out-of-place，K保留可审核身份，不修改原packet。

[PETSc PCILU](https://petsc.org/release/manualpages/PC/PCILU/)与[填充级数定义](https://petsc.org/release/manualpages/PC/PCFactorSetLevels/)为算法契约；API以现场已安装版本确认，不升级。**SciPy spilu(fill_factor=1)不能直接改名为ILU(0)**：其[接口](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.spilu.html)定义的是drop/fill规则，而非这里的level-zero契约。原生PETSc backend不可用则记录阻塞，不静默换ILUT。

新PC worker使用已资格化FE/PETSc解释器；pure NumPy原packet可同进程读取，不把另一套PETSc/MPI注入Torch/ML进程，也不安装新库。记录实际loaded libraries、ScalarType、IntType及数学线程；已有MPI socket权限问题优先复用已批准运行环境，不禁用监督/网络隔离以隐藏失败。

记ILU因子隐含的矩阵为M0，B0 r是其三角解：

```math
B_0r=M_0^{-1}r.
```

不得显式形成B0。PC是固定线性作用，不在apply内部启动Krylov或改容差。零主元、非finite或后端失败是该固定配置的结果，不临时加shift、改ordering或level。先小型非Hermitian复杂稀疏fixture与独立no-fill参考配对；实际矩阵只要求重复性、复线性和finite合格，不能又要求近似PC单次达到准确逆残差1e-10。norm(r-KB0r)仅作诊断。

K数值装配一套，PC参数规格一套。因one-run进程隔离而重建相同因子允许计费，但最多5次大因子setup（含资格、两暖路线、迁移、冷启动）；复用合法因子必须声明进程/数据身份，不序列化不可恢复的PETSc对象。不允许为了满足“只建一次”将多个候选藏成一条不明dat。

## 6. P40：同一体块因子的端口修正，不再加一种ILU配置

先做P0；P0数值可信而未过原方程时，使用同一B0构造：

```math
W=B_0C,\qquad J_p=H-FW,\qquad
B_{40}r=B_0r+W J_p^{-1}F(B_0r).
```

此式是M0-CH^{-1}F的逆作用（相关块可逆且精确运算时），不是原barS的准确逆。它避免仅凭体块预条件就把所有端口耦合忽略；原40个通道均保留。W仅18144×40的complex128数组，载荷11612160 B，约11.07 MiB；Fp/W及所有workspace另计。用40次同B0作用和原F构造，不重新分解K，不使用Hp替代Hhat，不把Jp命名为真实物理Schur。

F通过packet原局部Dhat/直接D项实现并核对符号，不假定互伴、不每次额外跑一个完整volume action来伪装便宜PC。记录F与B0次数和耗时。Jp的cond2<=1e10、40维solve运算尺度缺陷<=1e-12；否则仅P40_NOT_RUN_PORT_CORRECTION_UNSAFE，P0/控制已完成结果保留。小fixture检验上述逆公式、非互伴C/F及错误号反例；实际不要求barS B40=I。端口修正不安全不能删除通道或调小cond标准。

## 7. 右预条件与真实残差：每个候选仍求同一方程

以固定暖起点t_b为例，每周期重新计算原残差r_k，求：

```math
r_k=\bar b-\bar S t_k,\qquad
\bar S B\,y=r_k,\qquad y_0=0,\qquad t_{k+1}=t_k+B y.
```

B=I/B0/B40分别定义无PC、体块PC、端口感知PC。使用已安装SciPy GMRES256对LinearOperator(y -> barS(B(y)))，**M=None**；这样实现右预条件。不能把B放入SciPy的M参数后仍称右预条件（[SciPy契约](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.gmres.html)中M为左预条件）。内层tol/rtol=0、atol=1e-8*norm(原完整b)、maxiter=1、callback_type=pr_norm，正式原方程门限仍1e-6。

返回后先保存y与实际By/新trace，再原close得到z，切出40port，再独立audit/commit。不要把y直接当trace；不要重复加base；不要为PC改物理b或重归一化。小回归必须端到端覆盖真实dat解析、worker、右侧组合、完整close、失败后补审、计数与冷启动零trace。每周期保存原b-Sz；info/callback或预条件残差都不是资格。

首次原方程通过点单独保存，不覆盖。若还有配额，至多再2周期求1e-8余量；这是可选抛光，不提高强制门限。即使到1e-8也不能保证功率，必须最终V。

## 8. 固定队列与有进展后的后续，不在第一次普通失败就整批结束

| 阶段/待实现入口简称 | 内容 | 预算/继续规则 |
|---|---|---|
| S0 capacity_setup | 基点复核、K符号/容量/装配配对、唯一ILU0/右侧组合资格 | setup与数值资格合计<=1800s；可信即实际求解 |
| N control | L-GPOLY原点，无PC GMRES256 | 固定最多4周期；用于同算法PC贡献比较，不是新长迭代 |
| P0 body_ilu | 同一L-GPOLY原点，B0右预条件 | 先4周期，rho下降>=10%再4；以后每4周期同规则，最多16 |
| P40 port_ilu | P0未通过且PC块可信，同一原点独立用B40 | 同上；不从P0终态warm start，不增加因子配置 |
| T transfer_gnn | 选中的PC已有原方程通过，或原rho相对暖原点下降>=10倍；使用同规格PC | 从L-GNN末态新校正，最多16周期，按4周期10%规则；不是新物理泛化 |
| C zero_start | 同样进展准入后，从零trace、端口按原b闭合开始 | 不读旧解/Q/网络参数；最多32周期，每8周期rho下降>=20%才扩展 |
| V verify | 求解/选择冻结后一次FE完整审核 | 最多12个去重状态；验证后不再回算 |

顺序S0→N→P0→条件P40→条件T→条件C→V。N不依赖PC成功；S0中PC零主元/容量失败仍完成可信的N和轻量分析，但不据此擅启新PC。P0数值/接口不可信先修；只是收敛不好仍可做P40。公共错误先定位一次，避免在另一库复现同一失败。

预选PC只用原方程：优先已有原方程PASS且达到首次PASS所需总作用较少者；未PASS则选原rho较小的合法候选，同值优先B0。把rho与耗时分别报告，不能忽略setup。若P0已原方程通过，P40可不运行，直接T/C；若T失败不取消独立的C。每条暖PC周期wall<=1200s，T<=1200s，C<=1800s；所有路径同时受总截止，不抢占最后验证预算。

C使用新进程、从原packet重新构造同一K/因子，不能沿用暖过程内存中的因子或已求解向量。其名字是ZERO_TRACE_FROM_FROZEN_OPERATOR，不是从原几何输入开始的完全端到端fresh run：原packet/mesh/材料准备仍是必要上游成本。零trace也不意味着端口或内部特解为零；按原Hhat和非零RHS闭合与恢复。成功说明本micro存在不依赖旧神经基/长迭代初值的确定性路线，不能直接宣布神经方法普遍无用。

如果PC无显著收益，收口该固定ILU0/端口修正规格，列出实际pivot、PC响应、原残差与时间；不扫描drop/ordering/shift，也不自动继续旧LGMRES。下一项架构变化需要下一份review。

## 9. 状态、计数和安全资源

复用V18/V19返回→数值落盘→close→audit→commit协议。原action、K pattern/numeric、PC规格/有效配置、父trace、method/library、环境、实际source和窗口hash入manifest。PC事务需保存实际物理候选和右变量身份，不以若干callback数恢复未返回Krylov；返回后审核失败只补审。跨进程因子重建要计时并做固定2个PC作用配对，不能伪称保存了完整因子状态。

预算从接手起总14400s，start+12600s停重负载，1800s收尾；实现、修复、资格、setup、冷却和验证全计。全批原S/SH<=35000；B0三角apply<=35000（B40内部也算），F辅助作用<=35000；大K装配<=2次（共享一份与冷启动一份），同配置大ILUsetup<=5次；原audit<=120，字段状态<=12，新增持久artifact<=2 GiB。必要的受影响修复重放也扣此上限；不让次数预算成为目标。写盘父子/叶计时不重复累加。

同库/路线条件按其自身rho，不利用参考图像决定是否继续。两周期原Schur增长超过max(1e-10,100*已测重复作用差/norm(b))时，对同状态复核一次；不是finite/接线错误则停止该路线，保留证据，不偷偷线搜索。PC行/列装配或符号失败必须先修，不能用更大填充掩盖。

沿用受控共享CPU：其他heavy存在不自动阻塞；现场选空闲物理核避开忙SMT，MPI1、数学/Torch线程1、DataLoader0、GPU不用；规划峰<=8 GiB、树warn12/hard16 GiB、own swap0；保留max(128 GiB,effective_total的10%)系统余量、邻增长128 GiB和本任务16 GiB，磁盘自由>=50 GiB、Task042总artifact<=20 GiB。不得删旧负结果腾空间。仅管理自身进程，不改邻任务的锁/亲和性/优先级/监督，不改ABI/BLAS/CUDA/全机swap。

原PSI保护保持：full avg10>=0.1连续三次5s检查停止自身负载；至少120s冷却，最多600s观察，full avg10<0.05连续60s且其余Gate通过才重入。全批最多2次资源重入、累计等待<=1200s，计入截止；换算法不绕过资源不安全。独立0.5s进程树watchdog，不声称无cgroup时具有kernel连续硬限制；写盘不拖延硬清场。

至多4个意外根因级最小修复，每次<=900s、累计<=2400s，同根因最多2次。计划内新PC/右侧接线和测试不是意外失败，但其费用仍计入总窗口。数值零主元/不收敛不是bug；修复不能变更PC数学规格。非关键展示问题留安全阶段，原身份/真实预算/监督缺口先处理。前置Gate通过就连续完成已授权队列，不每个小阶段等待确认。

## 10. 验算、贡献和下一阶段的硬边界

所有求解退出、预选PC/状态/hash冻结后，独立FE进程才读REF7。最多12个状态：2个旧L末态、N、P0/P40末态、T/C末态最多7个，加相关首次原方程通过点最多5个；重复z去重。不从参考挑最好中间点。

严格Gate不变：原Schur/native/增广和规定端口各<=1e-6；恢复/identity<=1e-10、slave-zero；total/scattered E/H、scaled-curl、selected复场和40复通道<=1e-4；R/T/A/A_volume绝对差<=1e-5、每通道功率差<=1e-6、能量闭合<=1e-5。参考实际非零native重记；近零沿原绝对规则，不校幅相、不将功率反推复振幅。原native与独立total-native分母不同，保持两列。

| 观察 | 结论/动作 |
|---|---|
| 因子/setup失败但无PC对照完成 | FIXED_ILU0_SETUP_NEGATIVE；不称神经失败，不扫参数 |
| 原残差明显下降但功率仍不过 | EQUATION/PHYSICS分列；未完整合格功率仍diagnostic |
| 暖PC完整通过、零初值不通过 | WARM_START_MICRO_PASS_ONLY；保留全部上游成本，不宣传单次快速求解 |
| 零trace同离散完整通过 | ZERO_START_MICRO_DISCRETE_PASS；本micro可能不需要旧神经基，仍无p/h/大规模资格 |
| P40优于P0 | 本固定近似因子的端口处理收益，不是网络训练收益 |
| 全部失败 | 保留当前最小残差与具体失败项，结束该固定规格，不追加同设置循环 |

通过时只整理下一阶段p/h资格、多个规模容量测量、作用/PC/端口数据分布式化的清单，不在本批启动新p4参考或更大模型。2 TB放宽容量但不能替代可扩展架构；天然顺序的全局ILU三角作用不直接成为目标生产方案。

成本分开报告：本批增量；暖链所需历史基/image/LSQR/抛光与本次成本；零起点从原packet到解的成本及packet构建缺项；所有研发累计下界。没有相同严格精度就不称加速。不能把最后几秒校正的成本当作全部求解，也不能把两库全部研发总和当作一个解的耗时。

## 11. 实现、正式入口与提交

数值核心进src/solvers，参数化复用原runner/BarAction/close_point/原子writer/审核，不再复制大型solver脚本。默认旧路径、旧资料、旧负结果不改。新factor阶段走已有FE栈，PC代码不导入Torch；K由原packet构造，不需要重新JIT整套FE模型。直接查现场PETSc接口，小fixture验证后才正式启动，权限/认证不无限等待。

先实现和focused回归、提交clean源码、validate后按条件执行以下**待创建**入口；每个dat是一项明确计算，slice/resume继承同一窗口：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v20_capacity_setup.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v20_control_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v20_ilu0_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v20_ilu0_port_gpoly.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v20_transfer_gnn.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v20_zero_start.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v20_verify.dat
```

条件未满足的入口记not_run，不能盲跑全部命令。正式run绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/material/mode/action/K/PC/父状态hash、实际source、环境/ABI/MPI/线程、run_summary与全过程树RSS/时间。不要将文档HEAD当计算source。

建议提交：C1新稀疏块/PC接口、右侧作用与小测试；C2正式setup/准入记录；C3合法数值结果与验证；C4紧凑reader/response。活跃运行身份不得因提交文档改变；只在安全阶段推进HEAD。各stage可按已冻结源码连续执行，不等每次推送后再授权。

交付response_v20.md、outcomes/fixed_p3_ilu0_port_v20.md及紧凑records：capacity_and_pattern、K_action_pair、effective_pc_options/pivots/linearity、port_correction、right_pc_cycle、candidate_comparison、original_audit、40channels/fields/power、checkpoint与lineage、cold/warm成本、resource/repair/reentry/run_index及明确未运行项。向量、CSR、因子workspace放ignored artifact，不能Git提交大数组或反复复制巨型嵌套JSON。

同步summary、tests、changed_files、任务最新导航、development_progress和development_model_registry。Markdown使用fenced math、列数一致，检查链接和精确GitHub渲染；不能取得视觉证据写NOT_VERIFIED，不假称完成渲染Gate，也不为此取消可信数值队列。

只推送git push origin HEAD:refs/heads/task42_neural_coarse_inverse。结束于全部可执行队列完成/总截止/安全或修复上限，清理自身负载，报告完整HEAD/base/upstream/worktree、实际source、PC实际配置和因子存在性、原方程与完整物理资格、冷暖成本、资源和唯一下一建议；随后停止等待review，不merge。
