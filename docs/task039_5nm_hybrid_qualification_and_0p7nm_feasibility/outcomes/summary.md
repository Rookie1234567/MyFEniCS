# Task39 最终结果摘要

## 18.1 p6/h10 fixed-grid

静态凝聚是在每个单元内先消去局部未知量，以较小的接口系统完成全局求解；直接法
再对该系统做因子分解。Hybrid 的 `M` 是每个传播方向保留的内部 QEP 模态数，
不是 external DtN channel count。RSS/PSS/USS 分别是同时进程树 resident、共享页
分摊和独占页峰值，不能拼成同一时刻的内存向量。

| method | MPI | M | external modes/endcap | iterations | residual | R/T/A/A_volume | RSS GiB | total wall (s) | status |
| --- | ---: | ---: | --- | ---: | ---: | --- | ---: | ---: | --- |
| Full3D direct | 8 | — | 604 total; bottom/top=300/304 | — | `3.5128313346e-11` | `0.9094973679084956 / 0.0008705857370571771 / 0.08963204635444727 / 0.08963204635549822` | 15.591 | 290.480347 | authority pass |
| Full3D iterative | 8 | — | 604 total; bottom/top=300/304 | 4000 | `0.1552648200` | not_run | 11.749 | 2870.386489 | `5NM_FULL3D_ITERATIVE_NUMERICAL_NEGATIVE_AT_P6H10` |
| Hybrid direct | 8 | 120 | 604 total; bottom/top=300/304 | — | `1.8233748636e-11` | `0.91108988194936 / 0.0002093910975196154 / 0.08870072695312035 / 0.08871017770327345` | 8.720 | 432.931447 | own E Gate fail |
| Hybrid direct | 8 | 240 | 604 total; bottom/top=300/304 | — | `1.0675101578e-11` | `0.9095051959995949 / 0.0008680629679617986 / 0.08962674103244331 / 0.0896271622555655` | 10.742 | 815.862600 | own E Gate fail |
| Hybrid direct | 8 | 480 | 604 total; bottom/top=300/304 | — | `8.9806001686e-12` | `0.9094973679567342 / 0.0008705857380481595 / 0.08963204630521765 / 0.08963319109929625` | 22.264 | 1468.884482 | own pass; Full3D diagnostic fail |
| Hybrid direct | 8 | 960 | 604 total; bottom/top=300/304 | not_run | not_available | not_run | 22.008 | 4812.858962 | negative before solution |
| Hybrid iterative | 8 | not_established | not_run | not_run | not_available | not_run | not_available | not_available | not_run |
| Hybrid iterative | 1 | not_established | not_run | not_run | not_available | not_run | not_available | not_available | not_run |

T3 direct 的 604 keys、33 个 significant channels、selected E/H、canonical 和完整
身份见 [T3 outcome](fixed_grid_full3d_reference.md)。T4/T5 的全部资源和阶段证据见
[resource ledger](resource_ledger.md) 与 [T5 outcome](hybrid_m_convergence.md)。

## 18.2 M convergence

| M | QEP retained | Schur size / state | Full3D RTA delta | max order delta | field diagnostic | RSS GiB | selected |
| ---: | --- | --- | --- | --- | --- | ---: | --- |
| 120 | +/− 120 | 240×240；0 B/not materialized/augmented direct | not_run | not_run | own interface E fail | 8.720 | not selected |
| 240 | +/− 240 | 480×480；0 B/not materialized/augmented direct | not_run | not_run | own top E `0.0066259299 > 0.005` | 10.742 | not selected |
| 480 | +/− 480 | 960×960；0 B/not materialized/augmented direct | diagnostic R/T/A finite；compact delta not separately available | power `3.0499574e-8`、amplitude `2.2165650e-8` | E `5.4759e-6` pass；H z=10 `0.0616688` fail、z=60 `0.0599587` fail | 22.264 | diagnostic only |
| 960 | +/−960 delivered；candidate=1960/1961；group count=577 reported | not_run | not_available | not_available | not_run | 22.008 | no solution |

M120/M240 的 own Gate 失败，所以 adjacent Gate 没有运行；M480-vs-M960 未定义，
因为 M960 没有合法 observable。M480 own pass 不能消除 Full3D iterative 的 T4 blocker，
也不能建立 `M_robust_h10`。

## 18.3 Grid convergence

| h nm | Full3D iterative | M_robust | Hybrid direct vs Full3D | Hybrid iterative vs direct | RSS MPI8 | RSS MPI1 |
| ---: | --- | --- | --- | --- | ---: | ---: |
| 10 | 4000-step negative | not_established | M480 diagnostic H fail | not_run | measured T3/T4/T5 | not_run |
| 7.5 | not_run | not_available | not_run | not_run | not_available | not_available |
| 5 | not_run | not_available | not_run | not_run | not_available | not_available |

h7.5/h5 均为 `not_run/blocked`，不是通过或失败的收敛点；h10 也不是 accuracy-qualified
grid。详见 [grid convergence boundary](grid_convergence.md)。

## 18.4 内存分解

| h / MPI / case | FE cache | local factors | W | K/LU | modal basis | Schur | Krylov | recovery | process-tree peak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 nm h10 Full3D direct / MPI8 | not_available | global MUMPS factor NNZ=217,041,864；local-factor bytes not_available | not_available | not_available | not_available | not_available | not_available | not_available | RSS 15.591 GiB；PSS 13.606；USS 13.292；swap 0 |
| 5 nm h10 Full3D iterative / MPI8 | not_available | global direct factor count=0；local-factor bytes not_available | not_available | not_available | not_available | not_available | not_available | 0.922486 s recovery | RSS 11.749 GiB；PSS 10.487；USS 10.288；swap 0 |
| Hybrid direct M120 / MPI8 | not_available | not_available | not_available | not_available | 30,696,960 B | 0 B；not materialized | not_available | 0.025221 s | RSS 8.720 GiB；swap 0 |
| Hybrid direct M240 / MPI8 | not_available | not_available | not_available | not_available | 61,393,920 B | 0 B；not materialized | not_available | 0.028211456 s | RSS 10.742 GiB；swap 0 |
| Hybrid direct M480 / MPI8 | not_available | not_available | not_available | not_available | 122,787,840 B | 0 B；not materialized | not_available | 0.024862294 s | RSS 22.264 GiB；swap 0 |
| Hybrid direct M960 / MPI8 | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run | measured pre-solution RSS 22.008 GiB；swap 0 |
| 0.7 nm p6/h1 Full3D derived envelope | not_established | global factor values-only 3234.18–32341.76 GiB；not local-factor authority | global W 12228.01 GiB；illustrative only | not_established | not_established | not_established | not_established | not_established | no process-tree run |
| 0.7 nm p6/h1 Hybrid known-air-side derived | not_established | not_established | W 201.220 GiB | K/LU 3.829–7.658 GiB；two-endcap authority pending substrate | not_established | not_established | not_established | not_established | no process-tree run |

solver-rank historical peak sum不属于 simultaneous process-tree peak；完整口径和 T3/T4/T5
smaps counts见 [resource ledger](resource_ledger.md)。T4 DtN preallocation audit separately reported
explicit C/D=1/1；这些是 DtN blocks，不是 local-factor bytes。0.7 nm 数字均为 derived
envelope，不是 process-tree 实测；factor values-only 不含 sparse indices、factor metadata 或 workspace。

## 18.5 0.7 nm 组件审计

| component | 5 nm measured | scenario A | p6/h1 | 220 GiB status | redesign |
| --- | --- | --- | --- | --- | --- |
| material/substrate | 5 nm n/epsilon authority | not_instantiated | missing 0.7 nm material | blocked | `0P7NM_MATERIAL_INPUT_INCOMPLETE` |
| air external inventory | 604 channels | not_instantiated | 16030 channels / 8015 spatial | exact component only | substrate pending |
| global FE trace | 51,192 rows | insufficient fit points | 51,192,000 derived h^-3 | no conservative budget proof | factor/cache classification |
| Hybrid endcap W | endcap trace rows=8424 measured；W bytes not measured | not_instantiated | 201.22 GiB W + known-air W+K_LU 205.049–208.878 GiB | upper exceeds effective 205.259 GiB | `0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN` |
| factor values-only | 217,041,864 factor NNZ measured；factor bytes not carried | not_instantiated | 3234.18–32341.76 GiB derived | exceeds | `0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET` |
| internal modal | T5 M480 measured anchor | not_instantiated | conditional 1/lambda and 1/lambda^2 models | upper dense LU can exceed | `0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN` |
| convergence | T3 pass/T4 negative/T5 M not established | not_instantiated | unbounded/not_established | no validation | `0P7NM_CONVERGENCE_RISK_UNRESOLVED` |

T9 只完成 component-only feasibility；完整分类和 two-endcap conditional example 见
[feasibility_0p7nm.md](feasibility_0p7nm.md)。

## 最终分类与未完成项

并列保留以下边界：

```text
TASK039_5NM_FIXED_GRID_SOLVER_CAPACITY_QUALIFIED_ONLY
TASK039_FULL3D_ITERATIVE_WAVELENGTH_ROBUSTNESS_FAIL_AT_5NM
5NM_HYBRID_MODEL_NOT_ESTABLISHED_BY_M960_AT_P6H10
HYBRID_DIRECT_DIAGNOSTIC_FAIL
0P7NM_MATERIAL_INPUT_INCOMPLETE
0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET
0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN
0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN
0P7NM_CONVERGENCE_RISK_UNRESOLVED
```

禁止使用 `TASK039_5NM_FULL3D_HYBRID_ACCURACY_AND_MEMORY_QUALIFIED`、
`TASK039_ITERATIVE_SOLVER_PASS_HYBRID_MODEL_FAIL_AT_5NM` 或
`CURRENT_ARCHITECTURE_PLAUSIBLE`。T6–T8、h7.5/h5 和完整 0.7 nm PDE 仍为
`not_run`；repository full pytest 为用户成本覆盖取消的 `cancelled / not_run`，不是 pass
或 zero failures。T10 B1 的 code/static parent SHA 为
`b737c62149186356a1c07c267f473e360274cc8a`；docs-only closeout 不改变 Python、config
或 schema。
