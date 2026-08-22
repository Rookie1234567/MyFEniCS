# Task040 response v1

## 结论

Task040 研究的是能否把两个完整的 exact side factor 换成更小的迭代式 side inverse。
通俗地说，T40-3 先把底部算子分成三个相邻两层子域，在两条人工截面传递边界信息，再看
误差是否下降；只有这个最小传递机制稳定，才有理由继续做 bounded patch、FGMRES 和完整
Hybrid。它不是完整物理求解。

正式 T40-3 到达了算法并自然退出，但结果是受控的真实数值负结果：
`TRANSMISSION_MECHANISM_FAIL`。这不是 implementation failure、watchdog failure 或完整
Hybrid solve failure。

## 身份与证据

| 项目 | 值 |
|---|---|
| branch/source | `codex/20260822-task40-hybrid-side-factor-pc` / `483275dcdfa65fbc578bbee510878f2d065e2429` |
| formal root | `results/task040_level_a_bare_f_mpi8_483275dc` |
| frozen input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| physical SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| MPI / threads | 8 / 1 |
| QEP / PDE | 0 / not_run |
| checker | `python -m benchmarks.check_task040_level_a --run-root results/task040_level_a_bare_f_mpi8_483275dc` |

独立 checker 从 raw reports 和 watchdog/process samples 重算结论，不采信 worker status 或
worker gate。checker execution parent SHA 为 `483275dcdfa65fbc578bbee510878f2d065e2429`；
checker 文件 SHA256 为 `0278e76355cfda3b3cc4d53ee5e1de255598b7c98d69946df04d72f83904b3e5`。
compact record 为
[task040_level_a_bare_f_transmission_v1.json](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_level_a_bare_f_transmission_v1.json)。

## Q1–Q5：Level-A action 与 Gate

T40-3 的六个 source label 与顺序精确通过，physical source/output norm 为 0，故它只提供
zero-map 证据。五个非零 source 的 residual ratio（rho）为：

| source | rho | T40-3 limit | 结果 |
|---|---:|---:|---|
| modal traction positive | 16.512689191540417 | `<1`，preferred `<=0.90` | fail |
| modal traction negative | 14.24201480051629 | `<1`，preferred `<=0.90` | fail |
| external DtN coupling | 22.945123935386228 | `<1`，preferred `<=0.90` | fail |
| fixed random repeat 0 | 28.316064601533686 | `<1`，worst `<=0.95` | fail |
| fixed random repeat 1 | 25.70701839061571 | `<1` | fail |

因此 mandatory、worst、preferred 三层数值 Gate 均失败。定义为：

```math
\rho = \frac{\lVert b-F_s M_s^{-1}b\rVert_2}{\lVert b\rVert_2}.
```

实现身份方面，finite、repeat、linearity、restriction/prolongation、两个人工界面
mass/support、bare-F unchanged 均通过。三个 cross-section factor 为 oracle-only，
ready=3、cleanup 后为 0；full-side/global/nested factor 为 0/0/0。

## Q6–Q8：资源、物理与生命周期

watchdog 为 natural exit、rc=0、swap=0；process-tree peak 为
30,422,945,792 B = 28.333576202392578 GiB，process-sample wall 为
660.6481867840048 s，marker interval 为 658.022411 s，sample_count 为 1311。PSS/USS
没有独立记录，写作 `not_recorded`，没有从 RSS 推算。这个数是 T40-3 component peak，
不是完整 workflow peak，也不是 saving tier。T40-3 没有启动 QEP、PDE solve、top 或 full
Hybrid；释放顺序和 factor 3→0 已记录。

## Q9–Q15：未运行阶段与边界

| 问题范围 | 回答 |
|---|---|
| Q9 bounded patch / local cap | T40-4 `not_run_by_gate`；没有证明 bounded local PC 失败，也没有 `max_local_rows` 结果 |
| Q10 bottom scalable PC / inner FGMRES | T40-5/T40-6 `not_run_by_gate`；没有 checkpoint、inner residual 或 scalable candidate |
| Q11 overlap fallback | T40-7 `not_run_by_gate`；没有调整参数或执行 fallback |
| Q12 bottom/top/full Hybrid | T40-8/T40-9/T40-10/T40-11 `not_run_by_gate`；无新 full residual、R/T/A、recovery 或 workflow peak |
| Q13 h3/scaling | T40-12 `not_run_by_gate`；无 h3、PC exponent 或 0.7 nm 外推 |
| Q14 0.7 nm implication | 当前固定 Level-A 机制不能称 0.7 nm candidate；但没有证明每种 local PC、coarse space 或 Hybrid 都不可行 |
| Q15 stop status | T40-13 closeout；不再运行 T40-4 至 T40-12 |

继承的完整 workflow 参考仍为 direct `93.377006531 GiB`、exact-side iterative
`80.025856018 GiB`。T40-3 的 `28.333576202392578 GiB` 不能建立新的 full-workflow
tier。历史 module-invocation implementation failure root
`results/task040_level_a_bare_f_mpi8_52c88ff3` 保留；`483275dc` 的 package invocation
修复只解决了接线错误，没有改变数值 Gate。

## 复用边界与最终回答

可以候选复用：watchdog 的 package invocation regression、人工界面 support/mass identity
审计、factor owner cleanup 合同。三 cross-section exact factors、固定一阶 impedance
transmission oracle 及本次负结果属于 research-only。不得把 T40-3 action、完整 Hybrid
或 0.7 nm capacity 提升为 production/default。

因此，对“能否在其他 Hybrid 组件不变时稳定替代两个 exact MUMPS side factors”的当前回答
是：在本轮冻结的三组传输机制下，尚未能证明可以；已证实的缺口是 transmission mechanism
的 rho，而不是已证明的 bounded-local-factor 或 coarse-space 不可行。继续研究必须先重新
审议传输机制和所需的全局信息，不能从本次结果无边界扫描参数。

从“exact subdomain solve 仍然得到 rho>1”这一证据，可以把当前缺失的信息类别进一步说
清楚：人工截面上需要跨截面、多个切向模态之间的传播耦合；固定的标量一阶 impedance
不足以表达它。因此当前根因不再只是“local solve 不准”。但这还不能断言必须采用 coarse
space、modal DtN 或某一种具体实现；这些方案在本任务中没有运行，也不能由本次负结果替代。

## 测试与收口

test297 的 serial/MPI2/MPI4 各为 8/8，test298 为 3 passed，test299 为 1 passed；
full repository pytest `not_run`。完整 raw、watchdog timeline 和日志保持在 ignored
results，轻量结果只写入 compact record 与本目录 outcomes。
