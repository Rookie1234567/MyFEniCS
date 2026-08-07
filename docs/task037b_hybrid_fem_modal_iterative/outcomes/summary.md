# Task037b 受控结项总览

## 一句话结论

H0 继承基线通过；首次 H1 direct Hybrid MPI8 formal 在生成 Hybrid 解以前因近简并模态分组检查退出，历史证据保留。post-fix source `2990f357f7dec23b1713bd0088bdc43c3ce6f5bc` 已完成同一冻结条件下的有效求解并通过 task.md §9 H1 contract；H2a、H2b、H3 与 H4 均已通过，H5 是下一阶段。

## H0-H10 矩阵

| 阶段 | 状态 | 说明 |
|---|---|---|
| H0 | pass | 继承基线和文档治理完成 |
| H1 | pass（post-fix；首次 failed_before_solve 历史保留） | task.md §9 H1 numerical contract 通过 |
| H2a | pass | assembled-block MatPython action identity |
| H2b | pass | Matrix-free local endcap exact action identity |
| H3 | pass | exact block-LDU iterative oracle；offline 12+12 已通过 |
| H4 | pass | exact Sₘ + bounded G-only diagnostic；不要求 12+12 |
| H5 | next | H4 已完成，按顺序进入 approximate local inverse |
| H6 | not_run_by_order | H5 尚未完成 |
| H7 | not_run_by_order | H5 尚未完成 |
| H8 | not_run_by_order | H5 尚未完成 |
| H9 | not_run_by_order | H5 尚未完成 |
| H10 | not_run_by_order | H5 尚未完成 |

## H1 首次停止点（3f72ef3）

mode classification 发生在横截面 QEP 求解之后、Hybrid block system 生成之前。它把传播常数接近的模态分成小组，并建立后续界面方程需要的双基底。当前检查发现索引 50 和 52 属于不同组，但误差量达到冻结分组检查的边界，于是 fail closed。

| 字段 | 实际值 |
|---|---:|
| exception | NearDegenerateBlockPartitionSplitError |
| indices | [50, 52] |
| group_ids | [17, 18] |
| relative beta distance | 1.580086e-06 |
| identity row norm | 1.024637e-06 |
| identity max/cross-block max | 6.572908e-07 |
| limit | 1.000000e-06 |
| formal return code | 1 |

这一步没有产生当前 Hybrid 的解，因此不能填写为 0 的量都应标作 not_observed 或 not_run。

## 当前源码与 authority

| 项目 | 值 |
|---|---|
| branch | codex/20260807-task37b-hybrid-iterative-development |
| clean source SHA | 3f72ef3eb4f3002246802af30ef7bca6b0080888 |
| Full3D historical record | /home/Projects/MyFEniCS/benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_full_static_mpi8_244b62e.json |
| Full3D record SHA256 | b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3 |
| historical preflight authority SHA256 | 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 |
| pinned source | 244b62e1fb4f299a468363cf90a2dd548dc34ff6 |
| pinned gate | pass |
| ordinary defaults | unchanged |
| H1 mode | explicit opt-in |

## H1 结果边界

| 结果组 | 状态 |
|---|---|
| H1 telemetry | not_observed |
| combined/bottom/top FE/modal residual | not_observed |
| interface E/H 与 middle-plane E/H | not_observed |
| powers/amplitudes | not_run |
| R/T/A 与 A_volume closure | not_run |
| rows/block shapes/matrix NNZ/factor NNZ | not_observed |
| official Hybrid result | not_run |

## H1 post-fix recovery（2990f357）

post-fix formal return code 为 `0`，`formal_pass=true`，true relative residual 为 `1.4476013948489319e-12`。rows、block shapes、matrix/factor inventory、interface/middle-plane fields、R/T/A、A_volume closure、资源和 hash-bound 原始证据详见 [direct authority](direct_hybrid_authority.md) 与 [resource ledger](resource_ledger.md)。

| Gate | post-fix 结果 |
|---|---|
| true residual | `1.4476013948489319e-12`，pass |
| frozen-reference powers / boundary amplitudes | `12/12` / `12/12`，pass |
| Full3D pairwise relative-1e-3 powers / amplitudes | `12/12` / `12/12`，pass；最大相对误差分别 `6.51037642788911e-10` / `6.667955305244103e-10` |
| interface/middle-plane E/H | pass |
| R/T/A_volume closure | `1.0000000001554779`，error `1.5547785281455617e-10`，pass |
| swap | 0 |
| ordinary defaults | unchanged；H1 explicit opt-in |

runner 仍保留 `physical_qualified=false`、`official_record=false`、`mode_count_converged=false` 的 wider-M funnel 旧标签；它们不是 task.md §9 H1 Gate，也不改变本次 H1 task-specific contract pass。随后 H3 与 H4 已按顺序完成；H5 为下一阶段。

## 资源

| 指标 | 实测值 |
|---|---:|
| wall | 约 49.54 s |
| RSS/process-tree peak | 2647.4375 MiB |
| authority peak | 2.58538818359375 GiB |
| PSS peak | 1761.02734375 MiB |
| USS peak | 1637.375 MiB |
| swap | 0 |
| memory warning/termination/timeout | false / false / false |

该峰值来自 classification 阶段 whole-job，不是成功 Hybrid 求解的资源预测。

raw JSON 字段名虽含 max_*_mb，但本文按 bytes/1024^2 统一换算并显示为 MiB；authority 峰值显示为 GiB。

## 统一验收与未运行边界（H1 停止点历史快照）

| 能力/验收 | 状态 |
|---|---|
| current-source direct numerical authority | failed_before_solve |
| iterative Hybrid | not_run_by_H1_gate |
| exact action / exact LDU | not_run_by_H1_gate |
| bottom/top local inverse | not_run_by_H1_gate |
| one-sided / double funnels | not_run_by_H1_gate |
| MPI/restart | not_run_by_H1_gate |
| 12+12 powers/amplitudes、channel/field、RTA | not_run_by_H1_gate |
| merge recommendation | do_not_merge_to_master / wait for review |

## 测试与证据

测试和资源细节分别见 [测试汇总](test_summary.md)、[direct authority](direct_hybrid_authority.md)、[资源账本](resource_ledger.md) 和 [changed files](changed_files.md)。raw artifact 位于 Git ignored 目录；tracked docs 只保存相对路径和 SHA，不提交原始输出。

## 下一步边界

首次失败阶段不修 solver、不放宽 1e-6、不扫描 M、角度或 p-h；post-fix 只实施已审查的最小 grouping/audit 修复并完成一次 H1 recovery。H2a、H2b、H3 与 H4 已通过；H5 为下一阶段，H6-H10 按顺序未运行。

## H2a 当前边界

H2a 已完成 assembled bottom/top block 与 modal/coupling action 的 algebraic identity：
MPI1/2/4 的 deterministic probes、physical packed RHS、bottom-only/top-only/modal-only
probes、pack/split 和 ownership mapping 均通过。production global operator 是 MatPython，
没有 materialize global AIJ。

逐 probe relative error 与完整命令见 [block identity](block_operator_identity.md)。H3/H4 的 exact oracle 证据见 [exact block-LDU oracle](exact_block_ldu_oracle.md)。

## H2b Matrix-free local endcap exact action identity

H2b 将外部 auxiliary 从 Hybrid Krylov unknown 中排除：production 从构造开始使用
local-Schur action 和 matrix-free DtN action，test-only oracle 才使用 explicit-condensed
local blocks。它证明的是 local endcap 的代数 action、ownership、pack/split 与销毁顺序，
不是第一次 outer FGMRES、solver convergence 或资源资格化。

| 项目 | 结果 |
|---|---|
| H2b-L MPI1 | `1 passed`；bottom action/recovery/RHS `3.058e-16 / 4.352e-16 / 0`，top `3.730e-16 / 4.297e-16 / 6.993e-17`；Gate `<=1e-11` |
| H2b-G MPI1/2/4 | 每 rank `5 passed`；七 probes 四块合计最大分别 `2.942e-16 / 2.988e-16 / 3.539e-16`，均 `<=1e-11` |
| mapping/pack-split | 每个 MPI missing/extra/duplicates=`0/0/0`；bottom/top/modal=`0/0/0` |
| inventory | global A=false；bottom/top F=false；explicit external C/D=`0/0`；p6 direct factor count=`0`；Krylov auxiliary rows=`0` |
| 相关回归 | test224/test230/test231=`5 passed / 1 skipped`；import、Ruff、format、compileall、diff-check 全部 pass |

H2b-G 的每行数值是该 MPI 七个 probes 和 global/bottom/top/modal 四个输出块的总体最大值；
四块逐项均不超过对应 MPI 行的总体最大值。H3 与 H4 已完成，H5 为下一阶段。

## H3/H4 exact oracle checkpoint

| 阶段 | formal/diagnostic 结果 | 核心数值 | 资源与边界 |
|---|---|---|---|
| H3 | formal、numeric、no-swap pass | outer=1；true global/bottom/top/modal=`2.892237294698294e-12 / 3.610918199454199e-12 / 2.0470485206121342e-12 / 9.879221339086588e-13`；offline 12+12=`12/12 + 12/12` | `507.2017102949321 s`；authority peak `9.585384368896484 GiB`；factors released |
| H4a | exact Sₘ pass | outer=1；true global/bottom/top/modal=`2.7239301070596716e-12 / 3.982460029685523e-12 / 1.7429945983458624e-12 / 1.001248228432052e-12` | H4 whole-job oracle peak `9.802722930908203 GiB`；swap=0 |
| H4b | bounded diagnostic complete | G-only outer=3、reason=-3；finite/evidence/factor lifecycle pass；不以残差大小判失败 | H4 不要求 12+12；H5 采用 approximate Sₘ 路径 |

完整 residual、Sₘ/G feedback、operator inventory、factor before/after 和 hash-bound artifact 见 [exact block-LDU oracle](exact_block_ldu_oracle.md)。
