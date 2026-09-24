# Task041 Review V7 进度快照

> **进度快照；V7 未完成。G2 修正步骤没有运行，完整正式 5 nm consumer 未启动。**

这里的 Q 是粗层校正；p4 恢复是把粗层结果解回原有限元自由度；A4 是用原方程检查残差。

冻结仓库 HEAD：分支 `codex/20260902-task41-mpi1-shortwave-hybrid-capacity`，HEAD `6d27033e89646692e7f41e779ed65032a26b9967`，冻结时 upstream 同 SHA、ahead/behind `0/0`、clean。该 SHA 尚未用于真实 FE；各已运行 source SHA 见 record。

| 阶段 | 结果 | 边界 |
|---|---|---|
| G1 顶部因果诊断 | 14 项独立 Q 输入与 PH 输出逐字节一致，首次差异位于 p4 恢复；Q 差 `4.462076935295908e-11`–`5.217215402500894e-11`，原限值 `1e-11`，全失败。独立 PC 7/7 通过 `1e-8`。 | 原 A4 复核通过不替代 Q 门；根因未证明。 |
| G2 两场 | 首次 setup 缺布局采集字段退出；`ed16b8e3d55aa15b99a9c2d596bef2431c2f42d7` 修 capture 开关后重试，stable-layout admission 报差异。`6d27033e89646692e7f41e779ed65032a26b9967` 只补 gate 前持久化，尚无真实运行验证。 | 两场 correction stage 0/1/2 均 `not_run`；G2 新布局 hash `not_persisted`。 |

三次 G1/G2 服务均已退出：用户服务状态 failed、Result `exit-code`、ExecMainStatus `3`、MainPID `0`。起止时间取自主控宿主 `systemctl --user show` 的 CST 读数并换算为 UTC；精确 wall 仍引用原 finalizer。G2 tree/authority 峰按对应 summary 为 `38718169088 B` / `39235481600 B`，cap `53221163008 B`、swap `0 B`。G1/G2 细节见[中心 outcome](outcomes/causal_fix_5nm_v7.md)和[机器记录](outcomes/records/task041_v7_causal_fix_5nm.json)。

唯一阻塞是跨运行冻结输入布局身份：G1 九项 component hash 已保存；G2 运行时已计算比较字段，但未持久化新 hash，独立 `layout_identity_full` / `layout_identity_cell_condensed` 文件 `not_generated`，不能以长度替代身份。完整 5 nm consumer、Schur、outer/RTA/EH 与修正均未运行。

下一步：用已提交的落盘代码执行同一最小 top/PC1 诊断并取得真实新旧九组件比较；身份门不过则停在载入前逐项归因，不关门、不按长度加载。身份通过后，才对 Q1/Q2 分别执行最多两次同因子修正。
