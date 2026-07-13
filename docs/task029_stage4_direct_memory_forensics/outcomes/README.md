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

## 当前阶段

```text
stage = stage_b_baselines_complete_stage_c_ready
h5_baseline = pass
h3_baseline = pass_no_swap
h2 = locked
```

冻结 h5/h3 记录分别来自 clean source SHA `208aaab149ca5c2be0aae09a8d893bfa02e3f8cc` 与 `fba69d88ea8590ea01537b7561edff1684f25135`；两者之间只有文档和轻量证据变更，求解实现相同。本目录的新结果不得覆盖 Task28 canonical records；完整 timeline、场和 solver log 继续保留在 ignored artifact 目录。
