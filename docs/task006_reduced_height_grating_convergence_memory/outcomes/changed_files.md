# 本轮改动文件清单

## 源码

- `src/studies/run_3d_matrix_scale.py`：补充 task006 几何/材料参数透传、R/T/A 与衍射级字段、失败进度 fallback、增量 CSV 写入。
- `src/studies/run_3d_memory_profile.py`：新增 diagnostic-only 内存监控脚本，记录进程树 RSS、swap、OOC 磁盘和 progress stage。
- `src/postprocessing/diffraction_3d.py`：修正真实光栅 reduced-height domain 的自动 top probe 位置，使其落在光栅顶面和 top boundary 之间。
- `src/test/test_11_stage4_diffraction_modes.py`：更新 probe 位置测试，并新增 70 nm reduced-height 保护用例。
- `.gitignore`：允许 `docs/**/outcomes/**/*.csv` 作为轻量任务结果提交。

## Outcomes

- 生成 task006 下的 assemble/direct/OOC/MPI/RTA/衍射级/70-vs-150/memory-profile/failure-boundary/summary/raw_runs 等轻量结果文件。
