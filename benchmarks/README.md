# Benchmark 运行说明

Benchmark 与普通 `results/` 分离。轻量 JSON/CSV 记录提交 Git，完整网格和场写入被忽略的 `benchmarks/artifacts/`。

按功能查找“证明什么、参数、命令、Gate、record 与限制”请从 [`cases/README.md`](cases/README.md) 进入。

| 脚本/文件 | 实际内容 |
|---|---|
| `scripts/run_level1.sh` | compileall、全量单元测试、显式2D manual DtN、3D Stage1 MPI2 |
| `scripts/run_level2_mpi.sh` | MPI1/MPI4 condensation+physical-slab tests、automatic checker |
| `scripts/run_level3_direct.sh` | 默认h5/h3 direct；h2仅显式resource-heavy opt-in |
| `scripts/run_level3_iterative.sh` | p2 h5/h3/h2 workstation完整求解并运行checker |
| `configs/workstation_p2.json` | canonical profile唯一默认来源；CLI只做override |
| `expected/gates.json` | 残差、迭代比、RTA、RSS阈值 |
| `check_benchmarks.py` | 从 manifest/records 重算当前 Gate，含 Task030 Case060、Task031 Case070 与 Task032 Case080 Phase 1/2 的 provenance、数值、RTA、参考场 schema/hash、QEP/ownership 和分类；当前 `277/277` |
| `run_direct_memory_forensics.py` | Task029 h5/h3 direct worker + 0.25 s simultaneous RSS/cgroup/swap/CPU/thread sampler；支持显式 OpenBLAS threads 与 CPU affinity；h2 默认锁定并要求 G1–G10 |
| `run_task031_memory_forensics.py` | Task031 iterative external sampler；live-rank simultaneous RSS/cgroup/swap/stage、clean SHA、h2 lock 与 9.5/11 GiB watchdog |
| `run_task032_phase2_qep.py` | Task032 Phase 2：air 网格收敛、homogeneous lossy、当前 epsilon(x,y)、±beta、残差、L2 归一化与分布式 ownership；完整向量不聚集 |
| `scripts/audit_direct_thread_capability.sh` | 只读审计活动 PETSc/MUMPS、BLAS/OpenMP 链路、OpenBLAS 控制 API 与 CPU 可见性 |
| `records/` | canonical轻量记录与machine-readable Gate report |
| `artifacts/` | ignored重型输出 |

## 推荐顺序

```bash
sh benchmarks/scripts/run_level1.sh
sh benchmarks/scripts/run_level2_mpi.sh
sh benchmarks/scripts/run_level3_direct.sh
sh benchmarks/scripts/run_level3_iterative.sh
```

不要在14 GB环境默认执行direct h2。确需运行时必须显式传：

```bash
sh benchmarks/scripts/run_level3_direct.sh --include-resource-heavy-h2
```

## Record 身份

clean rerun 必须记录 commit、branch、dirty、实际 command、time、container digest、host ID 和 provenance。对历史 h3/h2 iterative，`command/actual_source_*` 保留原运行位置，`canonical_rerun_*` 单独描述今后规范位置；两者不可混写。h5 iterative 在 Response V1 从 `3b3abf0` clean source 重新运行；h3/h2 iterative 和 h5/h3 direct 是 `440885b` clean source 的 ancestor records；h2 direct 明确为 Task008 reviewed reference。

当前环境状态为 `qualified_local_image`，详见 `docker/STAGE4_ENVIRONMENT.md`。

Task28 最终 checker 为 148/148；Task29 新增 Case050 contract 后，checker 继续把该目录结构作为独立 Gate。历史报告中的 87/143/148 数字保留其当时语义。

Task29 Case050 最终分类为 `diagnostic_success`：最佳 h3 MPI2 候选只下降 15.119%，低于 20%；h2 预测区间 18.882–27.913 GiB，G3/G5/G7/G9 失败，因此没有运行 h2，也没有生成合格 low-memory direct profile。

Review V1 后的固定四核 h5 矩阵进一步判定当前 image 的 threaded direct 不可用：MPI1×4 虽创建更多 pthread，KSPSetUp CPU 核均值/峰值仍为 0.999/1.054，Stage4 相对 MPI1×1 仅 1.054× speedup。T1/T3 失败后 threaded h3 按 T4 `not_run`，ordinary default 不变。

Task029 Review V2 已技术通过并接受 Case050 的 telemetry、Gate 与负结果记录进入 master；`engineering_success=no`，没有新 optimized direct profile，h2 保持 `not_run`。

Task030 Case060 已通过 Review V3 并合入 master。Task031 Case070 从该 clean merge point 完成 h5/h3/h2：external simultaneous worker peak 为 1.620/3.474/7.898 GiB，h2 legacy internal peak 为 8.176 GiB，三残差与 official R/T/A 全通过、无 swap；保守结论为 Task030 历史约 9.4 GiB 压到约 8.0–8.2 GiB。h2 达到 strong memory success，但 assembled-F-free public MPC form action 使 solve 约为 Task030 的 5.01x。Case070 candidate 保持显式 opt-in，ordinary default 不变，完整 timeline 仍只写 `artifacts/cases/070/`；KSP/smoother 合法性见 `docs/iterative_solver_ports.md`。
