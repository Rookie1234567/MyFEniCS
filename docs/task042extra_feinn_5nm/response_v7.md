# Response V7：p4装配预算阻塞，U0通过并安全收口

本轮完成了同网格 p3→p4 的完整场/旋度嵌入、原算子配对与数组容量资格，但唯一 p4 参考在装配阶段耗尽数值工作窗口，状态 **P4_REFERENCE_TIME_BLOCKED**。没有获得 p4 参考场，因此未启动 p3/p4 比较，不能判断阶次变化大小。已按预算主动请求自有 watchdog 停止，原因明确；这不是 OOM 或 p4 精度失败证据。

| 身份 | 准确值 |
| --- | --- |
| 执行分支/worktree | task42extra_feinn_5nm / /home/fenics/Projects/NN-Lab-V2 |
| 本页生成前HEAD | c2bfd3ce2ae5d499b6d8afe6a0b3fc3cf743a2a9 |
| U0和唯一p4实际clean source | 76d863e43d2fc1b5bed8b1c835aa6f43bb2c93d2 |
| 停止后修正/checker source | c2bfd3ce2ae5d499b6d8afe6a0b3fc3cf743a2a9 |
| review发布 / 审阅基线 | ecabef960cdf1ac194ef293ff83c65b14e8b7ba3 / fa83e9cb751ecd213e04ce79804cda4643fc3232 |
| 冻结base | fbac3d8777fcfd897d93b898cb9f460f79ddd6ff |
| canonical common Git | /home/fenics/Projects/Maxwell3D-Lab/task-repository.git |
| upstream | remote origin；merge refs/heads/task42extra_feinn_5nm；共享fetch未映射，@{upstream}不可解析；精确refspec和显式tracking ref核对 |

## U0–U2实际阶段

提高阶次让同一个单元内的电场能表达更多细节，几何和网格都不变。准确 p3/p4 场的差可检查离散敏感性，不能直接当连续误差上界；代价是更大的有限元系统及一次独立准确参考。原 NN 对同一 p3 方程的失败与这个精度审计是不同问题，旧结论不改。

| 模型 / measured身份 | p3原只读参考 | 本批p4 |
| --- | --- | --- |
| M5波长 / geometry / h | 5nm / 原Si-air三维缺口 / h1.25nm | 相同 |
| cell / FE / 积分 | 384hex / N1curl p3 / volume与DtN q15 | 384hex / N1curl p4 / volume与DtN q15 |
| 含slave / slave / 独立复FE | 34050 / 2082 / 31968 | 78936 / 3672 / 75264 |
| 独立边 / 面 / 内部 | 3744 / 14400 / 13824 | 4992 / 28800 / 41472 |
| 增广rows / 完整端口 | 32008 / 40 | 75304 / 40；rows现场核实，完整CSR未取得 |
| 材料表SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 | 同字节，只读 |
| native packet SHA256 | 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215 | 062137c4c5be83b62be6a5373cfa24244f203f0b37244aeb4fb0b8feb75eb9ad |
| p3 reference SHA256 | 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7 | p4参考packet NOT_RETAINED_NO_SOLVE |

| 跨阶非零复场 / measured | E operation-relative | curl operation-relative | MPC恢复相对差 | 要求 |
| --- | --- | --- | --- | --- |
| small_transfer | 4.63720219433e-16 | 4.82654968846e-16 | 5.94382871167e-16 | ≤1e-10 |
| M5_transfer | 4.58598982543e-16 | 4.86625426167e-16 | 3.34063704495e-16 | ≤1e-10 |

U0完整边/面/内部、非零复场/多分量、orientation/MPC与三方向原A/A*、增广/端口载荷配对均≤1e-10。数组/转换derived上界4447112320B、小于内部12GiB规划线；symbolic容量未取得，不冒称通过。原体/面q15、材料、背景和完整40端口不变，普通p4面默认不改。

launcher在 3450.00074385s 到达原3600s的150s收口边界时，由Codex按用户预算请求停止。先核对自有PID/start_ticks和one-run命令，再只向launcher发SIGTERM，由既有watchdog终止/回收自身后代。原分类USER_CONTROLLED_STOP、worker exit−15，descendants_cleared=true；完整退出wall 3452.53531242s，剩余 147.464685061s≥120。本批全部数值阶段树峰 1586601984B（1.47763824463GiB），自身swap0，没有内存硬线、监督失效或OOM证据。

| 原方程/功率 / measured、原rhs或入射功率归一 | p3原参考 | p4本轮 | 验收 |
| --- | --- | --- | --- |
| native_relative | 6.78883619212e-12 | NOT_RUN | 参考各≤1e-10 |
| augmented_relative | 6.78883897883e-12 | NOT_RUN | 参考各≤1e-10 |
| original_total_augmented_relative | 3.514516446e-12 | NOT_RUN | 参考各≤1e-10 |
| independent_DOLFINx_total_native_relative | 3.26041877377e-12 | NOT_RUN | 参考各≤1e-10 |
| R_total | 0.812426499057 | NOT_RUN | 不能比较 |
| T_total | 0.0324623960953 | NOT_RUN | 不能比较 |
| A_balance | 0.155111104848 | NOT_RUN | 不能比较 |
| R00_s | 0.812256818464 | NOT_RUN | 不能比较 |
| R00_p | 1.25634444139e-26 | NOT_RUN | 不能比较 |
| R00_total | 0.812256818464 | NOT_RUN | 不能比较 |
| A_volume | 0.155111104847 | NOT_RUN | 不能比较 |

没有p4参考packet，U2未启动；total/scattered全场E/H/curl、六点复样本、四类40级复通道、逐级功率、R/T/A/A_volume/R00及原区域的p差异全部NOT_RUN，见[未运行CSV](outcomes/records/p3_p4_comparison_v7.csv)。p4参考未通过资格的原因是未完成，不是测得残差超限。不会根据这个停止推翻p3准确代数参考，也不会把旧NN失败归因于网格。

## 已修正的运行保全与证据边界

C1的中断manifest仍把physical_model_sha256/actual_operator_packet_sha256写成p3依赖packet；p4实际hash只会在正常worker结果后更新，中断没走到该处。原manifest/physical_model_sha256.txt保留原字节，不能当p4算子hash。实际p4输入062137c4c5be83b62be6a5373cfa24244f203f0b37244aeb4fb0b8feb75eb9ad由U0原始packet、失败run冻结依赖和degree4 physical_model事件核清；C1程序顺序是先加载该packet，再生成这个事件。compact binding明确标raw_manifest_hash_valid_for_p4=false，没有重定义历史hash。C2已在worker启动前绑定p4身份，并让V7 watchdog直接约束长原生调用到150s边界，避免只靠Python阶段间检查。新增10项原字段/截止/身份定向tests与Ruff/compileall通过；修正后的入口本批没有正式重放，因此没有fresh p4完成证据。

已排除此次测试的跨阶映射、完整未知量/内部矩、原action/端口及物理身份问题；p4实际精度、因子容量、p敏感性、h/端口截断和连续精度仍未知。c_scattered、alpha_scattered/total无已保存p4值；symbolic启动没有开始记录为NOT_RETAINED，完成0；numeric/solve0；新完成Maxwell factor、Gram/Gsolve/NN训练0。新authority为REFERENCE_ONLY、training_reference_allowed=false、neural_solver_qualified=false，旧V1–V6标签及负结果未改。

## 全账、交付与一个下一步

| 阶段 / measured | 完整launcher wall / s | 同时树RSS峰 / B | CPU | 自身swap峰 / B | 实际结果 |
| --- | --- | --- | --- | --- | --- |
| v7_p_transfer_checks | 158.807494071 | 1586601984 | 12 | 0 | U0资格通过 |
| v7_p4_reference | 3452.53531242 | 1289834496 | 11 | 0 | 预算受控停止 |
| v7_p3_p4_compare | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | p4参考未资格化 |

本页冻结前新增全账 3762.8175588s，含正式阶段、全部已完成辅助失败与直接/最终120s保守额度；旧45161.81665198447s及失联3284s/旧Gram/重放费用全部保留。原累计 48924.6342108s，剩 8675.36578922s。浏览器与发布后检查继续补入[最终资源账](outcomes/records/resource_costs_v7.json)。U0含轻检查181.809311786s≤1200，唯一p4≤3600，新批≤7200/原≤57600均未越线。未取得装配完成timer，写NOT_RETAINED，不重放补计；父wall已包含这段CPU费用，不能重复相加或删除。

CPU-only、MPI1、数学线程1；数值warn12/hard16GiB、自身采样swap0，轻测试/浏览器≤2GiB。启动时逐次选空闲物理核，U0 CPU12、参考CPU11；保留系统max(128GiB,10%effective)余量、至少384GiB邻增长及本任务预算。未改其他项目的进程、环境、亲和性、锁或watchdog。约0.5s同时树RSS采样，无cgroup委派，不宣称连续内核限额或零干扰；tmux管理开销是外部稀疏样本，wall计费，不能当数值树连续峰。

唯一下一步建议：review先决定如何在既定小型authority约束内解除p4装配预算阻塞并冻结比较基准，再决定是否授权[同规模单载波复包络方案](outcomes/phase_representation_plan_v7.md)的最小完整矩/VJP资格与同预算对照。本批只交计划，不实现训练器、不训练、不自动第二次factor。目标尺寸5nm和0.7nm、p5、h细化、更多端口均未启动；小型p4未完成不能推广为模型不可计算。

相位方案已核清原k_inc=(1.2564456695248023,0,-0.02193134074032823)nm的倒数、空间exp(+ik·x)/时间exp(-iωt)、xc=(0,0,3.75)nm与原MPC相位；在完整Nédélec积分点乘已知相位，不给FE系数任意乘中心相位、不重复Floquet。同3×64 tanh/6输出/8966实参数/FP64，但反射、多衍射/倏逝和界面可能仍让包络复杂，未证明一定有效。本轮只写计划，p4不得反馈训练。

[详细审计](outcomes/p3_p4_authority_v7.md)、[U0](outcomes/records/p_transfer_checks_v7.json)、[p4停止](outcomes/records/p4_reference_v7.json)、[Gate](outcomes/records/gate_decisions_v7.json)、[run/source/hash](outcomes/records/run_index_v7.json)、[最终资源](outcomes/records/resource_costs_v7.json)。独立checker从原配对、摘要、请求时钟、hash和资源样本重算，不相信单个status；新10项targeted tests/Ruff/compileall通过，原C1十项跨阶/数据测试复用；不full pytest、不重装、不让FE顶层import Torch。

summary追加V7并保留历史，进度/模型/测试/changed_files同步。[新Review V6和必要新页的真实GitHub渲染](outcomes/records/render_check_v7.json)另按DOM/截图定性，不能以本地解析当视觉PASS。最终精确HEAD、显式tracking ref/ahead-behind/clean和无自有活跃作业由Git receipt/最终终端报告给出；文档HEAD不冒充C1运行源码。只按指定ref push，之后停止等待review，不amend/强推/merge或自动重放。
