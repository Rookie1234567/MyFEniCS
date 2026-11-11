# PSTDDM 分区试验：最终结果

**阶段结论：PASS_WITH_QUALIFICATIONS。真实小型三维模型的同离散求解通过；本次增加分区没有降低全过程内存或时间。停止本轮数值扩展，不改变普通默认、不合并其他分支。**

源转移把远处激励的影响逐层换成下一层的等效源，再通过局部求解拼回整个场，目的是避免昂贵的全局求逆。本实现不是旧 Schwarz 的逐块残差修正改名：它使用独立双向累计源、Maxwell 弱截断交换项、非零源截断、局部 PML 和全局连续场投影。代价是额外 PML 网格、局部因子及重构。本轮验证的是一种具体实现，未证明任意模型收敛。

## 1. 同离散数值结果

以下 measured 数据来自四个独立进程；原方程残差包含全部 FE 与836个辅助端口方程。复总 E/H 的 L2 误差以同一离散的独立 direct 解为参考，不能代替网格或物理收敛。内存为100ms采样同时进程组加监督器峰值，MiB=2²⁰字节；非连续采样上界。

| 案例 | 首扫真残差 | FGMRES步数 | 最终真残差 | 总E误差 | 总H误差 | 峰RSS/MiB | 总时间/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| check_p2_v1 | 0.0491813 | 20 | 5.13323e-09 | 1.51688e-07 | 1.91924e-07 | 870.91 | 82.234 |
| direct_p2_v1 | 不适用 | 不适用 | 1.32285e-13 | 不适用 | 不适用 | 407.64 | 28.642 |
| candidate_p2_n2_v1 | 1.66258e-13 | 0 | 1.66258e-13 | 3.73467e-16 | 3.95642e-16 | 613.37 | 56.716 |
| candidate_p2_n4_v1 | 0.111569 | 18 | 5.74407e-09 | 3.41768e-12 | 3.40576e-12 | 874.19 | 82.300 |

真实 N=4 的一次双扫仍有0.11157原残差，不能通过；虽然总E/H误差仅4.19e−5/4.62e−5，背景场远强于散射场，实际上散射E/H误差仍达4.45%/4.83%。18步FGMRES后，散射E/H误差降至3.63e−9/3.56e−9，才满足整体门槛。N=2的唯一相邻两层问题覆盖整个物理域，没有人工PML，是退化正确性锚点，不是分布式节省证明。

## 2. 模型与身份

| 项目 | 冻结值/范围 |
|---|---|
| 本轮基线 | 2c7aa97f4746c5de0545cf511908321b356a74df |
| 四案数值source SHA | bd0d4daed6da301eaca26b2fdac76a59a834be8a |
| 等树的已核验实现发布 | 70afaab9aaa6cde32de23c1e45f509e86bfffb53 |
| 物理输入SHA256 | 2bc579e2ce3824025f85ec7382292a4028da5a294bbea30baebdc5663e831e9e |
| 模型 | λ=0.7nm；固定真实Si复折射率；有限x/y块；3×10×4=120 hex；p2 |
| 几何/端点 | x/y周期2.59259nm；z物理范围−0.518519至6.740741nm；双Floquet、原DtN |
| 规模 | 原FE3570；周期约束后3120；完整3956阶；m±5/n±9、上下s/p共836模式 |
| 内部PML | 固定10nm/每侧2层/比1.25/二次伸缩σ=8.8192122；只用于局部问题 |
| 实际运行 | 仅云端；MPI1；四线程环境均1；complex128；OpenMPI5.0.10；DOLFINx0.10.0；PETSc3.25.5 |

全部精确坐标、材料、相位、模式、原始RHS与配置见[冻结模型](../frozen_model_v1.json)、[方法规格](../method_v1.md)和[逐案records](records)。三案真实物理A/C/D/T/M/curl Gram及RHS逐数组一致；制造源另存，不能冒用物理RHS。5nm旧控制未用作本轮reference。

## 3. 全过程资源与成本

| 真实案例 | 最大local independent/free | 额外PML独立DOF/全部局部和 | 缓存local因子数 | local装配组/s | local分解/s | setup/s | 首扫/s | 外迭代/s | 恢复/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| candidate_p2_n2_v1 | 3120/3120 | 0 | 1 | 24.716 | 0.500 | 26.780 | 0.02242 | 0.00103 | 4.166 |
| candidate_p2_n4_v1 | 4560/4080 | 5760 | 3 | 48.037 | 1.096 | 51.974 | 0.04483 | 0.89561 | 3.920 |

N=4比N=2峰RSS增加42.52%，总时间增加45.11%；相对direct为2.14倍内存、2.87倍时间。N4最大local free4080已经大于global independent3120，原因是固定10nm PML带来的局部网格。三个局部L/U因子及一个全局质量矩阵因子同时缓存，未省略其开销；N2缓存一个局部因子及同一全局质量因子。没有因子重建/读盘。保留全局原算子以计算true residual，也保留全局质量逆用于lifting/投影，不能称为完全局部或matrix-free。

真实N2/N4每次PC分别做2/6个局部解，正式PC应用分别1/19次，对应2/114个局部solve；另有每pair一次局部逆残差验证与质量重构验证。N4后续18次PC累计约0.8333s，外迭代总约0.8956s；局部装配约48s，是本小模型主要成本，不能把所有变慢归因于迭代。保存数组头独立补数得到global full存储项1,106,992，A为303,596；N4三个local L分别510,720/453,359/510,719，见[sparse storage counts](sparse_storage_counts.json)。这是CSR/CSC存储项数，不等于去零后的数值非零数。完整时间细项、L/U NNZ、模式复振幅和计数边界见[汇总JSON](closeout_metrics.json)。

缓存记录不足以严格判定cold/warm：各案使用独立输出/cache路径，但没有初始缓存清单或hit/miss计数，因此不宣称全冷或热缓存速度。质量因子单独计时、输出独立计时及全部装配调用数未保存，标为未记录，不补成0；分阶段计时不可简单相加冒充总wall。

四案监督累计249.892443s，未触发资源门、零swap、均无遗留子进程。任务树RSS+512MiB<2GiB、系统用量+余量<6GiB、available≥2.5GiB、disk≥12GiB+输出保留；每案输出含监督记录均<256MiB。前瞻4n²×16只是保守计划量，不是实测因子内存或内核硬限额。原样资源记录及最终全文件hash见records中的supervision和final_artifact_manifest。

## 4. 物理量只作diagnostic

| 量 | direct | N4与direct绝对差 |
|---|---:|---:|
| R_total | 0.11328667277006 | 6.7292e-13 |
| T_total | 0.88179909132032 | 1.93512e-13 |
| A_flux | 0.0049142359096225 | 8.66418e-13 |
| A_volume | 0.0096170260819779 | 1.25941e-15 |
| energy_defect | 0.0047027901723555 | 8.65308e-13 |

功率均按入射功率归一化，比较绝对差，不用接近零的吸收作相对分母。真实reference与候选的能量缺口均约0.00470279（0.47%）；候选一致不代表reference物理准确。p2未做h/p、DtN模式或积分收敛，因此R/T/吸收/衍射均维持diagnostic，不宣布完整物理通过。总H由同一curl与解析背景恢复，其同离散误差门已纳入验收；保存DG-H插值仅为附加诊断。

重要零级数据和复振幅见closeout_metrics.json的diagnostics.zero_order/significant_modes；全836模式保留在原始备份。未列模式不代表0。制造源的通量吸收差1.028807e−4略超1e−4诊断门，原样保留false；该人为体/端口源没有入射照明功率解释，不能把它改判为物理散射失败或物理通过。

## 5. 未运行、负结果与决策

| 项目 | 状态 | 具体理由 |
|---|---|---|
| N4单次双扫 | failed residual gate | 真残差0.11157；按任务约定继续外层18步后通过 |
| N8 | not_run | 原网格仅4个z单元，不能合法切8区；不重划全局网格 |
| p4成对对照 | not_run / predicted admission rejection | 同网格推断24,000FE+836aux；direct 4n²16=39,476,921,344B≈36.765GiB，超过既定2GiB门，未实际启动 |
| 缓存/阶段部分统计 | not_recorded | 未保存初始冷热清单、输出单独计时等，不事后伪造 |
| 最小测试首次启动 | preserved setup failures | pytest缺失；isolated执行缺src路径；改为显式sys.path的stdlib unittest后7项通过 |
| 发布git push | credential blocked after authorization | 原缺授权拒绝后只凭新证据重试一次，认证缺失；实现通过授权connector发布；结果树调用曾超时/取消，未盲重试 |
| full pytest/MPI多rank/CI | not_run | 本轮只做最小相关检查，未声称全仓库或CI通过 |

本轮在具体小型非可分三维（材料同时依赖x/y/z）模型上解出了原Floquet–DtN系统，但未建立目标物理精度或大尺度容量。建议保留研究构造；若下一轮获准，先单独研究局部PML网格与因子驻留生命周期，衡量总内存/重建成本，再扩大。不得通过加损耗、删模式、扫参数或放宽误差制造通过。本轮不增加coarse space/神经网络/其他PC家族。

## 6. 复核、证据与选择性合入

7项代数检查后完成四案真实原生运行；独立checker只读保存数组，无新PDE/分解，重新构造MPC和完整原方程、E/H积分并逐样本核验资源，详见[独审V2](../review_report_v2.md)。原证据目录不改写。local源码提交与connector发布提交SHA不同，但树字节相同，最终publication记录会分别列出。

| 依赖组 | 文件/依赖 | 建议 |
|---|---|---|
| research-only numerical | src/solvers/pstddm_*.py及src/runners/pstddm_case.py；依赖原common/modes/Floquet/DtN | 保持opt-in，不能提升production默认 |
| reusable runner/watchdog | benchmarks/pstddm_partition_pilot/supervise.py与四个.dat | 仅限已冻结p2身份，扩大前重新准入 |
| checker/test | review_saved.py、test_pstddm_source_transfer.py | 同原数组/接口身份一起保留 |
| compact evidence/docs | 本目录、development_progress、development_model_registry | 可审阅，未经批准不merge |
| do-not-merge | 大矩阵/全场/JIT缓存、环境、原日志 | ignored artifacts及独立备份，不入Git |

复现入口仍为scripts/run_case.py，正式执行应由supervise.py包裹；必须新case ID防止覆盖。已用四案不重复运行。最终状态是阶段结果供审阅，不是生产或合并批准。

## 7. 备份恢复与交付

完整346,163,969字节证据ZIP已通过CRC和SHA256核验并保存到用户Space，见[备份回执](backup_receipt.json)。本次发布时云端回到较早快照，因此从该备份恢复原证据和报告；执行源码已在远端保留，运行环境未包含在备份内，没有为恢复而重跑任何PDE。40份结果记录重建后的Git树与原结果树491a22e0065539d7443210eb0338b22a74112e16完全一致。原最终文档commit ce43eb9917a023c40d2e4291fd808a6535565fda不在恢复快照中，本次仅从已保存报告及会话中的已验证数字补齐文档、统计及发布回执；不声称完整文档与旧commit逐字节相等。数值代码、原数组及原审阅保持原hash。

本轮结果已在用户明确授权后发布并回读为60be6bbdd79d0dfffba11590a6ba224bc656b2dc；本总结和审阅报告随随后文档提交发布，见[发布回执](publication_v2.json)。先前认证/确认及未知树问题保留为历史记录，已解决。
