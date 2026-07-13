# Changed Files

## 代码

| 文件 | 变更 |
|---|---|
| `src/studies/run_task021_target_aux_coarse.py` | 新增 target-geometry p=1/p=2 h=5 research runner；输出 baseline、mode mapping、aux-only、FE response、Schur PC 和 gate CSV |
| `src/postprocessing/postprocess.py` | 在 `save_mesh_plots()` 中增加 PyVista 缺失显式检查 |

## 文档和结果

| 文件 | 变更 |
|---|---|
| `docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/*.csv` | 新增 task021 数值结果 |
| `docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/parameters.json` | 新增可复现实验参数 |
| `docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/raw_runs/` | 新增轻量 residual history 和 system metadata |
| `docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/summary.md` | 新增中文总结 |
| `docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/solver_profile_ranking.md` | 新增 solver profile 比较表 |
| `docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/merge_recommendation.md` | 新增合并建议 |
| `docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/next_decision.md` | 新增下一任务建议 |
| `docs/README.md` | 更新任务索引和最新结论 |
| `notes/theory/maxwell_iterative_preconditioners_task012.md` | 补充 task021 理论判断 |

## 未提交内容

`papers/` 为本地论文资料目录，保持 untracked，不纳入本轮提交。
