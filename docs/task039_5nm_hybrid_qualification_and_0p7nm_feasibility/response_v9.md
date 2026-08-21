# Task039 Review V8 最终回应（V8-0～V8-3）

## 1. 结论

V8-0 inherited audit 已完成；V8-1 六层 block operator reconstruction 通过真实 local-F action/graph
Gate；V8-3 bottom layer-sweep 组件完成了五个固定候选的数值评估，但到 FB4 仍未通过 source-family
数值 Gate。因此本轮是“内存构造可行、底层 action 数值容量不足”的受控负结果，不是资源越线。

| 阶段 | 状态 | 关键事实 |
|---|---|---|
| V8-0 inherited audit | completed | 继承 V7 full/component 边界，ordinary defaults/master unchanged |
| V8-1 layer block operator | `PASS` | 六层、132300 rows、105038640 NNZ、long-range 0、half-bandwidth 1；独立 graph/action evidence |
| V8-2 fixed six-layer factors/actions | `completed` | `test_295` serial `2 passed/1.70 s`；MPI2 各 rank `2 passed/0.97 s`；MPI4 各 rank `2 passed/1.80 s`；同一六因子集依次审计 J1/F1/FB1/FB2/FB4 |
| V8-3 bottom sweep | `LAYER_SWEEP_NUMERICAL_LIMIT_NOT_REACHED_BY_FB4` | J1/F1/FB1/FB2/FB4 均未达到 frozen numerical Gate |
| V8-4 top | `not_run` | bottom Gate 未通过 |
| V8-4 both-side setup | `not_run` | top 未运行 |
| V8-4 full formal | `not_run` | 没有 eligible preferred bottom action |
| V8-5 matrix-free K | `not_run` | bottom numeric Gate 未通过 |
| 0.7 nm PDE / new Full3D | `not_run` | 本轮禁止启动 |

## 2. V8-3 formal identity and resource authority

| 字段 | 值 |
|---|---|
| source SHA | `c3c84a8d2538f6e534aac65fd7da94f1b51d4d83` |
| schema/profile | `task039.v8.h4.layer_sweep.bottom_component.v1` |
| method | `task039_v8_h4_layer_sweep_bottom` |
| input | 5 nm / 1° / phi0 / S / p6h4 / M480 / MPI8 |
| run root | `results/task039_v8_h4_layer_sweep_bottom_component_mpi8_c3c84a8d` |
| exit | worker exit 3；finished；parent termination null |
| parent hard stop | `48318382080 B =45 GiB` |
| overall construction | `23916404736 B =22.273887634 GiB <=45 GiB`，measured/pass |
| overall retained | `not_available/not_run`；preferred rehydration未发生 |
| swap | `0` |
| factors | layer ready `6` → final `0`；full-side/global direct `0/0` |

worker ledger 的 `controlled_stop` 与 exit3 是 numerical Gate negative 的受控退出，不是资源 stop。
run_summary 的 generic `task039_memory_budget=224000000000 B` 是历史通用 ledger，不是 V8 hard-stop authority；
V8 只接受上述 45 GiB nested resource authority。generic run_id 中的 `v4` 也不改变 route identity，
身份由 schema/profile/method/source SHA 绑定。

## 3. 五个候选的具体 Gate

| method | setup/apply s | K rank / condition | worst mandatory residual（`<=1e-2`） | preferred modal/external max（`<=1e-3`） | max repeat / linearity（各 `<=1e-10`） | 结论 |
|---|---:|---:|---:|---:|---:|---|
| J1 | 74.049002075 / 4.768835524 | 296 / 63.94325058975744 | 45.24747348981373 | 34.24246487175865 | 2.1517e-13 / 2.3087e-13 | residual fail |
| F1 | 82.200138326 / 5.133227528 | 296 / 63.94325058975718 | 141.532433583195 | 137.9502681252083 | 1.7451e-10 / 1.2509e-10 | repeat/linearity/residual fail |
| FB1 | 159.145945567 / 9.839546085 | 296 / 19096010.927585065 | 1244.7282511892267 | 1244.7282511892267 | 5.1217e-09 / 5.0354e-09 | repeat/linearity/residual fail |
| FB2 | 337.447901805 / 20.597998448 | 296 / 7847304509017.3955 | 52831.65459906019 | 52831.65459906019 | 2.1347e-04 / 2.0448e-04 | repeat/linearity/residual fail |
| FB4 | 696.156728291 / 42.186354544 | 55 / 3.1808907871836678e25 | 2025057925864.6484 | 1147917207920.235 | 1.8963 / 3.2920 | repeat/linearity/residual fail |

J1 仅 finite/repeat/linearity 通过；F1、FB1、FB2、FB4 的 repeat、linearity 和 residual 均未通过。
五个候选严格串行，between-method Woodbury destroy 和 collective cleanup 均完成。raw
`lifecycle.sweep_diagnostics_after_cleanup.method=FB1` 不是最后方法身份，而是对象默认字段；权威方法来自
`method_records`/markers。per-method retained interval 只用于 evidence-only 比较，不能代替 overall retained。

## 4. V7 inherited Pareto 与 memory tradeoff

V7 matched direct 为 `93.377006531 GiB`；Lane A full formal 为 `80.025856018 GiB`、1 iter、
节省 `14.298113646%`，是目前唯一完成并通过 full workflow 的低于 direct 结果；通过 5% tier，未达到 20% tier。
V7 Lane A setup measured `81.056903839 GiB`，`84.039305878 GiB` 是 advancement threshold，不是 measured
peak。V8-3 的 22.273887634 GiB 是 component construction peak，不能写成 full-workflow saving。

direct inherited `worker_total=7131.113596 s` 与 Lane A parent/observed elapsed `10126.231902 s` 不是同一
计时 authority；`+2995.118306 s / +42.0007%` 只是 derived comparison，不是 strict performance qualification。
V8-3 因 bottom numerical fail 没有 full wall/iteration tradeoff，不能推测。

详细表：[V8 memory–residual–time Pareto](outcomes/v8_memory_residual_time_pareto.md)。

## 5. 证据与保留边界

compact record：[task039_v8_layer_sweep_bottom_v1.json](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v8_layer_sweep_bottom_v1.json)。
raw 只保留在 ignored local path，不提交任何 `.jsonl`、worker stdout、factor 或大型数组。
V8-1 outcome 见 [layer block operator](outcomes/v8_layer_block_operator.md)，V8-3 outcome 见
[bottom sweep](outcomes/v8_layer_sweep_bottom.md)。V5/V6/V7 implementation failures 与负结果均保留。

## 6. 测试与选择性合入边界

| 类别 | 本轮状态 |
|---|---|
| compact JSON parse/hash/checker | `pass`；13 raw hashes、5 method records、资源/数值 Gate 从 raw 重算 |
| Markdown links/table/fenced math | `pass`；12 changed Markdown files，relative links/table columns/fences 全部通过 |
| `check_benchmarks --no-write` | `exit 0；302/302 passed；0.24 s` |
| Ruff/format/compileall | `pass`；V8-2 code-stage qualified evidence，本轮无 Python 修改 |
| full repository pytest / CI | `not_run`；不声称 CI |

建议合入分组：V8-1 layer-block core/测试与 V8-3 route/测试需分别审查；compact evidence/docs 仅作为
research record；V8-3 numerical negative 不提升为 ordinary/default solver。ordinary defaults unchanged，
master untouched。禁止 top/both/full、matrix-free K、0.7 nm PDE、第三 BLR、普通 ILU/budget sweep、h5 rerun。
