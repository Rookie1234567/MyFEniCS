# Task039 Review V3：V3-0 继承审计与 1° 模型隔离

## 1. 当前执行身份

| 项目 | 实际值 | 结论 |
| --- | --- | --- |
| 分支 | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` | exact |
| 同名 upstream | `origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` | exact |
| 同步前 HEAD | `1060a623255959cbe8f4255d4dbcd812ee5971a7` | clean |
| 同步后 HEAD / upstream | `641e011e9c802535a8b169d34955da135a065c75` | `0/0`、clean |
| 同步方式 | `git fetch origin --prune` 后 `git merge --ff-only @{upstream}` | 无分叉、无 merge/rebase |
| 当前 review | `review_report_v3.md`，`AUTHORIZED_WITH_STRICT_SCOPE` | V3-0 可执行 |
| master | 未触及 | unchanged |

远端在同步前仅比本地前进一个 review 提交；工作树当时 clean，因此按合同快进到
`641e011e`。没有创建分支或 worktree，也没有运行测试、MPI 或 PDE。

## 2. 10° 历史 evidence（保留但不继承为 1° reference）

这些记录来自 V2 的 10°、5 nm、S、phi=0° 案例。它们用于历史对照和资源锚点，不能
混入 V3 的 1° 物理身份。

| 证据 | record / raw identity | record SHA256 | V3 处理 |
| --- | --- | --- | --- |
| Full3D direct h5/MPI8 own authority | [`task039_v2_h5_full3d_direct_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_full3d_direct_v1.json)；physical `e35907c72ab97069d9ab66958fd00787f98dea08dce1aa6f64c053b7bda46cdb` | `ed2c05ef383607667d66f29f40456c406838e414fcd60254a7ce7fa37e2cd083` | `historical_10deg_only` |
| Hybrid direct h5/M480 same-grid | [`task039_v2_h5_hybrid_full3d_same_grid_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_full3d_same_grid_v1.json)；classification `H5_M480_HYBRID_MODEL_FAIL` | `73ec0f6332866bd4bbdec50188fe18db87780761e1f9dd60c920203c6998a654` | 保留 V2-6 negative，不作 1° authority |
| Hybrid iterative h5/M480 negative | [`task039_v2_h5_hybrid_iterative_m480_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_iterative_m480_v1.json)；classification `H5_M480_HYBRID_ITERATIVE_SOLVER_FAIL` | `8475462561b3079e16401c9b95a0aca8396206c11788c577b40276a074b2636a` | 保留 V2-7 negative |

V2-7 的运行 source SHA 是 `be5be4680065268303070bfb10c29f4511d483eb`；当前已推送的
telemetry 修复 `29ead2cda47a88bd312913a6101826eaba977f9b` 不会被倒填为旧运行的能力。
h10 继续是 `historical_underresolved_stress_anchor_only`，禁止进入 Full3D 5 nm
reference、Hybrid physical authority、accuracy-qualified 或 0.7 nm mesh-scaling。

## 3. V3 新物理 identity

Review V3 冻结的新物理只改变入射条件：5 nm、S 偏振、phi=0°，grazing angle=1°，
内部 `theta=89°`。几何、材料、接口 10/110 nm、p6、M480 及 external mode 由正式
枚举器生成；不得复用 10° 的 604-key inventory。

| 字段 | V3-1 冻结计划 | V3-0 状态 |
| --- | --- | --- |
| `model_id` | `task039_v3_1deg_s5` | planned；待 input materialize |
| `comparison_group` | `task039_v3_1deg_p6_s_m480` | planned；2D/3D/Hybrid 共用 |
| `grazing_angle_deg` / `azimuth_deg` | `1.0` / `0.0` | frozen |
| `polarization` / `wavelength_nm` | `S` / `5.0` | frozen |
| `requested_modes_per_direction` / MPI | `480` / `8`（2D reference 为 MPI1） | frozen by V3 |
| `physical_model_sha256` | `pending_v3_input_resolution` | **not established in V3-0** |
| external inventory | 由新 1° resolved input 重新枚举 | 不得手填 604 |

physical SHA 必须来自 V3-1 新 `.dat` 经 `load_and_resolve` 后的 resolved physical
identity；本 docs-only 阶段没有该 input 或 resolved artifact，所以明确记为
`pending_v3_input_resolution`，不把旧 10° SHA 冒充新模型。V3-1 在任何正式运行前必须
把实际 source/input/resolved/physical SHA 写入 identity record，并证明角度、波矢、
时间因子、端口法向和功率归一化一致到 Review 要求。

## 4. V3 漏斗与停止边界

| 阶段 | 任务 | 解锁条件 / 停止条件 |
| --- | --- | --- |
| V3-0 | 继承审计与 identity 隔离 | 本记录完成后进入 V3-1 |
| V3-1 | 2D TE/3D 角度与平面波 identity | identity 未通过不得比较数值 |
| V3-2 | 2D p6 h5→h4→h3→h2 reference | 相邻 Gate 通过即可停止更细 |
| V3-3/4 | 相近网格 3D direct 与 2D 选择 | h5 mandatory；h4.5/h4 仅按资源条件 conditional |
| V3-5 | selected mesh 上 Hybrid direct integrated physics | channel repair 仍 deferred |
| V3-6 | 解析旧 10° telemetry并接入 1° telemetry | 缺三类正式 telemetry 不得宣称归因完成 |
| V3-7 | matrix-free identity、side contraction、exact-side-LU oracle | operator/oracle 未通过不得选生产 PC |
| V3-8/9 | 有界 PC 候选与生命周期优化 | 只选一个全局候选；禁止盲目增加迭代 |
| V3-10 | 唯一 Hybrid iterative MPI8 formal candidate | residual、physics 与 RSS 节省同时满足才为 positive |

冻结禁项：M>480、MPI1 formal Hybrid、P 偏振、phi 非零、0.7 nm PDE、neural/learned
factor、Full3D M3a retuning、并发 heavy job，以及将逐通道相位/振幅修复提前为本轮
production Gate。所有旧 negative 保持原样；ordinary defaults 与 master 不变。

## 5. V3-0 结论

V3-0 `pass_with_v3_1_identity_pending`：继承身份、旧 evidence SHA、分支和停止边界
已核对，且 10° 与 1° 结果目录/record 计划严格分离；新 1° physical SHA 尚未建立，
因此本阶段不宣称 1° reference 或任何 numerical qualification。下一步只进入 V3-1 的
2D TE input/identity 实现和轻量 tests；未通过角度/端口/归一化审计前不启动正式 2D/3D
PDE。
