# V2：固定 M5 的 Gram 对角变量尺度诊断

本批只检验一个具体问题：直接优化全部有限元（FE）系数仍未求准时，各类基函数系数的量纲差异是否妨碍原优化器。把原 Gram 内积的对角开方用于改变优化坐标，可以让边、面、内部自由度在优化器眼中有较一致的尺度；原 Maxwell 方程、弱残差度量和物理场仍由实际系数 `c` 决定。它不能消除所有不定波动问题，也不代表网络有收益。本批没有训练任何新网络。

```math
a_j=\mathrm{Re}(G_{jj})>0,\qquad D_j=a_j^{-1/2},\qquad c=Dy,\qquad g_y=D^*g_c.
```

| 身份 / 单位 | 固定值或实测 | 证据 |
| --- | --- | --- |
| 模型 | 原 M5；5 nm Si/air；384 hex，Nédélec p3，q15；双 Floquet/完整 Fourier-DtN；40 port | [原设计](../../../input/task042extra_feinn_5nm/design_v1.json)、[V2 run index](records/run_index_v2.json) |
| 全部复 FE 未知量 | 31968；边 3744、面 14400、内部 13824；端口仅按原关系消元 | [D0 状态](records/state_diagnostics_v2.json) |
| 原 native / Gram 文件 SHA256 | `2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215` / `2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9` | [预登记](records/scaling_design_v2.json) |
| 新 D 数组 SHA256 | `3d1b8ab9d692c20f884271b4be88165c1e165b7afc83e28967246a87832a1693` | [D0 状态](records/state_diagnostics_v2.json) |
| 新候选 / 初值 | `FREE-FE-DUAL-GRAM-DIAG`；`y=0` 且 `c=0`，原 Adam500＋L-BFGS 参数不变 | [输入](../../../input/task042extra_feinn_5nm/v2_free_fe_dual_gram_diag.dat)、[checkpoint](records/run_index_v2.json) |
| 训练 / compare-only 实际 source | `19c725efd27ae5daedba8e77d2ad98375711bb71` / `bfff1458a389b2c4a4d57112cc771bb33847c20a` | [V2 run index](records/run_index_v2.json) |

## D0：只读旧状态诊断

D0只评估零态和三条 V1 路线的最终已提交态，共4次完整 loss/gradient，低于20次上限；未读取准确参考，也没有重放训练。现有 `history.jsonl` 保存各步 loss/审核与总 closure，checkpoint 只保存参数和实际 `c`。Adam500 审核行存在，但对应的参数快照与 Adam/L-BFGS 优化器内部状态均为 `NOT_RETAINED`；未接受的最后试探态单列，绝不替代最终已提交态。旧线搜索的全部内部接受步长未留存，标记 `unknown_not_recorded`。[原始状态统计](records/state_diagnostics_v2.json)保存每族绝对值 min、p1、p50、p99、max、范数和零计数，以及两个网络隐藏层/输出层参数与梯度分组。

| 家族 / 数量 | `G_jj` p50 / p99 | `D_j` p50 / p99 | 零态 `abs(g_c)` p50 / p99 | 零态 `abs(g_y)` p50 / p99 |
| --- | ---: | ---: | ---: | ---: |
| 边 / 3744 | 123.465 / 123.465 | 0.0899969 / 0.127275 | 8.59298e-6 / 0.00243749 | 8.11565e-7 / 0.000263195 |
| 面 / 14400 | 4260.60 / 6482.76 | 0.0153202 / 0.105888 | 0.000816638 / 0.196132 | 1.99792e-5 / 0.00764477 |
| 内部 / 13824 | 10632.6 / 30880.1 | 0.0108785 / 0.0862856 | 0.0297824 / 1.95546 | 0.000572904 / 0.0399458 |

| 已保存状态 / measured | 原 `L_D` | native / augmented | `norm(g_c)` / `norm(g_y)` | 参数状态 |
| --- | ---: | ---: | ---: | --- |
| 零态 | 0.5 | 1 / 1 | 55.1188 / 1.31867 | 本批诊断固定态 |
| V1 FEINN-EUC 最终 | 0.350221 | 0.928287 / 0.928287 | 65.5243 / 2.08964 | 仅最终 checkpoint |
| V1 FEINN-DUAL 最终 | 0.328252 | 1.102645 / 1.102645 | 53.3210 / 1.22137 | 仅最终 checkpoint |
| V1 FREE-FE-DUAL 最终 | 0.103899 | 0.596914 / 0.596914 | 0.606632 / 0.0250092 | 仅最终 checkpoint |

V1 EUC 的本表 `L_D` 是 D0 在保存场上新评估的同一个对偶目标，**不是**其原训练的欧氏 loss；原生残差的分母始终是固定原 `norm(f)`，对偶 loss 的分母始终是固定 `d_G`。`G_jj` 的家族差异说明变量尺度值得一次诊断，但这些静态统计本身不证明优化病态的唯一根因。D0 Gram factor setup 97.1968 s、5次 solve 1.28125 s，释放前/后 worker RSS 1,043,619,840/532,516,864 B；完整计入成本。

## D1：缩放和梯度资格

从已施加 MPC 的原全局 `G` 取对角，全部严格正且 finite，虚部相对缺陷为0；`diag(D*GD)` 对1的最大偏差为 `4.44e-16`。固定M5的3个非零复向量中，`c→y→c` 相对误差最高约 `7.26e-17`，`AD` 共轭转置 dot test 最高约 `3.15e-15`，原 loss 差为0。边、面、内部3个非零实参数方向在 `h=1e-4/1e-5/1e-6` 的中心差分均满足连续两个步长相对误差≤1e-5；复数非Hermitian合成算子及SPD Gram检查也通过。事务异常精确恢复已提交 `y`，保存 `c=Dy`，试探和closure费用未丢。D1 factor setup 96.9274 s，26次 solve 7.50272 s，最大真实相对残差 `1.66e-13`。[完整测试原值](records/scaling_checks_v2.json)。

## D2–D3：唯一候选与独立同 p3 验算

| 同口径量 / measured | V1 FREE-FE-DUAL | V2 scaled FREE | 判定或分母 |
| --- | ---: | ---: | --- |
| 完整closure / 已提交外层 | 4000 / 649 | 4000 / 649 | 两者均 `CLOSURE_BUDGET` |
| 最终 `L_D` | 0.1038990913 | 0.0990052598 | 同固定 `d_G`，下降但不是方程资格 |
| native / augmented 相对残差 | 0.5969144472 / 0.5969144472 | 0.6077719288 / 0.6077719288 | 固定原 RHS；严格各≤1e-6，研究各≤0.05969144472114 |
| 原 total 增广残差 | 0.282759425 | 0.287902633 | 固定原 total RHS；严格≤1e-6 |
| 散射 E L2 / scaled curl | 0.991924899 / 0.991755492 | 0.954208584 / 0.954118455 | V1同p3参考；严格≤1e-4，研究散射 E≤0.5 |
| total E L2 / selected total E/H | 0.680216602 / 0.672953696 / 0.670814662 | 0.654352483 / 0.646200248 / 0.644656951 | 场改善仍远离≤1e-4 |
| ordered 原 total port / 真出射复幅 | 0.573349002 / 0.275179736 | 0.554438846 / 0.266103778 | 同一40级，分母不同，见下节 |
| ordered scattered port 复幅 | 1.017927730 | 0.984354510 | 同一40级散射 port 参考范数 |
| R / T / A_balance / A_volume | 0.845194 / 0.115246 / 0.0395601 / 0.459627 | 0.841893 / 0.109807 / 0.0483005 / 0.443408 | 均为未资格化 diagnostic；参考0.812426/0.0324624/0.155111/0.155111 |
| 最大逐级功率绝对差 / 能量闭合绝对差 | 0.0825716 / 0.420067 | 0.0765753 / 0.395107 | 门限各≤1e-6/1e-5 |
| 监督候选 wall / s | 2901.906 | 2539.810 | shared workstation，时间改善不可归因 |
| 同时树RSS峰 / B；自身swap / B | 1,366,249,472；0 | 1,365,712,896；0 | 0.5 s采样、16 GiB硬线 |
| A / Aᴴ / 原方程audit / Gsolve 次数 | 4002 / 4000 / 331 / 4003 | 4002 / 4000 / 331 / 4003 | 相同工作计数；未隐藏额外closure |

新终态的完整端口残差相对值为 `1.86e-16`，MPC slave 存储为0，说明端口恢复仍准确；这不能补救 native 残差 `0.60777`。V2 的 R/T/A/A_volume 相对参考的绝对差分别为 `0.0294661/0.0773445/0.106811/0.288297`，吸收与能量闭合缺陷均约 `0.395107`，均未通过严格门限。六点 total/scattered 复 E/H、scaled curl、完整复通道与逐级功率的 absolute/denominator/relative、所有非通过字段和参考原值见[独立 Gate](records/gate_decisions_v2.json)与[原 compare 索引](records/run_index_v2.json)。

compare-only 进程在候选 checkpoint/hash 冻结后读取 V1 已保存的同 p3参考；MUMPS symbolic/numeric/solve 均为0，没有重建全局 Maxwell 参考矩阵或因子。参考同 p3 离散资格仍是原 V1 证据，不是连续极限或新的盲测试。首次 compare-only 因 FE 环境顶层 Torch 导入错误在组装前退出；局部修复后第二次因默认沙箱拒绝本机 MPI socket 在初始化前退出；第三次在相同 one-run 输入下完成。三次费用与 source 均保留在[run index](records/run_index_v2.json)，未覆盖候选或 V1 stage。

独立 checker 从原复向量重算四种40级通道的分子/分母、功率差、能量闭合、每个场误差的 absolute/denominator 比、原方程与资源 Gate，并复验 `D` 及 checkpoint 的 `c=Dy`。结果为 `SCALING_DIAGNOSTIC_NEGATIVE`：严格方程/场/功率均不通过；研究正信号的两个条件也不同时成立。场误差比旧 FREE 略低，只说明本次固定设置对部分观测有有限影响，不说明物理求解器获救，更不产生神经增量。

## 证据措辞与全过程成本

V1 表头“出射复通道”指原 JSON `ordered_complex_outgoing_channels` 对参考出射向量的误差，FREE 的分子 `0.2512611606`、分母 `0.9130801711`、比值 `0.2751797362`。CSV 字段 `ordered_total_channels_relative` 指 `ordered_complex_total_channels` 原 total port 向量，同一分子、分母 `0.4382342339`、比值 `0.5733490017`。两者不是抄写冲突，V2 以后分别明确称“原 total port 复系数”和“真出射复幅”；scattered port 又有自己的分母 `0.2468359523`。新终态这三者分别为 `0.554438846/0.266103778/0.984354510`；逐字段独立复算见[Gate](records/gate_decisions_v2.json)。

| 资源 / 单位 | V2 实测或归属 | 边界 |
| --- | ---: | --- |
| D0 / D1 / 候选 fresh Gram factor setup / s | 97.1968 / 96.9274 / 101.073 | 三次独立进程均计入；`RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR` |
| D0 / D1 / 候选 Gram solve / 次，s | 5/1.28125；26/7.50272；4003/1214.979 | 原 G 不变，训练最大真实相对残差1.66e-13 |
| 候选 Gram CSR payload / B | 146851456 | 对象体积，非树RSS；factor peak 633592648 B |
| 本批已完成正式监督 / s | 2778.420 | 含两次compare失败；轻测试/渲染单列，见[最终账](records/resource_costs_v2.json) |
| 候选复用装配新增成本 / s | 0 | 直接读取已hash绑定的G；不宣传冷启动免费 |
| 候选从零归属 / s | 3188.576 | 候选监督2539.810＋原G装配648.765；归属不加入本批实耗 |
| 本批数值最高同时树RSS / B | 1365712896 | 各阶段峰不相加；完整批次含浏览器峰1741213696B |

系统余量按 effective total 的10%约216.31 GB，加384 GiB邻任务增长预留和自身16 GiB；运行前有效可用内存约946–948 GB，资源窗口合规。全机候选期间有25页 `pswpin`，来源不能归属；本任务采样 `VmSwap=0`。历史监督器的 `WSL-global` 字符串是旧标签，当前执行实际为工作站原生 Linux。V1 数值阶段最高树RSS约1.313 GiB，而含浏览器渲染的完整账最高为2,095,390,720 B，两者口径不混称。没有证据宣称对邻任务零干扰或共享环境下的性能加速。

p4始终 `not_run`，V1 的 `DISCRETIZATION_NOT_QUALIFIED` 是未准入，不是已测 p4 误差。目标尺寸5nm与0.7nm/48h也均未运行。本次只排除了“原 G 对角单位尺度这一个固定变换足以让固定优化器取得合格 M5 解”；不排除更广义的优化条件、开放 Maxwell 谱/共振、网络表示和将来的其他研究方向。下一轮若获单独授权，最小建议应先定位原算子与当前损失几何之间的优化瓶颈，同时继续以原方程和散射场双指标作判别；本批不自行实施。
