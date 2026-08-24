# V11 S1：全局 LOR 结构与谱审计

## 结论先看

这一步回答的是一个很具体的问题：把高阶正定算子拉回到低阶独立边自由度后，两个算子是否在同一组全局坐标中具有一致的代数结构。审计通过了 p2 和 p3 的结构、转移、Hermitian、正定性和端点特征值检查，因此按 V11 只允许进入 S2。

这不是求解器或 PDE 的通过证明。S1 没有运行 p6/h10，也没有验证物理散射结果、2 GB 完整流程或 geometric multigrid；它只证明了下一阶段可以测量 p6/h10 的基础内存。

| 项目 | 本轮事实 |
|---|---|
| formal source | `d19848e6f5484835a84186d13e349ae30fc8d56d` |
| 分支 | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| 案例 | p2/h50 MPI1、p3/h50 MPI1，source=`random` |
| 方法 | audit-only assembled positive `B_H`、sparse independent transfer `L`、independent `B_L`、`A_pull=L^H B_H L` |
| worker/checker | worker rc=0；独立 checker `passed=true`，`contract_errors=[]`，`gate_failures=[]` |
| 后续边界 | 仅授权进入 S2；不等于 solver/PDE/physical PASS |

## 冻结的旧结论

本 S1 不改变旧证据，也没有把任何负结果重分类。旧 Q0、foundation-E、旧 global spectral 审计以及 HX/PCGAMG 路线的关闭结论仍按各自 response/review 生效。

| 冻结证据 | 事实与边界 | 原始/compact 入口 |
|---|---|---|
| V10 Q0 Reference E | 500 步 `rho=4.2034233790900783e-4 > 1e-8`，永久 negative | `outcomes/records/p3_exact_reference_triage_v1.json`；SHA `2d767143ce3b28ac9a4b45962faf370770e1e637f05b4f0b62bb279fe7f6ca82` |
| foundation-E | p3/h50 MPI1 random、exact LOR edge、3020 步 `9.260562270838936e-9`，已 PASS；本轮没有运行 Reference N | `outcomes/records/p3_exact_edge_foundation_10000_v1_checker_v2.json`；SHA `b42675cc9b3d6729f18c1ae744742fefbfe312ded30b5db2ada098664db98525` |
| 旧 global spectral audit | smallest GHEP 固定 500 次不收敛，仍是历史 negative；不被本 S1 覆盖 | `outcomes/records/p3_global_lor_spectral_audit_v1_failure.json`；watchdog compact SHA `55e2ae1299eace079aaf943422acd912052b869d5eaaaa147a88c9ad3142b9c3`，raw SHA `f06ccf3a825bd2ecc4b2446a069209b2222227d676f551743e42099c05963450` |
| HX/PCGAMG 关闭边界 | 旧 L2 one-apply、旧 80-step performance、additive-v2 关闭和 V8/V9 hard stop 原样保留；S1 没有接入这些 production 路径 | `response_v8.md`、`response_v9.md` 及其 outcomes |

## 三次失败尝试的不可变关系

这些是同一 S1 harness 在最终 d198 PASS 前的真实执行事实。它们分别属于执行前实现错误、命令 provenance 序列化错误和 watchdog 终止竞态；都不应被解释成数值方法通过，也没有被删除或覆盖。

| source / 分类 | raw root（保留原处） | 关键证据哈希 |
|---|---|---|
| `d7a1c420c9f2c5352c10a94b559e804a400548e6`：record 前 `NameError: HIGH_ACTION_LIMIT is not defined` | `benchmarks/artifacts/task038_extra_full3d_lor_global_spectral_audit_v2/d7a1c420c9f2c5352c10a94b559e804a400548e6/s1-batch` | watchdog raw `b898d15ebc1b2f2d142846c2a95b43eec7de1e4ac013d2f2989ffa5f583ce78b`；compact `2c3e278e547962f477c19a14d8b19355d65fc4dbcc017caee86feffab7a2456c`；log `e57c13159e04ddafb5ef60e68b7ca3c49137a6cbdb8df47ef6bf79d7c894d633`；marker `44d628f84061316c8cd0d8f5abd4777437459fa46cd78e77ad7abb8bf06ec968` |
| `a5772ab8f23dad500c4311f990f5e3dda88ef8f3`：worker command provenance serialization negative | `benchmarks/artifacts/task038_extra_full3d_lor_global_spectral_audit_v2/a5772ab8f23dad500c4311f990f5e3dda88ef8f3/s1-batch` | immutable record `42d2fdf32adcd2ab9647f6881faf9b70b292a64e13ce1ee3cdc4265f3e9bbb14`；checker `43720f3056f87c861baf59b363f2f710c0d66be68a5846a0982b598b487b1ddd`；watchdog raw `9025971aa840380118b2920fdcdae0990bda329bbe6f91f6cc0e0441d78101af`；compact `b1f134b0db94ed23af7f8961b0488a3416192fddc4f61fd954e9d5a09c7a94bb` |
| `34d65eab40f4f8e964dd61f5be968e2b55da706c`：terminal-exit poll race negative | `benchmarks/artifacts/task038_extra_full3d_lor_global_spectral_audit_v2/34d65eab40f4f8e964dd61f5be968e2b55da706c/s1-batch` | immutable worker record `40f24d0f58868f88325f31d44e5b8e813859089792c996e5de01e0d4f4b84dcb`；watchdog `bcc4215df4781c0a462c9a0d779864377936d415e417a94f4683b9a01e44e452`；watchdog raw `ea2c1e40c2ad5de72b445677f811c7754982eb9217cb786f0949ad6ea149e2cc` |

`d198` 的 watchdog 记录 `terminal_exit_race_discard_count=0`，所以最终 PASS 不是把旧竞态样本放宽后得到的结果。

## 正式运行与资源事实

正式 worker 使用 qualified activation、complex128/int32、MPI1、线程数 1；watchdog 的 worker command 与 record command 完全一致。命令入口为：

```text
/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python -m benchmarks.run_task038_full3d_lor_spectral_audit_v2 --stage s1 --case batch --source-name random --raw-dir <d198>/s1-batch/worker_raw --record <tracked record> --expected-source-sha d19848e6f5484835a84186d13e349ae30fc8d56d --expected-mpi-size 1
```

两案在同一 worker 内按 p2 后 p3 顺序执行，每次只保留当前 case 的对象。watchdog 事实为：`sample_count=357`、自然退出、无 orphan、所有状态可读、process-tree peak `788987904 B`、process-tree swap `0`、RSS limit `2000000000 B`、poll `0.25 s`。这些是本次 S1 watchdog 的进程树资源口径，不是 2 GB PDE 资格或 retained-live-set 结论。

证据入口如下：

| 类型 | 路径 | SHA256 |
|---|---|---|
| batch record | `outcomes/records/lor_global_spectral_audit_v2.json` | `8ffa8f1e74392bbd062314e0656d56c3bc464520c541d3a4668a52fad0a2ab09` |
| independent checker | `outcomes/records/lor_global_spectral_audit_v2_checker.json` | `acec3b84f2e8001335bf362aa509e5a809657d5af11b33a847e51fd63cf1a5e3` |
| watchdog compact | `benchmarks/artifacts/task038_extra_full3d_lor_global_spectral_audit_v2/d19848e6f5484835a84186d13e349ae30fc8d56d/s1-batch/watchdog.json` | `df42fbbcb3d238789133fba6434f7972381860711049adfd6df2373df931018e` |
| watchdog raw | `benchmarks/artifacts/task038_extra_full3d_lor_global_spectral_audit_v2/d19848e6f5484835a84186d13e349ae30fc8d56d/s1-batch/watchdog.raw.jsonl` | `9bdb2b3ee0ebb1727e8121e44d1cb101e748192704678a09ae880320c9bff07a` |
| raw worker manifest | d198 worker_raw 的 223-file manifest | `68617efd1fa950d45c5ad8f2835ab5cd580863d6609e890faefcf4bebd3cc0d6` |

## p2/p3 的独立结构结果

这里的“独立维数”是删去 slave identity rows 后的 owner 坐标；canonical owner ID 不被当作 CSR 行号。`tau` 是 V11 规定的 `max(m,n)*eps*sigma_max` 秩阈值。特征值两端均由原始向量和算子重新计算 residual；表中 checker recomputed 值优先于 worker 存储值。

| case | full/slave/independent | rank / tau | singular min … max | lambda min … max | condition |
|---|---:|---:|---:|---:|---:|
| p2-mpi1 | 988 / 220 / 768 | 768 / `2.0001220910793528e-13` | `0.25262199571308525 … 1.1728839979271446` | `0.07953013700040465 … 4.2447253801431595` | `53.37253952072989` |
| p3-mpi1 | 3018 / 480 / 2538 | 2538 / `2.1343936975044477e-12` | `0.35955933841154997 … 3.7874131839018776` | `0.019970670477800642 … 283.0573385017638` | `14173.652247500142` |

| case | smallest / largest eigen residual | `B_L` Hermitian | `A_pull` Hermitian | `B_H` Hermitian | SPD (`B_L`, `A_pull`) |
|---|---:|---:|---:|---:|---|
| p2-mpi1 | `1.1083766402470227e-13` / `2.7133854271858805e-15` | `2.548457279176639e-17` | `1.950699666691467e-16` | `5.854566232093166e-17` | true / true |
| p3-mpi1 | `2.0408235169191283e-11` / `6.039533107090146e-15` | `2.9414951754929604e-17` | `2.7306070926869746e-16` | `7.232789928240366e-17` | true / true |

### action、work、pull 与结构边界

以下是从每案 raw probe/artifact 独立重算的最大 relative 误差；它们不是 worker 自报的 status。`action` 是高阶正算子 probe，`pull` 是转移后的 `A_pull`/低阶比较，`work` 是高低空间 primal/dual work identity。

| case | high action max | pull max | work max | route / orientation / phase |
|---|---:|---:|---:|---|
| p2-mpi1 | `2.180965782950457e-15` | `1.6562333196988438e-15` | `1.889521500231777e-15` | owner route true；orientation closed；phase exactly once |
| p3-mpi1 | `7.141051720081054e-16` | `1.622600943261377e-15` | `3.616645449242639e-15` | owner route true；orientation closed；phase exactly once |

两案的 owner/slave partition、方向因子一致性、`slave_master_complete`、finite 和 sparse identity 均由 checker 从 artifacts 复核。p2 的 high/low full rows 是 988、slave 220、owner 768；p3 是 3018、480、2538。两案均记录 `B_H`/`B_L`/`L` 的 raw CSR rows/NNZ/index/numeric bytes，且测试维数闭合。

由 p2 到 p3 的 condition growth 为 `265.56076167211603`；这是两案结果的派生观察值，不是另加的通过阈值。

## audit-only 与 production 的边界

为了让 checker 能够逐项重算，S1 审计在 p2/p3 raw 中保存了 assembled high-order `B_H` AIJ 以及 sparse independent `L`；rank/SVD 使用了临时 dense `L` copy。它们只存在于这两个小型 audit case：

| 对象 | S1 audit | production / 后续 p6 |
|---|---|---|
| high-order assembled AIJ | `true`（审计 evidence） | 仍为 `false` |
| sparse independent transfer | `true`（审计 evidence） | 不等于生产保留 dense transfer |
| temporary dense `L` for direct SVD | `true`（临时 rank audit） | 不得带入 production/p6 |
| production global dense transfer / numeric allgather / global direct coarse | `false` | 仍为 `false` |

因此 S1 PASS 只是“结构审计已闭合、可以进入 p6/h10 内存资格测量”的许可。它没有解除旧 HX/PCGAMG 关闭结论，也没有批准 S4 geometric MG、完整 PDE 或 official physics。下一阶段应严格按 V11 S2 的独立资源合同执行；本文件不授权启动它。
