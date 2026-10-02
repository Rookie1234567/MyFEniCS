# Review V4：主线精度对照与 dot 恢复后的互补验证

## 0. 裁决、冻结身份与原尺寸目标

**接受主线 Review V3-A 的配对归因结论：当前散射场精度负结果保留，下一步直接完成已经登记的 Gx560/Gz528 两个网格对照。dot 的低内存端口表示值得继续，但恢复后的有限元接线尚未验证，周期分块入口仍受 p4/532 通道限制；目前不能交付“工作站大规模验证就绪”的结论。主线不等待云环境恢复，云端不重做主线的精度扫描。**

| 项目 | 本次冻结身份与裁决 |
|---|---|
| 主线分支 / 审阅 HEAD | task40extra_0p7nm_engineering / f376dfa00c554c6d15413f1f8f887d43eb361b9d |
| dot 分支 / 审阅 HEAD | task40extra_dot_parallel_cloud / 4a4360db8ae3d00692b69005f3a808639b87949f |
| dot 已发布 V15 / 恢复源码检查点 | de14d2a28333348a0f3eefc8d4471dcdafbddb37 / 112dcae23d986914fe6acfb3aa6a1fd5bdbd2e98 |
| 主线已有权威 | [task](task.md)、[Review V3](review_report_v3.md)、[Response V3](response_v3.md)、[summary](outcomes/summary.md)；本次新增联合恢复审阅范围，保留 V3 |
| 当前最新主线进展 | A_complete_B_preregistered_before_run；未发布 response_v4 或 Gx/Gz 求解记录；不据此推断本机没有在执行 |
| 本轮交付 | 仅新增本 review 到主线；不修改求解源码、dot 分支或 master，不启动计算 |
| 状态 | pass_with_qualifications：允许以下有界续作；原尺寸精度、资源及生产默认均未批准 |

最终验收对象是**原尺寸 50×25×140 nm、λ=0.7 nm 的完整三维模型**，先完成规则光栅基线，同时保留以后非可分三维缺口的全部自由度、端口与恢复能力。整机预算为**十进制 2,000,000,000,000 B，swap=0；单次完整必要流程不超过 172,800 s**。计时包括 JIT、构造、装配、分解、迭代、完整场恢复及规定输出/校验；不能只计一次回代。缩小尺寸、代数残差通过或组件通过，均不能替代这个目标。

本次直接读取两条远程分支的任务材料、源码、Git 差异和已提交数值记录，并用记录中的标量独立复算比例、范数关系和存储量。没有读取已丢失的云端原始数组，也没有运行 FE/PETSc、测试或 PDE。文中 measured 是已发布实测，derived 是从记录或尺寸推导，not_run/unknown 不继承任何历史 PASS。主线 f376 相对 Review V3 提交 8207bbeab7153731999f20fb719850cc58e3ee13 的三次提交只新增配对归因后处理、四项测试及两个记录，没有修改求解核心。

## 1. 主线：背景归因已完成，应该进入 x/z 对照

### 1.1 现有离散系统准确解出，但散射场仍不一致

本组模型将原尺寸全部缩小为 7/135，计算域约 2.592593×1.296296×7.259259 nm，带非可分三维缺口。p6 是单元内六阶电场表示；准确 p4 提供迭代校正。两种阶次的作用不同，p4 因子行数不是 p6 完整自由度。rows/NNZ 分别是输入矩阵的行数和非零项数；分解时还会产生额外非零项，称为填充，不能只据输入 NNZ 估算因子内存。

| 已发布实测 | F3/G0/M2 | F5/G1/M2 |
|---|---:|---:|
| x×y×z 单元 / p6 完整存储自由度 | 6×4×14 / 229,680 | 10×4×22 / 595,512 |
| p4 因子输入 rows / NNZ | 29,332 / 11,293,034 | 75,540 / 29,765,186 |
| 原 A6 真残差；限值 1e-6 | 7.5936104e-7 | 8.7353225e-7 |
| R / T / A_volume | 0.075651902 / 0.906206871 / 0.018141268 | 0.076124071 / 0.905769240 / 0.018106713 |
| workflow 秒 / 同时进程树 RSS 峰值 B | 1174.947 / 4,006,539,264 | 2448.071 / 7,754,170,368 |
| 任务 swap / 有序 M2 通道数 | 0 / 340 | 0 / 340 |

F3 求解源码为 a43f7f76a0df0f4440b77834846973b2de7ea3a8，F5 为 63dd2a7378153f2ab5094eb5e7a98d05758a39bf。完整场、模式键及环境身份见 [run_index](outcomes/records/run_index.json)、[P4 记录](outcomes/records/volume_h_agreement_v2.json)；不能把它们改标为当前源码新运行。

“散射场”是总场减去指定解析背景后的剩余量。分层 Fresnel 背景含入射、反射及透射；仅入射平面波是另一种定义。本轮归因在相同保存场、同序坐标及公共体积上配对两种定义，直接计算电场的 curl，再得到磁场；没有拟合相位或系数。

| M2 公共体积比较 | E 相对差 | H / curl 相对差 | 原 1% 门槛 |
|---|---:|---:|---|
| 总场，以 G1 总场范数归一化 | 0.375102% | 0.394986% | 通过 |
| 扣除分层 Fresnel 背景，以 G1 剩余场归一化 | 2.611883% | 2.750374% | 失败 |
| 只扣入射平面波，以 G1 剩余场归一化 | 1.465905% | 1.543451% | 同样失败，不能作为替代通过 |
| 入射归一化绝对差，诊断量 | 0.474044% | 0.499127% | 不是新增通过标准 |

两种背景得到相同的差分分子：E 的体积 L2 差为 0.0234144603123 (V/m)·nm^(3/2)，curl/k0 为 0.0246533966778 同单位。总场和散射场百分比不同来自分母，不是一次可把失败消掉的修正。R/T/A_volume 绝对差分别为 4.721693e-4、4.376307e-4、3.455502e-5，均小于 1e-3；但 top(0,0,s) 复振幅差 1.555605%、bottom(-1,0,s) 1.274430% 仍超过 1%。前者模长差仅 0.311584%，相位差约 0.0152173 rad，故只看功率不足以判断精度。

证据：[新原始归因记录](outcomes/records/background_attribution_v1.json)、[归因决策及实验预登记](outcomes/records/background_attribution_decision_v1.json)。分析源码为 c465d88f2c4b666118ba477abb347764dbdc2b7c；记录声明 clean source、complex128、MPI1/threads1，分析用时 2560.351 s。其 769,016 KiB ru_maxrss 是**单进程历史高水位**，不是新的进程树或整机峰值，且本次没有 PDE 求解。

### 1.2 真实 p6 空间的背景表示误差不足以解释负结果

这一步把同一个解析背景分别放进两张网格实际使用的 p6/MPC 空间：MPC 是把周期边界两侧自由度按相位关系连起来的约束。它用于检查“有限元表达不了背景”是否足以解释当前网格差，而不是用一个可调函数去抵消误差。

源码 [interpolate_p6_background / 配对积分](../../src/postprocessing/task40_saved_field_h_comparison.py)使用各自真实 function_space 的矩插值，随后执行实际约束的 homogenize/backsubstitution；E 的直接 curl 在 DG6 中独立求值。记录中约束残差为 0，相对 slave 调整小于 6e-15。记 d 为两保存电场之差，d_b 为两网格所表示背景之差，保留复内积交叉项，不拟合系数：

| M2、Fresnel 背景，derived | 原差范数 | 背景表示差范数 | 去掉该表示差后的范数 | 剩余 / 原差 |
|---|---:|---:|---:|---:|
| E，(V/m)·nm^(3/2) | 0.0234144603 | 0.0016374608 | 0.0233532180 | 99.7384% |
| 原始 curl(E)，(V/m/nm)·nm^(3/2) | 0.2212883711 | 0.0676860748 | 0.2099384920 | 94.8710% |

平方范数恒等式闭合误差小于 9.1e-16。**当前配对证据不支持把背景插值当作主要根因。** 单看“背景差范数占几成”会遗漏方向和相位，不能替代上述无拟合剩余量。各材料区 E 差平方贡献为空气外区 62.64%、缺口空气 2.48%、基底 8.05%、光栅硅 26.83%；因此盲目只加密缺口也缺乏依据。

对旧 h_agreement_v1.json，应进一步修正“背景不同就解释了旧 PASS”的推测：同一保存 M0 对的旧总场及入射归一化量可以复现，但按其声明只扣入射波，固定点散射 E/H 得到约 1.479247%/1.553318%，仍不是旧 0.291445%/0.306061%。**旧散射分母和生成程序仍未复现，不能认定旧程序 bug；这也不妨碍根据现有可靠比较进入 B。** 保留 generator_unknown，不再为追溯旧程序开启无界调查。

本次接受 A 的范围是“指定两背景、当前四个保存场和公共体积的配对归因”，并非整个后处理或连续解精度的普遍认证。下一轮复用这些结果，不再重跑 A。

### 1.3 B 的新增信息与现状

G0 到 G1 同时改变 x、z，现有结果无法分辨哪一方向更值得投入。预登记的两个交叉网格保留各自轴节点而非重新生成同数目的均匀节点：

| 四角 | 轴节点来源 | 单元数 | 发布状态 |
|---|---|---:|---|
| G00 = F3/G0 | G0 x、G0 y、G0 z | 336 | 已有场 |
| G10 = Gx560 | G1 x、G0 y、G0 z | 560 | 仅预登记，当前远程没有结果 |
| G01 = Gz528 | G0 x、G0 y、G1 z | 528 | 仅预登记，当前远程没有结果 |
| G11 = F5/G1 | G1 x、G0 y、G1 z | 880 | 已有场 |

既定假设是：对 Fresnel 散射 E、scaled-curl 和 top(0,0,s) 复振幅，Gx 比 Gz 更接近 G1。若任何一个主要量在可分辨精度内不满足这一关系，就不能确认 x 主导；不能只挑支持它的指标。四角混合增量 E11−E10−E01+E00 及对应 H/curl 用于检验 x、z 是否存在明显耦合。这个对照针对**当前 0.7 nm 负结果**，与旧任务笼统的轴向加密不同；仍不能单凭两条轴证明 y 收敛或连续解收敛。

## 2. dot：四类证据必须分开

依据 dot [V15](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/response_v15.md)、[恢复检查点](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/recovery_retained_h_checkpoint_v1.md)、[portable 合同](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/portable_retained_h_qualification_contract_v1_zh.md)与[原尺寸剩余缺口](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/original_target_remaining_gaps_recovery_v1_zh.md)。以下链接固定在本次 dot SHA，不随其后续提交改变。

| 证据类别 | 本次核实内容 | 能支持什么，不能支持什么 |
|---|---|---|
| 已发布历史实测 | V13 X、V14 XZ、V15 Y 的小尺寸完整三维 worker 与独立 checker 记录；完整 q 分支、内部恢复、regular/notch 对照 | 支持旧环境、旧配置下参考逆架构与代数接线；不证明原尺寸物理精度、新环境或新后端通过 |
| V15 后历史组件结果 | p6 低内存端口组件及 532 通道分解前对照曾通过；checker 曾因只读主元数组崩溃，修复后再检遭环境中断 | 按用户提供的历史状态及恢复清单保留；最终独立 checker 为 UNKNOWN，没有完整收据可补判 PASS，也不是数值方法已被反证 |
| 精确恢复的源码 | y_orbit_two_cell_block_audit.py 与 y_orbit_quotient_condensed.py 的文件字节哈希对应先前观察值 | 两个文件身份得到恢复；不等于整个原 p6 补丁、测试、运行环境或数值证据恢复 |
| 新重建代码与当前测试 | retained_port_block_layout.py、p6_cell_condensed_action.py 的恢复接线；27 项 NumPy 代数测试、4 项带 stub 的工厂元数据测试通过 | 证明所测代数和元数据分支；真实 FE/MPC/FFCx/PETSc 接线 NOT_RUN |
| 缺失资料 | 旧 raw fields/matrices/logs、完整原 p6 candidate/patch/test bytes 与旧环境 | 必须新建 fixture 和证据；不能把旧路径或旧 PASS 写进新环境资格 |

精确恢复两模块 SHA256 分别为 cd37ac48af2aeaebc2741d92927a2278f18aacc5b2dcec852440b6a6a33e39ab、55846638b8d1bc2e3c0f3fa32c2b567e40e4e91743f4823526d2534d276b79fa。完整旧 p6 candidate 的已知哈希 baa9c4229160d072e641d125f826dba9373991dcfdcc823b6feaecff252ce1f9 **不是**当前重建代码身份；新重建 p6 文件哈希为 7f2b2132569f8f40d9ba62f42bfd8e07dfcecc7eb98f041bebff7f7c6bdab692。[源码恢复清单](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/records/recovery_retained_h_v1/provider_source_recovery_inventory.json)给出其余缺失项。

27 项测试使用复数、非 Hermitian 控制，确实覆盖漏单元、错误共轭、原始 H 与消元后端口块混淆等，不仅是近零数据自洽。4 项测试通过提取实际工厂代码并替换 PETSc 整数类型和最终 action 构造器完成；它们没有构建真实 PETSc action。“clean_clone”收据实际是源码子集的新目录复跑，不应扩大为完整干净仓库的 FE 安装验收。当前 Python 3.12.14 / NumPy 2.3.5 / SciPy 1.17.0 环境缺少 FE/PETSc 栈；官方包源不可达且没有云端 FE 在运行，是当前恢复状态，不是主线续作的前置阻塞。[测试与环境收据](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/records/recovery_retained_h_v1/fresh_helper_and_factory_tests.json)、[新运行时清单](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/records/recovery_retained_h_v1/new_executor_inventory.json)。

### 2.1 X/XZ/Y 历史通过具体意味着什么

以下为缩小 7/135、p4、φ=5°、手动 532 通道的三维历史实测。两单元周期分块把重复 y 结构拆成多个相位分支 q 分别求解，再合回完整三维量；分支数增加时全部保留，未只取 n=0。

| 历史点 | 全局单元 / q 分支数 | worker / checker 秒 | 两者各自进程树峰值 B | regular / notch 最大原方程残差 |
|---|---:|---:|---:|---:|
| V13 X | 120 / 4 | 1535.147 / 590.104 | 1,422,172,160 / 1,567,666,176 | 7.57683e-11 / 4.71095e-12 |
| V14 XZ | 168 / 4 | 2392.339 / 754.006 | 1,669,115,904 / 1,594,347,520 | 7.60336e-11 / 4.58254e-12 |
| V15 Y | 120 / 6 | 1748.504 / 565.967 | 1,606,623,232 / 1,707,114,496 | 8.92748e-12 / 7.28650e-12 |

这些峰值不是同时叠加；worker 时间与 checker 时间的范围也分别保留。Y 首次约 88.705 s 的失败来自 H 检查写死乘 2，未到分解；修正 K=3 的验证元数据后成功，旧失败仍保留。Y 缺口沿周期 y 平移，虽同体积，却不是 X/XZ 的同一几何，**不能把三行当同一场的网格收敛序列**。Y physical RHS 上的缺陷指标约 1.86919e-4，是采样响应而非算子范数上界；弱小缺口的少数迭代步不能外推原尺寸或强缺口。[校准表](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/calibration_comparison_v15_zh.md)、[Y compact record](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/records/direct_Y_v15/compact_record.json)。

## 3. 低内存端口、完整内部恢复和周期分块的实际价值

### 3.1 确实省掉什么，尚未省掉什么

端口把开放边界上的场写成衍射通道。原始 H 是通道自身的归一化块；在当前定义下它是对角的，只需保存一个向量。单元内部消元又给端口添加 Di·XiB 修正：Di 把内部场作用送回端口，XiB 表示端口激励产生的内部响应。把这项保留为两次乘法，可避免先形成大的通道方阵；代价是保留内部响应缓存并在 apply 时做乘法。**原始 H、消元后的端口块必须区分。**

| 路线 | 源码核对后的判断 | 尚缺的目标规模证据 |
|---|---|---|
| 对角原始 H + 缓存乘法 | original_port_blocks.py 的 cached apply 借用 Di/XiB，不组装完整 Hhat 方阵；有明确表示收益 | 实际缓存数量、每单元端口支持大小、C/D、求积、全部 q 因子同时驻留成本 |
| 新 retained helper | 对角、只读借用、零 Hlocal 情形受 27 项代数测试；非零 Hlocal 明确拒绝，默认 dense_legacy 未静默改变 | 完整真实 FE/MPC 工厂、非零内部和端口 RHS 的实际接线；它不是任意 Hlocal 的通用替代 |
| 完整内部自由度恢复 | p6 源码仍保留内部 RHS 项、trace 响应与 −XiB·alpha；没有从数学式删除内部自由度 | 新运行时真实恢复、完整原方程残差和全部输出的 dense 对照 |
| 两单元参考逆 | 历史证据支持利用 y 周期结构缩小参考构造，完整外层三维方程仍保留 | AUTO 模式下 q 数、块尺寸、分解填充、全部因子占用、缺口耦合及完整流程时间 |
| 端口投影到 q 小块 | 已避免原始未投影通道大方阵 | 源码仍显式形成投影后的稠密矩形，再转 COO/CSR；并非整条管线都对通道数线性 |

关键源码入口：[original_port_blocks.py](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/src/solvers/original_port_blocks.py)、[新 helper](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/src/solvers/retained_port_block_layout.py)、[p6 action 的 original_hp_solve / reduce_rhs / recover_storage](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/src/solvers/p6_cell_condensed_action.py)。其中 recover_storage 保存“内部原方程解内部 RHS + trace 响应 − 端口响应”，这是源码层面的正确保留；真实 FE 验证仍待恢复。

本次另核实两处决定下一步范围的限制：

1. [y_orbit_quotient_condensed.py](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/src/solvers/y_orbit_quotient_condensed.py)仍冻结 532 个模式和对应 manifest，调用 spaces[4]，使用 degree=4、每单元 300 个局部自由度及 108 个内部自由度。模块名称包含 p6 action 不代表完整两单元入口已能运行 p6 或 AUTO。后续推广必须改变并验证这些结构假设，不能只删断言。
2. [y_orbit_two_cell_block_audit.py 的 _block_compact](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/src/solvers/y_orbit_two_cell_block_audit.py)先形成 dual_di 和 xib_primal，随后执行 projected = dual_di @ xib_primal；这个投影后的 lp×rq 块是稠密数组，之后才转稀疏并累加。AUTO 下必须量出最大 lp、rq、临时字节、实际 NNZ 和转换时间。不能用原始 H 已对角化，推断 projected、CSR 累加或 LU 填充也便宜。

### 3.2 原尺寸 AUTO 的收益可算，整机可行性还不能算定

[原尺寸端口库存](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/records/full_size_port_inventory_v1.json)记录 λ=0.7 nm、50×25 nm 周期、θ=89°/φ=0 的 AUTO 规划数为 **32,060 通道**，含 8,015 个不同 (m,n)，其中 31,488 通道 n 非零。该记录 ordered_key_hash 为 null，且是传播通道库存，**不是已经通过端口收敛的最终截断**；后续 evanescent 通道可能增多。

| derived 表示成本，complex128 | 字节 | 含义 |
|---|---:|---|
| 一个 32,060×32,060 密集 H | 16,445,497,600 | 十进制 16.4455 GB；不是整个求解器峰值 |
| 同一 H 的 32,060 个对角值 | 512,960 | 约 0.513 MB |
| 原始 H 载荷比 | 32,060 倍 | 明确有效，但不能当整机节省倍数 |

单个密集 H 约为 2 TB 的 0.822%；避免多处重复方阵可能更有意义，但必须数清实际同时存活的对象。C/D、内部恢复缓存、每个 q 的因子及工作区可能远大于这一项。当前 [端口求积公式](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/src/solvers/dtn_port_3d.py#L1610)为 max(10,2p+max_order+6)；历史 max_order=142 对应 p4 degree156 / p6 degree160，名义张量 Gauss 点为 6,241 / 6,561。实际编译点数、FFCx/JIT 内存及面工作缓冲尚无新实测，不能按 532 通道小例子的单位成本直接外推。

### 3.3 公共 PETSc 因子后端仍是方案

[公共后端文档](https://github.com/Rookie1234567/MyFEniCS/blob/4a4360db8ae3d00692b69005f3a808639b87949f/docs/task40extra_dot_parallel_cloud/outcomes/public_petsc_factor_backend_plan_v1_zh.md)没有实际 import、矩阵、分解或求解证据，尚需把当前 NumPy RHS 接口与 PETSc Vec 正确衔接。现有 q 因子使用 SciPy splu；旧私有 ctypes MUMPS 路径不应作为新环境的便携恢复方案。

LU 分解把矩阵预先拆成两个便于回代的三角因子，以减少重复求解的成本；符号分析先确定稀疏结构，数值分解再计算数值，额外因子和工作区会消耗内存。独立核对官方接口：setFactorSetUpSolverType 创建因子对象，不等于完成符号分析；首次 PC.setUp 会接续执行符号分析和数值分解，不能伪造一次“Python 在两阶段之间批准继续”的事件。小型有界资格可明确采用组合 setup；原尺寸若要求分析后再批准 numeric，该阶段准入能力仍未具备。[官方 PC API](https://petsc.org/release/petsc4py/reference/petsc4py.PETSc.PC.html)、[官方 PCLU 实现](https://petsc.org/release/src/ksp/pc/impls/factor/lu/lu.c.html)。

PETSc.IntType=int64 也不证明 MUMPS full64；必须按安装版本核实 rows/cols、NNZ、offset 和一基转换范围。无需为小算例强求 full64，但原尺寸不能凭小矩阵成功跨越未知整数限制。[PETSc MUMPS 官方说明](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)。这些网页是接口依据，不是本次运行环境的资格证明。

## 4. 哪些路线已有结果，本轮不重复

| 已试或仅设计的路线 | 已知结果与边界 | 本轮处理 |
|---|---|---|
| task035 残差型局部加密与 DWR（辅助方程加权目标误差） | 残差型对 uniform 的目标误差比约 18.263/5.738，负结果；DWR p4/p5 曾比对应 uniform 少约 8.4% DoF、误差低约 26.8%，但仍不胜既有 structured p4 h7.5 | 不重开自适应方法扫描；见[原 summary](../task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md) |
| task035b 高阶局部 hp、顶部 z 与 x-only | 原 13.5 nm 模型，顶部 z 两点各 8/12，反向 7/12、8/12，x-only 5/12、6/12；未消除逐模式超限 | 不把旧轴向建议包装成新方法；当前 B 只回答 0.7 nm 配对归因；见[原 summary](../task035b_high_order_local_hp_resource_envelope/outcomes/summary.md)及 V3 历史具体失败项 |
| task39extra 42 宏块 Schur（消去块内未知量后解块间关系） | exact RSS 为参考 1.510045 倍；approx A4 三项 37.2721/0.726414/41.8259，超过 0.5/0.2/0.5 | 不把同一宏块法改名重跑；见[p4 Schur 记录](../task039_extra_physical_multilevel/outcomes/p4_schur_v14.md) |
| 主线 M1→M2、背景与 P2 | M1→M2 场/模式变化已小；P2 积分复用已验证；本轮 A 已完成新配对归因 | 不再扫描 M 或重做同一背景检查 |
| 主线 P5 / P6 / P7 | P5 已做 q=1.25/1.5 增长，E2 原 worker exit4 保留；P6 是实际 p6 单元 450 内部/432 trace 与合成接口证据；P7 完整路线仅设计 | 不用离线补记录追认失败运行；不在主线另造 dot 参考逆或存储路线 |
| dot 旧裁剪 532 / 旧 H 修补 | 旧 C/D 近零、因子原残差约 1.434e12；只改 H 不能恢复已裁剪物理耦合，后续 centered 路线才有小例资格 | 不裁模式、删小耦合或只保留 q=0 来压资源；保留历史失败 |
| dot X/XZ/Y 与新恢复 | 小尺寸旧环境已通过；新恢复只有组件代数与元数据通过 | 不重跑整套旧尺寸增长；新环境仅用一个 fresh fixture 关闭实际接线缺口 |

task035b 最好 h13 点仍有具体失败：bottom(-4,0,s) 功率差 1.79970e-9 > 5.25100e-10，top(-4,0,s) 功率差 4.81518e-9 > 1.08649e-9；top(-5,0,s) 复幅绝对差 6.58997e-6 > 1.11321e-6，top(-4,0,s) 为 3.58744e-6 > 1.88152e-6。[原始记录](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_directional_z_mpi8.json)与上述方向扫描一起保留，不能由求解残差通过改写为物理通过。

V3 已给出 task035、task035b、task39extra 的冻结来源和逐项负结果；本轮复核主线继承记录，未修改这些历史材料。下一轮“最少”的含义是复用合格证据，把新运行用于尚不能由已有数据回答的问题。

## 5. 下一轮分工：主线两个对照，云端一条恢复验证链

### 5.1 主线顺序与明确产出

**M1：完成 B，至多两个新增物理配置。** 执行 Codex 先核对正在运行的任务、工作树及本地结果；若 Gx/Gz 已开始或已有与冻结身份一致的合格结果，接续或直接整理，不能重复启动。沿用现有 qualified WSL activation、p6、准确 p4 reference-metric、M2 全 340 通道、MPI1/threads1、相同材料/几何/入射及积分约定。按 Gx560→Gz528 顺序一次只运行一个 heavy case；保留全场、直接 curl、全部复模式及资源记录，不在此步骤改求解算法。

**M2：用四个场作一次共同比较，并给出网格投入结论。** 复用 F3/F5；按预登记取公共四网格体积，以固定 G1 范数比较 E/H/curl，另列绝对差与入射归一化值。模式保留原“第一振幅”分母，并额外列 G1 归一化的方向诊断。输出三个主要量的 Gx/Gz 排序、两个既有失败模式、x/z 增量及混合增量，保留全部 340 keys 与冻结 11 个显著模式。

结论只允许由实测支持：若三项均支持 x 主导，给下一次单向投入的网格建议；若 z 更有效则据实选择 z；若分裂或耦合明显则写“未分离”，不继续追加第三、第四张网格。任一新对比通过仍只是离散参考间一致，不宣称原尺寸/y 方向/连续精度已验收。

**M3：随同结果输出一个供 dot 对齐的轻量接口包。** 在现有 records/summary 中给：物理配置与完整轴节点、材料/单位、θ/φ与 s/p 定义、参考面/相位原点、背景函数身份、全有序通道 keys/digest、未知量及内部恢复约定、原残差定义、场/功率/复振幅指标和真实资源口径。重型数组仍在 ignored artifacts，以 hash 绑定。主线 φ=0/p6/M2=340 与 dot 历史 φ=5/p4/manual532 不能直接比较复振幅，也不能为对齐删模式或换相位。

这三步是两个新求解加一轮后处理/交付，不增设新的研究分支或框架。主线在 response_v4.md 一并回应 V3-A、V3-B 和本 V4；若该 response 已存在，沿现有执行序号继续，不覆盖既有正式回执。

### 5.2 dot 的互补任务：恢复条件满足后再执行

本段是主线与 dot 的接口分工，不是宣告云端现在可运行，也不指令主线修改 dot 分支。沿 dot 现有恢复合同推进，源码入口和执行命令尚未资格化，不能把旧依赖丢失 snapshot 的命令当新一键入口。

| 顺序 | 最小工作与收益 | 本轮边界 |
|---|---|---|
| C0：实际运行条件恢复 | 获得允许访问的官方 complex FE/PETSc 栈；记录实际 ABI、MPI/线程、索引/后端范围，落实持久 ignored raw 位置与完整进程监督 | 包源继续不可达就保持 FE NOT_RUN；不重复 27+4 纯测试来代替进展，不要求主线替云端搬家或安装 |
| C1：一个自包含 fresh 三维 fixture 的表示与恢复验证 | 先在实际 p6 单元缓存验证 dense 与 compact 原始 H/Di/XiB、任意内部与非零端口 RHS、全部内部恢复；再由同一 fixture 建立当前支持的 p4/manual532 全 q regular/notch 对照，用独立完整原方程与全输出验证 | 复用已有组件，限一个几何与一组小网格；p6 组件 PASS 与 p4 全链 PASS 分开，不能称 p6 全链已通过；不重做 X/XZ/Y 扫描 |
| C2：复用该 fixture 的后端和 AUTO 成本探针 | 公共后端先过 tiny complex 非 Hermitian 单块，再接同一组实际 q 块，记录完整因子填充、重复回代、所有因子并存成本；随后在完整 AUTO keys 下测一个有界代表端口/投影块 | 后端比较使用同一矩阵与 RHS，隔离表示变更；AUTO 只做结构/表示和计时探针，不启动原尺寸分解或完整 PDE |

C1 必须包括两个会被错误实现漏掉的输入：**非零内部 RHS 和非零端口 RHS**。在同一 fresh FE 对象上与 dense 对照，比较原始 H 解和消元后 action，恢复全部内部自由度、周期 slave 与全部 q/alias，检查原方程。独立 checker 重新生成并保存原始证据，不能读取旧已丢失数组；历史只读 pivot 崩溃和被中断的 checker 仍分别保留失败/UNKNOWN 身份。新旧后端切换不得与表示更改混成一次无法归因的比较。

C2 的 AUTO 探针先重新生成原尺寸完整 ordered keys 与 digest，保留 32,060 为旧传播库存对照，不预设它就是最终 M。当前入口的 p4/532 限制必须通过参数化支持映射及小例等价验证后才能扩展；若尚未完成，就报告该具体阻塞，不以删断言绕开。探针至少记录实际求积节点、JIT 峰值、C/D 支持、Di/XiB 缓存、最大投影矩形 lp×rq 及字节、CSR 转换/累加峰值。可以分批处理完整模式以限临时内存，但不能抽掉物理通道或把单批峰值说成完整全流程峰值。

先完成 C1 才进入 C2 的实际 q/AUTO 接线；公共后端若卡在必要阶段 API，继续保留已有 SciPy 的小型对照资格和 AUTO 结构结果即可，**原尺寸后端保持 held**。不为本轮额外发展私有 FFI 或大型全新求解器。

### 5.3 双方交接与避免重复

主线负责物理精度、统一观测量、Gx/Gz 选择和主任务集成要求；dot 负责低内存表示、完整参考逆/内部恢复、两单元周期分块、后端及规模校准。dot 不另做一套背景和网格收敛扫描，主线不重新实现其低内存 H 或周期参考解。

交接时按同一物理身份建立后续同离散小例，才比较完整 observable vector：总/散射 E、H/curl，全部通道复振幅及功率、R00_s/R00_p/R00_total、R/T/A_balance/A_volume、原残差。当前两条线的不同配置先并列，不假造等价。跨分支只提出经过审阅的最小文件级移植清单，不整体 merge/cherry-pick；本 review 不修改 dot，也不改变正在运行作业的源码。

## 6. 验收、资源和有界停止

| 对象 | 必须满足或明确记录 |
|---|---|
| 主线新离散求解 | 沿用原 A6 真残差 ≤1e-6、准确 p4 原 A4 目标 1e-10及既定精化限制；有限场、完整端口/约束检查、能量闭合 ≤1e-5；正式输出只来自通过残差门的场 |
| 主线工程精度 | 总/散射 E/H/curl 相对差 ≤1%，冻结显著通道复振幅 ≤1%，R/T/A/A_volume 绝对差 ≤1e-3；列所有实际值与两失败模式，不能只报通过数 |
| 配对方向判断 | 同物理、同坐标/体积、同背景/分母、同 keys；绝对与入射归一化值作为诊断保留；禁止拟合相位、换背景/分母、删模式改判 |
| dot fresh 组件及同离散对照 | fresh FE 的 dense/compact action 与完整恢复相对差 ≤1e-11，完整原方程真残差 ≤1e-10；既有纯代数测试仍保留其 1e-12 容差。列全部实际 q、各非零 RHS 的绝对/相对差；近零输出的绝对阈值按物理单位在运行前冻结。残差通过不授予目标物理精度 |
| 本机资源 | 沿主任务 physical-memory-pressure policy 读取实际 RAM/cgroup、MemAvailable 和 OS 余量；每场冻结适用限值。F3/F5 的 4.01/7.75 GB 是历史用量，不是任意新 cap，也不自动准入 2 TB |
| 云端小资格 | 开始 JIT 前按实际容器余量冻结硬限；可用历史 3 GiB、4500 s/worker 和 checker 各阶段作为规划上界，实际可用量更小时收紧；这不是目标规模估计或新环境实测 |
| 原尺寸最终资源 | 整机同时占用 ≤2e12 B，swap=0，端到端 ≤172800 s；全部并存因子、缓存、JIT、外层/恢复向量、输出与系统余量在账。OOC scratch 与 swap 分开，当前小资格不靠二者撑预算 |

正式运行一次一个 heavy case。有限、已通过且身份未变的昂贵 Gate 不因本 review 文档更新重跑；相关源码改变才重跑受影响 anchor 与必要测试。进程树受控停止并保存阶段与资源记录，OOM kill 不能作为合格限额停止。云端总时长按实际 JIT/worker/checker 流程记账，不把历史 caps 或阶段计时称为48小时验证。

| 遇到阻塞 | 有界替代与终点 |
|---|---|
| Gx/Gz 已在执行或分支有未提交改动 | 接续现有任务、单独整理 review 拉取；不 checkout/reset 覆盖，不并发启动同 case |
| 主线保存场确实缺失 | 先核对现有 artifact 索引一次；仅缺输入允许定向重建对应锚点并记录新身份，不整批重跑；若本机资源不允许则报告具体缺项，不拿采样或不同几何补齐 |
| B 未支持预期或仍超 1% | 完成四角结果、指出最有效方向/混合项；停在这两个新配置，不补扫 p、M 或更多网格 |
| 个别实现错误导致失败 | 仅局部修正并重跑受影响项；每个新 case 至多一次修复重试，新的物理配置需下一轮审阅 |
| 云端官方包源/实际 ABI 仍不可用 | FE/PETSc 维持 NOT_RUN；提交已有恢复状态即可；主线继续 B，不周期性重复纯代数证明 |
| 新 checker 再崩溃、原残差/恢复不符 | 保存真实失败，定位当前单个 fixture；不得继承旧 PASS，也不升级规模 |
| AUTO 投影块、JIT 或因子填充超过冻结小预算 | 保留已测支持尺寸、分配前字节和阶段成本，以明确瓶颈结束；不裁模式、增 swap 或直接换到2TB大机 |
| 公共后端不能提供合同要求的分级准入/整数范围 | 小型已资格结果按范围交付，原尺寸后端 held；不把创建因子对象写成 analysis PASS |

## 7. 到原尺寸还缺哪些实证，下一回执交什么

| 原尺寸缺口 | 当前证据不足之处 | 下一轮能推进的部分 |
|---|---|---|
| 离散与物理精度 | 当前缩小模型散射 E/H 和两模式仍超门；原尺寸、y 方向、端口截断尚未收敛 | 主线 B 给出下一次网格投入依据及可靠完整观测量 |
| 低内存表示的整体收益 | 一个 H 向量很小，但投影临时块、C/D、恢复缓存未在 AUTO 下测量 | dot C1 证明真实接线，C2 测实际对象与投影瓶颈 |
| 分解填充与内存 | 未知原尺寸各 q rows/NNZ、LU 填充、所有因子共存峰值与安装版索引限制 | 同一 fresh fixture 校准真实后端和生命周期；不能用旧每 q policy allowance 外推 |
| 完整必要耗时 | 原尺寸 JIT/组装、setup、回代、外层迭代、恢复/校验均无闭合预测或实测 | 小例分阶段成本和 AUTO 端口成本先测；保留强缺口迭代未知项 |
| 便携运行与证据保存 | 新 FE 栈及完整入口尚不可运行，旧 raw 不可用 | 官方栈恢复后 fresh 自包含资格与持久 artifacts；未满足则保持 held |
| 未来三维缺口 | 历史弱小缺口可解，但不同 Y 几何不能充当同场收敛 | 保留全内部自由度、全部 q/alias 和原三维 outer；以后强缺口另需证据 |

主线下一回执必须集中给：两个 B case 身份与统一数值表、四角归因及否证结果、原精度门逐项通过/失败、资源 scope、源码/测试/场 hash、接口包与 dot 已完成/未运行边界，并更新既有 summary/模型总账的相应记录。停止项也写入 response_v4，不为凑完整状态补运行。无需新建平行补充任务书。

**待落实事项不是现在向用户索取新的许可：** 执行端确认 Gx/Gz 当前本地状态；dot 获得可访问官方依赖及持久 raw 位置；双方后续冻结同物理接口与完整 AUTO keys；大规模后端的阶段准入和实际整数范围待 fresh 验证。上述条件未满足时，本轮只交付其明确范围内的结果，不能宣称原尺寸已可在工作站开跑。

主控 Codex 可直接按下文执行：

> 从 canonical clone 的 task40extra_0p7nm_engineering 跟踪分支获取本 Review V4；审阅基准为 f376dfa00c554c6d15413f1f8f887d43eb361b9d，dot 只读基准为 4a4360db8ae3d00692b69005f3a808639b87949f。先检查现有作业和未提交修改，安全 fast-forward，不打断在跑任务，不改 dot/master。主线 A 已接受，直接接续既有 B：Gx560(10×4×14) 后 Gz528(6×4×22)，复用 F3/F5、p6/准确p4/M2全340模式、MPI1/threads1；相同配置已有合格结果就复用。完成四角公共体积 E/H/curl、全部复模式、两失败通道、功率、绝对/入射归一化差与混合增量；按原门槛及预登记否证规则判定，不拟合相位或更换分母。一次一重任务，沿实际内存压力与零swap策略；最多两种新网格，失败至多一次局部修复重试，结果不支持假设就停并据实报告。同步输出轻量物理/模式/相位/恢复接口包；本机不实现 dot 的低内存 H、周期分块或新后端。dot 待官方 complex FE/PETSc 环境恢复后，按本 V4 C0→C1→C2 完成一个 fresh fixture 的表示/内部恢复与全q对照，再测公共后端及有界AUTO投影成本；旧PASS不继承，新环境未验证项仍为NOT_RUN，最终旧checker仍UNKNOWN。本轮不启动原尺寸计算、不宣布工作站就绪。将结果、失败/停止、测试和hash索引写入下一正式response及既有summary/总账，提交并推送主线，返回完整SHA与证据入口待审。

交付核验范围：本次检查了 Markdown 表格列数、链接目标及只新增本文件的提交差异；没有运行数值测试。当前 GitHub 网页抓取返回 Cache miss，rendered-view Gate 尚未核验，不将结构检查冒称网页渲染通过。
