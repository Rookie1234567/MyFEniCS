# 本轮改动文件清单

## 代码

- `.gitignore`：允许 `docs/**/outcomes/**/*.csv` 被 Git 记录，同时继续忽略 `results/` 大体积运行输出。
- `src/postprocessing/diffraction_3d.py`：修正真实 block grating 的自动 top probe 位置，避免 probe 落入光栅内部。
- `src/studies/run_3d_matrix_scale.py`：扩展几何、材料、R/T/A、progress fallback、增量 CSV 和资源诊断字段。
- `src/studies/run_3d_memory_profile.py`：新增进程树 RSS/swap/OOC scratch 采样脚本。
- `src/solvers/common_3d_solve.py`：修正 MUMPS OOC profile 和 PETSc extra options 的覆盖顺序。
- `src/test/test_11_stage4_diffraction_modes.py`：补充 reduced-height probe 位置测试。
- `src/test/test_18_3d_direct_solver_profile_cleanup.py`：补充 `mat_mumps_icntl_14` 覆盖测试。

## 文档

- `README.md`
- `docs/README.md`
- `notes/reference/current_version_boundaries.md`
- `docs/task006_reduced_height_grating_convergence_memory/outcomes/summary.md`
- `docs/task006_reduced_height_grating_convergence_memory/outcomes/failure_boundary.md`
- `docs/task006_reduced_height_grating_convergence_memory/outcomes/run_log.txt`
- `docs/task006_reduced_height_grating_convergence_memory/outcomes/parameters.json`

## 结果数据

- `assemble_matrix_scale.csv`
- `direct_default_scale.csv`
- `mumps_ooc_scale.csv`
- `mumps_ooc_tuned_extra_scale.csv`
- `workstation_recommendation.csv`
- `memory_profile_summary.csv`
- `memory_profile_timeseries.csv`
- `rta_convergence.csv`
- `reduced_vs_original_domain_comparison.csv`
- `raw_runs/` 轻量运行记录
