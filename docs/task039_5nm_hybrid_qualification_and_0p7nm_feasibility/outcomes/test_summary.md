# Task39 T10：测试与检查摘要

本文登记 Task39 已完成的 focused、MPI tiny fixture、静态和文档检查。最终 repository
pytest 按用户于 2026-08-12 的成本覆盖明确取消，状态为 `cancelled / not_run`；不将其写成
通过、zero failures 或 CI 结果。

## 已完成的 focused evidence

| 阶段 | 已有检查/证据 | 状态 |
| --- | --- | --- |
| T1 | Task39 profile、input/provenance、dispatch、adapter 和 ordinary-default focused contracts | `pass`，见已推送 T1 commits 与 `test_268` |
| T2 | A0 compact capacity record、8 个 dat 的 validate/dry-run 与 preflight capacity contract | `pass`，见 [T2 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t2_a0_preflight_v1.json) |
| T3/T4/T5 | 正式运行 raw 的独立 compact evidence 与对应负结果/diagnostic 边界 | 已记录；不是测试替代物 |
| T9 focused closeout | 0.7 nm air-side component generator/test：`test_272` 2 passed；`test_268` 52 passed；`test_26` 14 passed；JSON、链接、Markdown math、Ruff、format、compileall、diff-check pass | `pass`，source `60d2b3caa2bc5ea71be047718eace690e5638d2b` |
| T10 B1 | ABI qualified；Task39 focused `86 passed`；MPI1/2/4 tiny DtN fixture pass；Ruff check、31-file changed-Python format-check、compileall、`check_benchmarks` `302/302`、compact JSON、链接、fenced math、表格列数、diff-check pass | `pass`，code/static parent `b737c62149186356a1c07c267f473e360274cc8a` |

T9 的生成器只读取 tracked dat 和 compact records，没有创建 mesh、组装矩阵、启动
MPI/PDE 或读取 ignored raw。详细分类和容量边界见
[0.7 nm outcome](feasibility_0p7nm.md)。

## T10 结项边界（历史快照）

以下结果如实保留：

| Gate | 状态 | 边界 |
| --- | --- | --- |
| Task-focused final suite | `pass` | focused Task39 suite `86 passed`；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` |
| MPI1/MPI2/MPI4 launcher/ownership contract | `pass` | tiny DtN fixture；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a`；不等同于 T6 numerical lane，T6 仍 `not_run` |
| changed-Python Ruff/format/compileall | `pass` | 31-file scoped format-check、Ruff check、compileall；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` |
| `check_benchmarks.py --no-write` | `pass` | `302/302`；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` |
| repository `python -m pytest -q` | `cancelled / not_run` | 用户于 2026-08-12 为节省时间明确取消；无 zero-failures 或 CI 声明 |
| Markdown/documentation final Gate | `pass` | compact JSON、相对链接、fenced math、表格列数、diff-check |

本任务没有运行完整 0.7 nm PDE，没有恢复 neural/learned factor 路线，没有修改
master，也没有创建其他分支或 worktree。首轮 focused pytest 包装曾丢失 final exit/summary，
随后同一命令以可恢复 session 正式重跑并通过；一次误下发的全目录 Ruff format probe 报告
247 个历史文件需格式化，未批量修改，最终以权威 31-file changed-Python scoped Gate 通过。
上述 T10 B1 代码和静态检查的历史 parent SHA 为
`b737c62149186356a1c07c267f473e360274cc8a`；Review V1 当前代码的最终轻量 Gate
已在 code parent `36c729f7ae197d08f92e044907d0cb723f9fd43c` 上完成。后续最终
docs-only closeout 不再改变 Python、config 或 schema；本 Gate 对应上述已提交内容。

## V4-10 evidence/docs closeout

本轮只起草/更新 evidence、compact record 和 outcomes 文档，不运行 MPI、PDE、QEP 或
新的数值 case。Full repository pytest 明确为 `not_run`，没有 CI 声明。

| 检查 | 结果 | 口径/证据 |
|---|---|---|
| V4 compact records JSON parse | `pass` | 包括新增 h4 iterative record 与 Q-A/Q-B/Q-C/Q-D records |
| raw/compact iterative consistency | `pass` | c2829 formal raw、8c053a98 posthoc、packet/direct SHA 对齐 |
| Markdown links | `pass` | 本轮新增/修改 V4 文档的相对链接存在 |
| fenced math/table contract | `pass` | 本轮没有新增未围栏 display math；表格列数一致 |
| git diff --check | `pass` | docs/record-only diff |
| Python Ruff/format/compileall | `not_run` | 本轮没有 Python 修改；既有代码 Gate 保持原证据 |
| full repository pytest | `not_run` | 成本审阅边界；不是通过或 CI 结果 |

本轮文档引用的 formal evidence 均为既有 ignored raw；没有重跑 Full3D、Hybrid direct、
Hybrid iterative 或 QEP component。iterative formal outer exit=4 在文档中保持为 resource
objective 未满足，posthoc numerical/physics checker pass 作为独立 authority，不改写 raw
exit status。

## E6 Review V1 H-field diagnostic closeout

| 检查/证据 | 状态 | 说明 |
| --- | --- | --- |
| E6 implementation regression | `pass` | `test_273_task039_review_v1_contracts.py` + `test_274_task039_h_field_diagnostic.py`：22 passed |
| changed Python Ruff check/format/compileall/diff-check | `pass` | 仅 E6 序列化修复涉及的两文件；commit `af75d8c73c72cd9340191f7fb332227496e62509` |
| offline Hybrid/Full3D comparison | `pass` | `diagnostic_complete=true`、`numeric_gate_pass=true`；classification=`M480_H_DISCREPANCY_UNRESOLVED` |
| comparison payload identity | `pass` | Hybrid/Full3D payload、metadata 和 output SHA 见 E6 outcome |
| M480 Hybrid direct MPI8 diagnostic rerun | `completed exactly once` | 按 Review 冻结合同执行；最终 compare 消费该次 payload |
| Full3D new solve | `not_run` | 仅进行了既有 canonical replay |
| E7（首轮 T10 snapshot） | `historical not_run` | 首轮 E6 closeout 后停下；Review V1 extension 随后独立完成 E7 |

`pass` 在上表表示实现/离线比较命令成功，不表示 Full3D 或 production validation 成功；
历史 T3–T5 negative/qualification 边界保持不变。

## Review V1 extension checks

| 阶段 | 检查/证据 | 状态 |
| --- | --- | --- |
| E7 family audit | 四档 hash-bound JSON/NPZ、两侧矩阵、finite、sign/order、repeat、backward error | `pass`；family classification=`M960_TRACE_AUTHORITY_NUMERICAL_AUDIT_PASS` |
| E7 M960 direct | own residual、projection、exact traction、canonical online Gate、R/T/A、closure、604 keys、resource | `pass` own authority；`official_record=false` 是 M/model qualification pending |
| E7 offline comparisons | M480-vs-M960 pass；h10/h6 comparison 的 H/model negative 如实保留 | `pass` checker execution；不是 Full3D qualification |
| E8/E9 | Hybrid iterative MPI8/MPI1 | `not_run_by_review_v1_7p3_stop_after_m960_direct` |
| E10 | global RSS/PSS/USS、历史 RSS series、stage attribution boundary | `pass` evidence closeout；stage-aligned snapshots `not_available` |
| repository full pytest | 全仓 `python -m pytest -q` | `cancelled / not_run`；用户成本覆盖，不是 pass |

Review V1 extension 未运行新的 Full3D/Hybrid iterative/0.7 nm PDE；没有开发新 PC、
modal matrix-free 或 neural 路线。详细数值见 [M960 audit](m960_trace_numerical_audit.md)、
[iterative boundary](m480_hybrid_iterative_solver_diagnostic.md) 和
[memory forensics](memory_lifecycle_forensics.md)。

## Review V1 final light Gate

以下是当前 code parent `36c729f7ae197d08f92e044907d0cb723f9fd43c` 上完成的最终轻量
Gate；它们不改写上面的历史 T10 B1 结果。全仓 `python -m pytest -q` 仍按用户成本覆盖为
`cancelled / not_run`。

| 检查 | 结果 | 口径 |
| --- | --- | --- |
| ABI preflight | `pass` | qualified activation；仓库 `.venv`；PETSc complex128/int32；同一 Linux ABI |
| Task39 focused（8 个文件） | `132 passed, 1 skipped` | 当前 code parent `36c729f7ae197d08f92e044907d0cb723f9fd43c` |
| targeted `test_40`/`test_275` | `17 passed, 1 skipped` | 当前 code parent |
| MPI tiny DtN | `MPI1/MPI2/MPI4 pass` | ranks 1/2/4；tiny fixture，不是 PDE |
| official dat validate/dry-run | `26/26 pass` | 13 个 dat × 2；未启动 worker/PDE |
| Ruff check/format-check | `24/24 pass` | 24 个 changed Python |
| compileall | `pass` | `src`、`benchmarks`、`scripts` |
| `check_benchmarks --no-write` | `302/302 pass` | 无写入 |
| compact JSON | `17 parsed` | Task39 records |
| 文档合同 | `7/7 pass` | 相对链接、fenced math、表格列数 |
| `git diff --check` | `pass` | 当前工作树 |

## Review V2 V2-2 formal own-Gate

本轮只收口已完成的唯一 h5 Full3D direct MPI8 formal run及其 compact evidence；没有重新
运行 pytest、MPI fixture 或 PDE；V2-2 closeout 本身没有运行 V2-3，随后 V2-3 已以离线
comparator 完成。

| 检查/证据 | 状态 | 口径 |
| --- | --- | --- |
| h5 formal worker | `pass` | `exit_status=0`、`official_result=true`、true relative residual=`1.1426908495328136e-10` |
| official dtn-port own Gate | `pass` | R/T/A_balance/A_volume、closure、604 keys、E/H、canonical export 均通过 |
| watchdog | `pass` | RSS/PSS/USS=`92491.328/90440.785/90103.539 MiB`；swap=`0`；未跨 warning/critical/hard |
| compact JSON / 文档轻量检查 | `pass` | 本次 V2-2 evidence/docs closeout 的 parse、链接、math/table、benchmark no-write、diff-check |
| Task39 focused pytest / full pytest | `not_run / cancelled` | 本轮未运行；全仓 pytest 延续用户成本覆盖，不声称 zero failures |
| V2-3 comparison | `completed / negative` | 一次离线 h6-vs-h5 comparator；primary 未通过，h5 不称 convergence reference |

完整 machine identity、artifact SHA 和 measured/derived 边界见
[V2-2 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_full3d_direct_v1.json)
与 [h5 direct outcome](full3d_h5_direct_and_convergence.md)。

## Review V2 V2-1 light Gate

以下结果绑定 code/input source commit `c26debf71d2a7b76bcf9b9715412063682b091b0`；不改写此前
T10 B1 的历史测试行。V2-1 没有启动正式 h5 PDE，full repository pytest 仍为
`cancelled / not_run`。

| 检查 | 结果 | 口径 |
| --- | --- | --- |
| ABI / integer / resource preflight | `pass` | complex128/int32；MUMPS 5.6.2；MemAvailable `224.432 GiB`；swap `0`；disk `772.330 GiB` |
| focused `test_263/268/269/273` | `135 passed` | qualified activation；单次 focused suite |
| MPI tiny DtN | `pass` | MPI1 `1`、MPI2 两 rank 各 `1`、MPI4 四 rank 各 `1` |
| h5 validate / dry-run | `2/2 pass` | 604 keys exact；未启动 worker/PDE |
| Ruff check / format-check | `5/5 pass` | c26 修改的 5 个 Python 文件 |
| compileall | `pass` | `src/io src/runners src/test` |
| benchmark / JSON / docs / diff | `302/302 pass`；其余 `pass` | `check_benchmarks --no-write`；JSON、链接/公式/表格检查与 `git diff --check` |

## Review V2 V2-3 offline h6-vs-h5 comparator

本轮只读取既有 h6/h5 raw authority，各调用一次 loader 并执行一次 V2 two-tier comparator；没有
启动 PDE/MPI，也没有调阈值。`primary_pass=false` 是真实科学负结果，不是实现错误。

| 检查 | 结果 | 口径 |
|---|---|---|
| identity / 604 keys / selected coordinates | `pass` | physics-except-mesh exact；两侧 604 unique exact；坐标 exact |
| primary observables / closure | `fail / pass` | R/T/A 四项均超过 `1e-5`；两侧 closure 均小于 `1e-5` |
| selected E/H overall | `fail` | E relative L2=`0.14450862376996956`；H=`0.14701895099975776` |
| primary order / all-604 aggregate | `fail` | 10 primary；weighted power=`0.07101046038911143`；amplitude=`0.3868889801657988` |
| weak / below `1e-8` | `29 fail / 565 counted` | weak 行逐条保留在 compact record；弱通道不单独改变 primary 规则 |
| classification / h5 role | `not_converged` | `FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_AT_P6H5`；`best_available_discrete_authority_only` |

完整 weak rows、实际分母、公式和 artifact identity 见
[V2-3 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h6_h5_two_tier_convergence_v1.json)。

## Review V2 V2-4 readiness light Gate

| 检查 | 结果 | 口径 |
| --- | --- | --- |
| clean SHA / ABI / integer headers | `pass` | source `d4ea422c...`；complex128/int32；MUMPS 5.6.2，NNZ counter int64 |
| h5 Hybrid validate / dry-run | `2/2 pass` | 604 exact；未启动 worker/PDE |
| resource preflight | `pass` | MemAvailable `225.037 GiB`、swap used `0`、disk `808005708 KiB` |
| readiness decision | `conditional launch_eligible=true` | 预测为 derived；runtime factor safety not_established |
| V2-5 formal h5 Hybrid direct | `not_run`（V2-4 historical snapshot） | 随后 V2-5 已完成；当前 own pass 与 V2-6 model fail 见 V2-8 closeout |

### Review V2 V2-8 docs/evidence closeout

本阶段只读取已完成的 V2-7 raw，未运行 PDE/MPI、未修改 Python、未运行 full pytest。
V2-7 的 own numerical result 是真实负结果；以下为本次 compact/docs 收口检查，不是
solver qualification：

| 检查 | 状态 |
| --- | --- |
| V2-7 raw/compact JSON parse | pass; 23 Task39 compact records parsed |
| document link/math/table/control checks | pass; 7 changed/affected documents |
| `check_benchmarks.py --no-write` | pass; 302/302 |
| `git diff --check` | pass |
| Python Ruff/compileall | not_run；本轮无 Python 修改 |
| repository full pytest | cancelled / not_run |

## V6 closeout evidence

本轮只新增 compact JSON 和文档，不修改 Python、不运行 PDE/MPI/heavy。V6 formal raw
由 watchdog 以 22 GiB 绝对硬线受控停止；它不是测试失败计数，也不应被写成 numerical
zero-failure 结果。

| 检查/证据 | 结果 | 口径 |
| --- | --- | --- |
| V6 compact JSON parse | pass | 新增 port-modal record；raw 不入 Git |
| Markdown relative links | pass | 本轮 V6 新 outcome 与 summary/record 链接 |
| fenced math / table columns | pass | 本轮文档合同检查 |
| check_benchmarks.py --no-write | pass，302/302 | qualified activation 下 fresh docs/evidence check |
| git diff --check | pass | docs/record-only diff |
| V6 formal resource | controlled stop | peak 22.025470733642578 GiB > 22 GiB；swap 0 |
| V6 formal numerical probes | not_run | owner-ready/rank64 前停止 |
| focused serial / MPI2 / MPI4 | 沿用 source SHA 52f34262 代码阶段 evidence | 本轮无 Python修改；MPI2 test235 有一次 tmp cleanup warning |
| Ruff / format / compileall | 沿用 source SHA 52f34262 代码阶段 evidence | 本轮无 Python修改 |
| full repository pytest / CI | not_run | 不声称 zero failures 或 CI |

V6 第一轮 aac7e33e 是 right-only packet implementation failure；第二轮 52f34262
才是 resource authority。两者均保留在 compact record 中，不能合并成方法数值失败。

## DQ1 fixed-case qualification closeout

| 检查 | 结果 | 口径 |
| --- | --- | --- |
| Task39 scoped serial suite | 64 passed | test239=15、test241=6、test284=4、test285=39；本轮资格接线相关 serial evidence |
| MPI2 tiny evidence | 2 passed；另 test241 MPI2 attempt 无有效 Gate | test239 compatible fixture=2 passed；test241 受 pre-existing MPIAIJ nonlocal getValues fixture limitation 影响，不能概括为 MPI2 全 pass |
| formal DQ1 MPI8 worker | exit 0 | 5 nm、1°、phi=0、S、p6/h5、M480；数值、recovery、primary Hybrid-direct checker pass |
| parent resource authority | pass | process-tree RSS 51019.37890625 MiB，swap 0，<=69651.3 MiB |
| Ruff / changed-file format-check / compileall / git diff-check | pass | 代码阶段已通过；本 turn 是 docs-only closeout |
| compact JSON / Markdown links / fenced math / table columns / diff-check | fresh pass | 本次 docs/evidence closeout；未运行 Python focused tests 或 PDE |
| repository full pytest | cancelled / not_run | 没有声称 full pytest 通过 |

worker checkpoint 的 final_qualification_status 仍为 pending_parent_resource_gate；最终
case 分类只在 compact record 中由 worker checkpoint 与 parent run_summary 合并得到。
Full3D strict channel 继续保留为 diagnostic pending，旧 B/C/C1/D/E 负结果未被覆盖。

## V5 fixed-budget component evidence

本轮只做 docs/compact-evidence 收口；以下代码阶段证据沿用同一 `ff89f07bc26aecbab6f60f06408c3ab364e9c5f4`，没有因文档修改重跑 Python 或 MPI：

| Gate | 结果 | 边界 |
| --- | --- | --- |
| focused serial / MPI2 / MPI4 | 沿用 ff89 代码阶段已通过的 Task39 focused/tiny evidence | 本轮 docs-only，不重复运行 |
| Ruff / format / compileall | 沿用 ff89 代码阶段通过 | 本轮无 Python 修改 |
| `check_benchmarks --no-write` | fresh `302/302 pass` | 本次 docs/evidence closeout 在 qualified activation 下实际重跑，无写入 |
| fixed-budget setup resource | measured `21.677326202393 GiB <= 59.7638938904 GiB` | numerical stop 后不把 partial run 写成完整 resource qualification |
| mandatory numerical | modal traction +/− fail；external/random `not_run` | fixed-budget family negative |
| full repository pytest | `not_run` | 不伪造 CI/full regression |

raw/marker/ledger 的 hash 与 `status=launching`、`exit_status=null`、`ledger=in_progress` 见 [fixed-budget record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_fixed_budget_side_krylov_component_v1.json)。

## V7 Lane A exact-side full-formal evidence

| Gate | 结果 | 证据边界 |
| --- | --- | --- |
| V7 setup-only advancement (inherited) | prior `f4073ada` measured `81.056903839 GiB <= 84.039305878 GiB` | `SETUP_ADVANCEMENT_PASS_INHERITED` |
| V7 full-formal process-tree resource | measured `80.025856018 GiB <93.377006531 GiB` | `5NM_EXACT_SIDE_LOWER_MEMORY_CASE_RESULT` |
| outer KSP setup-ready | measured `76.937850952 GiB` | state reached；full solve completed |
| swap | `0` | zero-swap pass |
| bottom/top factor lifecycle | outer-ready `1/1`；final `0/0` | release-before-recovery/final cleanup pass |
| packet/QEP release | `true` | qep_calls=0，packet mmap released |
| modal Schur | rank960，condition `24.67720859303036`，matrix/LU repeat `0/0` | single-build + 10 sampled columns |
| outer KSP | `GMRES/restart10`；1 iteration | solve/postsolve pass |
| true residual | reported `3.506501655e-10`；global `2.869197459e-10` | `<=5e-9` |
| recovery/physics/direct checker | pass；Full3D secondary `not_available` | matched h4 direct authority |
| outer/recovery/field/R/T/A | completed | all recorded by raw authority |
| full repository pytest / CI | `not_run` | Review V7 optional；本轮仅做 focused/static，不声称 CI |

详见 [V7 Lane A outcome](v7_exact_side_limit.md) 与
[V7 full-formal compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json)。

## Review V7 final docs/evidence closeout

| 检查 | 结果 | 口径 |
|---|---|---|
| Lane C graph focused serial | `2 passed, 1 skipped, 90 deselected` | qualified activation；layer-graph pure/serial fixture |
| Lane C graph focused MPI2 | `3 passed, 90 deselected` 每 rank | tiny ownership/count fixture；非 PDE |
| Lane C graph focused MPI4 | `3 passed, 90 deselected` 每 rank | tiny ownership/count fixture；非 PDE |
| compact JSON parse/hash | `pass` | Lane B consumer 与 Lane C record；raw hash-bound，raw/results ignored |
| Markdown links/table/fenced math | `pass` | 本轮最终 docs contract |
| `check_benchmarks --no-write` | `302/302 pass` | qualified activation；无写入 |
| `git diff --check` | `pass` | docs-only closeout |
| Ruff / format / compileall | `inherited pass` | 沿用最终代码 SHA 的已通过 evidence；本轮未改 Python |
| focused serial/MPI2/MPI4 code suite | `inherited evidence` | 本轮无代码变化；不重新触发 heavy |
| full repository pytest / CI | `not_run` | 不声称 full pytest 或 CI 通过 |

V7 Lane B 的 producer/consumer 与 Lane C 负结果按 raw authority 分开记录；Lane A full
formal 的 residual/physics pass 也不被 component RSS 取代。首次 implementation failure、V5/V6
负结果均未被重写。

## Review V8-3 closeout checks

| 检查/证据 | 结果 | 口径 |
|---|---|---|
| V8-3 compact record parse/hash | `pass` | 13 个 raw 文件 hash 重算；5 个 method records 与 raw Gate 字段重算；不信 status |
| V8-3 method Gate | `numerical negative by FB4` | J1–FB4 五个 authoritative method records；不是 `sweep_diagnostics_after_cleanup.method` |
| V8-3 resource authority | construction `22.273887634 GiB <=45 GiB`；retained `not_available/not_run` | per-method retained 仅 evidence-only |
| V8-3 raw ledger | `controlled_stop` | 数值 Gate 受控退出，不是 memory termination；parent termination null |
| V8-2 tiny layer-sweep action | `serial 2 passed/1.70 s；MPI2 各 rank 2 passed/0.97 s；MPI4 各 rank 2 passed/1.80 s` | qualified `test_295_task039_layer_block.py`；不含 PDE |
| V8-3 docs/Markdown/table/fence/link | `pass`，12 个 changed Markdown 文件，0.006 s | docs-only Gate |
| `source scripts/activate_myfenics_wsl.sh && python benchmarks/check_benchmarks.py --no-write` | `exit 0；302/302 passed；0.24 s` | qualified WSL；不写 raw、不启动 PDE |
| `git diff --check` | `pass；exit 0` | docs/record-only diff |
| Ruff / format / compileall | `inherited pass; no Python changed` | 本轮不重跑 solver Python |
| repository full pytest / CI | `not_run` | 不声称 CI 或 full pytest |
