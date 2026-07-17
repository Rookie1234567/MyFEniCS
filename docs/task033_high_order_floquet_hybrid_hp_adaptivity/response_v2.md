# 对 `review_report_v1.md` 的回复

## 总体处理

审阅意见合理，已按“Phase A 先闭合、最小运行矩阵、禁止重复大 campaign”的路线执行。
Phase A 已完成，p3/p4 QEP 组件通过；legacy 全阶 aggregate 仍因 p1/p2 真实负结果保持
`not_qualified`，没有为了得到好看的总状态而放宽阈值。

## 已接受并完成

1. 使用已有 36 个 MPI1 QEP shards 离线复现 p1/p2/p4 异常；
2. 新增 near-degenerate block/subspace tracking，使用左右公共 Fourier fingerprint 的 principal
   angles，保留原 `overlap >= 0.5` 与 `beta drift <= 0.25`；
3. 证明 p4 h5→h3 的 `0.48444` 是四维近简并块内基旋转：块 overlap
   `0.999999999999851`、块中心 drift `8.11e-7`；
4. 保留 p2 h5→h3 `0.2608686` 真实 drift 失败和 p1 非单调/分支不闭合失败；
5. 在 clean source `bb830ba5dd74ced30475402bd6bc6d3c1856c630` 上完成 p3/p4 h3 的
   MPI2、MPI4 正向运行，四项均正式通过，并与 MPI1 数值一致；
6. 在 DOLFINx 环境运行普通 p2 Task032 QEP/模式分类回归，13 tests passed；
7. 形成 `outcomes/qep_tracking_diagnostic.md` 并同步阶段摘要、QEP 研究、负结果、测试与索引文档。

## 对两处执行方式的调整

### 没有重跑 p1/p2/p4 的 MPI1 PDE 最小矩阵

本轮修改的是 aggregate tracking，不是 shard-side QEP measurement。原 shards 已保存完整的
beta、左右 fingerprint、near-degenerate groups、残差和双正交输入；用新算法重放这些 exact
measured inputs 就是对审阅指定 p1/p2/p4 组合的最小复测。

如果重新求解相同 PDE，只会重新生成相同的 compact evidence，并不能提高对基旋转或谱漂移的
判别力。因此没有重复 7 个 MPI1 PDE，也没有重跑完整 36 项；新增 PDE 只用于原证据缺失的
p3/p4 MPI2/4 正向身份测试。

### 没有重跑 Case090

高阶 3D/QEP 数值装配和求解代码相对 Case090 source 未变化。直接要求同 SHA 会与审阅报告的
“数值行为未变化时不要重跑 Case090”冲突。已实现严格白名单的 descendant audit：只有文档、
测试、aggregate qualification 和 watchdog gate 变化可复用；任何 numerical source 变化都会
fail closed。本轮审计通过，因此没有重复 144 个 Case090 PDE。

## 当前结论

| 对象 | 状态 |
|---|---|
| p3 QEP component | qualified |
| p4 QEP component | qualified；四维近简并块基旋转已解析 |
| p1 QEP | diagnostic negative |
| p2 Task033 patterned h5→h3 | trend negative；普通 Task032 p2 regression pass |
| p3/p4 h3 MPI1/2/4 identity | pass |
| legacy p1–p4 all-degree aggregate | not qualified，按真实低阶负结果保留 |
| p3/p4 target Hybrid | 仍未资格化；需要 Phase B/C |

## 下一步

按审阅报告的阶段门禁，本提交应作为 Phase A review checkpoint。下一步是 Phase B：先做 p3
matched-trace 小型 fixture 的 MPI1/MPI4 组件记录；p4 由于 Phase A 已通过，可以做相同最小记录。
随后才进入 Phase C 的 p3/h5 direct full3D reference 与 Hybrid M80/M120/M160 漏斗。

自适应、完整 uniform p/h 矩阵和 p1 Hybrid 扩展继续暂停。
