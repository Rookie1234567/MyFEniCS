# Changed Files

## 代码

- `src/studies/run_3d_matrix_scale.py`：为 task008 的 matrix-scale/direct scan 增加入射角参数透传，并在 CSV 中记录 kx/ky/kz、Floquet phase、polarization、elapsed/max RSS/mode count 等字段。
- `src/solvers/dtn_port_3d.py`：assemble-only DtN port 结果现在也写出 top/bottom/propagating mode count，避免后续资源表字段为空。

## Task008 outcomes

- `summary.md`
- `geometry_validation.md`
- `oblique_incidence_validation.md`
- `assemble_matrix_scale.csv`
- `direct_solve_plan.md`
- `official_convergence.csv`
- `official_convergence_with_deltas.csv`
- `resource_convergence.csv`
- `p1_convergence.csv`
- `p2_convergence.csv`
- `p1_vs_p2_comparison.csv`
- `diagnostic_comparison.csv`
- `failure_boundary.csv`
- `failure_boundary.md`
- `parameters.json`
- `run_log.txt`
- `changed_files.md`
- `raw_runs/`

## 项目说明文档

- `README.md`
- `docs/README.md`
- `notes/reference/current_version_boundaries.md`
