# Response V41：交替条件线性核试验已完成，三路线联合门未到

**Review V40授权的实际神经包已完成：新算子资格、两条从零NN消融、同秩Cheb强控制、独立逐点q30/q60、完整FE compare-only和保存数组checker。三条M5联合FAIL，无验证神经资源增益；不是接口完成后停止。**

条件线性核求解把“一个小网络的最后输出系数”先作为线性问题处理：固定隐藏函数和另外两轴，用原方程选择当前轴的复系数；随后只在学习路线更新隐藏函数。它减少通用优化器处理乘积系数的困难，但仍要反复执行完整有限元矩和原 Maxwell 作用。它不是全FE完成器，也不是全部三核的联合最优或精确VarPro。

共同模型是原M5：5nm、8×6×8=384hex、p3、31968独立复FE系数、完整40端口，原Si/air三维缺口、材料/背景/双Floquet/DtN不变。NN仍为r=(1,8,8,1)、三轴sin网络9072实参数，Cheb控制为同r8的T0..T18、9120实系数。网络完整矩q30，独立逐点q60；体/DtN q15。全部边、面、内部矩及微小非零、真实Piola/orientation/唯一owner/MPC保留，没有换成容量诊断张量。

| measured；同原 M5 / 5nm / 384hex / p3 / N31968 / 40端口 | 学习隐藏层 NN | 冻结隐藏层 NN | Chebyshev 控制 | 原门或含义 |
|---|---:|---:|---:|---|
| 完整轮次 / 核心访问 | 4 / 12 | 4 / 12 | 6 / 18 | 各≤6轮 / 18访问 |
| LSMR迭代 / 隐藏loss-gradient调用 | 2887 / 54 | 2352 / 0 | 5400 / 0 | 各≤5400；迭代不等于closure |
| 接受核心 / 接受隐藏更新 | 12 / 4 | 12 / 0 | 18 / 0 | 完整状态真实接受，不是试探 |
| native / augmented | 0.938986749611 / 0.938986749611 | 0.939413868293 / 0.939413868293 | 0.19086785578 / 0.19086785578 | 各≤1e-6；全部FAIL |
| 独立 total 原残差 | 0.44479967704 | 0.445002003912 | 0.0904144394405 | ≤1e-6；全部FAIL |
| 总 E / 散射 E | 0.685685791479 / 0.999900336902 | 0.685693295091 / 0.999911279035 | 0.679322943215 / 0.990621722409 | 各≤1e-4；全部FAIL |
| 总 H / 散射 H | 0.683734176323 / 0.999917056728 | 0.683741494114 / 0.999927758525 | 0.677329532829 / 0.990550679422 | 各≤1e-4；全部FAIL |
| 总 scaled-curl / 散射 scaled-curl | 0.683734176323 / 0.999917056728 | 0.683741494114 / 0.999927758525 | 0.677329532829 / 0.990550679422 | 各≤1e-4；全部FAIL |
| 六点复 E/H 最大相对误差 | 1.01128902632 | 1.0110918867 | 1.00536206375 | total/scattered四类全保留；≤1e-4 |
| 完整total通道向量 | 0.563171285969 | 0.563179900821 | 0.563208323139 | 每类全部40复通道，原向量分母；≤1e-4 |
| 完整scattered通道向量 | 0.999858143859 | 0.999873438727 | 0.999923899904 | 每类全部40复通道，原向量分母；≤1e-4 |
| 完整出射通道向量 | 0.2702949258 | 0.270299060511 | 0.270312701846 | 每类全部40复通道，原向量分母；≤1e-4 |
| 边界面出射通道向量 | 0.259813198211 | 0.259817321457 | 0.259841126848 | 每类全部40复通道，原向量分母；≤1e-4 |
| R / T / A_balance / A_volume | 0.838121997023 / 0.113332560663 / 0.0485454423133 / 0.464869889332 | 0.838105144833 / 0.113333611138 / 0.0485612440293 / 0.464860193041 | 0.838316398868 / 0.113263707493 / 0.0484198936392 / 0.460129779765 | 残差失败，仅diagnostic；不是official功率 |
| R00_s / R00_p / R00_total | 0.837952957092 / 2.17695296115e-11 / 0.837952957114 | 0.837937029559 / 1.50932518185e-11 / 0.837937029574 | 0.838082548435 / 1.43476774557e-10 / 0.838082548579 | 两极化分别保留，不从功率推复振幅 |
| 独立能量闭合 / 最大逐级功率绝对差 | 0.416324447019 / 0.0809106947362 | 0.416298949011 / 0.0809123067707 | 0.411709886126 / 0.0808641910466 | ≤1e-5 / ≤1e-6；全部FAIL |
| 实际模型完整矩重建 | 4.60961153065e-14 | 5.40353232787e-14 | 1.03710508959e-14 | ≤1e-10；全部PASS |
| 网络q30-q60系数 / 原作用漂移 | 3.87459605239e-14 / 4.44092864799e-13 | 2.98060739498e-14 / 3.62895777443e-13 | 4.7485798608e-15 / 1.98585467264e-13 | ≤1e-8；全部PASS |
| 独立FE积分q15-q30漂移 | 1.17949314844e-14 | 7.43042654576e-15 | 1.30927808773e-14 | ≤1e-8；全部PASS |
| MPC / 端口恢复相对差 | 0 / 5.47926026874e-17 | 0 / 7.15638244977e-17 | 0 / 1.09971543408e-16 | ≤1e-10；全部PASS |
| 同原G场误差 | 0.999916644849 | 0.999927352566 | 0.990552429586 | 仅独立评分G乘法，无G逆或Gram因子 |
| 本路线实际attempt秒 / 同时树RSS采样峰B | 1371.57181736 / 469508096 | 1514.96984082 / 393895936 | 3384.2425484 / 388096000 | 含加载/成功准入/setup/内层/存盘；loaded-packet |
| 停止理由 | BLOCK_ALTERNATION_STAGNATION | BLOCK_ALTERNATION_STAGNATION | ROUND_LIMIT | 前两条科学停滞；控制轮次/迭代上限 |
| actual / producer 联合Gate | FAIL / FAIL | FAIL / FAIL | FAIL / FAIL | 独立评分，不挑有利版本 |

三条均NUMERICAL_GATE_NOT_REACHED，研究信号也未达。学习路线与冻结路线原残差相差0.000427118682723，相对冻结原残差改善约0.0454665081216%；散射E误差仍约99.99%。Cheb条件线性控制明显更低的原残差仍远未过门，不能把固定特征线性代数收益全部算成NN收益。

本批关闭当前r8/native-EUC、LSMR300、最多六轮及隐藏20调用配置的自动续算。没有证明所有r8或FTTNN数学上不可能，也不把未达到门归咎于已经通过的writer、映射或求积。NO_VERIFIED_NN_INCREMENT / FEINN_MAIN_SOLVER_ON_HOLD / FULL_TARGET_NOT_QUALIFIED保持；没有受支持的新神经生产候选，不自动改rank/loss/seed、开监督拟合、oracle或下一批。

0.7nm缩小pilot因learned M5联合FAIL而NOT_RUN，未注册空输入；原50×25×140nm、Si17/120nm、λ0.7完整3D FE、decimal2e12B整机、自身swap/OOC0、172800s完整冷流程及原精度仍未达到。未知的是可合格神经表示/优化、同精度完整成本以及原尺寸规模全过程，不由本次低RSS或小权重推断。旧M3600较好/Mfinal退化、D0成本否决/D1未运行、失败/UNKNOWN与全部费用保留。不改其他支线，不向Task42、主线或dot安排工作。

## 身份、完整实施与有限修复

首次现场为V40完成、HEAD80d65063fc82592baffc5f479635aaba450a2eff、clean、锁FREE、无本任务活跃run；精确fetch/ff-only取得Review发布4ed149dd709419f00bad01e6e5dea7079fa61d81。canonical/common Git分别为/home/fenics/Projects/NN-Lab-V2和/home/fenics/Projects/Maxwell3D-Lab/task-repository.git；精确分支task42extra_feinn_5nm，base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。共享fetch配置未改，显式refs/remotes/origin/task42extra_feinn_5nm作为核对权威，旧upstream解析128不被写成通过。

实现先clean提交7ae99c6aaafe41b234f49ba11b059a970968eb82并完成真实新算子资格；实际文件标签拒绝资格补丁f0bd287e8865d9717020a1f523aaf222d24f4794后运行三条路线和原独立重建/FE compare-only。用途封存source b64d594993316df4a1784553954c20468cde0229；独立保存checker恢复source d38d28953bed93b9457a060ec9c496083676586a。后续文档HEAD不冒充运行源码，健康旧数值和参考未重算。

普通问题已同批处理：ML环境没有Ruff时使用既有pure工具；只读进程API不匹配改用有限PID/start_ticks/锁检查；最终保存态核对脚本错选轴/层修正后只补受影响检查。39项数学/受影响回归已通过，另2项用途writer/seal/reopen和1项恢复目录保留测试通过，共42项相关案例；无full pytest、安装或CI声明。

完整数值之后发现通用comparisons仍带production_initialization_allowed=true。新增FTT用途限制只改元数据，原报告、旧saved_checker和result均以before_research_policy原件保留。首个保存复核恢复碰到FileExistsError，已改为attempt独立监督目录并定向测试；随后旧逐点/FE产物全部复用，只有独立保存checker重新读取原数组和原A。该失败、错误用途字段及费用不删除，没有因此重跑健康producer。三条训练的checkpoint均reference_sha256=null，实际四类禁止文件open在训练前被拒，bytes_read=0。

每个完整核心/隐藏边界先原子保存模型/buffers/参数顺序、全c/r、位置、累计作用与RNG，再发布committed行；四次已完成隐藏优化器状态保留，但下一轮按合同fresh历史。LSMR未保存内部bidiagonalization，不能从半次迭代恢复；本批没有丢失或伪造内层历史。最终模型与producer分开审核，全部功率为diagnostic。

## 完整成本与安全

三条各在原7200s硬上限内，零故障恢复或丢失内层训练；12/12/18次完整核心更新均有真实原loss下降及≤1e-10线性性配对，学习路线四次隐藏更新共54调用。LSMR停码和伴随残差不等于PDE通过；到300上限的有效方向按真实场验证接受。原[内层CSV](outcomes/records/conditional_inner_solver_v41.csv)逐次保存原线性残差、真实伴随残差、cond估计、作用次数对应索引及committed hash。

唯一43200s研究窗不重开，成功60sPSI观察、加载、失败、保存、独立验收和发布计在同一墙钟内。初始检查第一段精确时间未保留，使用首个保留观测之前600s的保守截止锚点，精确未保留准备成本UNKNOWN；它是预算锚点，不是假造实测起点。阶段actual_attempt秒为可加子项，继承跨度和父子timer不重复相加。采集时正式attempt合计7216.67265001s，含用途修复失败/恢复；当前资源与发布尾段另在[费用](outcomes/records/resource_costs_v41.json)及尾账保留。

已采样串行自身树峰最大658161664B，不是全机峰或多阶段相加；numeric warn12/hard16GiB、规划12GiB、cache/AD1GiB、light2GiB。全部自身swap/OOC0，CPU-only/MPI1/math/Torch1，现场空闲物理核、SMT/PSI/系统与384GiB邻增长保护不变；不宣称零干扰。新全局Maxwell因子、Gram因子/Gsolve、全FE Krylov、参考重求均0；现有准确小端口消元的作用成本保留。独立G评分只有稀疏乘法。

单场loaded-packet成本、可复用native/网格/矩准备、研发历史和完整冷N=1分开。必要准备不免费；完整冷N=1与项目精确历史累计仍UNKNOWN。旧10186.178641493432s波库训练不是本次从零FTT的必要前缀，但历史不删除。同精度三条都FAIL，无法授时间或同时峰20%神经收益，也不能称内核快于传统FE解。

## 证据与交付边界

[专题](outcomes/ftt_conditional_core_v41.md)、[独立完整Gate/分母/区域](outcomes/records/full_numerical_gates_v41.json)、[42次内层与真实接受](outcomes/records/conditional_inner_solver_v41.csv)、[隐藏及轮次](outcomes/records/hidden_updates_and_rounds_v41.json)、[三路线/初态](outcomes/records/conditional_core_routes_v41.json)、[完整40×四类复通道](outcomes/records/full_40_complex_channels_v41.csv)、[六点复场](outcomes/records/six_point_complex_fields_v41.csv)、[功率](outcomes/records/power_and_energy_v41.csv)、[用途/分母定义](outcomes/records/channel_and_norm_definitions_v41.json)、[run/source/hash](outcomes/records/run_index_v41.json)、[tests](outcomes/records/tests_v41.json)、[修复](outcomes/records/repair_log_v41.json)。大场与完整checkpoint留ignored，全部hash-bound。

只提交推送task42extra_feinn_5nm，不amend/强推/merge。最终完整HEAD、显式tracking/ahead-behind、clean及numerical.lock/自身数值和浏览器清场在发布收据及最终答复核对。有限GitHub视觉检查与本地解析分别记录，网页服务失败不冒称视觉PASS、不重做数值。整批结束等待review，不通知其他窗口或自动开下一包。
