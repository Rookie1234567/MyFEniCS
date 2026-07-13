# Task029 合并建议

## 总体建议

```text
task_classification = diagnostic_success
engineering_success = no
strong_engineering_success = no
h2_workstation_success = not_attempted_by_gate
threaded_direct_capability = unavailable_in_current_image
ordinary_default_changed = no
task29_master_merge_now = no; response_v1 后等待 final review
```

Task29 已得到可信的内存分解和主瓶颈结论。最佳 h3 候选将 simultaneous RSS 降低 15.119%，低于 20% 工程阈值。因此不得把任何候选宣传为 `optimized_direct_incore_candidate` 或 `optimized_direct_low_memory_candidate`。

## 建议审查后保留

- 外部 simultaneous-RSS/cgroup/swap/stage sampler、matrix/factor inventory、raw-index MUMPS telemetry 与 clean-source provenance。
- Case050 benchmark 合同、轻量 baseline/candidate records、对比表和 h2 安全决策。
- `DirectSolveFailure.cleanup()` 幂等异常清理。
- 正确尊重显式、可用的 MPI-distributed factor package；虽然 SuperLU_DIST 在本目标上更慢且更占内存，但选择逻辑本身属于正确性修复。
- OOC scratch/I/O/cleanup telemetry。
- 显式 `direct_release_base_after_augmentation` 生命周期选项：默认关闭，h5/h3 数值资格通过，h3 worker RSS 稳定但仅下降 5.462%。它应作为低风险生命周期控制保留，不得称为合格 low-memory profile。
- 完整 G1–G10 h2 Gate 验证与已测试的两点预测 helper。
- PETSc/MUMPS/BLAS 构建链接审计、固定亲和性 CPU/thread sampler 和负向 capability record；它们用于防止把“创建 pthread”误写成“因子化多核可用”。

## 不得提升为推荐 profile

- MPI2 MUMPS：h5 通过 20% 内存 Gate，h3 未通过（15.119%）；只保留为诊断运行点。
- MUMPS OOC：h5 worker RSS 下降 13.744%、cgroup 下降 18.737%，但 Stage4 时间为 1.539 倍并使用 559,715,776 scratch bytes；在两个 h3 候选上限内未获提升。
- BLR `1e-5`：尽管进程返回码为 0，true residual（`4.704e-3`）与 R/T/A 失败，拒绝。
- SuperLU_DIST：h5 worker RSS 增加 14.462%，时间增加 16.2%，拒绝用于本目标。
- MUMPS ordering `ICNTL(7)=3`：factor nnz 与峰值均增加，拒绝。
- 任何 h=2 运行、ordinary default rank 改动、静默启用 OOC/BLR 或 direct-assembly 重写。
- MPI1×4 threaded direct：KSPSetUp CPU 核均值/峰值仅 0.999/1.054，Stage4 相对 MPI1×1 只有 1.054× speedup；当前镜像身份为 `unavailable_in_current_image`，threaded h3 按 T4 `not_run`。

本建议刻意把基础设施/公共生命周期价值与性能 profile 资格分开。`review_report_v1.md` 的 P0 已在同一分支回应；最终 review 通过前不得宣称最终通过或把本分支合入 `master`。
