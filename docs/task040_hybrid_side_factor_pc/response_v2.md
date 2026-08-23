# Task040 response v2：V1-8 收口

## 结论先行

本轮 V1 Run B 的唯一正式 MPI8 尝试在 `45 GiB` absolute hard stop 处被 watchdog 终止。
它是 Review V1 §14.1/§16 定义的真实 resource hard stop，不是 implementation failure，
也不是 transmission algebra 的数值失败。exact interface oracle 已记录 factor `3 -> 0`，
但没有产生 `run_summary.json`、per-probe contractions、projected rank/condition 或 Krylov
checkpoint；因此 V1-2 numerical qualification、V1-3 projected screen 和所有后续阶段都不能
宣称通过或失败。

通俗地说，exact oracle 是用来测量人工截面真实响应的临时工具；它成功造好并释放，只证明
这一步的生命周期标记闭合。它不等于后面的 projected transmission 已经作用。PETSc/MPI
对象和内存分配器可能在逻辑对象销毁后仍保留页，随后构造会继续增加 RSS；所以
`factor_count=0` 与操作系统立刻归还内存不是同一件事。

## 身份与 formal 证据

| 项目 | 值 |
|---|---|
| source SHA | `16ecba568be901325e53c3652aa10bb432de5a6b` |
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| MPI / threads | `8 / 1` |
| formal root | `results/task040_v1_2_v1_3_run_b_mpi8_16ecba56` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected packet manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| V1-2 probe manifest SHA256 | `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` |
| exact-spool catalog SHA256 | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| watchdog status | `absolute_memory_limit`; SIGTERM whole process group；SIGKILL not required |
| peak / hard stop | `48,380,153,856 B = 45.05752944946289 GiB` / `48,318,382,080 B = 45 GiB` |
| swap / readability | `0 B / all_status_readable=true` |
| process-sample wall | `1485.4694942460628 s` |
| QEP / PDE | `0 / not_run` |

最新 markers 到达 `system_ready`、两个 artificial-interface mass ready、
`v1_2_exact_oracle_ready(factor_count=3)` 与 `v1_2_exact_oracle_released(factor_count=0)`。
它没有到达 V1-2 gate serialization 或 V1-3 checkpoint。PSS/USS 不在 raw 中，均为
`not_recorded/not_available`，没有从 RSS 推算。

## Review V1 §17 十问

### Q1. Scalar action 的尺度/相位问题还是方向问题？

V1-1 已有独立 scalar screen：五个 `r16` 均至少 `0.9`，scalar optimal correction 的
`rho*` 约为 `0.99895–0.99937`，`alpha` magnitude 约为 `0.00133–0.00219`，phase 约
`-0.0745–0.0464` radians；因此固定 scalar route 被分类为
`SCALAR_TRANSMISSION_DIRECTIONAL_FAIL`。V1-2 本次没有完成 exact-vs-scalar sampled
contractions，所以不能把新的 hard stop解释为尺度、相位或方向的进一步裁决。

### Q2. Fixed right-FGMRES 能否使用 scalar action？

V1-1 的 fixed right-FGMRES screen 已实际运行，但五个 phase-one source 没有达到 Gate，
32 步没有授权。因此它没有成为合格的可复用 preconditioner。V1-2/V1-3 的 projected
替代尚未测量。

### Q3. Lower/upper scalar impedance 与 exact Schur 是否等价？

没有数据可以回答。V1-2 只完成 exact oracle ready/release marker，没有 serialized scalar
与四向 Schur probe、cross-interface contractions 或 `Y^H S Z`。不能用 T40-3 的 rho 或
factor lifecycle 冒充这个比较。

### Q4. Mode span coverage 是否足够？

没有建立。虽然运行 marker 记录了 lower/upper mode count `296/480`，但没有 per-probe
projection、rank、singular values、condition 或 complement data。因此 selected span coverage
与 unseen/complement behavior 均 `not_evaluated`。

### Q5. Projected-exact transmission 是否有效？

V1-3 的 projected transmission setup 已开始，但没有到达
`v1_3_projected_ready` marker，也没有 one-apply 或 FGMRES checkpoint；随后被 resource
hard stop 终止。因此 V1-3 是 `setup_started_but_not_ready /
not_qualified_due_resource_stop`，numerical capacity 为 `NOT_EVALUATED`，不能分类为
`THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT`。

### Q6. Analytic mode-aware route 是否有效？

V1-4 `not_run_by_gate`。没有重建 QEP、没有改变 branch/beta、没有运行 analytic mode-aware
screen，也没有 0.7 nm 推论。

### Q7. Bounded local patch（`max_local_rows <= 1024`）是否可行？

V1-5/Level B `not_run_by_gate`。没有 bounded patch factor inventory、local-row ladder 或
资源/残差 Gate；因此不能说 bounded local PC 失败，也不能说它通过。

### Q8. 最低 bottom RSS、最佳 residual 和时间是什么？

已有组件证据如下：T40-3 component peak `28.333576202392578 GiB`、worst rho
`28.316064601533686`、wall `660.6481867840048 s`；V1-1 scalar component peak
`27.790115356445312 GiB`、五个 `r16 >= 0.9`、wall `669.4473022361053 s`。最新 V1-2
尝试 peak `45.05752944946289 GiB` 后受控停止，没有 residual。所有这些都是 component 或
失败尝试，不是完整 workflow saving tier。

### Q9. 是否建立了新的 full-workflow memory point？

没有。可比较的完整工作流仍是 inherited direct `93.377006531 GiB` 与 exact-side
iterative `80.025856018 GiB`。T40-3/V1-1 的小峰值和 V1-2 的 hard-stop 峰值都不能生成
新的 full-workflow Pareto tier；top、both-side、consumer、full Hybrid 均未运行。

### Q10. 对 0.7 nm，下一 blocker 是什么？

本次 Run B 首先暴露的是资源/生命周期信息缺口：同一进程中 exact oracle 的释放与后续
projection/scalar 构造之间的 RSS/allocator 行为尚未隔离，导致在数值 Gate 前停止。这不能
被解释为 transmission 数学失败。若未来继续，应先获得阶段分进程、持久化 V1-2 packet 或
有证据的 collective heap trim 的独立资源证据。

另有历史但独立的 T40-3 负结果：固定标量一阶 impedance 的 exact-subdomain rho 全部大于 1，
所缺类别可描述为人工截面上的跨截面/多模切向传播耦合信息；这排除了“只是 local solve
不准”作为 T40-3 的充分解释，但不能断言必须使用 coarse、modal DtN 或某一种具体方案。
本 Task40 没有证明局部 bounded PC、coarse space、完整 Hybrid 或 0.7 nm 不可行。

## 失败 root 与后续阶段

| root | source | 分类 | 事实 |
|---|---|---|---|
| `...a3585c44` | `a3585c449f1ae1f9fb439ae905fe727efccb8aa7` | implementation failure | resolved schema 使用了错误的 `counts['bottom']`；保留原始 root |
| `...618c668d` | `618c668d750f228c9eae457c8b69eda5d2cfcfda` | implementation failure | selected manifest SHA 与 exact-spool catalog SHA 混淆；保留原始 root |
| `...16ecba56` | `16ecba568be901325e53c3652aa10bb432de5a6b` | resource hard stop | exact oracle `3 -> 0` 后达到 45 GiB；无数值资格记录 |

V1-3 为 `setup_started_but_not_ready / not_qualified_due_resource_stop`，没有 numerical
capacity 结论；V1-4、V1-5、V1-6、V1-7、Level B、top、full Hybrid 和 h3 scaling 为
`not_run_by_gate`。完整 raw 与 compact record 不删除、不覆盖，见
[resource-stop record](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v1_2_v1_3_run_b_resource_stop_v1.json)。

## 选择性复用边界

| 分组 | 当前结论 |
|---|---|
| reusable candidate | watchdog package invocation、interface support/mass identity、factor owner cleanup，可独立审阅 |
| research-only | cross-section exact oracle、固定一阶 impedance 与 Run B resource evidence |
| do-not-promote | 未资格化 projected route、T40-3 action、完整 Hybrid/0.7 nm capacity claim |

### Checker 与测试口径

正式 checker 命令为：

```text
python -m benchmarks.check_task040_v1_run_b --run-root results/task040_v1_2_v1_3_run_b_mpi8_16ecba56
```

它因 worker 被 watchdog 终止前没有写出 `worker/run_summary.json` 而不能完成完整
numeric schema 重算；这不是把缺失字段补成通过的理由。compact record 记录了 watchdog、
markers、process samples 与 stdout 的 SHA。实现阶段 test297/298/299/300/302/303 及
Ruff/format/compileall/diff/check_benchmarks 的结果保留在
[test summary](outcomes/test_summary.md)；full repository pytest、新 PDE/QEP 和新的 heavy
均 `not_run`。
