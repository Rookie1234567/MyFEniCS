# P1 memory-first small qualification v2

## 先说结论

这里的“memory-first”是先限制内存生命周期：GMRES 每做固定 20 步就销毁本轮 Krylov 基，只保留当前解，再用精确算子重新计算 `b-Ax`，从这个解开始下一轮。这样不会让求解器把越来越长的历史一直留在内存里，但也意味着总迭代数可能变长。

P1 v2 实际完成 9/16 案。8 个 p2 案通过最终显式真残差；p3/h50 MPI1/random 在固定 2000 步后仍为 `0.01027838962263555`，超过 `1e-8`，触发 `FAILED_AT_FIXED_MEMORY_ITERATION_CAP`。这是真实数值 Gate，不是 checker、ABI、生命周期、内存或 swap 失败；后续 7 案与 P2–P7 因此停止。

| 固定合同 | 值 |
|---|---|
| source SHA | `891ef7fba8cb7d154ad9cac61d67652f02063fbb` |
| 方法 | `multiplicative-sequential-v1`；旧 additive-v2 不启用 |
| Krylov | right GMRES，unpreconditioned，`restart=20`，`max_it=2000` |
| residual replacement | 每 20 步；只用 explicit true residual 作正确性权威 |
| hard Gate | final explicit true residual `<=1e-8`，并要求 finite、PC legality、input unchanged、primal constraint |
| campaign | 9 completed = 8 PASS + 1 FAIL；未生成 16 案 aggregate PASS |

## 逐案事实

`final` 是用 `b-Ax` 重算的显式真残差；`rho` 是同一事实的相对值。`one_apply_rho` 仍只是诊断，不是 P1 hard Gate。`cycle RSS` 是每案 cycle ledger 中的 rank-root process-tree 峰值；MPI2 明确不含 launcher。GNU time 的 RSS 是单 worker/launcher 观察，二者不混称。

| case/source | final residual | iters / cycles | matvec / PC | checkpoints | one-apply rho（diagnostic） | cycle RSS | GNU time RSS / wall | swap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| p2-mpi1/random | 1.1143047039371322e-10 | 80 / 4 | 83 / 84 | 0 | 1.7348663090876784 | 138997760 B | 124149760 B / 0:06.63 | 0 |
| p2-mpi1/gradient | 2.400032697598806e-09 | 60 / 3 | 62 / 63 | 0 | 1.9112202119152333 | 139120640 B | 124817408 B / 0:05.26 | 0 |
| p2-mpi1/curl | 8.598540668057664e-11 | 80 / 4 | 83 / 84 | 0 | 1.172610368855703 | 139083776 B | 124616704 B / 0:06.43 | 0 |
| p2-mpi1/checkerboard | 7.629665027029832e-09 | 60 / 3 | 62 / 63 | 0 | 1.887570128672286 | 139116544 B | 124784640 B / 0:08.33 | 0 |
| p2-mpi2/random | 1.0757562911789184e-10 | 80 / 4 | 83 / 84 | 0 | 1.7812101122280801 | 123453440 B | 123400192 B / 0:04.01 | 0 |
| p2-mpi2/gradient | 4.070514353398614e-09 | 60 / 3 | 62 / 63 | 0 | 1.9292755508921247 | 123232256 B | 123236352 B / 0:03.32 | 0 |
| p2-mpi2/curl | 9.798780243058586e-11 | 80 / 4 | 83 / 84 | 0 | 1.169195075350463 | 122937344 B | 123035648 B / 0:06.80 | 0 |
| p2-mpi2/checkerboard | 7.648588208477553e-09 | 60 / 3 | 62 / 63 | 0 | 1.9228690260374444 | 123588608 B | 123502592 B / 0:03.47 | 0 |
| p3-mpi1/random | 0.010278389622635529 | 2000 / 100 | 2099 / 2100 | 10 | 76.31177801908873 | 155860992 B | 140693504 B / 7:10.64 | 0 |

所有 9 案的 worker 都自然退出（rc=0）。8 个 p2 checker rc=0；p3 checker v2 rc=1 且 `contract_errors=[]`，唯一 Gate 是最终 residual。所有已运行案的 PC facts 为 finite、input unchanged、repeat=0、linearity 约 `4e-16`、slave/primal constraint=0、no high-order global AIJ、no global dense transfer、no FE-sized numeric allgather。每个 cycle 的 `ksp_destroyed=true`，cycle 区间连续。

## p3 失败案的 checkpoint 画像

checkpoint 只保存 solution shard 和 provenance，不保存 Krylov basis、action 或 residual vector。p3 案有 10 个真实 checkpoint：`200,400,600,800,1000,1200,1400,1600,1800,2000`。以下是从 raw record 提取的完整标量历史；它显示残差下降，但在固定上限仍远离 `1e-8`。

| iteration | explicit true residual |
|---:|---:|
| 200 | 0.020121591456069118 |
| 400 | 0.017040041972196853 |
| 600 | 0.015105083608221234 |
| 800 | 0.014102818581032258 |
| 1000 | 0.013302270148598451 |
| 1200 | 0.012632596140229997 |
| 1400 | 0.011947247810146767 |
| 1600 | 0.011291414776885363 |
| 1800 | 0.010741673284057653 |
| 2000 | 0.010278389622635529 |

旧 `check.json` 的 SHA 是 `d7d270113aa01aeecadf6edd52a9cd5eae7a31cdc2ac1a71d87967fd4130ccdf`；其中把 400、600 等真实 `checkpoint_facts` 错误要求为固定 `checkpoint_status`，造成 evidence-layer contract errors。修正后的 `check_v2.json` SHA 是 `8702c22a1965a9d776dc10b3bc6135930f8e8cf46c907d1df825ade63753ec5a`，只保留上述真实数值 Gate；record SHA 为 `bb3017db9234c464e55dc6827d0c50d55441c77bb4471cd24a041b1af2f53e4c`。

## p2 MPI pair 的 raw-derived 事实

P1 在 p3 hard stop 后没有运行完整 16 案 aggregate checker，因此下表是从已完成 p2 raw canonical shards 独立重排后得到的 `derived_not_aggregate` 诊断，不冒充 campaign aggregate verdict。`action/rhs` 用同一 RHS key 对齐；动态上界为 `rho_1 + rho_2 + rhs_identity + 1e-11`。

| source | source identity | RHS identity | final action / RHS | dynamic bound | raw-derived bound |
|---|---:|---:|---:|---:|---|
| random | 1.417734557397384e-15 | 1.6029978812022376e-15 | 5.0327071033835924e-11 | 2.2900770250948626e-10 | within bound |
| gradient | 1.6222171816489272e-15 | 9.78406907963663e-16 | 3.0847953901989848e-09 | 6.480548029404328e-09 | within bound |
| curl | 2.042338716606187e-15 | 1.4429255308456253e-15 | 5.928495332369234e-11 | 1.9397465203669334e-10 | within bound |
| checkerboard | 7.0527624724249594e-15 | 2.6435190265449354e-15 | 3.5263665345542788e-09 | 1.528825587902641e-08 | within bound |

这四行不替代缺失的完整 aggregate 文件，也不把尚未运行的 p3 pair 写成通过。全部 record/check 路径与 SHA 见 `outcomes/records/memory_first_small_v2.json`；完整 arrays/checkpoints 仍只在 ignored raw root。

## 停止边界

P1 的失败是 p3 在固定内存生命周期和固定 `restart=20` 下的 p-robust convergence 不足：不能把“仍在下降”外推成 p6/h10 成功，也不能把已通过 p2 的内存观察外推成 `<2 GB` 完整 workflow。P2–P7 因此全部 `not_run_by_gate`；旧 V8 M0、old one-apply FAIL、old 80-step FAIL、additive-v2 CLOSED 和 P0 PASS 均原样保留。
