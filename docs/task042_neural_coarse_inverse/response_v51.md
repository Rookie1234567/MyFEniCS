# Response V51：解析相位使平界面准确，三维缺口精度仍未资格

回应[Review V49](review_report_v49.md)。本轮连续完成新相位弱式、全532边界、四次完整物理解、唯一独立VERIFY、保存数组checker及完整费用。结论为 **FLAT_PASS_NOTCH_NOT_QUALIFIED**：平界面解析场准确；NOTCH两组p/h增量仍超过原1e-4门，没有以小残差或守恒代替准确性。没有训练、推理或神经预条件器；原尺寸0.7nm、2TB/48h和NN20%均未资格。

这里把已知的横向快速振荡解析地保留，有限元只表示其包络，再恢复完整物理场。改变的是场的表示和相应弱式，不是物理波矢或方程精度。电场为E=g*u，磁场使用完整curl(u)+i*kappa×u。没有把物理场投回旧多项式空间。代价仍包括新单元积分、内部消元、有限直接因子和独立物理审核。

| 完成项 | 实际值／门 | 结论 |
|---|---|---|
| FLAT 80hex/p4解析total E/H/curl | 3.85798e-8／4.63574e-8／4.63574e-8，门1e-4 | PASS；selected最大2.45206e-8 |
| FLAT完整功率 | R=0.113433408921，T=0.882458998614，A_volume=0.004107592466；最大逐mode功率误差8.83182e-13 | 全解析功率门通过 |
| 四状态独立原true/native | 2.88117e-12、2.93150e-12、4.77771e-12、4.67476e-12，门1e-6 | 全部原方程通过；最大增广4.80787e-11 |
| 原内部恢复／slave／恒等式 | 最大单元操作尺度1.48409e-15；slave严格零，master差0；恒等式约4.57e-16 | 恢复通过；不删除非零内部端口支撑 |
| NOTCH p4/p5 | total E/H差1.38146e-4／1.35253e-4；scattered E/H差9.61667e-4／9.41540e-4；复通道1.84815e-4 | FAIL：场、selected、通道超过1e-4 |
| NOTCH p5/Z2 | total E/H差1.22562e-4／1.22545e-4；scattered E/H差8.53183e-4／8.53072e-4；复通道1.51246e-4 | FAIL：唯一z细化不能授准确性锚点 |
| 完整532及共同积分 | q47/q63全部通过；共同q23/q31操作缺陷1.53547e-15／7.29380e-16 | 独立积分可信；不能解释为求积不足救场 |
| 保存模式的独立功率重算 | 四状态×532，无原power函数调用；最大坐标/功率缺陷7.11e-15 | 位于原参考面的全部模式和能量重新核验 |

[完整结果](outcomes/phase_explicit_full3d_accuracy_v51.md)及[科学门](outcomes/records/phase_accuracy_checks_v51.json)分别列出原方程、场、复通道及功率。p/h的功率差均通过：最大逐mode差8.28146e-7／8.42200e-7，门1e-6；能量约1e-13。但不能据此覆盖场和复振幅失败。高阶消逝模式的raw辅助坐标差保留为0.659631／0.999024；实际参考面复振幅按已冻结解析相位计算，没有拟合幅相、删项或归一化守恒。

z细化由N5已预登记的梯度能量指标选择，x/y/z为0.0001223084／0.0000032021／2.8128084。它是选择一次对照的指标，不是误差界。保存数组归因显示p5/Z2场差平方中，缺口外空气占约68%，Si块约24–25%，缺口自身约3%；E差以y分量为主。差异是分布的散射场，不只发生在两cell缺口，也不能宣布唯一根因。[区域与分量](outcomes/records/physical_error_regions_v51.json)不新增FE动作。

| 全过程成本，shared-workstation | dat启动到退出下界s | 采样整树峰GiB |
|---|---|---|
| FLAT/p4 | 294.248354 | 1.032608 |
| NOTCH/p4 | 118.554778 | 1.007263 |
| NOTCH/p5已返回解＋修复后的补审 | 625.778514＋142.573980 | 2.245213／1.228489，顺序峰不可相加 |
| NOTCH/Z2 p5 | 841.587038 | 3.496330 |
| 唯一VERIFY | 788.376920 | 1.523537 |

上述数值不是从几何开始无缓存、无争用的统一计时：每个物理解新建全部数值因子；同namespace的OS/JIT缓存没有清空，q资格、失败准备、补审和唯一VERIFY另列并全额收费。单个启动前activation及部分历史细分仍unknown，不能填0。相同场门下的正式性能加速INCONCLUSIVE。[冷费用](outcomes/records/cold_n1_costs_v51.json)使用互斥阶段计时，父子计时不重复累计；[最终资源与累计账](outcomes/records/resource_costs_final_v51.json)包括准入、launcher、collector、末次文档检查和失败，历史已知下界96250.16526014329s保留。累计研究费用不是目标冷N=1的48h证明。

有限全局p4/p5直接因子明确存在，分别只作为本批准确参考authority，均在完整向量保存后释放；不重开旧生产p4强逆。Z2先拒绝29.659995GB的三倍稠密粗上界，转为装配容量门和已有MUMPS的可靠symbolic评估：1768 decimal MB，因子/workspace预留2倍、再加live整树及2GiB后续空间，计划7944717312B；实际ICNTL(23)=3536MB、OOC=0。未更换ordering、shift或后端，采样峰3.496330GiB。它不是factor-free或可扩展生产资格。

NOTCH/p5原求解已经合法返回，随后发生实数值复波矢到float的后处理错误。保存原失败610.305686s及最终数组hash；最小修复只补原作用审核、输出、p/h积分和指标，**未重新求解**。原求解source为`9100a925a2a074a2a305def8f27ec992451178c7`，补审source为`62537a4e7c56336160ec59f022081841abb8566c`。F4 source为`db95e8cf859385f02eef12f6bdd1a942f2cec2e7`，NH source为`c3009dd66993b42961666758068f343cd67044e8`，VERIFY source为`80e227660baac5bd89b0220455e4207bcb1d51d6`；最终文档HEAD另报，不冒充实际run source。[索引](outcomes/records/delivery_index_v51.json)绑定input/resolved、材料/模式、数组和源版本。

仅从冻结extra@8d617d4d206b08f38279320b67188db1b8ccd301迁移小数学闭包；不搬其build_model、340通道、材料或训练。[迁移与分工](outcomes/records/minimal_migration_v51.json)逐文件列donor blob和hash。本Task042与隔壁最新5nm学习/greedy路线分开：没有导入活跃工作树、通知、接管或修改其进程/文件，旧恢复FAIL保持。

本批从2026-10-05T09:05:22.289231Z冻结7h，heavy-stop15:20:22.289231Z、交付截止16:05:22.289231Z不刷新。MPI1、complex128/int64、数学1、Loader0、GPU0、ownswap/OOC0；现场逐stage选核，原PSI/增长余量/自有锁保持。请求0.5s采样，科学及收尾全库存实际最大间隔见最终资源账；科学队列最大2.374964s，不能称连续cgroup硬峰或绝对零干扰。早期一次CPU准入拒绝后215.239782s有界冷却计入总窗，后续科学队列未触资源停止；邻任务可比性能指标不可得，不归因自然阶段变化。

相关10项targeted tests、八入口schema、超时清场、实际curl退化及复非互伴非零内部/40port代数覆盖已完成；最终只做相关源码Ruff/compile及一次紧凑15项文档合同。[测试](outcomes/records/tests_v51.json)和[文档实际字节](outcomes/records/documentation_checks_v51.json)分别绑定。不例行全库pytest、全仓索引或旧artifact审核，不声称CI。GitHub精确页未取到视觉证据，NOT_VERIFIED，不重跑PDE。

唯一下一pilot建议：在独立新合同中，仅做同物理NOTCH/p5的预登记Z4完整对照，检验剩余z分辨与分布散射场；其44532凝聚行已超本批35000门，必须事前重新给出可信容量和完整物理审核，不在本批启动。[两个下一几何尺度](outcomes/records/next_scale_capacity_v51.json)给出1280/10240cell、483200/3852800独立FE的载荷区间；因子fill、同时RSS及迭代数unknown，且当前NOTCH准确性失败，不能直接扩模。

本批没有神经增量。即使尾部因子和solve全免费，本批诊断时间也最多仅省约2.0–2.7%，不足20%；準备替代的更乐观必要界保留完整冷数据/训练/部署/审核费用，最佳匹配准确传统引擎仍unknown。[20%必要条件](outcomes/records/necessary_NN_cost_conditions_v51.json)不授NN收益。F5、OC未准入：F4已经准确；OC只保留条件schema，真实保底执行未资格，不能写可运行通过。四次完整solve和一次VERIFY完成后冻结，不再加p/h/模式或训练。

旧task/review/response/raw不改。结束后closed、active null、清场/锁释放、提交推送唯一分支并核实实时remote、clean/upstream0/0；随后暂停，**不自动通知隔壁**，不merge、不改dot/master、不用subagents或重置卡。
