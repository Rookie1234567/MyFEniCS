# Task034 最终成果汇总（Review V2）

## 状态与范围

| 字段 | 结论 | 证据身份 |
|---|---|---|
| final status | `PASS_WITH_QUALIFICATIONS` | 失败和资源 stop 原样保留 |
| production mainline | S polarization | 用户批准；不重复整套 P 矩阵 |
| P capability | p2/h5 MPI8 Full3D + Hybrid M160 可计算 | capability sample，不参与 S 收敛主线 |
| Review authority merge | `a23d59981a64015e35c82b8afa2a945b8d8e1e3e` | normal merge；未 rebase/force/rewrite |
| numerical core in Review V2 | unchanged | 未重跑 p3/h3、p4/h5 或 MPI 重型矩阵 |
| unified fact table | 40 rows / 36 columns | `all_model_results.json/csv`；空缺为 `null`，不插值 |

## Capability layering

| capability | 状态 | 边界 |
|---|---|---|
| workflow decision complete | true | Task034 每阶段有正式 decision |
| uniform benchmark | pass | Case093 固定几何 p2/p3/p4 S 主线 |
| representative MPI identity | pass | p3/h5 S；Full3D/Hybrid MPI1/8/16，MPI32 exploratory |
| graded mesh mechanism | pass | mesh/Floquet/标记机制可执行 |
| equal-accuracy graded compression | controlled negative | 三档均未通过 fixed Full3D 同误差 Gate |
| field-driven adaptivity | not qualified | 不把 raw DoF reduction 写成 qualified compression |
| common-mesh / p3 adaptive extension | not run by stop condition | critical observable failure 后停止 |
| resource model | revised engineering stress test | p2/p3/p4 场景；envelope 与 simultaneous peak 分离 |
| production 0.7 nm feasibility | unknown / not demonstrated | current-layout stress tests 均有单组件超 2 TiB |

## 表 1：all models

所有入射均为 S；`R00_p/T00_p` 表示 S 入射下的 cross-polarized p 输出，不是 P 入射复跑。
完整结构、DoF、NNZ、timing、memory、R00 与 evidence path 见 `all_model_results.csv/json`。

| p/h nm | Full3D status；R/T/A_volume | Hybrid status；M；R/T/A_volume | closure |
|---|---|---|---|
| p2/h5 | pass；.089021603/.442588279/.468390118 | pass；160；.089021069/.442586743/.468392188 | pass |
| p2/h3 | pass；.004613031/.583653357/.411733611 | pass；160；.004612820/.583650940/.411736240 | pass |
| p2/h2 | pass；.001342933/.599213229/.399443838 | pass；160；.001342885/.599212676/.399444439 | pass |
| p2/h1 | `not_run_by_conservative_resource_gate_after_assembly`；无 official | `timeout_during_field_recovery_no_official_solution`；160；无 official | unavailable |
| p3/h10 | pass；.055398491/.406067867/.538533643 | `formal_not_pass`；160；.055398802/.406069310/.538531887 | not qualified |
| p3/h7.5 | pass；.003090727/.591160863/.405748409 | pass；160；.003090647/.591159679/.405749673 | pass |
| p3/h5 | pass；.001090107/.600622478/.398287415 | pass；160；.001090096/.600622368/.398287536 | pass |
| p3/h3 | pass；.000789468/.602514984/.396695548 | pass；160；.000789467/.602514979/.396695554 | pass |
| p3/h2 | `not_run_by_conservative_resource_gate_after_assembly`；无 official | shard pass only；160；.000764467/.602690128/.396545405 | no funnel/closure |
| p4/h10 | pass；.001882317/.596619520/.401498163 | pass；160；.001882348/.596619395/.401498258 | pass |
| p4/h7.5 | pass；.000802469/.602429773/.396767758 | pass；160；.000802465/.602429757/.396767778 | pass |
| p4/h5 | pass；.000766313/.602677531/.396556156 | pass；160；.000766313/.602677530/.396556157 | pass |
| p4/h3 | `not_run_by_conservative_resource_gate_after_assembly`；无 official | shard pass only；160；.000762185/.602706301/.396531514 | no funnel/closure |

## 表 2：M funnel（p3/h3 与 p4/h5）

| case | M | R/T/A_balance | true residual | peak GiB | total s | status |
|---|---:|---|---:|---:|---:|---|
| p3/h3 | 80 | .000789467335/.602514978712/.396695553953 | `6.762e-12` | 8.698 | 881.93 | pass |
| p3/h3 | 120 | .000789467334/.602514978699/.396695553967 | `7.632e-12` | 9.806 | 1002.97 | pass |
| p3/h3 | 160 | .000789467334/.602514978698/.396695553968 | `3.903e-11` | 10.762 | 1113.84 | selected/pass |
| p4/h5 | 80 | .000766313235/.602677529602/.396556157163 | `5.182e-12` | 5.049 | 558.97 | pass |
| p4/h5 | 120 | .000766313235/.602677529589/.396556157177 | `5.726e-12` | 5.498 | 634.19 | pass |
| p4/h5 | 160 | .000766313235/.602677529589/.396556157177 | `7.031e-12` | 5.961 | 734.22 | selected/pass |

两组 M120→M160 均通过 strong convergence Gate；M240 condition 未触发。

## 表 3：MPI identity（p3/h5 S）

| method | MPI | true residual | peak GiB | core solve/total s | identity |
|---|---:|---:|---:|---:|---|
| Full3D | 1 | `1.265e-10` | 6.340 | 1050.52 | pass |
| Full3D | 8 | `8.305e-12` | 9.014 | 150.51 | pass |
| Full3D | 16 | `1.143e-11` | 11.359 | 72.97 | pass |
| Full3D | 32 | `6.912e-12` | 15.773 | 41.95 | exploratory pass |
| Hybrid M160 | 1 | `6.418e-12` | 1.245 | 431.07 | pass |
| Hybrid M160 | 8 | `1.164e-11` | 4.900 | 144.69 | pass |
| Hybrid M160 | 16 | `3.397e-12` | 7.150 | 134.13 | pass |
| Hybrid M160 | 32 | `3.788e-12` | 12.088 | 201.10 | exploratory pass |

同一方法内 case/source/config/structure 一致，official R/T/A、fields/interfaces、orders、complex
amplitudes、QEP beta 与 true residual 全部满足 identity 阈值；MPI32 不替代 MPI16。

## 表 4：资源 stop 与受控负结果

| case/method | measured progress | measured peak GiB | predicted upper / timeout | exact status |
|---|---|---:|---:|---|
| p2/h1 Full3D | assembly；4,379,832 rows；461,122,320 NNZ | 67.923 | factor upper 418.821 GiB | `not_run_by_conservative_resource_gate_after_assembly` |
| p2/h1 Hybrid M160 | local factors/Schur 完成；field recovery 开始 | 95.879 | 7200 s timeout | `timeout_during_field_recovery_no_official_solution` |
| p3/h2 Full3D | assembly 1334.65 s；2,047,298 rows；488,789,000 NNZ | 64.015 | factor upper 232.460 GiB | `not_run_by_conservative_resource_gate_after_assembly` |
| p3/h2 Hybrid M160 | complete shard；residual `3.613e-11` | 49.642 | 3513.82 s measured | pass only；no M funnel/closure |
| p4/h3 Full3D | assembly 3035.14 s；1,540,028 rows；696,091,072 NNZ | 80.538 | factor upper 204.132 GiB | `not_run_by_conservative_resource_gate_after_assembly` |
| p4/h3 Hybrid M160 | complete shard；residual `2.924e-11` | 42.481 | 3662.69 s measured | pass only；no M funnel/closure |

三条 Full3D 的 factorization/full-solve 均 `launched=false`；upper 是预测而非 measured peak。
p2/h1 Hybrid 未触发 memory warning、swap 为 0，但没有 solver record、official R/T/A 或 true residual。

## Adaptive 与资源模型

| adaptive profile | raw DoF reduction | peak GiB | wall s | same-error result |
|---|---:|---:|---:|---|
| conservative | 1.561x | 3.964 | 112.12 | controlled negative |
| balanced | 3.172x | 3.292 | 96.63 | controlled negative |
| aggressive | 9.590x | 2.537 | 71.92 | controlled negative |

资源模型 v2.1 使用 p2/h3、p3/h3、p4/h5 三个 13.5 nm current-layout 场景。13.5 nm
simultaneous peaks 分别为 4.695/14.272/9.206 GiB；外推 peak 全为 `unknown`。0.7 nm 的
cumulative envelopes 分别为 2,014,975/6,804,671/3,008,763 GiB，但这些累计值不是同时峰值。
三个场景均存在单组件超过 2 TiB，故 current layout stress test 为负；production target-accuracy
DoF、M 和 peak 仍是 unknown。

## Review V2 工程边界

- benchmark Python inventory 覆盖 31 个变更文件，未发现 Task034 复制独立 solver；数值功能归 `src/`；
- `selective_merge_manifest.csv` 逐文件给出 action、dependency group、tests、数值变化、PDE 证据和顺序；
- research-only adaptive/reranking/resource/Review 聚合器不作为 production API；
- p1 与完整重型 P 矩阵仍按用户批准范围排除；任何 negative 未改写为 pass。
