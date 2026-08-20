# Task39 边界审计

审计日期：2026-08-20。本审计只读使用以下远端 ref，未 checkout、merge、cherry-pick
或复制代码：

```text
ref       = origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
commit    = f4073adabb91bffe5c3954b8ae8b63270efa3e15
base      = 438caf150439343ee7c4c58ad7e02a3da812a23c
task      = Task039 5 nm Full3D/Hybrid qualification and 0.7 nm capacity audit
review    = Review Report V7；reviewed branch head recorded as 9ce588133375ed3848c7ddee4951a98b1ac7d483
```

## 1. 已完整读取的权威

| 文件 | 只读审计结果 |
|---|---|
| `docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/task.md` | 读取完整；冻结 5 nm 主案例、方法顺序、资源与 0.7 nm 禁止项 |
| `review_report_v7.md` | 读取完整；V7 严格范围、分级内存目标和有限候选已核对 |
| `response_v7.md` | 读取完整；V6 资源停止、not_run 和旧负结果边界已核对 |
| `outcomes/summary.md` | 读取完整；V3–V6/V2 结果表及 measured/derived/not_run 分类已核对 |
| `outcomes/feasibility_0p7nm.md` | 读取完整；材料缺失、空气侧容量和 conditional/derived 外推已核对 |

这些文件是 Task039 的研究权威，不是 Task038-extra 的生产资格证明。

## 2. Task039 的真实定位

Task039 是一条结构化 Hybrid 加速、5 nm 波长鲁棒性和 0.7 nm 容量审计路线。它研究
Full3D reference、Hybrid direct/iterative、内部 QEP/modal 表示和外部 DtN/Woodbury
容量；它不能替代 Task038-extra 所要求的任意非可分离三维材料/几何 Full3D。Task039
允许沿 z 研究结构化接口和端口，但不能把这种结构假设当成 arbitrary non-separable
Full3D 的通用证明。

Task039 冻结了 5 nm、1° grazing、phi=0、S 偏振、p6/h4 主压力案例及有限的 M 候选；
`full_0p7nm_PDE = forbidden`，普通默认、master 写入和整支分支迁移也均禁止。

## 3. V7 复核时继承的 V6/V4 实测边界

以下是 Task039 文档中明确绑定的 `measured`、`controlled_stop` 或 `timeout` 事实，
不是本 Task038 分支的新运行：

| 路径 | 结果 | 正确分类与含义 |
|---|---|---|
| h4 Hybrid direct | own numerical/physics Gate pass；process-tree RSS `93.377006531 GiB` | matched reference；不是 arbitrary Full3D authority |
| h4 exact-side Hybrid iterative | residual、physics、direct comparison pass；RSS `104.334560394 GiB` | numerical/physical pass，但 resource regression/fail |
| V6-1 exact-side setup | `42.70841979980469 GiB`，超过 `42.019652939 GiB` setup line | controlled resource stop；仅 oracle/limit evidence，不是数值失败 |
| V6 port/modal bottom | `22.025470733642578 GiB`，超过 `22 GiB` construction line，swap `0` | controlled resource stop；rank64/128/256/512 probe 未运行，family closed |
| Full3D h4 factor setup | 配置的 `21600 s` timeout；process peak `213314.96484375 MiB`；solve 未开始 | `not_completed` timeout；不得写成 Full3D 算法数值失败 |

V7 review 没有把上述历史结果改写为通过，而是授权有限、预冻结的后续研究边界：一次
exact-side setup-only、一次 streamed owner-row Petrov producer/consumer、一次轻量 side
layer-graph audit；Full3D new heavy、full-ephemeral Petrov 原样重跑和 0.7 nm PDE 仍禁止。
V7 的 `93.377006531 GiB` 是 direct matched baseline；`<` baseline 才是最低内存正向，
`<=88.708156204 GiB` 才是 5% robust minimum，`<=46.688503266 GiB` 才能称 half-memory
strategic pass。上述分级目标不改变数值 Gate。

## 4. measured、derived、not_run 与 negative 的边界

### 4.1 5 nm

Task039 summary 记录过 Full3D direct、Hybrid direct 和 exact-side 研究结果，但方法身份
必须分开：h4 Hybrid direct 的 own pass 不是 Full3D direct pass；exact-side 的数值/物理
通过不能抵消 `104.334560394 GiB` 的资源失败；Full3D h4 timeout 不能被解释为迭代算法
数值失败。V6 的两个 resource stop 也没有产生后续 rank、top、outer、recovery 或 R/T/A
结果，这些项保持 `not_run`。

### 4.2 0.7 nm

Task039 明确没有 0.7 nm 的 `delta/beta` 材料输入，因此最终包含
`0P7NM_MATERIAL_INPUT_INCOMPLETE`，禁止 absorption/RTA 和完整 0.7 nm PDE。空气侧
`16030` channel、`8015` spatial orders、p6/h1 FE/factor、W/K/LU 及 modal/Schur 数字
均按原文标为 `derived`、`conditional` 或 `not_established`，不是 process-tree measured
PDE 结果。文档列出的并列瓶颈包括：

```text
0P7NM_MATERIAL_INPUT_INCOMPLETE
0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET
0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN
0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN
0P7NM_CONVERGENCE_RISK_UNRESOLVED
```

`CURRENT_ARCHITECTURE_PLAUSIBLE` 不适用；这些是 Task039 的组件审计分类，不是
Task038-extra 的 0.7 nm 资格结论。

## 5. 不可整体迁移到 arbitrary Full3D 的部分

Task039 的 exact-side/Hybrid 方程、局部端口 factors、QEP/modal/packet 表示、M480 或
固定 internal mode profile，以及它们的 runner/compact，均不能整体迁移为 arbitrary
non-separable Full3D 的 solver 或 PC。Task039 的正结果、negative result 和 resource
stop 只能作为研究边界，不能提升 Task038-extra 的 ordinary default 或生产资格。

可参考的仅是与物理候选无关、且仍需逐文件 fresh qualification 的通用模式：

- 输入身份、source/physical hash 和 one-dat/one-run provenance；
- simultaneous process-tree watchdog、swap/hard-stop 和阶段 telemetry；
- owned/borrowed 对象生命周期、释放顺序和不把阶段峰值相加的资源口径；
- matrix-free coupling 的接口与 artifact identity 记录方式。

这些模式不能携带 Task039 的材料、网格、模态数量、factor、QEP、收敛值或内存数字。

## 6. T0 结论

Task39 远端权威已经通过指定 ref 完整只读核验，故不再标为 `unverified`。但本轮仍是
Task038-extra T0 docs-only：没有迁移 Task39 代码，没有启动测试、benchmark、MPI、PDE
或 R/T/A，也没有把 Task39 的 Hybrid/5 nm/0.7 nm 结果提升为当前 Task038 生产资格。
