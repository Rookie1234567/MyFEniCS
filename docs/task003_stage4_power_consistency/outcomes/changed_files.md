# 本轮改动文件清单

## 代码

- `src/postprocessing/flat_layer_reference_3d.py`：新增 flat-layer 解析参考、参考面衰减和一致性 JSON 输出。
- `src/postprocessing/rta_3d.py`：将体吸收归一化从 `0.5*k0^2*Im(eps)*|E|^2` 修正为 `0.5*k0*Im(eps)*|E|^2`。
- `src/postprocessing/diffraction_3d.py`：probe E/H Fourier 与 E-only 诊断的有损基底 T 改为在 bottom probe plane 计算。
- `src/solvers/dtn_port_3d.py`：修正 auxiliary DtN traction 符号，底部有损端口投影分母和功率改为端口面口径。
- `src/solvers/common_3d_case_flow.py`：flat-layer case 自动输出 `flat_layer_reference.json` 和 `power_consistency.json`。
- `src/test/test_11_stage4_diffraction_modes.py`：新增 analytic-only probe/net_flux/volume absorption 测试。
- `src/test/test_14_stage4_dtn_modes.py`：新增 DtN 底部端口衰减、投影分母和 traction 符号测试。

## 文档

- `notes/theory/THEORY_RTA_AND_VOLUME_ABSORPTION.md`：更新体吸收公式和 code-unit 推导说明。
- `docs/task003_stage4_power_consistency/outcomes/summary.md`：本轮结果总结。
- `docs/task003_stage4_power_consistency/outcomes/metrics.csv`：本轮核心指标。
- `docs/task003_stage4_power_consistency/outcomes/parameters.json`：本轮参数与验证命令。
- `docs/task003_stage4_power_consistency/outcomes/run_log.txt`：本轮运行日志摘要。
- `docs/task003_stage4_power_consistency/outcomes/raw_runs/flat_h10_auto/*`：h=10 auto 小型输出归档。
- `docs/task003_stage4_power_consistency/outcomes/raw_runs/flat_h5_auto/*`：h=5 auto 小型输出归档。

## 未改动

- 未修改 task 文件。
- 未生成或修改 review report。
- 未归档大型 VTU/BP/mesh 文件。
