# Task41extra：新入射与新几何的0.7 nm计算主线

**唯一执行分支：`task41extra_phi90_p50x50_g17x20`。Codex项目名、现有主控/执行对话和工作目录不变。**

从Task40extra暂停收尾提交 `939ffe1f7b8d5a7406a01e25a716c08d36090078` 分叉。旧Task40保持暂停；旧矩阵与结果不删除，但不作为新物理的资格。

## 当前任务

当前为Review V19 两单元 native rank-1 来源审计收口：在原始行 5,218,672 对应的 cells 7,873、8,014 上，对两列输入捕获并保存 curl/material-mass 共 8 项积分贡献；只读 checker 将它们与目标及 900 个 internal rows 的 saved volume RHS 逐位绑定，三段有符号误差账在 Decimal 80/100 位闭合。此结果只限选中行；所选行不触及 MPC slave/master，MPI1 ghost rows=0。继承的 V15 全域 action 仍为 FAIL（约 5.7625744836e-11 / 1.2123684644e-10，对限值 1e-11），V19 没有重算或解锁 full owner、official result、200q、recovery、FGMRES、完整场、A6 或 R/T/A。定向测试为 28 passed / 4.18 s。见 [response_v19](response_v19.md)、[summary](outcomes/summary.md)、[compact](outcomes/v19_closeout/v19_selected_native_rank1_compact.json)、[attempt index](outcomes/v19_closeout/attempt_index.json) 与 [evidence index](outcomes/v19_closeout/evidence_index.json)。V18 及更早内容保留为历史记录。

V6 的 `actual_qmetric_blocked_gram` 候选已构建 28,000 个 `mesh_actual_exact` 键；八个代表键的 raw/oriented 张量、K/G/J/L 与 R/T/S 局部筛查均通过 `1e-11`。候选完整两列作用的冻结分母相对误差为 `1.7183209126709868e-10` 和 `3.6180522433957604e-10`，超过原 `1e-11` 门；独立 saved-only checker 已完成并确认数据完整，但数值资格失败，`official_result=false`。按 Review V6 停在 full-action gate，不进入 200q、factor、KSP/FGMRES、完整场、A6 或 R/T/A。候选恢复也未通过 forward 门，且只做了初次恢复，没有耗尽三次修正额度。V3/V4/V5 均保留为各自历史阶段，不用 donor PASS 替代 V6 候选结果。

V18使用用户单独批准的6小时saved-Jz窗口（总21,600秒、数值20,400秒、收口1,200秒），T0为`2026-10-29T00:50:15Z`；原合同资源/ABI/task swap0与数值阈值保持不变。候选不提升ordinary default；文档已由主控核对并集中收口，不合并master。

完整规则见 **[task.md](task.md)**；分叉依据见 [branch_provenance.json](branch_provenance.json)。任务书第10节可直接交接Codex。A1 已完成新几何 13.5 nm 完整直接场并通过独立 checker；A出口已通过：A2保存场同离散比较与 checker-only retry3 PASS。attempt7 原 worker 的 `WORKER_FAILED` / `official_result=false` 作为历史保留；checker未重新组装FE算子。

以下为早期B0阶段记录：当时真实FE/MPC与端口构建曾因全域分量装配速度受控停止，并保留94/64,120模式。后续V3完整carrier已完成并作为V4 donor复用；V4当前阻断点是完整volume action差异尚未闭合，而不是边界积分仍待接线。早期停止、旧窗口和历史费用原样保留，当前阶段见[outcomes/summary.md](outcomes/summary.md)。

| 固定物理 | 值 |
|---|---|
| 单胞 | 50×50 nm，x/y双Floquet |
| Si主体 | 居中17×20×120 nm；x=16.5…33.5，y=15…35，z=0…120 nm |
| z域 / 基底 | -10…130 nm / 底部10 nm显式Si与下方同材料半空间 |
| 入射 | 上入射、掠角1°、方位90°、S偏振、幅值1 |
| 主案例几何解释 | 完整居中矩形；不自动叠加母任务的诊断notch/void，见task §2.1 |
| 路线 | 原尺寸13.5 nm直接/迭代对照，通过后直接0.7 nm |
| 最终目标 | 完整3D复场与物理输出；整机十进制2 TB含余量、任务swap0、必要单场冷流程≤48 h |

程序继承Task40 p6 reference-q路线；新ky、完整二维模式、q映射和当前几何均重新资格。不得使用旧572-N0、旧q0/q4 PASS或旧RCWA值替代新结果。先完成计算，不先全仓重构或反复全仓测试。

后续Codex在本目录写 `response_v1.md` 与 `outcomes/`；ChatGPT只在本分支写后续review。未最终审阅和用户授权前，不合并master。
