# Changed Files

## 代码

- `src/solvers/dtn_port_3d.py`
  - 将 Stage 4 dtn_port official power source 改为 `dtn_port_modal_amplitudes`。
  - 为 `R_total/T_total` 增加 `R_total_dtn_port_modal/T_total_dtn_port_modal` 等显式别名。
  - 在 `port_power.json` / `port_power.csv` 中输出 modal metadata、total projection、incident projection、outgoing amplitude、boundary-plane amplitude 和 modal power。

- `src/solvers/common_3d_case_flow.py`
  - 保持 `summary["R_total"]` / `summary["T_total"]` 来自 DtN port modal metrics。
  - 将 E/H Fourier probe 和 sampled net flux 写入 diagnostic 字段。
  - 在体吸收计算后回写 `R_plus_T_plus_A_volume_dtn_port_modal` 和 `energy_closure_error_dtn_port_modal_volume` 到 `port_power.json` / `dtn_port_power_metrics_3d.json`。

- `src/postprocessing/diffraction_3d.py`
  - 将 probe-plane E/H Fourier power source 改为 `diagnostic_eh_fourier_probe`。
  - 增加 `diagnostic_e_only_fourier_probe` 和 `diagnostic_sampled_net_flux` 命名。
  - 保留 `R_total/T_total` legacy alias，但明确它们在该函数内只是 diagnostic。

- `src/postprocessing/rta_3d.py`
  - `power_summary.csv` 中 port row 使用 `dtn_port_modal_amplitudes`。
  - probe row 和 net-flux row 改为 diagnostic role/source。

- `src/studies/run_3d_matrix_scale.py`
  - 输出 CSV 增加 official dtn-port-modal 字段和 diagnostic probe/flux 字段。

- `src/test/test_11_stage4_diffraction_modes.py`
  - 更新 probe power source 测试，确认 E/H Fourier probe 是 diagnostic。

- `src/test/test_14_stage4_dtn_modes.py`
  - 新增 DtN port modal official alias 测试。

## 文档

- `README.md`
  - 更新当前分支和 task007 official power source 说明。

- `docs/README.md`
  - 更新 task007 状态和 outcome 入口。

- `notes/reference/current_version_boundaries.md`
  - 新增 task007 official DtN port modal 口径和 height scan 解释边界。

- `notes/theory/stage4_3d_dtn_port.md`
  - 新增 2026-07-06 official R/T/A 口径说明。

## 本轮 Outcomes

- `docs/task007_dtn_port_modal_official_rta/outcomes/summary.md`
- `docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_modal_investigation.md`
- `docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_power_formula.md`
- `docs/task007_dtn_port_modal_official_rta/outcomes/flat_layer_port_modal_validation.csv`
- `docs/task007_dtn_port_modal_official_rta/outcomes/block_grating_port_modal_vs_eh_probe.csv`
- `docs/task007_dtn_port_modal_official_rta/outcomes/reduced_vs_original_port_modal_comparison.csv`
- `docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_official_rta.csv`
- `docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_diagnostic_probe_rta.csv`
- `docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_resource.csv`
- `docs/task007_dtn_port_modal_official_rta/outcomes/diagnostic_probe_comparison.csv`
- `docs/task007_dtn_port_modal_official_rta/outcomes/port_power_schema_example.json`
- `docs/task007_dtn_port_modal_official_rta/outcomes/parameters.json`
- `docs/task007_dtn_port_modal_official_rta/outcomes/run_log.txt`
- `docs/task007_dtn_port_modal_official_rta/outcomes/changed_files.md`
- `docs/task007_dtn_port_modal_official_rta/outcomes/raw_runs/`
