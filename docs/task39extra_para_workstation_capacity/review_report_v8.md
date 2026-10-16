# Review V8：先关闭第17次准确 p4 返回故障，再验证 BAL_H 收敛与方向网格误差

## 0. 决策、分支与适用范围

**本轮首要任务是用保存的第17次 p4 粗修正输入定位并修复 A4 返回失败。候选 D 的直接法成果接受为受限离散解，不用于关闭 BAL_H 迭代资格。先正确、后评估收敛与分项时间；不另造预条件器，不开展缓存/暖启动或全仓整理。**

| 项目 | 固定身份 / 决定 |
|---|---|
| 审阅日期 | 2026-10-16，Asia/Singapore |
| 仓库 / 唯一执行分支 | `Rookie1234567/MyFEniCS` / `task39extra_para_workstation_capacity` |
| 固定结果 base | `7e7435feecb7d9254ca07ef1ff83fa98a12ced9a`；审阅时远端 HEAD 一致 |
| 上一正式 review / response | V7；其启动前文字不能覆盖 2026-10-16 统一交接的终态 |
| 统一交接 | `review_handoff_0p7nm_balh_20261016.md` |
| 最新失败 source / attempt | `d62c20fd2e6f77006edc80f6449447b39efcfdfe` / `20261013T225710.255482Z` |
| 当前总体裁决 | `DIRECT_N0_PASS_WITH_LIMITATIONS / BAL_H_ITERATIVE_QUALIFICATION_OPEN` |
| ChatGPT 本次修改 | 仅新增本 review；不改程序、旧证据或其他分支 |
| Codex 工作范围 | 当前分支的定向诊断、最小正确性修复、条件单场验证；禁止修改 master、Hybrid、原 task39extra 或 Task40extra |

本轮对象是原周期 50×25 nm、z∈[-10,130] nm 的 **沿 y 不变 Si 光栅**，不是 Task40 的带三维缺口 reference-q 路线。0.7 nm、1°掠入射、方位0°、S偏振、复数材料和三维 Nédélec p6/p4 保持。N0 端口为上下两侧、s/p、m=-142…0 共572项，父端口积分 q160 不变；体积分按实际编译 metadata 核验，不把 q160 误用于所有体积积分。[R0][R1]

当前整树 RSS 硬线 **1,800,000,000,000 B** 覆盖 V7 历史 1.95e12 B；worker CPU24、父 CPU9、MPI1/math1、NUMA interleave0–1、PSS/USS关闭。沿本分支最新合同，swap和预测值仅观察；不移植 Task40 的 cgroup/window/kill 合同。要如实记录任务 swap 和宿主活动，不能将全机换页归于本任务，也不能据旧 swap0 宣称未来资格。[R0][R1]

本 Chat 审阅了固定提交的交接、相关原始小记录、V7、方向验证及源码，没有登录工作站、读取468 MB NPZ、重做残差、运行FE/分解或pytest。下列独立见证系原归档结果；本次重新核对的是证据与源码关系及标明为 derived 的算术，不能冒称新科学运行。

## 1. 结果应分别接受到哪一层

### 1.1 直接法 D 与 RCWA：重要正结果，非收敛证明

| 量 | 旧 A：100×2×234 | D：200×2×118 | RCWA 用户报告 |
|---|---:|---:|---:|
| R | 0.08592253473181985 | 0.07028528534177456 | 0.0702787390763 |
| T（z=-10 nm） | 0.6522079390017288 | 0.6688236885790999 | 0.668830211715 |
| A_volume | 0.26186952633636734 | 0.260891026570664 | 0.260891048523 |
| 独立 A6_n0 残差 | 7.427046290347574e-8 | 1.3202759103785678e-7 | 非同口径，未提供 |

D 的吸收闭合差4.915383655657024e-10，原门1e-5；RSS峰1,303,868,440,576 B，workflow52,726.35 s（14.646 h）。D−RCWA 的 R/T/A_volume 差分别为 +6.54626547e-6、−6.52313590e-6、−2.19523360e-8。按当前硬线计算的峰值余量496,131,559,424 B只是这一场的算术余量，不是下一网格准入额度。[R2][R3]

接受 D 的 N0 离散求解和物理自洽。继续保留 `AUTHORITY_LIMITED / FULL_DTN_NOT_VERIFIED`：x加密和z粗化同时发生，A/D科学source不同；RCWA原工程、校准原件和复振幅缺失，不能把报告数值当独立复现。143阶功率仍逐阶比较；m=-8的T相对差约0.39%，绝对差很小，两种口径都保留。A/D的约18.6%复场样本差不是D对RCWA的场误差。[R2][R4]

V1实际Basix/FFCx符号与V2同物理平层x细化支持“横向离散色散是重要原因”：p6的hx=.5→.25 nm，归一化传播偏差约7.94e-6→2.58e-9；近临界掠入射下法向传播量敏感。它们没有证明原光栅z已充分解析，也没有排除端口、角点或源码差异。FE的572端口和RCWA的511个Fourier谐波不是相同计数；y不变也不证明省略的n=0倏逝尾部无影响。[R2][R4][R5]

### 1.2 三类迭代问题不能混同

| 问题 | 已有证据 | 本轮裁决 |
|---|---|---|
| P64方向变换错误 | 同一旧失败c/g，BAL_H由1.0814106222e-8降至1.1943062153e-10；A4=3.2266884293e-11 | 修复见证有效；保留原负例和旧g_norm元数据限制，不重开该方向研究 |
| FE-only精化未修正端口 | 旧运行在refinement0因端口超限退出；已加入原增广系统的联合残差修正 | 数学符号及后续端口改善有证据；不加次数、不换因子 |
| 最新逻辑C第17次 | A4在两次精化后仍1.1203379196e-10，端口2.9968337481e-14 | **当前必须关闭的故障**；不是新的BAL_H平衡失败 |

最后运行8条成功PC记录含1条setup QA，实际只完成7个外层步；这些成功平衡记录的初始最大值2.2977613607e-10，小于1e-8。失败发生在C返回前，当前失败调用尚未执行后续A6/H6/平衡检查，不能用前面的成功记录代替其资格。[R6][R7][R8]

## 2. 固定失败输入与诊断尺度

失败NPZ位于当前任务根下：

```text
results/euv_grazing1_phi0/v7_interleave_0p7nm_aniso_p6_q4_n0_full__full3d_iterative__mpi1__Mna/20261013T225710.255482Z/p4_failure_packets/p4_failure_0017.npz
recorded SHA256 = 79f7865f8d425a9ffa416d1d55fcd8b1a1dcdb427cdcb2531979061c8c86155a
recorded bytes  = 468361314
```

`g/c/r`各为9,757,120个complex128；`port_state/port_closure_residual`各572。**这里g是p4 RHS，不是旧方向诊断中的p6 g。** 记录的input SHA为 `488d50b4028b5a2fb84ee000af807cdb2d1a5255a17a0482113338f3bb8d2865`，physical SHA为 `d394308fe4dfcc8e0c25cdaa707fb8ff4bf4a394c268a8702b4afa069b78681a`。[R6]

| 精化下标（初解=0） | A4相对残差 | 端口相对闭合 |
|---:|---:|---:|
| 0 | 6.264898095326352e-8 | 1.8934525093751702e-9 |
| 1 | 1.1205184700057332e-10 | 2.7302617396252854e-14 |
| 2 | 1.1203379196396286e-10 | 2.996833748130505e-14 |

原rhs_norm=0.7348417462869713。由记录派生的末次绝对残差约8.232710733e-11，允许半径7.348417463e-11，超出8.842932701e-12，约12.03%。第二次精化仅将A4相对残差改善约0.0161%。这说明出现了停滞，但**不证明已知的舍入地板、缓存bug或条件数根因**。不放宽到1.2e-10、不修改分母、不少算自由度。[R6]

当前p4凝聚矩阵为3,938,172²、1,444,001,282 stored NNZ，其identity见原packet；它不是D的9,374,972² p6矩阵。旧因子是否仍live须现场核实；保存NPZ不包含可复用LU，不允许假称免分解恢复。

## 3. 用一个失败向量区分四种机制，而不是猜根因

### 3.1 原方程与残差关系

BAL_H使用同网格相容的P64及其复伴随。以下g6为细层RHS，g4=P^H g6；Delta是粗细算子差，避免与端口D混名。

```math
C=P A_4^{-1}P^H,\qquad B=C+(I-CA_6)H_6(I-A_6C),
\qquad \Delta=A_4-P^H A_6P.
```

```math
P^H(g_6-A_6Pc_4)=r_4+\Delta c_4,\qquad r_4=g_4-A_4c_4.
```

最新packet只有g4，不能伪造其原g6。可以按需要在同一c4上比较Delta*c4；旧p6方向失败packet用于原BAL_H恒等式回归。正确粗逆和Galerkin关系也不保证H6能高效处理剩余误差，外层收敛要另测。

对原增广端口系统定义e=H*a-D*c；原A4验算必须仍是消去端口后的物理算子，不能用Vc+B*a偷换：

```math
K_4=\begin{pmatrix}V&B_p\\-D_p&H_p\end{pmatrix},\qquad
A_4=V+B_pH_p^{-1}D_p,
\qquad e=H_pa-D_pc.
```

```math
r_4=g-A_4c,\qquad r_{\rm FE}=g-Vc-B_pa=r_4-B_pH_p^{-1}e,
\qquad r_K=\begin{pmatrix}r_{\rm FE}\\-e\end{pmatrix}.
```

当前代码按此关系联合校正两块，符号在静态审阅中一致。小的端口相对闭合并不单独上界FE残差：仍须测量B_p H_p^-1 e的实际作用、放大量及与r4的关系。[C1][C2]

### 3.2 P0：先做保存数组审计，不建FE或因子

在已有canonical工作树，读取并核验NPZ真实内容/hash、shape、dtype、finite；存新只读审计，不覆盖原packet。独立按原全存储范围计算g/c/r范数、最大值和原比值；比较原rhs_norm及保存r，检查原snapshot是否有别名/借用输出被覆盖的证据。记录读取和计算的真实时间与工作集。

检查PETSc Vec状态与NumPy/DOLFINx数组写入边界，比较有效恢复后的原Vec norm和实际payload范数。历史g_norm缓存嫌疑不是本次根因。不要单凭某API可能缓存就认定已定位，也不要只调用状态刷新而跳过独立数值核验。保存g、c、r不能独立重建原算子；由g-r反推出的A*c只用于内部账，不当独立验证。[R6][R8][E1]

### 3.3 P1：同输入、无全局factor的action-only定位

复用已有action-only入口，或在现有诊断模块窄加“p4失败packet”模式；不要另复制完整runner。使用失败场同一网格A、572模式、原体积分/端口积分、材料、MPC、方向和ABI。核对失败source到当前source的实际数值差；变化影响该算子时分列baseline/candidate，不能仅匹配物理参数就宣称同一离散实现。

当前源码已确认两条可比较路径：`apply_original_a4`优先选fast sum-factorized physical action；p4凝聚矩阵由compiled volume form及blocked-Gram局部张量构造。`P4RefinementLedger`文件在故障source和本次base的Git blob相同。上述事实提供诊断入口，不证明fast、native或凝聚哪条必然错误。[C1][C2]

按下面顺序，每个必要输出返回后立即复制、保存，后续调用不得覆盖借用buffer：

| 检查 | 所需证据与分支 |
|---|---|
| fast A4重复作用 | 同一保存c做两次；检查原g不变、作用重复一致、当前残差与保存r的差；若重复已不一致，先查状态/alias/工作区 |
| native A4与fast比较 | 在同一c上独立原生作用，分出curl、负mass、DtN与最后和；同时以原g范数及算子作用范数报告差异，不让大项归一化掩盖1e-10返回门 |
| FE/port增广一致性 | 用保存a，独立算e、B H^-1 e、r_FE及r4恒等式；保留原端口分母；检查归一化、正负号和MPC是否重复施加 |
| 凝聚与恢复一致性 | 用真实local tensor、maps及现有数据核查内部方程、trace/port行与缩减RHS；有兼容的原CSR才读取，没有则先用局部全贡献作用，不为此自动建完整p4因子 |
| 残差位置 | 以完整范数为母量，分内部、独立edge/face trace、slave和端口；记录最坏行/关联cell/材料/方向；不能只以几个点通过代替全场残差 |

若此处证明某一条路径不一致，修它并重做受影响见证。若路径一致而原残差确实超限，再进行有限精度诊断：记录curl/mass/端口各项尺度、相减与累加顺序敏感性、局部残差和条件性信息。优先在真正贡献误差的行/单元上用稳定求和或有明确有效精度的高精度参考检查，不建立全局高精度矩阵/因子；这种诊断不能改变生产complex128合同。

不得仅因端口已过、残差只超12%或重复结果相同就宣布舍入可接受；也不得选择数值较小的某个实现充当新裁判。任何生产修复必须说明其保持原离散算子，并经独立原A4和原端口门检验。若检查精度本身尚不能分辨8.84e-12量级绝对差，应报告该不确定性并继续定位，不直接授予PASS。

## 4. P2：什么修复足以解锁完整迭代

允许修正已定位的映射、张量/约束应用、恢复、Vec状态、残差形成或有限精度累加问题；不改变物理/积分定义，不调MUMPS排序/主元，不增加PC、局部平滑步骤或精化额度。稳定求和属于保持数学定义的实现候选，必须验证，不预先指定为唯一解法。

**必须用保存的原始g4重新执行“初解＋最多两次同因子联合精化”。** 不能在已经做完两次精化的c2上再加一次，或以c2暖启动后宣称只精化一次。最终A4和端口各<=1e-10；各次raw RHS/解/残差/端口修正与symbolic/numeric/MatSolve计数、归一化一并保存。

只读/action-only已经能定位的问题先闭合。确需检查inverse返回时，主控登记一次有依据的同g4 p4-only重放；若旧factor已销毁，可重建**一份**准确p4因子，不跑前7次outer来“等故障再现”。不额外建立p6直接因子。原0/1阶段向量若未保存，标NOT_RECORDED，只有该必要重放才补采，不伪造历史。

同时保持已有P64修复：原同失败c/g的BAL_H<=1e-8见证继续有效；本次改动影响P/PH/A4/A6时，在原保存数据上复核对应范围。仅元数据修复不自动触发整批昂贵回归。新增测试只覆盖本次失败机制、联合非零FE/port RHS及真实调用链，不默认全仓pytest。

若经不改阈值/次数的修复仍不能通过，状态保持`A4_RETURN_GATE_OPEN`，交出可复现分项证据与具体残差来源，不启动外层盲重跑。若已通过，立即进入下面有界、一次性的完整验证准备，不因普通接口bug又停一轮review。

## 5. P3：先在原 A 网格验证修复，再评价速度

**下一次完整BAL_H验证选原A网格100×2×234，而不是立刻改成D。** 理由是失败g17、p4矩阵身份、方向见证及历史迭代全部属于A；换网格会同时更换coarse方程和收敛问题。已有A直接解可作同离散对照，不需新跑直接法。

在修复见证、实际输入/算子身份和现场资源均通过后，允许登记**一场**A的准确p4双凝聚BAL_H验证：FGMRES32、max2048、zero start、原H6、572/q160保持；一份factor供同源QA与正式求解共用。能够在已经获准同一进程中安全复用该因子便沿用；否则如实计新的必要构建，不能把已销毁因子假称live。这里不授权缓存或warm-start研究。

每次C返回保持A4/port门，每次BAL_H保持原平衡门；按实际既有周期保存独立A6_n0，不增加每步全场落盘。必须越过原第17次C阻塞并持续检查，不能以“到第8步未报错”代替收敛。既有max-it/安全停止合同不改变，不增加16/32步自动终止线。

最后已知第7步0.9878594749仅为reported Schur值，独立A6只有iteration0=1；不能预测收敛步数。正确性关闭后，基于新独立A6历史、完整restart周期和实测每步成本更新可达性；达到A6_n0<=1e-6并恢复/物理门通过才授予本场结果。A网格的迭代解应与**A直接解**比较，不应以RCWA或D的R≈0.07028作为A离散的通过目标。[R6][R9]

分项性能按原日志统计：末次成功PC两C合计674.866s，其中四次MatSolve约156.238s；两A6共159.651s，H6共151.486s。MatSolve仅占这三组已记录PC父项合计约15.85%（derived，未含其他开销）。因此正确性通过后优先评估A4体积验算、RHS缩减和内部恢复，再决定最小实现提速。不能删除每次A4检查或独立A6来“提速”。第2–7步历史均值1014.038s不是新场或最终步数保证。[R0][R6]

成功后比较保存A直接解的E/H/scaled curl、同坐标复振幅、全部143阶功率与R/T/A；严格核对两source的数学和输出身份，缺完整场就报告采样范围。保留A自身离散精度有限的事实。新D网格BAL_H作为随后独立任务，不在未诊断前自动追加第二迭代场。

## 6. 独立精度工作：一张桥接网格，区分x与z的影响

在不挤占故障定位的前提下，先准备并审查一张 **E=100×2×118=23,600 cells** 的p6凝聚直接验证：x坐标逐点复用旧A，y复用两场，z坐标逐点复用D；同物理、N0/q160、端口面、source phase及输出坐标不变。不是缩小光栅，也不是换PC。

| 比较 | 保持的轴 | 唯一网格变化 | 能回答什么 |
|---|---|---|---|
| A(100,2,234) ↔ E(100,2,118) | x/y | z从17/200/17到9/100/9 | 在hx=.5条件下z减配造成的变化 |
| E(100,2,118) ↔ D(200,2,118) | y/z | x从.5到.25 nm | 在D的z网格上x加密造成的变化 |

这构成方向敏感性桥接，不是完整h收敛证明；仍缺hx=.25条件下的z加密及方向交互。不能因A→E的z变化小便证明D的全部近场或高阶尾部准确，也不能把两个方向误差假设为可加的独立误差。

**先关闭源码混杂。** A source=`9a3c4a3fd9a41702fff4069280cb9507cefb163d`，D source=`b4db2b5436a6fb188cf81773577ab31c4cacb7c5`。本次compare确认期间不仅改文档，还改过Floquet、mesh和diffraction/direct路径。E沿D已资格直接法定义，在当前分支只增加所需显式轴配置；逐项审查A/D相关变更是否在这两个case实际生效。优先对已有完整场/映射作同一原算子和同一后处理的只读复核。只有兼容桥得到证明，才把相应比较称为单轴受控；缺全场或无法证明时保持`CROSS_SOURCE_DIRECTIONAL_DIAGNOSTIC`，不擅自重跑A、D两场补齐。[R2][D1]

完整E是条件后续验证：先完成BAL_H正确性修复及首轮收敛评估，再由主控按现成heavy机制登记；最多一场，不以直接法成功代替BAL_H未完成项。不得立即启动93,600-cell或p7/p8全模型。E虽单元较少，LU fill/主元和工作区仍需实际图、装配、symbolic及实时整树RSS审查，硬线1.8e12 B；不能用23600/47200缩放1.304TB来保证容量。若准入不成立，保存结构、INFOG、实际占用和具体缺口，结束该压力路径，不强行换低精度模型。

方向比较沿既定标准：R/T/A/A_volume绝对差<=1e-4；显著功率/复幅值相对差<=1e-3（两场功率>=1e-8并集）；同坐标选定E/H相对L2<=5e-3/1e-2，弱量另报绝对差，无相位拟合。算子的代数误差及输出敏感性应明显低于所解释差异；原1e-6残差通过并不自动给出1e-6的R误差界。差异接近解算或报告精度时只报未分辨，不调参数凑RCWA。

V1/V2不再重复。RCWA缺少原工程、复振幅和原点/参考面校准时继续标reported。A6_n0与A6_full分别记录；572与511的计数差、n=0倏逝截断、y向对称范围继续列出，不由能量守恒或总R吻合关闭FULL_DTN_NOT_VERIFIED。

## 7. 执行、停止、提交与证据

本review授予的是上述限域诊断与条件验证范围；各次heavy仍由既有主控登记精确命令、source/input/ABI、现场排他和资源合同。不自动恢复历史一次重放许可，不凭远端文档假定工作站空闲；不终止邻项目。使用现有Task39para canonical worktree，真实路径以现场登记为准（现有证据为`/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity`）。正式PDE统一`python scripts/run_case.py <one-case.dat>`；action-only沿既有诊断入口，不先建p6/p4全套去做一个简单向量检查。

不引入新的任意6/12/24小时开发窗，不把48小时目标改成未授权的全程自动kill。沿现有“p6端口完成后24小时仍未进入solve”的窄setup守卫，进入solve永久撤销；实际RSS触线、真实数学/ABI/实现异常、不可恢复监控、用户停止按原合同。P0/P1无factor，P2仅必要的一份p4准确因子，P3一场原A迭代；E另行条件准入。所有测试、失败、准备和重算计入实际工程账；科学workflow父子不重复加，不以代码开发等待冒称算法时间。[R1][G1]

普通路径、变量、序列化等bug最小修复、相关测试、冻结后继续；输出错误优先消费已保存结果，不重解。无关模块不测，开始/结束/每次修复不默认跑全仓。因失败数据发现公共数值缺陷时，只扩展到真实依赖；不得改期望值、分母、门限或增加精化来让测试通过。

推荐原子提交：①同失败向量诊断及最小相关测试；②证实根因后的公共路径修复与同g4见证；③必要输入/单场验证及轻量结果。都在本分支，不amend/强推，不merge master。不得删除direct成果或迭代负例，也不向原task39extra/Hybrid/Task40分支写结果。

保留现有outcomes和run-index结构，新增紧凑的失败#17审计（文件身份/分项向量/原比值）、修复前后证据、允许的factor/replay和outer分项记录、方向桥计划/条件结果；不开发新证据平台。原始矩阵/NPZ/场与大日志继续ignored，Git提交精确path/hash和小统计。每次正式运行保存input_original/resolved/manifest/summary及source/physical/mesh/mode/ABI身份。更新`response_v8.md`、本目录summary/test_summary/run index、两级项目总账。

最终回应首先回答：①第17次A4为什么失败，有何实证而非猜测；②原g4在初解+至多2次下是否A4/port均过门；③原P64/BAL_H证据是否保持；④完整A网格迭代到哪一步、独立A6及成本如何；⑤E桥接和源码兼容做到哪里。没有关闭故障时给具体分量/位置/数值及缺项，不交笼统“仍有bug”。

## 8. 交给 Codex 的接续文本

```text
请读取同一分支的 review_report_v8.md，按固定base
7e7435feecb7d9254ca07ef1ff83fa98a12ced9a 接续 Task39extra_para。
只在 task39extra_para_workstation_capacity 工作；不修改master、
Hybrid、原task39extra或Task40extra。direct D的受限成果接受，
BAL_H失败不能关闭。

首要目标是保存失败p4_failure_0017.npz：先核真实hash与g/c/r/端口
数组，独立重算原范数，再在同A网格/模式/积分/ABI下做必要的
action-only fast/native/curl/mass/DtN及凝聚恢复定位。
这里g是p4 RHS，不是旧方向诊断p6 g。不要预设缓存或舍入根因，
不要只因端口约3e-14就忽略B H^-1 e的FE作用。

复用既有诊断和公共算子，初阶段不建全局factor，不跑前7次outer
来重现。若需要inverse验证，只登记一次有依据的原g4重放，
重新从初解开始、同一准确p4因子最多两次联合精化。
禁止从保存c2继续加修正、改1e-10门或分母、增加次数、替换PC、
调MUMPS参数、研究缓存/暖启动。每一步的真实残差与阶段向量及时保存。

以独立原A4和原端口均<=1e-10及相关P64/BAL_H原见证保持为放行条件。
通过后冻结源码和fresh资源/邻任务许可，至多一场原A网格
100×2×234的p6/p4 BAL_H完整验证，FGMRES32/zero/max2048保持。
QA和外层使用一份factor，独立A6_n0<=1e-6，物理门1e-5。
不拿第7步reported Schur当A6，不因到8/16步就宣布收敛。
原A迭代应对照原A直接解，不用D或RCWA的R值强求A通过。

正确性之后评估A4体积验算、RHS缩减、内部恢复和完整PC时间，
不把C全部说成LU回代，不删除必要验算以提速。

精度方向只准备一张E=100×2×118桥接：x完全沿A、z完全沿D，
同物理p6/572/q160。核对A/D源码差异；兼容已证明才作纯单轴解释。
先保主线修复与收敛评估，再按真实CSR/symbolic/RSS准入至多一场E。
少单元不保证LU少内存，不启动93600-cell或p7/p8全模型。
继续保留AUTHORITY_LIMITED/FULL_DTN_NOT_VERIFIED及RCWA reported范围。

资源沿当前合同：RSS硬线1.8e12 B，CPU24/父9、MPI1/math1、
NUMA interleave0–1、PSS/USS关、swap与预测observe-only。
不套Task40的固定窗或cap，不新增48h自动kill；保留既有窄setup守卫。
普通bug定向测试、冻结后继续，不默认全仓pytest或新架构整理。
交response_v8、同失败向量修复证据、实际迭代/方向结果和必要索引。
先报告数值阻塞是否关闭，再列测试。未经真实门通过不宣称迭代、
完整DtN、最终精度或2TB/48h全部实现。
```

## 9. 核验来源

以下相对路径均按页首固定base读取；既有运行source另列，不能用review提交冒充科学source。

- [R0] [统一交接](review_handoff_0p7nm_balh_20261016.md)。
- [R1] [Review V7](review_report_v7.md)、[task](task.md)、[当前summary](outcomes/summary.md)、[response_v7历史合同](response_v7.md)。
- [R2] [V1/V2/D回应](response_dispersion_validation_20261015.md)、[方向验证合同](validation_plan_dispersion_directional_mesh_20261015.md)。
- [R3] [D完整轻量终态](outcomes/records/v7_candidate_d_terminal_compact_20261016.json)、[比较JSON](outcomes/dispersion_directional_validation_20261015/candidate_d_comparison.json)、[143阶CSV](outcomes/dispersion_directional_validation_20261015/candidate_d_orders_143.csv)。
- [R4] [原FE/RCWA比较与来源](outcomes/rcwa_fe_comparison_0p7nm_20261015/README.md)、[RCWA用户原文](outcomes/rcwa_fe_comparison_0p7nm_20261015/rcwa_user_report.txt)。
- [R5] [实际参考单元符号](outcomes/dispersion_directional_validation_20261015/v1_actual_n1e_ey_dispersion_symbol.json)、[平面校准](outcomes/dispersion_directional_validation_20261015/flat_calibration.json)。
- [R6] [失败#17原packet索引](outcomes/balh_review_20261016/20261013T225710.255482Z/p4_failure_packets.jsonl)、[BAL_H compact](outcomes/balh_review_20261016/balh_evidence_compact.json)、[PC原记录](outcomes/balh_review_20261016/20261013T225710.255482Z/pc_applies.jsonl)、[归档来源manifest](outcomes/balh_review_20261016/source_manifest.json)。
- [R7] [方向机制诊断](outcomes/balh_review_20261016/historical/v7_main_balh_orientation_localization_review_20261013_v1.json)、[同失败向量修复见证](outcomes/balh_review_20261016/historical/v7_main_p64_orientation_fix_terminal_review_20261013_v1.json)。
- [R8] [联合端口精化修复说明](outcomes/balh_review_20261016/historical/v7_joint_port_refinement_fix_note_20261014.md)；旧g_norm限制也见[R7]终态。
- [R9] [最新外层步记录](outcomes/balh_review_20261016/latest_iteration_history.csv)。
- [C1] [p4 inverse/refinement ledger](../../src/solvers/p4_cell_condensed_inverse.py)：原g、残差、双块校正、失败快照；故障source与base的blob均为`9a62b447b9306f18c5238f910e072a254bbab1fe`。
- [C2] [retained runtime](../../src/runners/physical_retained_condensed_v20.py)：`apply_original_a4`、`port_closure`、`apply_port_coupling_correction`及fast/blocked-Gram构建。
- [D1] [A source至D source的变更](https://github.com/Rookie1234567/MyFEniCS/compare/9a3c4a3fd9a41702fff4069280cb9507cefb163d...b4db2b5436a6fb188cf81773577ab31c4cacb7c5)。
- [G1] [仓库原则](../repository_work_principles.md)、[根AGENTS](../../AGENTS.md)、[docs规则](../AGENTS.md)。
- [E1] [PETSc VecGetArrayRead](https://petsc.org/release/manualpages/Vec/VecGetArrayRead/)、[VecGetArray](https://petsc.org/release/manualpages/Vec/VecGetArray/)：外部API说明仅支持检查array/Vec状态，不替代本机ABI与失败数据验证。
