# Response V39：结构计算完成原优化量，M5联合数值门仍未达到

回应 [Review V38](review_report_v38.md)（15d20ed4f109fef52376a13e58c1204bce89d588）及[执行补充](review_report_v38_execution_addendum.md)（812a7818aa072379885017336bf63f9f80aa4a6c）。结果基线8136afcd8a5229974556038428b28833eafb9c91，冻结base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。**NUMERICAL_GATE_NOT_REACHED / NO_VERIFIED_NN_INCREMENT**。

首次现场状态是V38已交付、没有V39活跃run或既有更新；安全精确fetch/fast-forward后建立唯一V39窗口（2026-10-10T06:00:08Z，43200s）。本次新消息及上下文压缩没有重置窗口，也没有重复启动计算。四个V38完整Adam状态恢复参数/buffers/顺序、动量/step、RNG和c/r；没有只载权重重新建Adam。资格与成本通过后，在同一批完成两条native续算、独立逐点重建/FE compare-only、条件隔离fit续算及终验。

实际数值source为 **962de40947413b5c4c383f62189e951b92e5ecaa**；实现前序330f228073a0823ff80647ab2f7c80e4e27e6400、资源分派修复2e8dccaa20b9141d49ee55f95295f5a5fbb83441。后续文档/保存记录checker的HEAD不是数值source。每次正式run之前实现commit clean，输入、源码、环境、父检查点、材料/网格/modes/矩/参考hash均绑定。[run与源身份](outcomes/records/run_index_v39.json)。

本支只做神经。原M5为5nm、384个仿射hex、h1.25nm、第一类Nédélec p3、31968个独立复FE系数和完整40端口，Si/air真实三维缺口、原背景、双Floquet和DtN保持。体/DtN q15、网络完整矩q30、独立q60不改；没有新rank、载波、材料、loss、权重或优化器扫描。

FTTNN仍由三个小网络分别产生随x/y/z变化的复矩阵，再连乘形成三维复场，ranks=(1,8,8,1)、9072实参数；Chebyshev T0..T18控制同秩、9120实系数。本轮没有换模型，而是把相同的一维坐标核只计算一次，再准确重排完整边、面和内部矩的有限和。它减少重复核评价和反传，代价是新增索引/缓存/矩分解；材料始终留在原完整A中，不假设三维缺口或材料可分。

| measured，原M5/同p3；相对量无单位 | 无标签FTTNN | 无标签Cheb-TT | 隔离拟合FTTNN | 隔离拟合Cheb-TT | 原限值/含义 |
|---|---:|---:|---:|---:|---|
| 累计完整调用 / Adam / L-BFGS外层 | 1000/500/22 | 1000/500/23 | 500/100/17 | 500/100/18 | 调用不是epoch；LB外层含多次线搜索调用 |
| 本轮新增调用 | 954 | 932 | 460 | 467 | 继承46/68/40/33，未重放前缀 |
| native原残差 | 0.948212215045 | 0.98953446862 | 29.0452399133 | 7.41014885414 | 各1e-6，FAIL |
| 增广原残差 | 0.948212215045 | 0.98953446862 | 29.0452399133 | 7.41014885414 | 各1e-6，FAIL |
| 独立total原残差 | 0.449169796264 | 0.468744220559 | 13.7587813016 | 3.51020056301 | 1e-6，FAIL |
| G场相对误差 | 0.99947822619 | 0.999989123078 | 0.945276943861 | 0.0215169175885 | 诊断量，非单独成功门 |
| 总E L2 | 0.685383023283 | 0.685746705183 | 0.705679181285 | 0.0250191979084 | 各1e-4，FAIL |
| 散射E L2 | 0.999458825608 | 0.999989164225 | 1.02905566935 | 0.0364842100106 | 各1e-4，FAIL |
| 总H / scaled-curl | 0.683434443047 | 0.683783453926 | 0.644858998733 | 0.014360455049 | 各1e-4，FAIL |
| 散射H / scaled-curl | 0.999478716178 | 0.999989122038 | 0.943064621233 | 0.0210012376785 | 各1e-4，FAIL |
| 40复通道total | 0.562952990768 | 0.563245835038 | 0.590709354578 | 0.0821100007227 | 各1e-4，FAIL |
| 40复通道scattered | 0.999470581071 | 0.999990498786 | 1.04874941877 | 0.145778655554 | 各1e-4，FAIL |
| 40复通道outgoing | 0.270190154682 | 0.27033070574 | 0.283511864228 | 0.0394088212693 | 各1e-4，FAIL |
| 40复通道boundary_outgoing | 0.259720841948 | 0.259850665024 | 0.27610995858 | 0.039509006358 | 各1e-4，FAIL |
| 六点×总/散射E/H最坏相对差 | 1.01091661475 | 1.00031654128 | 1.47129659629 | 0.0367444706104 | 各1e-4，FAIL |
| R | 0.837413466178 | 0.837501564732 | 1.4666364954 | 0.814923672592 | 原残差未过，仅diagnostic |
| T | 0.113317049643 | 0.113256211846 | 0.312796146143 | 0.0326747286171 | 原残差未过，仅diagnostic |
| A_balance | 0.0492694841787 | 0.0492422234223 | -0.779432641544 | 0.152401598791 | 原残差未过，仅diagnostic |
| R00_s | 0.837289788478 | 0.837501555542 | 0.829319363261 | 0.812504666251 | 原残差未过，仅diagnostic |
| R00_p | 9.63826266483e-09 | 7.48056638007e-10 | 0.00263816954133 | 0.00126031072532 | 原残差未过，仅diagnostic |
| R00_total | 0.837289798116 | 0.83750155629 | 0.831957532802 | 0.813764976976 | 原残差未过，仅diagnostic |
| 独立A_volume | 0.464578132737 | 0.463356114376 | 0.549455283241 | 0.1561870145 | 由体吸收积分，非1-R-T |
| R/T/A/A_volume最大绝对差 | 0.309467027889 | 0.308245009528 | 0.934543746392 | 0.00270950605685 | 1e-5，FAIL |
| 独立体吸收能量闭合 | 0.415308648558 | 0.414113890953 | 1.32888792479 | 0.00378541570949 | 1e-5，FAIL |
| 最大逐级功率绝对差 | 0.0808577292431 | 0.0809242260629 | 0.596010076791 | 0.00126031072532 | 1e-6，FAIL |
| MPC恢复 | 0 | 0 | 0 | 0 | 1e-10，PASS |
| 端口恢复 | 1.79126681743e-17 | 3.40784863795e-17 | 3.98542513937e-16 | 7.63638553776e-16 | 1e-10，PASS |
| 实际完整模型重建 | 5.04918189575e-15 | 3.16275156736e-14 | 6.42080672241e-15 | 2.20294031273e-15 | 1e-10，PASS |
| 网络q30/q60系数漂移 | 5.17533891937e-15 | 4.3419525401e-15 | 5.99428775007e-15 | 4.53904596385e-15 | 1e-8，PASS |
| 网络q30/q60原作用负载相对漂移 | 6.9612069518e-14 | 3.88490959169e-15 | 4.28682688135e-12 | 7.36394365657e-12 | 1e-8，PASS |
| FE范数q15/q30漂移 | 2.01347078871e-14 | 1.07964625248e-14 | 1.60772519273e-14 | 1.47953290933e-14 | 1e-8，PASS |
| actual / producer联合Gate | FAIL / FAIL | FAIL / FAIL | FAIL / FAIL | FAIL / FAIL | 不挑版本；fit永久非PDE-only |

四类40复通道和六点均使用原完整向量/场范数作分母，JSON保留分子、实际分母和区域误差；没有拟合整体相位、删倏逝项或用total背景掩盖散射误差。scattered是原散射alpha，total加原背景，outgoing在top减真实入射、bottom沿total，boundary_outgoing再按原参考面相位转换。逐级功率列是outgoing按入射功率归一化，不是四类系数都直接取模平方。原残差失败时R/T/A全部仅作诊断。[全部actual/producer数值](outcomes/records/full_numerical_gates_v39.json)、[无标签全部通道](outcomes/records/complex_channels_native_v39.csv)、[隔离fit全部通道](outcomes/records/complex_channels_fit_v39.csv)。

G是电场能量加25nm²乘curl能量；独立保存FE积分与原稀疏G二次型配对≤1e-8。H_code=curl(E)/(i k0 mu_r)，本例mu_r=1；scaled-curl使用curl/k0，和H的相对误差相同，G的长度并非1/k0。实际y-Floquet=1；双非单位缝/角点是额外合成资格。参考仍为V1同p3文件0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7，无新MUMPS symbolic/numeric/solve。

两native累计Adam500后fresh原配置L-BFGS，累计各1000完整调用；FTT/Cheb新增954/932，L-BFGS外层22/23。本轮是完成既定有限优化量，不是全局最优。两fit累计Adam100、各500调用，新增460/467，LB外层17/18。最终均真实CALL_LIMIT；最后未完整返回的外层trial回滚匹配参数/optimizer/RNG，试探单列，不覆盖committed。最后审计比checkpoint元数据审计计数多1，是冻结后最终只读审核，不是额外参数更新。旧结果键zero_checkpoint在续算中表示继承边界，不能说V39重新零初始化。

每完整step先生成更新后的c/r，原子保存模型、buffers、顺序、optimizer、RNG、预算、c/r，再发布committed；每25累计调用后的完整边界审核原方程。保留最新两份及继承/Adam结束/freshLB/最终固定点；未保留中间版本NOT_RETAINED，不重放补日志。保存并不承诺SIGKILL执行finally。本批没有实际失联或训练故障恢复，不将小事务测试冒称整个run断电资格。[真实调用/恢复/匹配checkpoint](outcomes/records/resume_and_training_v39.json)。

隔离fit是参考暴露的有限表示诊断：Cheb-TT的G误差0.0215169175885，FTTNN为0.945276943861；Cheb在本流程中明显更好，但其native仍7.41014885414，场/通道/功率也未过。fit只G乘法、无G逆，标签和权重没有反馈native或0.7nm。永久reference_used_for_training=true、features_reference_exposed=true、pde_only_solve=false、production_initialization_allowed=false、pde_only_solver_qualified=false、official_candidate_results=false。有限拟合不是最佳空间oracle，也不能证明所有r8函数不可能。

| measured，原相同参数完整工作 | FTTNN | Cheb-TT | 含义 |
|---|---:|---:|---|
| 新增映射setup/s | 0.206218396081 | 0.172033020062 | 单列，不将初始化记为0 |
| 旧逐点完整工作均值/s | 39.7815866893 | 47.6840944683 | 每模型3份健康测量，旧快照hash复用 |
| 新完整工作均值/s | 0.618107247244 | 0.607903906687 | 3次梯度+更新后c/r+原子状态保存 |
| 新完整工作最大/s | 0.68212931999 | 0.671554421075 | 包含首测及3次连续工作，取最大 |
| 该完整工作均值比 | 64.3603304551 | 78.4401842852 | 仅计算内核等价工作，不是同精度求解收益 |
| native剩余保守规划/s | 1576.3332753 | 1539.00511368 | 原式≤7200 |
| fit剩余保守规划/s | 770.875449189 | 770.595904983 | 原式≤1800，保守使用native完整工作最大 |

旧逐点路径保持未修改，独立重建最终q30/q60；新映射与旧完整c/VJP配对约1e-15，Adam动量配对及freshLB外层、非零FD、batch1/8、点批128/512、三矩族/方向/MPC、缓存trial失效/恢复和原子状态资格通过。首次旧/新交替测量已保存，最终内核修正复用3份旧完整快照的hash，不重跑健康旧producer；新完整工作重新测量。完整工作包含梯度、一次更新、更新后的完整c/r、全optimizer/RNG捕获与flush/fsync保存，不只报热forward。首个张量实现native成本过门、fit规划2745.998/2914.263s失败；等价共享一维泛函后才得到表中全部成本门PASS。旧失败原JSON仍封存。[完整资格](outcomes/records/implementation_qualification_v39.json)、[互斥完整一步与失败历史](outcomes/records/complete_performance_v39.json)。

该加速使原计划可执行，**没有使M5求解成功**；64.36/78.44倍是相同状态完整工作比，不是同精度超过传统FE的神经收益。原A/A*、完整c/r、CL展开、端口和物理验收的O(N)成本保留，全局Gram因子、Gsolve、Maxwell因子及全FE Krylov完成器全部0。

| measured，串行正式attempt | 秒（含导入/准入/setup） | 同时树RSS采样峰/B | 物理CPU | source |
|---|---:|---:|---:|---|
| v39_ftt_factored_checks_attempt1 | 0.491898702923 | NOT_RETAINED | NOT_STARTED | 330f228073a0823ff80647ab2f7c80e4e27e6400 |
| v39_ftt_factored_checks_attempt2 | 328.594052734 | 759439360 | 1 | 2e8dccaa20b9141d49ee55f95295f5a5fbb83441 |
| v39_ftt_factored_checks_attempt3 | 196.206096222 | 704667648 | 13 | 962de40947413b5c4c383f62189e951b92e5ecaa |
| v39_ftt_factored_benchmark_attempt1 | 367.170747319 | 485662720 | 1 | 2e8dccaa20b9141d49ee55f95295f5a5fbb83441 |
| v39_ftt_factored_benchmark_attempt2 | 77.2867920571 | 476803072 | 0 | 962de40947413b5c4c383f62189e951b92e5ecaa |
| v39_fttnn_native_continue_attempt1 | 556.216935188 | 496128000 | 12 | 962de40947413b5c4c383f62189e951b92e5ecaa |
| v39_chebtt_native_continue_attempt1 | 545.834501735 | 516124672 | 1 | 962de40947413b5c4c383f62189e951b92e5ecaa |
| v39_ftt_independent_compare_attempt1 | 356.000329323 | 621998080 | 7 | 962de40947413b5c4c383f62189e951b92e5ecaa |
| v39_fttnn_fit_continue_attempt1 | 252.681125027 | 633483264 | 2 | 962de40947413b5c4c383f62189e951b92e5ecaa |
| v39_chebtt_fit_continue_attempt1 | 258.206474703 | 658649088 | 3 | 962de40947413b5c4c383f62189e951b92e5ecaa |
| v39_ftt_fit_compare_attempt1 | 357.439898819 | 621756416 | 2 | 962de40947413b5c4c383f62189e951b92e5ecaa |

以上正式attempt合计3296.12885183s；连续总窗还包括实现、失败、成功PSI60s、检查、等待和发布，收集时已过6668.02934599s。正式串行监督树采样峰759439360B，不追认未采样编辑区间为全流程峰；自身swap0、CPU-only/MPI1/math/Torch1。原资源门/系统max128GiB或10%和384GiB邻增长保护保持。新static约1.63MB、dynamic438144B，实际规划含AD微批远低于1GiB；数值硬16GiB不是12GiB对象预测，原envelope字段planning_cap_bytes仍表示该硬停止门，不据此宣称12GiB规划被精确实测。无16GiB分配、无OOC。[全部资源/费用](outcomes/records/resource_costs_v39.json)。

V38四个必要前缀3502.5114852511324/3385.226765566971/1631.0369326719083/1635.2432296220213s归属对应路线，但项目历史不重复收费。原native/moments/网格必要准备并非免费；loaded-packet新段实测、可复用准备、冷N=1、研发历史分账。冷N=1与项目精确历史累计仍UNKNOWN，旧10186.178641493432s波库不是FTT必要前缀但全部历史费用保留。没有共同合格精度，不能授同精度完整时间或峰值≥20%收益。

初次资格run因版本39未分派到现代准入路径，错误使用耗尽的旧V30观察池，在启动terminal/worker前失败；只修分派，原窗口/分配不改。Ruff环境/局部lint问题及初版实体重复收缩成本在同批修复并定向复验，没有因普通bug交棒。旧V38错误CALL_LIMIT、软截止越界下界25.6411715581s和未资格化保存窗口永远保留，不由本轮修复追认。[修复记录](outcomes/records/repair_log_v39.json)、[本地tests](outcomes/records/tests_v39.json)。本轮无full pytest、重装、CI声明或健康原算子/参考重算。

FTT_MAP_EQUIVALENCE_PASS / FTT_EXECUTION_COST_GATE_PASS / OPTIMIZATION_SCHEDULE_COMPLETED；M5_JOINT_GATE=FAIL，预登记native/aug≤1e-3且散射E/H/curl≤1e-3信号也未到。按合同关闭此r8/native-EUC+固定优化流程自动续算：CLOSED_NO_AUTOMATIC_CONTINUATION / FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE / FULL_TARGET_NOT_QUALIFIED。这不是所有神经表示无解，也不授新rank、seed、loss或优化器扫描。

0.7nm缩小pilot未通过无标签FTT M5联合前置，NOT_RUN，未预注册空输入。原50×25×140nm、Si17/120nm、λ0.7完整三维FE、decimal2e12B整机、ownswap/OOC0和172800s完整冷流程仍未达成。M3600较好态、最终退化、D0成本否决/D1未运行及所有历史失败/UNKNOWN保留。本支不转去W0/W1/传统PC/存储/主线，也不给其他支线安排工作。

有限GitHub实际呈现与本地Markdown结构检查分列，不因网页错误重做健康数值。最终准确HEAD、显式tracking、ahead/behind、clean、锁FREE和自身清场见最终消息/交付收据；文档HEAD不冒充数值source。只推本分支，不amend/强推/merge，完成后等待review，不通知隔壁、不自动开下一批。
