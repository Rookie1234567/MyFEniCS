# Task037b response v0：H1 controlled closeout

## 主审结论回应

同意按任务合同在 H1 停止。H1 的唯一 formal 没有进入 direct Hybrid 解的生成，更没有产生可以判断 residual、interface、middle-plane 或 R/T/A 的数值。因此将它分类为 inherited correctness regression，而不是 Hybrid 物理负结果或 H1 数值 Gate 失败。

| 项目 | 结论 |
|---|---|
| H0 | pass |
| H1 | failed_before_solve / controlled_stop |
| H2-H10 | not_run_by_H1_gate |
| current source | 3f72ef3eb4f3002246802af30ef7bca6b0080888 |
| ordinary defaults | unchanged |
| formal count | 1；未重跑 |

## docs-only 结项前身份快照

| 项目 | 值 |
|---|---|
| branch | codex/20260807-task37b-hybrid-iterative-development |
| tested source SHA | 3f72ef3eb4f3002246802af30ef7bca6b0080888 |
| pre-doc upstream | origin/codex/20260807-task37b-hybrid-iterative-development at 3f72ef3eb4f3002246802af30ef7bca6b0080888 |
| pre-doc ahead/behind | 0/0 |
| pre-doc worktree | clean |
| docs-only commit | 本文件编写时为 pending；主审通过后单独提交 |
| final push state | 本文件不自引用最终提交 SHA；以交付汇报为准 |

表中 clean 是写 docs 前快照；最终 HEAD/upstream/clean 由交付汇报确认。

## 发生了什么

mode classification 可以理解为“先把横截面模态整理成可用于界面方程的组”。它位于横截面 QEP 之后、Hybrid block solve 之前。当前源码在整理第 50 和第 52 个模态时，发现两个模态仍有近简并耦合，却被分到了不同组，于是抛出 NearDegenerateBlockPartitionSplitError 并让 MPI job 收口。

实际字段为：

| 字段 | 值 |
|---|---:|
| indices | [50, 52] |
| group_ids | [17, 18] |
| relative beta distance | 1.580086e-06 |
| identity row norm | 1.024637e-06 |
| cross-block max | 6.572908e-07 |
| limit | 1.000000e-06 |

由于解尚未建立，H1 telemetry、combined/bottom/top/modal residual、interface E/H、middle-plane E/H、12/12 powers、12/12 amplitudes、R/T/A、A_volume、rows/NNZ/factor inventory 全部是 not_observed 或 not_run，绝不填 0。

## formal 与资源证据

formal 使用 clean source SHA 3f72ef3eb4f3002246802af30ef7bca6b0080888，p6/h10、MPI8、augmented、M120/candidate240、static condensation 及 H1 explicit gate 参数均冻结。历史 Full3D record 是 pinned authority，record SHA256 为 b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3。

wall 约 49.54 s；RSS/process-tree peak 为 2647.4375 MiB，authority 为 2.58538818359375 GiB，PSS 为 1761.02734375 MiB，USS 为 1637.375 MiB，swap 为 0。该峰值只说明 classification 阶段的 whole-job 资源，不代表成功 Hybrid solve 的内存。raw JSON 字段名虽含 max_*_mb，但本文按 bytes/1024^2 换算并显示为 MiB。

完整字段、命令、证据 hash 和资源口径见：

- [direct Hybrid authority](outcomes/direct_hybrid_authority.md)
- [resource ledger](outcomes/resource_ledger.md)
- [test summary](outcomes/test_summary.md)
- [changed files](outcomes/changed_files.md)
- [summary](outcomes/summary.md)

原始 evidence 保留在 Git ignored artifact 目录，tracked docs 仅 hash-bind 它们，不把 raw 输出加入提交。

## 测试边界

| Gate | 结果 |
|---|---|
| H0 12-file focused | 76 passed / 1 skipped / 225.86 s |
| H0 test24 + test26 | 21 passed |
| H1-A targeted | 40 passed |
| H1-A Ruff/format/compileall/diff-check | pass |
| H1 preflight | pass |
| H1 formal | failed_before_solve |
| full pytest | not_run；按 H1 停止规则未启动 |

以上是本地结果，不是 CI 声明。

## 后续授权建议

若要恢复 Task037b，建议下一份 review 只授权：

1. 对历史 Case096 SHA 244b62e 与当前 mode-classification 实现做窄差分审计；
2. 依据审计决定是否允许一个最小、证据驱动的实现修复；
3. 修复通过最小 Gate 后，最多启动一个新的 H1 run。

不得直接放宽 1e-6，不得扫描 M、角度或 p-h，不得跳到 H2。H1 失败证据保留，不改写为通过。
