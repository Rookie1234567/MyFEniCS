# V15 证据导航：固定科学诊断完成

当前结论为P5两阶无明确h输出收益、R00_s超固定精度容差；原A1/P4正式FAILED与后处理诊断分列。正式7/8，历史末槽封存，无合并批准。

| 目录 | 实际范围 |
|---|---|
| focused / P2 | 10项定向测试、真实seed8闭包/FE116740与旧A2数组复算 |
| P3_failed / A1_scope_validation_failed / A1_scope_validation_passed / A1_saved_primary_recovered | A1正式失败、fixture失败/恢复与固定primary非PDE后处理 |
| P4_failed / h_validation_failed / h_validation_recovered | h正式写出失败、snapshot fixture失败与4项恢复+9项历史复用 |
| P5 | 原未用P5的完整两阶三场比较、原件标准库重算、主控trace/资源联合终态 |
| launch | 实际launch同字节归档；不授权重跑 |

完整数值与逐次源码身份见[机器结果](../v15_bugfix_and_scientific_results_v1.json)、[Response V15](../../../response_v15.md)。原trace/资源/NPZ仍在ignored artifacts，轻量索引保留path/hash和必要实值。

## 历史启动前导航（保留原文语义）

### V15 用户授权的局部 bug 恢复

用户要求普通实现问题修复、验证后继续原科学链；数值门保持不变。原失败与旧额度不回写。

本目录的启动脚本为实际 ignored launch 的同字节副本。先运行受监控的 10 个定向节点（真实 main 第一项），核对修复后的字段和新恢复来源的磁盘读取成功及拒绝行为。测试通过只授予本次有限工程资格。P2 仍须重新取得实际空间审计、旧 A2 数组响应和完整终态，再决定后续正式阶段。

当前为启动前冻结；未将计划或静态检查写成运行通过。
