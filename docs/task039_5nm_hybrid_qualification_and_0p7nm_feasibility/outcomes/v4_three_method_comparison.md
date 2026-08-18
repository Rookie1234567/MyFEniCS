# V4 三方法比较与最终边界

## 先说明比较口径

这里的“direct”是一次性全局稀疏因子分解；“Hybrid direct”是共享模态 packet 加全局
增广 MUMPS；“Hybrid iterative”是同一 packet 加 matrix-free right FGMRES 和两侧
exact-side 局部因子。三者共享 5 nm、1°、phi=0、S、p6/h4、MPI8 的物理、网格与
external-key identity；只有两条 Hybrid 方法使用并共享同一 M480 selected-mode packet。
Full3D 的 M 和 packet 均为 `N/A`，因此 Full3D 行的 M 记为不适用。

## 结果表

| 方法 | own 数值/物理 | reuse wall (s) | cold wall (s) | peak RSS | 相对 Hybrid direct RSS | 与 Full3D 的状态 |
|---|---|---:|---:|---:|---:|---|
| Full3D direct | `not_completed_timeout_during_factor_setup` | not_run | 21600.036032 watchdog elapsed | 208.315395 GiB | not_comparable | 未完成，不能形成 integrated authority |
| Hybrid direct M480 | own pass | 6771.478625 | 8430.560853 | 93.377006531 GiB | baseline | Full3D integrated `not_available` |
| Hybrid iterative exact-side M480 | numerical/physics pass；resource fail | 12357.484926 | 14016.567154 | 104.334560394 GiB | `-11.734745%` saving | Full3D integrated `not_available` |

表中 wall 和 RSS 均为 measured；cold 包含 1659.082228 s、9.478675842 GiB 的共享
packet preparation，冷启动峰值按串行阶段最大值计算，不把各阶段峰值相加。Hybrid
iterative 比 direct reuse 慢 `82.4932%`，cold 慢 `66.259%`；因此不能把一次 outer
iteration 宣传成高速。

Full3D formal 在 MUMPS setup 阶段运行到 timeout，RSS 为 208.315395 GiB，PSS 约
207.2955 GiB，swap=0；它不是数值失败，但没有 factor-ready、solve、recovery 或
postprocess。用它的 observed stop peak 计算 direct/iterative 少 `55.175177% /
49.915099%` 只能作为诊断下界，不能称为完成的 Full3D 方法间 saving。

## 分阶段内存比较

下表只列已有 process-tree 或明确 lifecycle evidence。Full3D 的峰值是 timeout-stop
peak，不是完成方法的峰值；Hybrid 的 PSS/USS 没有在本次 parent telemetry 中测得。
`max-rank RSS` 是单个 rank 的清理前后观测，不能与 process-tree peak 混用。

| 方法 | 全过程 process-tree RSS / PSS / USS peak | mode-prep peak | solver-process peak | factor-ready peak / marker | post-factor-destroy RSS / marker | recovery peak | final-cleanup RSS / marker | swap |
|---|---|---|---|---|---|---|---|---|
| Full3D direct | RSS `208.315395 GiB`；PSS `207.2955 GiB`；USS `207.1351 GiB`（timeout-stop） | `not_separately_persisted` | `208.315395 GiB`（incomplete/timeout-stop） | `not_reached` | `not_reached` | `not_reached` | `not_reached` | `0 B` |
| Hybrid direct M480 | RSS `93.377006531 GiB`；PSS/USS `not_measured` | `9.478675842 GiB`（packet producer） | `93.377006531 GiB`（consumer process-tree peak） | `88.574321747 GiB` marker-aligned sample（not stage peak） | `20.888683319 GiB` marker-aligned sample（not stage peak）；max-rank cleanup `16535.79296875 -> 2577.9765625 MiB`（补充，非 process-tree） | `not_separately_persisted` | `19.469589233 GiB` marker-aligned sample（not stage peak） | `0` |
| Hybrid iterative exact-side M480 | RSS `104.334560394 GiB`；PSS/USS `not_measured` | `9.478675842 GiB`（共享 packet producer） | `104.334560394 GiB`（consumer process-tree peak） | `not_separately_persisted` | `max-rank RSS 24904.859375 -> 2526.9375 MiB`（非 process-tree） | `not_separately_persisted` | `not_separately_persisted` | `0` |

## 分阶段时间比较

阶段时间保留其原始 clock 语义；没有独立 stage authority 的项不从总 wall 倒推，
也不把 worker clock 与 parent wall 相加。`not_reached` 表示该阶段没有执行，
`not_separately_persisted` 表示执行边界存在但没有独立可审计的阶段时长。

| 方法 | mesh/space | QEP/mode prep | packet write/read | assembly/coupling | factor/setup | linear solve | recovery/postprocess | lifecycle cleanup | cold total | reuse total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full3D direct | `not_separately_persisted` | `not_separately_persisted` | `not_reached` | `not_separately_persisted` | `not_completed；entered KSP setup at ~418.515 s；standalone factor duration not authoritative` | `not_reached` | `not_reached` | `not_reached` | `21600.036032 s`（timeout-stop） | `not_run` |
| Hybrid direct M480 | `not_separately_persisted` | `1659.082228 s`（共享 packet prep，已含 write） | write `1.324 s`；read `0.807076040 s` | local FEM-DtN `387.868237 s`；internal coupling `3194.168900 s` | KSP/setup `3394.103841 s`（含 direct factor） | `1.952535043 s` | field reconstruction `83.353779415 s`；postprocess `not_separately_persisted` | `not_separately_persisted` | `8430.560853 s` | `6771.478625 s` |
| Hybrid iterative exact-side M480 | `not_separately_persisted` | `1659.082228 s`（共享 packet prep） | write `1.324 s`；read `0.759975422 s`；hydrate `0.156106557 s` | `not_separately_persisted` | side factor setup `355.862599 / 363.000956 s`（bottom/top） | `not_separately_persisted` | recovery-physics marker interval `139.376248 s`；postprocess `not_separately_persisted` | `2.127689811 s`（max-rank marker） | `14016.567154 s` | `12357.484926 s` |

`1659.082228 s` 的共享 mode-prep 总时长已经包含 packet write；表中的 `1.324 s`
只是其中的 write 子阶段，不能再次加到 cold total。direct 的 `3394.103841 s` 按
raw 命名为 KSP/setup，包含 direct factor，不是纯 augmented assembly 时长。

## own Gate 与 integrated Gate

| 分类 | 结论 |
|---|---|
| Full3D lifecycle | `FULL3D lifecycle NOT_COMPLETED_TIMEOUT_DURING_FACTOR_SETUP` |
| Hybrid direct | `HYBRID_DIRECT_H4_OWN_PASS` |
| Hybrid iterative numerical/physics | `HYBRID_ITERATIVE_H4_EXACT_SIDE_NUMERICAL_PHYSICS_PASS_RESOURCE_FAIL` |
| Hybrid h4 integrated against Full3D | `HYBRID_H4_INTEGRATED_PHYSICS_NOT_AVAILABLE_FULL3D_INCOMPLETE` |
| 三方法资源比较 | `THREE_METHOD_RESOURCE_COMPARISON_NOT_COMPLETE` |

Hybrid iterative 与 Hybrid direct 的 R/T/A/A_volume 绝对差约为
`1.50e-12 / 1.15e-14 / 1.51e-12 / 3.33e-13`；selected E/H、normal flux、
power-weighted channel 和四类 canonical comparison 均通过 posthoc checker。600 个
external keys 的集合和 hash exact。由于 Full3D 没有完成同网格解，不能把这组 direct/
iterative 对照升级为“三方法完整比较”。

## 内存解释

Q-A 已证明 shared packet 的四组 M480 mode-major owner-row payload 只有
`356,505,600 B = 0.332022 GiB` 左右；这不是 93–104 GiB solver 主峰，也不能用 Q-D
的 M240/320/400 payload 线性 proxy 代替 RSS。Hybrid iterative 的 resource failure
来自实际 method-specific process-tree RSS 高于 direct baseline，不是 packet 本身复制
导致的可直接推断结论。

## 证据入口

- [Full3D h4 lifecycle](v4_full3d_h4_lifecycle.md)
- [Hybrid direct lifecycle](v4_hybrid_direct_h4_lifecycle.md)
- [Hybrid iterative lifecycle](v4_hybrid_iterative_h4_exact_side.md)
- [iterative compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_h4_hybrid_iterative_exact_side_v1.json)
- [Q-A/Q-B/Q-C/Q-D memory study and record index](v4_qep_m_memory_study.md)
