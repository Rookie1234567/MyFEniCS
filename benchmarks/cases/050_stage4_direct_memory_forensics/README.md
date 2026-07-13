# Case050：Stage4 direct memory forensics

## 最终状态（2026-07-13）

Case050 已以 `diagnostic_success` 收口。MPI4 h5/h3 baseline 的 simultaneous worker RSS 为 2328.145 / 8651.098 MiB；最佳 in-core 候选 default MUMPS MPI2 为 1655.484 / 7343.137 MiB，即分别下降 28.893% / 15.119%。两次候选均为 full solve、Task28 residual/R/T/A Gate 通过且零 swap，但 h3 未达到 20%，因此不形成合格低内存 profile。

h2 两种中央预测为 22.214 / 22.330 GiB，敏感性区间 18.882–27.913 GiB；G3、G5、G7、G9 失败，故 `h2_launch_decision=not_run`。精简证据见 [`h5_mpi2_candidate.json`](records/h5_mpi2_candidate.json)、[`h3_mpi2_candidate.json`](records/h3_mpi2_candidate.json) 和 [Task29 outcomes](../../../docs/task029_stage4_direct_memory_forensics/outcomes/README.md)。ordinary default 未改变，Task28 canonical records 未覆盖。

## 合同

| 项目 | 值 |
|---|---|
| 1. ID | `050_stage4_direct_memory_forensics` |
| 2. 证明 | Stage4 direct 的分阶段内存、matrix/factor inventory 与候选前后对比 |
| 3. 不证明 | 物理网格收敛、参数鲁棒性或新迭代法能力 |
| 4. 物理配置来源 | `src.common.config_3d::target_stage4_config` |
| 5. 几何 | 50 x 25 x 140 nm；17 x 25 x 120 nm block |
| 6. 材料 | 13.5 nm complex Si |
| 7. 入射 | 80 度、s 偏振 |
| 8. 边界 | double Floquet + auxiliary Fourier-DtN |
| 9. FE/mesh | p2 Nédélec；h5/h3，h2 条件式 |
| 10. MPI | baseline 4 ranks |
| 11. direct profile | default / mumps_ooc / mumps_blr |
| 12. 必跑 | MPI4 h5、MPI4 h3 |
| 13. 条件运行 | h2，仅通过 guarded Gate 后 |
| 14. sampler | 0.25 s external process/cgroup sampler |
| 15. matrix evidence | base/augmented/factor PETSc inventory |
| 16. memory evidence | simultaneous RSS、historical upper bound、cgroup、swap |
| 17. 数值 Gate | true residual、R/T/A、closure、modal identity |
| 18. ordinary default | 不改变；新 profile 显式 opt-in |
| 19. heavy artifacts | `benchmarks/artifacts/cases/050/`，不提交 |
| 20. records | 只提交通过 Gate 的轻量 summary record |
| 21. Task28 records | 只读，不覆盖 |
| 22. COMSOL | 另一机器/四面体/零级端口的定性参考 |

## 物理问题

50 x 25 x 140 nm 单胞、17 x 25 x 120 nm Si block、13.5 nm、80 度、s 偏振、p2 Nédélec、double Floquet、auxiliary Fourier-DtN、`auto_propagating` 全传播衍射级。profile、ordering、遥测和数学等价装配可以改变；物理、模式集合、official R/T/A 与 ordinary default 不得改变。

`target_stage4_config` 为安全的公共 factory，默认 `matrix_diagnostics_assemble_only=true`；Case050 full baseline worker 必须显式覆盖为 `false`。缺少 KSPSolve、true residual 或 official R/T/A 的运行只能记为 assemble preflight，不能获得 baseline 资格。

## 参数说明

`config.json` 冻结允许的 h、MPI、profile、artifact root 和 h2 安全上限；`expected.json` 冻结 Task28 h5/h3 R/T/A 与 Task29 数值/内存 Gate。profile 筛选一次只改变一个主要因素。

## PyCharm

在 Docker 解释器环境中把模块设为 `benchmarks.run_direct_memory_forensics`，参数先用 `--h-nm 5 --mpi-size 4 --profile default`。PyCharm 普通单进程 Run 不构成 MPI4 baseline；正式运行使用下方 shell wrapper 或 External Tool。

## CLI 或测试

在 `myfenics-stage4:task28` 镜像内：

```text
sh benchmarks/cases/050_stage4_direct_memory_forensics/run_h5.sh
sh benchmarks/cases/050_stage4_direct_memory_forensics/run_h3.sh
```

脚本调用 `benchmarks.run_direct_memory_forensics`，外部采样器以 0.25 秒间隔记录 worker-rank 同时 RSS、MPI 进程树 RSS、cgroup current/peak、swap 与 solver stage。raw timeline 与完整 solver 输出保留在 ignored artifact 目录。

Windows bind mount 的正式 Docker 运行由宿主机先执行 tracked-only clean check，再把同一时刻的 `HEAD` 作为 `TASK029_VERIFIED_CLEAN_SHA` 传入容器。容器必须确认 mounted `HEAD` 完全匹配；这样不会把 CRLF 归一化误判为 source dirty，也不会跳过宿主机 clean Gate。

h2 默认禁止：

```text
H2_GATE_JSON=<passing-gate.json> \
  sh benchmarks/cases/050_stage4_direct_memory_forensics/run_h2_guarded.sh
```

gate 文件必须同时证明 h5/h3 数值通过、两者内存至少降低 20%、h3 无 swap、h2 预测上界不超过 13.5 GB 且 watchdog 已启用。

## 代码路径与理论

`run_direct_memory_forensics -> mpiexec worker -> target_stage4_config -> run_stage4b_block_grating_3d_case -> common_3d_case_flow -> dtn_port_3d -> MUMPS`。内存字段定义见 Task029 任务书 Stage A，direct 物理/数值背景见 `notes/theory/direct_solvers_and_factorization.md` 与 `notes/theory/dtn_modal_ports_and_condensation.md`。

## 当前证据

Task29 h5/h3 baseline 已分别在 source SHA `208aaab149ca5c2be0aae09a8d893bfa02e3f8cc` 与 `fba69d88ea8590ea01537b7561edff1684f25135` 完整通过；两者之间只有文档/证据变更。二者均为 MPI4、p2、default MUMPS、full solve，true residual 分别为 `5.224671064148491e-12` 与 `1.3821009358870955e-11`，Task28 R/T/A Gate 和零 swap Gate 均通过。轻量记录见 [`records/h5_baseline.json`](records/h5_baseline.json) 与 [`records/h3_baseline.json`](records/h3_baseline.json)。

h5/h3 的最大同时 worker RSS 分别为 2328.145 / 8651.098 MB，最大 cgroup current 为 1729.035 / 8353.727 MB，均出现在 KSPSetUp；factor/augmented nnz 比例分别为 6.916 / 12.484。h5 MUMPS MPI1/2/4 rank 诊断显示 MPI2 相对 MPI4 降低 27.07% worker RSS，因此选为首个 h3 候选。Stage B 已完成，h2 仍锁定。

## 结果解释

诊断成功可以只确认主要瓶颈，即使内存收益有限；工程成功要求 h3 同时总 RSS 至少降低 20%。统计口径变化本身不算优化。COMSOL 量级不能替代 FEniCS 自身前后比较。

## 数值 Gate

- full true residual `<=1e-8`；
- h5/h3 的 R/T/A 相对 Task28 direct reference 绝对差 `<=1e-8`；
- modal order set、`n_aux`、FE DoF 和 Floquet constraint count 不变；
- official energy closure 不退化。

## 内存口径

`max_simultaneous_total_rss_mb` 是外部采样时刻所有 MPI worker rank 当前 RSS 的和。`sum_rank_historical_peaks_mb_upper_bound` 是各 rank 历史峰值之和，只作上界；两者不得混写。cgroup current/peak 与 process RSS 分开记录。

## 限制

h3 必须在无 swap 压力下完成。h2 默认锁定；即使历史 h2 record 存在，也不得跳过预测、20% 降幅、13.5 GB 上限与 watchdog Gate。OOC/BLR 必须同时报告磁盘/误差/时间代价。

## COMSOL 参考边界

COMSOL 报告见 [Task029 参考](../../../docs/task029_stage4_direct_memory_forensics/references/comsol_3d_direct_iterative_memory_report.md)，可比性说明见 [outcomes 文档](../../../docs/task029_stage4_direct_memory_forensics/outcomes/comsol_reference_comparability.md)。它来自另一台机器、自由四面体、P 偏振、16 nm block 与零级端口，只能提供定性内存架构线索，不能作时间、RTA 或每 DoF 效率基准。
