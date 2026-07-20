# Task034 Review V1 Addendum

本补充审查与 `review_report_v1.md` 共同构成 Review V1 权威。Codex 在 `response_v2.md` 中必须同时关闭两份 review 的 blocking findings。本文件不改变已经接受的 p3/h3、p4/h5、MPI identity 和 Case093 数值结论。

## A1. Benchmark Python 架构需要收敛

### 发现

Task034 分支在 `benchmarks/` 中新增或大幅扩展了较多 task-numbered Python 文件。当前并非“每个 p/h case 都复制了一套 Maxwell 求解器”：例如 Full3D watchdog 最终调用 `src.solvers.solve_maxwell_3d_stage_4b_block_grating`，Hybrid runner 也调用 `src/modes`、`src/coupling`、`src/solvers` 和 `src/postprocessing` 的主体实现。因此数值核心总体仍在 `src/`。

但是，多个 benchmark runner 已累积大量任务特定配置、source-compatible allowlist、provenance、watchdog、聚合和 Gate 逻辑。若继续按 Task 编号增长，将造成：

- 同一求解链存在多个入口和重复参数解析；
- task-specific allowlist 难以维护；
- benchmark 层与数值主体边界变模糊；
- 新 case 容易继续新增 Python 文件，而不是复用参数化 runner；
- selective merge 难以判断哪些是 reusable infrastructure、哪些只是 Task034 research tooling。

### 要求

Codex 必须在 `response_v2.md` 和 selective merge manifest 中给出完整的 benchmark Python inventory，并按以下类别归档：

1. 通用参数化 PDE runner；
2. watchdog / resource telemetry；
3. checker / evidence aggregator；
4. one-off research analysis；
5. numerical functionality that must live in `src/`；
6. historical compatibility entrypoint。

至少完成以下审查：

- 证明不存在“每个 p/h/M/MPI case 一个独立求解脚本”；
- 列明每个新增 Task034 Python 文件调用的 `src/` 主体；
- 标出重复 orchestration 和可合并入口；
- 未经重构的 task-specific research runner 默认不得作为 production merge candidate；
- 新增数值功能若只存在于 `benchmarks/`，必须迁入 `src/` 或标记 research-only；
- 后续 case 应通过配置 JSON/CLI 参数驱动通用 runner，而不是继续新增 case-specific solver script。

本轮不强制进行大规模重命名或重构，但 selective merge 必须避免把所有 task-numbered runner 无差别合入 master。

## A2. p2/h1、p3/h2、p4/h3 的“资源负结果”必须改用准确语义

### 当前事实

这三个 Full3D 案例均只完成 assembly，没有实际启动 factorization 或 full solve：

| case | rows | assembled NNZ | assembly peak | conservative factor upper | termination | 实际状态 |
|---|---:|---:|---:|---:|---:|---|
| p2/h1 | 4,379,832 | 461,122,320 | 67.923 GiB | 418.821 GiB | 184.163 GiB | factorization not launched |
| p3/h2 | 2,047,298 | 488,789,000 | 64.015 GiB | 232.460 GiB | 184.163 GiB | factorization not launched |
| p4/h3 | 1,540,028 | 696,091,072 | 80.538 GiB | 204.132 GiB | 184.163 GiB | factorization not launched |

因此这些记录证明的是：

```text
not_run_by_task034_conservative_resource_gate
```

它们不证明：

- 数学问题无法求解；
- FEniCS 在任意 solver/profile 上无法求解；
- COMSOL、PARDISO、OOC、更多内存、不同 MPI 或不同矩阵实现无法求解；
- 实际 MUMPS peak 必然等于 conservative upper。

用户已在 COMSOL 中运行过相同名义 p/h 参数，这与 Task034 的结果并不矛盾，因为软件、DoF 定义、矩阵结构、直接求解器、OOC/pagefile、网格实现和端口实现可能不同。

### 要求

- 所有 summary、CSV、manifest 和 response 中，将含糊的 `resource negative` 明确改写为 `not_run_by_conservative_resource_gate_after_assembly` 或等价状态。
- 必须同时报告 `factorization_launched=false` 和 `full_solve_launched=false`。
- 不得把预测上界写成实测 factorization peak。
- p3/h2、p4/h3 的 Hybrid M160 是 measured shard pass，但没有 M funnel 和 same-point Full3D closure；应单列，不得与 Full3D not-run 混成整个案例失败。
- p2/h1 Hybrid 是 field-recovery timeout，而不是 memory negative 或 numerical nonconvergence；必须按 A5 单独分类。

## A3. 缺少统一的全案例结果总表

### 发现

当前 `fixed_geometry_ph_convergence.csv` 只包含：

- p/h；
- Full3D/Hybrid 资格状态；
- Full3D R/T/A_volume；
- Full3D residual；
- Full3D/Hybrid peak memory。

它没有完整列出：

- elements、Nédélec/local FE DoF、external auxiliary、modal unknowns、total rows；
- assembled NNZ、factor NNZ；
- Hybrid R/T/A/A_volume；
- diffraction order `R(0,0)`；
- assembly/factorization/solve/total wall time；
- M、MPI、polarization；
- controlled stop / not-run 原因；
- source SHA 和 evidence path。

因此目前无法从一个表中回答“所有模型算了什么、物理结果是什么、成本是多少”。

### 必须新增的机器可读总表

建议新增：

```text
docs/task034_workstation_wsl_adaptive_scalability/outcomes/all_model_results.csv
docs/task034_workstation_wsl_adaptive_scalability/outcomes/all_model_results.json
```

每一行表示一个实际运行或正式 not-run decision，至少包含：

```text
case_key, p, h_nm, method, M_per_direction, MPI, polarization,
status, data_identity, source_sha,
elements, fe_dofs, external_aux_dofs, modal_unknowns, total_rows,
assembled_nnz, factor_nnz,
R_total, T_total, A_balance, A_volume,
R00_s, R00_p, R00_total, T00_s, T00_p, T00_total,
true_relative_residual,
assembly_seconds, factorization_seconds, solve_seconds, total_seconds,
peak_memory_gib, swap_bytes,
full3d_hybrid_closure_status, evidence_path
```

三维 `R(0,0)` 必须定义清楚。对于 S 入射，建议分别报告同偏振与交叉偏振功率：

```text
R00_s
R00_p
R00_total = R00_s + R00_p
```

这里的 `R00_p` 是 **S 入射下的交叉偏振输出分量**，不是要求重新运行 P 入射案例。不得只写一个含义不明的 `R(0,0)`。

### `outcomes/summary.md` 必须增加四张汇总表

1. **全模型主表**：以 S 偏振为主，列出所有 p2/p3/p4 Full3D 与 selected-M Hybrid，包括 not-run/controlled-stop 行；已有 P capability 可在单独的小型能力表中引用，不要求补跑完整 P 矩阵；
2. **M 收敛表**：至少 p3/h3、p4/h5 的 S 偏振 M80/M120/M160，列 R/T/A、R00、DoF/rows、memory、time 和相邻 M 差；
3. **MPI 表**：p3/h5 S 偏振 Full3D 与 Hybrid 的 MPI1/8/16/32，列物理量、DoF/rows、memory、分阶段耗时和漂移；
4. **资源停止表**：p2/h1、p3/h2、p4/h3 的 S 偏振结果，区分 assembly measured、factor upper predicted、是否启动 factor/full solve，以及 Hybrid 实际结果。

表格应由 JSON/CSV 自动生成或至少通过 checker 验证，避免 Markdown 手工抄写漂移。

## A4. AGENTS.md 已改为仓库级永久规则

根 `AGENTS.md` 已在 master 修正：不再写当前 Task 编号、日期、分支和阶段顺序，并新增 `src/` 与 `benchmarks/` 的架构边界。Codex开始 Review V2 前必须先拉取最新 master 并重新读取该文件。当前 Task 的具体范围仍以 Task034 任务书、补充任务书和两份 Review V1 为准。

## A5. 正式范围以 S 偏振为主，且 p2/h1 Hybrid 超时不得误判

### S 偏振主线

Task034 的统一收敛、M 漏斗、MPI identity、Full3D/Hybrid closure 和结果总表均以 **S polarization** 为正式主线。Review V2 不要求为表格对称性重复运行完整 P 偏振 p/h、M 或 MPI 矩阵。

现有 p2/h5 P capability 结果可以保留并在 summary 中单独说明其能力边界，但不得由此触发新的重型 P 重跑。只有用户后续明确要求，或发现 S 主线无法验证某项与偏振相关的数值内核时，才另行提出 P 偏振任务。

必须区分：

- `polarization_kind = s`：入射偏振为 S；
- `R00_p` / `T00_p`：S 入射结果中的交叉偏振输出分量；
- P 入射案例：另一套独立物理输入，本轮不要求补跑。

### p2/h1 Hybrid 实际发生了什么

p2/h1 Hybrid M160 的 watchdog 上限为 7200 s。该运行没有因内存终止，未触发 memory warning，job swap 为 0，实测峰值约 95.879 GiB。已完成的阶段包括：

| 阶段 | 完成时刻 |
|---|---:|
| bottom local factor | 2731.663 s |
| bottom Schur contribution | 3172.848 s |
| top local factor | 5205.347 s |
| top Schur contribution | 5542.727 s |
| field recovery 开始 | 5542.752 s |

进程随后在 `field_recovery` 阶段达到 7200 s 的 wall-time 限制并由 watchdog 终止。因此准确状态是：

```text
timeout_during_field_recovery_no_official_solution
```

它不等于：

- 线性系统被证明不收敛；
- 模态 Schur 系统被证明无解；
- 内存不足；
- p2/h1 Hybrid 在更长时间或更优 field-recovery 实现下必然失败。

但是，因为 field recovery、完整 solver record、full explicit true residual 和 official R/T/A 尚未完成，本次运行也不能称为数值成功或已有可用解。最准确的表述是：**主要局部 factor/Schur 阶段已完成，但完整场恢复和正式后处理在时限内未完成，因此没有获得可审查的最终物理解。**

Review V2 不强制仅为补齐表格而重新运行 p2/h1。应保留该 timeout 证据，并把优化 field recovery 或延长时限的复跑留给后续明确任务；当前 S 偏振主线可以使用 p2/h2、p3/h3、p4/h5 等已经正式闭合的案例。

## Review Addendum 结论

在关闭 A1–A3 和 A5 的状态/汇总要求前，Task034 仍不具备直接 selective merge 条件。上述要求主要涉及架构清单、状态语义、证据聚合和 summary 完整性；若不修改 Maxwell/Floquet/QEP/Hybrid 数值核心，原则上不要求重跑已经接受的 p3/h3、p4/h5 和 MPI 主 PDE，也不要求重复运行完整 P 偏振矩阵。