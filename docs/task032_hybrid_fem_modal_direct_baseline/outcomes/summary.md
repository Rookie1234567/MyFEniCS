# Task032 结果总结：Hybrid FEM–Modal direct baseline

> 数据身份统一使用 `measured`（正式记录直接测得）、`derived`（由已记录规模或公式计算）、
> `predicted`（工程外推）和 `not_run`（被 Gate 阻止）。表中的 `records/<name>` 统一表示仓库相对路径
> `benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/<name>`；`outcomes/<name>` 表示本任务
> outcomes。未单列单位/baseline 的状态型表，其单位为 N/A，baseline 为对应任务书或 Review 合同。

## 1. 最终状态与适用范围

| 项目 | 最终值 | 数据身份 | 范围 / baseline | 证据 |
|---|---|---|---|---|
| classification | `hybrid_direct_engineering_success` | derived decision | 13.5 nm、规则 Case080、h5/h3、主点 M160 | `review_report_v1.md`、`review_report_v1_addendum.md` |
| review status | `changes_required_before_selective_merge`，本 response 正在关闭 | measured | Review V1 + addendum | `review_report_v1*.md` |
| Hybrid/full3D 同网格一致性 | pass | measured | h5 对 h5、h3 对 h3；不是 h5→h3 连续网格收敛 | `records/hybrid_h*_m160.json` |
| h2 | `not_run_by_gate` | not_run | 中心 `<=4 GiB` 且上界 `<=5 GiB` 才允许运行 | `records/h2_prediction.json` |
| 1–10°、S/P | `parameter_interface_smoke`，30/30 | measured | h5 20 点 + h3 10 点，M4；不是 production qualification | `records/parameter_smoke.json` |
| current direct at 0.7 nm | `not_resource_feasible` | predicted | 当前显式模态布局 + local LU | `outcomes/task032_0p7nm_scalability_assessment.md` |
| future target architecture | promising / retained | derived decision | complex 3D FEM ends + generic `epsilon(x,y)` modal middle | Review addendum |
| ordinary default | unchanged | measured | 全部 Task032 入口显式 opt-in | Case080、代码入口 |
| final checker | 302/302 passed | measured | clean Case080 lightweight records | Case080 checker `--no-write` |

这里的“工程成功”只证明 Hybrid 域分解在当前 13.5 nm 同网格问题中正确并降低代数规模；
不证明连续物理解已网格收敛，也不证明当前直接法可扩展到 0.7 nm。

## 2. 冻结问题与记号

| 参数 | 值 | 单位 | 数据身份 | 证据 |
|---|---:|---|---|---|
| wavelength | 13.5 | nm | measured input | Case080 `config.json` |
| period x / y | 50 / 25 | nm | measured input | Case080 `config.json` |
| full domain / modal middle height | 140 / 100 | nm | measured input | `task.md` |
| current total local 3D height | 40 | nm | derived: bottom 20 + top 20 | local-mesh code / records |
| primary incidence | 10 grazing, phi=0, S | deg / identity | measured input | Case080 record |
| element / MPI | p2 Nédélec / 4 | identity / ranks | measured input | formal records |
| M | modes retained per propagation direction | count / direction | contract | Review addendum |
| M160 internal amplitudes | 320 | complex unknowns | derived: forward M + backward M | `records/hybrid_h*_m160.json` |
| external Fourier-DtN unknowns | 80 | unknowns | measured | 40 bottom + 40 top；不是 M | full3D records |

`M` 会随波长、角度、材料、接口位置和截断误差改变。M160 只资格化当前主点，不能直接移植到
0.7 nm。

## 3. Phase 0–10 实施矩阵

阶段编号以不可改写的 [`task.md`](../task.md) 为准；Review V1 第 2.1 节对 Phase 7/8 的
描述与任务书编号不同，因此本表保留任务书的正式编号。

| Phase | 任务书定义 | planned | run | 最终状态 | 数据身份；单位/baseline | 关键证据 |
|---:|---|---|---|---|---|---|
| 0 | 新目录、Git、环境、旧能力迁移 | yes | yes | pass | measured status；N/A / task.md | `local_migration_record.md`、`old_vs_new_smoke.md` |
| 1 | 冻结 full-3D h5/h3 reference | yes | yes | pass | measured status；N/A / task.md | `records/full3d_h5_reference.json`、`full3d_h3_reference.json` |
| 2 | 二维截面 QEP MVP | yes | yes | pass_with_discretization_scope | measured status；N/A / task.md | `records/qep_phase2.json` |
| 3 | 分类、双正交、tracking | yes | yes | pass | measured status；N/A / task.md | `records/modes_phase3.json` |
| 4 | 稳定双向传播 | yes | yes | pass | measured status；N/A / task.md | `records/propagation_phase4.json` |
| 5 | 匹配接口 trace coupling | yes | yes | pass | measured status；N/A / task.md | `records/trace_phase5.json` |
| 6 | Hybrid augmented direct + physical reconstruction | yes | yes | pass | measured status；N/A / task.md | `records/hybrid_h*_m160.json` |
| 7 | Modal-Schur direct | yes | yes | pass_numeric；fast-memory 非单调 | measured status；N/A / augmented | six memory records |
| 8 | M20→40→80→120→160 截断漏斗 | yes | yes | pass_current_single_point | measured status；modes / previous M | `records/hybrid_h*_funnel.json` |
| 9 | full3D 对照 + 参数 smoke | yes | yes | physical pass；parameter smoke only | measured status；N/A / same-grid full3D | M160 + `parameter_smoke.json` |
| 10 | 内存、时间与 h2 决策 | yes | yes / h2 not_run | pass_decision | measured+predicted+not_run；GiB/s / Gate | memory records + `h2_prediction.json` |

## 4. QEP 与 mode validation

| case / h | beta 或误差 | QEP residual / basis Gate | 数据身份 | baseline / 证据 |
|---|---:|---:|---|---|
| air h5 | beta relative error 29.5323% | selected-mode polynomial residual `<=1.8177e-15` | measured | analytic air beta / `qep_phase2.json` |
| air h3 | 5.58859% | same record Gate | measured | analytic air beta / `qep_phase2.json` |
| air h2 | 1.12629% | same record Gate | measured | analytic air beta / `qep_phase2.json` |
| air h1.5 | 0.454640% | same record Gate | measured | analytic air beta / `qep_phase2.json` |
| lossy h2 | 1.19656% | complex beta `0.0773232+0.00511172j 1/nm` | measured | analytic lossy beta / `qep_phase2.json` |
| patterned h3 | beta `0.0753552+0.00178365j 1/nm` | `+/-beta` error `<=7.50e-16` | measured | numerical QEP / `qep_phase2.json` |
| biorthogonality | patterned error `2.46e-10` | pass | measured | `modes_phase3.json` |
| tracking 80→79.8° | max principal angle `0.005918 rad` | no unmatched old mode | measured | `modes_phase3.json` |

h5 beta 误差说明 QEP 离散尚未收敛；它不否定同一离散上的 Hybrid/full3D 代数等价，也不能被
MUMPS 的小残差掩盖。

## 5. full3D 与 Hybrid 的规模

| mesh | 方法 | Nédélec / local FE DoF | ext. aux | internal `2M` | total rows | assembled NNZ | 数据身份 / 证据 |
|---|---|---:|---:|---:|---:|---:|---|
| h5 | full3D | 44,698 Nédélec | 80 | 0 | 44,778 | 4,896,156 | measured clean full3D record |
| h5 | Hybrid augmented M160 | 6,826 bottom + 6,826 top FE DoF | 80（40/side） | 320 | 14,052 | 2,000,624 | FE DoF derived from measured local rows minus aux；others measured M160 |
| h3 | full3D | 198,438 Nédélec | 80 | 0 | 198,518 | 21,317,860 | measured clean full3D record |
| h3 | Hybrid augmented M160 | 34,198 bottom + 34,198 top FE DoF | 80（40/side） | 320 | 68,796 | 8,594,673 | FE DoF derived from measured local rows minus aux；others measured M160 |

| mesh | full / Hybrid rows | rows reduction（分母=full） | full / Hybrid NNZ | NNZ reduction（分母=full） | 数据身份；单位/baseline；证据 |
|---|---:|---:|---:|---:|---|
| h5 | 3.187x | 68.62% | 2.447x | 59.14% | derived；ratio/% / full3D；full3D+h5 M160 records |
| h3 | 2.886x | 65.35% | 2.480x | 59.68% | derived；ratio/% / full3D；full3D+h3 M160 records |

| mesh | full3D hexa cells | two local blocks hexa cells | QEP full/reduced DoF | interface active DoF bottom/top | 13.5 nm M160 payload |
|---|---:|---:|---:|---:|---|
| h5 | 1,680 | 480 | 789 / 720 | 480 / 480 | right+left vectors 15,452,160 bytes |
| h3 | 7,776 | 2,592 | 2,053 / 1,944 | 1,296 / 1,458 | right+left vectors 40,929,280 bytes |

cell counts are `derived` from the recorded fitted x/y axes and the frozen Stage4 z-axis policy；
QEP/trace/payload numbers are `measured`。

| mesh | local-system rows / side | projection NNZ b/t | LU factor NNZ b/t | modal Schur | multi-RHS | transient RHS+solution / block | right+left vectors | 数据身份；baseline；证据 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| h5 M160 | 6,866 | 76,800 / 76,800 | 3,196,996 / 3,241,556 | 1,638,400 bytes | 321 RHS | 70,527,552 bytes | 15,452,160 bytes | measured；complex128 current direct；h5 M160 + h5 Schur-minimal records |
| h3 M160 | 34,238 | 207,360 / 233,280 | 30,593,644 / 30,078,396 | 1,638,400 bytes | 321 RHS | 351,692,736 bytes | 40,929,280 bytes | measured；complex128 current direct；h3 M160 + h3 Schur-minimal records |

## 6. Hybrid / full3D 物理结果

| mesh | method | true residual | R | T | A | max `|ΔR/T/A|` vs same-grid full3D | 数据身份 / 证据 |
|---|---|---:|---:|---:|---:|---:|---|
| h5 | full3D | `9.7340e-12` | 0.0890216029 | 0.4425882787 | 0.4683901184 | baseline | measured full3D h5 |
| h5 | Hybrid M160 | `2.5455e-12` | 0.0890210691 | 0.4425867427 | 0.4683921882 | `2.07e-6` | measured h5 M160 |
| h3 | full3D | `9.9234e-12` | 0.0046130314 | 0.5836533572 | 0.4117336114 | baseline | measured full3D h3 |
| h3 | Hybrid M160 | `2.6036e-12` | 0.0046128199 | 0.5836509402 | 0.4117362399 | `2.63e-6` | measured h3 M160 |

| mesh | interface E error | interface H error | max plane E error | max plane H error | volume closure | 数据身份；单位/baseline；Gate / 证据 |
|---|---:|---:|---:|---:|---:|---|
| h5 M160 | `2.46e-7` | `7.42e-3` | `3.20e-4` | `9.61e-4` | `1.73e-11` | measured；relative / same-grid full3D；pass / h5 M160 |
| h3 M160 | `2.50e-8` | `4.82e-4` | `9.96e-5` | `7.80e-4` | `3.27e-12` | measured；relative / same-grid full3D；pass / h3 M160 |

这些都是 `measured` 同网格误差。h5 与 h3 的 full3D R/T/A 差异明显，因此禁止写成连续物理网格
收敛。

## 7. 模态截断漏斗

| mesh | M transition | max total `|ΔR/T/A|` | significant amplitude relative delta | 结果 | 数据身份 / 证据 |
|---|---|---:|---:|---|---|
| h5 | 20→40 | `2.25e-5` | 未作为正式终点 | mandatory only；早期平台不足 | measured funnel |
| h5 | 40→80 | mandatory pass | record 内 | 未到 strong 终点 | measured funnel |
| h5 | 80→120 | strong platform begins | record 内 | continue once | measured funnel |
| h5 | 120→160 | `6.2395e-14` | `1.4793e-10` | strong pass / stop | measured M120/M160 |
| h3 | 120→160 | `1.2212e-14` | `1.3335e-10` | strong pass / stop | measured M120/M160 |

终止 Gate 的 baseline 是上一档 M；M160 不是越大越好的常数，而是当前单点的收敛终点。

## 8. direct path 内存与时间

权威内存口径为外部 0.25 s 同时采样的 live MPI worker RSS sum；不是各 rank 不同时刻的历史峰值和。

| mesh / path | worker RSS | cgroup current | total time | 相对同 mesh augmented（分母=augmented RSS） | swap | 数据身份 / 证据 |
|---|---:|---:|---:|---:|---:|---|
| h5 augmented | 1.8654 GiB | 1.5838 GiB | 70.72 s | baseline | 0 | measured memory_h5_augmented |
| h5 Schur fast | 1.7551 GiB | 1.1598 GiB | 63.01 s | -5.91% | 0 | measured memory_h5_schur_fast |
| h5 Schur minimal | 1.6977 GiB | 1.0611 GiB | 60.91 s | -8.99% | 0 | measured memory_h5_schur_minimal |
| h3 augmented | 3.8526 GiB | 3.2150 GiB | 102.58 s | baseline | 0 | measured memory_h3_augmented |
| h3 Schur fast | 3.9983 GiB | 3.3623 GiB | 111.97 s | +3.78% | 0 | measured memory_h3_schur_fast |
| h3 Schur minimal | **3.2244 GiB** | 2.5865 GiB | 99.69 s | **-16.31%** | 0 | measured memory_h3_schur_minimal |

Schur 代数本身不保证降内存；h3 的收益来自 bottom factor/contribution/release 后再处理 top，代价是
恢复场时逐侧重新因子化。当前峰值主因是 local sparse direct factor + all-mode dense multi-RHS，
不是 320×320 modal Schur。

## 9. h2 决策

| 方法 | center | conservative upper | Gate | 运行状态 | 数据身份 / 证据 |
|---|---:|---:|---|---|---|
| h5/h3 grid power law | 5.3649 GiB | 6.1697 GiB | center `<=4`, upper `<=5 GiB` | not_run | predicted / h2_prediction |
| MUMPS factor payload | 11.647 GiB | 13.394 GiB | same | not_run | predicted / h2_prediction |

两种预测差异很大且都失败，所以正确结论是 `h2 not_run_by_gate`，不能报告约 3 GiB 的假实测值。

## 10. 参数 smoke

| mesh | grazing angles | polarization | M / direction | pass | 证明 | 不证明 | 数据身份；单位/baseline；证据 |
|---|---|---|---:|---:|---|---|---|
| h5 | 1–10°，逐度 | S/P | 4 | 20/20 | parameter round-trip、QEP 重算、方向分类、algebra、有限输出 | 截断收敛、full3D 等价、cutoff 鲁棒性 | measured；deg/count / API Gate；parameter_smoke |
| h3 | 1/3/5/7/10° | S/P | 4 | 10/10 | 同上 | 同上 | measured；deg/count / API Gate；parameter_smoke |

## 11. 负结果与停止边界

| 负结果 | 观测 / 单位 | 根因或解释 | 决定 | 数据身份；baseline；证据 |
|---|---|---|---|---|
| h5 beta coarse error | 29.5323% | grazing beta 对横向色散敏感 | 保留；不宣称离散收敛 | measured；analytic beta；qep record |
| early M6 plateau | M20→40 仍 `2.25e-5` | 截断窗口太窄 | superseded by M20–160 funnel | measured；previous M；funnel |
| h3 Schur-fast memory | 3.9983 vs 3.8526 GiB | 并存因子/allocator 峰值 | 不提升 fast 为低内存路径 | measured；augmented；memory records |
| M120 per-mode Functions | MPI context exhaustion | 大量对象生命周期错误 | 改为共享 scratch；旧实现停止 | measured failure；prior object layout；`negative_results.md` |
| full3D h5 vs h3 | R/T/A materially different | 连续网格未收敛 | 只作同网格验证 | measured；h5；full3D records |
| h2 | 两套预测均过预算 | fail-closed memory Gate | not_run | predicted/not_run；4/5 GiB Gate；h2_prediction |
| current 0.7 direct | largest explicit object proxy about 1,595.60 TiB | local LU + replicated modes + all-mode RHS | do_not_run / redesign first | predicted/not_run；1–2 TiB；scalability assessment |

## 12. 0.7 nm 可扩展性摘要

| 量 | 13.5 nm measured baseline | 0.7 nm analytical estimate | 数据身份 | 边界 / 证据 |
|---|---:|---:|---|---|
| generic modes / direction | M160 retained；传播下界约43 | propagation lower bound 16,028.5；3.7x mechanical M=59,306 | derived | 后者不是收敛预测，也未含物理 evanescent buffer |
| QEP full DoF | 2,053 at h3 | 1,847,700 at uniform h0.1 | predicted | area factor 900 |
| local FE rows | 68,396 at 40 nm | 923,346,000 at 20 nm uniform h0.1 | predicted | volume/thickness factor 13,500；future external aux not projected |
| largest current-layout explicit object | current run fits | 1,595.60 TiB | predicted | all-mode RHS/solution proxy；excludes factors、mesh、Krylov |
| cumulative explicit-object volume | current run fits | 1,611.30 TiB | predicted | not simultaneous peak；projection JSON |
| 1 TiB desired local rows | n/a | `<=2e8` preferred；`2e8–3.5e8` candidate | design budget | not demonstrated |
| whole-solver memory | current direct semantics | `<=2 kB/FE DoF` preferred；3 kB hard exploratory ceiling | design budget | not demonstrated |
| final route | Hybrid proven | h/p + scalable generic modal core + iterative | decision | complex 3D ends required |

当前 Case080 的 y 不变性和 pure-modal 只允许作可选诊断/reference，不能进入未来通用服务资源预算，
也不能替代上下复杂三维 FEM。

## 13. 轻量 record 大小清单

| 指标 | 值 | 单位 | 数据身份 | 决定 |
|---|---:|---|---|---|
| tracked Task032 JSON count | 22 | files | measured filesystem | retain |
| total tracked JSON size | 1,406,455 | bytes | measured filesystem | retain |
| largest record | `hybrid_h5_m160.json` | 284,619 bytes | measured filesystem | retain |
| full field / eigenvectors / matrices / factors | 0 | tracked heavy payloads | measured repository policy | remain ignored |

当前最大 record 约 0.27 MiB，总量约 1.34 MiB（含本轮 3,488-byte projection）；M120/M160 中的逐衍射级复振幅是截断 funnel 的
必要轻量证据，且没有提交 full field、full eigenvector、matrix 或 factor。因此本轮**不压缩这些
records**。若未来单文件超过轻量阈值或加入完整数组，再只保留摘要、Gate、hash 和 ignored artifact
指针。

## 14. 选择性合并决定

| 对象 | 决定 | 身份 | ordinary default | 原因 / 证据 |
|---|---|---|---|---|
| QEP/Floquet reduction/mode classification/tracking | merge | experimental validated infrastructure | unchanged | Case080 Phase 2/3 pass |
| stable propagation / matched trace | merge | validated interface infrastructure | unchanged | Phase 4/5 pass |
| local mesh / local DtN / field reconstruction | merge | experimental Hybrid infrastructure | unchanged | h5/h3 physical pass |
| augmented direct | merge as reference | current-scale, not 0.7 production | unchanged | same-grid equivalence |
| Modal-Schur direct | merge as reference | current-scale experimental | unchanged | numeric pass；minimal memory positive |
| last-rank modal ownership | retain with warning | current-scale reference only | unchanged | not scalable |
| replicated dense M² / all-mode multi-RHS | retain with warning | current-scale reference only | unchanged | not scalable |
| all-modes MUMPS shift-invert QEP / local LU | retain with warning | current-scale direct only | unchanged | not 0.7 route |
| Case080/tests/docs/light records | merge | evidence + contracts | unchanged | checker 302/302 |
| heavy fields/meshes/eigenvectors/factors/logs/dirty records | do_not_merge | ignored artifacts | unchanged | repository policy |

文件级分类见 `selective_merge_manifest.csv`。在最终 review 接受前只推荐 provisional selective merge，
不建议整体合并 research branch。

## 15. 下一步与硬 Gate

| Task | 主目标 | quantified Gate / baseline | 停止条件 | 数据身份 | 证据 |
|---|---|---|---|---|---|
| 033 | local h/p adaptivity + interface-budget optimization | 13.5 nm 同误差 local DoF `>=3x` reduction，`>=5x` preferred / Task032 direct | <3x 或破坏同网格物理 Gate | planned | Review addendum / roadmap |
| 034 | scalable generic 2D modal core | distributed/streamed modes；no replicated M²；no all-mode RHS；adaptive M / current modal core | 任一显式核心仍超 1 TiB budget | planned | Review addendum / assessment |
| 035 | final Hybrid iterative | matrix-free local FEM、low-memory H(curl)、scalable modal action、true residual / Task033+034 | >3 kB/DoF 或数值 Gate 失败 | planned | Review addendum / roadmap |
| 036 | 13.5→5→2→1→0.7 nm continuation | 每步材料、M、网格、PC、1 TiB Gate 更新 / previous wavelength | 任一波长资源/数值 Gate 失败即停 | planned | Review addendum / roadmap |

未来精确复杂 3D ends 是目标架构的必要组成；pure-modal 只可作为当前简单几何可选 reference。

## 16. 证据入口

| 证据 | 路径 | 用途 |
|---|---|---|
| 任务书 | [`../task.md`](../task.md) | canonical Phase 与 Gate |
| Review V1 | [`../review_report_v1.md`](../review_report_v1.md) | 首轮结论与 P0 |
| Addendum | [`../review_report_v1_addendum.md`](../review_report_v1_addendum.md) | 复杂端部、M、1 TiB 路线修正 |
| Review follow-up | [`../response_v1_review_followup.md`](../response_v1_review_followup.md) | 采纳/暂不采纳和验证 |
| Case080 | [`../../../benchmarks/cases/080_hybrid_fem_modal_direct_baseline/README.md`](../../../benchmarks/cases/080_hybrid_fem_modal_direct_baseline/README.md) | 302/302 canonical contract |
| 0.7 assessment | [`task032_0p7nm_scalability_assessment.md`](task032_0p7nm_scalability_assessment.md) | 资源模型与 hard Gate |
| projection JSON | [`task032_0p7nm_projection.json`](task032_0p7nm_projection.json) | deterministic non-PDE estimate |
| merge manifest | [`selective_merge_manifest.csv`](selective_merge_manifest.csv) | 文件/模块级选择性合并边界 |
