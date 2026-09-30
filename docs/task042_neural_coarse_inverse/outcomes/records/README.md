# Task042 记录索引与版本边界

# V12 紧凑记录导航

本批原 0.7 nm／384hex／p3／40 端口对象保持不变。T1 完成、T2 实际固定头 FD 未过 Gate、F 八试探为负、T3 未准入，T4 仅验证旧物理起点；独立 checker 的 `PASS` 表示 raw 证据一致，不表示物理解通过。正式 clean 数值源码 `d9df7068ca3310a0499164251a57841dbdfbc7f5`；旧记录以下按原文保留。

| 本批内容 | 紧凑入口 |
|---|---|
| 冻结物理、材料、输入、V11起点与四小时钟 | [身份](plan_and_input_identity_v12.json) |
| M2/物理同向量三段差及两次失败保留 | [T1](roundoff_decomposition_v12.json) |
| 同点损失、复数小试验、三方向30点真实 FD | [T2](fixed_head_gradient_checks_v12.json) |
| T3未准入、F8试探负结果与头建议0 | [journal](block_descent_progress_v12.jsonl)、[头](head_proposals_v12.json) |
| 原方程／场、未资格化物理量与全部40复通道 | [候选](candidate_comparison_v12.csv)、[通道](channel_observables_v12.csv)、[独立Gate](qualification_and_dispatch_v12.json) |
| 五次source、输入、监督与历史费用 | [run index](run_index_v12.json)、[资源](resource_costs_v12.json) |
| Review V9表格/公式本地检查与GitHub未核验 | [渲染](review_render_check_v12.json) |

以下早期“当前”均是各轮当时原文，不代表 V12 现状。

| 记录组 | 当前事实 | 读取入口 |
|---|---|---|
| V1无后缀JSON/CSV | 原F0隔离与heavy资源等待历史，逐字保留 | [原run index](run_index.json)、[原Gate](gate_decisions.json)、[原response](../../response_v1.md) |
| V2实际数值 | 用户授权受控共享；11次真实尝试，F1/F2/F3/F4完成，严格粗逆未合格 | [当前run index](run_index_v2.json)、[当前Gate](gate_decisions_v2.json) |
| 同组粗返回 | 三路线各16未见RHS、完整native/port/recovery与成本；zero自身检查，不归因旧audit缓存 | [48项CSV](strict_rhs_metrics_v2.csv)、[B0](f4_b0_complete_v2.json)、[LIN](f4_lin_complete_v2.json)、[NN](f4_nn_complete_v2.json) |
| 离线数据/模型 | 384合格teacher、4rank oracle、FP64 CPU训练、basis/checkpoint/model/source hash | [当前provenance](dataset_model_manifest_v2.json) |
| 未运行p6 | 无F4合格路线，不产生official场/模态/RTA | [当前p6表](full_p6_comparison_v2.csv) |
| 测试/出版 | targeted/static checks与继承负记录、实际GitHub发布HTML | [final](final_checks_v2.json)、[static](static_checks_v2.json)、[publication](publication_checks_v2.json) |

V2为当前交付，V1等待状态不再作为本轮停止条件。原task/review/response_v1及旧数值records保留，实际数值source见每个run manifest；文档HEAD不替代source。大型raw logs、矩阵、factor、数据、basis及模型均在NN-Lab ignored目录，仅提交轻量摘要与hash。


## V3 当前交付；以上V1/V2为各自当时历史

| 新组 / 身份 | 实际结论 | 入口 |
|---|---|---|
| authorization/source/resource | 一个有限B0/表示批次；独立几何PC，shared CPU两阶段，source clean/整树swap0 | [run index](run_index_v3.json)、[预登记](../bounded_diagnostic_design_v3.md) |
| reused artifact | 9个已有失败state、36 probes与全部reported历史，映射/范数/CPU实际核清；不是重跑旧KSP | [reuse](reused_diagnostics_v3.json)、[CPU](cpu_provenance_v3.json) |
| new structure | 252真实cell trace/MPC/all80port重叠；3个consumed非零均failed，仍有全局停滞 | [structure](structure_complete_v3.json)、[Gate](gate_decisions_v3.json) |
| complete curves/probes | 新3×257独立原方程审核，旧9×257 reported及已存4快照（缺失旧native每步不猜补）；63 probes | [history CSV](full_residual_history_v3.csv)、[probe CSV](pc_probes_v3.csv) |
| not_run | teacher/误差空间/训练/fresh资格/F5；冻结后另选未消费pool，仅计划不宣称终测 | [pool](unconsumed_test_plan_v3.json)、[范数诊断](../residual_diagnosis_v3.md) |
| checks/publishing | 定向本地、继承fail保留、实际HTML发布，不称全仓CI | [static](static_checks_v3.json)、[auxiliary](auxiliary_costs_v3.json)、[publication](publication_checks_v3.json) |

原task/review、response_v1/v2、V1/V2 JSON/CSV与旧summary正文完整保留；最新实值与边界见[response_v3](../../response_v3.md)。新全量raw/model/cache仍为NN-Lab ignored artifact，提交compact表与hash，不复制邻任务结果。
