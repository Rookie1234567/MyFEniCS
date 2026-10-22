# Task43 任务书：实际求解验真的局部 h/p 自适应

## 0. 决策与本轮交付

**从 `task40para_phi90_mesh_modes_direct@405e3aff42ac421a4c99315df1ed9b96941ecbe4` 建立 `task43_hp_adaptivity`。先证明自适应选择有效，再证明同精度下是否省资源，最后检查迭代求解器能否支持这个空间。**

背景是当前新几何已有较可靠的直接解与方向网格对照，而旧 hp 工作已有局部加密、变阶、悬挂迹和周期约束的数值基础。缺口在于：怎样选 h 或 p，选择以后完整三维解是否确实改善，以及估计、试算和求解器重建的成本是否值得。旧 Task35e 的局部响应预测和 dot 的局部投影排名都出现过“指标变好、实际 PDE 收益不符”的证据，见 [基线审计](baseline_audit.md)。

本任务不重建一个庞大的 blind controller，也不要求 reference-free。可以使用已知较丰富的离散解校准开发；独立验收时必须说明这些参考的离散误差边界。

| 项目 | 完成本轮应回答的问题 |
|---|---|
| 空间能力 | 新几何上是否有真实 local h、真实 mixed p、合法约束与正确场恢复？ |
| 选择能力 | 至少 2 次、目标 3 次 accepted updates，是否由实际候选求解证明有收益？ |
| 精度 | 更丰富且未参与该次选择的独立离散核验是否支持完整输出，而不只 R/T/A？ |
| 成本 | 达到相同误差门槛时，最后一次求解与整个自适应过程分别花了多少？ |
| 迭代适配 | 当前变阶/悬挂空间能否进入已验真的迭代路径，且求解误差不污染标记？ |
| 短波可迁移性 | 前述条件通过后，一个 0.7 nm 缩比 pilot 是否仍有效；完整尺寸仍有哪些缺口？ |

本轮目标为可审查的数值闭环，**不预承诺 3 倍压缩、0.7 nm 全尺寸完成、full DtN convergence 或 continuum convergence**。一旦证明当前选择规则无效，应保存具体负结果并停止该规则的重复试探，而不是放宽容差制造通过。

## 1. 分支、授权与来源

| 身份 | 固定值 |
|---|---|
| 仓库 | `Rookie1234567/MyFEniCS` |
| 执行分支 | `task43_hp_adaptivity` |
| 初始代码父提交 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| 父 tree | `87b08dc47047c8ae3537428b8419e402d71d60e9` |
| 文档目录 | `docs/task43_hp_adaptivity/` |
| 上一阶段基础 | Task40para 的任务书、最新 summary、D15 Y5/Y6 与 B/Z1/Z2 对照；Task35e 最终 review |
| 辅助研究 | Task41 最新 V9 preparation；dot 最新 hp 报告；两条 NN 的最终 response |

用户本轮明确授权新建任务分支。ChatGPT 通过远端连接创建该分支和任务文档；Codex 在工作站 canonical clone 中 fetch、核对 SHA 与 upstream 后实施。此操作不修改仓库总则，也不授权删除历史分支、强推或合并 master。

Task40para 是本任务的**离散精度与直接解基线**；Task41extra 是另行进行的**0.7 nm 迭代算法主线**。它依赖规则 y 方向参考结构的预条件器不能直接视为局部非均匀 h/p 的预条件器。本轮不整体合并 Task41、Task35e、dot 或 NN 分支。

旧 Task35e 未完成 59-goal 自动 hp；Task40para 的 full DtN、完整网格收敛与侧壁场仍未全部资格化；Task41 的最新完整算子检查仍未有新通过证据。这些缺口保留原状，Task43 另建清楚的验证范围。

## 2. 物理模型与不可混用的身份

### 2.1 第一阶段：完整新几何、13.5 nm

| 项目 | 固定定义 |
|---|---|
| 周期 | x、y 均为 50 nm，双向 Floquet |
| 光栅实体 | Si，x=[16.5,33.5] nm，y=[15,35] nm，z=[0,120] nm；无 notch |
| 基底 | z=[−10,0] nm，沿用基线材料定义 |
| 上下端口 | z=130 nm、z=−10 nm；沿用上下介质与 DtN 约定 |
| 入射 | 从上方入射，grazing=1°，azimuth=90°，S 偏振 |
| 波矢方向 | k/k0=(0,cos 1°,−sin 1°)，入射 E 沿负 x；快入射相位沿 y |
| 波长与材料 | λ=13.5 nm，n=0.999002304859+0.00182649365i；按既有符号约定使用 ε=n² |
| 数值类型 | complex128、三维 Nédélec H(curl)、组装时静态凝聚 |
| 第一阶段求解 | 小规模 direct 参考；global LU 只能称本阶段核验，不称可扩展生产方案 |

不得把该有限 y 宽度模型退化成沿 y 不变问题。旧 phi0 的 x-first 经验不能直接用于新模型；x 仍有散射与边缘结构，z 仍影响穿透、界面和端口。

静态凝聚指先在单元内消去内部未知量，再求解共享迹/端口未知量，最后恢复内部场。它减少全局方程规模，但不自动减少所有局部 tensor、恢复和预条件器成本。

### 2.2 端口、积分和可比性

首轮沿用 Task40para 的 R13 完整矩形模态集合：m=−4…4、n=−8…8，上下端口和两极化共 612 个通道，包含 evanescent。保存实际解析后的逐通道 inventory；DAT 中的 `auto_propagating` 标签可能被 profile 覆盖，标签本身不是身份。

先沿用体积分 q15、端口面积分 q28，以及 `scale_homogeneous_relative_only_v1` 的相对 cutoff 1e−13。对更高 p、悬挂迹与新积分路径做一次积分阶次加严对照；若不合格，应提升并重新冻结受影响的比较，不以旧值永久豁免。

最终至少做一次相同源码、同网格/空间的 R13→R14（m=−5…5，n=−9…9，836 通道）检查，才能报告本轮端口截断稳定性。R13/R14 一次一致仍不是 full DtN 收敛证明。不同 inventory 的解不得伪装为 same-discrete direct/iterative 对照。

所有运行记录绑定 source、配置、材料、几何、mesh、degree map、约束、mode inventory、积分、RHS 和 recovery 身份。物理相同、离散相同、源码相同是不同字段；不要用一个含义不清的 hash 代替这些判断。

### 2.3 起点只是候选，不预先授予精度资格

优先试以下 interface-fitted 粗网格，共 3×10×6=180 个 affine hexa：

```text
x [nm]: 0, 16.5, 33.5, 50
y [nm]: 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50
z [nm]: -10, 0, 30, 60, 90, 120, 130
```

该网格对齐材料面并保留薄层；不意味着它能解析波场。G0 检查实际 cell tags、端口、周期配对、每方向 k·h/p 和网格质量。若网格生成器不能忠实表达这些节点，应修复参数路径，不以错误 homogenization 代替。

优先从 p3 开始研究；现有 local hp 只资格化 p4/5/6，**p3 是本任务新增的资格化工作**。先做 global p3 anchor，再实现并验真 p3↔p4 mixed entities、约束、端口和恢复。p2 与 p7 不在第一阶段默认范围。

为了并行推进方法验证，可以先用已验真的 p4–6 路径跑闭环。若 p3 尚未通过，只能写 `P4_BRIDGE / P3_LOCAL_NOT_QUALIFIED`，不能把 global p3 对照加局部 p4 实验包装为 p3 自适应成功。p3 路径的正常实现错误应修复，不因存在 p4 桥接就跳过。

## 3. 必须复用的基础与最小新增工作

| 基础 | 当前实际能力 | Task43 要做的工作 |
|---|---|---|
| exact-sequence variable-p | p6 reference carrier 上的 active p4/5/6；不是原生 runtime cellwise p 开关 | 扩展 p3，核验梯度子空间、orientation、实体阶次、投影和真实 PDE |
| dyadic hexa local h | 一分八、2:1 closure、周期镜像、材料界面保护 | 新几何 fresh anchor；最小引入多层能力，记录 requested 与 closure 后的实际 leaves |
| hanging/Floquet traces | 已有 covariant restriction、约束图和双向 Floquet | 检查混合 p 与多层叶实体共同作用，不把周期强制邻居漏出成本 |
| assembly-time condensation | active rows、局部消元、恢复与 full active residual | 每次 h/p 更新后重建索引、port functional 与恢复；保持原方程一致 |
| 35e 多层增量 | 留在 `f0f10be...` 的函数级增量 | 只取必需函数与依赖，保留当前基线后续修复 |
| dot hp | 实验报告与局部候选选择教训 | 有代码实物和完整 provenance 才迁移；否则自行实现最小通用路径 |

优先检查 `stage4_local_h.py`、`hcurl_broken_trace_graph.py`、`hcurl_broken_cell_trace.py` 的 Task35e 差分。当前基线仍有 `maximum_level == 1`、local-h interior 只 p5/6、双处 90k active FE DoF 上限；不能因文件已经存在就认为多层 mixed hp 可用。来源函数和固定链接见审计。

旧 90k 是研究预算，不是数学极限。本任务建立明确 Task43 resource profile，保留旧 profile 默认；不得通过设置 `task035e_scope` 冒用旧豁免。合法阶次需满足 edge≤incident face≤cell 等约束以及 exact-sequence 测试，不能随意把 trace p5 与 interior p4 拼接。

第一阶段只使用已存在的一分八真实 local h。贯穿方向的坐标层加密作为 structured anisotropic control，不能记成真实 local anisotropic split；各向异性局部新内核留作有证据后的后续范围。

## 4. G0/G1：最小资格化，不重复环境工程

| Gate | 必须得到的证据 | 不合格时 |
|---|---|---|
| G0 身份/环境 | 分支/upstream/source、干净或可解释工作树、工作站 ABI、complex128、MPI/线程、模型和资源 manifest | 局部修复；环境不一致时停止正式 PDE，不盲目重装 |
| 同阶等价 | empty refinement 与同 p active-space 路径对原 solver；同一完整输出向量 | 定位局部装配/约束/恢复错误 |
| 真 local h | 两单元的一侧细分形成 9 leaves；独立 12-cell 贯穿切分对照；新模型 local action | 若变成全方向切分，重新标记实现类别 |
| mixed p | 至少 p3↔p4 与 p4↔p5；合法实体 closure、梯度/curl exact-sequence、方向变换 | p3 不合格则明确桥接状态，继续修复 |
| 多层联合 | 至少 level0/1/2、悬挂迹、周期角/边、多层 mixed p 和恢复 | 只迁移解决当前缺口所需的旧核心 |
| MPI | 最小 fixture MPI1/2；正式执行所用 MPI 数的代表性复核 | 比较 global DoF、约束与完整 observables，不只 norm |
| 端口/积分 | incident projection、active trace/port functional、完整残差、q 加严对照 | 不允许以 sampled flux 替代 official 输出 |

G1 按实际执行路径授予资格：通过的 p4–6、单层路径可以先进入 G2；p3 或 level2 尚未完成时保留对应缺口。真正使用 p3、level2 或新的联合路径前，必须完成其增量资格化，不要求第一轮先开发未使用的全部能力。

对当前数值更改运行针对性测试及必要回归。已有且绑定相同源码/环境的昂贵证据可复用；改变数值行为后要重新运行相关 anchor。不要每次改 JSON 或 Markdown 都重跑 full pytest、整个旧 campaign 或所有波长。

## 5. G2：用实际候选求解建立闭环

### 5.1 两网格场差与完整输出分工

较丰富离散解与当前解之差用于估计哪里需要更多表达能力。对电场定义正定的比较量：

```math
\|v\|_G^2=\int_\Omega\left(\|v\|^2+k_0^{-2}\|\nabla\times v\|^2\right)\,d\Omega,
\qquad k_0=2\pi/\lambda.
```

```math
\eta_G(u;u_+) =
\frac{\|u_+-u\|_G}{\max(\|u_+\|_G,U_{\mathrm{inc}})}.
```

`U_inc` 是以同一域和同一 G 范数算出的固定入射场尺度，在 G0 冻结并写入记录。比较在共同物理域、材料分区和足够精度积分上进行；不能直接相减不同网格系数。同步计算 E、H 的公共体积分差、散射场差与完整边界复振幅差。

G 范数是正定场比较工具，**不是不定 Maxwell 双线性形式的能量范数，也不是已证明可靠的连续误差上界**。两网格都可能欠分辨；要结合独立加丰富核验。初期单元贡献用于定位，不当作单个修改动作真实收益的精确预测。

首轮必须有覆盖全域与接口/端口的 richer reference，优先复用同物理且具有完整场/身份的既有原始数据。没有可复用数据时，先顺序求解一个同网格 p+1 的 p-rich 参考，以及一个同 p、在预先确定的方向或区域真实细化的 h-rich 独立见证；后者不参与前者所支持的动作选择。先做实际 DoF、内存与时间预估，不默认每轮 global h/2+p+1。两类参考明显不一致时，保留 reference uncertainty，最多追加一次有明确判别目的的联合加丰富，不转成扫描。若最大已支持 p=6，`min(p+1,6)` 在 p6 区域不是加丰富；改用真实 h-shadow，不能把原空间当 fine space。

后续可在预算内复用冻结的较丰富场或构造覆盖候选并集的 enriched space；每轮所有候选必须与**同一个冻结参考、同一积分及同一输出尺度**比较。更换参考时，对保留的旧/新工作场都重新计算比较，不拼接不同参考下的误差曲线。局部 bubble 只检验内部，不能冒充完整 H(curl)/迹/端口误差；非正交方向面板不能直接平方求和后称全误差。

### 5.2 候选生成：简单、可解释、有实际闭合成本

1. 从单元场差、模态衰减与接口/端口诊断提取标记，首个规则使用 Dörfler θ=0.5；该值是初始方法参数，不是精度结论。
2. 对相同问题区域提出两个主要候选：合法 p-up 和真实 local h。先从粗到细，首轮不同时做 p-down/coarsening。
3. 对每个候选先完成 periodic、2:1、entity-p closure，记录请求单元与被迫新增单元、active FE/trace/port DoF、载体存储和预计求解成本。
4. 投影误差下降/新增 DoF 或预计时间仅用于排序。方向候选只能使用该方向自身的指标，不能把 max(x,y,z) 的缺陷记到另一个方向。
5. 每轮最多实际求解两个主要候选。两者均无效时允许一次有明确原因的修正候选；不做 ranks、optimizer、p-map、ILU/restart 的盲扫。

closure 指为保证相邻单元的场能够一致连接，额外必须改变的邻居或共享实体；它们的成本是真实动作成本的一部分。若不得不把大范围邻居一起提升，必须展示这一事实。

### 5.3 中间接受规则与最终精度 Gate 分开

每个候选先通过完整代数残差与有效空间检查。粗网格阶段不要求它立刻达到最终空间误差容差。

默认接受规则事先冻结为：相对同一 richer reference，`eta_G` 的下降超过参考/积分/求解扰动形成的不确定性地板；完整输出归一化误差的最大值不显著恶化。输出归一化使用第 6 节容差，对近零分量保留绝对尺度。G0 冻结每项差异度量 `d_j` 与容差 `tau_j`：功率逐通道为标量绝对差；复振幅为明确分组、相同边界归一规范下的复向量 L2 差；E/H 为公共体积分范数差，以参考或固定入射尺度归一化。不能给不同单位的场、幅值和功率套同一个绝对标量容差。定义：

```math
J_\infty=\max_j\frac{d_j(u,u_+)}{\tau_j}.
```

至少用一次加严求解与积分检查估计扰动，不用任意浮点小数差制造 improvement。如果候选改善 G 范数但恶化最大输出，应记录具体通道；仅在预先写明的多目标准则下保留为诊断，不能事后换指标宣布接受。个别通道允许在预先测定的不确定性范围内波动，不要求每个方向估计严格单调。

在满足接受条件的候选中，按实际新增成本与收益选择；只有测得收益才能报告“选择有效”。失败或回退后的继续应从上一 accepted state 开始，不能丢失曾失败的候选和成本。

目标 3 次、最低 2 次真实 accepted transitions。至少完成一次真实 h action 求解、一次 mixed-p action 求解；不强迫 h 与 p 都获胜。只有 0–1 次更新，或全局固定 p 扫描，均只能报 `PARTIAL`。

若粗空间严重欠分辨，允许一次明确标记的 phase-resolution bootstrap：有依据地增加必要方向分辨率后重建比较参考。它计入实际成本，不能伪装为指标选择成功。连续两轮无接受动作时优先检查共同欠分辨、积分/约束、参考与候选 ranking，不继续堆同类试算。

## 6. G3：独立精度核验与同精度成本

### 6.1 代数与物理门槛

本节 A6 指恢复后、包含全部 **active interior/trace/port** 的当前受约束离散原方程残差；保留编号不表示检查 uniform-p6 的所有测试行。若以 p6 carrier 和展开矩阵 P 表示当前合法空间，应检查：

```math
r_{\mathrm{active}}=P^{H}\left(A_{\mathrm{carrier}}P u_{\mathrm{active}}-b_{\mathrm{carrier}}\right).
```

P 包含实际 hanging、实体变阶、orientation 与复 Floquet 约束，端口按实际方程一并处理。inactive carrier 测试方向的缺陷可以用于加丰富诊断，不能要求它们也全部归零，否则会错误拒绝合法低阶/mixed-p 解。归一化与完整 action 必须独立于求解器内部残差实现并记录。

| 检查 | 本任务合同 | 解释 |
|---|---|---|
| 完整原方程 true residual A6 | ≤1e−6；小规模 direct 目标 ≤1e−8 | 由独立完整 action 计算，不只 condensed/KSP/递归残差 |
| condensed residual | direct 参考 ≤1e−9 | 补充检查，不能替代 A6 |
| 能量闭合 | abs(1−R−T−A_volume)≤1e−5 | A_volume 独立体吸收积分，不能用 1−R−T 回填 |
| R/T/A_volume 对独立参考 | 每项绝对差 ≤1e−5 | 全局功率的空间精度门槛 |
| 逐通道功率 | 完整公共 inventory，每项绝对差 ≤1e−6 | 不只看强通道或总和；新增模式单独列出 |
| 公共体积分 E/H、边界复振幅 | 相对 L2 差 ≤1e−4，并保留入射尺度绝对地板 | 处理近零与弱通道；不能仅用固定有限采样点冒充全域积分 |
| G 范数及局部场 | 主报告两网格差及独立参考差，目标 ≤1e−4 | 未满足不能宣称完整场精度；它不是已知连续真误差 |
| 端口截断/积分扰动 | 同一离散 R13/R14 与 q 加严引起的各主要指标变化≤其最终容差的 10% | 否则加严或保留未资格化；与空间误差分开记录，不称 full DtN 收敛 |

公共输出向量在第一次选择前冻结，包括所有解析后的 R/T 通道、复振幅、R00_s/R00_p/R00_total、A_volume 和 E/H。功率单位以入射功率归一化；复振幅与场使用一致规范和入射尺度。不得只挑旧 Task35 的 12 或 59 个目标替代新模型 inventory。

除总场外必须展示散射场的绝对与相对差，防止总入射场掩盖散射误差；若参考散射场接近零，以冻结的入射尺度为绝对地板，避免无意义的巨大相对数。

初期 solver 误差控制至少有一次 tighter-solve 对照，确认它对 G 场差及标记的影响小于当前空间差约 10%。不能把不同量纲的 residual 数字与 eta 直接比较。最终容差附近再检查一次，避免代数误差限制空间收敛。

### 6.2 独立核验不能循环自证

最终候选必须面对未参与其动作选择的更丰富离散：改变 h/p 的加丰富方向或组合，并重新计算共同积分和完整 observables。可复用 Task40para 现存丰富场，但必须找到真实 artifact、核对物理/模式/积分/恢复身份，并说明其只在有限离散之间受检；仅有 summary 中的 R/T/A 不够。

独立参考如未通过自身 residual/积分/端口检查，只能是诊断。若另一份更丰富场改变结论，要报告 reference uncertainty，不能将比较对象改回有利的那个。达到有限离散一致应称 best available discrete agreement；没有充分证据不称连续收敛。

新模型的四个垂直侧壁近场单独核验：在 G0 冻结双侧采样/积分位置、法向、距离、边角处理和材料侧，优先使用已有 canonical trace 定义。尚无可复用定义时，可用固定偏移面作工程诊断，但须明确它不是界面数学迹，不将角点奇异的逐点值当全域范数。原 Task40para 的 canonical sidewall 证据为 NOT_MEASURED，不能填成继承通过。Task43 未完成该项时可报告闭环结果，但最终状态须保留侧壁资格化缺口。

### 6.3 成本必须比较相同误差目标

建立少量 uniform p / structured h 对照，至少包含实际 p-only 和 h-only 控制。对照可以复用同身份的已存原始场；只有达到相同精度门槛的解才能参与“更省”的结论。不得用欠分辨廉价解对比合格解，也不能拿明显过密的唯一 uniform 网格制造收益。

报告两个时间：最终网格从冷启动到正式结果的必要路径；整个自适应过程的总成本。后者包含 enriched solves、失败候选、transfer、网格/约束、装配/凝聚、setup/PC rebuild、求解、恢复、输出和 checker。reference 的开发成本与每次用户实际必须支付的成本分列，不能隐去。

| 成本维度 | 必须记录 |
|---|---|
| 空间 | leaves、每阶单元数、edge/face/interior 阶次、active FE、retained trace、port、rows、NNZ |
| 隐藏存储 | p6 carrier、active 数据、局部 tensor、完整向量/metadata 复制、恢复缓存 |
| 内存 | simultaneous process-tree/cgroup 峰值及口径，不能相加各阶段峰值 |
| 时间 | 冷启动必要路径、各阶段 wall time、整个 adaptive campaign、失败与重试 |
| 系统 | MPI/threads、task swap 增量、OOC scratch、并行占用情况 |
| 收益 | 相同误差下 DoF、内存、冷启动时间和总开发成本分别比较 |

自适应选择有效但成本没有赢，是有价值的 `ACCURACY_LOOP_PASS / COST_ADVANTAGE_NOT_PROVEN`，不得写成总体加速成功。无需为得到正收益继续无界参数扫描。

## 7. G4：迭代接线是独立工作

当前 variable-p assembled DtN 路径可以投影端口、凝聚、恢复并算 full active residual；它明确不支持直接接入现有 `Stage4NeverMaterializedLinearSolverPort`。canonical vector export 也有 fixed-p 限制。因此不能以改一个 solver 参数宣布 BAL_H 或 matrix-free 已支持自适应。

在 G2 形成合格空间后，先对**完全相同的自适应离散**做 direct/iterative 对照。逐项验真：active trace 编号、hanging/Floquet 约束、prolongation 与复数伴随限制、coarse space、port Schur action、RHS、恢复、完整 true residual。每次 h/p 改动后重建必要对象，未证明复用有效的 PC 不复用。

可选择现有最小、适配该空间的已验证迭代路线；明确写出依赖和缺口。global LU 充当 PC 的小对照只验证代数等价，不是可扩展预条件器。不要将 Task41 的规则 q-sector reference 直接用于破坏其结构假设的局部网格，也不要重启 NN/FTT 或旧预条件器盲扫。

固定一个适配方案和一组有证据的 solver 参数，先核对 action/transfer，再运行一个小 direct-equivalent case。若该空间的迭代路线尚不成立，完成并交付 G2/G3，写明具体 blocker 与最小后续工作；不得把 direct 的成功扩写成短波生产能力。

## 8. G5：0.7 nm 的有条件小试验与长期目标

只有 13.5 nm 闭环、独立精度核验和 adaptive iterative gate 通过后，才进入一个 0.7 nm 缩比三维 pilot。默认将第 2 节全部几何长度乘以 0.7/13.5=7/135，保持 phi90、有限 x/y 宽度和拓扑；原始尺寸与缩比后尺寸必须同时记录。

该 pilot 用 Task40para 的 0.7 nm 材料 n=0.9998851259969171+0.000004325285938225562i，重新生成对应模态清单。Task41 使用过不同材料数值，不能静默混入。缩比与 13.5 nm 的材料不同，不能宣称二者为同一物理解；缩比成功更不能替代完整尺寸 0.7 nm 成功。

放大前必须审计当前实际执行路径里的 full-vector allgather、重复 metadata、p6 carrier 与 active 双存储。小 direct 可以接受的实现，不自动适合 2 TB 工作站。只迁移实际需要的 selected-row PETSc scatter/分布式恢复，不借此重写整个框架。

本任务第一轮不自动启动完整尺寸 0.7 nm 重型 campaign；交付其真实 DoF/内存/求解器适用性估计与证据边界。长期目标仍是通用、非沿某方向可分离的三维 Maxwell，工作站约十进制 2 TB、留系统余量、task swap 为零，完整冷启动必要路径单个场 ≤48 h。网格优化可能降低冗余，不能消除短波解析需求或替代有效预条件器。

## 9. 实验预算、并行与停止语义

第一批新模型完整 PDE 求解以约 8–12 个为目标、16 个以内为规划预算，包含 current、shadow、实际候选、独立参考、端口/积分复核和必要控制；小组件 fixture 不计为完整模型 case，不要求跑满预算。复用原始证据可减少 fresh runs。计划超过预算时，先说明新增哪一条判断所需的最少 case；不要扩成新的参数 campaign。修复相同 case 的普通 bug 不构成新科学路线，但真实时间仍计入总账。

第一阶段主动采用单 case 192 GiB simultaneous process-tree/cgroup peak 的开发上限，保证它仍是小规模直接解研究；这是 Task43 的开发预算，不是声称用户给所有波长定了同样上限。运行前按真实可用内存进一步收紧，至少给系统及已有占用保留 64 GiB 余量。若资源估计不合格，缩减参考/fixture 或调整最小验证设计，不盲目进入 factorization。

Task43 重型运行按队列执行；已有 Task40/41 的并行许可不自动授权再加 Task43。开发与轻量检查可继续，不终止或覆盖其他任务。使用与实际执行核数匹配的 CPU/memory admission，过时 snapshot 不当作当前可用资源。

正式结果要求无 task swap；区分已有系统 swap、task 增量与 OOC。因资源停止标为 `RESOURCE_STOP`，不冒充离散/求解方法失败。触发本任务资源终止时只终止本任务完整进程组并留存证据。

不要沿用 dot 的 600 s 或任意 16 步截断，也不要把长期 48 h 目标变成每个小步骤的短 timeout。根据同类实测阶段时长设有解释的监测与停止条件；无输出时先检查进程树、CPU、阶段日志与交互提示，不能重复启动同一任务。

## 10. 文件、运行记录与交付

实现优先复用通用 runner；新增数值算法进入 `src/`。只在确需新参数入口时加薄的 case runner。配置与轻量记录放入清楚命名的 `benchmarks/cases/` 或 `input/task43_hp_adaptivity/`；重型 artifact 使用新的 Task43 ignored 目录。

每个 candidate/accepted cycle 至少记录：parent state、mesh/degree map、requested/actual closure、source/env/command、mode/q/RHS/recovery 身份、full/condensed residual、完整 observables、同参考的场差、接受/拒绝原因、所有成本和 artifact 路径/hash。checker 从原始值重算规则，不信任单独的 status 字符串。

首份 `response_v1.md` 与 `outcomes/summary.md` 应提供：

1. 基线/环境/迁移清单，p3、multilevel、迭代接线各自状态。
2. cycle-by-cycle 表：current、p 候选、h 候选、实际闭合规模、场差、最坏旁路输出、选择和成本。
3. 最终 mesh 与 p 分布图；h refinement level、周期被迫邻居、edge/face/interior 阶次分开说明。
4. 独立参考与 full observable vector 的误差表；未完成端口/侧壁资格化如实保留。
5. 同精度 uniform/structured 对照，最终单次成本与完整 adaptive campaign 成本。
6. 负结果、资源停止、未运行项；不只列通过数量，要给具体失败量、实测值和阈值。
7. 迭代适配结论与一个条件满足才运行的 0.7 pilot；未运行时写清前置缺口。
8. 按 production core、runner/checker、evidence/docs、research-only、do-not-merge 分组的 selective merge manifest。

同步 `docs/development_model_registry.md`；最终审查前按仓库规范完善 `docs/development_progress.md`。所有技术说明中文优先，首次出现的算法名解释其作用、收益与代价。

建议提交顺序为：最小核心迁移与资格化；实际自适应闭环；独立精度/成本比较；迭代接线与条件性 pilot。每一组都绑定最终源码测试，不改 ordinary defaults，不合并 master。

最终状态可为 `PASS_WITH_QUALIFICATIONS`、`PARTIAL`、`CONTROLLED_NEGATIVE` 或 `RESOURCE_STOP`；分别说明空间能力、选择能力、精度、成本和迭代能力，不用单个 PASS 掩盖未完成项。

## 11. 方法依据与适用边界

- [Demkowicz, Fully automatic hp-adaptivity for Maxwell’s equations (2005)](https://doi.org/10.1016/j.cma.2004.05.023)：加丰富解、投影型候选比较和单位新增自由度收益，为本任务的初始设计提供方法依据。
- [Rachowicz–Pardo–Demkowicz, Fully automatic hp-adaptivity in three dimensions (2006)](https://doi.org/10.1016/j.cma.2005.08.022)：三维两网格和 h/p 候选选择框架。
- [DOLFINx refinement 官方文档](https://docs.fenicsproject.org/dolfinx/v0.10.0.post5/cpp/refinement.html)：已有 hexa uniform refinement；本项目仍需正确联合 local hanging H(curl)、Floquet 与 variable p。

这些方法依据不保证本项目短波、不定、复材料和 DtN 系统一定获得同样收益。Task43 要提供的是本项目实际解、完整输出和实际资源上的证据。
