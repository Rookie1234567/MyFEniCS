# Task041 Review V7 进度快照

> **进度快照；V7 未完成。G2 layoutfix-r2 已完成 Q1/Q2 的 0/1/2 修正诊断；r2及新修正策略下的 PC action/side.apply 与完整正式 5 nm consumer 未运行。G1 原独立 PC 7/7 通过仍成立。**

这里的 Q 是粗层校正；p4 恢复是把粗层结果解回原有限元自由度；A4 是用原方程检查残差。

本次文档更新前仓库 HEAD：分支 `codex/20260902-task41-mpi1-shortwave-hybrid-capacity`，HEAD `3bcf00527b3b2440a66792e079c6667cb30aec2d`，upstream 同 SHA、ahead/behind `0/0`、clean。V7 初始快照 HEAD `6d27033e89646692e7f41e779ed65032a26b9967` 保留作历史；该 SHA 与 validator-only 提交均未用于 r2 数值运行，各运行 source SHA 见 record。

| 阶段 | 结果 | 边界 |
|---|---|---|
| G1 顶部因果诊断 | 14 项独立 Q 输入与 PH 输出逐字节一致，首次差异位于 p4 恢复；Q 差 `4.462076935295908e-11`–`5.217215402500894e-11`，原限值 `1e-11`，全失败。独立 PC 7/7 通过 `1e-8`。 | 原 A4 复核通过不替代 Q 门；根因未证明。 |
| G2 三场 | 首次 setup 缺布局采集字段；layoutfix-r1 stable-layout admission 报差异；layoutfix-r2 与 G1 冻结布局匹配，并对 PC1 的 Q1/Q2 实际运行 0/1/2 修正。 | Q1/Q2 的 step0 超 `1e-11`，step1/2 通过；原用户服务仍因 public lifecycle schema 错读以 ExecMainStatus 3 结束。修正 validator 的只读重校验五项全真、诊断 complete，`qualification_pass=false` 仍表示非正式资格。 |

四次 G1/G2 服务均已退出：用户服务状态 failed、Result `exit-code`、ExecMainStatus `3`、MainPID `0`。起止时间取自主控宿主 `systemctl --user show` 的 CST 读数并换算为 UTC；精确 wall 仍引用原 finalizer。G2 tree/authority 峰依次为 `38718169088 B`、`39235481600 B`、`43820285952 B`；r2 cgroup peak `41557790720 B`，cap `53221163008 B`、swap `0 B`。r2 的 worker correction action gates 通过，但 public 的 backend lifecycle 字段路径最初不匹配；修正后只读 `_consumer_result` 重校验通过。该次与 Task39extra 并行，性能不资格化。细节见[中心 outcome](outcomes/causal_fix_5nm_v7.md)和[机器记录](outcomes/records/task041_v7_causal_fix_5nm.json)。

layoutfix-r2 的稳定布局身份门已通过；旧 r1 未持久化的组件差异仍保留为历史证据，不能用合成测试的 dofmap 变化解释。G1 的冻结输入 producer source 为 `e2965ee25e56220d1623afe4dd221612542c2764`；QEP producer source 是独立的 `b01a5932e4dfaf895e81e0424e0dd88c276fb0d3`。完整 5 nm consumer，以及 r2 和新修正策略下的 PC action/side.apply、Schur、outer/RTA/EH 未运行；G1 原独立 PC 7/7 通过。并行场景不作性能资格。

本次 Q/A4 分步实值、服务退出边界、只读合同重校验和测试账单见[中心 outcome](outcomes/causal_fix_5nm_v7.md)及[机器记录](outcomes/records/task041_v7_causal_fix_5nm.json)。
