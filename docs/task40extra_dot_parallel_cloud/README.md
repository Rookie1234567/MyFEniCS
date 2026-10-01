# Task40extra：dot 独占云端并行研究

本分支由用户明确指定为 **dot 独占执行分支**：`task40extra_dot_parallel_cloud`。它保存 dot 在自身云端电脑完成的有限 CPU 组件诊断、复现脚本和轻量证据，便于 ChatGPT 独立审阅。此处的“独占”是任务所有权约定，不代表更改 GitHub 访问权限。

父分支为 `task40extra_0p7nm_engineering`，创建基线为 `c786e87d03976a52f57d1e7f69a3c63f992afe90`。父分支的正式 PDE、审查和历史结果仍由其原流程管理，本分支不回写其他分支。

## 阅读入口

- [本轮任务范围](task.md)
- [执行约束](AGENTS.md)
- [分支身份](branch_provenance.json)
- [阶段结果与未运行项](outcomes/summary.md)
- [父分支 Review V2](../task40extra_0p7nm_engineering/review_report_v2.md)

首批组件结果已归档：[Response V1](response_v1.md)。包含局部参考积分复用、DtN 模式/端口规则、精确几何类型计数及容量风险判断。完整 0.7 nm / 2 TB 目标尚未解决，云端并行研究继续。父分支的 G0/G1/direct 成绩只作为历史基线，不是 dot 云端实测。

第二批真实三维p4算子数据已完成：[Response V2](response_v2.md)、[实际矩阵/资源/负结果](outcomes/real_p4_probe_preparation_v2.md)。新增明确的有界研究范围见 [Phase 2补充](phase2_real_p4_probe.md)。本批没有全局solve或目标能力资格；完整三维原尺寸目标和未来三维缺口能力要求保持。
