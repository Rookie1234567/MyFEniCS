# Task037 Review V1 response v1

## 1. 范围、身份与结论

本 response 只总结 Full3D static-condensed iterative 的 M0–M4 证据，不扩展
Hybrid、Task037b、0.7 nm、hp、M3b 或新的 PDE campaign。数值/PDE 证据的源码身份为：

| 项目 | 值 |
|---|---|
| branch | `codex/20260803-task37-matrix-free-iterative-development` |
| numerical/PDE evidence source / canonical-fix commit | `2631a4c47258c9def919530787e409774b8ce029` |
| parent of canonical fix | `151ba7ba3c41550d2b3d98dc9436ef9db732d943` |
| closeout scope | 仅 9 个 docs/compact records；不改变 numerical source |
| environment | `source scripts/activate_myfenics_wsl.sh`；project `.venv`；PETSc complex128/int32；OMP_NUM_THREADS=1 |
| final classification | `NUMERICAL_SUCCESS_RESOURCE_REVIEW` |
| production qualification / whole-branch merge | NO / NO |

“静态凝聚”可以直观理解为：先在每个有限元单元内部消去只属于该单元的未知量，
全局求解只保留单元边界 trace 和 DtN auxiliary unknowns，求解完成后再恢复完整
有限元场。它减少全局未知量，但会增加局部消元、trace action、恢复和资源管理
成本，所以本任务同时要求真残差、物理量、canonical field 和内存证据。

## 2. 当前正式结果

| 路径 | 模型 / MPI | residual | 物理 Gate | 内存 / wall | 状态 |
|---|---|---:|---|---:|---|
| Direct v2 | p6/h10/S；MPI8 | `1.17818264392128e-11` | official=true；12/12 powers、12/12 amplitudes | `15.059223175048828 GiB` / `218.851869611 s` | current authority |
| M3a full | same model；MPI4；overlap .125 partition | full FE `9.923273535279698e-7` | official=true；12/12、RTA pass | `8.265838623046875 GiB` / `701.6504903390305 s` | numerical success / resource review |
| M3a historical screen20 | same candidate；MPI8 | reported `0.04000947850823184` | screen only | `11.7366867065 GiB` | resource negative |
| old F3 overlap .25 | historical candidate | 100: `0.000608485581260`；200: `3.5885919793e-5` | screen/authorization evidence | old records | not M3a |

Direct v2 记录见 [task37_direct_authority_v2.json](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_direct_authority_v2.json)；
M3a 记录见 [task37_m3a_overlap0125_partition_full_v1.json](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_m3a_overlap0125_partition_full_v1.json)。

## 3. M0–M4 工作和边界

| 阶段 | 做了什么 | 证明什么 | 未证明什么 |
|---|---|---|---|
| M0 | 统一 source、observer、provenance、资源和 canonical artifact 记录 | 结果可绑定到 source/command/artifact | 不改变 ordinary 数值默认 |
| M1a/M1b | action-only fine Schur action；直接 C/D/H/RHS block sink | 可在不组装 augmented A/F 的路径上保持 DtN 代数 | 不等于最终高阶 PC |
| M1c | typed never-materialized request/port 接入真实 modal loop | M3a 路径的 global A/F=false 合同可审计 | 尚未证明所有 MPI 分区 raw hash bitwise 相同 |
| M2a | owner-local slab row closure、routed sequential matrices、partition metadata | `R_i F R_i^T` 的局部路由和通信/内存上界 | 不覆盖 M3a overlap 选择 |
| M2b/M2c | factor-only owner-local ILU、two-color、two-step GMRES、75D coarse 和 cleanup | setup 后只保留 factors；M3a 可复用同一 smoother lifecycle | 不证明 p2 auxiliary 或 high-order patch 足以替代 slab PC |
| M3a | overlap `0.125`、partition-of-unity weights、MPI4 full | 绝对 memory Gate、residual、canonical/physical observables 全通过 | engineering half-memory Gate、same-candidate MPI4/8 formal identity |
| M4a/M4b/M4c | p2 trace transfer、true Galerkin `F2=P^H F6 P`、projected DtN blocks、p2 auxiliary candidate | 小 fixture 上的 transfer/Galerkin/Modal algebra和 no-global p2 PC组件 | 没有把 p2 candidate接成当前最终 M3a solver |
| M4d | full element patch及真正 high-order complement oracle | 两类 patch 在 serial oracle 上都未达到 efficacy | 不应继续扩展 face/edge patch或用 damping 掩盖 |

### Review V1 后精确提交链

| 阶段 | commits（短 SHA） |
|---|---|
| M0 | `a45a6b30`, `d112fe85`, `74eae399`, `dd247398`, `d126e445` |
| M1 | `2a033481`, `7c285ed5`, `2b1e52da` |
| M2 | `3eb61d49`, `7d43986b`, `a9a141f1`, `1e9c9923` |
| M4 | `5fc06192`, `926cd735`, `c0dc7a2c`, `72657daf` |
| M3 | `89f3b745`, `93c25b9a`, `710ec053`, `0ecd5f14`, `151ba7ba`, `2631a4c4` |

真实 chronology 是：M4 transfer/p2/oracle 工作先于最后的 M3a full/canonical
收口提交；上表按 review slice 分组，不伪造线性阶段顺序。完整前序链以
`git log` 为准。

### 候选迭代账本

| 候选 | 20 步 | 100 步 | 200 步 | full / 边界 |
|---|---:|---:|---:|---|
| old F3 overlap .25 assembled | `0.0302833465991175`；[screen20 record](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_20_screen_v1.json) | `0.000608485581260`；[screen100 record](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_100_screen_v1.json) | `3.5885919793e-5`；[screen200 record](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_200_screen_v1.json) | old assembled full 337 it，约 `9.8166e-7`；[assembled outcome](outcomes/assembled_fgmres_full.md) |
| M2c never-materialized owner-local | `0.0341112948`；[M2c outcome](outcomes/m2c_never_materialized_screen.md) | `not_run`（resource negative） | `not_run`（resource negative） | 未形成 full authority |
| M3a overlap .125 MPI8 | reported/condensed `0.04000947850823184 / 0.040009478508230854`；[negative outcome](outcomes/m3a_overlap0125_partition_negative.md) | `not_run`（resource negative） | `not_run`（resource negative） | MPI4 full 365 it；[current outcome](outcomes/m3a_overlap0125_partition_full.md) |
| M4 p2 / high-order patch | N/A | N/A | N/A | 不是 20/100/200 KSP candidate；[M4d negative](outcomes/m4d_high_order_patch_oracle_negative.md) |

`not_run` 表示没有运行，不能由其他 screen 推测或补值。

M4d negative 记录保留在旧 outcome；它不是 production failure，也不授权继续
开发该路线。

### Assembled 与 matrix-free action 的历史边界

F5a cell-local Schur action 相对误差为 `9.2309237020e-16`；F5b 是
assembled-once、released-before-solve 的路径，不是 never-materialized。当前 M3a
才是 global A/F=false 的实际 full-solve 路径。详见
[matrix_free_report.md](outcomes/matrix_free_report.md)。

## 4. 数值、RTA 与通道 Gate

M3a residual sequence 的正式终点是 365 iterations，KSP
`CONVERGED_RTOL`；reported `9.923273241434768e-7`，condensed true
`9.923273236187206e-7`，full FE `9.923273535279698e-7`，interior max
`1.1140981751262269e-12`，均满足 `1e-6`。

| 量 | Direct v2 | M3a MPI4 | 绝对差 |
|---|---:|---:|---:|
| `R_total` | 0.000762881475132771 | 0.0007628813414779686 | 1.336548023948e-10 |
| `T_total` | 0.6027016339861171 | 0.6027016365247442 | 2.538627086324e-9 |
| `A_balance` | 0.3965354845387501 | 0.3965354821337779 | 2.404972221370e-9 |
| `A_volume_total` | 0.3965354845429724 | 0.396535483656842 | 8.861303912866e-10 |
| energy closure | 4.222400207254395e-12 | 1.5230641192687244e-9 | descriptive |

12/12 significant powers 和 12/12 outgoing boundary complex amplitudes 通过；
每项的 Direct/M3a 值、tolerance、power diff、complex amplitude diff 均在
M3a record 的 `channels_12` 中逐项保存。最大 power abs diff 为
`3.2419746887057954e-9`，最大 amplitude abs diff 为
`2.3497820161653558e-7`。

## 5. 规范化场与新鲜网格范数

active manifest 各为 60402 项，full-FE manifest 各为 173802 项，missing/extra/
duplicate 均为 0。60402 是由 51192 个 independent active coordinates 经
TraceConstraintMap 展开/约束还原后的完整 original-trace canonical packets，
不是线性系统 rows 增加。

| 比较 | relative L2 | max abs | Gate |
|---|---:|---:|---|
| active Direct MPI8 vs M3a MPI4 | 1.2553898016411866e-6 | 4.625555666881793e-5 | pass <=1e-5 |
| full FE Direct MPI8 vs M3a MPI4 | 7.880394026823442e-7 | 4.625555666881793e-5 | pass <=1e-5 |

full-FE 分组 relative L2：cell interior `3.9365767477e-7`、non-Floquet edge
`3.3065297416e-6`、non-Floquet face `6.2302185081e-7`、Floquet edge
`4.4843834146e-6`、Floquet face `8.3934712195e-7`。canonical Floquet
orientation fix 后，Floquet face 异常消失。

在同一 fresh p6/h10 mesh、MPI4、252 cells、173802 DoFs 上的 offline norm 为：

| 指标 | relative |
|---|---:|
| `relative_l2` | 3.449938833419635e-7 |
| `relative_curl_l2` | 3.278099243754906e-7 |
| `relative_tangential_trace_mass` | 7.099902806903749e-7 |
| `relative_hcurl` | 3.419997826589739e-7 |

命令是 `source scripts/activate_myfenics_wsl.sh && PYTHONPATH=/home/Projects/MyFEniCS mpiexec -n 4 python /tmp/task037_physical_norm_gate.py`；
脚本在 `/tmp`，未跟踪；耗时 339.75918469496537 s。它是 offline reconstruction，
不是新的 PDE solve。

## 6. 资源、因子与计时账本

| 项目 | Direct v2 MPI8 | M3a MPI4 |
|---|---:|---:|
| process-tree authority | 15.059223175048828 GiB | 8.265838623046875 GiB |
| worker RSS/PSS/USS | 15406.0078 / 13373.5186 / 13062.9414 MiB | 8449.6406 / 7505.6914 / 7209.0938 MiB |
| swap | 0 | 0 |
| factor rows / stored NNZ | 51272 / 209772680 factor NNZ | 127656 / 91415952 |
| M3a factor CSR payload lower bound | — | 1828829728 bytes |
| M3a coarse basis storage | — | 9481648 bytes |
| M3a operator/coarse/one-level applies | — | 1178 / 365 / 2190 |

M3a core setup/solve/recovery/total 为
`126.8370741350227 / 393.26021890802076 / 0.046614531020168215 /
520.1891550979926 s`；run-summary 的 Stage4 DtN linear solve
`520.1943626219872 s`，Stage4 total `686.207802555 s`，cell recovery
`0.2428163019940257 s`，full residual `1.5376178169972263 s`，
postprocess `8.297736085020006 s`，parent wall `701.6504903390305 s`。
Direct full residual timing为 `0.9020630560116842 s`；Direct parent wall
`218.851869611 s`。这些是不同嵌套 scope，不能相加。

derived M3a/Direct memory ratio `0.5488887791199146`，reduction
`45.111122088008536%`，half Direct `7.529611587524414 GiB`；cross-MPI
wall ratio `3.206052073423701`。M3a 通过绝对 `<=10.30 GiB`，未通过工程
half-memory目标；这不是 solver numerical failure。

## 7. 测试、来源与未运行项

final canonical fix targeted evidence：serial test226 `3 passed / 2 skipped`；
MPI2 test226 每 rank `4 passed / 1 skipped`；test227+228 `5 passed / 3 skipped`；
Ruff、py_compile/compileall、git diff --check 通过。正式 artifacts 的 command、
qualified activation、Python、PETSc scalar/int、MPI、parent descriptor/SHA 已写入
两个 compact records。

Full repository pytest 未在最终 source 上重跑，状态为
`not_run_by_user_efficiency_policy / not_verified`，不能写成 PASS。未运行项还包括
新的 MPI8 iterative full identity、原 task.md 中另列但本轮未完成资格化的 F4 集成、F5c、F6、Task037b、Hybrid、hp、0.7 nm 和新的
PDE screen。

## 8. 变更与提交

本轮 closeout 只涉及以下 9 个路径，均为文档或 compact record：

1. 修改：`benchmarks/cases/100_static_condensed_full3d_iterative/README.md`
2. 修改：`docs/task037_static_condensed_full3d_iterative/outcomes/summary.md`
3. 修改：`docs/task037_static_condensed_full3d_iterative/outcomes/resource_and_mpi_report.md`
4. 修改：`docs/task037_static_condensed_full3d_iterative/outcomes/test_summary.md`
5. 修改：`docs/task037_static_condensed_full3d_iterative/outcomes/direct_authority.md`
6. 新增：`benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_direct_authority_v2.json`
7. 新增：`benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_m3a_overlap0125_partition_full_v1.json`
8. 新增：`docs/task037_static_condensed_full3d_iterative/outcomes/m3a_overlap0125_partition_full.md`
9. 新增：`docs/task037_static_condensed_full3d_iterative/response_v1.md`

当前 closeout exact diffstat：tracked 5 files `+83/-29`；4 个新增文件按最终行数
`151+266+128+211=756`，合计 9 paths、`+839/-29`。统计只覆盖上述 9 个路径。此前相对 `origin/master` 的基线审计快照为 `62 files,
+18188/-422`，这是文档 closeout 前的历史统计，不是最终 closeout 后统计。
四个新增文件的行数按 Direct record、M3a record、M3a outcome、response v1 顺序列示。
tracked 删除只来自历史标题层级与措辞收口，不涉及数值算法。
前序 Task37 提交见上节提交链和 `git log`；本轮 closeout 由后续独立 docs/record commit 承载，不改变上述 numerical evidence source。

## 9. 未解决问题与 Task037b 建议

- same-candidate MPI4/8 formal identity 未验证：M3a full 只有 MPI4，MPI8 只有历史 screen20。
- final full repository pytest 未在最终 source 上验证，明确为 `not_run_by_user_efficiency_policy / not_verified`。
- M3a 通过 absolute `10.30 GiB`，但 50% memory target 未通过。
- Python/local metadata 与资源账本没有取得 0.7 nm qualification，不能外推 scalability。
- Task037b 只有在用户另行授权后，才可讨论 Hybrid iterative/endcap/modal/M120/direct-vs-iterative；本轮不启动。

## 10. 选择性合并建议与边界

| 依赖组 | 内容 | 建议 |
|---|---|---|
| canonical 通用修复 / opt-in tooling | Floquet canonical transform、canonical export/comparator、records/checker contracts | 可在独立 review 后选择性审阅；不改变 ordinary defaults |
| never-materialized / M2 / M3 / M4 | owner-local slab、M3a/M4 research profiles、p2/high-order candidates | 仍为 research-only；不得把整条链称为 production numerical/core |
| compact evidence/docs | 本 response、两个 records、M3a outcome、README/summary 索引 | 可独立合入以保留可审计结果 |
| negative evidence / do-not-merge | M4d high-order patch negative、未资格化候选、Hybrid/0.7 nm/Task037b | 保留证据，不合入 production |

当前没有 merge approval；`whole-branch merge=NO`。
