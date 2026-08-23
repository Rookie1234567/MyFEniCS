# T40-3 Level-A transmission mechanism oracle

## 结论先行

这个阶段测试的是一个很小但关键的问题：把底部有限元算子 F 分成三个相邻的两层子域，
在人工截面上加固定的一阶切向阻抗，然后按固定顺序来回传递修正。它不是完整 Hybrid
求解，也不是生产预条件器；它只回答这种局部传递机制能否把裸 F 的误差压下来。

正式结果为 `TRANSMISSION_MECHANISM_FAIL`。实现、身份、资源和生命周期证据均通过，但
五个非零源的 rho 都没有通过 T40-3 数值 Gate，因此 T40-4 至 T40-12 按前置条件停止。

## 冻结身份与可复现 checker

| 项目 | 值 |
|---|---|
| source SHA | `483275dcdfa65fbc578bbee510878f2d065e2429` |
| formal raw root | `results/task040_level_a_bare_f_mpi8_483275dc` |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected packet manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| MPI / threads | 8 / 1 |
| QEP / PDE solve | 0 / not_run |

独立 checker 命令为：

    python -m benchmarks.check_task040_level_a --run-root results/task040_level_a_bare_f_mpi8_483275dc

checker 从 worker reports、watchdog summary 和 process samples 重算标签、rho、factor
inventory、swap 与内存 Gate；不采信 worker 的 status 或 gate pass 字段。其
`checker_execution_parent_sha` 是 `483275dcdfa65fbc578bbee510878f2d065e2429`，实际
checker 文件 SHA256 为
`0278e76355cfda3b3cc4d53ee5e1de255598b7c98d69946df04d72f83904b3e5`。compact record
见 [task040_level_a_bare_f_transmission_v1.json](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_level_a_bare_f_transmission_v1.json)。

## 数值 Gate

rho 是“本次局部 action 后剩余的裸 F 残差”相对于源大小的比值；越小越好。正式公式为：

```math
\rho = \frac{\lVert b-F_s M_s^{-1}b\rVert_2}{\lVert b\rVert_2}.
```

| source | source norm | output norm | true residual norm | rho | Gate |
|---|---:|---:|---:|---:|---|
| physical_side_rhs | 0 | 0 | not applicable | zero-map only | pass |
| modal_traction_positive | 5.203888364374479 | 108.73994438408597 | 85.9301911483894 | 16.512689191540417 | fail: `<1`, preferred `<=0.90` |
| modal_traction_negative | 4.617843033490231 | 94.79133013766143 | 65.76738882942891 | 14.24201480051629 | fail: `<1`, preferred `<=0.90` |
| external_dtn_coupling | 107.45953654437675 | 2500.2417874123535 | 2465.67238404989 | 22.945123935386228 | fail: `<1`, preferred `<=0.90` |
| fixed_random_repeat_0 | 363.9322774573049 | 21824.612680713628 | 10305.129879064327 | 28.316064601533686 | fail: `<1`, worst `<=0.95` |
| fixed_random_repeat_1 | 363.33626002091285 | 21699.22330147993 | 9340.291918335137 | 25.70701839061571 | fail: `<1` |

因此 `mandatory_rho`, `worst_rho` 和 `preferred_rho` 全部为 false；不能把结果描述为
“实现正确但算法未调好”，因为冻结算法的正式数值合同本身没有通过。

## 实现、身份与资源证据

| 检查 | 实际结果 |
|---|---|
| six labels/order/finite | pass；physical source/output norm 均为 0 |
| interface mass/support | 两个界面均通过；support identity 完整 |
| bare F unchanged / RP / repeat / linearity | pass |
| factors ready / cleanup | 3 cross-section oracle factors / 0 |
| full-side / global direct / nested KSP | 0 / 0 / 0 |
| oracle-only / scalable candidate | true / false |
| process-tree peak | 30,422,945,792 B = 28.333576202392578 GiB |
| wall | process sample 660.6481867840048 s；marker interval 658.022411 s |
| swap | 0 B |

28.333576202392578 GiB 是一个 T40-3 组件的同时进程树峰值，不是完整 workflow peak，
不能与 93.377006531 GiB 直接 baseline 做 saving tier 宣称。PSS/USS 在这份 raw 中没有
独立记录，故为 `not_recorded`，不从 RSS 推算。

## 停止边界

保留旧的 package-invocation implementation failure root
`results/task040_level_a_bare_f_mpi8_52c88ff3` 及其最小修复 commit `483275dc`。
它不是算法结果。当前正式 root 是真实 transmission numerical negative；不翻转符号、
不扫描 beta、不重跑、不进入 Level B。后续阶段没有产生任何数值结果，详见
[summary](summary.md) 与 [response_v1.md](../response_v1.md)。

## V1-8 Run B 是独立的资源结果

较早的 T40-3 数值负结果仍为 `TRANSMISSION_MECHANISM_FAIL`，五个 rho 不变。后续 V1-2
Run B 不是第二个传输负结果：它到达 exact oracle ready/release (`3 -> 0`)，随后在
`45.05752944946289 GiB`、probe 指标写出前停止。V1-3 setup 已开始但未到 ready，尚无
one-apply/FGMRES 数值；更后续路线为 `not_run_by_gate`。最新证据不能判断 exact/projected
transmission mechanism 是否通过。
