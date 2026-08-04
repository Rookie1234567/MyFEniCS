# Task037 结果总览

## 最终结论

Task037 在固定的 13.5 nm、p6/h10、S 偏振、MPI8 Full3D 上完成了 direct
authority、assembled FGMRES 和一次 released matrix-free full solve。求解器真残差、
物理 observables 及 12/12 powers 和 12/12 boundary amplitudes 通过；raw
PETSc-index vector Gate 和资源 Gate 未通过。因此最终分类是
`PARTIAL_WITH_CONTROLLED_NEGATIVES`，不是 production-qualified pass。

静态凝聚把每个单元内部未知量先局部消去，只把 active trace 与 80 个 auxiliary
rows 留给全局系统；收益是全局 rows 降为 `51272`，代价是必须做 interior recovery 和
full explicit residual。assembled FGMRES 先形成 fine `F`，再用右预条件的两层 PC
迭代求解，避免 global direct factor，但仍保留 assembled fine matrix。F5b 在 setup
阶段用同一个 `F` 建立 slab factors 和 coarse basis，随后在 outer KSP 前释放 `F`，
用 cell-local Schur action 继续施加 fine action；它不是 never-materialized 方案。

## 统一结果

| 路径（证据） | 终点与 residual | 物理/向量 Gate | 峰值与 wall | 分类 |
|---|---|---|---|---|
| F0 direct（[authority](direct_authority.md)） | `2.8094057923e-11` | 12+12 pass；direct reference | `15.2550010681 GiB`，`370.18 s` | authority pass |
| F3 screen 20（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_20_screen_v1.json)） | reported/full `0.0302833465991175` | screen-only；decision pass；solver max-it expected；RTA `not_run` | `13.2211914063 GiB`，`159.96 s` | decision pass |
| F3 screen 100（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_100_screen_v1.json)） | reported/full `0.000608485581260`；last-40 ratio `0.1852104694` | screen-only；decision pass；RTA `not_run` | `12.9641036987 GiB`，`212.73 s` | decision pass |
| F3 screen 200（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_200_screen_v1.json)） | full `3.5885919793e-5`；predicted `323` it / `473.764 s` | full-solve authorization pass；RTA `not_run` | `12.9706878662 GiB`，worker `293.35 s` | full-solve authorization pass |
| F3 assembled full（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_assembled_full_v1.json)） | 337 it；three residuals `9.8166e-7` | 12+12/RTA pass；raw vectors fail | `13.6522331238 GiB`，`410.546 s` | not pass |
| F5b matrix-free（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f5b_matrix_free_full_v1.json)） | 337 it；three residuals `9.8166e-7` | 12+12/RTA pass；raw vectors fail | `13.6580085754 GiB`，`396.603 s` | partial |

F3 screen 的关键 history 均保留在 records；20 步没有预测值，100 步使用实际
last-40 decline，200 步使用记录中的 last-40 log-linear 预测。三项 screen 都是
screen-only，不是收敛或 official result。

## full solve 数值比较

| 量 | F0 direct | F3 assembled | F5b matrix-free |
|---|---:|---:|---:|
| `R_total` | `0.0007628814751` | `0.0007628816329` | `0.0007628816329` |
| `T_total` | `0.6027016340` | `0.6027016326` | `0.6027016326` |
| `A_balance` | `0.3965354845` | `0.3965354857` | `0.3965354857` |
| `A_volume` | `0.3965354845` | `0.3965354852` | `0.3965354852` |
| `R(0,0)_s` | `7.537612200510555e-4` | `7.537613464884375e-4` | `7.53761346488528e-4` |
| `T(0,0)_s` | `0.6026738723475807` | `0.6026738712269` | `0.6026738712269` |
| energy closure | `4.9916e-12` | `-5.3943e-10` | `-5.3943e-10` |
| significant channels | 12/12 + 12/12 | 12/12 + 12/12 | 12/12 + 12/12 |

F5b 的 fine-action relative error 为 `9.2309237020e-16`，远低于 `1e-11`；其
active-trace 与 recovered-FE ownership-order bytes 相对 F3 的差分别为
`1.5478270800e-14` 和 `1.4162962151e-14`。但相对 F0 direct 的 raw indexwise
relative L2 为 active `1.4210359558`、full FE `1.4121310623`，均失败
`<=1e-5`。这支持 ordering inference，不能替代 Task 7.1 raw-vector Gate。

## 资源与结构 Gate

| 项目 | F0 | F3 full | F5b |
|---|---:|---:|---:|
| process-tree RSS | `15.2550010681 GiB` | `13.6522331238 GiB` | `13.6580085754 GiB` |
| worker PSS / USS | `13254.321 / 13047.027 MiB` | `11980.911 / 11776.828 MiB` | `12058.898 / 11854.363 MiB` |
| swap | 0 | 0 | 0 |
| active / auxiliary / augmented | `51192 / 80 / 51272` | same | same |
| operator / coarse / smoother applies | direct path | `1093 / 337 / 2022` | `1093 / 337 / 2022` |

F5b 相对 F0 只节约约 `1.597 GiB`、约 `10.5%`，仍高于 `10.30 GiB` resource
gate；相对 F3 没有实质改善。它有 `16` physical slabs、75/75 coarse、16
factor-only ILU(0)、global direct factor count `0`；这些结构结果不能替代内存
Gate。

## 规模与分阶段耗时

| 规模/存储量 | F0 direct | F3 assembled | F5b released matrix-free |
|---|---:|---:|---:|
| full FE / active / auxiliary / augmented rows | `173802 / 51192 / 80 / 51272` | same | same |
| full trace rows | `60402` | `60402` | `60402` |
| fine matrix NNZ used / allocated | `41989040 / 42625520` | same and held | setup formed same `F`, released before outer KSP |
| factor inventory | MUMPS `209772680` | global direct factor count `0` | global direct factor count `0` |
| local-factor aggregate | — | `103336560` across 16 local factors, not a global factor | `103336560` across 16 local factors, not a global factor |

| path | measured phase timings (s) | total wall (s) |
|---|---|---:|
| F0 direct | assembly `90.9635`; factor setup `140.3829`; backsolve `0.1941`; recovery `0.1260`; full residual `109.5097`; RTA/post `8.6164` | `370.18` |
| F3 assembled | core setup `26.39295`; core solve `265.87634`; recovery `0.03812`; stage4 `391.65416`; post `9.15041` | `410.54647` |
| F5b released | core setup `26.16943`; core solve `252.79113`; recovery `0.02824`; stage4 `378.93805`; post `9.14910` | `396.60297` |

Core setup/solve/recovery 与 stage4/parent total 是不同的嵌套计时口径，不能相加。

## 受控负结果与边界

- F1 direct-vector oracle 的 residual 约 `3029.7262491090364`，远高于其
  `1e-9` Gate；returned augmented norm `1484.6523798860264` 与 F0
  `742.1374458852146` 不一致，证明 F0 raw active vector 不能直接作为当前运行坐标的 oracle。
- F3/F5b raw vector indexwise Gate 均失败；物理采样、排序 magnitude 和 F3/F5b
  ownership-order 一致性只能说明比较口径疑似受 partition/DoF ordering 影响。
- 两次 serial tiny lifecycle smoke（p2/h50、p6/h50）在 release/KSP 前因 5 层
  z 网格上的固定 75D coarse basis singular，既不证实也不否定 F5b；另有一次目录
  路径拼写错误未形成有效数值 run。正式 p6/h10 MPI8 F5b 只运行一次。
- MPI4 formal full、F4、F5c、F6、Hybrid、hp、0.7 nm 和 Task037b 均未运行，且
  F5c/F6 保持 `not_run`。当前不能外推为 0.7 nm 可用。

## 证据与下一步

完整 12-channel 表和 F5b/F3/F0 对比在
[matrix_free_report.md](matrix_free_report.md)，资源与 MPI 边界在
[resource_and_mpi_report.md](resource_and_mpi_report.md)，F3 full 细节在
[assembled_fgmres_full.md](assembled_fgmres_full.md)。结构化证据还包括
[F0 record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_direct_authority_v1.json)
和 [F5b record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f5b_matrix_free_full_v1.json)。

建议下一步先做峰值对象生命周期归因；若另立任务，再评估真正 no-global-F 和
scalable auxiliary multigrid。Task037b 只作为建议，不在本任务启动。
