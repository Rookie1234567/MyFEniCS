# Outcome Summary

## Task

task007_dtn_port_modal_official_rta：把 Stage 4 `dtn_port` 主线官方 R/T/A 改为直接来自 DtN port modal amplitudes，并把 probe-plane fitting / sampled field 方法全部降级为 diagnostic。

## Branch

`codex/20260704-dtn-port-modal-official-rta`

## Changed Files

核心代码：

- `src/solvers/dtn_port_3d.py`
- `src/solvers/common_3d_case_flow.py`
- `src/postprocessing/diffraction_3d.py`
- `src/postprocessing/rta_3d.py`
- `src/studies/run_3d_matrix_scale.py`
- `src/test/test_11_stage4_diffraction_modes.py`
- `src/test/test_14_stage4_dtn_modes.py`

本轮 outcome 文件见 `docs/task007_dtn_port_modal_official_rta/outcomes/`。

## Run Commands

所有运行均在 Docker `code-dolfinx-mpc:latest` 中执行，并先启用：

```text
. dolfinx-complex-mode
```

已完成：

- `python3 -m compileall -q src`
- `python3 -m unittest src.test.test_11_stage4_diffraction_modes src.test.test_14_stage4_dtn_modes`
- flat-layer p=1 h=5
- flat-layer p=2 h=5
- block grating height scan：70 / 110 / 130 / 150 nm，p=2 h=5 MPI=8
- optional：70 nm p=1 h=5 MPI=8
- optional：70 nm p=2 h=4 MPI=8
- zero-contrast smoke：70 nm p=1 h=5 MPI=8，`n_grating=1+0j`

完整 result directory 清单见 `run_log.txt`。

## Physical Model

主线设置：

- `lambda0 = 13.5 nm`
- `period_x = period_y = 100 nm`
- block grating：`50 nm x 50 nm x 50 nm`
- `n_substrate = 0.999002304859 + 0.00182649365j`
- real Si grating：`n_grating = 0.999002304859 + 0.00182649365j`
- normal incidence，`polarization_kind = s`
- `stage4_boundary_model = dtn_port`
- `stage4_dtn_assembly = auxiliary`
- `stage4_dtn_order_policy = auto_propagating`
- official power source：`dtn_port_modal_amplitudes`

height scan 几何：

| total height nm | substrate nm | top air above grating nm | air_height nm |
|---:|---:|---:|---:|
| 70 | 10 | 10 | 60 |
| 110 | 30 | 30 | 80 |
| 130 | 40 | 40 | 90 |
| 150 | 50 | 50 | 100 |

## Numerical Settings

主线 height scan 使用：

- Nedelec degree `p=2`
- `mesh_target_size = 5 nm`
- MPI ranks = 8
- direct LU，实际 factor solver 为 MUMPS
- DtN auxiliary mode count = 708

## Key Results

official height scan 结果：

| height nm | R_port | T_port | A_volume | R+T+A |
|---:|---:|---:|---:|---:|
| 70 | 7.079669e-04 | 9.646033e-01 | 3.468869e-02 | 1.0000000000000075 |
| 110 | 5.431444e-05 | 9.349102e-01 | 6.503548e-02 | 1.0000000000000018 |
| 130 | 2.212366e-05 | 9.202230e-01 | 7.975483e-02 | 1.0000000000000149 |
| 150 | 1.960416e-04 | 9.054207e-01 | 9.438328e-02 | 0.9999999999999692 |

70 nm 与 150 nm 在 official port modal 口径下仍不同：`T_port` 从 `0.964603` 降到 `0.905421`，`A_volume` 从 `0.034689` 增到 `0.094383`。这符合当前 reference plane 定义，因为 bottom port 位于 `physical_z_min`，substrate 越厚，有损 Si 中到 port plane 的传播衰减越多。

## Diagnostic Probe Comparison

70 nm p=2 h=5：

| method | R | T | A |
|---|---:|---:|---:|
| official DtN port modal | 7.079669e-04 | 9.646033e-01 | 3.468869e-02 |
| diagnostic E/H Fourier probe | 1.630145e-02 | 7.522551e-01 | 2.314434e-01 |
| diagnostic sampled net flux | 2.350566e-01 | 7.417808e-01 | 2.316260e-02 |

130 nm 的 diagnostic E/H Fourier probe 出现 `T > 1` 和负 `A_balance`，说明 probe-plane fitting 在这些粗网格/采样条件下不应作为 official R/T/A。

## Energy Check

本轮所有完成的 official DtN port modal 运行均满足：

```text
R_total_dtn_port_modal + T_total_dtn_port_modal + A_volume_total - 1 ~= 0
```

主线 height scan 的闭合误差量级为 `1e-14` 到 `3e-14`。

## Mesh / DoF / Solver Cost

height scan 资源：

| height nm | cells | dofs | matrix rows | nnz | elapsed s | max RSS MB |
|---:|---:|---:|---:|---:|---:|---:|
| 70 | 5600 | 142188 | 142896 | 1.880322e7 | 89.696 | 2206.9 |
| 110 | 8800 | 221564 | 222272 | 2.721855e7 | 305.382 | 2106.5 |
| 130 | 10400 | 261252 | 261960 | 3.142621e7 | 490.162 | 2725.0 |
| 150 | 12000 | 300940 | 301648 | 3.563388e7 | 617.119 | 2620.2 |

optional 70 nm p=2 h=4 完成，`cells=13851`，`dofs=346610`，`elapsed=1082.256 s`，`max RSS=2497.5 MB`。结果为 `R=1.000623e-06`，`T=0.9638547`，`A_volume=0.0361443`，闭合误差 `-2.95e-14`。

## Known Issues

- `diffraction_3d.py` 为兼容旧调用仍返回 `R_total/T_total` legacy alias，但 `power_source` 已是 `diagnostic_eh_fourier_probe`。Stage 4 dtn_port 的 `run_summary.json` 中 official `R_total/T_total` 来自 `dtn_port_modal_amplitudes`。
- 当前 official `T_total` 是 bottom physical port plane 的功率。若未来要比较不同 truncation height 下的同一物理界面透射，应新增“统一 reference plane”或界面处外推功率，而不是直接比较不同 bottom port plane 上的 `T_total`。
- 本轮 p=2 h=5 height scan 是数值验证和口径整理，不应直接作为最终物理 benchmark。

## Next Questions for Review

- ChatGPT 审查时请优先检查：`dtn_port_3d.py` 中 auxiliary total projection 到 outgoing amplitude 的转换是否清晰且无符号混乱。
- 请确认 `port_power.json` / `run_summary.json` 的 official 字段是否足够明确，是否还需要删除或进一步标记 `diffraction_total_power_source` 这个 legacy 字段。
- 请判断是否需要下一轮新增 common-reference-plane 后处理，用于把不同 height 的 bottom power 外推到同一 substrate 深度或界面处再比较。
