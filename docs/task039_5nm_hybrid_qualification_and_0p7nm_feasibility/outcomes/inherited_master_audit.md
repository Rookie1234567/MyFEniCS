# Task39 T0：继承路径审计

本审计以 Task39 执行分支 `48f1a6ec375edc73b7e23babc42d10af3aa3bfda` 为只读基线。
它记录当前 master 已有能力和 Task39 缺口，不是数值资格结论，也没有改写
Task37、Task37b、Task37c 或 Task38 的已接受路径。

## 1. 结论分类

| 分类 | 当前内容 | T0 边界 |
| --- | --- | --- |
| inherited production | [scripts/run_case.py](../../../scripts/run_case.py)、`src/io` 的 `.dat` 读取、解析、resolved mapping、execution plan 和 launcher；Task38 ordinary 2D、staged 3D、Full3D direct 的已连接入口 | 继续复用现有数值核心；普通默认值、旧 CLI 的 retained research 行为和既有 authority 不在本任务中改写 |
| accepted research-only | Task37 的 Full3D iterative/M3a 路径、Task37b 的 Hybrid iterative M10 结果和 Task37c 的 Hybrid iterative robustness 结果；Task38 Hybrid direct 另有有限 integration record，但其 `official_record=false`、`mode_count_converged=false` | 这些路径可作为继承的算法与证据边界；均不等于 ordinary production qualification，也不把历史资源估计当作当前实测 |
| legacy adapter | `benchmarks/run_task032_phase6_augmented.py` 的 augmented/modal-Schur runner、Task37b/Task37c runner 及 Task38 的 Hybrid direct/iterative adapter | adapter 是薄接缝；其固定 profile、argv、provenance 和 checker 约束不能被普通入口静默覆盖 |
| missing Task39 support | public `full3d_iterative` method；5 nm 材料 `delta/beta` provenance；Task39 有限 p6/h10 profile；M3a 历史 config 与当前 resolved dat 的明确接缝；0.7 nm 的材料常数 | 只允许有限 profile/adapter 接线和 provenance 补齐；不得把 public 入口泛化成扫描器、自动 campaign 或新 solver |

## 2. 逐项实现审计

| 审计对象 | 已继承的事实 | Task39 需要保留或补齐的合同 |
| --- | --- | --- |
| public entry | `scripts/run_case.py` 只接受一个 `.dat` 和 validate/dry-run；普通运行把 method、MPI、solver 交给 resolved input | 一个 dat 对应一个 run；不能通过 CLI 偷换物理、profile、MPI 或输出路径来绕过 resolved identity |
| `src/io` | `input_loader` 保持字节 hash；schema/validation 生成 `RunSpecification`、physical hash 和 execution identity；`execution_plan` 生成无 shell 插值的 MPI worker argv | 在不破坏 Task38 字段语义的前提下保存 Task39 材料 provenance，并让 source/input/physical/resolved hash 继续可核验 |
| Task38 Full3D direct | [Full3D adapter](../../../src/runners/task038_full3d_direct.py) 由 `stage_case` 选择既有 Stage1、Stage2、Stage4 solver；Stage4 才传 canonical-vector export；authority 使用 solver 返回的 summary | Task39 可复用 stage dispatch 和 authority 形状；不能把 assemble-only 或 factorization-only 当完整 solve，也不能复制 solver |
| Task38 Hybrid direct | [Hybrid direct adapter](../../../src/runners/task038_hybrid_direct.py) 将 resolved payload 映射到 legacy augmented runner；当前只接受 `continuous_beta + continuous_qep_beta`、`standard_full`、default direct profile，并固定 candidate 为 `2M` | Task39 若复用它，必须显式证明 geometry/material/incidence/profile 与 Task39 contract 一致；不能把旧 13.5 nm/1°/M160 record 伪装成 5 nm authority |
| Task38 Hybrid iterative | [Hybrid iterative adapter](../../../src/runners/task038_hybrid_iterative.py) 调用已有 Task37c runner，不嵌套 MPI/KSP；validator 和 adapter 都检查 finite accepted profile、source SHA、residual、traction、physics、release | Task39 需要独立有限 profile 和材料身份；不能静默接受旧 profile 被 runner 覆盖，不能新增 retry、fallback 或通用 profile registry |
| Task37 Full3D iterative | [Task037 summary](../../task037_static_condensed_full3d_iterative/outcomes/summary.md) 中 M3a 是 MPI1/2/4/8 的 Full3D research baseline：static-condensed、matrix-free exact action、physical-slab/two-level coarse right-FGMRES profile；先消去内部自由度、只解较小边界系统，再恢复场 | 这是可复用数值路径和研究证据，不是 Task39 public `full3d_iterative` 已连接的证明；ordinary defaults 不变 |
| accepted Hybrid direct/iterative | [Task037b response](../../task037b_hybrid_fem_modal_iterative/response_v8.md) 的 M10 与 [Task037c response](../../task037c_hybrid_iterative_robustness/response_v3.md) 的 accepted robustness path 属于 Hybrid block-LDU iterative profile；Task38 Hybrid direct 只保留上表所述有限 integration boundary | 只沿既有接缝复用；Hybrid 的 M120 仅表示中部 QEP/内部模态每个传播方向保留 120 个，不是 external DtN mode count、收敛定理或普通默认值 |
| dynamic DtN enumerator | outgoing 3D DtN order 根据波长、材料、Floquet shift 和传播性动态枚举，并保留零级；Rayleigh/near-cutoff 是状态与 warning 信息。significant channel 只属于后处理 reporting 集合，不参与 PDE mode selection；reporting bounds 与 outgoing DtN policy 已分开 | Task39 不得硬编码固定 40/80/12 等模式数；每个 resolved run 必须记录实际 outgoing order keys、count、cutoff warning 和 provenance |
| watchdog / telemetry | `task034_wsl_resources.py` 读取 process-tree RSS/Swap、dedicated cgroup 和 WSL 诊断；`watchdog_process_control.py` 负责进程组终止；Task38 launcher 记录 samples、peak、warning、termination 和 zero-swap authority | 继续使用 process-tree/cgroup 的现有口径；global WSL swap 只能作诊断，不能充当本作业的 authority；不写新的 watchdog 框架 |

## 3. 不变项与最小实现边界

- Task37、Task37b、Task37c 的 accepted/research 路径、Task38 的三类已连接 adapter、普通默认值和现有 solver 数学均保持原样。
- Task39 的必要工作是把有限、可审计的 5 nm profile 接到已有核心，并补齐材料 provenance、source/hash 和 resource evidence；不是开发新的 Maxwell、DtN、Hybrid 或预条件算法。
- matrix-free DtN 的通俗含义是：边界上的 Dirichlet-to-Neumann 作用通过向量动作计算，而不是每次都存一张完整稠密边界矩阵；它降低存储压力，但仍必须记录真实 mode inventory。
- Woodbury 更新的通俗含义是：在固定的主预条件器上用低秩边界修正快速处理少量模式变化；它不是把不同物理 profile 混成一个默认 solver。
- M3a 是 Task37 历史的 Full3D static-condensed、matrix-free exact-action、physical-slab/two-level coarse right-FGMRES runner/profile；它不是 Hybrid block-LDU。block-LDU 属于 Task37b/c Hybrid iterative 路径，也不表示当前 public schema 已经提供同名 method。

T1 的缺口必须在后续阶段以最小 diff 处理：public methods 尚无 `full3d_iterative`；Task38 hybrid profile/checker 绑定旧的 13.5 nm、1°、M120 等组合；当前材料解析没有 Task39 所需的 `delta/beta` provenance 标签；M3a runner 仍有历史 config 绑定。任何缺口若需要改变 solver 数学或普通默认，必须停止并重新审查，而不是在 T0 文档中宣称已完成。
