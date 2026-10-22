# Task43 执行进展

| 范围 | 当前实测状态 | 证据 |
|---|---|---|
| 工作区与分支 | 复用 NN-Lab-V2 注册 worktree；跟踪既有 `origin/task43_hp_adaptivity`；初始 HEAD `0a625d770e1d3638bf53016a72facecfc8c81407`，基线祖先核验通过 | [工作区与环境](records/workspace_environment_v1.json) |
| 运行环境 | 复用 Task40 pord64 activation，complex128/int64；原通用 activation 缺失 MPC，未用其启动正式 PDE | 同上 |
| 旧成果 | 旧分支保留；按用户后续授权删除旧 Task42extra 大型 artifacts/results，保留删除前路径与体积；这些大文件本地已不可回放 | [清理记录](records/old_artifact_cleanup.txt) |
| p3/p4 局部核心 | 参考空间、实际实体阶次映射、周期约束、复数装配及内部场恢复定向测试通过 | [G1 组件记录](records/g1_components_v1.json) |
| p4–6 兼容 | 参考空间模块 9 项通过，既有阶次计划及 local-h 内部阶次回归通过 | 同上 |
| 悬挂约束 | 17 项通过，1 项旧 p4 字节哈希失败；初始源码与修改后矩阵在当前 ABI 下逐项相同 | 同上；失败不改为通过 |
| one-level 联合 h/p 组件 | p3/p4、p4/p5 的 9↔12 单元独立已知场检查通过；真实 36 单元空 h active-p3 的独立残差、同阶完整场/612 模态对照和 MPI1/2 对照均通过 | [mixed-p 组件](records/mixed_hp_9_to_12_component_v1.json)；[三锚点记录](records/h100_anchor_triplet_v1.json) |
| 完整场比较与首轮选择 | 冻结180单元active-p3 current及Y6_1/Y6_2共同q8/q10积分选出46个单元；p-up通过冻结中间接受门并被接受为transition 1，accepted updates=1；h算例受控停止，资格状态unknown | 固定入射尺度 η_G 从0.4280717降至0.2927588；h缺独立A6/完整场/Task43记录；Y5_1及最终6×10×6 p6对照未读 |
| Round-2 p-up 与残差修正 | 原 p-up 尝试完成内部有限元场恢复后，在 live-observer 入口因旧 full-active residual 9.1353×10⁻⁸ 超过 1e−9 preflight 而失败；Task43 完整场 checkpoint/采样未写出，独立 A6 未运行。默认关闭的 same-LU 修正已在 mixed-p 组件中验证，正式重试待运行 | [修正组件记录](records/same_lu_residual_correction_component_v1.json)；不构成新接受转移或精度结果 |
| p6 carrier 张量组件 | Task43 实际完整 curl+mass/q15/default grating 单元的 FFCx 与 BlockedGram 矩阵相对差 1.7235×10⁻¹⁵（门槛 1e−10）；p6 carrier 上 active p3 builder 定向重试 4 项通过 | [张量组件记录](records/p6_tensor_component_v1.json)；首轮接口失败日志保留 |
| 36 单元小模型与独立 A6 | attempt1 **数值门失败**：active 预检查残差 1.6445×10⁶⁴，A6 未调用；attempt2 使用已授权的边界幅值缩放后，solver、完整独立 active action 和两级残差门均通过。A6 relative residual 为 8.7763×10⁻¹³（task gate 1e−6、小模型门 1e−8）；独立行数为 trace 1782 + cell interior 1296 + modal lower 612 | [attempt1 负结果](records/a6_component_attempt1_v1.json)；[attempt2 组件记录](records/a6_component_attempt2_v1.json)；全量逐模态数据留在 ignored artifact |
| 真实场接线级锚点 | 三个 36 单元 h100 算例均通过同阶、完整场/端口和 MPI 等价 Gate | 属于 `numerical_sanity_only`，不能代替空间精度证明 |
| 正式 180 单元起点 | 3×10×6、active p3；独立 A6=2.3848e−10，condensed residual=6.3065e−11，能量闭合差3.2516e−13；15,120独立 FE DoF | [正式起点与参考恢复](records/initial_current_and_reference_restore_v1.json)；只通过离散求解门，空间精度待比较 |
| 丰富参考的原场恢复 | Y6_1/Y6_2 的576单元p6系数、网格/周期约束与历史612模态身份吻合；12,800点E差0，H相对差约8.7e−16 | 同上；只取得恢复身份，不等于完整参考精度、q/R14或侧壁资格 |
| 自适应闭环与成本 | p-up候选通过冻结噪声规则并按保守单位独立DoF得分接受为transition 1，accepted updates=1；h资格仍unknown；同精度成本优势未建立 | [transition 1选择及成本记录](records/round1_selection_transition1_v1.json)；p-up比较与h受控停止原始记录见下表 |
| 迭代与 0.7 nm | `not_run`，等待前置 Gate | 不启动额外 campaign |

局部 p 自适应通过增加选定单元及共享边、面的多项式阶次来提高表达能力；局部 h 自适应把选定单元分成八个更小单元。二者均需额外约束，保证相邻单元和周期边界上的场能够正确连接。当前组件验证只说明这些空间与装配操作局部一致，还不能证明真实散射解更准确。

场比较需要在同一物理位置评价不同网格的解。当前组件把每个单元的原始高阶电场及旋度复制到能完整容纳这些多项式的独立单元表示（DGQ6），再用共同积分点计算差异，避免低阶可视化输出丢失细节；代价是额外临时场存储和采样时间。残差则衡量把解代回离散方程后还剩多少不平衡，残差不过关时不能用输出功率证明物理解正确。

新增 p3 测试曾暴露一处梯度秩误判：旧判据使用 QR 分解对角元估计独立方向数，把应为零的常数梯度误算为额外方向。现改为奇异值分解的标准浮点秩判据，并以常数核、curl-grad、方向变换及局部凝聚恢复交叉验证。阈值尺度随判据改变，不能表述为“阈值数值不变”。旧 p4 哈希失败另属起始源码在当前环境下已存在的身份差异；未修改旧 golden。

用户指定最终对照为 50×50×140 nm、6×10×6、uniform p6。该信息只用于选型完成后的独立精度及自由度比较，不进入标记与候选排序；不宣称整个研究从未知道对照。独立有限元自由度的公式估计为 237600，仍须用实际约束审计核对，不能与凝聚后的矩阵行数混称。参见[对照合同](records/final_control_contract_v1.json)与[推导计数](records/uniform_dof_estimates_v1.json)。

attempt1 与 attempt2 是两个独立结果，均保留。attempt1 使用未缩放衰减模态并在进入 observer 前因 active residual 超门而失败；attempt2 启用 `boundary_magnitude_scaled_r5_v1` 后，36 单元、uniform p3-on-p6 的同类组件算例完成。attempt2 的 condensed true relative residual 为 3.0631×10⁻¹³；独立重组的 FE trace、cell interior 和原始 modal lower 行残差范数分别为 4.2934×10⁻¹³、5.5804×10⁻¹³ 和 1.1028×10⁻¹³。primary modal R/T 为 0.9999860056 / 1.15824×10⁻⁵，`A_volume_total` 为 2.4120155×10⁻⁶，`R+T+A_volume` 与 1 的差约 1.83×10⁻¹³。这些量来自 `numerical_sanity_only` 组件；runner 内部 `official_result=true` 不代表 Task43 正式模型或精度结论。attempt2 runner 总时长约 541 秒，完整 pytest 595 秒；A6 observer 在报告中只记录合并区间，编译与后续 action 未分别计时。单 rank 历史 RSS 峰约 1072 MiB，不是编译子进程计入的进程树峰值，也不是资源 Gate。

这三个 36 单元 fixture 都不是冻结的 3×10×6 起点。它们已验证同一几何上，原生 p3 有限元空间与 p6 载体上的空细化 active-p3 空间给出一致的全域场和 612 个端口模态；同一个 active-p3 算例在 MPI1/MPI2 下也一致。它们仍不能证明更细网格上的精度、自适应收益或完整任务完成。后续显式 Task43 profile 已将 variable-p 体张量的几何/缓存身份切换为 `raw_unrounded`；local-h forest及拓扑box key仍保留12位舍入，不能宣称整条链都不舍入。本次冻结轴及单层二分坐标可精确表示；历史三等分参考采用其原始 Task40 网格恢复协议。

## 正式起点与丰富参考恢复（G2准备）

正式起点用较少的多项式未知量先求一个场，再将它与更丰富的已存场比较，寻找需要提高表达能力的单元。本次求解采用直接消元，保存了完整恢复系数、实际网格和自由度顺序，使后续可以在新公共积分点重采样。这样避免因缺少场数据而重复求解，代价是额外存储和后处理时间。

| 模型与目的 | R / T / A_volume | 自由度与方程 | 实测成本及结论 |
|---|---|---|---|
| phi90、13.5 nm、3×10×6、全体active p3；正式current | 0.807473677583 / 0.005279003523 / 0.187247318894 | 独立FE=8640 trace+6480 interior=15120；612端口；凝聚系统9252行、2,420,652 used NNZ；p6存储124530 | watchdog395.323s；同时进程树RSS峰1,270,714,368B（1.18345GiB），task VmSwap峰0；完整A6及物理闭合通过，尚未通过空间精度门 |
| Y6_1 selection参考恢复；6×16×6、p6 | 历史功率只随原始身份保留 | 389832个complex128存储系数；历史unscaled模态转换到boundary规范后比较 | 恢复及核对21.776s；E历史样本差0、H相对差8.7304e−16；公共q8/q10比较完成，仍非精度/连续参考资格 |
| Y6_2 calibration参考恢复；不同y分段的6×16×6、p6 | 用于测量参考之间的差异 | 389832个complex128存储系数；同612模态 | 恢复及核对21.254s；E差0、H相对差8.6978e−16；公共q8/q10比较完成，不替代最终holdout |
| Round-1 p-up：46个标记根单元由p3升至p4，180个叶单元 | 0.619051847080 / 0.012126176567 / 0.368821976411；能量闭合差5.7802e−11 | 独立FE=9,887迹+9,792内部=19,679（较current +4,559）；612端口；矩阵10,499行、3,049,725 NNZ | watchdog总时长1,694.686s，进程树RSS峰1,438,400,512B，task VmSwap峰0；独立A6=1.1636e−9、凝聚残差=7.3970e−10；η_G=0.4280717→0.2927588，J∞=556,138.09→367,685.66，按冻结规则接受为transition 1（accepted updates=1），但最终精度未通过 |
| Round-1 h：46个标记根单元请求细化，闭包实际形成600个p3叶单元 | legacy求解器报告R/T=0.552257539825/0.015288131019；`A_volume_total=null`，不是Task43 gated物理结果 | 计划审计FE DoF=25,635迹+21,600内部=47,235（较parent +32,115）；增广矩阵26,247行、6,695,999 used NNZ | watchdog记录`USER_CONTROLLED_STOP`，2,430.829s，进程树RSS峰2,904,961,024B、task VmSwap峰0；solver residual=7.4766e−10。未保存Task43独立A6、完整field/storage或候选record，故h数值资格unknown |

current的R00_s=0.807460398697、R00_p=1.23971e−26，R00_total为两者之和。比较器在所有三张实际网格断点并集上用张量 Gauss 规则重新采样原始高阶电场和旋度；q8 有589,824点，q10 有1,152,000点，两者积分体积均为350,000 nm³。q8/q10 的每单元 G² 贡献最大绝对差为1.64e−11，46个标记完全相同，表明这次标记对积分阶数稳定。此处的 G 衡量电场及其旋度差异，用固定入射场范数处理近零分母；它用于分配下一轮计算，不表示已知连续真误差。

| 比较对象（均以当前场/selection Y6_1 为主） | G 差范数 / 固定入射尺度相对差 | 电场总场 / 磁场 / 旋度相对差（固定尺度） | 612 通道及标记结果 |
|---|---:|---:|---|
| current 对 Y6_1，q8 与 q10 | 358.1505046 / 0.42807173；q8/q10差约3.2e−16 | E=0.42795664；H=0.42818679；curl(E)/k0=0.42818679 | 最大单通道功率差0.5561381（top,0,0,s）；46/180格捕获G²的0.5011251 |
| 校准 Y6_2 对 Y6_1，q8 与 q10 | 0.0038018494 / 4.54408e−6 | E=9.33331e−7；H=6.35816e−6；curl(E)/k0=6.35816e−6 | 最大逐通道功率差4.17448e−8（top,0,0,s） |

两参考的全域 G 差远小于当前相对 selection 参考的场差，因此可用于首轮选择；该参考差只是一次校准观测，不是完整的不确定度模型。逐通道功率使用完整612个有序模态，未拟合全局相位。原始场数组和逐单元贡献的hash、标记 IDs与全量字段见[公共比较记录](records/reference_comparison_v1.json)。Y5_1未读取，最终6×10×6 p6对照不参与标记。四侧壁单侧迹、独立重算参考完整残差及最终精度验收仍未完成。

p-up 将有限参考差降低，但相对场及边界量仍远高于最终 `1e−4` 精度限值。交叉极化幅值略有恶化：`top_p` 固定尺度相对误差从1.9256e−4升至2.3289e−4，`bottom_p` 从3.2090e−4升至4.0044e−4；不应说全部观测都改善。完整612通道、真实独立DoF和方程硬门由比较器从原始字段重算通过。冻结分数下界为2.9678396669976532e−5。h计划与求解路径的实际新增独立FE DoF为32,115，即使假设其 `eta_G=0`，加入同一G噪声后得分上界也仅1.3329622224401209e−5；因此p-up在冻结的单位DoF排名上严格胜出，已接受为transition 1，accepted updates=1。该选择只表示第一轮中间更新，不是最终精度或成本优势。精简判定及证据哈希见[transition 1记录](records/round1_selection_transition1_v1.json)。

h算例完成矩阵分解、回代、旧求解器显式残差及其R/T输出后，watchdog记录受控停止并清理全部子进程。其progress记录分解setup 764.040s、solve 0.665s和旧残差7.4766e−10；这些不能替代Task43独立A6。当前目录没有 `candidate_recovered_solution_storage.npz` 或 `task43_round1_candidate_record.json`，端口记录的 `A_volume_total` 为空，因此无法从R/T或模态数据恢复完整场或计算 `eta_G`、`J_infinity`。h资格状态为unknown/controlled_stop，不能称h Gate通过或数值失败。watchdog只记录收到SIGTERM的时间和整树范围，不存发送者身份；没有证据能把停止归因于用户或工具会话清理。其原始hash索引与资源/失败成本列在上述compact记录中。

主控还从保存的 q8/q10 原始场数组独立重算 G 差及标记；数值与该记录一致。这是审阅侧复算，不是 CI 测试。

Round-2 p-up 首次求解完成内部有限元场恢复后，在进入 live observer 时因原 full-active residual 未过 1e−9 preflight 而失败；Task43 完整场 checkpoint/采样未写出，独立 A6 未运行。保留该失败和资源记录。新增的默认关闭 same-LU 回代只复用原矩阵、右端和 LU 因子，且只在显式 true residual 有限并严格下降时更新原解向量；mixed-p 小算例及 observer/lifecycle 回归通过，但不代表正式 p-up 已重试。首轮 h 的 watchdog 原始分类仍为 `USER_CONTROLLED_STOP`；用户明确表示没有手动停止，停止发送方仍未知，不把记录归因于用户。完整尝试、测试和源码哈希见[组件记录](records/same_lu_residual_correction_component_v1.json)。

本次current基于 `8fe6793e0a5e0689a5435ddf209d095b75b3bd0f` 加已归档dirty源码；完整35文件快照、命令/环境、分阶段时间及原始artifact哈希见[轻量记录](records/initial_current_and_reference_restore_v1.json)。使用既有JIT缓存，395.323s不是隔离冷缓存成本。首轮p-up按冻结单位DoF排名接受为transition 1，accepted updates=1；h已受控停止，h的独立Task43资格unknown，后续仍须取得完整资格证据。Y5_1未参与选择，6×10×6、p6仍仅作最后对照；当前没有最终精度或同精度成本优势结论。

启动包装器曾因可选版本字段及在watchdog父进程提前初始化MPI而退出，均发生在PDE worker启动前；失败日志保留。Y6_1首次恢复误用了Task43简化模态序列化，历史SHA检查失败；改用历史原函数后exact hash通过，未改预期值或覆盖首试证据。后续审核另发现MPI采样的非root提前返回、未参与最后错误广播；已局部修复并通过MPI2成功及域外点集体失败测试。本次current为MPI1，原数据不受该分布式控制流修正影响。

新增的独立小组件把两个相邻单元中的一侧分成八块，得到 9 个叶单元；另行建立把接口切分贯穿到另一侧的 12 单元网格。两者的离散空间与自由度不同，检查采用双方均能表示的已知复数多项式场，右端由原始形式独立积分得到，再比较各自恢复场与已知场，不能解释为任意散射解在两网格上都严格相等。

| mixed p 组件 | 9 叶单元独立 FE DoF | 12 单元独立 FE DoF | 两网格电场相对 L2 差 | 两网格旋度相对 L2 差 | 判定 |
|---|---:|---:|---:|---:|---|
| p3/p4 | 1082 | 1782 | 1.3775×10⁻¹¹ | 9.7871×10⁻¹³ | 小于 1e−8 组件门槛 |
| p4/p5 | 2320 | 3649 | 3.3996×10⁻¹¹ | 9.5386×10⁻¹³ | 小于 1e−8 组件门槛 |

两组原始单元作用的一致性指标均约 1e−14，但其分母是未装配的逐单元作用及右端范数，因此只作为组件一致性指标，不与正式模型独立组装右端归一化的 A6 混称。逐网格对已知场的误差、原始残差范数、日志及源码身份见[9↔12 组件证据](records/mixed_hp_9_to_12_component_v1.json)。

后续选择采用的 G 范数同时衡量电场大小和空间旋转变化，让局部较快变化也能进入网格标记；旋度项先除以波数，以免直接相加不同量纲。它是两个离散场之间的距离，不是已知的连续真误差。为避免弱散射场造成无意义的巨大相对差，归一化还保留固定入射场尺度：本域体积为 350000 nm³，单位入射平面波的电场 L2 范数平方为 350000，G 范数平方为 700000。散射场从总场减去同一解析平面空气/基底背景；共同积分取所有比较网格的断点并集，先用每方向 8 点 Gauss，再以 10 点检查积分扰动，代价是额外采样和积分工作。指标、容差、完整模态分组与四侧壁双侧位置均已写入[比较合同](records/comparison_contract_v1.json)，未运行项仍未获资格。

## 36 单元空细化同阶与 MPI 锚点（G1）

三个算例使用相同的 phi90、13.5 nm 模型和边界拟合网格。它们只相差有限元实现或 MPI 进程数：原生 p3/`standard_full` 给出基准；空 h 代表“保持原网格、不分小单元”，在 p6 载体上求解 active p3；最后把同一 active-p3 算例改为 MPI2。这样可检查新 active 空间是否复现原生 p3，并检查分布式划分是否改变结果。完整比较在共同的 q8/q10 积分点上核对电场、旋度、电场推得的磁场，并逐项检查 612 个有序复模态和功率。

| 算例 | 实际空间和求解方式 | DoF/矩阵口径 | 残差与耗时 |
|---|---|---|---|
| 原生 p3 / MPI1 | 真正 p3 N1curl、`standard_full`，CPU1 | 3540 个有限元存储行含 462 个周期从属行；独立 FE 为 3078；含 612 模态的增广矩阵 4152 行、1,048,424 NNZ | 显式完整 `Ax−b` 相对残差 7.5466×10⁻¹³；runner wall 115.70 s |
| 空 h active-p3 / MPI1 | p6 载体，36 个叶单元全部 active p3，无 h 标记、无悬挂面 | 独立 active FE 为 trace 1782 + cell interior 1296 = 3078；加端口为 3690 行；消去 cell interiors 后矩阵 2394 行、547,386 NNZ | 凝聚 trace 相对残差和旧 full-active 变换残差均 1.2281×10⁻¹²；独立原方程 A6/RHS 2.1429×10⁻¹²；runner wall 280.43 s |
| 空 h active-p3 / MPI2 | 与上一行相同的网格和 active 空间；rank affinity 为 Linux CPU1/29 | 独立 FE 与增广/凝聚行数同上一行；两 rank 历史 RSS 峰值合计上界 1170.0 MiB（不是进程树峰值） | 凝聚 trace 相对残差和旧 full-active 变换残差均 1.3528×10⁻¹⁴；独立原方程 A6/RHS 1.7762×10⁻¹²；runner wall 173.97 s |

两种 p3 空间在相同 36 单元网格上的 q10 电场与磁场相对差分别为 7.7927×10⁻¹³ 和 8.4190×10⁻¹³；固定单位入射尺度下的 G 差为 3.5442×10⁻¹⁵。MPI2 对 MPI1 的 q10 电场/磁场相对差为 6.3581×10⁻¹³ / 4.6890×10⁻¹³。两组比较均核对全部 612 通道并通过 1e−8 Gate。近零 p 偏振通道须同时报告两种尺度：active MPI1 对 native 的 top-p 原始相对幅值差为 1.0730×10⁻⁹，使用固定单位模态尺度后为 4.2345×10⁻¹⁵；本记录保留二者，不能只挑较小者。R00_s、R00_p、R00_total、总 R/T 和 A_volume 均在合同容差内；最大单通道功率差对 serial/native 为 4.4539×10⁻¹⁶，对 MPI2/MPI1 为 3.3307×10⁻¹⁶。独立复核者还从原始 q8/q10 NPZ 与 612 通道 JSON 重算，结果通过；该手工复核不是 CI。

DoF 数必须区分“存储行”“独立有限元自由度”和“凝聚后矩阵行”。原生 p3 的 3540 存储行中 462 行由周期条件关联，所以独立 FE 为 3078。active p3 用 1782 个独立迹自由度和 1296 个单元内部自由度构成同一个 3078 维 FE 空间；另有 612 个端口未知量。凝聚只把内部未知量从全局矩阵中消去，求解后仍会恢复，所以 2394 个矩阵行不表示 active FE 只有 2394 个自由度。三个结果均标记为 `numerical_sanity_only`；runner 的 `official_result=true` 只表示本算例自身数值 Gate 通过，不表示 Task43 精度或自适应目标通过。

复现和逐字段证据见[三锚点 compact record](records/h100_anchor_triplet_v1.json)，原始 solver records、q8/q10 场、模态 JSON、日志和源码快照按其中路径及 SHA256 绑定；全部大文件保留在 ignored `benchmarks/artifacts/task43/h100_anchor/`。正式180单元起点、参考恢复和公共全域场比较已在前文登记；下一步先测更紧求解对场差与标记的影响，再进入真实候选闭环。本三锚点不提供候选排序依据，也没有运行最终p6对照。
