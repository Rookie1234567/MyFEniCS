# Response V40：完成FTT容量判别，保留实际FE证明边界

已连续完成Review V39授权的四个阶段，包括真实内部矩提取、九份完整谱、两态实际隐藏特征及固定Cheb判别、独立保存checker。**最终为NO_VALID_FE_CAPACITY_CERTIFICATE，而非r8已被证明不可能或已足够。** 条件性谱没有排除纯r8；固定NN特征在规范Cartesian小矩空间中超过E门，但实际浮点几何和近相关特征阻止将该结果升级为原FE空间排除。

本轮用“场对局部正交测试函数的积分”检查模型能否承载必要的电场信息。这一步避开了重新训练：先从已保存准确参考提取小张量，再测其完整奇异值和实际隐藏函数能覆盖的空间。它付出一次有限诊断成本，得到的是必要条件，不生成新前向解、训练方向或生产权重。

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


原V39的M5联合门仍FAIL：无标签FTTNN/Cheb native残差0.948212215045/0.989534468620，散射E误差0.999458825608/0.999989164225；原1e-6/1e-4门不变。64.36/78.44倍只是映射实现收益，不是同精度FEM或完整NN求解收益。本批不重跑健康训练、旧完整物理Gate或准确参考；训练/新PDE/A与A*/G作用/全局Gram与Maxwell因子/Gsolve均0。FE读取阶段只重建原mesh/space定义及basis以验证保存场，不组装原方程。

## 完整执行、修复与证据

初始现场为V39完成、HEAD45e6656a4ba55be77404b84681de07be16a2401f、工作树clean、numerical.lock FREE、无本任务活跃run。安全精确fetch/ff-only取得审阅发布e4d6ca9553b73d2938a44b31b3ef2b03204ad571，未改共享fetch配置。冻结base为fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。

实现先clean提交392ec0bb55eb1481a62505591ca8bd7d28d33082。首资格attempt发现直接Basix构造器采用不同默认内部泛函规范；原采样点相同而插值矩阵相对差1.03600527458，原packet没有损坏。复用原UFL N1curl构造器修复，定向核验约2.4e-14，提交9066ce669aca126753190a170cdc00a6079729f8后沿同一stage预算重验并继续。健康张量与谱未重算。独立checker再补原J/origin数组、真实后向误差及预登记margin复算，28项小fixture通过，源码a706d335d17ca534f8a36b53b33e79b9587d18b0；最后pure阶段单独重开保存数组，不调用producer。

| 入口 / 实际source | 执行结果 | 证据 |
|---|---|---|
| v40_capacity_checks；392ec0bb→9066ce66 | 首次原泛函规范FAIL，修复后DIAGNOSTIC_QUALIFIED | [资格与原失败](outcomes/records/interior_moment_bridge_v40.json)、[修复](outcomes/records/repair_log_v40.json) |
| v40_interior_moment_tensor；9066ce66 | 完整与Q111子集双路线配对PASS，秩桥接LIMITED | [真实内部矩/分母](outcomes/records/interior_moment_bridge_v40.json) |
| v40_rank_and_feature_bounds；9066ce66 | 完整谱与三个特征空间均冻结，无删列 | [154奇异值](outcomes/records/capacity_spectrum_v40.csv)、[尾能量/必要秩](outcomes/records/rank_spectrum_bounds_v40.json)、[特征](outcomes/records/frozen_feature_bounds_v40.json) |
| v40_capacity_decision；a706d335 | 独立保存数字一致性PASS；实际FE容量证书无效 | [checker](outcomes/records/saved_capacity_checker_v40.json)、[裁决](outcomes/records/capacity_decision_v40.json) |

所有阶段使用既有durable launcher→watchdog→worker→scripts/run_case.py，串行且逐项清场。FE使用complex128/int64同ABI、未顶层import Torch；pure/ML单核math/Torch1。数值warn12/hard16GiB，轻树2GiB，小矩阵规划256MiB，自身swap/OOC0；原PSI/CPU/SMT/系统与384GiB邻增长余量不变。成功60s准入计总墙钟，拒绝后额外等待0s。唯一14400s窗起点2026-10-10T08:56:11Z，至少1800s发布余量保持；已采集费用及发布尾段分别保留。[运行绑定](outcomes/records/run_index_v40.json)、[完整资源账](outcomes/records/resource_costs_v40.json)、[28项定向测试](outcomes/records/tests_v40.json)。没有full pytest、环境重装或CI声明。

## 投入决定

不再原样续算r8/native-EUC固定流程。当前数字不能支持新增rank训练、扩大隐藏层或把固定特征条件性失败推广为所有FTTNN无解；因此NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE。尚未解决的是对任意输出幅值成立的实际几何/数值特征桥接，必要秩小也不能证明优化能达到原残差、H/curl或端口门。本批不提出无证据的新机制，不自动开V41、注册0.7nm或给其他支线派活。

FTT诊断永久reference_exposed=true、pde_only_solve=false、production_initialization_allowed=false、pde_only_solver_qualified=false、official_candidate_results=false。原M3600较好态、最终退化、D0成本否决/D1未运行、全部失败/UNKNOWN与费用保留。原50×25×140nm、Si17/120nm、λ0.7完整3D FE、双Floquet/完整内部与端口、decimal2e12B整机/ownswap OOC0/172800s完整冷流程及原门仍未达成；FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED。

只提交推送task42extra_feinn_5nm，不amend/强推/merge；实际数值source与发布HEAD分开，完整最终HEAD/tracking/clean/清场由最终交付核对报告。冷N=1和项目精确历史累计仍UNKNOWN，不以本次小矩阵费用替代单场完整成本。[方法与全部限定](outcomes/ftt_capacity_decision_v40.md)。
