# Task041 Review V13：结束嵌套迭代长跑，验证一致固定BAL_H块预条件并取得0.7 nm全场

## 0. 审阅决定与身份

**最新V12不是没有运行，而是已运行52,356.221 s（14.543 h），outer到11步后仍未收敛，最后一次模态子求解32步的独立残差为0.472902，超过近似PC接纳线0.1。两侧因子已完成，峰值约53.50 GB，未触80 GiB上限。当前首要问题是嵌套预条件器的有效性与总工作量，不再是50 GiB限制、8步入口或QEP未运行。**

本轮不再把modal迭代上限不断加大、不把0.1接纳线放宽到0.5，也不原样重跑14.54 h失败路线。新增一个范围明确的候选：**在模态反馈和LDU两侧修正中使用同一固定物理BAL_H作用B，构建并直接求解小型近似模态矩阵S_B，正式求解只保留原Hybrid的外层RIGHT FGMRES。** 它取消反复的side-128步与modal-32步嵌套；是否有效必须由同一0.7 nm问题的原残差、物理量、总时间验证，不能提前写PASS。

```text
repository              = Rookie1234567/MyFEniCS
branch                  = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date             = 2026-10-11, Asia/Singapore
reviewed_HEAD           = 3e6c5d6f33c523225619f09c52192acf99f47489
latest_commit           = docs: record Task041 V12 warm terminal result
latest_commit_time      = 2026-10-11T00:50:04Z
reviewed_code_commit    = eca72c8b12e2b979f919cb5b69578ad99111fef0
previous_review         = review_report_v12.md
reviewed_response       = response_v14.md
latest_Invocation       = 62c3763e266345e0b094a4f3ba3ae19c
new_candidate_name      = task041_v13_consistent_fixed_balh_modal_surrogate
response_required       = response_v15.md
primary_case            = W0.7 / 10x5 nm / p6 h0.70 / M400 / MPI8x1
W5_weak_channel         = DEFERRED_BY_USER; historical comparison FAIL retained
swap_policy             = observe_only
master_merge            = NOT_APPROVED
```

本轮消除“每次原外层都支付大量侧区迭代，且辅助模态求解仍会终止全场”的blocker。最终目标保持0.7 nm、50×25 nm目标单胞、约2 TB整机物理内存及系统余量、48 h从QEP至清理的完整计算；Hybrid只适合内部可模态传播的结构，不代表任意非可分三维Full3D已通过。

本报告为最新已回应V12后的新review，不修改旧报告。只在上述注册pilot显式授权固定B、近似S_B物化与小型LU；**覆盖旧“任何模态矩阵一概不得物化”和本新候选必须运行side/modal内层KSP的解释**，不授权准确D逆逐列Schur、全局p6直接分解、扩容、删模式或放宽最终精度。新数值核心进入src，沿现有runner接线；原V12/W5/ordinary默认不变。用户已授权本轮实现与连续验证；主控内部审核保留，不再把每个正常阶段送回用户等待相同批准。

## 1. 已读证据与结论边界

已核对任务目录、最新response/outcome/summary、V12、task及适用规则；根AGENTS、docs规则、repository_work_principles与task保持已读同blob版本，任务目录未列独立补充任务书。eca72c8至当前HEAD只增加文档，不能把文档HEAD误称新的数学优化。关键固定证据见§10。

| 事项 | 最新事实 | 裁决 |
|---|---|---|
| V12实际运行 | 14.5433947 h，outer至11；末条global/bottom/top/modal真残差0.0620431/0.0736481/0.0389836/0.229259 | 确有计算；没有合格原方程解，不是只等dispatch |
| 末次modal | solve累计13；32步，reason -3；eta=0.47290220837766356，solver/total作用32/33；trusted iterate=true，输入未污染，budget_exhausted=false | 是当前辅助问题在既定方法/工作量下未解好；不等于物理方程无解，也不能归为callback bug |
| 策略 | H6→fixed physical BAL_H实际切换一次，共用原side因子 | 允许近似返回与备选已经试过，不能再将其作为尚未实现的解法 |
| 资源 | tree RSS峰53,504,184,320 B；job-cgroup峰51,665,588,224 B；hard85,899,345,920 B | 本场非容量停止，两个peak不相加；尚不证明整场及目标规模容量 |
| side64 | 两侧armed，capture_armed=false，pending=false，trial_count=0 | 未执行，不是验证失败或容量拒绝；不能声称restart64无效 |
| 快照 | ordinal1成功、ordinal4未达目标各有800维g/m/raw；末次ordinal13向量没有保存 | 现有文件能支持部分分析，不能离线恢复末次失败RHS；终态保存仍须补最小缺口 |
| finalizer | 7/12；5项false含结果/正常退出、两项成员检查、policy检查 | 资源/数值/收尾原因分开；policy false来自public summary缺嵌套字段，不证明实际方法错配 |
| W5 | 16.643 h自身五残差/物理通过；一个弱显著通道同离散比较失败 | 保留提速事实和限定；按用户决定本轮不修、不重跑、不作0.7前置 |

summary首页仍突出10月10日旧V11终态，V12终态附在后面；先将“当前结果”移到顶部，历史保留。Response V14前部的“尚未dispatch”只能标成准备快照，不能与10月11日终态并列为当前状态。

### 1.1 这次为什么仍没有合格结果

**数学/性能层：** 便宜H6反馈与较贵固定BAL_H反馈，都没有证明能让当前嵌套方式经济收敛。原side的128步近似求解此前已显示短波长困难；V12最新全量side工作和分段wall需从现有日志提取，不能沿用V11的每条残差冒充V12实测。14.54 h/11是含setup与失败工作的摊销观察，不是纯outer单步时间，不据此发布线性ETA。

**控制层：** 源码中side64候选捕获要求backup已激活、backup次数为1、outer停滞已确认且capture_armed。于是它不能作为backup之前的主动诊断，且可能在满足条件前已因modal拒绝退出。当前证据不证明某个触发分支写错；证明的是“登记了备选”没有变成“实际做了对照”。新主候选不再依赖这套side64状态机，也不为补它单独运行一场旧嵌套PDE。

**工程层：** finalizer读错证据层级、首个未达目标用完快照配额、异常标签混淆trusted iterate，以及进程收尾检查都是应修问题；它们没有造成0.4729的模态残差。先用既有文件/小fixture修复，不以“修finalizer”为理由重算电磁问题。

## 2. 本轮算法：用一致的固定作用，代替两个反复迭代的内层

### 2.1 原方程不变

把两侧场合写为u_s，模态未知量为a。以下符号吸收现有traction/projection的正负号；实现必须对照原全局MatMult，不能只按符号名称接线。

```math
\mathcal A\begin{bmatrix}u_s\\a\end{bmatrix}
=\begin{bmatrix}D&G\\L&C\end{bmatrix}\begin{bmatrix}u_s\\a\end{bmatrix}
=\begin{bmatrix}f_s\\f_m\end{bmatrix},\qquad D=\operatorname{diag}(D_b,D_t).
```

现有流程的侧区初次/修正响应调用容差停止的SideBalancedInverse.apply，而模态反馈内部使用H6或一次固定BAL_H：两个位置不是同一个固定线性逆。FGMRES允许这种不精确/可变PC，不表示这种组合一定高效。[S1]

### 2.2 复用已经实现的固定物理BAL_H

```math
B_s=J_s\left[Q_s+(I-Q_sA_{6,s})H_{6,s}(I-A_{6,s}Q_s)\right]J_s^H,
\qquad B=\operatorname{diag}(B_b,B_t).
```

复用`FixedPhysicalBalancedActiveTraceAction`及其借用的p4因子、A6、H6、P/PH和trace映射。每Q仍请求一次固定同因子数学精化，原A4物理/增广残差<=1e-10，exact-zero按实际审计处理；不把普通自适应5e-13/max2调用偷偷放进固定B，不修改owner的普通side设置。B不是准确D逆，也不要求一次B作用达到原side迭代的1%目标；这是明确的新PC作用合同，而非将side未收敛改成PASS。

### 2.3 形成的是小型近似模态矩阵，不是旧准确Schur

```math
S_B=C-LBG=C-L_bB_bG_b-L_tB_tG_t.
```

当前M400对应n_m=800。每列用一次固定B_b和一次固定B_t生成，仅保留投影后的800维结果。禁止调用`SideBalancedInverse.solve/apply`去构造这些列；禁止先形成全FE×800响应矩阵。两侧底层因子仍有且仅有现存两份p4；新增的是模态owner的一份小型S_B LU，不是p6全局因子。

| 构造方式 | 每侧每列的工作 | 本轮含义 |
|---|---|---|
| 旧逐列Schur | 一个D_s逆响应，包含多步BAL_H侧区FGMRES | 仍禁止重启这条长流程 |
| 本轮S_B | 一次固定BAL_H作用B_s | 允许的近似PC构造，不声称S_B等于准确Schur |

M400的S_B单数组payload为800²×16=10,240,000 B（约9.77 MiB）；矩阵、LU、复制和求解scratch分别计量，owner新增模态存储设256 MiB预算，仍服从总cap。800列共1600次B作用；现有固定B每侧每次含2Q/2A6/1H6，每Q最多2次实际p4回代，因此列构造最多6400次p4回代，setup检查另记。这是源码推导工作上限，不是实测时间或RSS保证。

先计算预先固定、覆盖正负方向的8列并计时，直接存入最终矩阵，不作为用完即弃的probe。以实测每列成本和进展持续核对全部构造成本；若其规划已明显吞噬48 h完整预算，保存已测阶段与具体工作量，不盲目建立全部800列。该矩阵必须逐列/有界小batch流式生成，FE临时向量数量不随800增长。

S_B采用带主元LU；必要时仅允许等价行列尺度变换，必须反变换回原坐标。独立检查矩阵作用与原固定反馈action一致，非零RHS的原S_B相对残差<=1e-10。奇异、非有限或可靠求解失败不允许伪逆、任意对角shift、删模态或提高阈值掩盖；它们是该PC候选的可定位负结果。无需手写GMRES或替换PETSc主求解器。[S2–S3]

### 2.4 LDU所有位置使用同一个B：本轮的关键

每次PC收到r=(r_s,r_m)，按下式执行：

```math
y=Br_s,\qquad g=r_m-Ly,\qquad S_Ba=g,\qquad z_s=y-BGa,\qquad z_m=a.
```

外层依旧在原A与f上运行RIGHT FGMRES。新路线不调用side128步FGMRES、不调用modal32步GMRES，也不触发V12 H6→BAL_H/side64状态机；必要原A、A4与输出检查保留。

这不是只把原modal solve换成LU、却在两侧保留另一个不一致的非线性逆。相同固定B产生一个可直接检验的代数性质：

```math
Lz_s+Cz_m=Ly+(C-LBG)a=r_m.
```

即PC的模态行可以在小型求解精度内闭合，剩余难度主要留在原D与B的匹配。用原全局算子的modal块验证此性质，而非只用同一构造函数自证。若实际代码符号不同，推导并实现对应恒等式，不用调符号“拟合”结果。

**代价和风险：** B可能仍不足以有效近似D逆，外层步数可能增加、停滞；S_B也可能病态。精确求解一个近似模态矩阵不等于原问题精确。因此本轮追求的是“setup+全部外层+恢复”的净收益，不承诺十倍或48 h。若PC一致性通过而原D相关残差停滞，就得到明确的侧区预条件不足证据，不继续用放宽modal门来应付。

## 3. 执行顺序：一条候选、一份因子生命周期、尽早取得原方程结果

### P0：只读收口旧运行，薄修证据链

现场核对当前branch/HEAD/upstream/dirty、unit/Invocation/PID/starttime与runroot；远端最新终态不代表工作站实时状态。健康授权作业继续，不为新review中止或热改。先从V12现有markers/side audit提取：非重叠setup/outer/cleanup时间、全部side次数/步数、各方法modal次数和作用、p4回代/精化。缺字段写not_persisted，不重算补历史。

finalizer应从由manifest绑定的consumer summary读取实际policy/方法历史，而非要求public顶层存在它没有传出的嵌套结构；没有证据仍写unknown/失败，不能只凭请求字符串判匹配。用现有失败文件离线复核和一个错配负例完成修复，不为新exit0重跑PDE。原成员检查失败保留，下一次让公共父进程join其已知子进程后再检查；只处理本Invocation进程，不使用pkill或误杀邻任务。

快照改为一个成功控制、一个首次异常和一个终态槽；正常KSP返回且策略拒绝时先保存可信m/g/raw，再抛出结果异常，terminal不受first-unmet配额限制。保存最大3份小模态NPZ；不新造通用捕获系统。原场x只在安全边界按既有分布式packet保存，缺失旧向量不能事后补造。

### P1：最小数学与实际入口验证

用现成block-LDU、fixed-Q和MPI2 fixture验证：小型复数非HermitianD/G/L/C，故意令B不等于D逆；验证S_B列/action一致、PC模态行恒等式、复线性、非零/精确零、原A外层收敛、输入不变及borrowed factor生命周期。加入奇异S_B、错误通道次序/符号的负例。tiny真FE/MPI2沿现有matched-cell构造验证一次新组合，不重跑整场13.5/W5、symbolic桥或QEP资格。

正式入口只增一个新profile/selector，沿现有参数对象贯通public→worker→factory→finalizer；互斥旧V12 policy，不能同时请求两套方法。producer/source/material/mesh/M不变，PC改变只更新数值方法身份，不伪造producer provenance。用真实candidate helper到工厂的轻量测试覆盖选择，不只检查argv字符串。普通数学默认不改。

### P2：一次真实W0.7构造后连续求解

固定当前W、0.7 nm、10×5 nm、z=-2..26、接口2/22、p6/h0.70/M400/MPI8、matched L20/N29/h20/29；沿PORD、compact transfer和identity-sharing，复用合格producer packet。延迟分解桥与阶段预算已能在此矩阵工作，不再从小API证明开始。

两侧p4完成后建立固定B与S_B；先用已有成功/未达modal快照作可选同身份对照，布局不能证明时直接使用当前真实输入，不让跨运行映射变成新前置。新PC代数门通过后立即进入原全场FGMRES，不在“矩阵已形成”处退出。

初始outer restart32，max_it保持原上限，不从零重复运行不同参数。记录第1/4/8/16/32步及后续restart边界的原全局和三块真残差，保留原f与分块分母；额外原A作用计入wall。第一个32步窗口若清楚显示重启丢失进展，允许在安全边界**一次**改outer restart64并启用本机支持的MGS；按真实V/Z尺寸检查新增内存，保留当前x、非零初值、原f及累计账。这只是同一候选的有界Krylov存储调整，不重新启动side64、改p4或增加第二套PC。

原残差有效下降且资源安全则继续至全场、恢复、完整E/H、R/T/A/A_volume及全部衍射；48 h是目标不是时钟一到强杀。如果经过至少一个完整outer窗口及上述必要的一次调整后，连续两个16步窗口的最佳global和未通过分块残差各改善不足10%，则在安全边界保存当前x/残差与实际工作量并收口为PC成本/收敛负结果。此为预定进展判断，不是收敛定理；单次残差尖峰不自动停止。不得放任数千步、几天长跑仅等待随机改善。

本轮最多一场主warm以及一场明确实现错误修正后的必要重试；不同参数值不各自重建。代数或进展负结果不自动重试。若新候选已数学正确却仍不够强，交出D-B作用、模态行误差和成本数据，下一步再设计针对性coarse-space改进，而不是本轮加十个PC。

## 4. 数值与资源验收

| 层级 | 必须保留的标准 |
|---|---|
| 固定B中的p4 | 原physical/augmented A4相对残差<=1e-10；每Q一次固定数学精化，exact-zero有证据；普通owner的5e-13/max2设置不被改写 |
| 新近似块 | 独立action-vs-stored S_B、复线性/重复相对差<=1e-10；非零modal RHS原S_B求解相对残差<=1e-10；零分支独立处理 |
| 小fixture PC模态行 | 对原块作用的非零r_m用相对1e-10；r_m=0时按原各组成项尺度报告绝对后向误差，禁止max(norm,1)掩盖缩放 |
| 正式原方程 | reported/global/bottom/top/modal五项各<=5e-9；KSP reason与独立真残差同时核对 |
| 物理/恢复 | traction及projection<=1e-8，external-q<=1e-10；能量闭合及A-A_volume各<=1e-5；复E/H、完整外部keys、复振幅/功率、canonical、法向通量与身份全部检查 |
| 内存 | hard80 GiB=85,899,345,920 B；warning72 GiB=77,309,411,328 B；阶段W8 GiB；node0 floor384 GiB=412,316,860,416 B，均不变 |

新PC是研究候选；只有最终原方程和物理门通过才生成official结果。pilot的own pass不等于h/M收敛；W5延期项不写PASS，也不阻塞当前独立pilot。

全树RSS与专属cgroup峰分列；冻结总cap，按当前新增需求检查下一阶段，不重复扣本job已占内存。不在同一进程常驻全FE×mode矩阵；不得通过低精度、BLR、OOC、隐藏精确p6因子或删通道换结果。继续release-before-recovery，保存最小必要恢复包后释放KSP/PC/因子再恢复。

swap继续仅观测，不单独否决或触发停止；不得将换出导致的RSS下降记为算法省内存。host/node0、父cgroup、磁盘、硬件告警、ABI、非有限和原算子错误仍为真实保护。默认已冻结的socket0/node0物理核map、MPI8×1，六线程变量含BLIS=1；一次一个heavy，不启用node1、不改BIOS、不拆DIMM、不触碰邻项目。

## 5. 从pilot推进到50×25 nm、2 TB和48 h

本轮首要交付仍是**一个真实0.7 nm完整离散解及完整成本**，不是只做出S_B矩阵。第一场成功后，在同几何上先以相邻M（400→600，若预算允许）检查模式截断，再以相邻h0.70→0.525检查网格；每场独立.dat，不做h×M全组合扫描。matched策略的N必须从L/h实际生成，不硬套29。材料/geometry/external keys不变项严格绑定。相邻比较沿原task Mandatory门：RTA/体吸收差1e-4、显著级幅度/功率1e-3、E 5e-3、H 1e-2；未通过就保留best available discrete reference，不称准确性已完成。

放大前分别估计两侧网格与p4填充、QEP/TOAR workspace、mode/trace/G/L/DtN驻留、B单次成本、小模态矩阵与LU、Krylov、恢复；每项标measured/derived/predicted及依据。不得把10×5小模型的约53.5GB乘一个倍率当目标容量。M不是external channel数，也不能无证据按面积放大25倍。0.7 nm目标与pilot的既有派生external清单要分别由各自resolved输入实际绑定。

**本轮显式S_B首先限于M400，条件性M600资格后才扩大。** 它存储O(M²)、稠密分解O(M³)、构建O(M·cost(B))，不自动成为任意大M的生产方案。较大目标若小模态LU或列构造超预算，应依据已测谱/列成本，转为有界模态粗空间或压缩/迭代作用；这是下一阶段的明确容量问题，不静默建成巨大owner coarse factor。当前2TB目标也不能建立在未资格node1可用的假设上。

完整时间分别报告：实际fresh QEP→cleanup、warm consumer、复用producer实测时间加warm的组合估计、研发累计失败费用。没有原producer完整wall就标unknown，不让QEP=0的warm成绩冒充48 h冷启动通过。用户终极目标的任意非可分3D仍须Full3D的matrix-free/可扩展PC路径，Hybrid成果不替代该资格。

## 6. 防止工程工作再次吞掉整轮

15次pytest的184.676 s不是14.54 h失败运行的原因；本轮不应再用“测试多、接口多”解释数值成本。只修受影响helper/工厂/字段并重测对应节点；明确的dtype、missing-key、fixture、exact-zero计数或路径错误由Codex保留attempt后自行修复继续。相同根因两次出现先小fixture解决，禁止第三次支付大型setup。已有同数学源码/同ABI的有效Gate可复用，不因普通文档提交重算。

新代码需覆盖真实入口到底层PC，而不是再写多层重复registry。非数值文档/计费派生修正不能要求新PDE；原始run不回写，数值停止与收尾bug分栏。失败的terminal向量须在可信时保存，主root、首因、cleanup分别记录。

不启动W5 polish、不另跑W2绕开0.7瓶颈、不扫描ILU/GPU/神经网络/新硬件配置。若新增候选需要超出本报告的独立架构重写，先交已完成的实际数据和差额，不借此扩成无界项目。最终实现/测试/运行分别普通commit，主控内部审核通过就连续执行，用户不必逐个小步骤再批准。

## 7. 交付与提交

提交`response_v15.md`、中心`outcomes/w0p7_consistent_block_pc_v13.md`及一个轻量record，并同步summary首页、test_summary、development_progress、development_model_registry。已有大日志/矩阵/场留ignored results；只新增必要NPZ/矩阵文件索引与hash，不建新的账本体系。

顶部必须直接回答：这轮实际运行了吗；当前unit/Invocation/source和唯一runroot是什么；S_B是否构建/通过，是否还调用side/modal KSP；setup/B构造/outer/恢复各用多久；原残差下降多少；最终E/H/RTA有没有；48 h与目标尺寸/精度/内存各通过了什么。

记录B/Q/A6/H6/P4全量工作，small-modal矩阵/因子次数与bytes，原side KSP、modal KSP在新路线应为0的实际调用断言（必要独立诊断另scope）；没有隐藏回退。每个阶段开始、终态和明确阻塞推轻量结果，长阶段沿现有日志至少每小时更新，不只推代码。首个可信解/终态残差packet优先保全；没有成功也须交出可定位的原PC性能/收敛负结果，而不是再次只有“内部失败且末向量未保存”。

仅原Task041分支；不amend/force-push/覆盖stash/merge master。开始及提交前核对远端竞态，保留新推成果。ChatGPT本次仅新增review，实际实现与运行由Codex完成，不能预填通过状态。

## 8. 总裁决

V12：`FAIL_TO_COMPLETE_W0P7_WITH_MEASURED_PROGRESS`；保留14.54 h与11步正确信息、原失败及收尾问题。当前资源不足不是停止原因。

V13：`APPROVED_RESEARCH_EXECUTION_WITH_GATES`。首先减少嵌套总工作，并通过一致B/S_B获得可验证的模态行闭合；原D与B的匹配仍可能是剩余瓶颈。若本候选失败，必须承认现有p4/BAL_H的短波长有效性尚不足，而不是继续放宽门限或宣布0.7 nm本身不可计算。

## 9. 本轮最小commit序列

1. 现有V12终态的离线证据/薄收尾修复与定向测试，不动数学结果。
2. 固定B一致block-LDU＋有界S_B生成/小型LU的src实现及复数/FE/MPI2、实际入口测试。
3. clean源码下一场W0.7 main run；结果、计时、资源、残差与恢复工件索引。
4. 条件性M/h资格或具体PC负结果、完整Response V15及总账。

中间普通文档更新不重置运行，也不把一次数值修改拆成十套独立runner。健康作业、有效packet与已保存解不得为“重新计时”删除重算。

## 10. 固定证据与技术依据

- [R1：Response V14，含10月11日终态](https://github.com/Rookie1234567/MyFEniCS/blob/3e6c5d6f33c523225619f09c52192acf99f47489/docs/task041_mpi1_shortwave_hybrid_capacity/response_v14.md)。最新运行/截图与准备态必须分开；ignored terminal compact SHA `77a5ab816d9d48103f8a31c6e9e2c8a50fef2a70e1606beac3919185169b04f5`。
- [R2：V12 outcome](https://github.com/Rookie1234567/MyFEniCS/blob/3e6c5d6f33c523225619f09c52192acf99f47489/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/w0p7_inexact_pc_progress_v12.md)。
- [R3：当前block-LDU源码](https://github.com/Rookie1234567/MyFEniCS/blob/3e6c5d6f33c523225619f09c52192acf99f47489/src/solvers/hybrid_fem_modal_block_ldu.py)：初始/修正各两侧apply、模态独立solve及V12状态机。
- [R4：固定BAL_H与side源码](https://github.com/Rookie1234567/MyFEniCS/blob/3e6c5d6f33c523225619f09c52192acf99f47489/src/solvers/physical_balanced_side_inverse.py)：固定Q、借用关系及side64捕获条件。
- [R5：service边界](https://github.com/Rookie1234567/MyFEniCS/blob/3e6c5d6f33c523225619f09c52192acf99f47489/src/runners/task041_service.py)与原Review V12、task；旧合同仅按本报告明确范围覆盖。
- [S1：PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：允许非线性/不精确PC，不保证任意PC收敛。
- [S2：PETSc PCFIELDSPLIT](https://petsc.org/release/manualpages/PC/PCFIELDSPLIT/)：block-LDU分解结构。本文推导需按本项目G/L符号验证，不要求移植整个PCFIELDSPLIT。
- [S3：PETSc PCFieldSplitSetSchurPre](https://petsc.org/release/manualpages/PC/PCFieldSplitSetSchurPre/)：区分显式近似Schur与代价高的准确Schur。资料仅支持方法结构，不证明Task041性能；运行保留已安装ABI，不能因在线文档版本较新而升级软件栈。
