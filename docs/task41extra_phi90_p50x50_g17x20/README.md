# Task41extra：新入射与新几何的0.7 nm计算主线

**唯一执行分支：`task41extra_phi90_p50x50_g17x20`。Codex项目名、现有主控/执行对话和工作目录不变。**

从Task40extra暂停收尾提交 `939ffe1f7b8d5a7406a01e25a716c08d36090078` 分叉。旧Task40保持暂停；旧矩阵与结果不删除，但不作为新物理的资格。

## 当前任务

当前唯一执行范围是 Review V4 的保存数据审核与 volume-only 误差归因；见 [response_v4.md](response_v4.md) 和 [V4 outcomes](outcomes/summary.md)。V3 的两列 recovery PASS 与完整 p6/native action FAIL 原样保留。V4 的 required saved-evidence checker 已完成且数据完整性、恢复门通过，但 joint action 仍 FAIL、`official_result=false`。两格实际/标准几何对照解释了一个选中行上的差异方向，却不足以证明全域修复或原 `1e-11` 门通过。200q、factor、KSP/FGMRES、完整场、A6 和 R/T/A 仍未运行。本轮沿用已批准的16 GiB原始证据配额、固定窗口、资源门和数学阈值，没有调整这些合同值。

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
