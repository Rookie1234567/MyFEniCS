# V29 原尺寸完整口面作用与主线接入

## 1. 模型、问题和边界

有限元体内场要经过上下边界与外部辐射模式交换信息。V28只验收两个面片；本批检验原尺寸所有面片合起来之后，相位求和、共享行、周期代表、角点及回散布是否仍正确。收益是一个主线可调用的全口面组件，代价是完整输出、独立参考及保存成本。没有替代体内方程或获得NN收益。

| 固定物理 / 数据身份 | 实测范围与限定 |
| --- | --- |
| 原尺寸 | 周期50×25nm、高140nm，Si17/120nm/三维缺口；λ0.7、掠角1°/φ0/s、air/Si背景不改 |
| 口面 | x90/46/46/90、y4，z=-10/130nm，上下2,176面；实际binary64宽度保存，1ulp不同不合并 |
| 空间 | p4原生dim300/p6 dim882；边界trace行69,632/156,672；不是体积FE DoF |
| 模式 | W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28；32,060有序key、四组各8,015，全部所选传播模式 |
| 输入 | 36,263,033B/SHA7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e；H/参考面/归一化不改 |
| 数学来源 | c354afa449fb80cfb5012e7d2ff66a3e3e64e088，43文件/1,054,179B；原DirectionalBoundaryAction(face_inventory=None) |
| 固定见证 | seed4212801通用复trace/dual/非零modal载荷，seed4212901周期缝/角点见证，真实物理入射 |
| 方法 | 原q60，≤64模式分块，不建32,060平方或全trace×mode密集矩阵 |
| 未覆盖 | 体内恢复、全域PDE、任意向量误差界、倏逝截断/网格收敛、完整目标2TB/48h资格 |

[设计](records/design_v29.json)、[源/数组hash](records/run_index_v29.json)、[Gate](records/gate_decisions_v29.json)。旧52d7ec80…原件和ledger未恢复，新旧数值等价UNKNOWN。

## 2. 真正调用和独立检查

薄adapter将模式送入未修改的FacetPolynomial / BoundaryLayout / DirectionalBoundaryAction。face_inventory和face_masks均为None，每份实际布局覆盖2,176面。两坐标系均完整计算，不是两个面片结果乘面数。B使用traction，D使用电极化投影除以原H；不能假定互为共轭转置。recover是逐模式投影/幅值，apply是完整边界返回向量。

P1保存全部模式两切向分量/幅值、完整apply/adjoint/modal RHS/真实入射RHS、坐标桥两侧输出、布局方向/权重和原生列。物理入射按已知top00s载荷进入接口，不是制造的体内准确解。

独立参考在候选评分前冻结。精确binary64频率共3,503项、ell0..6，复用V28的357项、新增3,146项Decimal80/110；p6全部复用p4，没有重复高精度积分。两个producer释放后独立checker用保存矩/多项式作y-before-x扩展算术收缩和独立实体回散布，不调用候选apply/recover/scatter生成参考。按物理坐标/拓扑核对每个实体、方向、周期角点，并核对固定种子。

新增面宽/方向在两坐标系、上下侧共68个case上检查全部300/882原生列，固定物理key为00s和横向频率极值；未按幅值丢小迹。V28基系数副本逐字节复用。局部case不是全部模式的全原生列矩阵证书；全32,060模式的完整输出另逐key核验。

## 3. 原门和额外负结果同时保留

| measured / 独立参考分母 | p4 | p6 | 原门 |
| --- | --- | --- | --- |
| 原门项数 / 失败数 | 513,630 / 0 | 513,630 / 0 | 每项通过 |
| 最坏逐模式幅值相对差 | 8.784101295566122e-11 | 7.435717804637401e-11 | ≤1e-10 |
| 一维矩最大绝对差 | 9.082805012334877e-14 | 同参考复用 | ≤1e-12 |
| Decimal80/110/解析配对最大绝对差 | 3.3422138886441676e-16 | 同参考复用 | ≤1e-12 |
| 全作用/伴随/坐标桥/物理RHS/全部模式两分量及映射 | 固定见证均过原门 | 固定见证均过原门 | ≤1e-10 |
| 额外逐列项数 / 失败数 | 61,200 / 1,360 | 179,928 / 4,947 | 未授逐列资格 |
| 单列积分最大相对差 | 23.87790429183715 | 16.805483465112903 | >1e-10 |
| 单列B/D最大相对差 | 0.7359035711449673 | 0.7431740785896633 | >1e-10 |

[172行逐字段最大值及分子/分母](records/full_surface_metrics_v29.csv)、[完整CSV/NPZ入口和hash](records/independent_checker_v29.json)。ignored原CSV保留全部失败key/列。

c129曾使用每个原生列的范数，6,307项失败；受测V28原积分为完整矩阵，B/D为完整向量，原源码对完整对象取范数并验三个固定复杂方向。c229恢复这一同一规则，候选、参考和阈值不变，额外逐列结果继续原样保存，没有扫描分母或提高q，旧c129 FAIL不改写。

极小原生迹分子约1e-15，参考约1e-17至1e-16，相对差很大。完整向量门没有消除这一负结果；不能按“绝对小”裁项，不能将它升级为主线体内消元资格。这里授予的只是固定见证完整表面经验资格。

## 4. 本机可消费接线

P1实际API记录：两坐标系每份各8次project、7次scatter；经原数值类完成完整作用/伴随/恢复/两类RHS。证据不是只写status或复制索引。[调用和默认消费](records/main_api_handoff_v29.json)。

真实本机包：

```text
/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task42extra/w1_receiver/v29/h29/surface_handoff/main_opt_in_bundle/
package_manifest SHA256 e54d17b4184daf258901624afa487a2121fe6a97e2f1478c61c4b3731aed3ba9
```

37个相对路径载荷共251,699,594B，另有manifest/ready收据。包括新模式/配置、p4/p6布局/矩/见证/输出、原生列/基、独立参考/报告、原主线模块/adapter/checker及实际dat。V28原位保留，没有复制旧1.6GB包。

consumer.py --inspect仅检查身份/封存，不做FE；provider(4/6)供接收方显式opt-in，在其资格化Basix环境建立原类并要求基系数逐位相同。活依赖为相对路径，旧binding绝对路径只是来源说明。监督成功且清场后，默认ready路径实际重开同一37文件并读取封存数值报告；这不是第二次独立FE生命周期，也不是跨机/断电资格。

状态MAIN_API_ADAPTER_LOCAL_PASS_NOT_REMOTE_INGESTED。主线必须绑定同instance体内对象/内部恢复，或独立证明版本桥，不能拼接旧B/D/H/factor。未写主线/dot工作树或调用其PC/B2/W2/存储。

## 5. 完整成本与结束条件

| 实测秒 / 共享参考，不作公平加速比 | p4 | p6 |
| --- | --- | --- |
| 原类及全口面构造 | 10.482446 | 10.753701 |
| 全部实际作用 / 两坐标系 | 0.867860 | 1.119802 |
| 冷构造及参考准备 | 82.579226 | 21.026626，复用p4 |
| 全payload含保存 | 84.349817 | 22.813703 |
| 全receiver含PSI/源准备/加载/监督 | 153.006203 | 91.694705 |
| 采样同时树峰 / B | 814,727,168 | 910,086,144 |

最终checker全链162.992869s/payload96.619852s，包封存重开69.831761s。全部正式阶段费用976.1939919528086s，不重复加嵌套worker/watchdog；开发/失败/等待/阅读/发布在同一连续窗另记，不能只报热project/scatter。[资源费用](records/resource_costs_v29.json)。

连续28800s从2026-10-05T05:53:09.288359Z起，明示300s开场保守allowance，没有重开。24/24真实准入样本、等待813.597248s≤900s；各formal CPU观察≤2.959228s，独立60s PSI。CPU-only/MPI1/单核数学1，原系统及384GiB邻余量不改。采样树自身swap0，OOC0；启动前/元数据未测峰UNKNOWN，不冒充连续硬RSS资格。artifact快照966,649,196B＜16GiB。

收据键/格式、D共轭、派生面字段、原生对象分母及P0根因计数均有限修复并保存失败；健康p4/p6不重跑。最终17项测试/Ruff/compile通过，纯fixture不是原生物理证据。[修复](records/repair_log_v29.json)、[测试](records/targeted_tests_v29.json)、[合并分组](records/selective_merge_manifest_v29.json)。

辅助交付到此收口。主线按自己的合同推进完整参考逆、体内恢复、目标场及截断/网格精度，不为维持本支制造再读回批次。

## 6. 仍未验证和目标

全域残差、总/散射E/H/curl、六点复场、实际散射复通道、R/T/A/A_volume及完整目标冷流程NOT_RUN；不把边界模式或固定trace见证称为散射观测量。q60分面/稳定求和未触发，NN/Gram/Maxwell factor/solve为0。

FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED保持；保留M3600较好/Mfinal退化、D0成本否决/D1未运行、全部旧失败/UNKNOWN及费用。最终原50×25×140nm、Si17/120nm、λ0.7完整3D FE、decimal2e12B/ownswap-OOC0/172800s及原门仍未达成，无production/master merge批准。新页视觉未确认，旧渲染失败与已审阅范围分别保留，不因网页问题重跑数值。[呈现记录](records/render_check_v29.json)。
