# Response V32：多尺度波动神经已连续执行，M5联合数值门未达到

本轮查明：保存空间没有严格零支持cell，底部导数P·U也不是严格零；“缺底部覆盖”假设未证实。新神经路线实际发生241次非零已提交连续q更新，保留1350个复方向。但M5原native/增广残差0.111824065796、散射E相对差0.0423218706136，联合Gate仍失败，没有同精度20%神经资源收益。关闭本批FIXED_MULTISCALE_WAVE_BLOCK / LEARNED_MULTISCALE_WAVE_BLOCK的这份配置，不能推广为所有神经方法不可能。条件0.7nm真实缩小pilot未运行。

这次改动让网络始终能选择覆盖整个模型或不同大小区域的波动函数，并按它们对完整原方程的作用决定加入哪一块。神经路线额外学习连续波矢；固定控制有相同物理种子、窗口、完整矩、块幅值和稳定线性代数，也按原残差确定性选向。所有旧幅值可重新组合。它改变表示与选区，不改变原M5方程、材料、网格、端口或误差门；代价包括筛选、插值、方向梯度、全空间作用、累计列库、小系统与存盘。

| measured；同M5/λ5nm/384hex/p3/31968复FE/40端口 | 固定多尺度控制 | 学习多尺度神经 | 原门及边界 |
|---|---:|---:|---|
| 保留复方向 / 接受块 | 1377 / 246 | 1350 / 241 | 共同4096容量，独立零散射起点 |
| 实际非零已提交q更新 | 0 | 241 | 连续q真实优化；不强制扰动 |
| native / augmented原残差 | 0.157431767049 / 0.157431767049 | 0.111824065796 / 0.111824065796 | 各≤1e-6 |
| 独立total原残差 | 0.0745757053209 | 0.052971256913 | ≤1e-6；原total RHS |
| 散射E相对L2差 | 0.0288946898255 | 0.0423218706136 | ≤1e-4；原参考分母 |
| 总E相对L2差 | 0.0198146530522 | 0.0290223978106 | ≤1e-4 |
| 散射H / scaled-curl相对差 | 0.0289677399528 | 0.0423056325836 | ≤1e-4；同原H单位 |
| 模型→完整矩重建相对差 | 8.91426760953e-13 | 5.0500950991e-15 | ≤1e-10；全部内部矩保留 |
| R / T / A_balance，诊断 | 0.8058557873 / 0.03196918217 / 0.1621750306 | 0.8005600005 / 0.03447361115 / 0.1649663883 | 非official；差值原门各≤1e-5 |
| 独立A_volume，诊断 | 0.152331141191 | 0.161769367016 | 体积分，误差≤1e-5 |
| R00_s / R00_p / R00_total，诊断 | 0.8057819472 / 5.458602451e-07 / 0.805782493 | 0.8004588516 / 9.452904899e-10 / 0.8004588526 | 三项分列；完整40模式另存CSV |
| 独立体吸收能量闭合 | 0.00984388938608 | 0.00319702129457 | ≤1e-5；不是A=1−R−T恒等式 |
| 最大逐级功率绝对差 | 0.00647487128873 | 0.0117979668499 | ≤1e-6 |
| 本路线实际学习attempt / s | 9572.249428 | 11982.685081 | 准入/setup/试探/存盘均计；其他审核另列 |
| 含本路线早期审核/读出修复 / s | 10186.178641 | 12180.057796 | 共享最终审核仅在项目账计一次 |
| 本路线采样同时整树峰 / B | 5290643456 | 2288005120 | 自身swap0；不是阶段峰相加 |


实际点值网络与producer分别完成q30/q60重建、独立total/MPC、全部E/H/curl、六点、四类40复通道、逐级功率、R/T/A/A_volume/R00和材料/界面区域验收。全字段分子、实际分母与失败项见[完整指标CSV](outcomes/records/full_metric_index_v32.csv)，[Gate与原数组绑定](outcomes/records/full_numerical_gates_v32.json)。功率是未合格场的diagnostic，不是official结果；参考只在隔离验收读取，训练不读teacher/参考向量，继续只使用标量，benchmark_previously_seen=true，不称盲测。

两条从零路线均先冻结第一节点、独立评分，再按第二节点继续门恢复原完整边界；没有重置四小时路线钟。第一516方向节点：fixed原残差0.3200412713/散射E0.0489075852；learned0.1787393622/0.0703433930。学习残差更小而场更差，不能仅据loss宣称收益，也不是同时间比较。终态同样是学习原残差更小、场误差更大。最终[成本与容量](outcomes/records/cost_and_capacity_v32.json)、[资源与全部attempt](outcomes/records/resource_costs_v32.json)保留所有中断、失败、试探和修复；共享完整审核800.492336s只在项目账计一次，完整冷N=1成本UNKNOWN。

固定读出遇到small-R与完整原作用配对超过1e-10；在原边界保存后，用不改变U、波参数、列顺序及rcond的原AU经济型QR重建，经真实点值配对通过后继续。原错误分类导致一次2GiB监督停止，修正数值角色后资格完成；原负记录不改。学习方向评价采用18次完整调用硬守卫，SciPy实际maxiter12实现另绑定；未保存的实际nit/丢失试探计数标NOT_RETAINED，不重放补日志。[修复](outcomes/records/repair_journal_v32.json)、[targeted测试及source](outcomes/records/tests_v32.json)。未full pytest、未重新安装、未重求准确参考，训练global Maxwell/Gram factor均0。

权威为Review V31，发布2b841cb6910be14fcaf9fea98ea59b7f458a5c94；reviewbase e67ceeef13308d195596c83c8601c5dc692943e6，冻结base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。最终运行/独立checker source `a11c3ae2157f42a6874e54ec6cec29ab57fe0b81`，固定健康前缀/source修复链在[run index](outcomes/records/run_index_v32.json)，后续文档HEAD不冒充数值source。本批唯一57600s窗包含开发、成功PSI60s、失败与发布，至少3600s终验预留；历史费用与精确累计UNKNOWN不清零。

原50×25×140nm、Si17/120nm、λ0.7完整3D FE、双Floquet/全部内部/全端口、decimal2e12B整机、ownswap/OOC0和172800s完整冷流程及原精度门仍未达成。NUMERICAL_GATE_NOT_REACHED / FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED保持。保留M3600较好、最终退化、D0成本否决/D1未运行及所有负结果/UNKNOWN；不返回W0/W1、主线接入或传统完成器。完成本批后暂停，等待审阅，不自行延长训练或给其他支线安排任务。

[专题](outcomes/multiscale_neural_support_v32.md)、[设计](outcomes/design_multiscale_v32.md)、[覆盖与端口](outcomes/records/saved_space_coverage_v32.json)、[24列无标签见证](outcomes/records/unlabelled_direction_witness_v32.json)、[完整复通道](outcomes/records/complex_channels_v32.csv)、[逐级功率](outcomes/records/per_mode_power_v32.csv)、[区域](outcomes/records/material_interface_regions_v32.csv)、[逐块增长](outcomes/records/block_growth_v32.csv)、[依赖分组](outcomes/records/selective_merge_manifest_v32.json)。
