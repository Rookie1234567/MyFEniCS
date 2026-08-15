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
`b737c62149186356a1c07c267f473e360274cc8a`；后续最终 docs-only closeout 不再改变
Python、config 或 schema；Review V1 最终轻量 Gate 对应已提交的 A commit
`36c729f7ae197d08f92e044907d0cb723f9fd43c`。

## E6 Review V1：M480 H-field diagnostic

这一步把 Hybrid 的既有 native 磁场、由完整重构电场解析求旋度得到的 `curlE` 磁场，
以及从 T3 canonical shard 离线恢复的 Full3D 磁场放在同一组七个平面上比较。它回答
“差异是否只来自 H 的后处理路径”，不回答生产模型是否已经被验证。

| 比较 | E relative L2 | H relative L2 | flux/energy Gate | 结论 |
| --- | ---: | ---: | --- | --- |
| native vs curlE | 0 | `0.0010876471954123718` | mandatory/strong pass | 两种 Hybrid H 路径接近但不完全相同 |
| curlE vs Full3D | `0.0008277153668860366` | `0.007498197526364605` | mandatory/strong pass | Full3D 对照差异保留 |
| native vs Full3D | `0.0008277153668860366` | `0.007797760173875772` | mandatory/strong pass | Full3D 对照差异保留 |

E6 checker 的 `numeric_gate_pass=true` 和 `diagnostic_complete=true`，但正式分类仍为
`M480_H_DISCREPANCY_UNRESOLVED`：三个特殊因果分支都没有被充分证据命中。这个分类
与数值阈值通过不矛盾。Raw 的 `physical_augmented_direct_pass=false`、`official_record=false`
和 sampled traction-density proxy `false` 原样保留；exact traction Gate 已通过。
完整七平面和逐分量证据见 [E6 H diagnostic outcome](m480_h_field_diagnostic.md)。

## Review V1 extension closeout

本节是首轮 T3–T10 历史表之后的扩展结果；§18.1–§18.5 中的 h5 `not_run` 条目是不可改写的
historical snapshot，已由下方 Review V2 V2-2 current status supersede，不应解读为当前 h5
状态。首轮 M960 在 T5 的 pre-solution negative 记录仍保留，下面的 M960 是 Review V1 E7
唯一一次冻结 direct rerun，不能互相覆盖。

### E5–E7 结果

| 主题 | measured / derived 结果 | 正式边界 |
| --- | --- | --- |
| Full3D direct | h10、h7.5、h6 own solve pass；h5 `not_run_by_resource_policy` | 网格 mandatory/strong 未收敛；`FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_WITHIN_RESOURCE_BUDGET` |
| Full3D reference | h6 为 `best_available_discrete_reference` | 不是 continuum/refined authority；E5 `reference_established=false` |
| M480 H diagnostic | numeric Gate pass；三路径比较已完成 | `M480_H_DISCREPANCY_UNRESOLVED` |
| M960 trace family | M120/240/480/960 两侧 finite、sign/order、repeat 和 backward Gate pass | family classification=`M960_TRACE_AUTHORITY_NUMERICAL_AUDIT_PASS` |
| M960 formal direct | residual `1.679e-11`、projection `5.789e-13`、traction bottom/top `3.835e-12/1.672e-11`、closure `1.149e-6` | own Gate pass；`official_record=false` 仅表示 M/model qualification pending |

### M960 formal direct 与比较

| 项目 | 值 |
| --- | --- |
| R/T/A_balance/A_volume | `0.9094973679165264 / 0.0008705857370964508 / 0.0896320463463772 / 0.08963319492586634` |
| external keys | `604` exact；bottom/top `300/304` |
| numerical wall | `5332.772663516924 s` |
| RSS/PSS/USS | `71502.582 / 69746.089 / 69465.102 MiB`，独立峰值 |
| swap | `0 MiB` |
| M480 vs M960 | totals、33 significant power/amplitude、selected E/H 全部通过 |
| M960 vs Full3D h10 | H z=10 `0.0616688409`、z=60 `0.0599587361` 失败 |
| M960 vs Full3D h6 | 差异大；h6 不是已建立 reference |

h6 的 mesh-dependent physical SHA 与 h10 不同是预期；E5 已独立证明
`physics_except_mesh_exact=true`，不能将其写成物理合同错误。M960 与 Full3D 的 H 失败
也不撤销 M480 H diagnostic 的 `M480_H_DISCREPANCY_UNRESOLVED` 分类。

### E8–E10 停止与内存

E8/E9 均为 `not_run_by_review_v1_7p3_stop_after_m960_direct`。这表示 Review §7.3
要求的受控停止，不表示 Hybrid iterative 成功或失败；首轮 T6 的 iterative 未运行
事实保持不变。

| M / 运行 | RSS | PSS / USS | stage-aligned snapshot |
| --- | ---: | --- | --- |
| M120 | `8.720 GiB` | not_available in E10 series | not_available |
| M240 | `10.742 GiB` | not_available in E10 series | not_available |
| M480 | `22.264 GiB` | not_available in E10 series | not_available |
| M960 prior trace | `22.008 GiB` | not_available | not_available |
| M960 formal direct | `71502.582 MiB` (`69.827 GiB`) | `69746.089 / 69465.102 MiB` measured | not_available |

formal direct 只有全局 process-tree peak，没有 stage-aligned snapshot；basis、coupling、
projection 或 factor 容量不能相加冒充 resident RSS。E10 仅确定
`UNATTRIBUTED_RUNTIME_OR_ALLOCATOR_HIGH_WATER`；`LIFECYCLE_OVERLAP_DOMINANT` 只是
hypothesis/not_established，其余 QEP workspace、mode replication、coupling、local
factor、modal Schur dominant 均 not_established。完整说明见
[M960 numerical audit](m960_trace_numerical_audit.md)、[iterative boundary](m480_hybrid_iterative_solver_diagnostic.md)
和 [memory forensics](memory_lifecycle_forensics.md)。

### Review V2 progress：V2-0 / V2-1

| 阶段 | 状态 | 结论与边界 |
| --- | --- | --- |
| V2-0 inherited audit | `completed` | h10 仅为 `historical_underresolved_stress_anchor_only`，禁止作 Full3D 5nm reference、Hybrid physical authority 或 0.7 nm mesh-scaling |
| V2-1 h5 readiness | `historical V2-1 status: pass_with_formal_run_pending` | validate/dry-run、604 keys、资源与 ABI 通过；整数运行时 factor 路径仍 `not_established`；已由下方 V2-2/V2-3 current status supersede |
| V2-2 h5 Full3D direct | `pass` | 唯一正式 run 的 own Gate 通过；h5 是 Full3D discrete authority，不宣称收敛 |
| V2-3 comparison | `completed / negative` | 离线 primary 未通过；不把 h6-vs-h5 写成 convergence |

V2-1 的用户覆盖 watchdog 为 warning `170 GiB`、critical `195 GiB`（只记录 crossing）和
absolute hard `224000000000 bytes`，任意 swap 立即停止；195 GiB 不再单凭预测阻止启动。
详情见 [h5 readiness](full3d_h5_direct_and_convergence.md)、[V2-1 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_full3d_readiness_v1.json)
和 [resource ledger](resource_ledger.md)。

### Review V2 V2-2：h5 Full3D discrete authority

V2-2 只运行了一次冻结的 p6/h5、5 nm、Full3D direct、MPI8 formal case。`official_result=true`、
`case_status=completed`、true relative residual=`1.1426908495328136e-10`，official dtn-port
R/T/A_balance/A_volume=`0.0020255498177907264 / 0.02845408887668467 /
0.9695203613055247 / 0.9695203613041327`，closure=`-1.3919976282750213e-12`。
604 keys 为 exact unique（bottom/top=`300/304`），beta 与 amplitudes 均 finite；5 个选定平面的 E/H 均 finite；active/full
canonical export 分别为 `371502/1127502` packets，各 8 rank shards、duplicates=0。

| 资源 / 时间 | measured 值 | 口径 |
| --- | ---: | --- |
| process-tree RSS/PSS/USS | `92491.328 / 90440.785 / 90103.539 MiB` | 独立峰值；不能视为同一采样点向量 |
| swap / warning / critical | `0 MiB / false / false` | warning 170 GiB；critical 195 GiB 仅记录 crossing |
| absolute hard | `224000000000 bytes`（约 `208.6162567138672 GiB`） | 用户覆盖的 contract hard stop |
| KSP setup/factorization / solve | `4748.209038352999 / 2.743420086999322 s` | measured |
| numerical elapsed | `5330.2902718020005 s` | measured |

矩阵口径为 cells=`1680`、full FE DoFs=`1127502`、active trace=`336960`、assembled rows with auxiliary=`337564`，
condensed NNZ used/allocated=`283210150/298136764`。因子遥测的 raw int32 溢出
（INFOG(9)=`-2597`、raw matrix NNZ=`-1697967296`）和 `factor_nnz_corrected=2597000000`
均原样保留，未修复或重跑。完整身份、artifact SHA 和 own-Gate 字段见
[V2-2 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_full3d_direct_v1.json)。

本节不改变 h10 的 `historical_underresolved_stress_anchor_only` 边界；h5 仍不是
h6-vs-h5 convergence reference，V2-3 已完成且为 `negative`，完整 repository pytest 仍为
`cancelled / not_run`。

### Review V2 V2-3：h6-vs-h5 two-tier offline comparison

既有 h6/h5 raw authority 已各读取一次并完成一次离线 comparator；没有重跑 PDE/MPI。
identity、604 keys、selected coordinates、closure 通过；R/T/A、E/H、primary orders 和
all-604 aggregate 未通过。h5 保持 `best_available_discrete_authority_only`，不称收敛参考。

本次 comparator 的代码/测试来源为 `d63f37b213c11aa3f965fec066074451e06ca57c`，正式 comparator
调用次数为 `1`；compact record 保留完整逐级诊断，raw matrix/field artifact 未进入 Git。

| 当前 Gate | 实际结果 | 限值 / 状态 |
| --- | ---: | --- |
| observables max abs delta | `0.0020442043200439297` | `<=1e-5`；fail |
| closure h6 / h5 | `3.0365709946522657e-12 / 1.3919976282750213e-12` | 各 `<=1e-5`；pass |
| selected E / H relative L2 | `0.14450862376996956 / 0.14701895099975776` | `2e-3 / 5e-3`；fail |
| primary orders max power / amplitude | `0.3673545224476542 / 0.3905831132869025` | `<=1e-3`；fail |
| all-604 weighted power / amplitude | `0.07101046038911143 / 0.3868889801657988` | `<=1e-4 / <=1e-3`；fail |
| weak / below `1e-8` | `29 fail / 565 counted` | weak rows retained in record |

正式分类为 `FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_AT_P6H5`，h5 role 为
`best_available_discrete_authority_only`；完整逐级诊断和来源路径见
[V2-3 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h6_h5_two_tier_convergence_v1.json)
与 [V2-3 Full3D outcome](full3d_h5_direct_and_convergence.md)。

### Review V2 V2-4：h5 Hybrid direct readiness（historical snapshot）

V2-4 仅完成 clean-SHA、ABI、资源、输入 validate/dry-run 和 604-key preflight；没有
QEP、local FE、augmented、factor 或 PDE。MemAvailable=`225.03710174560547 GiB`、
swap used=`0`、disk free=`808005708 KiB`，readiness/launch eligibility=`true`
（conditional）。h5 Hybrid 的 rows/NNZ/factor/RSS 都是由 h10 Hybrid、h10 Full3D 和
h5 Full3D measured anchors 推导的中心值与保守区间，不是 measured formal result。

V2-5 formal h5 Hybrid direct=`not_run` 是 V2-4 readiness 时点的历史状态；随后 V2-5
own run 已完成、V2-6 为 `H5_M480_HYBRID_MODEL_FAIL`，详见下方 current closeout。
当时的整数 ABI 已知 row/order=`int32`、NNZ counter=`int64`，runtime factor 内部路径仍
`not_established`。详见
[h5 Hybrid readiness](h5_hybrid_direct_readiness.md) 和
[compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_direct_readiness_v1.json)。

### Review V2 V2-7/V2-8 current closeout

下表是当前状态，覆盖并更新本页较早的 V2-7 `not_run` 历史快照；首轮 T3–T10 和
V2-6 负结果均保留。V2-7 只在用户覆盖下作为 diagnostic 运行，不能提升 Hybrid
物理资格。

| 阶段/模型 | current status | measured result / boundary | evidence |
| --- | --- | --- | --- |
| V2-6 h5 Hybrid direct vs Full3D | `H5_M480_HYBRID_MODEL_FAIL` | 9 primary 中 5 fail；weak 30 中 29 fail；weighted power `8.685769e-5` 通过但不否决 primary | [V2-6 outcome](h5_hybrid_direct_memory_attribution.md) |
| V2-7 h5 Hybrid iterative M480 MPI8 | `H5_M480_HYBRID_ITERATIVE_SOLVER_FAIL` | `6000` iterations，`DIVERGED_MAX_IT`；global/bottom/top residual `0.9679803826/0.9882585936/0.9641613365`，limit `5e-9` | [V2-7 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_iterative_m480_v1.json) |
| V2-7 user status | `overridden_by_user_for_diagnostic_only` | 不是 Hybrid physical qualification；未进入 MPI1/M960/M>480 | [V2-7 outcome](h5_hybrid_iterative_m480_mpi8.md) |
| V2-7 resource | measured negative-run comparison | RSS/PSS/USS `83155.316/82055.122/81869.0 MiB`，swap `0`；较 h5 direct RSS 少 `4.1376972771%`，低于 meaningful 20% | [V2-7 outcome](h5_hybrid_iterative_m480_mpi8.md) |
| V2-8 iterative-vs-direct physics | `not_run_not_applicable` | residual Gate 未通过，未形成合法 recovery/physics/RTA/field | [V2-7 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_iterative_m480_v1.json) |

最终并列边界仍包括 `FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_AT_P6H5`、
`H5_M480_HYBRID_MODEL_FAIL`、`H5_M480_HYBRID_ITERATIVE_SOLVER_FAIL`、
`TASK039_FULL3D_ITERATIVE_WAVELENGTH_ROBUSTNESS_FAIL_AT_5NM` 以及既有 0.7 nm
材料、factor/cache、external DtN、modal Schur 和 convergence-risk 分类。
不存在 `TASK039_5NM_FULL3D_HYBRID_ACCURACY_AND_MEMORY_QUALIFIED` 或 Hybrid physical pass。

### Review V3：1° Full3D 网格选择（current）

| 阶段 | 状态 | 结论 |
| --- | --- | --- |
| V3-3 h5 Full3D direct | own pass | 1°/5 nm；RSS `93.8976 GiB`；selected solver-stress anchor |
| V3-3 h4.5 Full3D direct | own pass | RSS `125.5527 GiB`；与 h5 的 R/T/A/A_volume 差约 `1e-8` |
| V3-4 2D↔h5/h4.5 | negative | scalar、selected E/H、main-m power fail；分类 `reduction/model-contract discrepancy pending` |
| V3-3 h4 / h3 | not run | h4 predicted约 `201.1 GiB`，h3 `360–630 GiB`，按资源策略停止 |
| V3-5 Hybrid direct | `TASK039_V3_HYBRID_INTEGRATED_PHYSICS_PASS_CHANNEL_DIAGNOSTIC_PENDING` | integrated Gate 通过；逐通道保持 diagnostic pending，见 [V3-5 outcome](h5_hybrid_direct_memory_attribution.md) 与已绑定 record |

V3-3/V3-4 的 raw 仍在 ignored results，compact 数值与 SHA 见
[V3 Full3D outcome](v3_3d_full3d_convergence.md) 和
[V3 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_3d_full3d_convergence_v1.json)。
原有 V3-2 Q8 二维 reference 和所有 V2/T3–T10 negative 结论不改写。

### Review V3 h4 supplementary Full3D result

The earlier h4 `not_run` row was a pre-launch decision snapshot. The later user-authorized
single h4 run is now a measured resource-controlled stop: the direct linear solve converged
in one iteration with true relative residual `3.5718033073581125e-10`, and DtN modal
`R/T/A_balance` were `0.7331834795712868 / 0.00022243948649826534 /
0.26659408094221493`. `A_volume`, independent closure, final field/canonical package and
final 604-key authority are `not_available` because the process was stopped during
`solver_objects_retained_for_postprocess`.

The resource authority measured RSS/PSS/USS peaks `214091.234375 / 212744.140625 /
212535.75390625 MiB`, swap `0`, and `17448` complete samples. The warning/critical/hard
contract was `170 GiB / 195 GiB / 224000000000 bytes (208.6162567138672 GiB)` at `0.25 s`;
classification is `memory_terminate`, not a numerical failure or full own-pass. h3 remains
cancelled/not_run. See the [h4 supplementary record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_h4_full3d_direct_supplement_v1.json)
and [full h4 outcome](v3_3d_full3d_convergence.md); the Task39 main line returns to the h5
Hybrid V3-7 algebra/telemetry diagnosis with formal MPI8 only.
