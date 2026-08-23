# T40/V1/V2 memory–residual–time Pareto boundary

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
它完成了 owner-row packet 和独立 checker 复核，但没有运行 V2-B consumer、projected
transmission 或完整 Hybrid，因此不能建立新的 saving tier，也不能与 direct baseline 做
节省比例比较。`max_projected_exact_relative=1.0281892054707484` 只是 producer raw
diagnostic，不是 V2-B 数值 Gate；V2-B 仍为 `pending`。

V1-4 至 V1-7、Level B、top、full Hybrid 和 h3 scaling 均
`not_run_by_gate`，所以没有 cold/reuse/full workflow peak、完整 residual-time 曲线或
PC-specific h-scaling。下一轮若获授权，先解决 phase-separated lifetime/packet persistence
或有证据的 collective heap trim，再重新建立可比较的资源点；本轮不提出实现。
