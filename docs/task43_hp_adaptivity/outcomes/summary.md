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
| 完整场比较组件 | 原始 N1curl 电场及旋度转为逐单元 DGQ6 后与解析多项式一致；串行和 MPI2 采样、集体拒绝扭曲单元的测试通过 | 公共积分采用所有比较网格的断点并集；完整模型比较尚未运行 |
| p6 carrier 张量组件 | Task43 实际完整 curl+mass/q15/default grating 单元的 FFCx 与 BlockedGram 矩阵相对差 1.7235×10⁻¹⁵（门槛 1e−10）；p6 carrier 上 active p3 builder 定向重试 4 项通过 | [张量组件记录](records/p6_tensor_component_v1.json)；首轮接口失败日志保留 |
| 36 单元小模型与独立 A6 | attempt1 **数值门失败**：active 预检查残差 1.6445×10⁶⁴，A6 未调用；attempt2 使用已授权的边界幅值缩放后，solver、完整独立 active action 和两级残差门均通过。A6 relative residual 为 8.7763×10⁻¹³（task gate 1e−6、小模型门 1e−8）；独立行数为 trace 1782 + cell interior 1296 + modal lower 612 | [attempt1 负结果](records/a6_component_attempt1_v1.json)；[attempt2 组件记录](records/a6_component_attempt2_v1.json)；全量逐模态数据留在 ignored artifact |
| 真实场接线级锚点 | 三个 36 单元 h100 算例均通过同阶、完整场/端口和 MPI 等价 Gate | 属于 `numerical_sanity_only`；冻结 180 单元起点、正式 R/T/A 精度和自适应收益仍为 `not_run` |
| 自适应闭环与成本 | `not_run`：accepted updates=0；尚无同精度成本优势 | 后续实施范围 |
| 迭代与 0.7 nm | `not_run`，等待前置 Gate | 不启动额外 campaign |

局部 p 自适应通过增加选定单元及共享边、面的多项式阶次来提高表达能力；局部 h 自适应把选定单元分成八个更小单元。二者均需额外约束，保证相邻单元和周期边界上的场能够正确连接。当前组件验证只说明这些空间与装配操作局部一致，还不能证明真实散射解更准确。

场比较需要在同一物理位置评价不同网格的解。当前组件把每个单元的原始高阶电场及旋度复制到能完整容纳这些多项式的独立单元表示（DGQ6），再用共同积分点计算差异，避免低阶可视化输出丢失细节；代价是额外临时场存储和采样时间。残差则衡量把解代回离散方程后还剩多少不平衡，残差不过关时不能用输出功率证明物理解正确。

新增 p3 测试曾暴露一处梯度秩误判：旧判据使用 QR 分解对角元估计独立方向数，把应为零的常数梯度误算为额外方向。现改为奇异值分解的标准浮点秩判据，并以常数核、curl-grad、方向变换及局部凝聚恢复交叉验证。阈值尺度随判据改变，不能表述为“阈值数值不变”。旧 p4 哈希失败另属起始源码在当前环境下已存在的身份差异；未修改旧 golden。

用户指定最终对照为 50×50×140 nm、6×10×6、uniform p6。该信息只用于选型完成后的独立精度及自由度比较，不进入标记与候选排序；不宣称整个研究从未知道对照。独立有限元自由度的公式估计为 237600，仍须用实际约束审计核对，不能与凝聚后的矩阵行数混称。参见[对照合同](records/final_control_contract_v1.json)与[推导计数](records/uniform_dof_estimates_v1.json)。

attempt1 与 attempt2 是两个独立结果，均保留。attempt1 使用未缩放衰减模态并在进入 observer 前因 active residual 超门而失败；attempt2 启用 `boundary_magnitude_scaled_r5_v1` 后，36 单元、uniform p3-on-p6 的同类组件算例完成。attempt2 的 condensed true relative residual 为 3.0631×10⁻¹³；独立重组的 FE trace、cell interior 和原始 modal lower 行残差范数分别为 4.2934×10⁻¹³、5.5804×10⁻¹³ 和 1.1028×10⁻¹³。primary modal R/T 为 0.9999860056 / 1.15824×10⁻⁵，`A_volume_total` 为 2.4120155×10⁻⁶，`R+T+A_volume` 与 1 的差约 1.83×10⁻¹³。这些量来自 `numerical_sanity_only` 组件；runner 内部 `official_result=true` 不代表 Task43 正式模型或精度结论。attempt2 runner 总时长约 541 秒，完整 pytest 595 秒；A6 observer 在报告中只记录合并区间，编译与后续 action 未分别计时。单 rank 历史 RSS 峰约 1072 MiB，不是编译子进程计入的进程树峰值，也不是资源 Gate。

这三个 36 单元 fixture 都不是冻结的 3×10×6 起点。它们已验证同一几何上，原生 p3 有限元空间与 p6 载体上的空细化 active-p3 空间给出一致的全域场和 612 个端口模态；同一个 active-p3 算例在 MPI1/MPI2 下也一致。它们仍不能证明更细网格上的精度、自适应收益或完整任务完成。当前 variable-p 装配仍经过 axis-coordinate 的 12 位小数 canonicalization；后续三等分参考路径需审查这一近似，不能把现有 raw-tensor 单元比较解释为整条装配链都使用未舍入坐标。

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

复现和逐字段证据见[三锚点 compact record](records/h100_anchor_triplet_v1.json)，原始 solver records、q8/q10 场、模态 JSON、日志和源码快照按其中路径及 SHA256 绑定；全部大文件保留在 ignored `benchmarks/artifacts/task43/h100_anchor/`。下一阶段是补齐正式 180 单元任务的资源 Gate、未舍入几何身份及参考场角色/完整场资格，再开始真实候选闭环；本三锚点不提供候选排序依据，也没有运行最终 p6 对照。
