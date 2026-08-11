# Task037-extra Review V9 consolidated response

本文件保留并引用 [response_v8.md](response_v8.md)，不改写 V8 已记录的 H2B fixed-unit numeric hard stop、H2A 证据和历史结论。本轮新增的是 H2B-S0 证据、P0 run1/run2 历史受控停止、run3 exact-class formal PASS、P1 execution-fix formal 的第33因子受控停止，以及相应的窄修复测试结果。

## 用户授权与总状态

2026-08-11，用户明确允许：对执行性问题持续做针对性定位、修复和修复后的重跑；在后续数值/物理/资源 Gate 全部通过后继续完整 PDE 目标。这一明确授权覆盖 Review V9 原 P0=1 campaign 之外的 execution-fix rerun，但不放宽任何数值、物理、RSS、swap 或 provenance Gate，也不允许把数值失败包装成执行问题重复运行；不授权新分支、PR、merge/rebase/cherry-pick、force-push、master 或 ordinary default 修改。

## 保留的冻结结论

| 结论 | 状态 |
|---|---|
| G2 LOR-HX | `G2_FAIL` |
| G3 additive LOR-HX | prohibited |
| old G4 sweep with failed LOR-HX | prohibited |
| old H1.2 | `CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED` |
| H1R3.0R / H1R3.1 / H1R3.2 | PASS |
| H2A-R0 / H2A-R1 / H2A-R2 | PASS，但不等于 PDE qualification |
| V8 H2B fixed-unit primary | `FAIL_NUMERIC / NOT_QUALIFIED` |
| ordinary default | unchanged |
| research-only implementation | 不提升为 production numerical candidate |

上述结论继续以 [response_v8.md](response_v8.md) 为历史 authority；本 response 只补充 V9 的 S0/P0 执行边界，不覆盖其原始 evidence。

| 阶段 | 状态 | 结论边界 |
|---|---|---|
| H1R3.0R / H1R3.1 / H1R3.2 | PASS | 保留此前已审 action/identity/scaling evidence |
| H2A-R0 / R1 / R2 | PASS | discovery、JIT hit、constrained factor store；不等于 PDE qualification |
| H2B fixed-unit primary | FAIL_NUMERIC / NOT_QUALIFIED | 详见 `response_v8.md`，不因本轮执行修复改变 |
| H2B-S0 | evidence 可验；direction Gate FAIL | 三组合 valid，但无一组合通过，route=H2B-P |
| H2B-P0 原始 campaign | CONTROLLED_STOP / NOT_QUALIFIED | 旧 telemetry policy 在 stage 中止，online 未启动 |
| H2B-P0 execution-fix rerun | CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED | stage 完成，P0 assembly 超时，未形成数值 summary |
| H2B-P0 exact-class formal run3 | PASS / QUALIFIED | worker/checker 完成，42/42 checks true；仅代表性 central patch |
| P1 | `CONTROLLED_STOP_UNIQUE_FACTOR_LIMIT / NOT_QUALIFIED` | 84-neighborhood campaign 在第33 factor停止；numeric/capacity Gate fail，不再重跑 |
| H2B-K normalized two-level coercive solve | not_run / `locked_by_P1` | S0 失败后的 P 路线须先完成 P1 才能返回 K |
| H2D / full-space matrix-free DtN | not_run / `locked_by_H2B-K` | H2B-K 未完成 |
| H4 time-harmonic PDE | not_run / `locked_by_H2D` | 还须通过 H4 Gate |
| official field / RTA | not_run / `locked_by_H4` | 须完成 H4 full solve，并通过 true residual/physics Gate |

## S0 结论保持不变

S0 compact 的 evidence `status=pass` 只表示 raw 记录可被 checker 验证；`s0_direction_gate_pass=false`，三种组合都没有取得方向资格，正式路线为 H2B-P。不能把 S0 写成算法 PASS。S0 的五类 source、687476736 B whole-campaign peak、swap=0、factor+metadata=201933812 B 和 raw/compact 证据继续以 [h2b_scale_invariant_direction.md](outcomes/h2b_scale_invariant_direction.md) 为准。

## P0 历史受控停止、run3 formal qualification 及最小诊断

P0 的 row-complete patch 只围绕 central cell 的 882 个 independent rows，目标是构造 `B_P = R_P B0 R_P^T`，不是全局矩阵或 PDE。P0 的永久边界保持：uncondensed full-space、condensation=false、global matrix/global constraint matrix/static Schur/trace slab/B2-B4 Krylov/KSP/matrix-free DtN/PDE 均未使用，ordinary default unchanged。

| attempt | source | raw | measured outcome |
|---|---|---|---|
| 原始 P0 | `d6f7cc4d1cb334a5666545783add7e171da00c52` | `h2b_p0_d6f7cc4_run1` | stage 在 `b0_compile_started` 附近被旧 monitor 的单帧 unreadable policy 终止；online 未启动 |
| execution-fix rerun | `90a9dbbf01ac06abf3417116831d3483b7f37ca8` | `h2b_p0_90a9dbb_run2` | stage RC0；P0 在 3600.090414687 s timeout，`p0_summary.json` 缺失 |
| exact-class formal run3 | `74f566de78b8665b704f5506b3a6072c5ac56bae` | `h2b_p0_74f566d_exactclass_run3` | stage/P0 完成；独立 checker RC0，P0 PASS / QUALIFIED |

run2 的实测边界：stage `26.242200638 s`、RC0、peak `1,286,606,848 B`、swap0；P0 elapsed `3600.090414687 s`、RC `-15`、peak `709,206,016 B`、swap0；reason=`timeout`，SIGTERM 足够、无 SIGKILL，进程全部退出。最后 marker 为 `patch_assembly_started`。authority、mesh、space、Floquet、cache、R2 factor/class authority、central cell selection 已完成；central ordinal=3、class=3、touching cells=19。没有生成 P0 factor/rho/solve/patch completion measurement，因此结论是执行 timeout，不是数值算法 FAIL。

### run2 v3 compact：结构化受控失败证据

对同一 run2 raw 只运行了一次轻量离线 checker，RC=1 是预期的 `gate_failed`，不是 checker 异常。v3 compact 的 `pass=false`、`measurements=null`，problems 精确为 `p0_execution_timeout` 与 `p0_measurements_not_produced`；除 `p0_measurements_formed=false` 外所有 checks 均为 `true`。它是 run2 受控失败的合格 compact evidence，不是 P0 数值 PASS。

| 字段 | 值 |
|---|---|
| path | `benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch_timeout_v3.json` |
| run source | `90a9dbbf01ac06abf3417116831d3483b7f37ca8` |
| checker clean source | `83609f3ac564530ebffea55e3e9e9d0726b33379` |
| file SHA | `14e796543dbd69005077dd8f5d03c964c71c7840c14fdfd445361a05ef124931` |
| embedded evidence SHA | `8d853895e48a1e382d92783fb6eddb165c124a9233222130d5176d284be0b11e` |
| watchdog SHA | `100128aee4a4c013256a27313cd8f9b4565d75479182e969a24eda8300ec8430` |
| failure measurements | 仅真实 stage/P0 elapsed、peak、swap、RC、timeout、last marker、source、退出与 raw artifact hashes |

run source 与 checker source 不同且分别绑定；v3 没有 factor/rho/solve 伪造字段。v2 compact 仍保留为旧 generic `raw_unreadable` 历史输出，不能单独证明 run2；v3 才结构化绑定 run2。

### run3 exact-class formal PASS

run3 是用户授权范围内、exact-class execution-fix 后的本次 formal run3，也是该路径的一次正式 attempt。它针对已测得的 per-cell 重复 tabulation；run2 则针对 telemetry race，二者是不同执行缺陷的针对性修复，没有以执行修复名义重跑数值负结果。run3 保持同一 p6/h10、MPI1、central representative、patch/operator/source 定义和资源 Gate；只采用已经审查的 exact-class tensor reuse。run source 与 checker source 都绑定为 clean SHA `74f566de78b8665b704f5506b3a6072c5ac56bae`。worker `return_code=0`、`status=measurement_complete`；watchdog RC0/status=pass；独立 checker RC0、`status=pass`、`pass=true`、`problems=[]`。v4 JSON 实际 `len(checks)=42`，42 项全部为 `true`；这是 checker 对本次 P0 evidence 的资格化，不是后续 P1/PDE 的通过。

| 阶段/字段 | 实测值 | Gate/含义 |
|---|---:|---|
| stage wall | `25.3289132800 s` | watchdog stage 正常完成、RC0；independent stage measurement |
| stage peak process-tree RSS | `1,277,276,160 B` | `<1,500,000,000 B`；不是 PDE peak |
| stage swap | `0 B` | pass |
| P0 online wall | `2366.9756512710 s` | `<3600 s` |
| P0 online peak process-tree RSS | `767,352,832 B` | `<1,500,000,000 B`；不是 PDE peak |
| P0 online swap | `0 B` | pass |
| processes gone | `true` | stage/P0 均回收 |
| scope | `252 cells / 173802 rows / 882 nloc / 9210 constraints` | p6/h10, MPI1 |
| patch selection | `central=3 / class=3 / touching=19` | representative P0 |

P0 official Gate 只判 row-complete `B_P` 的 patch rows；element block 是同一 frozen source 与同一 `R_P r` 的对照。`closure` 是对同一 row-complete operator 的 exact-action closure；full-space diagnostic rho/spill 只作诊断，不进入 P0 Gate。阈值为 checkerboard `<=0.70`、mixed `<=0.85`、其余三类 `<=0.95`。

| source | element `rho_star` | official row-complete patch `rho_star` | closure | patch Gate |
|---|---:|---:|---:|---|
| gradient-dominated | 0.9728665528326489 | 2.443641000531458e-14 | 2.9170545853584576e-14 | PASS (`<=0.95`) |
| curl-dominated | 0.9745047703319052 | 2.7851705029630627e-14 | 3.747872940054648e-14 | PASS (`<=0.95`) |
| mixed | 0.9731618380561192 | 2.958455252834771e-14 | 3.0414591048074225e-14 | PASS (`<=0.85`) |
| checkerboard/high-frequency | 0.9533514082156586 | 3.1648606985495957e-12 | 2.3554516876773214e-12 | PASS (`<=0.70`) |
| physical-RHS-like | 0.9746781762235208 | 8.874407923550598e-15 | 3.930741982540268e-14 | PASS (`<=0.95`) |

element 对照的约 `0.953–0.975` 仍不合格；row-complete patch 五类全部通过。通俗地说，单个 element 的逆只看到自己，遗漏了相邻 touching cells 的贡献；row-complete patch 把邻居项补齐后，局部逆从明显收缩变成接近精确消除。这只证明一个 representative class 的 P0，不是全局 smoother 或 PDE 证明。

| patch factor / reuse 字段 | 实测值 |
|---|---:|
| factorization residual | `7.886088118436545e-16` |
| solve residual | `3.4228547837843815e-12` |
| factor bytes | `12,450,312 B` |
| condition estimate | `7,388,382.1345291715` |
| reciprocal condition estimate | `1.3534762845123542e-07` |
| pivot growth | `1.2081134295646951` |
| fixed RHS solve gains | `18.855105828569798 / 18.85889387376584` |
| finite / deterministic | `true / true` |
| touching classes | `[6, 8, 14, 3, 5, 13, 2, 7, 4, 1, 0]`（11 个） |
| tensor tabulations / reuse | `11 / 8` |
| max live dense proxy / per-cell dense retained | `1 / false` |

P1 原 Gate 要求覆盖全部 exact-neighborhood classes、总 factor+metadata `<=500 MB` 和 predicted live set `<=1.7 GB`；本次已实际推进至 P1，但在第33个 unique factor处触发 numeric/capacity Gate fail，最终 factor payload 与 residual 未形成。不能把本次一个 patch 的 factor 或 online peak 外推为 P1/PDE 资格。

### 最可能的性能边界

旧 P0 producer 对 19 个 touching cells 逐 cell 重新 tabulate curl+mass dense tensor。冻结 R2 raw 的 class factor 步骤约 191.78–195.89 s，median 约 193.78 s；因此 `19×193.78≈3681.82 s`，超过 3600 s。run2 的 class 序列是：

```text
[6, 8, 14, 3, 5, 13, 3, 3, 3, 5, 2, 3, 2, 2, 7, 4, 1, 4, 0]
```

它包含 11 个 unique exact classes；按每 class 只 tabulate 一次，旧计时推导的 construction estimate 为约 `11×193.78≈2131.58 s`。这两个数值都是 derived prediction，不是优化后 formal 实测。raw 支持的根因边界是重复 exact-class tabulation 与 timeout 的时间关系；不能把预测写成修复后的 PASS，也不能把 stage/P0 peak写成 PDE 内存。

### exact-class 修复与 run3 formal qualification

当前代码按 first-seen class 分组、class 内 ordinal 升序；每个 class 只为代表 cell tabulate 一次，随后每个 cell 仍用自己的 `independent_global_rows` 与同 class expansion pattern 累积，组完成即释放 proxy，最多一个 dense proxy 存活。没有改变 patch、orientation、MPC、action、factor、rho 或物理定义，没有 per-cell tensor/cache。

implementation commit=`83609f3ac564530ebffea55e3e9e9d0726b33379`，代码与 focused tests 先以 `implemented/tested_only` 收口，随后 run3 提供了正式 P0 qualification。最终实现测试为 test297 `15 passed`、focused `294–297=91 passed`，compileall、AST duplicate-key、diff-check 均通过；正式 P0 数值结论以 run3 raw 与独立 checker 为准。

## P0 qualification 与长期 PDE 目标

run3 已测得 representative row-complete patch 的 factorization residual `7.886088118436545e-16`、solve residual `3.4228547837843815e-12`、condition estimate `7,388,382.1345291715`、pivot growth `1.2081134295646951`，以及五类 official patch `rho_star` 全部通过。element block 对照的 `0.953–0.975` 仍不合格；这正是为什么 P0 Gate 必须采用包含 touching 邻居贡献的 row-complete operator。run3 的 full-space rho/spill 仍只是 diagnostic，不替代 patch-row Gate。

P0 只资格化一个 central representative（class=3、19 touching cells、11 touching classes），不是全部 neighborhood classes、全局 smoother 或 PDE。P1 原 Gate 要求覆盖全部 exact-neighborhood classes并验证总 factor+metadata `<=500 MB` 与 predicted live set `<=1.7 GB`；本次 P1 已在第33个 unique factor处停止，Gate 未满足，最终 payload/residual 未形成。

用户要求的 MPI1 full PDE process-tree RSS `<2,000,000,000 B`、swap=0 和 direct authority physics comparison，本轮没有运行 PDE、没有 true PDE residual、没有 field/RTA，也没有 direct-method comparison；run3 stage 的 `1,277,276,160 B` 和 online 的 `767,352,832 B` 都不能冒充 full PDE peak。因此 H3/PDE qualification 仍为 none。

## P1 formal：第33个 unique factor 受控停止

### 授权边界与分类

用户在 2026-08-11 明确授权：对具体 execution defect 可以持续定位、窄修、必要时执行修复后的 rerun，并在 Gate 通过后自动推进后续阶段；用户于 2026-08-12 本轮再次明确授权持续处理执行问题直至目标。授权覆盖了初始 P1 anchor false-fail 与 checker 修复，但不放宽数值、物理、RSS、swap、provenance 任何 Gate，也不覆盖当前 P1 数值停止，更不允许把数值负结果包装成 execution fix 重跑。第33个 unique numeric factor 是实际的数值/容量负结果，因此不再重跑。

| P1 记录 | source / raw | status |
|---|---|---|
| initial run1 | `b5f8c2b9a736e532ca51e323644a2279c75063d2`；`h2b_p1_b5f8c2b_run1` | `CONTROLLED_EXECUTION_FAILURE / NOT_QUALIFIED`；per-source `finite` 缺失导致 worker false-fail，不是 numeric fail。stage peak `1,275,670,528 B`、online peak `801,951,744 B`、swap=0；v1 compact 保留。 |
| execution-fix formal | `8a22239347aa6c14b0f487c256138a0bfa54c7dd`；`h2b_p1_8a22239_execution_fix_run1` | `CONTROLLED_STOP_UNIQUE_FACTOR_LIMIT / NOT_QUALIFIED`；anchor 契约通过后，numeric/capacity Gate 在第33 factor失败。 |

P1 formal budget `1 + 1 execution-fix` 已用完。相关提交链为：v1 evidence `b68c0254e4a336104e1f2a616f928dbbda7bc33b`；anchor finite/failure metrics `6d9a76744d6b92483390eaf4d1853614c663acbe`；checker finite/evidence contract `8a22239347aa6c14b0f487c256138a0bfa54c7dd`；progress/provenance checker fix `674cdee63eb03df91b029e4efd929ddc5f17421c`；v3 evidence `61cd6a5b3ccbb9c33c4e00077853500ec1e961ac`。这些提交证明实现/checker contract，不构成 P1 数值通过。

### execution-fix formal 的 measured 结果

| 阶段/字段 | measured 值 | 边界 |
|---|---:|---|
| stage worker elapsed / watchdog wall | `23.850801 s / 24.706280 s` | stage RC0，正常完成 |
| stage peak / swap | `1,276,121,088 B / 0 B` | `<1.5 GB`；不是 PDE peak |
| P1 worker elapsed / watchdog wall | `124.180332 s / 125.042021 s` | worker RC1 的结构化 factor-limit stop |
| P1 peak / swap | `987,938,816 B / 0 B` | `<1.7 GB`、swap=0；不是 PDE peak |
| processes gone | `true` | stage/online 均回收 |
| fixed predicted live set | `1,562,565,932 B` | 余量 `137,434,068 B`；predicted，不是 measured RSS |

authority/discovery 闭合为 84 neighborhoods、252 cells、24 classes、173802 rows、882 nloc、9210 constraints；16 个 R2 class factors 已重构并释放。`p0_anchor_started -> p0_anchor_ready` 证明 worker 的 anchor finite 与 closure `<=1e-11` contract 通过，但 controlled summary 没有保留五个 source 的实际数值，所以五源 rho/closure/finite 必须记录为 `actual values=not_retained`，不能复用 P0 或 R2 数值。

| factor campaign | 实际证据 |
|---|---|
| neighborhoods 0–31 | 32 个 unique factors 已完成 |
| neighborhood 32 | matrix SHA=`3284fdf8334d49a4bd0be2db29c3981020ffe0fd3cc22490f945d4b7cf06093c`；key SHA=`621bbd6d1ec06ce8761ed9bb841632eb89c2c218bf9fbead32a8ff5c3d888914` |
| controlled stop | `unique_numeric_factor_limit`；lower-bound=`33 > limit 32` |
| P1 factor store | manifest 未写；P1 final factor payload、factorization residual、solve residual `not_formed` |

这是精确 numeric SHA ledger 的新矩阵，不能用 tolerance 合并，也不能以冻结 R2 的16 factors替代P1 factor count。Review V9 因此把 P1 关闭为数值/容量负结果；不是 execution failure。

### v1/v2/v3 compact 与 checker provenance

v1 是 initial anchor false-fail 的历史输出。v2 是同一 frozen raw 经旧 checker 的过渡输出：第33因子 numeric stop 已存在，但真实 incomplete-start 序列使 `progress=false`。`674cdee63eb03df91b029e4efd929ddc5f17421c` 只修 checker 状态机/provenance，不改 raw、worker 或数值路径。随后同一 raw 只执行一次 lightweight checker 生成 v3：RC1 为预期的 numeric negative，23/23 checks 全 true，problems 仅 `unique_numeric_factor_limit`。

| compact | file SHA | embedded evidence | status |
|---|---|---|---|
| v1 `h2b_expanded_neighborhood_factor_v1.json` | `80500bcec08a7b45c7088673007dbb8f92c6570875d6ed10a4bc3c6e21cd0724` | 初始 execution-failure evidence | 历史保留，非 numeric fail |
| v2 `h2b_expanded_neighborhood_factor_v2.json` | `39aaa9522ea147c71ed7675cdde357e0931a13a97ed4e689661b07b590f5b374` | `adddd713827f38f87be7e031034b9c73f98de0fd73586f4ad216be2f7e89ffc7` | numeric stop，旧 progress false，永久保留 |
| v3 `h2b_expanded_neighborhood_factor_v3.json` | `2e56bab2a4d2b074bdc8cff4a89a1c23dfe1932c4a0d4bceeff960a7d6eb387f` | `fa64bbc7238f19881e33e4f45827e2740a9ee6aba8742091bcb0ad5dd695b0df` | RC1、`gate_failed`、`pass=false`、23/23 checks true、唯一 problem 为 factor limit |

v3 raw source=`8a22239347aa6c14b0f487c256138a0bfa54c7dd`；checker source=`674cdee63eb03df91b029e4efd929ddc5f17421c`，为另一个 clean SHA，二者没有混称。

| raw artifact | SHA256 |
|---|---|
| `p1_watchdog_summary.json` | `e6007a13151ace5ecc0b3d626ab7f5436a43a8e90e66b8b337edb7b1a8812515` |
| `p1_summary.json` | `30898ef68564dcfd7156c0dead0197861979d89ac09a40a447652ea717014894` |
| `p1_progress.jsonl` | `f0e21c95eb5bc146d3a3acdfc2294f7dcbdad87ab79df4ad5d195fbddab4a861` |
| `p1_timeline.jsonl` | `47e731f39adc21a54c6ca19e4c54b5e08574ceb9761c50df59ca4de2250b7b7b` |
| `stage_summary.json` | `5caf190755af37f72bd86bf66e7ae8fbfc2803b09c2ceebe6c44b66e292d4e29` |
| `stage_progress.jsonl` | `5c634a9ccc31bbf8c941a64a1c104a292fbe50e9b74e3c38611a10359b08a3a6` |
| `stage_timeline.jsonl` | `7c947a25f31ab92d209d84b2a274232bb97f597ab03747f2c6c7c7b11a876507` |
| `p1_stdout.log` | `8a926d1f42e8eb787382d1b71aee2e4683ac6264e109ea6237a273d813db5655` |
| `p1_root_pid.txt` | `0eb4ab1460a30a6f9fff23dc4584681e60ce3c0bb1c7893926dc0371a32c4bc5` |
| `stage_stdout.log` | `b35ee3352239a6e1139bbcd14653434495946c0fca87fcc92d58e685ad6ef1e7` |
| `stage_root_pid.txt` | `aed48de12edc51ffeb4bd492d4db5cfe64aa51113ba2002d8bc5c1a0754f52d2` |

冻结 R2 manifest `1bac2dab37ac19dfa6ab81834327b96e251b1178e0ff652a03347bdd0fa48f98`、R2 compact `2af81d454b89d63e1a5d03916286b527112dd76da34259712e73557918516c9c` 和 P0 v4 compact `2f1862043f9e75002f53230eee86f8c6ee68ac389b319397bd71b3bdd93fc75b` 仅作为 authority 输入，不能填充 P1 未形成的 factor/rho/solve 字段。

### 后续依赖与停止边界

P1 失败后 H2B-K normalized two-level coercive solve 仍 `locked_by_P1`；H2D/full-space matrix-free DtN `locked_by_H2B-K`；H4 time-harmonic PDE `locked_by_H2D`；official field/RTA `locked_by_H4 full solve + true residual/physics Gate`。P1 formal budget 已用完，numeric negative 禁止再跑。Review V9 §5.4 two-cell 未执行，它不提供 P1 factor-count 绕行。

当前 full-space block-factor lane 在 P1 class-count Gate 关闭。若继续，需新的 review 定义有界、证明性的 exact permutation/phase-similarity canonical factor reuse 诊断；失败则转回 geometric MG 审阅。不得原样重跑 P1，不得无界扫描，不得制造 parallel evidence。MPI1 full PDE process-tree RSS `<2,000,000,000 B`、swap=0、direct-authority physics comparison 仍未测量/未达成；没有 PDE、true residual、field、RTA 或 direct comparison。

## Evidence index

| evidence | 路径 / 身份 |
|---|---|
| S0 outcome/compact | [h2b_scale_invariant_direction.md](outcomes/h2b_scale_invariant_direction.md)；compact file `44283799e9712aa8e4355fa31e232ce8b3cbf679867c7fface599f3152054637` |
| 原始 P0 outcome | [h2b_row_complete_patch.md](outcomes/h2b_row_complete_patch.md) |
| run2 raw | `benchmarks/artifacts/task037_extra_development/h2b_p0_90a9dbb_run2` |
| run2 watchdog | `p0_watchdog_summary.json` SHA `100128aee4a4c013256a27313cd8f9b4565d75479182e969a24eda8300ec8430`；embedded `7fc7af8e391bd0b30f0663128376de0c5a35dc9291253baca98043053db2ade4` |
| run2 stage summary | `stage_summary.json` SHA `ee7278fd44288753664827677355500e8101d4090d0600677a292ac98d0e2c9f` |
| run2 progress | `p0_progress.jsonl` SHA `d3ac29e2b32755f47a915d874632cf96dcf066892f4fe2b782b7c4fa0893ed59` |
| run2 timeline | `p0_timeline.jsonl` SHA `a8e1b6dc11b78538edbda49745aac677004d359a9fbcd59e13f44c3b57d4a74f` |
| run2 v3 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch_timeout_v3.json`；file `14e796543dbd69005077dd8f5d03c964c71c7840c14fdfd445361a05ef124931`；embedded `8d853895e48a1e382d92783fb6eddb165c124a9233222130d5176d284be0b11e` |
| run3 raw | `benchmarks/artifacts/task037_extra_development/h2b_p0_74f566d_exactclass_run3`；source `74f566de78b8665b704f5506b3a6072c5ac56bae` |
| run3 watchdog | `p0_watchdog_summary.json` SHA `53c07461a5eb2800fb77f769c766507fd742aa0a4ca707cb2982cd5a3e5a885d` |
| run3 P0 summary | `p0_summary.json` SHA `fd18a51bce00d7af0797e3e2fb1a0b5fbbccefdf2945b39123fcf037d8855245` |
| run3 progress | `p0_progress.jsonl` SHA `47eab2997f2a7a6a86f284e920dbc295547aecf64fcea35ac9fdbee4cb0d4b64` |
| run3 timeline | `p0_timeline.jsonl` SHA `6ce0653f6298acf2da4b80c98ea75f76a50cf84e7a8c17e2ce65b5f0b52bfc92` |
| run3 stage summary | `stage_summary.json` SHA `ab709222f231131dd68b4a131f75a5bead380eb797f1634c205fb6fba195f874` |
| run3 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch_exactclass_v4.json`；file `2f1862043f9e75002f53230eee86f8c6ee68ac389b319397bd71b3bdd93fc75b`；embedded `11f6a5a00557cf6ad11d4a9413a72283a7fd9ec9a5085a56e74b733538e75d47` |
| v2 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch_v2.json`；SHA `d811b5d5fa834699088b255631a05621b61dbfdb6e150b36850c3eda8944ac3a`；byte-for-byte 保留 |
| old compact | `.../h2b_row_complete_patch.json`；同 SHA `d811b5d5fa834699088b255631a05621b61dbfdb6e150b36850c3eda8944ac3a` |
| P1 v1 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_expanded_neighborhood_factor_v1.json`；file SHA `80500bcec08a7b45c7088673007dbb8f92c6570875d6ed10a4bc3c6e21cd0724`；raw source `b5f8c2b9a736e532ca51e323644a2279c75063d2` |
| P1 v2 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_expanded_neighborhood_factor_v2.json`；file SHA `39aaa9522ea147c71ed7675cdde357e0931a13a97ed4e689661b07b590f5b374`；raw source `8a22239347aa6c14b0f487c256138a0bfa54c7dd`；旧 checker 的 progress=false |
| P1 v3 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_expanded_neighborhood_factor_v3.json`；file SHA `2e56bab2a4d2b074bdc8cff4a89a1c23dfe1932c4a0d4bceeff960a7d6eb387f`；embedded `fa64bbc7238f19881e33e4f45827e2740a9ee6aba8742091bcb0ad5dd695b0df`；raw source `8a22239347aa6c14b0f487c256138a0bfa54c7dd`；checker source `674cdee63eb03df91b029e4efd929ddc5f17421c`；23/23 checks true |
| P1 raw | `benchmarks/artifacts/task037_extra_development/h2b_p1_8a22239_execution_fix_run1`；watchdog SHA `e6007a13151ace5ecc0b3d626ab7f5436a43a8e90e66b8b337edb7b1a8812515`；summary SHA `30898ef68564dcfd7156c0dead0197861979d89ac09a40a447652ea717014894` |
| V8 history | [response_v8.md](response_v8.md)，不覆盖 |

## 后续与 selective boundary

| 组别 | 当前判断 |
|---|---|
| H2B P0 code/test | research-only；exact-class implementation/test 已通过，representative P0 run3 已 formal qualification；不提升为 production default |
| S0/P0 compact/raw/docs | 保留 hash-bound 正/负证据，不覆盖旧证据 |
| P1 | `CONTROLLED_STOP_UNIQUE_FACTOR_LIMIT / NOT_QUALIFIED`；第33 factor处 numeric/capacity Gate fail，后续保持 locked |
| H2B-K normalized two-level coercive solve | `not_run / locked_by_P1`；S0 失败后的 P 路线须先完成 P1 才能返回 K |
| H2D / full-space matrix-free DtN | `not_run / locked_by_H2B-K` |
| H4 time-harmonic PDE | `not_run / locked_by_H2D` |
| official field / RTA | `not_run / locked_by_H4`；H4 full solve + true residual/physics Gate |
| ordinary default | unchanged |

在用户 2026-08-11、并于 2026-08-12 本轮再次明确授权下，execution issue 可做窄修并重跑；本轮已从 P0 PASS 实际推进至 P1。P1 的 `1 + 1 execution-fix` 预算已经用尽，并因第33个 unique factor 的 numeric/capacity 负结果停止；不得以 execution-fix 名义再次重跑。若出现其他数值负结果，严格走 Review V9 规定分支（包括 §5.4），不能包装为执行问题。P1 第33因子受控停止后未再启动 formal/heavy，也没有创建 H2D/H4/PDE outcome 或 record。
