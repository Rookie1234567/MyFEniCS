# T40/V1/V2/V3 memory–residual–time Pareto boundary

这里的峰值都是 process-tree RSS；它们只在同一阶段、同一资源口径下比较。组件峰值不能
直接代表完整工作流的节省。

## 已测量的组件与继承 baseline

| 路线 | residual / rho | peak RSS GiB | wall | swap | 状态 |
|---|---|---:|---:|---:|---|
| inherited direct full workflow | matched reference | `93.377006531` | inherited | `0` | reference |
| inherited exact-side iterative full workflow | full residual/physics pass | `80.025856018` | inherited | `0` | reference |
| T40-3 Level-A component | worst rho `28.316064601533686` | `28.333576202392578` | `660.6481867840048 s` | `0` | controlled numerical negative |
| V1-1 scalar component | five `r16 >= 0.9` | `27.790115356445312` | `669.4473022361053 s` | `0` | directional negative |
| V1-2 Run B | no numerical rho serialized | `45.05752944946289` | `1485.4694942460628 s` | `0` | resource hard stop |
| V2-A1 packet producer | packet diagnostics only；不作 V2-B residual 结论 | `28.706954956054688` | `1202.5501016210765 s` | `0` | oracle resource target pass |
| V2-B2 projected packet consumer | 五个 `r16 >= 0.9`；32 未授权；preferred checkpoint `null` | `32.453453064` | `1077.3351624270435 s` | `0` | `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT` |
| V3-2 full-span coupled consumer | 五个 `r16 = 0.9706859881–0.9832307912`；32/64 未授权；preferred `null` | `26.118938446045` | `892.680907273083 s` | `0` | `COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL` |

最新 V1-2 root 的 hard stop 是 `48,318,382,080 B`（45 GiB），峰值是
`48,380,153,856 B = 45.05752944946289 GiB`。watchdog 以
`absolute_memory_limit` 终止完整进程组；status 可读、swap 为零、无需 SIGKILL。它没有
产生 full workflow result，也没有建立 V1-2 的 scalar-vs-exact residual、projected rank 或
condition，因此不是新的 accuracy/resource Pareto 点。

PSS/USS 在最新 formal raw 中为 `not_recorded/not_available`，不从 RSS 推算；dedicated
cgroup 不存在，process-tree authority 是唯一 formal peak 口径。Run B 的
`v1_2_exact_oracle_ready` 与 `v1_2_exact_oracle_released` 只说明 exact factor 生命周期的
ready/release 标记，不说明后续对象已从 allocator 或 RSS 中回收。

## Pareto 结论

当前没有新的 full-workflow saving tier。最佳完整工作流参考仍为 `80.025856018 GiB`；
T40-3 的 `28.333576202392578 GiB` 和 V1-1 的 `27.790115356445312 GiB` 是组件，不能与
`93.377006531 GiB` direct workflow 相减后宣称节省比例。V1-2 的 `45.05752944946289 GiB`
是 hard-stop attempt，不是通过的 side PC。

V2-A1 的 `28.706954956054688 GiB` 同样只是独立 packet producer 的诊断/oracle 组件峰值。
V2-B2 consumer 的 raw peak 为 `34,846,629,888 B = 32.453453064 GiB`，process-sample
wall 为 `1077.3351624270435 s`；它完成了资源/身份/remap Gate，但五个 `r16` 均仍不低于
0.9，故没有建立新的 saving tier。producer wall `1202.5501016210765 s` 与 consumer
wall 是两个分进程 component 时间，不能相加冒充完整 workflow 的 cold/reuse 时间。
`max_projected_exact_relative=1.0281892054707484` 只是 producer raw diagnostic，不是
V2-B 数值 Gate。两者都不能与 direct baseline 做节省比例比较。

V3-2 的 `26.118938446045 GiB` 与 `892.680907273083 s` 是同一 MPI8 full-span consumer
组件进程的 process-tree RSS 与 process-sample wall。它在 identity、joint、生命周期和资源
上成立，但五个 full bare-F true residual 仍约 `0.9707–0.9832`，所以不是新的完整 workflow
saving tier，也不能与 producer、V2 consumer 或 inherited full workflow 时间相加。

V3-3 至 V3-7、bounded local patch、bottom/top/both/full Hybrid、h3/0.7 nm 均
`not_run_by_v3_2_numerical_gate`；V1/V2 的历史 `not_run_by_gate` 结论保持不变。因此没有
cold/reuse/full workflow peak、完整 residual-time 曲线或 PC-specific h-scaling。V3-2 的
组件点只能说明本次 mechanism oracle 的资源边界，不能说明 production 或 0.7 nm 可行。

## Review V4-1 metadata-only identity preflight

| 路线 | residual / rho | peak RSS GiB | wall / sample | swap | 状态 |
|---|---|---:|---:|---:|---|
| V4-1 exact-authority metadata preflight | 无 residual；`not_run_by_identity_gate` | 1.643180847167969 | 最后 watchdog sample `9.697888669999884 s`（不是 workflow wall） | 0 | metadata-only identity preflight |

该点只检查原始 JSON、spool 元数据和 watchdog 证据：MPI8、每 rank 1 thread、20/20
authoritative samples，process-tree peak 为 `1764352000 B`，dedicated cgroup swap 为 0。
runner 自身的 resource authority 是 `not_run_by_identity_gate`、sample count 0，因为
system/F/Vec 没有构造。它不是 solver Pareto 点，不能与完整 workflow/direct 的节省比例、
residual 或 wall 直接比较，也不能据此宣称 side inverse 可扩展。
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

## Review V5 Route C 与 Pareto边界

V5 Route C 是一个 metadata/hash-bound 的 current-layout screen，不是完整 workflow saving
tier。独立 checker artifact 为
`results/task040_v5_route_c_teardown_adjudication_b5b765ef/checker.json`，其 SHA256 为
`2db1741dfa0bdb877d1a3f548f66d521ed27328724f1f32d1fbd0b96c49f0a23`。

| 路线 | residual | peak process-tree RSS | wall | swap | 状态 |
|---|---|---:|---:|---:|---|
| V5-2 fresh bare-F authority | one-cell source `1→0`；无 full-side factor-ready、exact packet或bare-F residual | `45432283136 B`（约 `42.31 GiB`） | `21600 s` 窗口耗尽 | authority readable `0` | `FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED` |
| V5 Route C screen | external/fixed-random 的 r64/r128 已测 | `30254075904 B`（约 `28.17 GiB`） | timeline 最后 `13029.23296845 s` | raw observed `0` | `VALID_NEGATIVE_ROUTE_C_NO_SIGNAL_RESOURCE_AUTHORITY_GAP` |

V5-2 的阈值为 preferred `59055800320 B`（55 GiB）、warning `62277025792 B`（58 GiB）、
hard `68719476736 B`（64 GiB）；peak 未越过 hard。五个 current-layout RHS 与
owner-sharded canonical/`Gamma_L`/`Gamma_U` layout 已写出，但 full-side diagnostic factor
只到 `v5_bare_f_factor_setup_begin`，没有 factor-ready，不能把 OS teardown 当作 full-side
factor `1→0`，也没有 residual Pareto 数值。该点是部分完成后的 wall/resource block，不是
数值失败。

Route C raw RSS 低于 `45 GiB` hard line `48318382080 B`，raw observed swap 最大值为 `0`；
但两个中段 live-unreadable rows（5825/5826）使 RSS/swap authority completeness 不成立。
末尾 21296/21297 的 cleanup-complete rows 才按严格 suffix 规则派生排除，故该点不能与
完整 workflow 或 direct baseline 比较节省比例。`dedicated_cgroup_present=false`，不能把
raw dedicated-swap 的 0 写成独立 authority。

没有新的 bottom/top/both/full Hybrid、bounded rank、h3 或 0.7 nm Pareto 点；这些项目均为
`not_run_by_route_c_no_signal_and_resource_authority_gate`。

## V6-2 identity-gate component point

| 路线 | residual / classification | peak process-tree RSS | wall | swap | 状态 |
|---|---|---:|---:|---:|---|
| V6-2 full-interface Schur identity | identity gate negative；exact 未运行 | `27,801,870,336 B`（约 `25.89 GiB`） | `339.7141449260016 s` | `0` | `V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL` |

这是一次 identity-gate component measurement，不是完整 Hybrid workflow、production saving
或 numerical Pareto 点；不得与完整 workflow 峰值相减宣称节省。其 watchdog 为 natural exit，
`616` 个 authoritative samples，hard stop 为 `45 GiB`。
