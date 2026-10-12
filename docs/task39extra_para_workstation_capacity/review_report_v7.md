# Review V7：暂停大模型，优先完成0.7 nm各向异性网格的准确p4双凝聚验证

## 0. 本轮决定与身份

**暂停530,856-cell的p3大模型及其16步pilot。由Codex只完成对新任务有直接价值的N0端口筛选/输出接线，不要求先算完旧大模型。新优先任务是一场0.7 nm Si光栅完整求解：p6、准确p4凝聚MUMPS修正、BAL_H双凝聚；网格100×2×234=46,800个六面体，x约0.5 nm、y两层各12.5 nm、z不超过0.6 nm。首场保留n=0的全部143个m级次及上下端口/s/p，共572通道，不再截成m=-20…0。**

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task39extra_para_workstation_capacity
review_date                = 2026-10-12 (Asia/Singapore, UTC+8)
reviewed_HEAD              = 4de49260ab5663b57a466760281227ae3bac46e1
latest_commit              = Add N0 port-filter pilot workflow
previous_review            = review_report_v6.md
latest_numbered_response   = response_v6.md
latest_additional_response = response_post_v6_p3.md
latest_target_evidence     = outcomes/n0_port_filter_preparation_20261012.md
batch_id                   = review_v7_urgent_0p7nm_anisotropic_q4_n0
sequence                   = U0 -> U1 -> U2 -> FULL -> OUTPUT_AUDIT -> Z
normal_new_full_PDE        = 1
old_530856_cell_campaign   = PAUSED_BY_USER_PRIORITY
old_16_step_stop           = NOT_APPLICABLE_TO_NEW_FULL_SOLVE
fine_degree / coarse      = 6 / 4
mesh_axis_cell_counts      = [100, 2, 234]
cell_count_limit           = 50000; expected actual 46800
active_modes               = n=0, m=-142..0, top/bottom, s/p; expected 572
formal_MPI / math_threads  = 1 / 1
worker / parent            = CPU24 / CPU9
NUMA                       = interleave nodes0-1, not strict single-node binding
rss_hard_limit_bytes       = 1950000000000
resource_policy            = measured process-tree RSS; PSS/USS off; swap observe-only
response_required          = response_v7.md
ChatGPT_scope              = review only; no code migration, solver execution or process control
Codex_scope                = scoped adaptation, tests, execution, outputs and evidence
master_merge               = NOT_APPROVED
```

本批消除的blocker：全三轴细化及大量无关端口使0.7 nm迟迟没有可分析的完整场；本场利用已知y不变结构，将预算优先用于解析x和z变化，验证现有准确p4双凝聚能否给出数值自洽且物理上合理的0.7 nm结果。它是结构特定的紧急验证，不是任意非可分三维资格，也不预先证明2 TB/48小时目标已实现。

用户最后更正为五万单元以内，覆盖此前一万单元设想。本review覆盖旧“先完成53万单元/p3”“只能16步pilot”“0.7 nm仅metadata”等执行限制；不删除旧task/review、结果、费用或失败。只在现有分支新增显式profile，不改ordinary default，不重新研究低内存p4逆、p2递归、patch、BLR、DD或新的PC。

## 1. 当前证据和优先级切换

按上述HEAD核对根/目录AGENTS、仓库原则、原task、Review V6及其结果、post-V6 p3回应、最新summary、N0准备记录，以及网格/模式入口。工作站现场仍由Codex复核，远端文档不代替SSH进程状态。[N0准备][S1]、[汇总][S2]、[V6回应][S3]、[追加回应][S4]

| 已知事实 | 本批如何使用 |
|---|---|
| 旧完整0.7 nm run 20261011T070335.458824Z已受控停止；未进KSP | 保留停止和78277.660374 s workflow，不再要求先完成它 |
| 4de4926已提交N0筛选和pilot接线；最新报告仍为实现中、新场未启动 | 复用代码，不能把提交标题当数值资格或现场无进程证明 |
| 父清单32060→572；双方两偏振各143，m=-142…0；保留父清单q160 | 新任务复用筛选政策，p6/p4共用同一active inventory |
| 旧目标p6的572项及p3的148项缓存路径存在 | 新网格改变FE映射，且粗层改成p4；不能直接沿用这些FE数组 |
| 5 nm准确p4路线已完成121步；p3较省内存但短波收敛曾明显变慢 | 本批按用户要求回到准确p4，不再跑p3对比 |
| 旧2 nm p6/h1.5为54332 cells，峰值约1.15 TB，曾被node1 memory-policy OOM杀死 | 只是历史容量点；单元数少于它不保证新因子一定更小或更快 |

### U0：Codex先判断哪些旧工作值得做完

只允许完成新任务必需的N0筛选、公共profile/缓存身份、p4接线、完整求解和输出支持。若这些已可用，立即复用；若缺关键闭合，在同一模块内最小补齐，不另建性能平台。

若旧大模型现场仍活跃，本条授权Codex在可安全记录的边界保存stage、PID/start_ticks、输入/source、资源、完成缓存索引后，受控结束本任务旧进程树并核对清场。不要用SIGSTOP长期冻结TB级驻留；不要为等齐旧p3通道或旧16步而延后紧急任务。不热改活跃源码或算子，不停止邻项目。没有可靠可恢复packet时明确说明，不能承诺免setup/免LU续算。

落一份简短priority-switch记录：旧状态、停止/不必停止的依据、可复用模块、不可复用数组、未执行项。之后连续推进，不等额外审阅。旧重型工作完成与否不是新任务准入条件。

## 2. 冻结物理和网格：选择x=0.5 nm，给z保留分辨率

物理保持当前0.7 nm输入：周期50×25 nm；光栅x宽17 nm、y宽25 nm、高120 nm；z范围[-10,130] nm，界面0 nm；空气/Si各向同性，Si折射率0.9998851259969171+0.000004325285938225562i，mu_r=1；1°掠入射、方位角0°、s偏振；双Floquet、layered背景、上下DtN、无PML。epsilon=n*n。该材料值沿用已有输入身份，不新增材料实验资格。[S5]

### 2.1 唯一主网格

| 方向/区段 | 长度nm | 单元数 | 实际步长nm |
|---|---:|---:|---:|
| x：左空气/光栅/右空气 | 16.5 / 17 / 16.5 | 33 / 34 / 33 | 0.5 / 0.5 / 0.5 |
| y：完整周期 | 25 | 2 | 12.5 |
| z：下基底[-10,0] | 10 | 17 | 10/17，约0.588235 |
| z：光栅高度[0,120] | 120 | 200 | 0.6 |
| z：上空气[120,130] | 10 | 17 | 10/17，约0.588235 |
| 总计 | 50×25×140 | 100×2×234=46800 | max hx=0.5，hy=12.5，max hz=0.6 |

这些是依当前尺寸和轴分配算法计算的设计值，不是已生成网格的实测。x坐标沿现有定义为0、16.5、33.5、50 nm，y为0、12.5、25 nm；如现场坐标原点不同，保持相同相对几何，不平移物理相位原点。

已读`src/geometry/mesh_builder_3d.py`中的`_subdivide_piecewise_axis_exact_count`和`_stage4_axis_plan`，现有`mesh_axis_cell_counts`支持保材料面的精确三轴计数，且Floquet要求x/y至少两层。优先使用现有`boundary_fitted`+`mesh_axis_cell_counts=[100,2,234]`，不另写网格生成器，不冒用R13 frozen mesh ID。[S6]

标量`mesh_target_nm`不能再作为实际三轴尺寸的说明。新dat若schema仍要求该字段，可保留0.5作为名义值，但explicit-axis authority必须覆盖三轴生成；在resolved/manifest记录真实数组、轴hash、分段计数及宽度。检查所得z分配是否为17/200/17；若现有分配规则受额外必要平面影响，只允许用已支持的显式z轴完成上述计划，不删除材料面、不静默增至五万以上。

选择0.5而非0.3–0.4的原因是先保证z分辨率和总规模；在本nx/ny/nz合同下同时把x改到0.3/0.4会超出本轮预算。不是断言0.5已达到连续精度。y只有两层依赖本场沿y不变；完整三维p6空间仍保留，不能据此支持一般y变化结构。长宽比约25，必须保留真实Jacobian、方向、MPC交叉项，不能复用假定立方单元的对角/缓存。

### 2.2 必做的无长场网格检查

在唯一正式运行的preflight/setup内核对：实际cells=46800且<=50000；所有材料面、两端口和平移周期面匹配；正Jacobian、无跨材料单元；同xz位置的各y层tag相同；没有notch或其他y变化；方向/索引为当前complex128/int64/PORD64合同。记录尺寸比和PC适用范围。不额外跑小模型PDE，也不重新进行13.5/5/2 nm资格阶梯；必要pure/接口回归仍执行。

周期规则网格的条件行数账可供预检交叉核对：p6 full independent约30340800、内部21060000、trace+572约9281372；p4 full independent约8992000、内部5054400、trace+572约3938172。这来自`3 p^3 Nc + 2 p^2 Nx Ny`及每cell内部`3 p(p-1)^2`的拓扑公式，不包含Floquet从属存储、ghost或额外实现对象，不是实际矩阵/RSS。实际map计数优先，差异必须解释，不能改raw数凑公式。

## 3. 为什么不先截为m=-20…-2，以及z为何不能很粗

在上方空气、n=0时，当前波矢约定给出：

```math
\frac{k_{x,m}}{k_0}=\cos(1^\circ)+0.014m,\qquad
\frac{k_{z,m}}{k_0}=\sqrt{1-[\cos(1^\circ)+0.014m]^2},\qquad
\lambda_{z,m}=\frac{0.7}{|k_{z,m}/k_0|}\;\mathrm{nm}.
```

| m | 派生z方向相位周期nm | 含义 |
|---:|---:|---|
| 0 | 40.1091 | 入射/零级的慢z相位不是所有衍射波的尺度 |
| -2 | 2.9710 | 低阶也明显快于零级 |
| -20 | 1.00845 | 截到20仍不支持任意粗的z网格 |
| -71 | 0.700012 | 近法向出射，接近最短z相位周期 |

这是传播方向/相位的解析计算，不是强度预测。各衍射级波矢由Floquet关系和介质色散决定，模式计数不提供能量大小。[模式代码][S7]、[衍射波矢说明][E1]

**首场不再裁掉m。** 572通道已经仅为原32060通道的约1/56，当前新网格每端口100×2=200张面，而旧目标为73×36=2628张面；没必要为进一步省这143个级次中的尾部，再引入一个未知边界误差。绝不省略m=0或-1；用户提出的“-2到-20”可作结果重点观察区间，但不是完整开放边界清单。

不能通过删除某些出射通道就证明内部高空间频率不存在，也不能用它为粗z网格补资格。z<=0.6 nm与p6是本轮工程选择，最大空气传播相位步长约5.386 rad/单元；它不是误差上界或网格收敛证明。角点、材料界面及倏逝场仍可能要求后续局部/方向加密。

### 3.1 本场端口政策和等价边界

复用`build_n0_mode_inventory`，在昂贵FE装配前从完整metadata筛选n=0，保留m=-142…0和top/bottom×s/p。p6和p4共用同一active清单、顺序和归一化；metadata仍生成全部32060项用于父身份与原q160积分规则，不意味着构建全部FE泛函。[模式枚举][S7]、[N0筛选][S8]

现有父清单SHA=`7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb`；active SHA=`946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b`。新mesh不应改变纯物理模式，但应从live配置重新导出核对，不硬填hash。mesh/FE/算子组合hash必须新建。

本批不新增对称空间求解器、不改为2D、不平均材料、不仅留s偏振。沿y不变的连续问题支持n=0扇区，但当前完整三维FE、H6、PC及恢复未形成严格子空间等价证书，故`A6_n0`不冒称原32060通道`A6_full`。对称性要求源与结构共同满足，离散仍可能引入泄漏。[E2]

`auto_propagating`本身只保留现有传播政策的级次，n=0仍有未覆盖的倏逝尾部；572不是无限精确DtN。首场保留当前政策，以获得可分析场，不同时开展倏逝级次扫描。

### 3.2 用这次结果判断将来能否截断，不先猜能量

收敛后仅对已有572通道结果和算子做离线/同场终点诊断，不重建factor、不多跑一场PDE：

- 分别给出m=0、-1、[-20,-2]、[-40,-21]、[-80,-41]、[-142,-81]的R/T功率；保留每个m的s/p复振幅。
- 计算`tail20_power=sum(R_m+T_m, m<-20)`，所有功率统一除以同一入射功率；不能在保留集合内重新归一化到1。
- 通过现有572 carrier逐项累加省略作用，计算`delta20=||(A572-A84)u572||/||b572||`；A84指m=-20…0、n=0、双方两偏振的84通道算子。保留原RHS，直接组合`b572-A84*u572`；不新装全局A84。分清投影、traction及复归一化，近截止项单列。
- `tail20_power<=1e-5`且`delta20<=1e-7`只作为未来截断候选的保守筛查，不是本次必过门或严格场误差界。功率小不等于边界作用小；本次不自动改84通道再算。发现高阶重要时，保留它并报告，不为省时间删掉。

## 4. 最小代码范围：保留准确p4和已测快速组件

准确双凝聚指p6与p4都在单元内消去内部自由度；p6只在trace/port空间迭代，p4对其全局凝聚trace/port矩阵建立一份准确MUMPS因子；内部场随后恢复。不是把全域三维简化成若干独立子问题。

保持BAL_H的C→A→H→A→C及反馈组合，直接P64/PH，H6既有对角/谱窗规则，FGMRES32、zero start、max2048、complex128；A4每次返回<=1e-10，最多两次同因子精化；非零内部/端口RHS和左右端口耦合不省略。不重新研究弱p4逆，不改p3或新PC作为失败fallback。[S3]

优先复用本工作站V6已通过的q4实现和已移入的融合A6、快速完整A4验算、reference-metric H6、自然积分点顺序、blocked Gram和低扰动监督。不重新整体merge Task39extra或重跑旧迁移任务。

当前N0入口和checker锁定p3、530856 cells、pilot16、official_result=None；因此必须增加独立显式q4/aniso/full profile和对应checker，不能只改dat的coarse_degree或删掉校验。`RetainedCondensedRuntime`的细/粗mode_inventory、凝聚port行数、RHS、原A4、恢复和后处理必须一致。[S8]

允许为新profile复用已验证的对角Hp/结构零Hlocal存储方法，但不能把仅p3注册的优化无条件改成所有q适用；p4使用前需核对代数前提、真实array形状及既有测试。没有现成资格时沿用已测p4路径，不借紧急任务开启端口算法研发。

新输入建议：`input/task39extra_para_workstation_capacity/v7_0p7nm_si_p6_hx0p5_hy12p5_hz0p6_q4_n0_full.dat`。记录显式轴counts、coarse=4、active-policy、full solve、门限和资源；正式只用`python scripts/run_case.py <该dat>`。

### 缓存规则

可复用：代码、身份匹配的编译缓存、纯物理模式metadata和与mesh无关的参考表。不可直接复用：旧53万单元的FE端口向量、DOF/owner/MPC映射、方向数据、condensed matrix/factor、full/trace解向量。p3 payload不是p4 payload。

改变网格后全部FE泛函要按新映射构建，或经显式数学映射并完整验证后复用；本批优先只重建新网格572项，不发展复杂跨网格缓存转换。不把旧p6完整端口缓存拿来给新网格做A6_full检查。

## 5. 执行和资源合同

| 阶段 | 必做内容 | 继续/结束规则 |
|---|---|---|
| U0 | 现场旧任务和缓存核对，切换优先级，必要的受控停止 | 不等待旧大模型完成，不干预邻任务 |
| U1 | 完成必要N0/q4/full接线，现有精确轴计划和纯/接口测试 | 不新小模型PDE，不额外跑13.5/5/2 nm |
| U2 | 实际网格/材料/y不变/ABI/端口/资源preflight；同场setup QA | 错误最小修复，不能静默变模型；QA与主求解共用一份factor |
| FULL | 一场46800-cell、0.7 nm、q4、572通道完整FGMRES | 16/32/128步只记录；达到独立原A6_n0残差目标才算本算子收敛 |
| OUTPUT_AUDIT | 完整恢复、E/H、衍射、功率/吸收、y泄漏和尾部诊断 | 保留作用域限制，不为追“合理”增加第二场或删通道 |
| Z | response_v7、结果总账、旧工作恢复建议 | 不自动恢复53万单元旧任务，不merge master |

最新N0报告写明RSS线已按用户更正升为1.95e12 B，本批沿用，不再自动退回旧1.3e12 B，也不再提高。1.95e12 B不是允许占满2 TB整机：启动前以实际MemTotal/有效可用内存/cgroup和系统余量复核，协调独占heavy窗口；不能仅以“旧5.4万单元用了1.1 TB”作为准入证明。[S1]

worker CPU24、parent CPU9、MPI1/math1、NUMA interleave0–1；不得strict membind单node。PSS/USS/smaps扫描关闭，保留真实同期进程树RSS、身份、swap观察、退出与后代清场。全机换页不归因本任务，不据swap/预测峰/预计耗时自动杀进程。RSS触线、真实数值/实现异常、不可恢复环境错误、持续监控失效、用户主动停止仍按合同处理。系统OOM是异常终态，不是RSS Gate PASS。

最新已授权的“p6端口准备完成后24小时仍未进入solve”的窄setup守卫沿用，只绑定新run/PID/source并从新p6完成事件计时，进入solve永久撤销；不得沿用旧run时钟或增加其他隐含deadline。48小时是完整求解目标及报告项，不新增全程48小时自动杀进程；旧16步计划停止必须对新full profile禁用。[S1]

每16步或沿现有低扰动频率记录独立A6_n0、完整PC和两次C成本，保存必要检查点。不要每步落盘整个场，避免输出成为主耗时；同场checkpoint为solution-only时明确其不能免factor恢复。正式前冻结clean source；文档更新不得改变活跃源码身份。

实现bug允许最小修复、对应测试及受影响本场至多一次登记重放；数值慢、内存超限、max2048未收敛或能量Gate失败不是反复重跑理由。阶段内连续执行，不每完成一个小检查就等待批准。

## 6. 如何判断“结果合不合理”

### 6.1 必须分别给出四层结论

| 层次 | 必须测量/检查 | 可以声称什么 |
|---|---|---|
| 线性求解 | 恢复到完整未凝聚p6坐标，用572通道原算子独立算A6_n0<=1e-6；每次A4_n0<=1e-10；约束/端口/内部恢复闭合 | N0离散系统求解通过，不是全32060问题通过 |
| 物理自洽 | 实际E/H/curl、全部572幅值、R/T/A_balance/A_volume；原能量及吸收一致性绝对限值1e-5；被动性异常如实列出 | 本作用域功率与体吸收一致；单独守恒不证明场精度 |
| 对称及端口范围 | 检查多y位置的E/H，以及可得FE范数中的y变化、Ex/Ez与Hy泄漏；完整DtN或省略作用若未测则明确unknown | 可作y不变假设支持或反例，不用粗y采样证明全部n!=0为零 |
| 精度与目标 | 独立同物理参考及h/p对照是否存在；端到端时间、实测RSS、swap和预算 | 无新h/p/同物理参考时AUTHORITY_LIMITED；本次不能宣布任意3D生产通过 |

输出分类建议`ANISOTROPIC_N0_DISCRETE_PASS_AUTHORITY_LIMITED`，其前提是本算子数值和物理Gate都通过；如完整DtN未核验，必须同时保留`FULL_DTN_NOT_VERIFIED`。原A6_full和A6_n0残差严禁共用一个未注明scope的字段。N0算子通过后可输出明确标注scope的R/T/A，不再继承旧pilot“RTA永远NOT_RUN”；但不能把它标成原全通道official result。

y泄漏可记录`||E-mean_y E||/||E||`及H对应量（有真实FE积分时），至少提供多个同xz不同y的复数场对照和采样位置。1e-4是建议的诊断警戒线，不是新的中途自动停止线；超线则结果不支持对称等价，不临时投影掉它以制造通过。比较复数场不拟合任意整体相位。

若已有独立、同0.7 nm材料/几何/入射的RCWA或二维TE参考，可只读复用并核对归一化与衍射key。没有则明确REFERENCE_NOT_AVAILABLE；本批不开发第二个求解器，也不拿13.5/5/2 nm结果作同物理参考。

### 6.2 本轮只做一场，但保存下一步能决策的数据

完整保存E/H、场系数与map、curl、同坐标探针、两端口572复振幅及功率、体吸收、恢复检查、tail20及边界作用诊断。近场图/采样网格不是FE精度证明；使用已有FE/DtN积分计算功率，不以24×24稀疏采样DFT冒充高m衍射数据。

首场结果若自洽，下一轮才根据实际场变化和尾部决定是否将预算用于x=0.4/z加密/y复核或缩m。没有新授权不自动追加第二网格、84通道场或重启旧p3工作。

## 7. 时间、内存和可达性报告

分别记录mesh/port(p6,p4)/局部凝聚/H6/symbolic/numeric/QA/纯KSP/独立残差/恢复/输出及完整workflow；父子区间不得重复相加。给出每次C内PH、RHS缩减、MatSolve、恢复、完整A4验算、P及精化次数；复用与重新构建成本分列。

46800较530856少约11.34倍单元，端口面2628→200少13.14倍；这是几何工作量比，不是整场提速或RSS保证。p4因子填充依赖形状、连接、波长/主元、端口耦合和方向长宽比；Ny很小也改变消元图。不得用旧RSS乘cells比例宣布“肯定放得下”。

条件payload示例：p6 trace+572约9281372维，一根complex128约148.50 MB；约65根FGMRES基向量约9.653 GB。它不含完整场/PC向量、A4矩阵、MUMPS、端口或缓存，不等同进程树RSS。

完整目标仍是setup+factor+全部迭代+恢复/检查/输出<=172800 s。可以用本场阶段和每步实测滚动报告时间缺口，不从旧波长步数或短pilot外推必然收敛。超过目标不自动改精度或边界；如实报告“本场通过但超过48h”或“未取得完整解”。

## 8. 提交和交付

本review只提交本文件；Codex负责实际代码、测试、运行和response。推荐提交：U0优先级记录；最小q4/N0/full接线和轴输入及测试；冻结正式source；新run证据和Z收口。不得amend/强推、整体merge、覆盖旧负结果，或改task39extra/Hybrid/master。

每场绑定`input_original.dat`、`resolved_config.json`、`run_manifest.json`、input/physical/source SHA、mesh/axis/map/mode/ABI hashes、`run_summary.json`及artifact hashes。新physical hash由实际schema生成，不把旧输入hash写到新网格；旧波长和源结果仅作历史。

```text
response_v7.md
outcomes/urgent_anisotropic_0p7nm_v7.md
outcomes/records/v7_priority_switch.json
outcomes/records/v7_axis_mode_runtime_contract.json
outcomes/records/v7_terminal_compact.json
outcomes/records/v7_diffraction_tail_and_scope.json
outcomes/summary.md; test_summary.md; records/run_index.json
```

更新项目progress/model_registry，区分measured/derived/not_run/failed/controlled_stop；重型数组、factor和日志留ignored。检查Markdown表格/公式、链接、定向测试和diff；未做全仓pytest/CI/网页渲染不得宣称通过。

Response首屏回答：旧任务是否已暂停、哪些DtN模块复用；实际三轴/cells、p4与572接线；是否真正完成求解而非16步；E/H/功率/体吸收及原算子scope；高m尾部是否重要；各阶段时间与RSS；48h和完整3D精度还缺什么。不得只给“PASS”和图片。

**最终判断：先把y方向冗余网格预算移给x/z，用46800单元、准确p4双凝聚和全部572个N0通道取得一场可审查结果；不要在未知能量谱时再裁m、粗化z或重开弱p4逆。**

## 9. 证据入口

下列仓库相对路径按页首reviewed_HEAD读取；运行时追加真正新source和run，不回写历史。

[S1]: outcomes/n0_port_filter_preparation_20261012.md
[S2]: outcomes/summary.md
[S3]: response_v6.md
[S4]: response_post_v6_p3.md
[S5]: ../../input/task39extra_para_workstation_capacity/v6_0p7nm_p3_pilot16.dat
[S6]: ../../src/geometry/mesh_builder_3d.py
[S7]: ../../src/common/modes_3d.py
[S8]: ../../src/solvers/fullspace_dtn_action.py
[E1]: https://meep.readthedocs.io/en/latest/Python_Tutorials/Mode_Decomposition/
[E2]: https://meep.readthedocs.io/en/latest/Exploiting_Symmetry/
