# Task39extra Review V23：A6/H6真实热点加速与p3/p2准确凝聚粗层对照

## 0. 审阅结论、目标与权限

**接受V24的有界p4精化、优化owner传递及单核h7.5离散求解/物理一致性结果，保留无独立高精度参考的限制。本批在同一分支、同一笔记本上完成两项工作：先单独优化真正被调用的A6/H6，再在同一加速后端下比较准确p4、p3、p2凝聚粗逆。正常最多三场新的完整original p6/h7.5，结束后统一审阅，不逐阶段等待确认。**

```text
repository                  = Rookie1234567/MyFEniCS
branch                      = task39extra
review_date                 = 2026-09-21
reviewed_base_SHA           = aaa767ca50a379c329ed7b565731d8ae33ecbd2e
base_latest_commit          = task39extra: finalize V24 audit and evidence
latest_completed_review     = review_report_v22.md
latest_response             = response_v25.md
baseline_formal_source      = b480178314efdf434c5f7405f2ab356ff9137c17
batch_identity              = review_v23_a6_h6_speed_and_coarse_degree
suggested_new_profile       = physical_p6_trace_coarse_degree_speed_v25
coarse_degrees              = 4, 3, 2; each case has one selected degree
response_required           = response_v26.md
execution                   = S0 -> S1 -> S2 -> S3(Q4) -> S4(Q3) -> S5(Q2) -> S6
environment                 = existing qualified laptop WSL/Linux ABI
formal_MPI                  = 1
formal_threads              = one frozen common setting for Q4/Q3/Q2
ordinary_default            = unchanged
master_merge                = NOT_APPROVED
```

本批针对最终“约2 TB内的0.7 nm任意非可分三维Maxwell”消除两个blocker：**细层算子/平滑器单次成本过高，以及当前准确全局p4因子随规模增长。** 这不是直接开展0.7 nm计算，也不保证p3/p2一定更快或同样容易收敛。

用户要求“所有的都跟用p4时一样”，本报告据此冻结**最终p6物理方程、实际网格、材料、入射、80通道、精度、完整输出与评价口径**；不将其解释为不同粗层必须产生相同PC向量、126步或逐字节相同结果。后面三项恰恰是要实测的变化。不能通过降低最终p、改h、减少通道或放宽容差来实现“省资源”。

用户本轮明确授权在本Task同分支研究q=3/2，因此仅对新profile覆盖旧“只能p4/不得降粗阶”的范围限制；旧失败代码、review、用户授权、profile和checker行为不改。允许保持同一数学作用的局部内核优化，不授权H4递归、p1、粗网格p6、BLR、DD/PML、新restart或其他PC筛选。不运行notch、其他波长，不干预工作站、Task41或正在运行的2 nm任务。

## 1. 本次接受的事实与比较分母

来源：[Response V25](response_v25.md)、[V24 compact](outcomes/records/laptop_speed_v24_compact.json)、[组件记录](outcomes/records/laptop_speed_v24_components.json)、[精化记录](outcomes/records/laptop_speed_v24_a4_repair.json)、[decision](outcomes/records/laptop_speed_v24_decision.json)和[summary](outcomes/summary.md)。GB=10^9 B，GiB=2^30 B。

| V24基线，13.5 nm original p6/h7.5 | 数值 | 口径 |
|---|---:|---|
| 网格/端口 | 9×5×22=990 cells；80 modes | measured；不是720单元，不是7.5 nm波长 |
| 完整workflow | 4579.015917060999 s；76.31693195 min | measured monotonic，主要时间分母 |
| KSP | 3716.1522563079925 s；126步 | measured；29.49327188 s/step |
| RSS/PSS全峰 | 7339319296 / 7307023360 B | continuous process-tree sampled peak；swap0 |
| 原A6最终/释放后残差 | 9.283164961979326e-7 / 同值 | measured，limit 1e-6 |
| p4逻辑/物理回代 | 254 / 255 | 一次额外同因子精化；无内层KSP |
| native A6累计 | 283次；1637.1402389939758 s | inclusive组合计数；须区分PC/诊断角色 |
| native A4核验累计 | 255次；426.09123840702523 s | coarse返回质量检查 |
| p4缩减—回代—恢复 | 230.02264079889574 s | 不等于全部粗修正成本 |
| P/PH累计 | 74.13890026698937 / 65.49211706320057 s | 优化后owner传递 |
| p4 symbolic/numeric | 0.5657629839988658 / 216.7832953909965 s | 后端独立计时 |
| p4 allocated/used | 4687 / 4326 decimal MB | 原生统计，不是RSS |
| JIT与线程 | 11 hit / 0 miss；MPI1/threads1 | 没有2/4线程资格 |

计时父项/子项不得重复相加；H6本轮独立累计和旧完整setup精确边界不能由减法猜出。旧93.0196433分钟仅作历史第二分母，不继续当作最新速度基线。

旧p4异常已复现：rho从2.887066115526587e-10经一次同因子精化降到9.827559370577234e-13。接受`CAUSE_UNRESOLVED_BOUNDED_REPAIR_QUALIFIED`：修复已有效，不为寻找唯一浮点根因重复前缀或重新建立诊断平台；保留实际异常输入作回归fixture。

V24正式采用owner优化，**没有采用packed A6和packed power10**。历史组合探针的setup/apply为206.3725/53.1104 s，baseline为136.5396/52.3144 s；它改变多个组件且受首次回代冷暖影响，既不能作为新内核加速证据，也不能证明所有A6/H6优化都无效。本批必须先逐算子配对，再组合。

## 2. 同一个最终问题：冻结清单

正式输入从[已测V24输入](../../input/task39extra/v24_laptop_speed_original_h7p5.dat)复制物理与离散语义到三个新dat；每个dat仅代表一次明确计算。不得修改旧文件。

| 内容 | Q4/Q3/Q2共同要求 |
|---|---|
| 物理 | 真空波长13.5 nm，1°掠入射、azimuth0、s偏振、幅值1 |
| 几何/材料 | 周期50×25 nm，z=-10…130 nm；original grating 17×25×120 nm；原Si/air、mu_r=1；不挖缺口 |
| Si折射率 | 0.999002304859+0.00182649365i；不得把n误作epsilon |
| 网格 | V21冻结轴计划及990单元拓扑/坐标/材料标签逐项相同，不重新按target生成另一张网格 |
| 最终FE | p6、同Basix变体、Nédélec H(curl)、complex128、双Floquet |
| p6保留系统 | 199260个独立trace+80端口=199340；full storage667152；内部445500；slave22392 |
| 积分/端口 | 原curl、mass及DtN规则，80个key/order/相位/方向/归一化完全相同 |
| 求解 | retained-space right FGMRES32、max2048、零retained初值；同一KSP；内部非零RHS特解按原规则 |
| 预条件组织 | 原增广逆桥、BAL_H结构、一个H6、两次逻辑粗逆；仅粗阶q变化 |
| 精度 | 原A6<=1e-6；每个原Aq逻辑返回<=1e-10；完整物理与同离散回归门槛相同 |
| 生命周期 | 编译前置，共享identity，因子活跃时安全保留矩阵；保存场/最终A6通过后释放，再独立核验和后处理 |

保持同一fine物理RHS storage hash：

```text
b85dde2599428906be4ffd2f2200438f3011e57358d20a541679b3ab50687824
mesh plan: b5bab6aae4668be60aacbb49265b4c875def42e2620256cd168d8c26207dc157
q4 CSR:    857bc8bb5f04b28a55283fb960a2b695e1078983e55ff151687780de5dab8ee0
q4 mapping:bed2794532a40630632e06637cfda5a7bb52a06a7209824d5344085b6fa2cb1d
q4 values: cf081185f6950ebb2c704e0426e02bb0687ef7ae47faf34115d729c8eb832b34
```

q3/q2矩阵、粗RHS和映射的尺寸/hash应当不同，必须新建各自身份，不能硬填p4的SHA。若历史physical hash混有profile字段，保留原schema并另列纯物理、fine离散与执行配置的fieldwise bridge；最终模型不变不等于所有文件hash相同。

## 3. S1：先做A6/H6的独立配对优化

### 3.1 先分清真正耗时的作用，不增加大型profiling平台

用既有低开销计时器添加必要角色标签：A6的volume/DtN/MPC，PC内部A6与独立原A6检查，正定B6作用，H6完整apply，H6对角/power10准备，P/PH，粗层缩减/MatSolve/恢复/native检查，以及KSP正交化/保存/物理评价。分别记录count、inclusive及可获得的exclusive时间；缺失写unknown。

V24的1637 s native A6含不同用途。优先优化BAL_H实际使用的A6，不能把不再出现在计数器中的调用当作成本消失，也不能将仍用旧native路径的验证时间宣称为已加速。p6外层Schur已较快，不用其微优化代替本节。

使用同一990网格的固定、合法、hash-bound向量，覆盖实际PC输入及周期/非零内部分量。固定owner优化、q4准确因子、seed/谱窗及精化策略；先只换A6，再只换B6/H6，最后组合。**算子配对不要求建立粗层因子**；完整PC兼容检查才建立/复用一份q4因子。不得为每个向量、每个内核重新numeric。

每个候选按相同向量/工作量做首调用及最多三次warm重复，交错旧/新顺序，报告全部值及中位数。不把一边冷MatSolve、另一边热MatSolve的组合计时用于内核结论。

### 3.2 A6：减少局部积分计算与搬运，而不是只重新启用旧packed开关

从`fullspace_partial_assembly.py`、`fullspace_mpc_action.py`、`fullspace_physical_action.py`和`physical_equivalent_fast.py`追踪实际回调。允许复用V24的`build_packed_physical_action`作受控比较，但仅再次设置packed=true不构成本批已完成优化。

优先实施一份有界批处理后端：按实际几何/材料/方向/积分身份共享reference表和metrics；预分配小gather/flux/scatter工作区；把可合并的逐cell Python工作移入批量或现有ABI下的编译循环；减少重复方向变换和全长临时数组。不同curl/mass积分规则不能错误合并。DtN保持原streaming物理作用，至少单独计时；允许同值的布局/批处理优化，但不减少通道，不新建全局trace×mode稠密矩阵。

若配对证明主要成本仍来自完整参考表收缩，允许在这一后端上实现**一个共同的张量积sum-factorization内核**，服务于物理A6或正定B6中已识别的主导作用。它把三维基函数求值/导数/投影变成一维连续收缩，不要求三维材料分布可分。必须从实际Basix0.10的N1E变体、分量多项式空间、DoF变换和排列取得或推导相容映射，并与原tabulation验证；不能猜Nédélec排列，不能为得到tensor-product API更换最终FE或升级栈。若该API不支持，记录真实原因；允许基于现有tabulation验证等价局部变换，但不另造有限元平台。

本批不再增加“每类完整882阶稠密A6缓存”并行候选，不形成全局A6/S6/传递矩阵，不用complex64、fast-math、GPU或经验截断。先一个批处理实现，条件一个张量积改进；没有收益就撤出，不无限扫描batch、编译器或融合策略。

独立native A6保留作为最终残差与回归见证，不能同时替换唯一见证并自证相等。新后端接入PC内部，fine Schur/RHS与恢复的数学定义不变。每种独立作用、加总作用和完整PC都验证，不能靠curl与mass两处错误抵消。

### 3.3 H6 apply与setup分开处理

H6的正定算子、Chebyshev次数、power10迭代次数、种子规则和安全系数不改。不增设H4，也不调谱窗改善低粗阶收敛。

先固定同一个对角/谱窗，仅比较B6/H6 apply的新旧实现。然后单独比较setup：将已资格化快速正定作用用于power10；相同局部类型的对角贡献共享，边界/多master仍按精确`diag(C_K^H B_K C_K)`处理，保留交叉项。几何使用已修复的平移消去，保留genuine non-affine拒绝。

比较对角、inverse-sqrt、power history、lambda_lo/hi及H6输出；操作尺度相对差<=1e-10，旧更严检查不放宽。q4/q3/q2使用同一个H6构造规则和同一fine状态；不能因粗空间变小而改变H6质量。若新setup不通过或更慢，只撤回setup优化，不自动撤回已通过的apply优化。

**S1不能只交付新增计时和再次组合一个更慢的packed探针。** 至少对A6与H6分别取得正确性、速度、内存和实际启用路径的判定；可接受有理由的负结果，但不能声称未测/未启用的代码已提速。新快后端没有合格收益时，保留V24已测后端，并继续独立的降粗阶试验。

### 3.4 性能与内存选择

保持原每8步A6、每32步场以及每个粗逻辑返回的native检查，不以降低覆盖率提速。允许同一状态下的已证等价计算复用，记录节省的重复工作，禁止返回陈旧残差。

默认MPI1/单线程，承接用户“不以增加内存换多核速度”的要求。可在S1仅对选定局部核比较2线程；2线程有稳定收益且去重常驻+全部scratch与同scope RSS/PSS均不增加，才条件试4线程。没有支持/安全并发实现则给出具体原因，选单核。MUMPS仍单线程；不并发调用同一PETSc/factor，不用每线程全局长向量、MPI多进程复制或并发`np.add.at`同一输出。

全部Q4/Q3/Q2在正式前冻结同一个后端与线程设置；不得q4单核、q3多核再把收益归因降阶。线程自身的内存中性必须对同q4单核配对证明，不能用q3省出的因子空间掩盖线程增加。总峰值与7339319296 B比较，若更高就不能声称满足本批多核采用条件；这一收益判据不是新的安全kill阈值。边界不清时选单核，正式不暗换。

## 4. S2：准确p3/p2是替换粗空间，不是又增加内层迭代

### 4.1 数学定义与尺寸

对q=4、3、2，分别建立同网格空间Vq和直接相容传递P6q。以下式子在去除slave后的合法物理坐标中理解，具体代码通过已有storage/MPC适配实现：

```math
A_q=P_{6q}^{H}A_6P_{6q},\qquad
C_q=P_{6q}F_qP_{6q}^{H},\qquad F_q\simeq A_q^{-1}.
```

```math
\mathcal{B}_{6,q}=C_q+(I-C_qA_6)H_6(I-A_6C_q),\qquad
\mathcal{M}_{\Gamma,6,q}=J\mathcal{M}_{\mathrm{aug},q}J^H.
```

Fq是**本阶真实物理方程的装配时单元凝聚、一个准确全局LU及完整恢复**，允许第4.4节有界浮点精化。不能把p4 LU裁成小块当p3逆，不能将p3/p2负质量项换成positive Bq，也不通过一个迭代近似内部求解器增加不确定因素。

沿原增广桥，输入FE/端口残差先形成w=r_FE-B_port,6 Hp^-1 r_port，调用本阶BAL_H，再由原Hp及D_port,6恢复端口部分。这里B_port,6/D_port,6是增广端口耦合，不是H6采用的正定B6。原Hp、凝聚后Hhat和粗层端口矩阵不能混用。p6的J、Schur、RHS及最终恢复不随q变化。不能假设S_q=Pt^H S6 Pt；**先在完整相容空间定义粗修正，再用原桥进入保留空间**。

在当前周期拓扑下，独立边E=3060、独立面F=3015。按当前N1E阶次约定，可推导：

```math
N_{\Gamma,q}=qE+2q(q-1)F+80,\qquad
N_{i,q}=990\cdot3q(q-1)^2.
```

| 粗阶q | 局部单元DoF | 凝聚trace+端口行数 | 消去内部DoF | 身份 |
|---|---:|---:|---:|---|
| 4 | 300 | 84680 | 106920 | 全局行数为既有实测锚点 |
| 3 | 144 | 45440 | 35640 | derived拓扑计数，需实际验证 |
| 2 | 54 | 18260 | 5940 | derived拓扑计数，需实际验证 |

这只是待核对的维数，不是RSS或factor大小预测。q3/q2全局行数分别较q4少约46.34%/78.44%，最终内存须计入填充、所有局部数据、H6及工作区。成功比较的是最终p6场，**不要求不同维数的粗修正与原p4向量相等**。

### 4.2 直接传递与原物理一致性

现有局部与owner传递已列有(6,3)，但没有(6,2)。在新opt-in范围增加直接(6,2)并完成同一套Basix插值、方向、梯度/curl相容、P/PH伴随、owner/shared-row及Floquet测试。保留legendre等原FE变体，不用节点值简单插值，不用6→4→2链暗中保留p4空间。

已有全局runtime的PHYSICAL_DEGREES、physical_only_degrees、(6,4)索引和p4-only builder等需要最小参数化。**每场仅构建fine p6和选定q的必要空间/物理作用/传递/因子**；H6依赖fine几何材料而非一个额外p4因子。q3/q2运行不得留下未调用的p4全局矩阵、因子、传递或检查对象来制造假节省/抵消真节省。用对象库存及创建/销毁计数证明。

Aq可独立装配，但须继承p6的物理材料、每项quadrature与完整80通道，并在小FE及本场合并setup上比较native Aq v与P6q^H A6 P6q v，分别检查volume及DtN。不能使用粗阶auto规则减少通道或积分点，也不能每个在线Aq检查都绕回昂贵的p6组合来掩盖缺失的native实现。

### 4.3 所有阶都用装配时单元凝聚

参数化复用`hcurl_assembly_time_condensation.py`、`p4_cell_condensed_inverse.py`与现有端口缩减/恢复。先组成完整单元物理张量，再做一次消元；只装配选定q的独立trace+端口矩阵。内部小LU、RHS缩减/恢复按真实算子类型共享；没有42宏块或逐单元MUMPS。

非零内部RHS、Bi/Di、端口RHS及MPC dual/primal语义必须完整保留。native Aq、约束和返回尺寸均从选定q建立，不能将写着A4的旧字段原样解释为A3/A2。旧类名可通过兼容wrapper保留，但新记录明确`coarse_degree`和原算子身份。

q3/q2各自只作一次symbolic/numeric，后续反复回代。小fixture可以顺序建立同阶full与condensed对照；正式990场不得先构建全量Aq再抽Schur，不新建p6全局direct参考。不对所有候选同时保留factor。

本批q2是**取代p4的单一物理粗层**，不是旧递归任务的8192行/512MiB bottom pilot。仅新profile覆盖这些旧bottom专属准入条件；不能由本批18260行试验全局放宽旧保护，也不将其称为bounded-size最终生产粗空间。

### 4.4 保持已修好的准确返回政策

对每个q都执行native rho_q=norm(gq-Aq cq)/norm(gq)<=1e-10。零RHS沿原直接零分支；非有限、映射或身份错误立即停止，不用精化掩盖错误。

先一次Fq；只在超限时按原g分母，用同一factor对原native残差作最多两次额外缩减—回代—恢复。累计FE及端口状态，对总cq重新应用原native Aq，成功后才交给外层。ICNTL(10)=0，BLR关闭，无hidden refinement、无inner KSP、无新增shift。精化次数可能随q变化，必须计入时间，不硬要求仍然只触发一次。

动态计数：每次BAL_H有两次逻辑粗调用；实际MatSolve=非零逻辑调用数+额外精化数。setup PC、零RHS和原检查单独列出。新checker不得硬编码126/127/254/255、logical3一次精化或固定p4数组尺寸；这些只是历史observed值。

## 5. 连续执行矩阵与停止分流

| 阶段 | 操作 | 完成/分流 |
|---|---|---|
| S0 | 规则、SHA/ABI、V24原始场与hash、资源；补精确计时边界 | 不重跑已关闭p4前缀；明确模型与旧结果限制 |
| S1 | 固定q4下，A6、H6 apply、H6 setup独立配对，条件线程 | 选定一份共同后端；负候选撤出，不无限微调 |
| S2 | q=4/3/2最小参数化、局部FE/传递/凝聚/repair测试 | 先完成全部公用实现，再冻结正式source |
| S3 / Q4 | 共同快后端+准确p4，一场完整990模型 | 与V24比较内核优化的完整影响 |
| S4 / Q3 | 同后端/H6/线程，准确p3，一场完整990模型 | 测最终场、迭代、时间、factor与RSS |
| S5 / Q2 | 同后端/H6/线程，准确p2，一场完整990模型 | 独立于Q3是否收敛；不新增中间层 |
| S6 | 同口径三阶对照、负结果与下一步裁决 | response_v26、推送同分支，统一等审 |

**正常最多三场完整PDE，不为1/2/4线程各跑全场，不另重跑76分钟旧基线。** 三场独立dat/run root/零初值、逐场清场，在同一最终clean source下完成；每场setup检查通过后直接使用同一份factor进入KSP。工程probe和正式运行成本分别记，不把必要setup放到统计外。

若S1所有候选均无收益而共同数学仍是V24，允许明确选回V24后端，复用已测q4完整结果而不重复S3，直接比较Q3/Q2；最终必须写`A6_H6_NO_ADOPTED_SPEEDUP`，不能把降粗阶收益冒称内核提速。若新的后端已改变，不能跳过Q4完整回归。

Q3达到max2048仍不收敛、粗系统不可分解或未省内存，不自动终止Q2；保持公共内核已合格、安全与输入身份成立，清场后继续唯一Q2。不同PC没有简单的单调成功保证。若发现公共A6/H6/传递/物理错误，则先停止受影响路径修复，不让错误传播到下一场。

不设单次PC降残差准入，不用第64/128步残差经验线，不以“比126步多”或“超过76分钟”中止。时间沿`observe_only`，每场max2048保留；数值breakdown、非有限、coarse返回仍不合格、物理/身份问题、真实内存/swap/I/O/监督失败或用户停止才受控退出。慢或资源收益不足不是implementation bug。

仅真实实现bug可沿现有hash-bound机制登记，本批合计最多一次必要正式重放；修正无关文档不重跑PDE，不改旧账本，不自动扩大迭代数、调粗阶以外参数或换后端。完成候选或负结果后继续规定分流，统一收口。

## 6. 所有候选的精度、回归与资源Gate

### 6.1 最终都求原p6解，不把粗解当物理解

| 验证 | 统一要求 |
|---|---|
| 原A6 | 保存完整恢复场后独立norm(b6-A6x)/norm(b6)<=1e-6；释放前后均核验 |
| 每个Aq逻辑返回 | 原gq分母，rho<=1e-10，最多2次额外同factor精化；所有实际计数可重算 |
| 传递/作用/凝聚桥 | 操作尺度等价<=1e-10；保留旧更严伴随/row/线性/repeat约束；端口闭合<=1e-8 |
| 输入/状态 | finite，输入不变，strict slave-zero；最终场必须包含完整内部恢复；缓存不随迭代增长 |
| 与V24保存的同p6场回归 | FE L2/scaled-curl、同坐标E/H、完整复模式向量相对差<=1e-4 |
| 功率回归 | R/T/A/A_volume绝对差<=1e-5；逐模式功率最大绝对差<=1e-6 |
| 物理一致性 | abs(R+T+A_volume-1)<=1e-5、abs(A-A_volume)<=1e-5；80模式求和、归一化、被动性等原Gate |
| 输出 | 相同采样坐标、复数E/H、curl/界面切向量、R/T/A/A_volume、全部80模式复幅值与功率 |

沿用原近零项的绝对例外，不拟合相位、不重新归一化、不对结果平滑。功率仅来自合格DtN端口口径；probe-plane Fourier仍为diagnostic。

每8步保存Schur及恢复后原A6残差，每32步保存场/适用评价，终态完整输出。原A6达标而同离散场回归失败时，明确`SOLVE_PASS_REGRESSION_FAIL`，不能忽略。反过来，p3/p2的粗场或PC方向与p4不同并非失败；只有最终p6解受本表回归要求约束。

基线V24是同离散迭代回归参照，**不是独立高精度authority**。本批全部通过也只授予`DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`及回归资格，不宣称连续精度/5nm/0.7nm/任意几何鲁棒性。旧V23的58/59继续保留。

### 6.2 物理内存与公平生命周期

继承V24的真实物理压力策略：确认实际可用Linux/WSL/宿主RAM及cgroup，使用连续整树watchdog，保持系统实际余量、zero-swap和可写证据；至少保留既有128MiB监督/写盘空间，但不能把这个最小值理解为允许操作系统无余量。一次一个heavy，不触碰其他项目。

不恢复旧6GiB库存/8GiB树上限、固定2倍symbolic或旧3.857GB续算阈值作为唯一拒绝理由。估计只用于对象/批量规划，actual压力停止仍有效；OS OOM不是正常终态。额度、后端allocated/used、数组载荷、RSS/PSS分列。

q4沿已验证MUMPS额度与排序/主元策略。q3/q2使用相同控制规则及不高于q4已验证4687 decimal MB的numeric工作额度，结合现场压力冻结并读回；不因q变小强令原生allocated等于q4，也不启用BLR/OOC/排序扫描。额度不足保存真实结果，不在本批不断增加限额。

不同q每场只保留对应一个全局factor；q4对照对象在q3/q2正式时不得常驻。本场matrix在factor live时仍按后端依赖安全保留，销毁顺序沿V24。新的JIT全部计入所属工程/正式范围；不清缓存制造冷启动，记录首次编译和正式hit/miss。所有阶段同口径，不能以q3仅solve峰值比较q4全过程峰值。

多核增加内存不能称满足用户条件；单核kernel若也增加了工作集，必须如实报告，不用q3 factor减少掩盖q4实现回退。任何配置只有数值有效且资源可接受，才进入保留建议。

## 7. 如何回答“快多少、收敛有没有打折、内存省多少”

采用两个相互独立的比较轴，不只列一张总秒数表：

```math
S_{\mathrm{kernel,full}}=\frac{4579.015917060999}{T_{4,\mathrm{new}}},\qquad
r_n(q)=\frac{n_q}{n_{4,\mathrm{same\ backend}}},\qquad
r_M(q)=\frac{M_q}{M_{4,\mathrm{same\ backend}}}.
```

Q4回答等价内核优化的端到端效果；Q3/Q2相对同后端Q4回答粗空间缩小的代价/收益。若明确复用V24为Q4，则分母固定其对应值并注明跨次运行局限。93.02分钟只作更早历史，不用它夸大本轮收益。

最终表至少包含：q、实际fine/coarse/condensed行数、NNZ、factor条目和allocated/used、local class/缓存/临时bytes、JIT、setup/symbolic/numeric、KSP次数/总时间/每步时间、A6/H6/P/PH/native Aq计数与耗时、逻辑/额外/物理回代、全流程wall和各阶段RSS/PSS、残差与场/模式/功率回归、全部状态。

必须新增精确`setup_end`、`ksp_start/end`、`final_native_check_start/end`和后处理边界，clock固定monotonic；不要再把全流程减KSP的差额当setup，或把final check混入纯KSP峰值。父子区间标注，无法exclusive的保持unknown。

按相同步数列原A6残差，例如8/16/32/64/96/128及各自终点；未到某步留not_applicable，不能补零。同步给出随时间的结论，使“更多步但每步更快”可分辨。迭代比只报告实测，不预设必须<=126；数值通过但更多步属于收敛成本退化，不等于物理解降精度。

最少形成以下裁决：

| 结果 | 应如何归类 |
|---|---|
| 更快且内存不增、最终精度/物理/回归通过 | 该测试范围的性能候选 |
| 内存明显下降但迭代/总时间增加 | 低内存—时间tradeoff，不宣称无损提速 |
| 外层不收敛但原Aq每次都很准 | 本粗空间/组合不足的证据；不是LU精度不足，也不否定所有低粗阶方法 |
| Aq未达到精度或映射/凝聚一致性失败 | coarse实现/数值返回问题；不能先判粗空间物理无效 |
| 组件快、整场不快 | 保留真实开销账，不选局部数字代替整体 |

可同时推荐“实测最快配置”和“合格的最低内存配置”；不强行一个标量排名，也不以缩小矩阵行数替代最终RSS证据。

## 8. 代码组织、检查与提交计划

优先复用而非复制：

```text
src/solvers/fullspace_partial_assembly.py
src/solvers/fullspace_mpc_action.py
src/solvers/fullspace_quadrature_diagonal.py
src/solvers/physical_light_setup.py
src/solvers/physical_equivalent_fast.py
src/solvers/fullspace_same_mesh_hcurl_pmg.py
src/solvers/fullspace_same_mesh_hcurl_pmg_runtime.py
src/solvers/fullspace_physical_intermediate_runtime.py
src/solvers/hcurl_assembly_time_condensation.py
src/solvers/p4_cell_condensed_inverse.py
src/solvers/physical_interface_balanced.py
src/runners/physical_retained_outer_adapter.py
src/runners/physical_p4_cell_condensed_v18.py
src/runners/physical_dual_cell_condensed_lowmem_v20.py
```

用显式`coarse_degree`和后端参数进入resolved config，新dat可命名为`input/task39extra/v25_q4_speed_h7p5.dat`、`v25_q3_speed_h7p5.dat`、`v25_q2_speed_h7p5.dat`。建议新profile v25与Review V23是不同编号系列，名称若冲突选唯一新名称并记录。

禁止为q3/q2各复制整份runner/checker。旧V24 checker的固定127/254/255仅服务旧记录；新通用checker从实际n、setup调用和repair raw records重算，不删除或放宽旧checker。失败先保存已完成向量/计数，正常仅小型scalar/必要checkpoint，避免全量每步向量IO。

正式前一次集中task-focused测试，覆盖复非Hermitian、各q非零内部/端口RHS、直接P6q与伴随/grad/curl、Galerkin、凝聚恢复、精化次数上限/零/异常/端口累计、缓存身份/释放、backend选择及old-default兼容。tiny FE可包含冻结notch材料分布用于正确性，不授权完整notch PDE。检查ABI、compileall、diff和文档；没有运行的CI/全仓测试不声称通过。

提交顺序：S1算子与定向测试；S2粗阶参数化及测试；冻结共同backend/profile/三dat和clean source；S3–S5正式运行；S6结果、总账和selective manifest。运行中不修改源码，不amend/force push，不写master。远端并发变化时非破坏核对，不reset覆盖。

至少提交以下轻量证据：

```text
response_v26.md
outcomes/a6_h6_coarse_degree_v25.md
outcomes/records/a6_h6_coarse_degree_v25_components.json
outcomes/records/a6_h6_coarse_degree_v25_frozen_manifest.json
outcomes/records/a6_h6_coarse_degree_v25_q4.json
outcomes/records/a6_h6_coarse_degree_v25_q3.json
outcomes/records/a6_h6_coarse_degree_v25_q2.json
outcomes/records/a6_h6_coarse_degree_v25_decision.json
outcomes/records/run_index.json
outcomes/summary.md / outcomes/test_summary.md
outcomes/selective_merge_manifest_v25.md
```

q4复用或任何未运行也须有对应轻量记录及理由，不能空缺。大型场、矩阵、factor、局部表、资源日志在ignored并绑定hash。每场保存input_original.dat、resolved_config、run_manifest、run_summary、input/physical/source及artifact SHA；补环境/ABI/线程/绑核/资源/清场。同步`docs/development_progress.md`与`docs/development_model_registry.md`。

继承V24已披露的组件manifest冲突与FE评价wrapper监督偏差，不追溯删除。新组件每场绑定真实clean source或准确base+diff+script hash；新增FE回归评价使用当前合格监督，不为绕过timebase问题静默切回legacy规则。局部文档/评价元数据问题按最短路径修复，不触发整场PDE重跑。

Response第一屏给出旧V24、Q4、Q3、Q2的统一表，明确：A6/H6到底哪一项获得实测加速；q3/q2是否解到相同p6验收精度；步数/每步/总时间变多少；真正省在哪个内存对象；哪些候选不值得采用。完成后推送同一分支并报完整HEAD，统一等待审阅，不自动继续其他阶次/网格/波长或merge。

## 9. 设计依据与本报告自身检查边界

以[task](task.md)、[Review V22](review_report_v22.md)、[用户内存授权V23](user_authorization_v23_physical_memory.md)、根/目录AGENTS和[仓库工作原则](../repository_work_principles.md)为继承依据；本报告明确覆盖处仅作用于新批次。已有结果通过不自动构成本批新算子或粗空间资格。

外部一手资料只支持方法/接口含义，不替代本机ABI验证：

- [PETSc 3.19.6 KSPFGMRES](https://web.cels.anl.gov/projects/petsc/vault/petsc-3.19.6/docs/manualpages/KSP/KSPFGMRES.html)：保留flexible right PC，适用于有界精化引起的有限精度变化，不保证任意粗空间收敛。
- [Basix 0.10 finite_element](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.finite_element.html)：DoF变换、插值和张量积相关接口；特定N1E变体是否可直接使用须实际核验。

ChatGPT本次只新增审阅报告，不实现代码、不启动PDE或修改旧证据。报告本地检查fenced math、表格/链接和小型复数代数；提交后回读核对内容/HEAD。GitHub网页视觉核验若不可达就如实记录，不能冒称已目视通过。上述维数为规则推导，速度/内存改善均留待Codex实际测量。
