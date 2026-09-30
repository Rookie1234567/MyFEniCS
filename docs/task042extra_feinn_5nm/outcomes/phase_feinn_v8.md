# Task42extra V8：相位表示、从零原方程对照与条件拟合

本轮把已知入射传播振荡从网络需要自行学习的部分中提取出来：网络学习三分量复包络，点值再乘固定物理相位，最后通过完整 Nédélec 矩形成有限元场。这有助于表示传播振荡，但没有提供目标解。最终从零原方程训练中，phase 的散射场近似比 plain 好，原残差却更大；两条 C 路线都没有解出原 p3 方程。因此按授权另做两条参考已暴露的 D 拟合，区分表示和残差优化的因素。

## 1. 只改变表示，完整 FE 空间保持相同

```math
E_\theta^{\rm scat}(x)=\exp\{i k_{\rm inc}\cdot(x-x_c)\}\,a_\theta(x),\qquad
c(\theta)=\mathcal I_{h,3,\rm MPC}^{\rm curl}E_\theta^{\rm scat}.
```

物理坐标单位为 nm；固定 k_inc=(1.2564456695248023,0,-0.02193134074032823) nm的倒数，xc=(0,0,3.75) nm。相位在所有边/面/内部积分点相乘，早于 Piola、方向变换和完整矩；MPC 从自由度只展开一次。网络输入仍用中心/半宽归一化，不给 FE 系数乘中心点相位、不强制包络周期、不加第二次 Floquet 相位。

两类网络均为 3→64→64→64→6，tanh、8966 实参数、FP64、seed421001。隐藏层从固定随机初始化开始，末层为零；初始实参数 SHA256 均为 `11d8cd454281fab85cfc59f04cee6aa7b864157d9f98513830947a0223d64103`。phase 的 k/origin 是不可训练 buffer，不增加参数。M5/p3 的全部 31968 独立复 FE 系数及 40 端口保留；边 3744、面 14400、内部 13824，未退回 trace 或冻结末层。

方法采用[compatible FEINN 论文](https://arxiv.org/html/2411.04591v2)的完整兼容插值和弱残差/Riesz 思路；显式物理相位是本 review 授权的扩展。论文的正质量项 Maxwell 问题与这里有损、开放、负质量项散射算子不同，不能借其正定性作本轮收敛保证。

## 2. B 的新增资格

| 测试 / measured | 实测 | 门限及含义 |
| --- | --- | --- |
| k=0 回归 | 原网络矩差 0 | ≤1e-10，参数规模及旧映射保持相同 |
| 独立相位积分 | 64-node Legendre 积分差 2.63e-15；DOLFINx 插值 2.24e-15 | ≤1e-10；独立于旧矩密度算法 |
| 全部自由度族 | 边/面/内部最大差 3.69e-15，均非零；5 类方向 | ≤1e-10；完整矩而非边界点值 |
| 非单位 Floquet | x 相位约 -0.999999886+0.000478480i，与1距离约2 | 小网格周期2.5 nm；没有利用 M5 相位接近整数圈来漏测符号 |
| 三个非零实参数方向 | hidden/last/random，三档中心差分，各有连续两档稳定区 | ≤1e-5；完整矩 VJP 经实际对偶链验证 |
| batch1/8 | 系数、loss、VJP 和克隆 Adam 更新差最大约1.7e-15 | ≤1e-10；两条新路线同一实现 |
| 网络矩 q15→30→60 | 两类相邻档最大约1.6e-15 | ≤1e-8，因此两条共同保留 q15；原体/DtN q15 未变 |

B 单独建立了一次研究用 Gram 因子验证对偶梯度，完整 setup/solve/释放计费；C 两条还各自计一份 fresh factor。D 拟合不需要逆 Gram。非单位小网格的实测相位来自原1°入射和短周期，未把未使用的 scratch grazing_deg 字段解释成实际35°模型。

## 3. C：从零原方程求解

C 只读取原 native/Gram/完整矩三类数组，训练白名单不含 reference_state、旧监督模型或 Phi/Q。两条都从同 seed 零散射开始，原 A/f/G、d_G、端口、材料、MPC 不变；仅相位表示不同。

```math
L_D=\frac{(Ac-f)^*G^{-1}(Ac-f)}{2f^*G^{-1}f},\qquad
g_c=\frac{A^*G^{-1}(Ac-f)}{f^*G^{-1}f}.
```

这里 Gram 是衡量电场及其旋度变化的正定内积，不是 Maxwell 逆。准确稀疏 Gsolve 保持真残差≤1e-11，标 `RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR`。训练未形成 global Maxwell CSR/factor、A* A 或新 PC。d_G 按上述公式在每路线 setup 中计算一次；C 的运行 JSON 没有单独保留该标量，记 `NOT_RETAINED`，源码/f/G 身份和零场 loss=0.5 已绑定，不为补元数据新增因子或冒充当时测量。

原 Adam500(lr1e-3,weight_decay0)后进入空历史 L-BFGS(lr1,history20,strong-Wolfe,max_iter20,max_eval25,tolerance_grad1e-7,tolerance_change1e-9)。完整 loss+gradient closure 包括线搜索试探，不能当 epoch 或外层 step。每个完整外层返回后先同步原子保存匹配参数/optimizer/buffers/RNG/预算，再发布 committed 行；接受更新量由 step 后参数差计算。结束采用 final committed，last_trial 独立保留，不使用试探或最佳历史态代替终态。

| 共同工作点 / measured | plain | phase | 判断 |
| --- | --- | --- | --- |
| Adam500 native / augmented | 1.5046243543 | 1.1144200929 | phase 约1.35倍下降；远未到1e-6 |
| Adam500 scattered E L2 | 0.9993697135 | 0.5826536990 | 同完整500更新点场近似改善；未到1e-4 |
| Adam500 scattered curl | 0.9994002849 | 0.5833167917 | 未达到预登记≤0.1研究强信号 |
| 终态计费 closure / 已提交位置 | 4000 / 3997 | 4000 / 3986 | 最后未返回的试探费用保留，匹配完整状态回滚 |
| 终态 native / augmented | 1.0554095372 | 1.3192886662 | phase 比 plain 更大；两者均未解方程 |
| 终态原 total 增广残差 | 0.4999493566 | 0.6249493647 | ≤1e-6，均未过 |
| 终态 dual loss | 0.3165587659 | 0.2499617601 | phase loss更低不能当求解正信号 |
| 终态 G 场误差 | 0.9989650389 | 0.2145123712 | 参考只在两候选冻结后读取 |
| 终态 scattered E L2 / curl | 0.9989451840 / 0.9989655403 | 0.2134667998 / 0.2145387128 | phase 场近似改善约4.7倍，但仍远未过1e-4 |
| 终态 total E L2 | 0.6850307914 | 0.1463857409 | total也分别验算，不只比较背景主导的功率 |
| launcher全成本 / s | 9294.134800 | 8747.323512 | shared-workstation；未达到相同资格，不能声称提速 |
| 同时整树 RSS峰 / B | 1508184064 | 1441140736 | sampled tree；自身 swap0、两阶段清场 |
| Gram setup / Gsolve耗时 / s | 65.536657 / 853.424012 | 67.541692 / 857.765034 | 都已包含在各自wall中，不再次相加 |
| Gsolve次数 / 最大真残差 | 4043 / 6.10e-13 | 4043 / 1.19e-12 | fresh准确Gram因子已释放 |
| A / A* / VJP调用 | 4042 / 4000 / 4000 | 4042 / 4000 / 4000 | 稀疏原方程审核41次另列 |

预登记 `PHASE_RESEARCH_SIGNAL` 未成立：Adam500 点原残差不是10倍下降、散射L2/curl均大于0.1；终态原残差没有改善。可以明确记录相位改善了场近似，以及早期共同500更新点三类指标同时改善；不能把它升级为独立方程求解、生产资格或神经增量。共同 wall 比较采用共同截止之前最近已落盘审核，记录时间间隔，见[共同工作量记录](records/common_work_comparison_v8.json)，不从更晚终态补出严格同秒场指标。

C 标记 `reference_used_for_training=false`、`features_reference_exposed=false`、`pde_only_solve=true`、`benchmark_previously_seen=true`、`production_initialization_allowed=false`。这不是新的盲测基准。

## 4. C 冻结后的独立物理检查

独立 ML 参数→保存完整c的差为0；q30 相对 q15 为 plain4.55e-15、phase1.60e-15。独立 FE 只加载原 V1/p3 参考，没有新 MUMPS/Gram factor/Gsolve。还审核了两条 Adam500 共同工作点。参考已保存准确解只用于C的冻结后验算。

| 终态功率 / measured，均为 diagnostic | plain | phase | 原 p3 reference |
| --- | --- | --- | --- |
| R_total | 0.8373971010 | 0.7784899564 | 0.8124264991 |
| T_total | 0.1132687865 | 0.0414337384 | 0.0324623961 |
| A_balance | 0.0493341125 | 0.1800763052 | 0.1551111048 |
| A_volume | 0.4650227017 | 0.2070765764 | 0.1551111048 |
| 能量闭合 / 吸收差绝对值 | 0.4156885892 | 0.0270002712 | 约3e-13 |

功率/能量门限仍为1e-5，逐级功率差1e-6。完整 total/scattered E/H、curl、六点各三分量、四类40级复通道与各自分母、逐级功率、R00_s/R00_p/R00_total，以及原材料/界面区域均由独立 FE 记录保留，见[PDE比较](records/PDE_comparison_v8.json)和[完整通道CSV](records/PDE_comparison_channels_v8.csv)。G 与 L2/curl 能量恒等式独立检查通过；没有全局相位拟合、reference重求或改q15后重训。

## 5. D：条件监督表示诊断

C phase 没有严格通过，且共同数据、插值、资源合格，故自动触发D。plain/phase各自从同 seed、零末层重新开始；没有采用 C 的失败权重、旧拟合权重或 p4 场。

```math
J_{\rm fit}=\frac{(c-c_{\rm ref})^*G(c-c_{\rm ref})}{2c_{\rm ref}^*Gc_{\rm ref}},\qquad
g_c=\frac{G(c-c_{\rm ref})}{c_{\rm ref}^*Gc_{\rm ref}}.
```

D每条另有2次setup非零batch loss/梯度资格检查及18次中心差分值评估；它们没有参数更新，也不计为优化器callback closure，但全部计入路线wall和G/VJP调用。每条实际VJP1502、Gmatvec1538、原方程稀疏审核16次，均原样披露。

D 的训练 closure 只有G乘法和完整矩VJP；G逆、Gram factor、A/A*均为0。原方程稀疏审核、保存、标签身份/非零方向梯度/batch测试都计入1h和本批资源成本。每条最多1500完整closure、同原Adam500+L-BFGS，不延长、调参或重置。D标签只能是原p3独立散射系数，不能是total场或slave存储。

| D终态 / measured | G误差 | 散射E L2相对 | 散射curl相对 | native / 原rhs | 计费 / committed closure | launcher wall / s | 表示分类 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| plain | 0.02509159227 | 0.02572950659 | 0.02507527061 | 3.524097926 | 1500 / 1480 | 2847.717009 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| phase | 0.01040885398 | 0.01005721383 | 0.01041758155 | 0.7662824909 | 1500 / 1480 | 2954.236851 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |

| D功率 / diagnostic | R | T | A_balance | A_volume | 能量闭合绝对 | 最大逐级功率差 |
| --- | --- | --- | --- | --- | --- | --- |
| plain | 0.8154647648 | 0.03390513729 | 0.1506300979 | 0.1552334771 | 0.00460337923 | 0.001065919802 |
| phase | 0.8125474719 | 0.03261911224 | 0.1548334159 | 0.155181753 | 0.000348337116 | 0.0001555013657 |

phase终态三项为0.010409/0.010057/0.010418，均高于0.01；plain三项约0.025。因此两条都没有部分表示见证，不能因接近门限或仅G误差改善而写PASS。

D的三项表示门限是G/L2/curl均≤1e-3（正见证）或均≤1e-2（部分见证）。它们是研究用的表示诊断，原PDE门限不放宽。即使拟合达标，也没有从零无标签求解；一次未达标不能证明网络数学上不能表达。

所有D的manifest/checkpoint/results标记 `reference_used_for_training=true`、`features_reference_exposed=true`、`pde_only_solve=false`、`production_initialization_allowed=false`、`pde_only_solver_qualified=false`、`official_candidate_results=false`。D目录/index/模型与C隔离，未把D权重反馈C、Task042或0.7nm。

## 6. 结论边界和证据

监督 phase 的 G/L2/curl 三项分类为 **REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED**，plain 为 **REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED**。相位在相同参数规模和1500完整closure内的G误差改善约2.410600851倍，说明它在这个固定G目标和预算下更容易拟合；C的原方程优化仍未通过，不能把D监督结果等同于无标签求解。两条拟合均使用参考，因此结果只能限定本架构、目标、预算，不能独立证明网络表达能力的数学上限。

已经排除本轮相位符号/单位/完整矩、非单位Floquet、非零实方向VJP、batch一致性、冻结参数重建、求积漂移、标签混入C、资源超限和匹配状态丢失等已测问题。剩余因素包括有限网络对反射/衍射/界面细节的表达、非凸残差目标的优化、G度量与原方程误差的差别，以及p3连续精度；p4对照仅说明离散敏感性，不解释NN未解出同p3。

后续只建议一项设计：在原M5/p3和同8966参数的plain/单相位表示上，预登记受控的网络参数空间Gauss–Newton信赖域对照。它用局部线性近似决定一次参数更新，并限制更新范围，检验当前非凸残差优化是否为瓶颈；仍从零、无标签，保持原Riesz目标/严格验收，不用Maxwell逆或监督权重。先核定JVP/VJP、A/A*、Gsolve、工作内存和完整成本上限，再由新review授权；本批没有实现或启动新优化器、PDE微调、多载波、p5/h细化或更大模型。

数值运行 source 为 `bc052a3744528277f00a7a9a5566aa4a6d7393ed`；后续checker/文档HEAD单独登记。[设计](records/campaign_design_v8.json)、[资格](records/phase_checks_v8.json)、[训练/检查点/费用原字段](records/training_v8.json)、[独立Gate](records/gate_decisions_v8.json)、[所有运行索引](records/run_index_v8.json)、[完整资源账](records/resource_costs_v8.json)。大参数、匹配optimizer状态、完整history和资源时间线留ignored，compact记录包含hash。

旧V1–V7结果与全部费用不改。旧 lost 817 状态仍未保留，新D中的工作点不能回填旧历史。目标尺寸5nm、0.7nm、p5、h细化、更多端口/载波均未运行。本批执行完授权矩阵后提交并等待review。
