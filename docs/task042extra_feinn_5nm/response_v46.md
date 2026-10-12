# Response V46：实际一份神经残差修正及完整验收

**本批实际神经残差增量和同态冻结控制已完整执行并验收，四份actual/producer原联合门均FAIL。修正非零且可独立重建，原残差与散射场相对基场都有有限改善；仍远离原门及研究强信号。学习隐藏层没有显示相对冻结控制的有效净收益。本具体加性配置收口，0.7nm pilot未准入；不自动增加第三网或另开窗口。**

研究对象仍为原Si/air非可分三维M5：lambda5nm、8×6×8=384hex、h1.25nm、p3、31968独立复FE与40端口、34050完整FE行；双Floquet/完整DtN、材料、A/f、背景/相位、体/DtN q15、网络q30/独立q60不变。全局A的NNZ为NOT_ASSEMBLED（matrix-free作用），不是矩阵全零。p/h/M/MPI固定，只研究一份新完整神经修正。

| measured；原M5/5nm/384hex/p3/N31968/40端口 | 学习修正隐藏层 | 冻结修正隐藏层 | 原门与口径 |
|---|---|---|---|
| 持有 / 更新 / 隐藏实参数 | 38400 / 19200 / 3360 | 38400 / 15840 / 3360 | 基网19200全冻结；新网W32/r8 |
| 新完整轮次 / 核心访问 / LSMR迭代 | 6 / 18 / 21354 | 6 / 18 / 21340 | 各最多6 / 18 / 21600；不把旧14轮记新费用 |
| 新隐藏实际调用 / 接受步 / 总变化范数 | 35 / 6 / 5.47531795873e-07 | 0 / 0 / 0 | 实际调用≤120；相对共同修正初态 |
| 修正完整系数范数 | 0.297391436244 | 0.298591707604 | 非零神经电场完整H(curl)插值 |
| 训练残差 / 原native残差 | 0.96592282125 / 0.34634593953 | 0.965866773391 / 0.346325842741 | 训练分母norm(g)，正式分母norm(f)；原门1e-6 |
| 原augmented / 独立total残差 | 0.34634593953 / 0.164064681542 | 0.346325842741 / 0.164055161658 | 各≤1e-6；原方程与原载荷 |
| 总E / 散射E | 0.0443141628975 / 0.0646210654522 | 0.0442747528659 / 0.0645635958293 | 各≤1e-4；同p3参考的实际分母 |
| 总H / 散射H | 0.0442090559875 / 0.0646528880296 | 0.0441698069567 / 0.0645954888578 | 各≤1e-4；同p3参考的实际分母 |
| 总scaled-curl / 散射scaled-curl | 0.0442090559875 / 0.0646528880296 | 0.0441698069567 / 0.0645954888578 | 各≤1e-4；同p3参考的实际分母 |
| 六点复E/H最大相对差 | 0.0726399742072 | 0.0725810261119 | 六点×四类×三复分量；≤1e-4 |
| 完整total通道 | 0.0394106022487 | 0.0393781006642 | 每类全部40复向量；≤1e-4 |
| 完整scattered通道 | 0.0699698521472 | 0.0699121486123 | 每类全部40复向量；≤1e-4 |
| 完整出射通道 | 0.0189151792287 | 0.0188995800431 | 每类全部40复向量；≤1e-4 |
| 边界出射通道 | 0.0183042963173 | 0.0182891869956 | 每类全部40复向量；≤1e-4 |
| R / T / A_balance / A_volume | 0.804741514353 / 0.0294616953879 / 0.165796790259 / 0.143057899904 | 0.804723055684 / 0.0294659334194 / 0.165811010896 / 0.143075185119 | 原残差FAIL，仅diagnostic |
| R/T/A/A_volume绝对差 | 0.00768498470441 / 0.00300070070736 / 0.0106856854118 / 0.0120532049429 | 0.00770344337282 / 0.00299646267589 / 0.0106999060487 / 0.0120359197283 | 各≤1e-5；对原同p3参考 |
| R00_s / R00_p / R00_total | 0.804721007705 / 3.04012256552e-09 / 0.804721010745 | 0.804702530201 / 3.2262655142e-09 / 0.804702533428 | 零级两极化及其和，不由功率反推振幅 |
| 独立能量闭合 / 最大逐级功率差 | 0.022738890355 / 0.0075358107587 | 0.0227358257773 / 0.00755428826273 | ≤1e-5 / ≤1e-6 |
| 实际双网完整矩重建相对差 | 6.4490655058e-14 | 6.65877204834e-14 | ≤1e-10；磁盘重开、旧逐点MLP求和后完整矩 |
| q30/q60系数 / 原A作用漂移 | 3.72890541563e-14 / 4.62652741759e-11 | 3.70969741435e-14 / 6.73599263401e-11 | 各≤1e-8 |
| FE独立积分q15/q30漂移 | 1.89574056772e-14 | 3.13762955517e-14 | ≤1e-8 |
| MPC / 端口恢复 | 0 / 3.01965655502e-18 | 0 / 3.05181293e-15 | 各≤1e-10；背景与约束只一次 |
| 残差补足次数 / 内层仍未充分 | 18 / 14 | 18 / 14 | 真伴随比≤1e-3只作内层诊断，不是容量证书 |
| 最大真伴随残差比 | 0.792042152175 | 0.842845864747 | 有限内层未解准不称整个网络全局最优 |
| actual / producer联合门 | FAIL / FAIL | FAIL / FAIL | 四份分别评分，不挑有利输出 |

## 实际工作与裁决

冻结V45原坐标最终第14轮基场，另深拷贝一个W32/r8完整修正，只有z输出清零，使初态严格零且首z方向非零。由原方程一次计算g=f−Ac0，只训练Ad≈g，再独立验c0+d。训练norm(g)=0.1043574223800681与正式norm(f)=0.29104200262261154分开，原f不变。这样增加可表达的修正函数，但没有预设准确场误差或传统FE完成器。深拷贝、缓存、背景/端口、复伴随、非零FD、完整矩和恢复负控先通过，clean实现后才串行完成checks→prepare→learned→frozen→compare。

两条各6轮/18核心；学习21354计费LSMR/35隐藏实际调用，冻结21340/0。base模型/buffers/RNG和c0/g身份全程不变；隐藏学习相对共同修正初态变化5.47531795873e-7、冻结0。磁盘重开两网，旧逐点路径各含一次chi，先相加再完整H(curl)插值，actual与producer分别原门评分。新修正非零，但这份新增容量未取得合格解。

| 独立评分对象 | 原方程 | 完整场/点/40通道 | 功率/吸收/能量 | 重建/MPC/端口 | 求积稳定 | 联合 |
|---|---|---|---|---|---|---|
| RESIDUAL_FTT_R8_LEARNED | FAIL | FAIL | FAIL | PASS | PASS | FAIL |
| RESIDUAL_FTT_R8_FROZEN | FAIL | FAIL | FAIL | PASS | PASS | FAIL |
| RESIDUAL_FTT_R8_LEARNED_PRODUCER | FAIL | FAIL | FAIL | PASS | PASS | FAIL |
| RESIDUAL_FTT_R8_FROZEN_PRODUCER | FAIL | FAIL | FAIL | PASS | PASS | FAIL |

| 路线 | 末态原R / 散射E / 散射H | 相对冻结基场改善百分比 R/E/H | 隐藏相对共同修正初态变化范数 |
|---|---|---|---|
| 学习修正隐藏层 | 0.34634593953 / 0.0646210654522 / 0.0646528880296 | 3.40771787638 / 21.6597534329 / 21.6687655985 | 5.47531795873e-07 |
| 冻结修正隐藏层 | 0.346325842741 / 0.0645635958293 / 0.0645954888578 | 3.41332266197 / 21.7294239714 / 21.7383084776 | 0 |

学习与冻结的末态原R/E/H差为2.00967891886e-05 / 5.7469622874e-05 / 5.7399171745e-05（学习减冻结）。隐藏层确有六次接受、35次真实调用，总变化5.47531795873e-7；冻结总变化严格0。但不能把轻微轨迹差称隐藏学习增量或资源收益：两者都未达到同严格精度，内层仍未充分，参考只作审核。增加一份网络改善了本次有限场近似，约两次各2.5h新训练仍未得到合格解，不能认定额外容量已值得用于生产。

原方程R约0.346而门1e-6；散射E/H仍约百分之几而门1e-4，六点、完整复通道与功率/吸收/能量另列实际数值。完整读出、约束、端口或求积如果通过，只说明这些工程路径可靠，不修复物理精度。两条实际重建及MPC/端口、独立求积均通过原门。这不是rank8容量不足或所有神经方法无解的证明，也不是continuum convergence。

| 新增完整轮次；原R/散射E/H | 学习修正隐藏层 | 冻结修正隐藏层 |
|---|---|---|
| 1 | 0.351299310633 / NOT_RUN / NOT_RUN | 0.351299407451 / NOT_RUN / NOT_RUN |
| 2 | 0.349388093479 / 0.0752638988586 / 0.0752937815247 | 0.349384728047 / 0.0750623232463 / 0.0750922764169 |
| 3 | 0.34798568736 / NOT_RUN / NOT_RUN | 0.347995791523 / NOT_RUN / NOT_RUN |
| 4 | 0.347158771485 / 0.0678347793087 / 0.0678663550246 | 0.347148313552 / 0.0678893846776 / 0.0679209114853 |
| 5 | 0.346726140903 / NOT_RUN / NOT_RUN | 0.346708492159 / NOT_RUN / NOT_RUN |
| 6 | 0.346345939539 / 0.0646210654522 / 0.0646528880296 | 0.346325842749 / 0.0645635958293 / 0.0645954888578 |

第2/4轮返回独立R/E/H标量，未采用旧0.1早停；第1/3/5轮E/H NOT_RUN，第6轮在完整验收中评分。每个完整更新原子保存双网与完整c_base/c_delta/c_combined/r_original/g/RNG/计数；未保存的LSMR内态不称可恢复。

LEARNED实际及producer原M5联合门均FAIL，故0.7nm缩小三维pilot为NOT_RUN_LEARNED_M5_JOINT_GATE_FAILED，未建立空输入，也未迁移或缩放参考系数。失败原因是数值原门未过，不是额外时间、内存或前端限制。剩余时间不允许绕过准入。研究强信号还要求原R≤1e-3、散射E/H各≤1e-3与完整稳定性，本批均未达到。

保持FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED；没有同严格精度20%NN资源收益。下一步只等待对此有限负结果的审阅，不自动续训/增宽/增rank/改loss/加PC，不恢复旧谱或oracle。原尺寸0.7nm的任意非可分3D目标仍需独立授权且有证据的新方案。

## 费用、测试与连续修复

唯一43200s窗口保守起点mono=1694664.73632、登记UTC=2026-10-12T01:47:49.875460+00:00。登记时另预扣300s覆盖初始只读检查；UTC是登记时间，不冒充更早的精确检查时间。原始初检精确时刻未保留。此窗不重开V45窗口；证据采集时已过24676.3610166s、余18523.6389834s，最后至少3600s验收发布预留。正式五阶段实际attempt合计19154.521689s，包含准入、加载、setup、两段LSMR、隐藏、保存与隔离审核；嵌套算子计时不能再相加收费。轻任务和发布尾段另记。

| stage | 分类 | CPU | 实际attempt/s | 同时自身树采样峰/B | swap/B | 实际source SHA |
|---|---|---|---|---|---|---|
| v46_residual_branch_checks | COMPLETED | 0 | 391.442466164 | 406683648 | 0 | 9022141a43e60d2e1a926a04003e076ea04497b8 |
| v46_residual_branch_compare | COMPLETED | 18 | 449.33598041 | 627265536 | 0 | 0b8fb32fbf180b5dc775dac6642f27cd198afa60 |
| v46_residual_branch_frozen | COMPLETED | 12 | 9105.53692083 | 869515264 | 0 | 0b8fb32fbf180b5dc775dac6642f27cd198afa60 |
| v46_residual_branch_learned | COMPLETED | 12 | 9139.93418654 | 935538688 | 0 | 0b8fb32fbf180b5dc775dac6642f27cd198afa60 |
| v46_residual_branch_prepare | COMPLETED | 2 | 68.272135074 | 351363072 | 0 | 9022141a43e60d2e1a926a04003e076ea04497b8 |

两条训练均在10800s内正常完成六轮，没有安全、ABI或不可恢复数据出口。正式阶段自身树RSS最高采样值935538688B（0.871288299561GiB），ownswap/OOC=0；这是有限采样值，不是精确cgroup峰或主机峰。每个阶段先60s真实主机PSI稳定观察并现场选择空闲物理核；学习/冻结用同一CPU12，比较另用现场合格核，不据此授隔离速度优势。AD/缓存合计1GiB、轻2GiB和原系统/邻增长保护不变。artifact仅限定新V46目录，未把整个旧历史库计入新批存储上限。

逻辑上每条部署还需已付基场前缀12788.395328277858s，含V42/V43 4545.707329502931s、V44 5483.305245663039s、V45原坐标两个attempt 2759.382753111888s；共享研发账不重复收费。必要mesh/native/moments冷准备仍缺项，不能把checkpoint后费用当完整冷单场。完整冷N=1、历史项目精确累计均UNKNOWN；未留细分的日历空档NOT_RETAINED，不称训练秒数。

本地定向测试JUnit并集117个不同通过case；重复执行不累加。C1前最终116项通过，随后分母日志修复的44项定向复验包含一个新case，合计117。Ruff、compileall、五dat validate-only及diff检查通过；没有full pytest、重装或CI声明。

正式checks/prepare在C1 source 9022141a43e60d2e1a926a04003e076ea04497b8通过。随后只修legacy native_trial日志语义和manifest的prepared身份：正式native_trial明确为原norm(f)分母，训练native_trial另名保存norm(g)。这次是静态记录歧义，没有数值方程变更、没有失败PDE或g重算。44项复验后clean提交C2 0b8fb32fbf180b5dc775dac6642f27cd198afa60，直接继续学习、冻结与compare。所有健康基场、参考、g、资格和准备保留；不用日志修复解释完整场误差。原修复日志在[repair_log_v46.json](outcomes/records/repair_log_v46.json)。

资格覆盖复杂非Hermitian残差符号/分母、非零背景端口、冻结/深拷贝无别名、严格零修正及非零z方向、三轴纯虚/复伴随和非零隐藏FD、先加点值再完整矩、缓存失效与wrong-base/g/hash/phase/partial恢复负控。真实M5首次z方向范数20.6340220961；三轴9见证最大adjoint配对6.445e-15、旧点值配对2.245e-15、原A配对1.554e-13，均≤1e-10；非零隐藏FD稳定段误差均≤1e-5。重复背景端口负控差0.47684290868，说明错误相加会被拒绝。每项原数值和JUnit名称均保留。

## 来源、证据与选择性合入

审阅发布5a48c802486875ac628e6e710b5caf240769248b，结果基线9b4832e79cc57e852c7a70f32c527d7b41e2b348，原任务base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。资格/prepare source=9022141a43e60d2e1a926a04003e076ea04497b8；两路线/compare source=0b8fb32fbf180b5dc775dac6642f27cd198afa60；后续交付HEAD只代表文档与证据提交，不替代数值source。

设计SHA256 e6187f3bd04389777e24af27dd7b38a9c829728bac2ab6cbd4142c37c0fd5e1b。固定g/c0档72755ea06625041b36e6bcd1aca91e05632fc455c07d14cfeb6e8d58c2e22a53（1023476B）；共同零修正/冻结基网档da1b586fa6c93f2e681dc3b10d4001f339eeefae8f1a59abe63a4715535b1002（354241B）。g数组hash9ee7039a391203426452e4bd45ca92aae2d48a55257d4acfa1febb609ccba528、c0数组hashcda595e3bc687219e6a2b0d8b8a1bf95418f97d47fe2b4f001c1f4be560a3214、原f数组hashea17da9735541104f770ec58390a71c99bd26c53fb09ff85e2b7ffe4b68e575f分别保存。只有FE compare-only读取原同p3参考0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7；训练、model proof和compact writer均不读参考系数。

证据入口：[原run/source/hash](outcomes/records/run_index_v46.json)、[资格/准备](outcomes/records/residual_branch_qualification_v46.json)、[两路线/检查点](outcomes/records/residual_branch_routes_v46.json)、[双网冻结与隐藏消融](outcomes/records/same_state_hidden_ablation_v46.json)、[内层36核心](outcomes/records/conditional_inner_solver_v46.csv)、[隐藏/轮次](outcomes/records/hidden_updates_and_rounds_v46.json)、[隔离标量](outcomes/records/isolated_scalar_continuation_v46.json)、[完整四份Gate](outcomes/records/full_numerical_gates_v46.json)、[功率/能量](outcomes/records/power_and_energy_v46.csv)、[四类40复通道](outcomes/records/full_40_complex_channels_v46.csv)、[六点复场](outcomes/records/six_point_complex_fields_v46.csv)、[范数/相位/通道定义](outcomes/records/channel_and_norm_definitions_v46.json)、[测试](outcomes/records/formal_tests_and_qualification_v46.json)、[成本](outcomes/records/resource_costs_v46.json)。大型PT、mesh与矩阵留在ignored artifact；轻量记录逐项hash绑定。

五dat通过同一个durable入口顺序执行，wrapper选择资格化环境并调用scripts/run_case.py。全程CPU-only/MPI1/math1/Torch intra/inter1；ML CPU Torch2.7.1、网络float64/complex128；FE PETSc complex128/int64、DOLFINx/Basix0.10来自同一Linux ABI。成功进程组均清场，未改变其他工作树或生产分支。GitHub实际呈现及最终推送/清场在后续发布尾段单列，本地Markdown检查不能冒充视觉PASS。

| 依赖组 | 实际变化/行为 | 依赖、测试、fresh证据与顺序 |
|---|---|---|
| production numerical/core | 无合格production新默认；仅opt-in residual view、双模型/恢复与原训练钩子 | residual_branch/io/qualification → core_training/checkpoint/mapping；117本地定向与fresh M5 checks；原门FAIL，不提升production |
| reusable runner/watchdog | 复用CoreWorkerProfile/既有durable/watchdog；新增schema16 profile及五输入 | campaign → worker → action adapter → source/prepare manifest；五dat validate及串行fresh五阶段；资源阈值未放宽 |
| checker/benchmark | 旧独立点值支持双网先加后矩；FE compare-only与saved checker复用 | verification/checkpoint points、隔离joint反馈；actual/prod四份fresh审核，原参考只读；功率diagnostic |
| compact evidence/docs | 本批完整Gate、40复通道、六点、成本、修复、source和当前入口 | 依赖两完整路线及compare；原字段独立重算；后续文档SHA不冒充数值source |
| research-only | 固定基场+一份W32/r8加性修正及学习/冻结消融 | 有有限改善但完整FAIL、无强信号；不作为默认/生产初始化，独立神经研究配置关闭 |
| do-not-merge | ignored PT/大数组、未资格化研究默认、自动0.7/第三网络/历史扫描 | 没有production/master merge许可；不把研究负结果升production |

建议仅依赖顺序审阅：residual数学与恢复 → 原trainer opt-in钩子 → schema/profile/输入与独立双网读出 → tests → compact/docs。无生产合入建议或授权。完整专题及公式/六点/通道解释见[ftt_one_residual_branch_v46.md](outcomes/ftt_one_residual_branch_v46.md)。[最终绑定核对](outcomes/records/delivery_check_v46.json)、[端到端研究用途](outcomes/records/end_to_end_research_use_v46.json)、[本地文档合同](outcomes/records/markdown_check_v46.json)、[发布/清场尾段](outcomes/records/publication_tail_v46.json)与[实际呈现状态](outcomes/records/render_check_v46.json)单列。实际GitHub呈现未取得前只记NOT_VERIFIED，不把本地解析当视觉PASS；精确最终HEAD、tracking与clean在推送尾段记录并对用户报告。

发布阶段的定向检查在已通过原字段/source核对后，因markdown_check_v46.json自引用收据尚不存在而失败。失败日志、4.554s受监督用时及60s准入保留；先建立明确NOT_RUN的bootstrap收据，再只复验八个新页/当前段及历史保留，不重算健康原门或PDE。此修复只涉及本地发布顺序。

数值完整包已先推送ca122c6a3e944b7782ebdd3e5635f41bf77acb3a，并精确fetch同分支确认0/0、clean。随后真实GitHub两页1440×5200视口检查通过，专题两条新公式、关键结果/隐藏/趋势/原门表正常呈现；未截取的尾段及其他页为NOT_VERIFIED，不授全文视觉PASS。浏览器轻阶段19.729s、同时自身树峰1066500096B、swap0，与正式数值峰935538688B分开；没有重算健康PDE。最终元数据提交不改变数值source，最后完整HEAD/0:0/clean与自身清场由最终推送后收据及用户交付报告给出。
