# Task042 V42：有限分布式作用可信，内部恢复未资格化，目标作用停止

Task042的研究目的仍是神经网络突破：在相同原有限元正确性下，相对最佳合格非神经方法，完整耗时或同时峰内存至少改善20%，另一项合规。本轮没有神经训练或推理；分布式体积、伴随和残差接口用于以后核验神经场，不能记作神经贡献。用户本轮再次明确这一主线，下一轮建议必须回到神经接入与非神经对照，不能把接口准备无限延长为独立纯FE研究。

这里的体积作用是把整个三维有限元系数向量代入原Maxwell方程，并返回方程左右不平衡的量；伴随是它的复共轭转置作用，可用于神经模型梯度。内部恢复则从边／面系数还原每个单元内部系数，必须保留非零载荷的特解。它们是审核神经候选的基础，本轮没有求得新的物理场。

## 1. 身份与连续执行

| 身份／单位 | measured记录及证据 |
|---|---|
| canonical工作树／唯一分支 | /home/fenics/Projects/NN-Lab；task42_neural_coarse_inverse |
| common／origin／upstream | /home/fenics/Projects/Maxwell3D-Lab/task-repository.git；Rookie1234567/MyFEniCS；origin/task42_neural_coarse_inverse |
| base／接手Review V39 | ccd357885f7f9be84efe3be07868cc94f13d93fc／31774b6282f61280fe33c162f9f48bf4ea526ce6 |
| 最终运行实现source | a7c6404265fda804392beecce60d9b6c12953f26；早期正式run各自绑定完整source，见[run index](records/run_index_v42.json) |
| 冻结窗口 | 2026-10-04T11:23:46.596679260+00:00；monotonic1038021.45；boot fd8f4b00-1e17-46af-a6fa-da3a32dbeba3；24h／末1h交付，不刷新 |
| 物理／材料 | nominal0.7nm，source0.699999988明确alias；Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1；三tag、1°s、原Floquet相位和参考面 |
| 目标／有限模型 | 原目标530856hex／p6／32060port；A为同大周期连接64hex／p6／三tag／45000native行；B为冻结V40八hex／p6／12mode，无新的边界求积 |
| 环境／并发口径 | 原资格化native activation、complex128／IntType64、数学1，真实MPI1/2/4；GPU不用、Loader0、shared-workstation |

按5.1→5.2→独立CHECK→条件TARGET_GATE→部分接口DEPLOY→CAPACITY执行。缺阶段默认通过、保存包自证identity、逆映射对偶和oriented/rank-users库存缺口已同轮修复。A／B生产核、旧native CSR及独立保存数组checker保留独立路径；没有改旧authority或旧packet。最后文档HEAD不是运行source。

## 2. 完整数值门分别验收

| 对象／比较；relative门1e-10 | measured结果 | 分类／范围 |
|---|---:|---|
| 六个raw类，仿射原矩阵对V40/native q15/独立q17 | 全部检查通过；初始class最大3.931665034781359e-15 | 同六类原体积积分，非新模型或可分场近似 |
| A完整原CSR正向／伴随、复线性、零输入、真实MPI1/2/4全canonical输出 | 独立作用检查最大7.4373561447666037e-10；CSR正向2.05060063094916e-15 | 有限原作用可信；不能授完整仿射恢复 |
| A保存的局部内部平衡 | MPI1最大4.4382659417654474e-10；MPI2最大6.281844275527451e-10；MPI4最大7.437356144766604e-10 | 原门FAIL；未改容差／输入／归一化 |
| A独立native单元内部平衡 | 最大7.5914669173601817e-10；99/192个cell状态失败 | FAIL；不以动作或内积通过替代恢复门 |
| B新MPI2/4原作用、非互伴C/D、完整12port、仿射恢复、native方向／MPC | 原生产与独立多项检查通过 | 实际新进程消费；仍受下一项CSR原平衡限制 |
| B原CSR独立内部平衡 | 分子8.547419438477142e-9／分母84.59035110603175＝1.0104485117650333e-10 | 两个rank数均FAIL，不四舍五入过门 |
| 原目标raw／oriented库存保存数组重算 | 530856cell；270raw／858oriented；rank私有306／900 | 库存PASS，不代表目标作用运行 |
| CHECK汇总／有限恢复资格 | DISTRIBUTED_VOLUME_NOT_QUALIFIED | A/B内部恢复未闭合；body action单独保留 |
| 原尺寸体积＋完整32060port正向／伴随 | NOT_RUN | 首要原因FINITE_NUMERICAL_GATE_FAILED；其他heavy、排他锁未核实、目标backend未实现、保守RSS预测unknown亦保留 |
| 完整PDE、E/H/curl、R/T/A、A_volume、R00_s/p/total、逐通道功率与能量 | NOT_RUN／NOT_QUALIFIED | 无official结果；没有以任意向量动作代替物理解 |
| 2TB／48h、神经20% | NOT_QUALIFIED／NOT_DEMONSTRATED | 没有训练、推理或完整N=1成本对照 |

[完整分子／分母和原始判定](records/component_checker_v42.json) · [有限MPI阶段](records/finite_volume_and_recovery_v42.json) · [准入](records/target_admission_v42.json)。原V40及V41成功证据保持；新增独立审核揭示的新失败不追溯改写旧结果。

A恢复中，两个大项相减得到小的内部载荷：操作量对载荷的比例为9522.94370445..128032.181778。已有六个局部LU的1范数rcond估计约5.48e-8..1.92e-6，无新分解。这些数据说明运算尺度与结果尺度差很大，可影响浮点恢复；它们不是通用误差界，也不能单独证明唯一根因。本轮没有通过精化／高精度／换seed或放宽门来制造成功。B仅稍高于门也仍按失败保留。

## 3. 可调用部分与未实现部分

| 接口／数据 | 实际状态及消费者 | 尚欠内容 |
|---|---|---|
| NativeDistributedAction.apply_original及apply_original_adjoint | A真实MPI1/2/4消费全部owned／ghost和cell贡献，独立CSR全向量审核 | target canonical全体积backend没有实现；不能拿有限native桥当目标decoder |
| SavedRecoveryConsumer.apply_original及有限recover | B新MPI2/4消费不可变旧CSR／4类LU／C/D／fi/g；旧producer编号与新consumer编号分开 | recover仍受原CSR内部1e-10失败；NOT_QUALIFIED |
| native边界抽取及逆映射的共轭转置 | live依赖／材料／basis／q／phase／owner检查；一般复数非互伴反例覆盖 | 原目标boundary routing继承V38/V41；没有新全体积boundary组合 |
| residual：r_FE-C*r_port，含非零内部特解 | 有限独立残差恒等式及12port审核 | 无目标physical RHS／完整残差／场功率解 |
| DEPLOY | PARTIAL_INTERFACES_FROZEN_AFTER_NUMERICAL_GATE；引用已发生的新进程消费，新增作用0／LU0 | 不再重放不合格恢复，不授部署完整通过 |

全部依赖、source、原数组字节和caller live身份见[阶段DAG](records/stage_dependencies_v42.json)、[consumer](records/consumer_interface_v42.json)、[source清单](records/source_inventory_v42.json)。构造packet先原子保存，路径／元数据失败从可信tensor继续。只有有限CSR用于独立oracle，45000行／48550477NNZ／971189560B显式载荷，未全局分解。新增六个450行局部内部LU，旧B四类只读复用；LOCAL_INTERNAL_LU_PRESENT，不能称factor-free。目标LU／全局QR／PC／Krylov／训练均0，global p4 factor不存在。

## 4. 费用、存储与48h差距

| 项目／单位／口径 | measured／derived值或unknown | 解释 |
|---|---|---|
| 同时自有进程树采样峰／swap | 3729522688B／0 | 不是各阶段峰相加；0.5s设置，实测间隔及漏峰见资源账；无可用独立cgroup硬峰 |
| ORACLE全部失败＋继续 | 695.898983075s | 210.102435541s失败保留；原生q15 JIT和6类nativeCSR装配费用全部计入，不藏setup |
| CLASSES／A三rank／B失败与成功 | 56.344827231s／47.745961261s／43.081382674s | 包括所有正式失败，不随修复刷新；B不重建LU |
| 新native与LU库存 | 152hex累计≤512；6次尝试／6成功局部LU | 旧A/B包只读；未新增第三类fixture |
| 科学数组 | 33包；469逻辑／469实际／0alias | 文件／成员shape/dtype/C-order hash独立核验；压缩存储不是RSS |
| 本轮最终全部有载／probe／元数据收尾 | 见[完整费用](records/resource_costs_v42.json) | 所有测试失败、重放、collector、最终文档检查逐项计费，闭账后生成最终版本 |
| 历史监督下界 | 81610.59579075915s＋本轮监督 | 历史未监督实施、完整原N=1仍unknown，不补造精确累计 |
| 目标一份canonical trace＋interior | 5506942464B payload | 与native含slave一份5532337056B不同；不是树RSS预测 |
| 目标raw270／私有306矩阵 | 3360631680／3808715904B payload | oriented858未构造；270目标LU未构造 |
| 目标setup／完整动作／通信／恢复／IO／K | unknown | 不能由有限8/64hex外推成已测目标或48h收敛 |

```math
T_{N=1}=T_{setup}+K(T_{solve\_action}+T_{PC}+T_{communication})
+T_{recovery}+T_{original\_audit}+T_{IO}\le172800.
```

各项与K均缺可靠目标测量，不能求可信K上限。[容量与神经成本门](records/original_size_integration_capacity_v42.json) · [就绪矩阵](records/integration_readiness_v42.json)。dot匹配的operator／canonical order／material／mode／physical RHS／recover／PC身份仍须逐字段核验，本轮未读取其factor或运行其solver；缺包不是A/B工作前置条件。

自有lock、rank逐核实时CPU／SMT准入、ownswap、原PSI／系统与邻任务增长余量保持。无GPU／ABI或系统配置修改；邻任务未操作。没有同条件邻任务速率基线，影响INCONCLUSIVE，不承诺零争用或无干扰加速。

## 5. 失败保留、测试与决策

普通窗口schema、nativeCSR装配路径、producer/consumer ABI边界、C_adapter与C_native接线、permutations字段及局部getter导入错误均保存原stderr／source／费用，作最小修复和相关复验。原数值恢复失败不是bug，不继续参数扫描。ORACLE已存的tensor被继续使用，失败费用不清零；没有改旧closed账。

pre13轻量测试尚未完全退出时发生一次commit：代码字节未变，但nominal HEAD混合。该次只作候选字节验证，事件留journal，全部费用保留；随后pre14在完整已提交source上重验61项通过，正式运行均独立核验clean source的Git blob hashes。最终compile、Ruff、ABI/getter与15项文档合同见[测试](records/tests_v42.json)、[文档检查](records/documentation_checks_v42.json)。新数值／checker／参数化runner的Ruff检查通过；scripts/run_case.py仅新增V42注册标记，保留接手baseline已有的10项格式告警，已用相同配置／文件名逐项对照，见[继承lint](records/legacy_runner_lint_v42.json)。不宣称全文件Ruff通过，不作无关全仓清理。没有full-repository pytest或CI声明；GitHub精确页面视觉NOT_VERIFIED，local结构检查不替代网页证据。

唯一下一建议（只交审阅，不自动实施）：在已可信的有限原作用／伴随接口上，将一个冻结神经trace表示接到canonical实体及原残差，核验真实伴随梯度并做同正确性非神经对照；把尚未通过的非零内部恢复门作为显式限制，未闭合前不授完整求解或20%收益。不得用目标参考场监督拟合，不能把传统缓存收益归神经。

本轮受真实有限数值门停止，不启动目标完整动作／物理求解，也不无意义耗尽24h窗口。按依赖组仅交研究opt-in与检查器，未批准merge或production default，见[selective manifest](records/selective_merge_manifest_v42.json)。旧task/review/response/raw和历史汇总完整后缀保留。清场、ledger closed、仅推送本分支并核实clean/upstream0/0后，以execution-review-handoff-20261004-v42原队列交回，提醒神经主线并停止。
