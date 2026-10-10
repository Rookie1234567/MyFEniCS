# V40：用实际内部矩判别FTT秩与固定隐藏特征

**四阶段数值诊断完成，实际FE容量裁决NO_VALID_FE_CAPACITY_CERTIFICATE。** 这不是没有取得数据：张量、完整谱、必要秩与真实隐藏特征结果均已保存；限制在于它们能证明到哪里。纯r8条件性尾能量低于原E门；冻结NN特征在高精度规范矩空间中略高于门，但目前不能据此排除原FP64 FE输出。

## 1. 对象与两条独立路线

对象是原M5：5nm、8×6×8=384hex、p3、31968独立复Nédélec系数及40端口、非可分Si/air三维缺口、原双Floquet/DtN。准确参考只读复用V1，SHA2560c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7。原native、q30矩、材料、mesh/mode和V39两个唯一final checkpoint全部由[run index](records/run_index_v40.json)绑定，不取best/last_trial，不读旧wave oracle。

内部矩把每个小单元的场与标准多项式相乘后积分，类似把场拆成少量互相正交的可测分量；这些分量误差不能大于完整电场误差。因此可以给容量必要条件，但它们不含全部curl/端口信息。实际Basix内部行空间按原元素入口抽取，不硬编码DOF排序；36行/cell、13824唯一内部owner，原MPC只展开一次且内部无slave，orientation与trace交叉项0。x/y/z分量的测试次数分别是Q(2,1,1)/Q(1,2,1)/Q(1,1,2)。

原系数路线使用原interior行、完整逆orientation和真实J推导线性转换。独立路线由原FE basis、中心化顶点拟合的完整J及q15积分得到相同物理矩，同时计算完整散射E范数，不用原interpolation matrix生成第二份答案。物理测试函数由参考Legendre乘detJ^(-1/2)归一；真实Piola分量混合由J^(-1)保留。仅规范对角Cartesian情形具有严格分轴性质；共同Q111子集在一般仿射分量混合下仍处于dual交集，本轮也实际提取并配对，但不能解决物理坐标的非分轴问题。

| measured / derived；原M5、5nm、384hex、p3、31968复FE、40端口 | 实际数字 | 范围与判定 |
|---|---:|---|
| 三分量内部矩shape / complex128字节 | (24,12,16) / (16,18,16) / (16,12,24)；221184B | 由原Basix与cell轴索引得到；不是整树RSS |
| 原系数转换与独立FE积分相对差 | 7.42856038896e-15 | ≤1e-10，PASS |
| 完整测试泛函转换最大相对缺陷 | 1.9299363692e-14 | ≤1e-12，数值配对PASS；不等于任意权重秩证明 |
| 原完整散射E范数 / 独立复核相对差 | 4.92496876599556 / 2.70512909391e-15 | 原全场分母，未换成内部矩范数 |
| 内部矩能量 / 完整E能量 | 0.992386074567 | Bessel配对；不是完整E/H验收 |
| 原J非对角最大值 / 跨轴origin或width差 | 1.92220044999e-15nm / 0 | 非对角未清零；任意权重扰动界NOT_ESTABLISHED |
| 九份完整SVD最大后向误差 / 正交缺陷 | 1.34346623825e-15 / 5.97568460249e-15 | ≤1e-12，PASS；154个奇异值全部保存 |
| 纯r8 / 宽16 / Cheb19的条件性秩下估计 | 1.90261961344e-05 / 1.90261961344e-05 / 1.90261961344e-05 | 均低于1e-4；必要条件未排除，不是容量足够 |
| native最终隐藏 / fit最终隐藏的条件性特征下估计 | 0.000112480113846 / 0.000142785680139 | 均超过1e-4+1e-8；仅固定高精度Cartesian有限矩空间 |
| 固定Cheb19特征条件性下估计 | 7.54083315863e-05 | 低于1e-4；不授求解PASS |
| 实际原FE容量裁决 | NO_VALID_FE_CAPACITY_CERTIFICATE | 小非对角映射未获统一秩桥接，NN特征又近相关 |
| 五次正式attempt总秒 / 同时树RSS采样峰最大值 | 342.630689421s / 347017216B | 含首轮失败、每次成功60sPSI、加载/审核；阶段峰取max |


完整转换在原允许1e-12内数值配对，不被写成任意浮点权重的精确代数证明。原J非对角没有被裁成零；报告同时保存完整测试与Q111子集、独立积分、axis_ids和示例变换。合成axis permutation/shear、非单位双Floquet及角点只用作接口/保留矩资格，明确不是本M5的两个实际非单位入射相位，不拿少量随机例代替秩定理。

## 2. 秩定理、完整谱和真实分母

在已分轴的数学模型中，每个分量由三核连乘构成。单轴积分是线性运算，所以x及z切分秩至多8，y切分至多64；宽16最后隐藏特征加常数使共享y函数维数至多17，Cheb为19。把这些界套到实际FE需要保证原点值→Piola/方向→完整矩→owner/MPC全过程保留该分轴结构。当前小非对角J和全权重范围的扰动界未闭合，故下面只给条件性Cartesian图表数字。

```math
B_R^2=\frac{\sum_s\max_a\left(\max(0,\|\sigma_{s,a,>R_a}\|_2-\delta_{in}-\delta_{svd})\right)^2}{\|E_{ref}\|_{L^2}^2}.
```

同一分量的三个切分尾能量取max，三物理分量能量相加，不能把重叠约束加三次。原完整散射E分母4.92496876599556独立复核，不换成内部张量范数。输入双路线差及SVD后向缺陷都从尾范数扣除，排除还需超过1e-4+max(1e-8,10倍归一化缺陷)。本轮margin=1e-8；这只是浮点诊断，未作区间证明。

九份economy complex128直接SVD完整保存154个值与U/s/Vh，不形成Gram特征值问题、不截取前8个值。全部尾能量及分子/分母在[谱记录](records/rank_spectrum_bounds_v40.json)，完整[CSV](records/capacity_spectrum_v40.csv)可复算。[checker](records/saved_capacity_checker_v40.json)在独立pure进程从原数组重算重构、正交、Bessel、尾能量、原J与margin，没有调用生产算法或生成新网络权重。

| 条件性必要切分秩；顺序x/y/z | E门1e-2 | E门1e-3 | E门1e-4 |
|---|---|---|---|
| 物理x分量 | 0/0/0 | 1/1/1 | 3/2/3 |
| 物理y分量 | 1/1/1 | 4/2/3 | 7/4/7 |
| 物理z分量 | 0/0/0 | 1/1/1 | 3/2/3 |

这些值逐分量逐切分是必要值，不保证它们共同足够，更不保证原残差/curl/H/复通道。0表示该分量的内部矩相对原全场分母本就低于这档门，不是该物理分量可以任意删掉。即使暂按规范图表，r8尾估计1.90261961344e-05未排除目标E精度，因此没有证据直接要求r16或r32训练。

## 3. 两个实际冻结隐藏状态与固定Cheb

native和fit只取V39各自唯一final完整checkpoint；核对模型/buffers/参数顺序/source与标签身份后，读取最后16个sin隐藏特征加常数，输出层幅值不改变。Cheb固定T0..T18只算一次。所有函数来自模型或固定函数库，不根据参考误差补列；参考只用于隔离评分，不生成权重、Adam或训练方向。

| 固定轴函数对象 | 条件性相对误差下估计 | 全列处理 / 实际FP64限定 |
|---|---:|---|
| V39 native最终FTTNN | 0.000112480113845731 | 17列全保留；多数小奇异值低于double输入缺陷，有限80位图表可核，实际任意幅值未资格化 |
| V39 fit最终FTTNN | 0.000142785680139187 | 17列全保留；同样近相关；不是全部可再训练隐藏层的下界 |
| 固定Cheb19 | 7.54083315863183e-05 | 19列全保留，条件稳定；仍受实际J秩桥接限制，不授求解PASS |

先用一份直接SVD报告完整特征谱；近相关时一次固定80位小矩阵SVD/QR核查全部列，不扫描截断/precision，不加ridge。行数不超过列数且完整行空间可核时用全行空间，避免删掉小但非零方向后制造更强“下界”。tall矩阵则保留全部17/19列。native的最小奇异值/输入缺陷比低至约2.60e-5，fit低至约3.29e-4；该数值说明double输入扰动可能改变极弱方向，80位有限数学核查不能自动替代原FP64任意输出系数证明。完整奇异值、保留维数、方法、正交/重构和限制见[固定特征记录](records/frozen_feature_bounds_v40.json)。

特征投影放宽TT耦合秩，因此只能给固定隐藏函数的必要条件；它与秩尾能量重叠，取较强者，不能相加。native/fit的条件性值高于1e-4+1e-8，但actual_FE_certificate均false。没有将参考/fit信息反馈无标签训练、Task42或0.7nm。

## 4. 修复、成本和投入决定

首个正式资格失败保留：直接Basix默认variant与原UFL元素内部dual不一致，插值矩阵相对差1.03600527458。改成原入口定义后原q30 packet逐位匹配，通过三组仿射密度配对和原内部owner/MPC资格，沿同一1800s stage分配重验，未重启总窗。源码392ec0bb→9066ce66；独立checker最小强化源码a706d335，张量/谱保持原hash。28项小fixture包括已知秩8/12、复共轭、错误轴、完整分母、原始数组几何、margin、删列和用途越权负控；Ruff/compile通过，无full pytest、环境重装或旧数值重放。

正式五次attempt（含一次失败）的总实际秒342.630689421，数值payload、准入60s、存盘和checker都计入；最大同时自身树RSS采样峰347017216B，ownswap/OOC0。轻工作及源码阅读/开发/工具等待/发布按同一个14400s连续窗计费，最后至少1800s留给审核发布。额外资源拒绝等待0；原系统max128GiB或10%加384GiB邻增长保留。小张量实际221184B，完整小核对象规划小于256MiB；FE packet/ABI读取是数值角色，pure/ML特征与checker是2GiB角色。[完整资源](records/resource_costs_v40.json)与发布尾账区分互斥wall和嵌套监督秒，不能重复相加；项目精确历史累计、物理冷单场N=1及同精度NN收益仍UNKNOWN/NOT_VERIFIED。

**投入决定：NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE。** 当前r8/native-EUC固定流程继续关闭，旧稠密波族不恢复。规范谱未排除r8，冻结特征信号又缺实际FE全权重桥接；不据此拟造增秩、换优化器或重新命名的生产实验。本批不自动实现/训练后续机制；若未来有新授权，先解决可证的桥接/数值特征条件并定义同能力控制，而不是继续原样EUC。

所有新输出DIAGNOSTIC/reference_exposed=true/pde_only_solve=false/production_initialization_allowed=false/pde_only_solver_qualified=false/official_candidate_results=false。原V39全物理FAIL照旧复用；全部历史较好态、最终退化、D0成本否决/D1未运行、负结果、UNKNOWN与费用永久保留。原50×25×140nm、Si17/120nm、λ0.7完整3D FE/decimal2e12B/ownswap OOC0/172800s与原精度门未达；本批不注册0.7nm、p/h/端口扩展，不恢复W0/W1、传统PC、存储或主线接口。

[Response V40](../response_v40.md)、[run/provenance](records/run_index_v40.json)、[原始修复与失败](records/repair_log_v40.json)、[tests](records/tests_v40.json)。大数组/完整模型/原packet保持ignored原位置，本轮仅新增小型诊断raw及compact引用，没有移动或重复封存健康旧数据。只提交推送本分支，完成后保持自身清场等待review。


## 发布尾段与视觉限定

完整数值及独立checker没有重做。实际GitHub首屏分别访问审阅发布e4d6ca95和文档发布b9853da3417d9537fae0f7be6180b92dda19a4bf；三页均显示服务错误页，未呈现正文/表格/公式，因此全部文档视觉NOT_VERIFIED，没有把截图成功或本地结构检查当视觉PASS。旧网页失败与本次截图/峰值/费用保留。

正式数值阶段最大同时自身树RSS采样峰347017216B；包含浏览器的所有已采样串行轻阶段峰最大632467456B，分别低于16GiB与2GiB，自身swap/OOC0。末次元数据轻任务在CPU准入时被拒绝，worker未启动；原数值不重做，改为复用既有有界fresh_admission并重新实测60sPSI/CPU窗口，不放宽阈值、不改邻任务。原失败CPU sampler细耗时NOT_RETAINED，尾账保守计入拒绝后全部额外日历区间并受900s限制；早期资源记录的拒绝等待0仅是当时快照，不冒充整批最终值。连续窗口尾账含代码、修复、成功60sPSI、失败、保存、审核、Git和浏览器；阶段秒是总wall的子集不能重复相加，最终Git/fetch收尾由ignored交付收据绑定。项目精确历史累计和冷N=1仍UNKNOWN。

[实际渲染失败收据](records/render_check_v40.json)、[发布与自身清场账](records/resource_and_cleanup_tail_v40.json)。
