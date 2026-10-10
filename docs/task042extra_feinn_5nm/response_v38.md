# Response V38：FTTNN真实试验已闭环，原数值门未达到

回应 [Review V37](review_report_v37.md)，发布670a33398dfa9413c275772796611e085ef17c35，结果基线5838d9c7560403164bdfee8b60d997bf4e18eeba。**NUMERICAL_GATE_NOT_REACHED / NO_VERIFIED_NN_INCREMENT**。已实际完成两条无标签训练、独立FTT重建和完整场验收，并按条件完成两条隔离参考拟合及独立验收；没有在接口、commit或普通bug处停止。0.7nm未准入、未注册、未运行。

新神经表示由三个小网络分别产生随x/y/z变化的复矩阵，再连乘得到三维复电场。中间秩8让方向耦合；它不要求材料可分，也不保证这个固定秩够用。完整边、面、内部矩仍把点值变成全部31968独立复FE系数，原Piola/orientation/唯一owner/MPC/DtN保持。它移除了旧全局波形列库和反复QR，付出的代价是每次完整梯度要重新评价所有积分点并逐微批反传。

本次是原FE方程下的复向量推广，不冒称复现[FTTNN固定v1](https://arxiv.org/html/2510.13386v1)全部算法/定理或继承GPU/分离积分优势。M5为5nm、384hex、p3、真实Si/air三维缺口、31968复FE和完整40端口；体/DtN q15不改，网络q30、独立q60。

| measured，同M5/同p3原参考；相对量无单位 | 无标签FTTNN | 无标签Cheb | 隔离拟合FTTNN | 隔离拟合Cheb | 原门/含义 |
|---|---:|---:|---:|---:|---|
| 完整loss/gradient调用 | 46 | 68 | 40 | 33 | 实际调用，不是epoch/迭代上限 |
| Adam完整提交 | 46 | 68 | 40 | 33 | native计划500；fit计划100 |
| L-BFGS外层步 | 0 | 0 | 0 | 0 | 未到切换边界如实记0 |
| native原残差 | 0.998818668222 | 3.39713275365 | 23.9624301842 | 69.6724500532 | 1e-6 |
| augmented原残差 | 0.998818668222 | 3.39713275365 | 23.9624301842 | 69.6724500532 | 1e-6 |
| 独立total原残差 | 0.473142162262 | 1.60922776845 | 11.351045381 | 33.0039622978 | 1e-6 |
| G场相对误差 | 0.999951972949 | 1.00007386653 | 0.992359773046 | 0.924916613637 | 表示诊断；不是单独成功门 |
| 总E L2 | 0.685720474906 | 0.685749540923 | 0.676128562258 | 0.60899308041 | 1e-4，原完整向量分母 |
| 散射E L2 | 0.999950913962 | 0.999993299439 | 0.985963520891 | 0.888063299314 | 1e-4，原完整向量分母 |
| 总H / scaled-curl | 0.683758070006 | 0.68384279279 | 0.678676674419 | 0.633073034538 | 1e-4，原完整向量分母 |
| 散射H / scaled-curl | 0.999951999695 | 1.00007590129 | 0.99252078696 | 0.925828410091 | 1e-4，原完整向量分母 |
| 40复通道 total | 0.563221266409 | 0.563407549573 | 0.554000981152 | 0.516885474588 | 1e-4，原完整向量分母 |
| 40复通道 scattered | 0.999946879474 | 1.00027760788 | 0.983577122116 | 0.917681998508 | 1e-4，原完整向量分母 |
| 40复通道 outgoing | 0.270318913989 | 0.270408320881 | 0.265893623884 | 0.248079979363 | 1e-4，原完整向量分母 |
| 40复通道 boundary_outgoing | 0.259839583401 | 0.259926948342 | 0.255477312273 | 0.238685192526 | 1e-4，原完整向量分母 |
| 六点×总/散射E/H最坏相对差 | 1.00010141542 | 1.00321195752 | 1.01947140001 | 1.59498623525 | 每项1e-4；全部分子/分母见JSON |
| R | 0.837465686644 | 0.837444396846 | 0.842826200746 | 0.85301393188 | 原方程未过时仅diagnostic |
| T | 0.113250263846 | 0.113278457882 | 0.112689561638 | 0.1066956969 | 原方程未过时仅diagnostic |
| A_balance | 0.0492840495103 | 0.0492771452711 | 0.0444842376161 | 0.04029037122 | 原方程未过时仅diagnostic |
| R00_s | 0.837465533873 | 0.837434397331 | 0.835688881387 | 0.831913663565 | 原方程未过时仅diagnostic |
| R00_p | 3.89034065682e-10 | 8.35791058058e-06 | 3.2665956586e-08 | 0.00292538243529 | 原方程未过时仅diagnostic |
| R00_total | 0.837465534262 | 0.837442755241 | 0.835688914053 | 0.834839046 | 原方程未过时仅diagnostic |
| 独立A_volume | 0.463379025542 | 0.463355617548 | 0.468470069893 | 0.417647483993 | 原体积分，不用1-R-T替代 |
| R/T/A/A_volume最大绝对差 | 0.308267920695 | 0.3082445127 | 0.313358965045 | 0.262536379145 | 1e-5；各项见JSON |
| 独立体吸收能量闭合 | 0.414094976032 | 0.414078472276 | 0.423985832277 | 0.377357112773 | 1e-5 |
| 最大逐级功率绝对差 | 0.0809182401449 | 0.0809442210956 | 0.0796663816356 | 0.0711562940221 | 1e-6 |
| MPC恢复 | 0 | 0 | 0 | 0 | 1e-10 |
| 端口恢复 | 1.75915145565e-17 | 3.40172199242e-17 | 4.30020026047e-16 | 1.94710150247e-16 | 1e-10 |
| 实际完整模型重建 | 0 | 0 | 0 | 0 | 1e-10 |
| 网络q30/q60系数漂移 | 4.62850445507e-15 | 4.35115838455e-15 | 4.62595770666e-15 | 4.69469059222e-15 | 1e-8 |
| 网络q30/q60原作用负载相对漂移 | 1.86670425752e-15 | 8.64289041436e-14 | 3.86943923103e-13 | 2.55991357231e-12 | 1e-8 |
| FE范数q15/q30漂移 | 2.41947760692e-14 | 2.05820086221e-14 | 1.51259340362e-14 | 7.46019046862e-15 | 1e-8 |
| actual / producer联合Gate | FAIL / FAIL | FAIL / FAIL | FAIL / FAIL | FAIL / FAIL | 不挑版本；fit永久非PDE-only |


表内都是独立保存数组checker从原数值重算的实际模型结果，producer逐位一致且也独立评分。完整JSON保留原分子、实际分母、六点四类E/H、curl、区域、吸收差与每项布尔门；四类40复通道CSV按side/m/n/polarization与原参考面排列，不拟合整体相位。scattered为散射alpha，total加原背景，outgoing在top减真实入射、bottom沿total，boundary_outgoing再乘参考面相位；功率列明确为该路线outgoing按入射功率归一化，不能当各类系数的模平方。近零规则沿原合同。[原数值与Gate](outcomes/records/full_numerical_gates_v38.json)、[无标签通道](outcomes/records/complex_channels_native_v38.csv)、[拟合通道](outcomes/records/complex_channels_fit_v38.csv)。

原G定义为电场能量加5nm长度平方乘curl能量；新增checker把稀疏G二次型与独立保存FE积分配对，容差1e-8，不改训练范数或分母。H_code沿原curl(E)/(i k0 mu_r)，本例mu_r=1；scaled-curl范数用curl/k0，二者相对误差相同，但G的长度不是1/k0。它们都来自恢复后的FE场，不用网络空间导数代替。q30/q60系数及原作用、FE积分q15/q30分别检查；系数重建通过并不能代替原方程/全场通过。参考只在独立评分/隔离拟合读取V1同p3文件0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7，无新MUMPS symbolic/numeric/solve。


FTTNN为1→16→16→48/384/48、两层sin、9072实参数；同秩Chebyshev T0..T18控制为9120实系数。两者参数接近但函数族不完全相同。seed4213701，x/y非零、z仅末层为零，初始散射严格零；未使用可选核归一化、载波、旧波库、teacher或旧权重。零散射时x/y梯度为零是连乘的正确结果，第二次非零态三轴梯度均非零；独立重建确认全部9072/9120参数都已变化。它证明真实更新，不证明求准。

无标签训练目标是原native欧氏残差，显式model_kind/metric_kind适配，不把新路线名塞进旧自动Gram分支。全局Gram因子、Gsolve、全局Maxwell因子及Krylov完成器均0；原小端口准确消元保留。每cell生成坐标，点批512，最多8cell调度，固定矩共轭转置先把余切拉回点值，再逐微批backward并释放图，没有全网格AD图、N×r²/N×P、大Jacobian或U/Q。原CL展开与O(N)向量成本仍在。

原实际M5的ky=0、y-Floquet=1；两非单位缝及角点另有使用原展开/拉回的合成见证，不能说实际M5有非单位y相位。两模型实测参数数、复连乘、完整三族、三个非零FD、实伴随、batch1/8、点128/512、同状态一次更新及完整状态保存/恢复通过；S0每模型报告2次新完整closure，旧AD/FD配对工作另计费用，不拿zero态替代资格。[完整资格](outcomes/records/implementation_qualification_v38.json)。

每完整外层step先原子保存模型/buffers/顺序、匹配optimizer/梯度/RNG/c/r/身份与预算，再发布committed。保存采用临时文件、flush/fsync、原子替换，保留最近两份及zero/固定点；已删除的中间版本为NOT_RETAINED，未到Adam500/100为NOT_REACHED。trial独立、异常恢复整套状态，不能承诺SIGKILL执行finally或宣称未实测的整批跨进程恢复。

隔离拟合从各自原零初态开始，目标是原G场误差，只G乘法，不逐步A/AH/Gsolve；起末原方程审核单列。其模型和标签不反馈无标签训练或0.7nm。永久reference_used_for_training=true、features_reference_exposed=true、pde_only_solve=false、production_initialization_allowed=false、pde_only_solver_qualified=false、official_candidate_results=false。它是有限优化诊断，不是最佳空间oracle；拟合失败只限定本配置/预算，不能证明整个r8函数类不可能。

| measured，串行阶段成本 | 秒 | 同时树RSS采样峰 / B | CPU物理核 | source SHA |
|---|---:|---:|---:|---|
| v38_ftt_checks | 944.380514273 | 827686912 | 0 | dedaec1b347d85a28bf8b608cbf677d560b86a0d |
| v38_fttnn_native | 3502.51148525 | 463720448 | 3 | 5f192b5c1e871536469174cbc009f0bc4689941a |
| v38_chebtt_native | 3385.22676557 | 463044608 | 1 | 26e71e886a42bf5ba65dcb99c7f2162d5d80569e |
| v38_ftt_reconstruct | 191.908190136 | 556630016 | 0 | a319b9b0cc09a04989111cb4494380d9912d0a5e |
| v38_ftt_compare | 223.426066808 | 794464256 | 12 | a319b9b0cc09a04989111cb4494380d9912d0a5e |
| v38_fttnn_reference_fit | 1631.03693267 | 612298752 | 0 | a319b9b0cc09a04989111cb4494380d9912d0a5e |
| v38_chebtt_reference_fit | 1635.24322962 | 608882688 | 0 | a319b9b0cc09a04989111cb4494380d9912d0a5e |
| v38_ftt_fit_compare | 351.624649055 | 617476096 | 0 | a319b9b0cc09a04989111cb4494380d9912d0a5e |


成本使用实际串行attempt墙钟和身份绑定terminal+launcher/watchdog/worker整树RSS采样，导入、两次60s成功PSI、setup、试探、失败、保存、审核均计连续总窗。未采样编辑/启动区间不追认全过程峰。物理核每次现场选择，MPI1/math/Torch1、CPU-only、自身swap/OOC0；warn12/hard16GiB，轻树2GiB，保留系统max128GiB/10%与384GiB邻增长。不改邻任务或全局环境。[完整成本](outcomes/records/resource_costs_v38.json)、[准确source/input/artifact绑定](outcomes/records/run_index_v38.json)。

坐标、核评价、收缩、矩、点余切、AD反传、A/AH/端口及持久化互斥叶计时与嵌套父计时分开；不把closure、optimizer_and_commit、network/VJP和其子计时再相加。G乘法次数实测，独立耗时未保留就NOT_SEPARATELY_RETAINED。新权重72576/72960B只是对象之一，q30/q60矩原数组约22.28/127.04MB、native约8.35MB，原CL和完整c/r保留，完整内存生命周期/派生对象账见成本JSON。

loaded-packet实测、原native/moments/mesh可复用准备、完整冷N=1和研发历史分账。冷N=1必要准备缺项仍UNKNOWN。Review V37引用的672.462895s历史FE成绩不是已闭合的同口径完整冷分母，本轮未重求参考。旧10186.178641493432s波库不是新FTT必要前缀，但研发历史永远保留；项目精确累计UNKNOWN。两条无标签结果没有共同合格精度，不能授同精度完整时间或同时峰20%收益，更不能用删掉失败NN列库冒充删掉传统FE成本。

FTTNN无标签首轮raw stop_reason=CALL_LIMIT错误，46<1000，实际为TIME_LIMIT。最后一次完整调用越训练软截止至少25.6411715581s，但总硬3600s/零swap/内存门未超；流程限定如实保留。150s收口未合格，120s完整保存窗口没有独立资格记录，因此不追认整条时间协议PASS；硬总时限、内存和零swap与该流程缺口分列。后续最小修复用最长实测完整closure/保存和1.5裕量预留，并正确标时间出口，未重放健康FTT训练。初始sandbox PID视图、Ruff环境/格式、拟合用途遗漏与所有失败/费用见[修复记录](outcomes/records/repair_log_v38.json)；不把受控停止叫OOM或数值收敛。


本配置在既定native时间/调用上限内未解准M5，研究信号的native/augmented≤1e-3且散射E/H/curl≤1e-3也未到；不能从有限拟合推出完整函数类最低误差。关闭本批r8/native-EUC及本次有限拟合配置的自动续跑，等待明确review，不自动新rank/架构/seed/优化器。旧稠密波库保持关闭，FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED / NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE保持。

0.7nm缩小缺口要求无标签FTTNN的M5联合PASS、资源安全和剩余≥7200s；第一项失败，故NOT_RUN，没有注册空输入。原50×25×140nm、Si17/120nm、λ0.7完整三维FE、decimal2e12B整机、ownswap/OOC0和172800s完整冷流程及原精度门尚未达成。旧M3600较好态/Mfinal退化、D0成本否决/D1未运行、所有负结果/UNKNOWN和费用保持，不恢复W0/W1/传统PC/存储或给其他支线派活。

仅本分支提交推送，base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。最终完整HEAD/tracking/ahead-behind/clean/锁FREE和自身清场由最终消息及本地delivery receipt报告，不把后续文档HEAD冒充数值source。有限GitHub视觉与本地结构检查分开记录，网页错误不触发健康数值重做；完成后等待review，不发隔壁通知、不自动下一批。
