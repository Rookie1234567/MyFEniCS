# RESPONSE V1：Task029 Review V1 更正回应

## 1. 总体回应

```text
review_report = review_report_v1.md + review_report_v1_p0c_addendum.md
classification = diagnostic_success
engineering_success = no
threaded_direct_capability = unavailable_in_current_image
h2 = not_run
h3_threaded_direct = not_run
ordinary default changed = no
master merge = wait for final review
```

Review V1 接受的 Task029 内存诊断结论保持不变。本次更正补齐真实线程能力审计、固定四核 h5 证据、项目级完整回顾、长期 Task 回顾治理与可执行文档合同，并同步全部指定项目文档。模板按建议使用；当 h5 已触发明确 stop 时，没有机械追加 MPI1×2 或 threaded h3。

## 2. P0-A：thread capability audit

状态：完成，运行期触发 T0。

新增 [`benchmarks/scripts/audit_direct_thread_capability.sh`](../../benchmarks/scripts/audit_direct_thread_capability.sh) 并在正式镜像内审计：

| 项目 | 结果 |
|---|---|
| PETSc | 3.24.0；活动架构 `linux-gnu-complex128-32` |
| MUMPS | 5.8.1；PETSc `--download-mumps`；`-lzmumps -lmumps_common -lpord -lpthread` |
| BLAS/LAPACK | PETSc `-llapack -lblas`，动态解析到 system OpenBLAS |
| system OpenBLAS | 0.3.26 pthread；`parallel_mode=1`；环境读 4 threads、API 改 2 后读回 2 |
| PETSc/MUMPS OpenMP | configure/header/link chain 未显示 OpenMP 构建 |
| NumPy BLAS | 独立 scipy-openblas 0.3.29；明确不作为 MUMPS 证据 |
| CPU | 容器可见/允许 `0-15`；正式 h5 固定 `0-3` |
| nested/oversubscription | OpenMP 嵌套已禁用；NumPy 与 PETSc 是不同 OpenBLAS runtime，runnable-thread oversubscription 不能完全排除；CPU affinity 将实际执行封顶在 `0-3` |

runner 增加 `/proc` worker/process-tree thread count、累计 CPU seconds、区间 CPU core equivalents 和实际 `Cpus_allowed_list`。MPI1×4 在 `during_ksp_setup_peak` 的 thread count 为 12，但 CPU 核均值/峰值只有 0.999/1.054；MPI1×1 为 0.999/1.060。因此线程池虽然存在，MUMPS KSPSetUp 仍约 1 核，且多个 BLAS runtime 无法被环境变量隔离，满足 T0 停止条件。

最终记录：[`outcomes/threaded_direct_capability_audit.md`](outcomes/threaded_direct_capability_audit.md)、[`environment.json`](outcomes/environment.json)。

## 3. P0-B：fixed-four-core h5 screening / stop decision

四个 full solve 都来自 clean source `48958571f62590418bf4281f09ad22b1419eb880`，使用相同 target config、MUMPS、ordering/options、80 modes、`n_aux=80`、full residual、official R/T/A、CPU `0-3` 和零 swap。

| 配置 | worker RSS | cgroup | KSPSetUp | KSPSolve | Stage4 | KSP CPU mean/max |
|---|---:|---:|---:|---:|---:|---:|
| MPI4×1 | 2351.707 MiB | 1813.465 MiB | 2.385 s | 0.070 s | 18.311 s | 3.906 / 4.061 |
| MPI2×2 | 1677.062 MiB | 1391.320 MiB | 1.953 s | 0.063 s | 20.687 s | 3.272 / 4.025 |
| MPI1×4 | 1399.648 MiB | 1272.477 MiB | 23.841 s | 0.140 s | 48.273 s | 0.999 / 1.054 |
| MPI1×1 | 1401.988 MiB | 1269.812 MiB | 25.578 s | 0.111 s | 50.891 s | 0.999 / 1.060 |

所有 residual `<=2.765e-11`，最大 Task28 R/T/A 绝对差 `<=1.729e-13`，modal identity 与零 swap 通过。MPI1×4 / MPI1×1 RSS 比 0.9983、cgroup 比 1.0021，所以 T2 通过；但 KSPSetUp 没有多核，Stage4 相对 MPI1×1 speedup 仅 1.054×，相对原 MPI4 14.800 s baseline 为 3.262×。因此：

```text
T0 = failed_at_runtime
T1 = failed
T2 = pass_but_not_sufficient
T3 = negative
T4 = stop
threaded_direct_capability = unavailable_in_current_image
```

MPI1×2 是 review 中的建议补点，不是强制门槛；MPI1×4 已同时触发 T0/T1/T3，继续补点不会改变 stop 身份，因此未运行。完整表为 [`outcomes/threaded_direct_matrix.csv`](outcomes/threaded_direct_matrix.csv)，Case050 轻量 record 为 [`h5_threaded_direct_audit.json`](../../benchmarks/cases/050_stage4_direct_memory_forensics/records/h5_threaded_direct_audit.json)。

## 4. P0-C1：Task029 development progress rewrite

状态：完成。

[`docs/development_progress.md`](../development_progress.md) 新增独立 `# 36. Task029：Stage4 direct memory forensics` 章节，包含：任务身份/最终状态、为什么启动、冻结模型与 baseline、方法、实际运行矩阵、h5/h3 基线、KSPSetUp 根因、H1–H7、带正负号语义的候选表、线程 T0–T4、h2 G1–G10、实测/估算/外推边界、成功与负结果、合并边界、局限、下一步因果关系和证据入口。

章节明确：

```text
classification = diagnostic_success
engineering_success = no
h2 = not_run
new direct profile = no
ordinary default changed = no
threaded direct = unavailable_in_current_image
```

同时按同一标准重写 [`outcomes/summary.md`](outcomes/summary.md)，删除容易混淆的中间态主叙述，保留可追踪的历史证据文件。

## 5. P0-C2：repository-wide retrospective standard adoption

状态：完成。

Review 新增的 [`docs/task_retrospective_standard.md`](../task_retrospective_standard.md) 已固化为“从 Task029 起所有新 Task 的强制阶段回顾标准”。同步文件：

- 根 [`README.md`](../../README.md) 保护区与文档导航；
- [`docs/README.md`](../README.md) 保护区、项目总览、Task029 状态与 review/response/audit 入口；
- [`docs/repository_work_principles.md`](../repository_work_principles.md) “结果与文档闭环”长期条款。

长期条款区分详细 `outcomes/summary.md` 与项目级 `development_progress.md` 的职责，并强制背景、基线、方法、结果、解释、负结果、最终决策、局限、下一步和证据入口；一句状态或纯链接不构成完成。本轮没有重写 Task000–Task028。

## 6. P0-C3：documentation contract enforcement

状态：完成。

[`src/test/test_24_repository_work_principles.py`](../../src/test/test_24_repository_work_principles.py) 现在检查三份保护文件同步包含长期回顾条款，并检查两个 README 链接标准。

新增 [`src/test/test_29_task_retrospective_contract.py`](../../src/test/test_29_task_retrospective_contract.py)，自动检查：

1. 标准存在且 docs index 链接；
2. repository principles 含强制条款；
3. Task029 在 development progress 中是独立且长度足够的章节；
4. 章节内部包含为什么启动、方法、关键结果、解释、决策、局限、下一步和证据；
5. 章节内部含 `diagnostic_success`、`engineering_success = no`、`h2 = not_run` 与 threaded identity；
6. 章节内部链接 outcomes summary、review V1 与 Case050；
7. Task029 outcome summary 使用标准结构；
8. 后续 task flow 引用长期标准。

## 7. P0-D：project documentation synchronization

状态：完成。

| 文件 | 同步内容 |
|---|---|
| `docs/README.md` | Task029 当前状态、review、response、thread audit |
| `docs/capability_matrix.md` | telemetry merge candidate；optimized profile none；MPI2/OOC/BLR/SuperLU/release-base/threaded 身份 |
| `docs/solver_guide.md` | default MPI4、MPI2、MPI1、OOC、BLR、SuperLU、release-base、MPI1×4 选择表 |
| `docs/benchmark.md` | Case050 最终内存与线程审计数字 |
| `benchmarks/README.md` | CPU/thread sampler、audit script 与最终 stop |
| Case050 README/records index | 固定四核矩阵、运行命令语义、轻量 negative record |
| direct walkthrough | 新 public telemetry 字段、thread control 和当前 image 边界 |
| current version boundaries / cases index | 最新 Task029 能力与 not-run 边界 |

ordinary default、Task28 canonical records 和已有 physical model 均未改变。

## 8. P0-E：conditional h3 threaded confirmation

状态：`not_run_by_T4`。

P0-E 只在 h5 达到强正信号时生效。MPI1×4 h5 同时失败 T1 和 T3，故没有运行 MPI1×4 或 MPI2×2 h3，没有重建复杂镜像，也没有把 threaded direct 写成下一步推荐。这是审查 stop rule 的正确执行，不是遗漏。

## 9. 验证结果

| 验证 | 结果 |
|---|---|
| 四组 h5 full solve | 4/4 numerical/modal/no-swap pass |
| focused telemetry + governance + documentation links + retrospective | 42 passed |
| ruff changed Python | pass（host ruff 0.12.0；image 未安装 ruff） |
| compileall `benchmarks src` | pass |
| full unit discovery | 146 passed, 10 skipped |
| benchmark checker `--no-write` | 149/149 passed |
| JSON / CSV parse | pass；thread matrix 4 rows |
| `git diff --check` | pass |

## 10. 最终合并边界

final review 通过后，建议保留 telemetry、cleanup、factor-package 选择正确性、显式 release-base、OOC evidence、Case050、h2 guard、线程审计与文档合同。不得提升 MPI2、OOC、BLR、SuperLU_DIST、ordering 或 threaded direct 为推荐 profile；h2/threaded h3 保持 `not_run`；ordinary default 不变。本 response 不自行宣称最终 review 通过，也不在本轮直接合并 master。
