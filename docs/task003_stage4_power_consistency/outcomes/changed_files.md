# 本轮改动文件清单

## 代码

- `src/postprocessing/flat_layer_reference_3d.py`：新增 flat-layer 解析参考、参考面衰减和一致性 JSON 输出。
- `src/postprocessing/rta_3d.py`：将体吸收归一化从 `0.5*k0^2*Im(eps)*|E|^2` 修正为 `0.5*k0*Im(eps)*|E|^2`。
- `src/postprocessing/diffraction_3d.py`：probe E/H Fourier 与 E-only 诊断的有损基底 T 改为在 bottom probe plane 计算。
- `src/solvers/dtn_port_3d.py`：修正 auxiliary DtN traction 符号，底部有损端口投影分母和功率改为端口面口径。
- `src/solvers/common_3d_case_flow.py`：flat-layer case 自动输出 `flat_layer_reference.json` 和 `power_consistency.json`。
- `src/runners/run_3d_cases.py`：将 CLI 的 `--no-unique-output` 选择同步写入 `SimulationConfig3D.unique_output`，避免 `run_summary.json` 误报输出目录策略。
- `src/test/test_11_stage4_diffraction_modes.py`：新增 analytic-only probe/net_flux/volume absorption 测试。
- `src/test/test_14_stage4_dtn_modes.py`：新增 DtN 底部端口衰减、投影分母和 traction 符号测试。
- `src/test/test_13_3d_stage_entrypoints.py`：新增 3D runner 输出目录策略测试，确认默认保留 timestamp 唯一 `results/3D_*` 目录。

## 文档

- `notes/theory/THEORY_RTA_AND_VOLUME_ABSORPTION.md`：更新体吸收公式和 code-unit 推导说明。
- `docs/task003_stage4_power_consistency/outcomes/summary.md`：本轮结果总结，并补充 results 输出目录策略说明。
- `docs/task003_stage4_power_consistency/outcomes/metrics.csv`：本轮核心指标。
- `docs/task003_stage4_power_consistency/outcomes/parameters.json`：本轮参数与验证命令。
- `docs/task003_stage4_power_consistency/outcomes/run_log.txt`：本轮运行日志摘要，并记录后续保留完整 `results/` 目录的规则。
- `docs/task003_stage4_power_consistency/outcomes/raw_runs/flat_h10_auto/*`：h=10 auto 小型输出归档。
- `docs/task003_stage4_power_consistency/outcomes/raw_runs/flat_h5_auto/*`：h=5 auto 小型输出归档。
- `docs/task003_stage4_power_consistency/outcomes/supplement_small_cell.md`：10 nm 小 cell 补充验证说明。
- `docs/task003_stage4_power_consistency/outcomes/small_cell_metrics.csv`：10 nm 小 cell 多网格收敛指标。
- `docs/task003_stage4_power_consistency/outcomes/small_cell_parameters.json`：10 nm 小 cell 补充验证参数、关键结果和后续推荐运行命令。
- `docs/task003_stage4_power_consistency/outcomes/raw_runs/small_cell_h*/*`：小 cell 补充验证小型输出归档。

## 未改动

- 未修改 task 文件。
- 未生成或修改 review report。
- 未归档大型 VTU/BP/mesh 文件；完整运行结果仍保留在本地 `results/`，并继续由 `.gitignore` 排除在 Git 管理之外。
