# Task41extra：新入射与新几何的0.7 nm计算主线

**唯一执行分支：`task41extra_phi90_p50x50_g17x20`。Codex项目名、现有主控/执行对话和工作目录不变。**

从Task40extra暂停收尾提交 `939ffe1f7b8d5a7406a01e25a716c08d36090078` 分叉。旧Task40保持暂停；旧矩阵与结果不删除，但不作为新物理的资格。

## 当前任务

当前最新执行范围是 Review V5；结论见 [response_v5.md](response_v5.md) 和 [V5 outcomes](outcomes/summary.md)。V5 的 mesh_actual_exact 候选完成了 28,000 个 exact key 的清点、8 个真实 cache-miss 前缀测量，以及 cells 26762/26897 的实际坐标与 K/G/J/L 逐位重放核验。完整候选因固定窗口余额不足而 CANDIDATE_NOT_ADMITTED；全域两列、checker、200q、factor、KSP/FGMRES、完整场、A6 和 R/T/A 均未运行。V3 完整 action 数值失败与 V4 saved-evidence/recovery/action 分类仍按原样保留；V5 不是新的数值失败，也没有 official result。原始资源/数值合同未调整，新窗口没有自动续期。

V3 详细结果作为历史阶段保留在 [response_v3.md](response_v3.md) 与 [V3 compact](outcomes/b0_v3_full_action_failure_20261019.json)：恢复门通过，但两个完整作用误差仍超过 `1e-11`，不得改写为资源停止或 official result。

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
