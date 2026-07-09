# 改动文件

## 新增代码

```text
src/studies/run_real_split_ams_qualification.py
```

说明：隔离的 research runner，在 real PETSc 模式下构造 FE-only complex Maxwell 的 real split 系统，并测试 Jacobi 与 blockdiag AMS PC。没有修改正式 Stage 4 solver 主线。

## 新增 outcomes

```text
docs/task013_real_split_ams_hx_qualification/outcomes/summary.md
docs/task013_real_split_ams_hx_qualification/outcomes/real_split_equivalence.csv
docs/task013_real_split_ams_hx_qualification/outcomes/fe_only_real_split_ams_summary.csv
docs/task013_real_split_ams_hx_qualification/outcomes/fe_only_real_split_ams_memory.csv
docs/task013_real_split_ams_hx_qualification/outcomes/p_coarsened_auxiliary_summary.csv
docs/task013_real_split_ams_hx_qualification/outcomes/ams_memory_breakdown.md
docs/task013_real_split_ams_hx_qualification/outcomes/reduced_stage4_real_split_summary.csv
docs/task013_real_split_ams_hx_qualification/outcomes/full_stage4_h2_real_split_validation.csv
docs/task013_real_split_ams_hx_qualification/outcomes/full_stage4_h2_vs_direct_rta.csv
docs/task013_real_split_ams_hx_qualification/outcomes/full_stage4_h1p5_breakthrough.csv
docs/task013_real_split_ams_hx_qualification/outcomes/solver_profile_ranking.md
docs/task013_real_split_ams_hx_qualification/outcomes/merge_recommendation.md
docs/task013_real_split_ams_hx_qualification/outcomes/next_decision.md
docs/task013_real_split_ams_hx_qualification/outcomes/parameters.json
docs/task013_real_split_ams_hx_qualification/outcomes/changed_files.md
docs/task013_real_split_ams_hx_qualification/outcomes/raw_runs/
```

## 更新文档

```text
docs/README.md
notes/reference/current_version_boundaries.md
notes/theory/maxwell_iterative_preconditioners_task012.md
```
