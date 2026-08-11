# H2B-P0 row-complete patch：run3 formal PASS 与历史受控停止证据

## 先用通俗语言说明

P0 的 row-complete patch 是一个只围绕中心 cell 的局部实验：中心 cell 有 882 个独立行，但相邻 touching cells 也可能通过 Floquet/MPC 约束影响这些行，所以要把这些邻居的局部贡献累加成同一个 `B_P = R_P B0 R_P^T`。它不是全局矩阵、全局约束矩阵或 PDE 求解器。

本轮还修复了一个明显的重复工作：如果多个 touching cells 属于同一个已验证 exact class，它们的 material、几何宽度、orientation、constraint pattern 和 canonical basis 相同，局部 curl/mass dense tensor 只需对该 class 的代表 cell 做一次。之后每个 cell 仍使用自己的 `independent_global_rows` 和同一个 class expansion pattern 累加。收益是减少昂贵的 form/tensor tabulation；代价是必须严格证明 class identity、cell 行映射和浮点累加顺序没有改变。

run1/run2 是历史受控停止：run2 针对 telemetry race，run3 则针对已测得的 per-cell 重复 tabulation，二者是不同执行缺陷的针对性修复。随后完成 exact-class execution-fix 后的本次 formal run3，并由独立 checker 通过 P0 Gate；没有以执行修复名义重跑数值负结果。下文保留 run1/run2 的负证据，同时把 run3 的 measured 结果与其代表性边界单独列出；run3 不等于后续 P1 或 PDE 资格。

## 授权与结论

2026-08-11，用户明确授权：对于已经确认的执行性问题，可以继续做针对性修复并执行修复后的重跑，在后续 Gate 通过后继续完整 PDE 目标。该授权覆盖 Review V9 原 P0 单次 campaign 预算之后的 execution-fix rerun，但不放宽数值、物理、内存或 zero-swap Gate，不允许把数值失败伪装成执行问题重复运行，也不授权新分支、PR、master 或 ordinary default 变更。

| 项目 | 结论 | 分类 |
|---|---|---|
| P0 原始 campaign | stage 启动后受 telemetry lifecycle 竞态终止 | controlled execution stop |
| execution-fix rerun | stage 完成，P0 assembly 在 3600 s timeout | controlled execution stop |
| exact-class formal run3 | worker 完整测量，watchdog/checker 均通过 | PASS / QUALIFIED |
| P0 数值资格 | run3 row-complete representative 通过；仅覆盖代表 class | PASS / QUALIFIED |
| P1 | 未运行 | not_run / ELIGIBLE_UNLOCKED |
| H2B-K normalized two-level coercive solve | 未运行 | locked_by_P1；S0 失败后的 P 路线须先完成 P1 才能返回 K |
| H2D / full-space matrix-free DtN | 未运行 | locked_by_H2B-K |
| H4 time-harmonic PDE | 未运行 | locked_by_H2D |
| official field / RTA | 未运行 | locked_by_H4 full solve + true residual/physics Gate |

## 三次 P0 执行记录

| attempt | source | raw | 实际边界 |
|---|---|---|---|
| 原始 P0 | `d6f7cc4d1cb334a5666545783add7e171da00c52` | `h2b_p0_d6f7cc4_run1` | stage 在 `b0_compile_started` 附近因旧 telemetry policy 终止；online 未启动 |
| execution-fix rerun | `90a9dbbf01ac06abf3417116831d3483b7f37ca8` | `h2b_p0_90a9dbb_run2` | stage 正常完成；P0 assembly 到 timeout；没有数值 summary |
| exact-class formal run3 | `74f566de78b8665b704f5506b3a6072c5ac56bae` | `h2b_p0_74f566d_exactclass_run3` | stage/P0 完成；独立 checker RC0，P0 PASS / QUALIFIED |

### run2 measured evidence

| 阶段/字段 | 实测值 | 含义 |
|---|---:|---|
| stage elapsed | 26.242200638 s | measured |
| stage return code | 0 | measured |
| stage peak process-tree RSS | 1,286,606,848 B | measured；stage peak，不是 PDE peak |
| stage swap | 0 B | measured |
| P0 elapsed | 3600.090414687 s | measured |
| P0 return code | -15 | timeout 后 SIGTERM |
| P0 peak process-tree RSS | 709,206,016 B | measured |
| P0 swap | 0 B | measured |
| termination | `timeout`；SIGTERM 足够、无 SIGKILL | measured |
| process reclaim | 进程全部退出 | measured |
| last marker | `patch_assembly_started` | measured |
| P0 summary | 不存在 | measured absence |

run2 已完成 authority、mesh、space、Floquet、R1 cache hit、R2 factor/class authority、central-cell selection 和 touching discovery；central cell 为 canonical ordinal 3，selected class 为 3，touching cells 为 19。没有生成 P0 matrix/factor/source measurement 的完成记录。

### run2 的 v3 受控失败 compact

对同一 run2 raw 只执行了一次离线 `p0-check`，没有启动 worker、JIT 或 formal。RC=1 是预期的 `gate_failed`，不是 checker 异常；这是把 run2 的受控 timeout 绑定到 raw 的结构化 compact evidence，而不是 P0 数值 PASS。

| 字段 | 值 |
|---|---|
| compact | `benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch_timeout_v3.json` |
| status / pass | `gate_failed` / `false` |
| measurements | `null` |
| problems | `p0_execution_timeout`, `p0_measurements_not_produced` |
| checks | 除 `p0_measurements_formed=false` 外全部 `true` |
| run source | `90a9dbbf01ac06abf3417116831d3483b7f37ca8` |
| checker clean source | `83609f3ac564530ebffea55e3e9e9d0726b33379` |
| file SHA | `14e796543dbd69005077dd8f5d03c964c71c7840c14fdfd445361a05ef124931` |
| embedded evidence SHA | `8d853895e48a1e382d92783fb6eddb165c124a9233222130d5176d284be0b11e` |
| watchdog SHA | `100128aee4a4c013256a27313cd8f9b4565d75479182e969a24eda8300ec8430` |

run source 与 checker source 明确不同且分别绑定。v3 的 `failure_measurements` 只保留真实 stage/P0 elapsed、RSS、swap、return code、timeout、进程退出、progress last marker、source 和 raw artifact hashes；没有伪造 factor、rho 或 solve 字段。v2 compact 仍是旧 checker 的 generic `raw_unreadable` 历史输出，v3 才是绑定 run2 的结构化受控失败证据。

## 重复 tabulation 的根因与窄修复

旧实现对 19 个 touching cells 逐一重新 tabulate curl 与 mass dense tensors。冻结 R2 raw 中 24 个 class factor 步骤约为 191.78–195.89 s，median 约 193.78 s。由旧计时得到的 construction 预测为：

| 口径 | 计算 | derived estimate |
|---|---:|---:|
| 旧逐 cell | `19 × 193.78 s` | 约 3681.82 s，超过 3600 s |
| exact-class reuse | `11 × 193.78 s` | 约 2131.58 s |

这些是由旧计时推导的预测，不是优化后正式实测。run2 的 touching class 序列为：

```text
[6, 8, 14, 3, 5, 13, 3, 3, 3, 5, 2, 3, 2, 2, 7, 4, 1, 4, 0]
```

共有 11 个 unique exact classes。实现的窄修复保持：

- first-seen class 顺序；每个 class 内按 cell ordinal 升序；
- 每个 touching class 只对一个代表 cell tabulate curl/mass 和构造一个 proxy；
- 每个 cell 仍用自己的 `independent_global_rows` 与同 class expansion pattern；
- 每组完成立即释放 dense proxy，最多同时保留一个 proxy；
- 不保留 per-cell dense tensor/cache，不改变 patch 定义、orientation、MPC reduction、action、factor、rho 或物理方程。

implementation commit=`83609f3ac564530ebffea55e3e9e9d0726b33379`，代码与 focused tests 先以 `implemented/tested_only` 收口，随后 run3 才提供正式 P0 qualification。`test297=15 passed`，focused `294–297=91 passed`；这些是实现支撑证据，正式 P0 结论以 run3 worker/raw 与独立 checker 为准。

## 永久 scope 与尚未测量项

| 字段 | 值/状态 |
|---|---|
| discretization / MPI | p6/h10 / MPI1 |
| full-space rows / Floquet identity rows | 173802 / 9210 |
| cells / local nloc | 252 / 882 |
| operator | Review 定义 `B0 = K_curl + k0^2 M_abs_epsilon`；代码含 `(1/mu_r)`，固定配置 `mu_r=1`，数值相同 |
| patch operator | `B_P = R_P B0 R_P^T` |
| condensation / global matrix / Schur / slab / KSP / matrix-free DtN / PDE | false / 0 / not used |
| ordinary default | unchanged |
| P0 factor residual、solve residual、condition/pivot、solve gain | run3 measured；见上表 |
| five-source element/patch `rho_star`、closure | run3 measured；element 对照失败，row-complete official Gate 全过 |
| full-space diagnostic rho/spill | measured as diagnostic only；不属于 P0 Gate |
| P0 online Gate | run3 pass；仅代表性 central patch，不是 PDE Gate |

不能用 H2A-R2 factor store、S0 peak 或 run2 stage/P0 peak 推导 P0 数值资格；尤其不能把 1.286 GB stage 或 709 MB 未完成 P0 peak 当作 MPI1 full PDE 内存。

## Evidence index

| evidence | 路径 | SHA / 状态 |
|---|---|---|
| run2 raw | `benchmarks/artifacts/task037_extra_development/h2b_p0_90a9dbb_run2` | ignored raw，保留不改 |
| run2 watchdog | `.../p0_watchdog_summary.json` | `100128aee4a4c013256a27313cd8f9b4565d75479182e969a24eda8300ec8430` |
| watchdog embedded evidence | 同一 watchdog | `7fc7af8e391bd0b30f0663128376de0c5a35dc9291253baca98043053db2ade4` |
| run2 stage summary | `.../stage_summary.json` | `ee7278fd44288753664827677355500e8101d4090d0600677a292ac98d0e2c9f` |
| run2 P0 progress | `.../p0_progress.jsonl` | `d3ac29e2b32755f47a915d874632cf96dcf066892f4fe2b782b7c4fa0893ed59` |
| run2 P0 timeline | `.../p0_timeline.jsonl` | `a8e1b6dc11b78538edbda49745aac677004d359a9fbcd59e13f44c3b57d4a74f` |
| run2 v3 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch_timeout_v3.json` | file `14e796543dbd69005077dd8f5d03c964c71c7840c14fdfd445361a05ef124931`；embedded `8d853895e48a1e382d92783fb6eddb165c124a9233222130d5176d284be0b11e` |
| run1 watchdog | `benchmarks/artifacts/task037_extra_development/h2b_p0_d6f7cc4_run1/p0_watchdog_summary.json` | `514ae1f01ab6f6dd1126f4b8790c0e47bf69acbae52ff2ebc1e38e2dbeaa60a2` |
| run1 stage progress | `.../stage_progress.jsonl` | `ac2b6278b467d42c469e1c8df2a4daa38a841e60ede9e08202d4c13bc14170f3` |
| run1 stage root PID | `.../stage_root_pid.json` | `9ff92245b304f8b019a3e421c523f1c898bc805f9f7fb1b0efbf9d535d564140` |
| run1 stage stdout | `.../stage_stdout.txt` | `1d5791863505d38408c3bd843e0ad247b4d511892f69b9d007173926cebf3cb5` |
| run1 stage timeline | `.../stage_timeline.jsonl` | `09fe1b0bffd989cb77b5af26a24b63a2344ca5d9c671b79a97fa3c75fb583a4a` |
| v2 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch_v2.json` | `d811b5d5fa834699088b255631a05621b61dbfdb6e150b36850c3eda8944ac3a`；保持原字节 |
| old compact | `.../h2b_row_complete_patch.json` | 同为 `d811b5d5fa834699088b255631a05621b61dbfdb6e150b36850c3eda8944ac3a` |
| old compact embedded evidence | 同一 compact | `52e9251d46b1c6b7353f7975fb0ffa8e15ee63f15ae0691cab216ba980d98f3e` |
| old P0 raw | `benchmarks/artifacts/task037_extra_development/h2b_p0_d6f7cc4_run1` | 负证据，保持不改 |
| run3 raw | `benchmarks/artifacts/task037_extra_development/h2b_p0_74f566d_exactclass_run3` | source `74f566de78b8665b704f5506b3a6072c5ac56bae`；stage/P0 完成 |
| run3 watchdog | `.../p0_watchdog_summary.json` | `53c07461a5eb2800fb77f769c766507fd742aa0a4ca707cb2982cd5a3e5a885d` |
| run3 P0 summary | `.../p0_summary.json` | `fd18a51bce00d7af0797e3e2fb1a0b5fbbccefdf2945b39123fcf037d8855245` |
| run3 progress | `.../p0_progress.jsonl` | `47eab2997f2a7a6a86f284e920dbc295547aecf64fcea35ac9fdbee4cb0d4b64` |
| run3 timeline | `.../p0_timeline.jsonl` | `6ce0653f6298acf2da4b80c98ea75f76a50cf84e7a8c17e2ce65b5f0b52bfc92` |
| run3 stage summary | `.../stage_summary.json` | `ab709222f231131dd68b4a131f75a5bead380eb797f1634c205fb6fba195f874` |
| run3 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch_exactclass_v4.json` | file `2f1862043f9e75002f53230eee86f8c6ee68ac389b319397bd71b3bdd93fc75b`；embedded `11f6a5a00557cf6ad11d4a9413a72283a7fd9ec9a5085a56e74b733538e75d47` |

v2 compact 仍是旧 checker 生成的 generic `raw_unreadable` 输出，不能单独绑定 run2；它作为历史输出保留，不能覆盖旧 compact。v3 compact 已单独绑定 run2，未改写 v2 或旧 compact。

## run3 exact-class formal PASS

run3 是 exact-class execution-fix 后的本次 P0 formal run3，也是该路径的一次正式 attempt。它保持 p6/h10、MPI1、同一 central representative、patch 定义、operator、source 定义和资源 Gate；只改变已审的重复 tabulation 路径。run source 与 checker source 都绑定为 clean SHA `74f566de78b8665b704f5506b3a6072c5ac56bae`。worker `return_code=0`、`status=measurement_complete`；watchdog RC0/status=pass；独立 `p0-check` RC0、`status=pass`、`pass=true`、`problems=[]`，JSON 实际 `checks` 数量为 42，且 42 项全部为 `true`。这 42 项是 checker evidence qualification，不是把未运行的后续阶段写成通过。

| 阶段/字段 | 实测值 | Gate/含义 |
|---|---:|---|
| stage wall | `25.3289132800 s` | watchdog stage 正常完成、RC0；independent stage measurement |
| stage peak process-tree RSS | `1,277,276,160 B` | `<1,500,000,000 B`；不是 PDE peak |
| stage swap | `0 B` | pass |
| P0 online wall | `2366.9756512710 s` | `<3600 s` |
| P0 online peak process-tree RSS | `767,352,832 B` | `<1,500,000,000 B`；不是 PDE peak |
| P0 online swap | `0 B` | pass |
| processes gone | `true` | stage/P0 均正常回收 |
| fixed scope | `252 cells / 173802 rows / 882 nloc / 9210 constraints` | p6/h10, MPI1 |
| selected patch | `central ordinal=3 / class=3 / 19 touching cells` | representative P0 |

### element 与 row-complete patch 的五类 source

P0 official Gate 只看 row-complete `B_P` 的 patch rows；element block 是同一 source、同一 `R_P r` 下的对照。`closure` 是统一 row-complete operator 的 exact-action closure。full-space diagnostic rho/spill 只作诊断，不改变 P0 Gate。阈值为 checkerboard `<=0.70`、mixed `<=0.85`、其余三类 `<=0.95`。

| source | element `rho_star` | row-complete patch `rho_star` | closure | patch Gate |
|---|---:|---:|---:|---|
| gradient-dominated | 0.9728665528326489 | 2.443641000531458e-14 | 2.9170545853584576e-14 | PASS (`<=0.95`) |
| curl-dominated | 0.9745047703319052 | 2.7851705029630627e-14 | 3.747872940054648e-14 | PASS (`<=0.95`) |
| mixed | 0.9731618380561192 | 2.958455252834771e-14 | 3.0414591048074225e-14 | PASS (`<=0.85`) |
| checkerboard/high-frequency | 0.9533514082156586 | 3.1648606985495957e-12 | 2.3554516876773214e-12 | PASS (`<=0.70`) |
| physical-RHS-like | 0.9746781762235208 | 8.874407923550598e-15 | 3.930741982540268e-14 | PASS (`<=0.95`) |

element 的约 `0.953–0.975` 仍未达到对应 Gate；把邻居贡献补齐后的 row-complete patch 五类全部通过。它说明原 single-element operator 的问题是遗漏邻接贡献，而不是把 element factor 当作 official P0 结果。

### patch factor、reuse 与 materialization

| 字段 | 实测值 |
|---|---:|
| factorization residual | `7.886088118436545e-16` |
| solve residual | `3.4228547837843815e-12` |
| factor bytes | `12,450,312 B` |
| reciprocal condition estimate | `1.3534762845123542e-07` |
| condition estimate | `7,388,382.1345291715` |
| pivot growth | `1.2081134295646951` |
| fixed RHS solve gains | `18.855105828569798 / 18.85889387376584` |
| finite / deterministic | `true / true` |
| touching class IDs | `[6, 8, 14, 3, 5, 13, 2, 7, 4, 1, 0]`（11 个） |
| tensor tabulations / reuse | `11 / 8` |
| max live dense proxy | `1` |
| per-cell dense tensors retained | `false` |

streaming 仍按 first-seen class、class 内 cell ordinal 排序；orientation 与 MPC expansion 各施加一次。它只资格化一个 representative class 的 row-complete patch。P1 仍必须验证全部 exact-neighborhood classes、总 factor+metadata `<=500 MB` 和 predicted live set `<=1.7 GB`，不能由本次代表性 P0 外推。

## 停止边界

当前 P0 representative row-complete patch 已 `PASS / QUALIFIED`，因此 P1 为 `not_run / ELIGIBLE_UNLOCKED`。H2B-K 仍 `locked_by_P1`；它必须在 S0 的 P 路线完成 P1 后才可返回。随后 H2D/full-space matrix-free DtN `locked_by_H2B-K`，H4 time-harmonic PDE `locked_by_H2D`，official field/RTA `locked_by_H4 full solve + true residual/physics Gate`。本次没有启动这些阶段，也没有把 P0 结果写成 PDE 结果。

P1 必须覆盖全部 exact-neighborhood classes，并重新验证总 factor+metadata `<=500 MB`、predicted live set `<=1.7 GB`、完整 residual/physics Gate；本次 P0 的 `12,450,312 B` 单 patch factor 和 `767,352,832 B` online peak 不能替代这些测量。长期目标 MPI1 full PDE process-tree RSS 严格低于 `2,000,000,000 B`、swap=0，以及与 direct authority 的物理比较，仍未测量、未达成。若后续出现数值负结果，必须严格走 Review V9 规定分支（包括 §5.4），不能以 execution fix 名义重跑。
