# Task042 response_v49：完整有限散射链通过，p增量精度未收敛

回应[Review V47](review_report_v47.md)。连续完成P0→P1两参考→P2两结构引擎→独立P3→唯一NOTCH p5→费用交付；没有在接口或普通bug处停止等待。实际输入为新80hex/p4、0.7nm、grazing1°/azimuth5°/s，REGULAR和真实两cell NOTCH，双Floquet、全部532端口及四q，没有沿用旧64hex/p6制造对象或384hex/p3/40端口。

装配时凝聚先在单元内消去内部系数，减小全局系统，再恢复完整场；直接参考使用有限MUMPS因子。结构引擎用四q规则背景逆帮助求解，缺口外层仍作用完整非可分三维方程。两例从独立物理零初值准备，不读取参考warm-start。代价包括全部局部/四q因子，不能称factor-free或神经训练增量。

| 实际链 | 原true/native残差 | 同p4 E/H/curl最大差 | 完整功率/能量 | 资格 |
|---|---|---|---|---|
| REGULAR直接参考 | 1.776046e−12 | authority | 能量−4.238984e−9 | 原方程/恢复通过 |
| NOTCH直接参考 | 1.567842e−12 | authority | 能量−4.239629e−9 | 原方程/恢复通过 |
| REGULAR all4q，1外步 | 9.112582e−13 | 2.021704e−12 | 最大mode功率差1.221245e−15 | 完整同离散PASS |
| NOTCH all4q，3外步 | 8.038623e−12 | 8.052334e−12 | 最大mode功率差6.550316e−15 | 完整同离散PASS |
| NOTCH p5直接参考 | 2.575903e−12 | 对p4总E差2.953190、H/curl差2.814719 | R/T差9.279756e−4/9.582776e−4 | 自身方程通过，p增量未收敛 |

审核保留原未凝聚体作用、全DtN、增广/端口、内部恢复及slave，checker从全精度原字段重新判定，不信任status。[完整结果](outcomes/complete_scattering_engine_anchor_v49.md)逐项列出E/H单位、完整532复通道、selected复场、R00_s/R00_p、R/T/A/A_volume、能量、门限及p4/p5背景定义。跨p场差大不能归为唯一根因；小残差和能量闭合不替代离散精度，原尺寸0.7nm/2TB48h/NN20均未资格。

| 完整数值冷N=1下界 | 时间(s) | 整树采样峰(B) |
|---|---|---|
| REGULAR / NOTCH直接p4 | 118.672806 / 71.547987 | 852762624 / 814084096 |
| REGULAR / NOTCH结构p4 | 137.522063 / 138.235644 | 754126848 / 775528448 |
| NOTCH直接p5 | 463.065159 | 1840844800 |

进程和数值准备冷，OS/JIT cache保留；启动前activation/解析费用unknown，故报下界。所有成本为shared-workstation，不称无争用加速。独立P4审核1683.875600s、成功最终审核/费用98.553537s及失败重放全部计入研究账，[完整冷成本](outcomes/records/cold_n1_costs_v49.json)与[最终费用](outcomes/records/resource_costs_final_v49.json)分列，历史88875.68891642192s已知下界继续累计，未知不补0。

实际source分开：p4参考`e184c386a7187bd39d485de369071cb80badea55`，p4引擎/VERIFY`5a21673150dc3cc2b282e6f9f0f319722b51d128`，p5参考`1bbcffc14ede9e11742e6ad6db89339c6f793923`，最终科学审核`06d4fe2c40d40c301b9566d6fa4ba198a31ff468`；最后文档HEAD另报，不冒充运行source。[run index](outcomes/records/run_index_v49.json)和[交付索引](outcomes/records/delivery_index_v49.json)绑定input/resolved/mesh/material/mode/RHS/数组/环境和原始日志。旧e184总库存hash、launcher占位0、factor作用/构建口径在新记录准确勘误，不回写旧证据。

本轮真实采用受控共享CPU，逐stage实时选核避忙SMT、MPI1/math1/GPU0/ownswap0，自有锁、隔离cache、计划≤8GiB、整树warn12/hard16GiB、0.5s配置监督；实际最大采样间隔以最终全集记录为准，无可写cgroup不称连续内核硬限制。未观察到资源Gate或持续压力触线，但邻任务可比阶段证据不可得，不能承诺绝对零干扰；没有操作邻任务。

已定位shape/API/writer/公共guard和p4/p5重构degree接线问题同轮最小修复，失败与费用保留；普通不收敛未当bug改参数。原JSON已有完整hash，漏写的两个单独txt已在F7修复并明确post-run补档，不重跑科学链。[repair journal](outcomes/records/repair_journal_v49.jsonl)、[18项focused测试](outcomes/records/tests_v49.json)、[15项文档及实际字节检查](outcomes/records/documentation_checks_v49.json)可重算。本地测试不是CI，GitHub视觉Cache miss/NOT_VERIFIED。

唯一下一建议：集中审阅该完整物理基线的p4/p5精度大差和准备剖面，确定准确代表性离散及最强精确共享控制后，才决定是否研究完整FE+DtN系数预测。只替代尾部factor/solve乐观也仅省1.598%/2.787%；连凝聚全省时冷teacher/训练/推理/纠错总允许量仅51.321350/46.628277s，同case完整teacher已超过，因此不自动训练或宣称NN20。[必要机会与同时峰](outcomes/records/opportunity_decision_v49.json)保留unknown。

本轮未运行新NN/codec/旧固定A、第三p、网格扫描或最大模型，未用GPU/subagents/重置卡，未修改dot/其他分支/master或merge。全部授权科学队列完成并冻结后仅轻量交付，最终closed/active null、后代清场/锁释放、clean/upstream/实时remote核实，再按`execution-review-handoff-20261005-v49`原队列一次交回并停止。
