# V2-7：h5 Hybrid iterative M480 MPI8 诊断

## 结论

这次运行只回答一个窄问题：在冻结的 h5/M480 Hybrid 方程上，右侧 FGMRES 能否在
6000 步内达到五项真残差门槛。它不是新的物理资格运行。用户覆盖将本阶段标为
`overridden_by_user_for_diagnostic_only`，因此即使资源较低，也不能把结果升级为
Hybrid physical authority。

正式结论为：

```text
H5_M480_HYBRID_ITERATIVE_SOLVER_FAIL
```

失败原因是 `DIVERGED_MAX_IT`，不是内存、swap、launcher/session 丢失或参数切换。
原运行自然结束，未发送终止信号，未重跑。

## 运行身份与证据

| 项目 | 实际值 | 口径 |
| --- | --- | --- |
| source commit | `be5be4680065268303070bfb10c29f4511d483eb` | 旧 raw 的运行源码；早于 telemetry 修复 |
| current pushed patch | `29ead2cda47a88bd312913a6101826eaba977f9b` | 已推送；本次旧 raw 未使用 |
| input / physical / resolved SHA | `073f7292...3dcda` / `e35907c7...46cdb` / `5be93719...84ab4` | manifest/resolved binding |
| method / mesh / M / MPI | `hybrid_iterative / p6-h5 / 480 / 8` | frozen profile |
| external inventory | `604` manifest keys | 有身份清单；没有有效 recovery 输出 |
| raw directory | [20260814T134138.138043Z](../../../results/task039_5nm_hybrid_iterative_m480_candidate/task039_5nm_hybrid_iterative_p6h5_m480_mpi8__hybrid_iterative__mpi8__M480/20260814T134138.138043Z) | ignored raw；实际目录名含 `task039_5nm_` |
| compact evidence | [V2-7 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_iterative_m480_v1.json) | hash-bound 摘要 |

`run_manifest.json`、`run_summary.json`、`resolved_config.json`、`online_record.json`、
stdout 和 stage marker 的完整 SHA/bytes 见 compact record；不把 4.16 MB online record
复制进 Git。

## 数值 Gate

迭代法每一步都在改进线性方程的近似解；真残差衡量当前近似解离方程还有多远。
这里 modal 子问题残差很小，但 FE/interface 相关残差仍接近 1，因此不能把局部代数
成功误读为整个 Hybrid 方程成功。

| Gate | actual | limit | status |
| --- | ---: | ---: | --- |
| reason / iterations | `DIVERGED_MAX_IT` / `6000` | `iterations <= 6000` 且 reason > 0 | fail |
| reported relative residual | `0.9679803825849653` | `<=5e-9` | fail |
| global true residual | `0.9679803825849654` | `<=5e-9` | fail |
| bottom true residual | `0.9882585935946882` | `<=5e-9` | fail |
| top true residual | `0.9641613365401176` | `<=5e-9` | fail |
| modal true residual | `4.861832264924273e-12` | `<=5e-9` | pass |
| interface projection | not_available | `<=1e-8` | fail-closed |
| exact traction, external q | not_available | `<=1e-8`, `<=1e-10` | fail-closed |
| R/T/A/A_volume, closure | not_available | finite, `abs(closure)<=1e-5` | fail-closed |
| recovery / own physics | not_entered | pass required | fail-closed |
| selected E/H and canonical active/full | not_available | complete finite | fail-closed |

因此没有合法的 iterative field、R/T/A 或 closure 可以与 direct 比较；V2-8 不伪造
iterative-vs-direct physics comparator 结果。

## 资源与生命周期

| 指标 | measured |
| --- | ---: |
| process-tree RSS peak | `83155.31640625 MiB` |
| independent PSS / USS peak | `82055.1220703125 / 81869.0 MiB` |
| swap | `0 MiB` |
| samples / complete smaps | `47810 / 47809` |
| warning / critical crossing | `false / false` |
| absolute hard stop | `224000000000 bytes`；未触发 |
| effective hard display | `208.6162567138672 GiB` |
| observed stage markers | `setup`, `solve` only；2/18 |
| outer wall | `17187.881117 s` |
| linear solve timer | `14358.243030897 s` |
| recovery | not_entered |

资源峰值低于 h5 Hybrid direct 的 measured RSS `86744.54296875 MiB`，差值
`3589.2265625 MiB`，相对节省 `4.1376972771%`。这只是一项失败数值运行的资源对照，
小于 Review 的 meaningful-saving 20% 分类线，不能构成资格收益。

旧 raw 没有 `process_tree_samples.jsonl` 或 `memory_object_ledger.json`；这是因为该运行
绑定旧 source `be5...`，不能反向否定已推送的 `29ead2cd` 接线修复。已有
`memory_stages.jsonl` 只有 setup/solve 两行；缺失阶段不补写、不伪造。

## 线性系统身份

| 项目 | 实际值 |
| --- | ---: |
| operator | exact monolithic matrix-free Hybrid |
| global size | `104640` |
| modal count | `960` |
| global A materialized / bottom-top A assembled | `false / false` |
| bottom/top direct factors | `0 / 0` |
| bottom/top fixed ILU factors | `1 / 1` |
| nested local KSP | `false` |
| modal Schur condition | `2601651.7564810147` |
| bottom/top K condition | `19.5832 / 372.1533` |

没有证据表明发生 direct fallback；运行在 recovery 前停止。不得把固定 ILU 的存在
写成 direct factor 成功。

## V2-6 与最终边界

V2-6 仍保持：`H5_M480_HYBRID_MODEL_FAIL`。9 个 primary 通道中 5 个失败，最坏为
`top(-4,0,s)`：power relative `0.0506995`、complex amplitude relative `0.1525935`，
限值均为 `1e-3`；weak 集 30 个中 29 个失败。all-604 weighted power aggregate
`8.685769e-5 <= 1e-4`，但不能抵消 primary failure。用户只覆盖了继续 V2-7 诊断，
没有覆盖物理资格。

因此 h5 Hybrid physical qualification、Hybrid-vs-Full3D qualification、iterative-vs-direct
physics comparison 均未建立；不进入 MPI1、M960、M>480、新 PC 或 0.7 nm PDE。
