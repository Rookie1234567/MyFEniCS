# Task034 post-merge hardening 审计

## 结论

任务书列出的五组 selective-merge 后风险均已实现 fail-closed 修复并由测试覆盖；ordinary defaults 未改变。numerical blob 审计状态为 `numerical_blob_compatibility_pass`，有意改变的数值路径没有仅凭静态检查放行，而由后续 WSL PDE 锚点重新资格化。

| 风险 | 修复与边界 | 验证 | 状态 |
|---|---|---|---|
| 高阶 Floquet topology cache 生命周期 | owner 改为 weak reference；显式 clear；验证命中、释放和对象 id 复用边界 | 生命周期/回归测试 | closed |
| active-column 全局 Python `allgather` | 统计改为 distributed numeric reduction，不收集 Python object payload | MPI2/MPI4 测试 | closed |
| WSL/shared-host watchdog | 识别 cgroup root；以进程树 memory/swap 为作业权威；终止后 drain terminal output | watchdog 单测与正式作业记录 | closed |
| source-clean | tracked 修改与所有 nonignored untracked 文件均 fail closed | clean-source 测试及每次 heavy launch Gate | closed |
| evidence-to-current-checkout | 逐 numerical blob SHA-256 分类；需要重跑的 kernel 显式列出 | `numerical_blob_compatibility.json` | pass |

## 数值 blob 边界

审计记录：`docs/task034_workstation_wsl_adaptive_scalability/outcomes/numerical_blob_compatibility.json`。

- base 精确绑定 `82a5107b5c2bfe4c466a0d00ead31d7b172e2af4`。
- `mode_classification.py`、`hybrid_fem_modal_schur_direct.py`、`hcurl_multilevel.py` 被分类为需要相应 PDE rerun；不是“注释/诊断变化”。
- Case093、p3/h3 和 p4/h5 的 fresh WSL Full3D/Hybrid/QEP 证据完成对应资格化。
- cache、watchdog、factorization-only 和 source-clean 变化均为显式 opt-in 或诊断/lifecycle 路径；普通求解默认仍走原路径。

## API 与失败语义

assembly-only、factorization-only 和 full-solve 使用独立状态；factorization-only 不进入 `KSPSolve`，失败不会被 full-solve 结果覆盖。所有受控负结果保留原始状态和固定阈值，未通过的 adaptive/research path 不列为默认 merge candidate。

## 已知非 Task034 Ruff 边界

全仓 `ruff check .` 仍报告 15 个既有、与 Task034 无关的问题，位于 `src/postprocessing/diffraction_3d.py`、`full3d_reference.py`、`hybrid_field_reconstruction.py`、`src/solvers/solve_maxwell_3d_common_old.py` 和 `src/studies/run_3d_memory_profile.py`。Task034 变更文件的 scoped Ruff 通过；本任务没有借机改写这些历史文件。
