# Full3D direct 网格比较（E5）

本页记录同一 5 nm、p6、S 偏振、10° 入射、MPI8、静态凝聚 direct Full3D 运行的离线比较。直接法在这里表示一次性组装并因子分解线性系统；网格比较用于判断离散网格改变后物理量是否稳定，不等同于连续极限证明。

完整 comparator 输出见 [E5 compact JSON](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e5_full3d_direct_grid_convergence_v2.json)。输入和 raw 运行目录只作为哈希绑定的证据载体，不纳入 Git：

```text
h10: results/task039_5nm_full3d_direct/task039_5nm_full3d_direct_p6h10_mpi8__full3d_direct__mpi8__Mna/20260812T204543.545080Z
h7.5: results/task039_5nm_full3d_direct/task039_5nm_full3d_direct_p6h7p5_mpi8__full3d_direct__mpi8__Mna/20260813T125001.607954Z
h6: results/task039_5nm_full3d_direct/task039_5nm_full3d_direct_p6h6_mpi8__full3d_direct__mpi8__Mna/20260813T133507.990830Z
```

## 1. 判定口径

| Gate | Mandatory | Strong |
|---|---:|---:|
| R/T/A/A_volume 绝对差 | 1e-4 | 1e-5 |
| 显著衍射级 power 相对差 | 1e-3 | 1e-4 |
| 显著衍射级复振幅相对差 | 1e-3 | 1e-4 |
| selected E 整体相对 L2 | 5e-3 | 2e-3 |
| selected H 整体相对 L2 | 1e-2 | 5e-3 |
| 每侧 energy closure | 1e-5 | 1e-5 |

显著集合按两侧 power 的并集、power ≥ 1e-8 定义；604 个 external mode key 必须 exact，坐标必须 exact。每个显著级的左右 power、复振幅、分母、相对差和两级状态均保存在 compact JSON 的 `significant_rows` 中，而不是只保存失败项。

## 2. h10 与 h7.5

该比较未通过 Mandatory，也未通过 Strong。closure、坐标、604 keys 和除 mesh 外的 tracked physical identity 检查通过；结果量本身和场误差未通过，不能把差异解释为收敛。

### 2.1 观测量与衍射级

| quantity | h10 | h7.5 | absolute delta | Mandatory actual/status | Strong actual/status |
|---|---:|---:|---:|---:|---:|
| R | 0.9094973679084956 | 0.001362582383157172 | 0.9081347855253384 | 0.9081347855 / 1e-4 / fail | 0.9081347855 / 1e-5 / fail |
| T | 0.0008705857370571771 | 0.027073280562035278 | 0.026202694824978102 | 0.02620269482 / 1e-4 / fail | 0.02620269482 / 1e-5 / fail |
| A | 0.08963204635444727 | 0.9715641370548076 | 0.8819320907003603 | 0.8819320907 / 1e-4 / fail | 0.8819320907 / 1e-5 / fail |
| A_volume | 0.08963204635549822 | 0.9715641370556518 | 0.8819320907001535 | 0.8819320907 / 1e-4 / fail | 0.8819320907 / 1e-5 / fail |
| significant power max relative | 39 keys | 39 keys | 0.999981803447285 | 0.9999818034 / 1e-3 / fail | 0.9999818034 / 1e-4 / fail |
| significant amplitude max relative | 39 keys | 39 keys | 1.8321482475850035 | 1.8321482476 / 1e-3 / fail | 1.8321482476 / 1e-4 / fail |

### 2.2 selected E/H

整体 E 的 absolute L2=43.53908659349355、relative L2=1.1253144112393418；Mandatory/Strong 均 fail。整体 H 的 absolute L2=0.1155770116466833、relative L2=1.1244693641767198；Mandatory/Strong 均 fail。

| z (nm) | E relative L2 | E status M/S | H relative L2 | H status M/S |
|---:|---:|---|---:|---|
| 10 | 1.003099092964 | fail/fail | 1.002654114001 | fail/fail |
| 30 | 1.002495759776 | fail/fail | 1.002290573184 | fail/fail |
| 60 | 0.995837372408 | fail/fail | 0.995965593815 | fail/fail |
| 90 | 0.982591242414 | fail/fail | 0.982275275561 | fail/fail |
| 110 | 1.262141592609 | fail/fail | 1.260983483434 | fail/fail |

各平面 absolute L2、参考范数、分母和五个场分量的完整值见 JSON 的 `fields`。

### 2.3 closure

| side | measured closure | Mandatory/Strong limit | status |
|---|---:|---:|---|
| h10 | 1.0509371151101732e-12 | 1e-5 | pass/pass |
| h7.5 | 8.44213587924969e-13 | 1e-5 | pass/pass |
| pairwise difference | 2.0672352718520415e-13 | diagnostic only | not a closure Gate |

## 3. h7.5 与 h6

该比较的 observables、closure、坐标、604 keys 和 selected E/H 均通过 Mandatory 与 Strong；但显著衍射级的 power/amplitude comparison 失败，因此总判定仍为 `grid_mandatory_fail`，不能仅凭 R/T/A 和场的接近而宣称网格收敛。最坏级为 bottom `(-10,0,S)`：power relative=0.630689、complex amplitude relative=1.076169；该级 power 约为 1e-7，仍属于已纳入的显著级 Gate。

| quantity | h7.5 | h6 | absolute delta | Mandatory actual/status | Strong actual/status |
|---|---:|---:|---:|---:|---:|
| R | 0.001362582383157172 | 0.0013619654896771616 | 6.16893480010405e-07 | 6.1689348e-7 / 1e-4 / pass | 6.1689348e-7 / 1e-5 / pass |
| T | 0.027073280562035278 | 0.02707346888475427 | 1.8832271899207886e-07 | 1.8832272e-7 / 1e-4 / pass | 1.8832272e-7 / 1e-5 / pass |
| A | 0.9715641370548076 | 0.9715645656255686 | 4.285707609907874e-07 | 4.2857076e-7 / 1e-4 / pass | 4.2857076e-7 / 1e-5 / pass |
| A_volume | 0.9715641370556518 | 0.971564565622532 | 4.285668802062048e-07 | 4.2856688e-7 / 1e-4 / pass | 4.2856688e-7 / 1e-5 / pass |
| significant power max relative | 38 keys | 38 keys | 0.6306892942411526 | 0.6306892942 / 1e-3 / fail | 0.6306892942 / 1e-4 / fail |
| significant amplitude max relative | 38 keys | 38 keys | 1.0761692217758436 | 1.0761692218 / 1e-3 / fail | 1.0761692218 / 1e-4 / fail |

整体 E 的 absolute L2=0.017643078424994872、relative L2=0.0004560041086575358，整体 H 的 absolute L2=4.121943519591991e-05、relative L2=0.0004010309949790607；两者均为 Mandatory/Strong pass。

| z (nm) | E relative L2 | E status M/S | H relative L2 | H status M/S |
|---:|---:|---|---:|---|
| 10 | 0.001492228103 | pass/pass | 0.001578260133 | pass/pass |
| 30 | 0.000880152664 | pass/pass | 0.000494237138 | pass/pass |
| 60 | 0.000517522641 | pass/pass | 0.000319971911 | pass/pass |
| 90 | 0.000229377087 | pass/pass | 0.000271741717 | pass/pass |
| 110 | 0.000185146585 | pass/pass | 0.000174016958 | pass/pass |

| side | measured closure | Mandatory/Strong limit | status |
|---|---:|---:|---|
| h7.5 | 8.44213587924969e-13 | 1e-5 | pass/pass |
| h6 | -3.0365709946522657e-12 | 1e-5 | pass/pass |
| pairwise difference | 3.880784582577235e-12 | diagnostic only | not a closure Gate |

## 4. §5.7 best-available 三层误差入口

当前没有独立、accuracy-qualified 的 `h_ref`。因此以 h6 作为 `h10 vs h_ref` 的 best-available discrete comparison，不称为离散化参考或连续极限。

| quantity | h10 | h6 | absolute delta | Mandatory actual/status | Strong actual/status |
|---|---:|---:|---:|---:|---:|
| R | 0.9094973679084956 | 0.0013619654896771616 | 0.9081354024188184 | 0.9081354024 / 1e-4 / fail | 0.9081354024 / 1e-5 / fail |
| T | 0.0008705857370571771 | 0.02707346888475427 | 0.026202883147697094 | 0.0262028831 / 1e-4 / fail | 0.0262028831 / 1e-5 / fail |
| A | 0.08963204635444727 | 0.9715645656255686 | 0.8819325192711214 | 0.8819325193 / 1e-4 / fail | 0.8819325193 / 1e-5 / fail |
| A_volume | 0.08963204635549822 | 0.971564565622532 | 0.8819325192670338 | 0.8819325193 / 1e-4 / fail | 0.8819325193 / 1e-5 / fail |
| E overall relative L2 | — | — | 43.53910476987228 | 1.1253144255 / 5e-3 / fail | 1.1253144255 / 2e-3 / fail |
| H overall relative L2 | — | — | 0.11557709692345329 | 1.1244695119 / 1e-2 / fail | 1.1244695119 / 5e-3 / fail |
| significant power max relative | 39 keys | 39 keys | 0.9999818035882131 | 0.9999818036 / 1e-3 / fail | 0.9999818036 / 1e-4 / fail |
| significant amplitude max relative | 39 keys | 39 keys | 1.879127035679951 | 1.8791270357 / 1e-3 / fail | 1.8791270357 / 1e-4 / fail |

## 5. 资源与范围边界

本 E5 只读取已完成的 h10、h7.5、h6 raw，并按现有 comparator 重算；未启动 h5。h5 状态为 `not_run_by_resource_policy`，原因是 E4 确认没有可用的 MUMPS symbolic/analysis-only authority，不能把完整因子分解冒充 preflight。

| item | result |
|---|---|
| h10 | measured fixed-grid direct authority；不代表网格收敛 |
| h7.5 | measured fixed-grid direct authority；与 h10 的 mandatory/strong grid comparison fail |
| h6 | measured fixed-grid direct authority；相对 h7.5 的 observables/fields pass，但 order comparison fail |
| h5 | not_run_by_resource_policy |
| E5 classification | `TASK039_FULL3D_DIRECT_GRID_CONVERGENCE_NOT_ESTABLISHED` |
| h6 data selection | `h6_best_available_discrete_reference`（仅为 best-available 数据选择，非 established reference） |
| continuum/grid convergence claim | false |
| formal §5.6 classification | `FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_WITHIN_RESOURCE_BUDGET` |
| Hybrid M480 | not evaluated in this E5 artifact；留待后续阶段 |

```math
\text{grid comparison pass} = \text{identity} \land \text{604 keys} \land \text{observables} \land \text{closure} \land \text{fields} \land \text{significant orders}.
```

因此 h7.5 与 h6 的局部场和总量接近并不足以建立完整网格收敛；h10 与 h7.5 的大幅差异原样保留，不被解释为实现修复或被改写为通过。
