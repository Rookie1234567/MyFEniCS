# Task39extra Review V19：p6/p4双层单元凝聚与保留BAL_H的真实模型验证

## 0. 审阅决定、身份与权限

**接受V18准确p4单元凝聚的固定original完整通过和p4控制内存收益；凝聚BLR没有额外价值，不继续扫描。新批只检验一个变化：把p6外层未知量也改为单元凝聚后的独立trace＋原端口，在这个较小空间上迭代；p4仍使用已验证的准确凝聚LU。不是把p6的Schur矩阵再整体LU，也不是重新设计42宏块或谱粗空间。**

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task39extra
review_date                = 2026-09-14
reviewed_base_SHA          = bcb641bf7bc0cac739f576c5073f48eb1eb30709
latest_commit             = Close V18 with original p6 pass and user-stopped notch evidence
previous_review/response  = review_report_v18.md / response_v19.md
accepted_U2_source        = e1b5a398a199cdbc7c26ce3af8645daed2eeb7d6
accepted_original_source  = 8a2d5cbba6ed834a6d731a30dd3735c8824fa762
interrupted_notch_source  = c56437271a4e3c34c984e4c3dee111b61dc5130e
new_batch_identity        = review_v19_p6_p4_cell_condensed
suggested_profile         = physical_p6_trace_p4_condensed_balh_v19
execution                 = X0 -> X1 -> X2(original only) -> X3
response_required         = response_v20.md
time_policy               = observe_only
ordinary_default          = unchanged
master_merge              = NOT_APPROVED
```

本批解决的blocker是：**在保留已有效的p4全局物理纠错时，p6完整空间迭代的向量、正交化和单元内部工作能否进一步降低？** p6原方程、材料、离散、外部通道不改变。目标仍是0.7 nm、任意非可分三维周期单胞、约2 TB整机内存；本批只是13.5 nm固定模型上的架构对照，仍有增长型p4全局trace因子，不构成最终可扩展生产资格。

用户本轮明确要求试验双层凝聚并写任务，因此授权新profile的一次完整original；V18已关闭的notch不恢复、不重跑，**本批也不自动新开notch**，其最终资格保持未取得。新方法original完成后统一审阅再决定非可分验证与规模扩展。不运行5 nm/0.7 nm、不影响Task41及并行工作站线、不新增分支、不合并master。旧review、profile、负结果、账本和用户停止记录不改写。

## 1. 最新结果审阅与应当修改的认识

证据入口：[Response V19](response_v19.md)、[V18中心结果](outcomes/p4_cell_condensed_v18.md)、[决策](outcomes/records/p4_cell_condensed_v18_decision.json)、[compact](outcomes/records/p4_cell_condensed_v18_compact.json)。下表是远程记录，不是本review新运行；GB为十进制，RSS为同时process-tree采样峰值。

| 对象及范围 | measured结果 | 审阅结论 |
|---|---|---|
| 原p4全局LU对照 | RSS 2,825,973,760 B | 仅p4控制的旧分母，不是完整p6峰值 |
| V18准确单元凝聚p4 | RSS 1,785,585,664 B；21824行全局因子；12类局部LU | 同scope控制RSS下降36.8152%（derived）；原A4最大残差7.52867e-11，场/旋度约5.2e-12 |
| 新p4局部数据 | 局部LU/恢复/RHS缓存11,327,040 B，其中LU 2,244,672 B（对象载荷） | 不是42/252份MUMPS；载荷不等于独立RSS |
| 凝聚BLR tau=1e-5 | RSS 1,810,874,368 B；条目减2.3564% | 质量通过，但RSS增加1.4163%（derived）；关闭此附加优化 |
| V18 original完整p6 | 564步；原A6残差9.92314718715201e-7；RSS 2,528,460,800 B | 完整数值/物理/资源已通过；保留作新original的主要对照 |
| original场与功率 | L2=1.3644783293e-8，scaled-curl=4.3714257233e-9；R/T/A/A_volume=0.365625790969/0.0129906323212/0.621383576710/0.621383574597 | 同离散参考、80模式、复E/H与守恒通过，不是网格收敛证明 |
| original时间 | monotonic全流程6609.661379 s，保守结算7210.314085 s | 约110.16/120.17分钟；不同时间口径不混用；仍为564步，未证明迭代加速 |
| V18 notch | 完成494步；最后explicit残差第488步5.47830720755e-6；第480步场误差8.36579e-8 | 父监控丢失、用户关闭续算；不是最终PASS，也不是已证实的数值不收敛 |

本轮审阅状态为`PASS_WITH_QUALIFICATIONS_FOR_V18_ORIGINAL_ONLY`；这不批准合并。接受旧notch停止，不为填表追加其计算。旧计时错误与父丢失的全部失败、未知字段保留。

### 1.1 p6并不是先装配完整稀疏矩阵

当前`src/solvers/fullspace_physical_action.py`明确采用split volume＋dynamic DtN的matrix-free action，`global_aij_materialized=false`。V18 runner只替换p4 inverse，p6仍为full-space向量上的matrix-free求解。**full-space指未知量空间，matrix-free指算子存储方式；二者不是反义词。** 不得把当前2.528 GB说成主要用于存储一张并不存在的完整p6 AIJ。

新方法改变外层未知量和Krylov空间，而非简单“删除旧p6矩阵”。新增p6局部消元／恢复缓存也要付费；总内存和迭代次数可能降低，也可能不降低。历史p6直接法从35.024到16.998 GiB的降幅，不能迁移到这条已经matrix-free的迭代路径。

### 1.2 本批需处理的实际工程事项

| 项目 | 必须做的最小处理 | 不做的事情 |
|---|---|---|
| 服务方式仅有ABI/help资格 | 在X0做一次很小的非PDE服务生存/退出测试，确认调用会话返回后案例监督可独立完成、日志可回读、子进程可清理 | 不恢复旧notch，不开发新调度平台，不声称help成功等于真实长程资格 |
| 两个曾阻止original的时间检查 | 新profile全链路保留observe_only；定向验证配置、PC记录及cleanup | 不恢复600秒、25/30秒或总wall veto |
| 凝聚会改变残差的空间和归一化 | 保存新Schur残差、恢复后的原A6残差及端口闭合；以原方程裁决 | 不直接把Schur相对残差1e-6当原A6达到1e-6 |
| 两层凝聚与降阶次序 | 采用第4节明确的逆桥；不重定义已通过的A4 | 不直接假定trace限制后的S4是S6的Galerkin粗矩阵 |
| 新缓存/端口组件 | 按degree、材料、几何、方向、积分和算子身份共享，记录真实对象与峰值 | 不用行数下降或峰值相减伪造内存收益 |

## 2. 冻结身份与唯一候选

保持原50×25 nm周期单胞、z=-10…130 nm、Si/air、13.5 nm、1°掠入射、phi=0、s偏振、电幅值1；n_Si=0.999002304859+0.00182649365i、mu_r=1。保持252个轴对齐仿射hex、p6/h10及同网格完整p4、complex128、双Floquet、原积分和80个DtN条目的key/顺序/法向/相位/归一化。物理SHA与模式SHA沿V18：

```text
physical_model_sha256 = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
ordered_mode_sha256   = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
```

环境沿已资格化WSL/Linux、MPI1/线程1、PETSc3.19.6 complex128/int32、DOLFINx/Basix0.10、MUMPS5.6.2；实际路径与版本仍预检，不升级ABI。ordinary/default路径不变，所有新参数落入显式profile/dat/resolved/manifest。

| 层级 | 本批作用 | 因子与存储边界 |
|---|---|---|
| p6外层 | 凝聚后trace＋80端口上的right FGMRES32 | 不构建完整A6或全局S6的LU；不保留完整S6 AIJ/稠密矩阵 |
| p6局部 | 完整单元物理张量的准确内部消元、恢复及局部Schur action | 按类型共享紧凑complex128 LAPACK LU；不创建逐单元MUMPS |
| p6 PC | 第4节的保留空间逆桥，内部使用已有BAL_H/H6 | 一次外层PC只有一次BAL_H；不启动full-space p6内层KSP |
| p4 | V18准确单元凝聚逆，不改变A4=P64^H A6 P64 | 一份21824行左右的准确全局凝聚LU，跨全部调用复用；BLR关闭 |
| 后处理 | 从p6保留解恢复完整p6场，原native流水线评价 | 保留必要factor至本场最终评价结束；不同时新增heap-trim/提前释放优化 |

预计p6独立全空间164592、存储173802；单元内部252×450=113400；独立trace51192＋80端口=51272。p4对应48960/53084、单元内部27216、trace21744＋80=21824。**这些是拓扑计数核对预期，不是硬编码允许省略实际Basix/MPC盘点。** p6的物理解仍完整，内部自由度没有物理删除或降阶。

## 3. p6凝聚算子：保持完整端口与非零内部RHS

### 3.1 先合并单元物理项，沿原端口增广消元

为避免与细层平滑器H6混淆，下文端口矩阵记为B、D、H_p；它们属于p6，H6始终指旧平滑器。原物理问题与等价增广形式为：

```math
A_6=V+BH_p^{-1}D,\qquad A_6x=b_6,\qquad
\mathcal A_6=\begin{bmatrix}V&B\\-D&H_p\end{bmatrix},\qquad
\mathcal A_6\begin{bmatrix}x\\\alpha\end{bmatrix}=\begin{bmatrix}b_6\\0\end{bmatrix}.
```

采用已应用Floquet的独立坐标解释。令i为单元内部、t为独立trace；只消去体积内部块V_ii=diag_K V_ii^(K)，保留所有原端口：

```math
\mathcal A_6=
\begin{bmatrix}
V_{ii}&V_{it}&B_i\\
V_{ti}&V_{tt}&B_t\\
-D_i&-D_t&H_p
\end{bmatrix}.
```

curl和复材料质量项必须先相加成完整V_K再凝聚；不能分别Schur后相加。局部LU不稳定时停下，不加shift、正则化、伪逆或改材料。端口内部支撑B_i/D_i不默认置零，复用V18一般公式；MPC的primal/dual和storage零slave语义不重复应用。

```math
\begin{aligned}
S_V&=V_{tt}-V_{ti}V_{ii}^{-1}V_{it},&
\widehat B&=B_t-V_{ti}V_{ii}^{-1}B_i,\\
\widehat D&=D_t-D_iV_{ii}^{-1}V_{it},&
\widehat H&=H_p+D_iV_{ii}^{-1}B_i,\\
f_t&=b_t-V_{ti}V_{ii}^{-1}b_i,&f_p&=D_iV_{ii}^{-1}b_i,\\
\mathcal S_6&=\begin{bmatrix}S_V&\widehat B\\-\widehat D&\widehat H\end{bmatrix},&
\mathcal S_6\begin{bmatrix}x_t\\\alpha\end{bmatrix}&=\begin{bmatrix}f_t\\f_p\end{bmatrix}.
\end{aligned}
```

H_p是原carrier的端口块，widehat H可能非对角；不得把修正后的80×80块仍按对角处理。Bi/Di及端口源贡献只计一次，不能同时从已凝聚carrier与原carrier重复插入。

### 3.2 p6只保留action，不为减向量反而新增大AIJ

复用`hcurl_assembly_time_condensation.py`的`materialize_global_matrix=False`及局部Schur保留机制（实际接口先核对），顺序生成／共享局部S_K、内部LU、缩减与恢复数据。以trace gather/local multiply/scatter实现S_V；widehat B/D按真实稀疏支撑或streaming action，widehat H只保留小端口块。MatShell/Python仅提供作用，不在完整模型上生成全局S6 CSR、完整V6 CSR或稠密DtN。

现有`assemble_port_condensed_terms`面向AIJ插入；本次应最小抽取其已验证代数，新增action-only carrier出口，不能为了复用该函数临时创建一张51272阶全局矩阵。小fixture可以显式矩阵作oracle，正式根不能。不要复制数千行V14 runner。

p6完整native A6 action仍保留，供PC及最终true residual使用；它本来matrix-free，不等于重复保存全局矩阵。其局部张量与新凝聚缓存是否能安全共享须按身份/所有权核实；临时raw张量与最终Schur/恢复信息不留下无用同义副本。p4与p6不同degree的缓存不能误合并。

### 3.3 完整场恢复与残差关系

对任意保留解y=(x_t,alpha)，恢复：

```math
x_i=V_{ii}^{-1}(b_i-V_{it}x_t-B_i\alpha),\qquad
x=\operatorname{restore}_6(y;b_6).
```

准确局部恢复时，增广残差的内部段为零，其余正是Schur残差。若增广残差为(e_FE,e_p)，原物理残差满足：

```math
b_6-A_6x=e_{\rm FE}-BH_p^{-1}e_p.
```

因此必须独立用原native A6重算，不能用端口／凝聚右端范数稀释原残差。保存内部恢复误差、端口残差及该恒等式，才能区分凝聚误差与Krylov未收敛。

## 4. 唯一PC桥：保留成功的p4作用，不猜trace Galerkin

### 4.1 两层凝聚不能直接截取旧P64

即使A4=P64^H A6 P64成立，通常也不能推出S4=P_t^H S6 P_t。原因是p6和p4的单元内部空间不同，消元使用的内部响应不同；降低阶次和消元一般不交换。直接截trace并复用两个Schur矩阵，是另一个尚未验证的方法，本批不做。

本批用“完整空间近似逆的保留块”来桥接，既不假设上述等式，也不将旧p4准确逆改成新p6-Schur的Galerkin粗矩阵。

### 4.2 先将BAL_H解释为增广问题的近似逆

令旧完整FE空间上的BAL_H作用为$\mathcal B_{6,H}$。它继续使用原H6、P64、两次在线p4准确凝聚求解，不改其数学定义。对于任意增广RHS(r_FE,r_p)，定义：

```math
\begin{aligned}
w&=r_{\rm FE}-BH_p^{-1}r_p,\\
z&=\mathcal B_{6,H}(w),\\
a&=H_p^{-1}(r_p+Dz),\\
\mathcal M_{\rm aug}\begin{bmatrix}r_{\rm FE}\\r_p\end{bmatrix}
&=\begin{bmatrix}z\\a\end{bmatrix}.
\end{aligned}
```

这是原端口增广的块逆组织。若$\mathcal B_{6,H}$替换为精确A6逆，则$\mathcal M_{\rm aug}$就是精确增广逆。这里只使用原H_p的小规模解和B/D action，**没有全局A6逆或额外p6求解**。H_p的可逆性及原符号/归一化按native接口验证，不使用widehat H代替它。

### 4.3 再限制到p6保留未知量

令J从完整独立FE＋端口向量提取(t,alpha)，J^H将保留RHS注入相应位置、在i置零。新外层的唯一PC是：

```math
\boxed{\mathcal M_{\Gamma,6}=J\mathcal M_{\rm aug}J^H.}
```

该定义依据准确块逆恒等式：

```math
\mathcal S_6^{-1}=J\mathcal A_6^{-1}J^H.
```

**这证明接口尺寸与代数桥是合理的，不证明用近似BAL_H替换后一定收敛，也不保证复现564步。** 新外层的最小化空间和残差度量变了，必须真实求解验证。

每次外层PC：将(r_t,r_p)注入完整storage（slave保持零），执行第4.2节的一次BAL_H，再取z的独立trace和a返回。J/J^H仅为坐标提取/注入，不额外施加Floquet C/C^H。物理输出的MPC backsubstitution单独在副本上完成。

内部$\mathcal B_{6,H}$仍为：

```math
\begin{aligned}
g_1&=P_{64}^Hw,&c_1&=F_{4,\rm cell}^{\rm exact}(g_1),&z_c&=P_{64}c_1,\\
s&=H_6(w-A_6z_c),&g_2&=P_{64}^HA_6s,&c_2&=F_{4,\rm cell}^{\rm exact}(g_2),\\
z&=z_c+s-P_{64}c_2.
\end{aligned}
```

F4包含非零内部RHS缩减、一次已建trace全局MatSolve、完整p4内部恢复。一次非零外层PC原则上2次p4全局回代；零RHS快捷返回按实际计数。不能塞入旧I4/C_U/S-p2、42宏块、接口SVD、recycling、MR或新的内层FGMRES。H6自身已有辅助层级不变。全空间scratch允许且计入；所有外层Arnoldi V/Z必须是新trace＋端口长度，不能隐藏一个full-space Krylov basis。

## 5. X0/X1：必要验证合并完成，不重复旧研究

X0先读取本目录task、V18、最新response/summary、适用AGENTS及旧源；核对HEAD/canonical worktree/clean source、ABI、原输入、磁盘/宿主卷、可用内存、swap与排他。当前服务薄入口见`scripts/run_case_in_user_service.sh`。仅做一次非PDE的服务生存及退出小测试，记录unit/MainPID/日志/退出/清场；保留原case watchdog和KillMode整组停止语义。不能把systemd整个用户管理器作为本case树RSS，也不能遗漏case的JIT/MPI/编译子进程。用户systemd不保证宿主重启/注销后仍存活，不自动修改linger或系统设置。

数值实现进入可复用src/solvers；runner做profile/资源/证据编排。优先泛化V18的无全局矩阵单元核、缩减/恢复和端口action接口，不大改p4已合格实现。单一新dat建议`input/task39extra/v19_x2_dual_condensed_original.dat`；服务入口最终仍执行`python scripts/run_case.py <one-case.dat>`，不得脱离公开输入运行未记录的替代求解脚本。

| 必要小检查 | 固定要求 |
|---|---|
| 复数非Hermitian分块oracle | Bi/Di非零、Hp非实、一般非零内部/端口RHS；凝聚、恢复、原残差及J逆恒等式误差<=1e-11（操作尺度） |
| 局部FE与MPC | 真实单元/相邻单元、方向/Floquet、primal/dual；零与非零内部RHS；局部LU/重复/线性/输入不改 |
| 两层非交换防误用 | 小fixture证明直接截trace不能普遍声称S4=Pt^H S6 Pt；测试拒绝错维数/错映射 |
| 端口与算子 | 完整tensor后消元；Bi/Di/Hhat更新、原H_p块逆、无重复端口或phase；伴随小检查 |
| 空间与计数 | 外层V/Z新长度、p4因子1份、A6/S6全局因子0、无内层KSP；每次PC/solve计数与缓存不增长 |
| 运行方式 | observe_only贯穿dispatcher、KSP、PC/checker/清理；服务脱离调用会话后可结束并保存终态 |

不为了证明J逆恒等式分解真实全局A6；仅小矩阵oracle允许。p4已有三个reference/CSR/重复与线性资格尽量复用，无受影响语义时不重跑完整U2/U3。

X1在新original同一正式根内完成p6局部setup和有限作用校验：最多3个预先固定、reference-free的复数保留向量（覆盖trace、port和混合支撑）；比较local-condensed action与native增广action的恢复恒等式，操作尺度<=1e-10；原物理b6/hash核对；一次实际新PC的输入/输出空间及调用计数检查并单列其费用。此时不设“单次PC必须降残差”的Gate。通过后沿同一组对象进入X2，不退出再重复setup、不单独新建参考。

每个阶段先保存可复算小证据再进入下一阶段。matrix-free p6记录local-class tensor/LU/recovery、trace map、端口carrier及operator recipe hashes，而不是虚构S6 CSR hash；p4真实全局矩阵继续流式CSR hash及factor前后不变检查。

## 6. X2：新original完整求解与停止规则

采用right FGMRES、restart32、最多2048个外层步；初始保留未知量y为零。此时恢复的完整场可以含由非零b_i产生的内部特解；这是正确的非齐次消元，不是使用参考或非零猜测，不能误报完整FE系数全零。

**本批不沿用旧full-space第64步rho<=0.10的硬筛选。** 新空间/度量发生变化，64/128步的原A6残差照实报告作比较；本批以最终原方程、非有限/真实breakdown、最大步数、资源与用户停止裁决。不在运行中换PC、tau、restart或增加最大步数。时间全链路observe_only，无隐藏wall timeout；用户可随时停止，终态必须区分用户停止与数学失败。

每8步保存新Schur explicit残差、恢复后的原A6 explicit残差、端口/内部残差、计数与资源；每32步先保存y，再恢复完整场作既有参考评价。每次预计收敛和最终退出前必须重新计算原A6。不能只按KSP的Schur归一化rtol就宣布成功；让同一KSP的convergence callback/停止逻辑以原A6与端口闭合裁决。Schur estimated残差只用于监控；若内部判断收敛但原A6未合格，不隐式创建另一个外层solve或用准确A6补解。

除原残差外，要求端口方程操作尺度闭合：l_p=-D x+H_p alpha（原右端端口为0，故增广残差e_p=-l_p），norm(l_p)/(norm(Dx)+norm(Hp alpha)+tiny)<=1e-8；零尺度使用明确绝对舍入判据，不除零。记录native physical residual恒等式与内部恢复残差的操作尺度<=1e-10。正式模式和功率仍从完整恢复场与原native后处理计算，与保留alpha对照，不从粗层/PC端口数据生成official结果。

| 最终Gate | 沿用或明确补充的要求 |
|---|---|
| 原A6 | full explicit norm(b6-A6x)/norm(b6)<=1e-6；与Schur、递推残差分列 |
| 同离散场 | L2/scaled-curl<=1e-4；参考仅评价，无相位拟合 |
| 复E/H与近场 | 同坐标、同接口与既有U4采样；各既有相对差限1e-4，近零按原绝对尺度 |
| 功率 | R/T/A/A_volume对匹配参考绝对差各<=1e-5 |
| 独立守恒 | abs(R+T+A_volume-1)、abs(A-A_volume)均<=1e-5 |
| 80个模式 | 复幅值向量相对差<=1e-4，逐通道功率最大绝对差<=1e-6，完整key/order/phase |
| provenance与资源 | 输入/源码/物理/模式/对象及数组hash、完整树RSS/PSS/时间、zero swap、终态与后代清场 |

本批只跑此新original，不恢复旧notch、不新增BLR、不重复V18完整original作对照。共用已保存的同离散参考和V18结果；缺失的必要reference必须指出，不能自动新建全局A6 LU。新original成功或失败均进入X3；没有新的备选PC或自动fallback。数值成功不以节省某个人为内存百分比为前提，资源收益单独裁决。

## 7. 内存与时间：先明确可能省什么，再测总量

FGMRES32按33个Arnoldi向量＋32个右预条件方向的示例载荷，有：

```math
65\,(173802-51272)\,16
=127431200\ \mathrm{bytes}\approx121.53\ \mathrm{MiB}.
```

这是使用旧storage长度与新预期长度推导的**向量数值载荷差**，不是measured RSS；实际vector数量/布局按运行统计。若只按独立坐标比较，数字也会不同。它提示不能仅因外层行数下降约70%就声称总内存下降70%。p6局部450阶LU、432阶trace张量和恢复／端口数据可能抵消向量收益；p4全局因子、H6、P64及完整native A6检查对象仍然存在。正交化可能便宜，但每次PC并未自动少掉两次p4或H6，matvec与恢复也新增了工作。

| 比较内容 | 口径 |
|---|---|
| 主要完整基线 | V18 U4 attempt3：2,528,460,800 B、564步、6609.661379 s monotonic；准确运行源码8a2d5cbb… |
| 新original | 新正式根的完整RSS/PSS、实际Krylov大小、local p6/p4缓存、global p4因子、端口与所有临时对象 |
| 同scope限制 | 对齐parent/子树覆盖、cold/warm、因子保留及评价；服务管理器不纳入，case后代不能漏算 |
| 历史p4 36.8% | 仅p4 control收益；不作为新完整p6分母 |
| 计时 | setup/local tensor/Schur、p4 symbolic/numeric、Schur matvec、lift/BAL_H/drop、p4缩减/回代/恢复、原A6检查、正交化、保存/后处理分列；嵌套时间不累加 |

若基线轨迹不足以建立同口径比值，报告`RESOURCE_COMPARISON_INCONCLUSIVE`及新实值，不为补一个比例默认重跑完整基线。给出实际变化量/百分比和采样边界，不能把很小的单场变化称为稳健收益。若内存下降但时间上升，明确是内存—时间取舍；若向量变短但缓存增加使总峰上升，也保留负结果，不调cap来制造成功。

安全沿V18：启动tree cap=min(8 GiB,effective_available-reserve)，reserve=max(4 GiB,15% effective_total)，动态检查不重复扣自身RSS；数值常驻合计<=6 GiB，同时临时池<=1 GiB；job swap与新增global swap均0、无OOC、一次一个heavy。公共缓存不按类型分别给6 GiB；预测/allocated/used/实测RSS分列。p6新local工作集的预审仅用于安全，不代替实测节省判断。

新账本只追加`review_v19_p6_p4_cell_condensed`，引用旧V18最终hash及43200秒政策占用、旧600秒unknown，不返还或混为本场实耗。正常路径一场新original；真实实现bug最多一次有证据的受影响formal重放，旧失败与费用保留。数学未收敛、无内存收益不是bug。再次发生文件系统/监督失联先停止并保存，不能自动扩大基础设施恢复权限。

## 8. 提交、输出与下一步决策

提交顺序：①最小degree通用action/端口/逆桥＋focused tests及真实dispatch；②新original数据及独立checker；③response和汇总。正式运行前clean source；不amend/强推/覆盖旧任务、不更改master。定向测试覆盖所有最终改动，未运行Ruff/full pytest/CI如实注明。局部fixture与服务smoke不能替代完整模型。

必要交付：

```text
response_v20.md
outcomes/dual_cell_condensed_v19.md
outcomes/records/dual_cell_condensed_v19_compact.json
outcomes/records/dual_cell_condensed_v19_decision.json
outcomes/records/run_index.json                 # 增量
outcomes/summary.md / outcomes/test_summary.md  # 保留历史
```

同步development_progress、development_model_registry及selective边界。大矩阵/场/向量/原始轨迹进ignored；compact保留逐8步真残差、逐32步场评价、实际计数和raw hash入口。每个根保存input_original.dat、resolved_config、run_manifest、source/input/physical/mode SHA与run_summary。保持同一准确p4全局factor跨调用、局部缓存不增长；本场最终评价后清理，测同类生命周期而不是叠加另一种释放优化。

| X3结果 | 结论与下一步，均需统一审阅 |
|---|---|
| 原original通过且可信内存/时间收益 | 保留此单一双层凝聚候选；下一轮再决定非可分验证和网格扩展 |
| 原original通过但没有资源收益 | `PASS_NUMERICAL_ONLY_NO_RESOURCE_GAIN`；保留V18为当前较优基线，不继续给新方法叠加组件 |
| 原方程/物理失败 | 报实值及完整曲线；不说Schur类方法不存在，不扫transfer/restart/BLR |
| 安全/执行/参考不足 | 与数值失败分开，保存已完成证据；不为结论好看恢复旧notch |

Response首屏回答：p6是否真正只在保留空间迭代；p4准确作用有没有改变；为何没有假设S4=Pt^H S6 Pt；原A6是否最终合格；与V18比较内存/时间各变化多少、是否同scope；额外局部缓存抵消了多少向量收益；后续采用新路径还是保留V18。**“p6/p4都变小了”或“接口残差很低”不能作为完成结论。**

## 9. 来源与验证边界

仓库事实固定第0节base：V18 review、response_v19、decision/summary；`fullspace_physical_action.py`、`physical_p4_cell_condensed_v18.py`、`p4_cell_condensed_inverse.py`、`hcurl_assembly_time_condensation.py`及现有BAL_H/FGMRES实现；服务薄入口与历史Task035b只用于复用，不等于新完整模型已经通过。

- [DOLFINx 0.10静态凝聚示例](https://docs.fenicsproject.org/dolfinx/v0.10.0.post1/python/demos/demo_static-condensation.html)：单元核内消元的实现思路，示例是弹性，不是Maxwell收敛证明。
- [PETSc虚拟Schur作用](https://petsc.org/main/manualpages/KSP/MatCreateSchurComplement/)：不显式形成全局Schur的接口语义；本任务用准确局部响应，不引入默认迭代内部逆。
- [PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：right flexible预条件框架；允许组合不意味着当前候选收敛已有保证。

第3/4节来自直接复数分块代数。ChatGPT本次用小型非Hermitian、非零Bi/Di/RHS矩阵核查了消元、恢复、物理残差与逆桥，并验证了简单trace Galerkin不普遍成立；这些不是项目FE/ABI或真实PDE测试。Markdown须fenced math、表格/链接检查和本地预览；GitHub rendered view受限时明确记录，不谎称已完成网页视觉核验。本次ChatGPT只新增review，不实现、运行或修复项目代码。
