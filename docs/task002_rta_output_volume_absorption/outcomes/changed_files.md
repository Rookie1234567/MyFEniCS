# Changed Files

## 代码

- `src/postprocessing/rta_3d.py`：新增 3D 材料体吸收积分与 `power_summary.csv` 生成。
- `src/postprocessing/diffraction_3d.py`：新增 `probe_power.json` 和 `flux_power.json` 正式输出。
- `src/solvers/dtn_port_3d.py`：新增 `port_power.json` 正式输出。
- `src/solvers/common_3d_case_flow.py`：DtN port 完成后运行 probe/net-flux/volume 后处理，并写总览 CSV。

## 文档

- `notes/docs/THEORY_RTA_AND_VOLUME_ABSORPTION.md`：解释四类 R/T/A 口径和体吸收定义。

## Outcomes

- `notes/outcomes/20260702_rta_output_volume_absorption/summary.md`
- `notes/outcomes/20260702_rta_output_volume_absorption/metrics.csv`
- `notes/outcomes/20260702_rta_output_volume_absorption/parameters.json`
- `notes/outcomes/20260702_rta_output_volume_absorption/run_log.txt`
- `notes/outcomes/20260702_rta_output_volume_absorption/changed_files.md`

## 未提交的大文件

- `results/` 下的 case 输出用于本地复核，但按 `.gitignore` 不提交。
