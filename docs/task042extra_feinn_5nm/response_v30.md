# Response V30：真正学习了新波动方向，M5数值门未达到

本轮实际运行了新的局部复指数神经网络和同能力固定方向控制。**神经路线接受3,127个模块、14,520个波动神经元；每个接受模块均有非零连续波矢及复幅值更新。完整native/增广残差为0.3308837562，控制为0.4237611235，均未达到1e-6。** 没有求准M5，没有可验证的同精度神经资源收益，条件0.7nm缩小pilot未运行。

结论为 **NUMERICAL_GATE_NOT_REACHED / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED**。本轮没有回去做W0/W1或全口面组件；没有旧权重、参考标签训练、全局Gram/Maxwell因子或传统完成器。

## 1. 数值结果与实际停止原因

“残差”衡量当前场还违反多少原有限元方程。把新函数加入累计空间确实降低了它，但它不是场误差，也不是求解通过。以下原量来自冻结producer和四次独立完整矩重建，未用小系统残差替代。

| measured / 原M5同p3；相对量无量纲 | 固定方向控制 | 可学习波动网络 | 原门/判定 |
| --- | ---: | ---: | --- |
| 完整native及增广残差 | 0.4237611235276062 | 0.33088375619287214 | ≤1e-6，两者失败 |
| producer原total增广残差 | 0.2007363905457445 | 0.15674021806304106 | ≤1e-6；不代替独立total验证 |
| 原端口恢复操作相对差 | 1.9080592381271006e-17 | 6.387473891952872e-17 | ≤1e-10，此项通过 |
| 网络点值→完整矩与producer系数相对差 | 1.596430748798739e-11 | 1.719858821415671e-10 | ≤1e-10；控制通过，神经失败 |
| 完整系数q30→q60相对漂移 | 5.168545078858821e-13 | 1.132689485848676e-11 | ≤1e-8；仅系数子项通过 |
| 独立total方程、展开MPC、total/scattered E/H/curl及六点复场 | NOT_RUN | NOT_RUN | 不推断通过或物理失败 |
| 四类全部40复通道、R/T/A/A_volume/R00、逐级功率、独立能量及区域 | NOT_RUN | NOT_RUN | 没有official结果 |
| 原算子q30/q60、FE场范数q15/q30 | NOT_RUN | NOT_RUN | 完整求积Gate UNKNOWN |

[原字段、限值、失败及未运行项](outcomes/records/full_numerical_gates_v30.json)、[保存重建向量/hash](outcomes/records/rebuild_recovery_v30.json)。网络与producer的累加差没有被改门或覆盖；其具体原因尚未独立归因，不能把系数漂移小写成全部稳定性通过。

独立FE进程完成两路线q30/q60重建、核对同p3参考后，在`physical_model`日志写出时遇到Python complex没有`.tolist()`的错误，未完成场后处理。已修正实际事件writer并加入完整重建的hash复用入口；8项受影响pure测试、Ruff及compile通过，四次健康重建和训练均未重跑。

修复commit后实际再次使用正式launcher。它在**创建tmux/worker之前**拒绝：`V30_RESOURCE_OBSERVATION_BUDGET_REACHED`。本批已计1158.0882629137486s前台资源观察，原上限1200s，剩41.9117370862514s，不足新监督树必需的60s PSI窗口（入口保留64s）。旧树已退出，不能冒充同一活跃监督链复用旧窗口。这是本批的硬资源观察额度出口，**不是内存不足、OOM、PSI正在超限、4096列耗尽或精确172800s耗尽**。余下总窗用于保全、独立记录检查和发布，未开第二窗。

[失败→修复→测试→真实恢复拒绝](outcomes/records/repair_journal_v30.json)、[最终纯逻辑资格](outcomes/records/recovery_qualification_v30.json)、[资源账](outcomes/records/resource_costs_v30.json)。原FE失败2713.0728316761088s和修复、测试、等待费用全部保留；不能用修复测试数替代未完成的物理验收。

## 2. 新神经机制与控制

每轮从尚未满足的原方程学习一个局部波动函数，冻结后与以前全部函数共同求系数。网络学习连续波矢和复向量幅值；窗口中心、半径及支持是固定几何库存中的残差选向，不宣称连续训练了中心/半径。所有边、面、内部矩及31968个完整复FE系数、40端口都保留；累计网络子空间为3127列，仍是原p3空间的子空间。

| measured / 冻结模型 | 固定控制 | 神经路线 |
| --- | ---: | ---: |
| 接受列/模块 | 2160/2195 | 3127/3128；最后trial未接受 |
| 神经元 | 6784 | 14520 |
| 连续方向训练 | 0 | 3127个接受模块均非零更新 |
| 方向更新范数范围 | 不适用 | 1.7294635184e-7至20.5144685455 |
| 幅值更新范数范围 | 确定性微型SVD | 1.9329857000e-10至42627.5057132 |
| 存储的实参数描述数，derived | 65376，包含固定方向 | 136934，包含累计复系数；不是FE独立维数 |

两路线共用物理种子、局部窗口、完整矩、准确端口对角消元、两遍正交化、小QR/SVD及已资格化等价缓存。控制包括确定性残差选向和局部方向细化，不是弱随机对照。训练没有读取参考、旧监督权重或精确逆；参考只由冻结后的独立进程读取。Torch用于独立导数测试，实际学习为NumPy FP64/complex128解析梯度和连续方向优化。

[首次学习前冻结设计](outcomes/records/design_v30.json)、[实际学习及全部部分计数](outcomes/records/training_v30.json)、[空间增长/参数/梯度](outcomes/records/basis_growth_v30.json)。方向优化261个接受模块报告局部停止成功，2866个报告迭代/调用上限；后者不能写成优化收敛。完整native未出现超过1e-12的接受步增大，预测/实际下降差仍记录，不据此授完整求解资格。

## 3. 成本及0.7nm边界

| measured / 单位s或B；同时采样树峰不相加 | 原量及边界 |
| --- | --- |
| 固定控制完整attempt | 64834.23888433515s；采样峰3267076096B、swap0 |
| 神经共同约18h节点 | 2563列/native0.342678708；当前控制2160列/native0.423761124，差约19.13%；共享争用及多source工程前缀使同成本结论limited |
| 最后神经续段 | 完整attempt29081.75956760696s，payload29017.028222583933s，峰4395831296B、swap0；包含控制等待的继承日历不是另一次费用 |
| 最后续段含失败FE依赖 | 31796.833254938945s；FE2713.0728316761088s已在其中，不能再双加 |
| 末态残差相对控制下降，derived | 约21.92%，但用了额外时间且两者不合格；不是≥20%同精度资源收益 |
| 因子及存储 | 全局Gram/Maxwell训练因子0，新参考求解0；U/Q/R、缓存、所有加载/原子保存均计费；4096列同时活跃规划7142899712B是预测，实际仅3127列 |
| 新artifact快照 | 11214618652B＜20GiB；健康历史不删除 |

[完整run/source账](outcomes/records/run_index_v30.json)、[成本比较](outcomes/records/cost_comparison_v30.json)。前三次工程暂停及资源拒绝费用保留；第366列以前细分作用计数、第二attempt独占加载/setup时间、单版本从零成功冷N=1时间均NOT_RETAINED/NOT_MEASURED，不重放补历史。研发时钟覆盖所有准备、失败、等待及发布；全项目精确累计仍UNKNOWN，旧失联3284s及全部历史费用不删除。

5nm解析空气波原函数误差约1.90e-16，p3插值E/curl约0.001962/0.01185；未缩放0.7nm约1.033/0.953。平界面的已知复β解析函数不是受限实波矢网络的资格。这些校准不是M5通过，也不能用连续离散误差解释本轮对同p3方程未求准。

M5联合Gate未通过，长度×0.14的真实0.7nm缺口pilot为`NOT_IMPLEMENTED_NOT_RUN_PRECONDITION_M5_JOINT_GATE`。原50×25×140nm、Si17/120nm、λ0.7完整三维FE、decimal2e12B整机、自身swap/OOC0、172800s完整冷流程及原精度目标未达成。

## 4. Git、测试和一次收口

唯一分支`task42extra_feinn_5nm`，canonical `/home/fenics/Projects/NN-Lab-V2`，common Git `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；原base `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`，本轮合同发布`8d617d4d206b08f38279320b67188db1b8ccd301`，审阅基线`bb0f5216976e58df834310595ebb3d23f1e37e3a`。

实际末段神经及失败FE source为`79f363981765876e7020ac09cec326e8ba7e656e`；控制source为`e6aafc6583aeb8aeebb32a8359dab662ba14ca66`；修复和worker前拒绝source为`7bd72c7e81a9983addeff4032e9feacde6088a27`。后续文档HEAD不冒充运行source。八文件数值训练链未改，既有真实全矩/梯度/作用资格按hash复用；不full pytest、不重装ABI，不修改其他工作树/分支或共享fetch配置。

最终HEAD、显式tracking/ahead-behind、clean、锁及清场在本机`tmp/task42extra/v30/delivery_receipt.json`和最终回复记录；Git文档不制造自包含commit SHA。[测试/呈现](outcomes/test_summary.md)、[文件依赖分组](outcomes/records/selective_merge_manifest_v30.json)、[专题](outcomes/neural_wave_galerkin_v30.md)。GitHub视觉有限访问仍须如实记录BLOCKED，不能以本地结构PASS替代。

旧M3600较好/Mfinal退化、D0成本否决/D1未运行及全部FAIL/UNKNOWN保留。研究实现留本支，普通默认不改；不授生产初值、NN净收益或merge。完成推送和清场后暂停等待审阅，不通知隔壁、不自动重开训练或新研究窗。
