# Task042 记录索引与版本边界

| 记录组 | 当前事实 | 读取入口 |
|---|---|---|
| V1无后缀JSON/CSV | 原F0隔离与heavy资源等待历史，逐字保留 | [原run index](run_index.json)、[原Gate](gate_decisions.json)、[原response](../../response_v1.md) |
| V2实际数值 | 用户授权受控共享；11次真实尝试，F1/F2/F3/F4完成，严格粗逆未合格 | [当前run index](run_index_v2.json)、[当前Gate](gate_decisions_v2.json) |
| 同组粗返回 | 三路线各16未见RHS、完整native/port/recovery与成本；zero自身检查，不归因旧audit缓存 | [48项CSV](strict_rhs_metrics_v2.csv)、[B0](f4_b0_complete_v2.json)、[LIN](f4_lin_complete_v2.json)、[NN](f4_nn_complete_v2.json) |
| 离线数据/模型 | 384合格teacher、4rank oracle、FP64 CPU训练、basis/checkpoint/model/source hash | [当前provenance](dataset_model_manifest_v2.json) |
| 未运行p6 | 无F4合格路线，不产生official场/模态/RTA | [当前p6表](full_p6_comparison_v2.csv) |
| 测试/出版 | targeted/static checks与继承负记录、实际GitHub发布HTML | [final](final_checks_v2.json)、[static](static_checks_v2.json)、[publication](publication_checks_v2.json) |

V2为当前交付，V1等待状态不再作为本轮停止条件。原task/review/response_v1及旧数值records保留，实际数值source见每个run manifest；文档HEAD不替代source。大型raw logs、矩阵、factor、数据、basis及模型均在NN-Lab ignored目录，仅提交轻量摘要与hash。
