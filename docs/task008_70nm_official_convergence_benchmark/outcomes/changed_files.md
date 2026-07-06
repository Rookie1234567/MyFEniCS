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

## Review 后收尾

- 删除 `raw_runs/` 中 0-byte 的空 `stderr_tail.txt` 占位文件，仅保留有实际内容的轻量运行记录。
- 微调 `summary.md`、`README.md`、`docs/README.md` 和 `notes/reference/current_version_boundaries.md` 中关于 `p=2 h=2` 与 `p=2 h=5` 的表述：`p=2 h=2` 是当前个人电脑 best-effort direct benchmark，不是最终网格收敛物理解；`p=2 h=5` 的高 R 只作为粗网格敏感性参考。

## 项目说明文档

- `README.md`
- `docs/README.md`
- `notes/reference/current_version_boundaries.md`
