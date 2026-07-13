# Task029 outcomes

本目录保存 Task029 的轻量、可审查证据。重型运行输出写入 gitignored 的 `benchmarks/artifacts/cases/050/`，不得在此保存 mesh、field、factor、OOC scratch 或完整 PETSc log。

## 入口

- [任务书](../task.md)
- [COMSOL 强制补充](../task_comsol_reference_addendum.md)
- [COMSOL 内存参考报告](../references/comsol_3d_direct_iterative_memory_report.md)
- [比较边界](comsol_reference_comparability.md)
- [h5 轻量 summary record](../../../benchmarks/cases/050_stage4_direct_memory_forensics/records/h5_baseline.json)
- [h3 轻量 summary record](../../../benchmarks/cases/050_stage4_direct_memory_forensics/records/h3_baseline.json)
- [h5/h3 分阶段内存](baseline_memory_timeline.csv)
- [h5/h3 matrix inventory](baseline_matrix_inventory.csv)
- [h5/h3 factorization summary](baseline_factorization_summary.csv)
- [h5 rank-count 诊断](rank_scaling.csv)
- [优化假设表](optimization_hypotheses.csv)
- [候选实施清单](optimization_manifest.csv)
- [direct 对象生命周期](direct_object_lifecycle.md)
- [候选统一对比](candidate_comparison.csv)
- [h2 G1-G10 决策](gate_decision.csv)
- [h2 内存预测](h2_memory_prediction.md)
- [h2 启动决定](h2_launch_decision.md)
- [合并建议](merge_recommendation.md)
- [下一步判断](next_decision.md)
- [少 rank + 多线程能力审计](threaded_direct_capability_audit.md)
- [固定四核线程矩阵](threaded_direct_matrix.csv)
- [h5 MPI2 精简记录](../../../benchmarks/cases/050_stage4_direct_memory_forensics/records/h5_mpi2_candidate.json)
- [h3 MPI2 精简记录](../../../benchmarks/cases/050_stage4_direct_memory_forensics/records/h3_mpi2_candidate.json)

## 当前阶段

```text
stage = review_v1_corrections_complete_pending_final_review
h5_baseline = pass
h3_baseline = pass_no_swap
h3_best_candidate = numeric_pass_memory_minus_15.119pct
classification = diagnostic_success
engineering_success = no
threaded_direct_capability = unavailable_in_current_image
h3_threaded_direct = not_run_by_T4
h2 = not_run_by_gate
```

冻结 h5/h3 baseline 分别来自 clean source SHA `208aaab149ca5c2be0aae09a8d893bfa02e3f8cc` 与 `fba69d88ea8590ea01537b7561edff1684f25135`；正式内存候选来自 `6babe4700328be2b3b93aad7e3e6c212b6dbad10`，线程审计来自 `48958571f62590418bf4281f09ad22b1419eb880`。最佳 h3 内存候选未达到 20%；MPI1×4 在 KSPSetUp 的 CPU 核均值/峰值仅 0.999/1.054，Stage4 相对 MPI1×1 speedup 仅 1.054×，所以不产生低内存或 threaded direct profile，也不运行 threaded h3 或 h2。本目录的新结果不得覆盖 Task28 canonical records；完整 timeline、场和 solver log 继续保留在 ignored artifact 目录。
