# V72 outcome：复用38块的完整有界迭代与诊断输出

本轮已复用健康38块与7068行粗层，完成39个numeric、真实PC资格和一次RIGHT FGMRES，实际执行256步。**完整原方程未通过；与V70同离散完整场严格再现失败。** 最终状态为`ITERATION_BUDGET_EXHAUSTED`，没有停在代码、symbolic或第一个factor。process `COMPLETED`表示授权流程结束，科学资格另判。

这里先逐单元解出内部未知量，只让界面与完整828端口参加全局迭代，再恢复全部767280个内部系数。小粗层协调远处区域，38个重叠小块修正局部误差；每次PC还实际调用一次原接口作用。小块解的残差与PC线性是组件检查，全局收敛由完整原式决定。本次没有全局细层K/S读取、形成或细层factor；仍有父内部LU和新局部/粗LU，不能称factor-free。

## 身份与实际流程

| 项目 | 精确身份 |
|---|---|
| canonical / 分支 | `/home/fenics/Projects/NN-Lab` / `task42_neural_coarse_inverse` |
| base | `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| Review commit | `07d3f3d2aa6177cc015ac1a279900f7fbb14f4c7` |
| Review blob / SHA256 | `5acdfa2e769001b696ef7973e119aef8b6bbd5ed` / `512577697347f248ca1568bf6df61d44a3df9c7ad7cd273aeaea2b136c372d71` |
| REUSE / ITERATE实际source | `5564befc97ccb749e1b0e4d5fc909592d130c808` |
| 独立VERIFY实际source | `3a4a336e34e433bb673085dea1a72ccae1bd1894` |
| 物理身份 | `df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44` |
| 模型 | 0.7nm缩尺真实NOTCH；25576tet/p5，其中1000个NOTCH tet；κ=(8.94046081729244,0.7821889682108057,0)，828完整模式 |
| 规模 | 独立FE1943745；内部767280；retained FE1176465+port828=1177293 |
| 固定求解配置 | RIGHT FGMRES；restart32/max256；retained零初值；恢复包含原内部特解 |
| 固定窗口 | 2026-10-11T04:04:31Z开始；17:04:31Z heavy-stop；18:04:31Z截止；未刷新 |

源码先clean提交和资格化再运行三个one-run输入。REUSE_ADMIT消费旧独立数学资格与新80GiB容量门，保留V71的64GiB拒绝和closed账本；没有重建分区、Z/E0或粗Galerkin。ITERATE逐块装载CSR、做symbolic/numeric、保存非零RHS见证后释放输入，首个校准factor一直留用。最后候选冻结、actor退出后唯一VERIFY才读取V70场。

[身份](records/authority_identity_v72.json) · [实际运行索引](records/run_index_v72.json) · [数组增量](records/array_inventory_v72.json) · [源码绑定](records/source_bindings_v72.json)。实际run source与最终文档HEAD分开；最终完整remote/HEAD见交付回执。

## 原方程、完整场与具体负结果

| 原式或组件 | measured | 门限 / 分类 |
|---|---:|---|
| 独立原式 true | 0.998857044302 | ≤1e-6，FAIL |
| 独立原式 native | 0.998857044302 | ≤1e-6，FAIL |
| 独立原式 augmented | 0.999209905213 | ≤1e-6，FAIL |
| 独立原式 port | 0.00456299823852 | ≤1e-6，FAIL |
| retained显式true | 0.999209919609 | ≤1e-11，FAIL |
| 39个固定RHS最大原块残差 | 1.38870485323e-10 | ≤1e-8，组件PASS |
| 实际PC复齐次差 | 2.06773995942e-12 | ≤1e-10，组件PASS |
| 原内部恢复操作尺度误差 | 5.58822515019e-16 | ≤1e-10，PASS |
| MPC恒等式 | 1.58920802317e-18 | ≤1e-10，PASS |
| Schur/未凝聚原式操作尺度差 | 1.37482027758e-15 | ≤1e-10，PASS |
| 51024个共享/周期三角面切向E差 | 7.93638214434e-15 | ≤1e-10，PASS |

无下降率早筛选、无参考warm-start、无额外尾部、无参数扫描。曲线及所有重复callback消费保存在[残差历史](records/residual_history_v72.json)和[分类计数](records/explicit_counters_v72.json)。formal原式1e-6、retained1e-11、恢复/MPC/恒等式1e-10不变；独立direct1e-10单列。大原残差表明这个固定组合在配额内没有解出原方程，不能据此认定唯一根因或所有迭代都不可行。

全域作用实际started/completed=557/557，门600；按类型计数为I_reused_hot_pair=2, I_PC_internal_scaled_trace=258, I_explicit_true_scaled_trace=16, I_public_original=16, I_outer_scaled_trace=263, I_final_public_original=1, V_saved_public_original=1。父V71已付8次另列，不清零；重复审核照计，不将callback次数当额外Arnoldi步。

保存完整native包络、mesh/MPC/κ及全部内部系数，恢复物理total/scattered E/H/curl，原240点和828物理复通道/单mode功率完整。以下比较在同基同几何中先减系数，再于共同物理域评价，沿原q23/q31分母/floor，未投影或调幅相。

相对差按原比较器以第二方V72场范数为分母。E_total的原差积分平方值为38.8506120621，分母积分平方值为9.78771308366e-05；本轮total范数极小，使该相对比值较大。E_scattered沿同一差分子，分母积分平方值为35.2156577318。保留这些原值与floor，不为负结果换分母。同基同实载波差分子沿已资格的精确多项式q13计算，配对q23/q31及独立q31见证差6.9232347946e-16；没有降低Fourier边界求积。

| 与V70同离散比较 | 全域相对差（/V72） | 原240点相对差（/V72） | 严格门 |
|---|---:|---:|---|
| E_total | 630.025775498 | 630.249896627 | ≤1e-6 |
| H_total | 629.931404163 | 626.442715493 | ≤1e-6 |
| curl_total | 629.931404163 | 626.442715493 | ≤1e-6 |
| E_scattered | 1.05034272196 | 1.05327311418 | ≤1e-6 |
| H_scattered | 1.05032116371 | 1.05325736957 | ≤1e-6 |
| curl_scattered | 1.05032116371 | 1.05325736957 | ≤1e-6 |

参考面复通道相对差1.2392160698（≤1e-6）；逐mode功率最大差0.920580711327（≤1e-9）。R/T/A/A_volume差分别R_total=0.920580296088, T_total=0.905662888262, A_balance=0.0149174078255, A_volume=0.0181162341519（各≤1e-8）；运算尺度求积差6.9232347946e-16（≤1e-10）。全部原分子/分母、保存数组与独立复算见[checker](records/scientific_checks_v72.json)及其绑定的完整payload。

| 诊断功率 / 体吸收 | measured | official |
|---|---:|---|
| R00_s | 0.996798855098 | False |
| R00_p | 4.97592564777e-14 | False |
| R00_total | 0.996798855098 | False |
| R_total | 0.996798855314 | False |
| T_total | 2.27286799178e-06 | False |
| A_balance | 0.00319887181757 | False |
| A_volume | 4.54869808251e-08 | False |
| R+T+A_volume−1 | -0.00319882633059 | 门1e-5；diagnostic |

本次official=False，功率仅来自当前候选，不沿用参照填数。actor与独立checker结果分列；consumer通过表示保存资产和评分可信，不自动把科学FAIL改成PASS。历史连续精度FAIL、原尺寸0.7nm/2TB48h/NN20均未资格。

## 实际容量、生命周期和完整成本

因子双倍symbolic合计80322000000B=74.8056918383GiB，满足新80GiB子门；最大逐factor共驻计划90.3903437853GiB≤96GiB，future逐项核算且至少8GiB。全部39个ICNTL22=0、23为原decimal-MB估计的两倍；实际INFOG、图与原块残差见[逐factor库存](records/numeric_factor_inventory_v72.json)。局部输入nnz合计374068350、coarse nnz3541640为已保存实际图，未阈值drop。不是用最大的单块代替总预算。

KSP创建/solve/destroy各1；local/coarse factor共39已释放。释放前后单进程RSS为41144000512B→8418959360B，RSS下降=True。截至正式VERIFY结束，全树采样峰40.1189613342GiB、最大gap1.81898451899s；最终费用收据还计入末次文档检查和清场，报告的科学阶段快照不冒充未来采样。配置0.5s不等于连续硬峰。ownswap观测0、OOC0，MPI1/math/CPU1/GPU/Loader0及原宿主/cgroup/PSI/邻增长/CPU-SMT保护保持。[生命周期](records/lifecycle_v72.json)与最终费用记录区分单进程观察和采样树峰。

| 实际分段 | measured wall（s） | 口径 |
|---|---:|---|
| ITERATE_one_run01 | 6977.90752732 | 从启动到监督/后代清场；该层不重叠 |
| REUSE_ADMIT_one_run01 | 204.856167693 | 从启动到监督/后代清场；该层不重叠 |
| VERIFY_COST_one_run01 | 516.453830357 | 从启动到监督/后代清场；该层不重叠 |
| auxiliary_pre01 | 91.9586848749 | 从启动到监督/后代清场；该层不重叠 |
| auxiliary_pre02 | 92.0186336529 | 从启动到监督/后代清场；该层不重叠 |
| auxiliary_pre03 | 93.8163622569 | 从启动到监督/后代清场；该层不重叠 |

39个numeric子计时243.471794241s，资格全段398.535837303s；后者还包含读取、symbolic、固定RHS与写出，均嵌套于ITERATE，不重复相加。PC全部调用、local/coarse/原作用子计时见[PC实测](records/PC_qualification_v72.json)。当前必要prepared-start链实测7699.21752537s；它是实际完整诊断尝试成本，合格解T_N1=未取得。

几何起点packet-only构建仍unknown：父V70 BUILD形成过S，不能扩大本批无S声明到整个cold历史。V70 BUILD9646.82648389s与prepared SOLVE12666.5476045s、V71准备及全部旧失败已在历史前缀346072.0271125611s中一次计费。最终[费用](records/resource_costs_final_v72.json)续记末次文档/收尾，分列全部窗口elapsed、已知不重叠wall下界、未分段unknown、实际存储和free；不授未配平且不同正确性的生产速度/峰比。

65条retained V/Z主向量1224384720B是derived，库内实际unique载荷未测，不能冒充RSS；完整FE向量与trace+port分开。新artifact许可32GiB/Task632GiB/free50GiB，完整数组ignored，只引用本批清单和父hash。

## 修复、边界与唯一下一建议

三个接续修复已落实：旧数学与新容量分开；首次实际校准factor不重建；PC异常释放和仅本批合法初值续算协议。定点测试覆盖真实小PETSc restart、累积迭代/身份/RHS拒绝及异常因子释放，三dat validate、相关compile/Ruff完成；一次文档合同结果见[测试](records/tests_v72.json)。CI未运行，GitHub精确视觉NOT_VERIFIED。

运行中发现相同restart边界状态重复原式审核，原向量/hash与额外作用/费用保留。保持活跃HEAD不变完成actor，随后按完全相同vector+iteration缓存修复并定点复验；没有重factor/KSP或删除失败。详细[source/修复](records/repair_journal_v72.json)。无需重建的旧分区、Z/E0、fine K/S/factor、参照求解、新NN、MPI扩大均未执行。

紧凑记录writer的一处括号错误已在同轮修复，原stderr、修复前源码与成功消费收据保存，没有科学重放。修复与复验的保守elapsed上界6787.935464s≤9000s；该上界包含等待原actor结束的嵌套区间，不另加到研究wall。

唯一下一pilot：冻结失败残差的粗层/局部转移分解，据此预登记一个波动粗层跨区通信替换，同时保留已验证局部块并作一次同离散完整对照。该项仅建议，尚未执行；当前证据未定位唯一根因，不能继续原PC尾部或无界扫描p/ILU。目标端口增长不能直接塞进现有8192行粗层上限。[目标缺口](records/target_gap_v72.json) · [消费合同](records/retained_iterative_contract_v72.json) · [依赖分组](records/selective_merge_manifest_v72.json) · [原始增量](records/raw_archive_index_v72.json)。

完成同分支推送、实时remote/full SHA、clean/upstream0/0、closed/active null、自有后代清场与锁释放后暂停；不merge、不改邻支，不通知隔壁，不自动开新窗口。闭窗实核见[closure](records/closure_v72.json)。
