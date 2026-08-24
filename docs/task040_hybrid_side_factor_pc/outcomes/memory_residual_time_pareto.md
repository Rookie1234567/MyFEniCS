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
