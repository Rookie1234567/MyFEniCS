# 改动文件清单

## 新增

- `notes/docs/CODEX_TASK_20260703_stage4_validation_cleanup.md`
- `notes/docs/REVIEW_REPORT_20260703_stage4_validation_cleanup.md`
- `notes/outcomes/20260703_stage4_validation_cleanup/summary.md`
- `notes/outcomes/20260703_stage4_validation_cleanup/metrics.csv`
- `notes/outcomes/20260703_stage4_validation_cleanup/parameters.json`
- `notes/outcomes/20260703_stage4_validation_cleanup/run_log.txt`
- `notes/outcomes/20260703_stage4_validation_cleanup/changed_files.md`

## 修改

- `notes/README.md`：增加当前 Stage 4 验证口径说明。
- `src/common/config_3d.py`：增加 EUV 13.5 nm、Si 基座/光栅复折射率、材料标签和验证角色字段。
- `src/common/modes_3d.py`：修复 lossy substrate 中复数 `beta` 的传播级识别，确保透射零级计入 R/T。
- `src/main.py`：PyCharm 3D Stage 4 输入改为 Si 基座和 Si 光栅复折射率，并传递材料标签和验证角色。
- `src/postprocessing/diffraction_3d.py`：统一 probe 后处理官方 R/T 来源为 E/H Fourier，E-only 和 net flux 标为诊断。
- `src/runners/run_3d_cases.py`：Stage 4 默认基座和光栅材料改为 Si 复折射率，CLI 增加材料标签和验证角色。
- `src/runners/run_3d_airbox_old.py`：旧 3D 入口同步材料标签和验证角色，避免误读。
- `src/solvers/common_3d_case_flow.py`：运行日志头部打印材料、波长、验证角色和吸收余额。
- `src/solvers/common_3d_postprocess.py`：有吸收材料时将 `A_balance = 1-R-T` 解释为吸收/损耗余额。
- `src/solvers/common_3d_utils.py`：summary 顶层增加 `physical_benchmark_candidate` 等字段。
- `src/test/diagnose_p2_mpc_constraints.py`：旧 633 nm / 实数折射率诊断标记为 `numerical_sanity_only`。
- `src/test/stage2_test_utils.py`：Stage 4 测试默认基座和光栅材料改为 Si 复折射率。
- `src/test/stage4_2p5d_compare.py`：旧 2.5D 对照标记为数值 sanity。
- `src/test/test_11_stage4_diffraction_modes.py`：增加官方 R/T 来源和 lossy zero-order 传播识别单元测试。
- `src/test/test_13_3d_stage_entrypoints.py`：增加 PyCharm 3D 参数中的 Si 基座/光栅复折射率检查。

## 删除

无。
