# V37：函数张量列车神经场的单场准入说明

**唯一裁决：EVIDENCE_INSUFFICIENT。** FTTNN 确实改变表示方式：三个小网络产生矩阵值函数，连乘后直接给出三维复电场，避免保存每个波形在所有有限元自由度上的大列库。已形成具体设计和一个可证伪的最小试验，但现有文献与保存证据不能证明本问题所需的秩、训练收敛或冷单场成本机会。它不具备实施、训练、生产或初始化许可；本轮完成准入说明后保持空闲，等待明确授权。

执行权威为 [Review V36](../review_report_v36.md)，读取版本 e5e282d830f377c86e119db56d5d84f6daed0b9c，结果基线 4543797060bac8f4d8341d8d5d797be285a1cd2d，原 base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。[紧凑记录](records/neural_restart_admission_v37.json)分列原证据复用、本次整数形状推导、文献范围及未运行项。本轮没有新 FE、矩阵作用、网络前向、训练或参考场数组读取。

## 1. 已回答的旧问题

以下均复用同 M5：5nm、384hex、p3、31968 独立复 FE、40 端口；没有加载、移动或重新封存大数组。最小残差问“能多好地满足原方程”，最佳 G 场问“知道答案后能多好地表示场”，两者幅值不同。

| 原 measured 量，无量纲 | 学习冻结空间 | 确定性控制空间 | 原门及结论 |
|---|---:|---:|---|
| 列数 / 有效秩 | 1377 / 1377 | 1377 / 1377 | 全部保留，非删列空间 |
| 最佳 native 原残差 | 0.14318770428345817 | 0.1444069377900675 | 1e-6；均失败 |
| 最佳实际 G 相对场误差 | 0.0031762428063071215 | 0.003101530777126289 | E/curl 同过 1e-4 的必要条件不满足 |
| G 正交缺陷 | 1.73855719961e-12 | 1.89881487604e-12 | 1e-9；原资格通过 |
| 最优性相对缺陷 | 7.53770161444e-14 | 2.60110871427e-14 | 1e-9；原资格通过 |
| 原点值网络完整矩重建 | 2.00725127960e-13 | 1.23951167651e-14 | 1e-10；原资格通过 |
| 原方程 / 全场 / 功率联合 | FAIL | FAIL | 原 [完整 Gate](records/joint_gates_v36.json) 不改 |

以上末尾位数以 [oracle 原记录](records/field_oracle_v36.json)及 [Response V36](../response_v36.md)为权威；本轮不重新赋予数学资格。原残差证据为 [V35 A](records/unlabelled_optimality_v35.json)。完整保留与映射稳定支持**这两份冻结空间的浮点数值排除**，不等于区间证明，不否定所有 FEINN，也不证明可变波矢的全局最优。V35 的未完成、930 日志无可恢复基、全部费用和旧 UNKNOWN 仍保留；当前最佳场答案已知，不再列为待算。

CURRENT_DENSE_WAVE_SOLVER_FAMILY_CLOSED / FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED / NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE。M3600 较好时刻、最终退化、D0 成本否决与 D1 未运行均保留。oracle 仍是参考暴露的表示诊断，不能算无标签 NN 成功。

## 2. 文献实际支持与不能移植的部分

已读固定 v1 的 HTML 方法、近似定理、实验正文及结论，未复现实验或检查 PDF/图像数值。Feng 等的 FTTNN 用一维神经核连乘，物理残差训练采用 Adam 后接 L-BFGS；其积分分解需源项、系数的 FTT 表示。实验为标量问题；高波数例子使用较低波数训练结果逐级初始化，不能当本案从零冷单场证据。见 [原论文 §2–4，2510.13386v1](https://arxiv.org/html/2510.13386v1)。

该论文的 L2 近似存在性没有给出本案固定小网络、复 H(curl) 误差与所需秩的上界。本项目的非可分 Si/air 缺口、复材料、Floquet 和 DtN 不被上述便宜一维积分自动覆盖。下述设计保留原 FE 算子，不压缩或改写材料，不采用论文的可分 loss 积分捷径；因此那项文献积分优势不列入收益。

Maxwell 张量网络论文只读原摘要：常材料、空间—时间谱配置及 TT；它没有神经训练，也不是本频域有损 Nédélec 散射的资格证据。见 [Adak 等，2512.15631v1 摘要](https://arxiv.org/abs/2512.15631v1)。仅作为边界参照，不宣称全文或实验复现。单纯对已知 FE 场做 TT-SVD 属于传统分解，本设计不以此冒称训练或独立求解。

## 3. 唯一候选的准确形状（PROPOSED_NOT_IMPLEMENTED）

每个物理分量 s 使用秩链 (1,8,8,1)。三个轴各一个 MLP：标量归一化坐标输入、两层 16 宽 sine 隐层、线性输出；轴内三个分量共享隐层，但输出分开。两层、宽度和秩是本说明的固定假设，不是论文给出的本问题参数。坐标由真实 nm 盒的中心与半宽归一化；不添加 carrier、监督权重或波库方向。

```math
 E_{\theta,s}(x,y,z)=F_{x,s}(x)F_{y,s}(y)F_{z,s}(z),\quad
 F_{x,s}\in\mathbb C^{1\times r},\quad
 F_{y,s}\in\mathbb C^{r\times r},\quad
 F_{z,s}\in\mathbb C^{r\times1},\quad r=8.
```

| 小网络 / derived | 实输入 | 实输出（实虚配对） | 真正可训练实参数 |
|---|---:|---:|---:|
| x 核：1→16→16→48 | 1 | 6r=48 | 304 + 17×48 = 1120 |
| y 核：1→16→16→384 | 1 | 6r²=384 | 304 + 17×384 = 6832 |
| z 核：1→16→16→48 | 1 | 6r=48 | 1120 |
| 总计 | 三个轴坐标 | 三个 complex128 场分量 | 9072，FP64 实参数 |

权重体积为 72576B，不是程序峰值。所需 rank 为 **UNKNOWN**；r=8 只是一个可证伪的试验点。共享 16 个隐特征进一步限制固定网络，不能用无限宽/变秩存在性定理保证此 9072 参数模型通过。界面法向跳跃、角点及多方向散射可能要求更高秩或更复杂轴函数；本批不进行 rank 估计、压缩、扫描或实现。

拟议初始化 seed4213701：x/y 隐层与输出随机，z 仅最后输出层置零，产生真实零散射。不能将三个核全部置零，否则乘积导数消失。初始 x/y 梯度为零需在 z 首次非零更新后检查全部参数参与；不通过强制扰动伪造学习。核的可逆缩放存在冗余，可能造成梯度尺度问题；其稳定性仍未资格化，不宣称条件数改善。

拟用原 native 欧氏残差目标，完整 A/f 不变：

```math
 c_\theta=I_h^{\mathrm{curl}}E_\theta,\quad
 r=A c_\theta-f,\quad J=\frac{r^*r}{2f^*f},\quad
 g_c=\frac{A^*r}{f^*f},\quad
 g_{\theta,j}=\mathrm{Re}\big((\partial_jc_\theta)^*g_c\big).
```

选择 EUC 是此设计的明示假设，既不是继续原 DUAL 训练，也不是论文 loss 的复刻。旧 EUC/DUAL 优化负结果保持，EUC 与场误差的关系仍可能困难。G 只留给隔离验收的场范数乘法；不在训练中隐含 Gsolve/全局 Gram 因子。若将来改成 Riesz loss，必须另算该因子/求解成本并重新授权，不能保持“无全局因子”声明。

拟议流程为 Adam500（lr1e-3）后 fresh L-BFGS（lr1、history20、strong-Wolfe、max_iter20/max_eval25、tolerance_grad1e-7/tolerance_change1e-9）。每路线总计至多1000完整 loss/gradient closure 或3600s，含加载、线搜索、保存及独立检查前的冻结；不自动重置或加 rank。当前仅为待审方案，执行次数为0。

## 4. 原有限元接口与流式导数

源码核对绑定 e5e282d830f377c86e119db56d5d84f6daed0b9c，读取文本，不 import FE/Torch。接口兼容是静态分析，不是新网络资格。

| 现有接口 | 可复用的物理操作 | 尚需显式适配 / 风险 |
|---|---|---|
| [完整矩构建](../../../src/solvers/feinn_interpolation.py) | 边/面/内部积分、独立 owner、方向变换、Jacobian | 仍用原 moments/orientation/hash；不裁内部矩或小迹 |
| [CompleteMomentMap](../../../src/solvers/feinn_torch.py) | forward 接受坐标到三分量复值模型；Piola 与完整矩，batch1/8；VJP 按块重算 | 构造器当前缓存全部 C×Q×3 坐标；大尺度需经配对的逐块生成适配，本轮未改 |
| [FullNativePacket](../../../src/solvers/feinn_native.py) | 全 FE 局部 A/A*、MPC 展开及原 B/D/H 准确端口消元 | expand 仍有 C×L 全单元数组；load_native 复制 packet，不是已流式的大规模入口 |
| [原优化器](../../../src/solvers/feinn_optimization.py) | 实参数梯度及事务规则可参考 | 当前构造 CoordinateField/8966 参数；不能直接运行 FTTNN，需未来 opt-in model factory/保存 schema |
| [独立验收](../../../src/runners/neural_space_verification.py)、[保存 checker](../../../src/postprocessing/neural_space_saved.py) | FE 物理范数、原方程和原数组 Gate 依据 | 旧波库 exporter 不适合新核；未来需实际模型重建与独立来源分离 |

每次 closure 先无全网格 AD 图地逐块生成完整 c，再做原 A 与 A*，最后逐块重算核收缩，通过完整矩 VJP 累加参数梯度。最多8cell保留图；不构造 N×P Jacobian、N×m 列库、A*A、全 FE 逆或全网格导数图。主要增加的是两次点值网络计算、核收缩和反传。连乘用行向量×小矩阵×列向量，单点主要工作为 O(r²)，不展开 r² 个全 FE 列。

物理点值在全部边、面、内部积分点进入协变 Piola 拉回，方向与唯一 owner 顺序沿原映射；MPC 只按原展开施加一次 Floquet。网络本身可无边界封套，最终 FE 场的周期约束由原 MPC 保证，不能再给 FE 系数乘中心相位或重复乘 Floquet。非可分材料仍由原 cell tags/复系数张量表示，DtN 仍是原完整端口作用；H/curl 从实际 FE 场计算，不用核的空间导数代替 FE 物理场。

任意三维几何的算子处理由原 FE 支持，不代表有限 rank 的轴连乘一定能表示任意三维场。模型导出、真复梯度、非单位双 Floquet 和各自由度族均须未来资格化，当前为 NOT_RUN。

## 5. 完整内存生命周期与保留成本

定义 N 为独立复 FE 数、C 为 cell 数、L 为每 cell 的局部系数数、Q 为完整矩积分点数、b≤8、P 为实参数数、m 为旧波列数、n_port 为端口数、nnz_port 为 B/D 非零数。下表是 derived 对象模型，不是 RSS 预测；未知 packet/workspace/库峰不得用权重大小代替。

| 生命周期对象 / bytes 模型 | 保留或变化 | 峰值重叠与限定 |
|---|---|---|
| 原 mesh/MPC/材料/局部体张量/原 B/D/H | 保留 M_operator(N,C,L,nnz_port) | 装载副本及装配准备仍计费；原目标值 UNKNOWN |
| 全 c/f/r/g_c/trial/已提交备份 | 以6份complex128向量计96N，仅形状清单 | 备份/保存与 trial 可同存，实际释放顺序须核实；不保证只需6份 |
| 原单元展开及 A/A* 临时数组 | 16CL 级及 W_A | 与全向量/packet同存；当前实现未消除 O(N) 局部展开 |
| 原完整矩/方向缓存 | 16×3QL、方向矩阵、owner/J 等 | 全域静态身份必须保留；全坐标缓存当前另有24CQ |
| 拟议坐标与神经核 | 块坐标24bQ；复核输出48bQ(r²+2r)；另有隐层/图 | 仅在未来流式适配通过后不含24CQ；此表达只是对象体积下项，不是AD峰上界 |
| 参数/梯度/优化器 | 权重8P、梯度8P、Adam状态16P；L-BFGS两向量×20对约320P | Adam应在切换后释放；trial/回滚/序列化副本和Torch allocator另计 |
| 端口与物理验收 | 完整B/D/H、alpha、E/H/curl及分块积分 | 路线冻结后独立 FE checker，训练图先释放；输出仍 O(N) |
| checkpoint | 模型/buffers/optimizer/RNG/c/r/身份 | 临时文件原子替换可能和前一完整版并存；计磁盘与序列化内存 |
| 旧 U/Q 与反复全列 QR | 此表示可以不产生32Nm两份库 | 这是相对旧波库的结构删除，不能算相对最佳 FEM 的已测收益 |

必须以同时存活对象、运行时/BLAS/AD工作区和内核采样得到峰值。参数9072的72576B只占其中一项。本轮没有加载 packet，目标 M_operator、Q、N、实际所需 rank、每次 closure 秒数、达到原门的次数及全过程峰均为 UNKNOWN。

训练峰的规划式为 M_operator + M_moments + M_coords + 96N + 16CL + W_A + M_block_AD + M_optimizer + M_runtime；各项都按同一时刻的存活对象记账，不是实测上界。其中 M_coords 当前为24CQ，未来若流式适配合格才改为24bQ；M_block_AD 至少含48bQ(r²+2r)核输出，隐层、收缩中间量及反传额外空间仍 UNKNOWN。验收先释放训练图/优化器，再另计完整FE场、端口和保存副本；全过程峰取训练、保存、验收三阶段同时峰的最大值，不能用“先后运行”漏掉保存时的重叠。

形状例：旧 U/Q 的32Nm在 N=10^7、m=1377时为440640000000B，N=10^8时为4406400000000B；两份库本身就可能越过整机2e12B。假设6份全向量分别为960000000B/9600000000B，但原算子、端口、展开和验收不因此消失。这些 N 不是原尺寸实际 DoF，不能据此宣布本设计已适配2TB或48h。

## 6. 冷单场 N=1 成本否决门

冷单场指一次物理问题从必要准备到完整验收，所有训练费用归属于这一场，不用未来反演/重复查询摊销。相对最佳合格传统 FE，用同精度和同最终输出定义共同保留项；不能将该 FE 本来就没有的 U/Q 当作可删除基线成本。

```math
 T_{\mathrm{new}}=T_{\mathrm{retained}}+T_{\mathrm{data}}+
 T_{\mathrm{learning}}+T_{\mathrm{correction}}+T_{\mathrm{recovery/check}},\qquad
 T_{\mathrm{base}}=T_{\mathrm{retained}}+T_{\mathrm{removable}}.
```

20%时间收益的必要条件是新增项之和≤T_removable−0.2T_base；右边≤0且新增成本>0时立即成本否决。形状算术小检查仅验证此式，不给未测时间填有利值。内存收益则要比较同精度同时峰，不用对象体积相减。完整冷T_base、其中可删除部分、新学习/映射/恢复费用均 UNKNOWN，因此当前20%机会门是 UNKNOWN，不能放行生产。

V1参考的symbolic/numeric/solve分段不是全部冷单场成本；V36快速确定性审计也不是神经求解速度。旧必要前缀10186.178641493432s、V34学习加载packet归属20728.120829955675s、V35失败B5110.947981953854s及所有发布尾段不清零。[旧成本账](records/cost_capacity_v36.json)的冷N=1与项目精确累计继续 UNKNOWN。本次完整日历墙钟及轻检查另记，不与旧项重复收费。

## 7. 一个待授权、可证伪的最小 pilot

**PROPOSED_NOT_AUTHORIZED / NOT_RUN。** 此表是将来若审阅愿意解决证据不足时的单个 M5 试验设计，不是新输入、stage或当前运行指令。它既不研究原尺寸端口工程，也不自动晋级0.7nm。

| 固定项 | 待授权最小试验定义 | 拒绝或判定出口 |
|---|---|---|
| 输入身份 | 原M5/λ5nm/384hex/p3/N31968/40端口；沿V36绑定的native/moments及原Si/air；体/DtN q15，网络矩q30/q60 | 仅恢复声明副本；无精确逆、oracle权重或材料压缩 |
| NN | 上述r8、三核、9072实参数、seed4213701，从零散射 | 不换rank/宽度/seed；非有限梯度或映射不通过先资格化失败 |
| 同能力确定性控制 | 同TT秩/分量，每核元素用固定归一化坐标的Chebyshev0..18，复杂系数自由优化；9120实参数；同完整矩/目标/优化预算 | 属于非神经FTT基函数系数法，不是随机弱控制，不作参考TT-SVD；rank相同不意味两个函数族完全等价 |
| 训练白名单 | native A/f、moments/owner/orientation/MPC/几何；不包含 reference_state、V36 oracle、U/Q或旧权重 | 标签隔离与故意误读负控；任何教师/完成器使本pilot失效 |
| 资格 | 小复核收缩/实方向FD/实伴随；全矩edge/face/interior及非单位双缝；batch1/8；初始化、回滚、原子保存及实际模型重建 | fullJ/全域AD图、大列库或全局Gram/Maxwell因子路径直接拒绝 |
| 唯一未来总窗 | 14400s：资格1800 + NN3600 + 控制3600 + 独立终验3600 + 发布1800；串行/不重开，closure各≤1000 | 是研究停止预算，不是48h成绩；资源门需新的正式授权与实测准入 |
| 冻结输出 | 参数/buffers/实际c/r/全计数/费用/峰/标签/来源；完整边界committed，trial隔离 | 只交网络推理时间不合格；同packet结果与完整冷账分开 |
| 独立评分 | 冻结后只读原V1同p3参考；实际网络与producer分别通过下一段全门 | 不回传参考向量，不按参考误差选best；未过即该固定pilot失败 |
| 收益 | 与确定性同秩控制及已有合格传统FE比较同精度完整N=1时间/同时峰 | 基线冷账缺失则UNKNOWN；失败候选较快或模型较小不是20%NN净收益 |

固定控制不是复制传统 Maxwell 求解器；它在同 TT 函数空间内优化固定一维基的系数，两路线都不由传统完成器补齐 FE 场。其参数略多于 NN，学习策略相同；确定性基也可能不足，不能将两条都失败解释为 NN 更好。对该固定 rank/预算的否决能否定此具体设计，不能否定所有 FTTNN。

联合门保留：native/增广/独立total各≤1e-6；total/scattered E/H/curl、六点复场和四类完整40模式向量各≤1e-4；R/T/A/A_volume、体吸收一致性及独立能量≤1e-5；逐级功率≤1e-6；实际模型/MPC/端口恢复≤1e-10；网络完整矩及原作用、FE场求积复核≤1e-8。原函数、FE插值与实际物理场误差分列。不能以平面波/制造态/loss代替真实缺口 Gate，也不把同p3通过称连续精度。

## 8. 投入决定与本轮交付边界

机制差异与小网络形状已具体化；全文证据不支持将其标为生产候选。关键未验证项是复向量完整矩兼容、r8的真实精度、乘积核优化/尺度稳定性、native全场成本，以及同精度冷N=1的20%机会。当前统一裁决 EVIDENCE_INSUFFICIENT，保留 PROPOSAL_ONLY_NOT_QUALIFIED，实施/训练/新PDE/初始化/merge 均为 false。

本轮只做源码文本/紧凑记录阅读、整数形状和文档一致性检查；资源及有限实际呈现范围见唯一[记录](records/neural_restart_admission_v37.json)。没有变更 src/input、旧task/review或其他工作树；没有注册新stage。网页失败或未知不转换为数学失败，也不触发健康数值重做。

最终目标仍是原50×25×140nm、Si17/120nm、λ0.7、完整3D Nédélec/双Floquet/完整DtN、全部内部及E/H/衍射/体吸收，在整机十进制2e12B、ownswap/OOC0和连续172800s完整冷流程内通过原门。目标未达；本支当前不能承担它。交付后等待该机制的明确审阅授权，不生成重命名试验或其他支线任务。
