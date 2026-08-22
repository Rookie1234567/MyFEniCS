# V5 LA0/LA1 启动受控停止记录

## 结论

本次不是局部线性代数数值失败，而是 formal worker 尚未开始工作就退出了。LA0 的任务原本是抓取 N2 v1 第一个失败的 exact class；LA1 则是在同一 class 上，用固定 RHS 比较当前 packed Cholesky 路径、专用三角求解、直接解和恰好一次 refinement。两者都没有真正运行。

一个“factor”可以通俗理解为把局部矩阵拆成便于解方程的三角矩阵。这里的 Gate 是固定 RHS 解回去后，重新计算 `||B x-b||/||b|| <= 1e-11`。它不是可以事后四舍五入的性能指标。

## 启动事实

| 项目 | 实际值 |
|---|---|
| formal source | `4b9ccbcc411ef529a5a1258cc11bddc691d11b95` |
| case | p6/h10 MPI1 |
| attempt | 1；按 V5 合同不重跑 |
| worker/checker/watchdog rc | 1 / 1 / 1 |
| 实际阶段 | startup；没有到 worker preflight、mesh、class extraction |
| 根因 | 启动命令预先创建了 `raw/markers`，而 `_prepare_paths` 要求 raw、record、marker 路径在 worker 开始时不存在 |
| marker | 只有 watchdog 的 `startup`；worker marker ledger 为空 |
| LA0 reproduction | `not_run`；没有 digest、rows、matrix/RHS |
| LA1 Path | `not_determined`；S0–S3 和矩阵指标均 `not_run` |

因此不能把这次结果写成 `CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE` 的新数值重现，也不能把它写成 LA1 的 Path T/R/P/C/A 或 close。旧 N2 v1 negative 仍保持原样、原 SHA 和原结论。

## 实际测到的资源

watchdog 在 startup 阶段取得 3 个有效 sample：

| 指标 | 值 | 口径 |
|---|---:|---|
| process-tree memory authority peak | `14,446,592 B` | startup process-tree measured，仅表示启动阶段 |
| process-tree swap | `0 B` | startup sample |
| sampled elapsed | `2.0098296020005364 s` | watchdog sample timeline |
| post-setup retained | not run | 没有 setup 对象 |
| LA diagnostic resource pass | false | 不能用 startup peak冒充 LA0/LA1 resource Gate |

worker 自行返回 rc=1；watchdog 没有发送 SIGTERM 或 SIGKILL，随后确认 `already_exited`、process group exited、无 orphan。raw 的 `stop_reason=natural_exit` 只表示 watchdog 没有外部终止；compact 的 `natural_exit=false`，因为 worker rc=1。

## 未测内容与停止边界

没有生成 failed exact-class digest、代表 cell identity、local rows、B/RHS/L 数组，也没有测 Hermitian defect、特征值范围、condition、factorization residual、S0/S1/S2/S3 residual/backward error、pairwise difference 或 decision Path。LA2–LA5、完整 N2 setup、MPI2、N3、N4、T6-F、official physics、T7–T9 和 full 0.7 nm PDE 均未运行。

本次停止不是放宽 Gate 的理由，也不是 production solver 失败。production `_PackedCholesky.solve`、B0、patch、mode、coarse、Gate 和旧 N2 v1 evidence 均未改变。由于 V5 只允许一次 formal attempt，不能用另一次启动来替换这份真实启动层证据。

## 证据索引

| artifact | bytes | SHA-256 |
|---|---:|---|
| ignored worker backfill record | 1,788 | `dfcbfb751c2bbee41f56a2668944e19dd374275f0482280de8eaec3b26aff77b` |
| watchdog raw | 5,113 | `858eab4a3a13218991c9a2c605d3f0bf6298af4962750d4cc45424e912e0e482` |
| watchdog compact | 1,821 | `69de7ed21736ad18488dd998f5bc11d9e9e1695efcc01bd2215a7b3073b38238` |
| independent checker output | 1,121 | `33bfc1b5cb0f9e21073ea30110cdfdaf40625f8ca565f6134efc5b769e3099bd` |
| worker log | 1,553 | `865b1319133ddba30baf7e89b93afe17e87245b10f21294db38648aafc795c2d` |

上述 raw 文件均保留在 ignored 目录：

`benchmarks/artifacts/task038_extra_full3d_n2_la_v1/4b9ccbc/p6_h10_mpi1/`

tracked compact 是
`outcomes/records/n2_local_factor_la_v1.json`，其中明确区分了启动测量、controlled stop 和所有未运行项。
