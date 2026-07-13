# 3D Stage4A 平坦有损层 DtN 教程

## 1. 功能与物理图景

Stage4A 在 10 x 10 x 10 nm 平坦周期单元中加入 complex substrate、双 Floquet 和 3D auxiliary DtN port，用于验证 modal R/T、volume absorption 与能量闭合，避免 grating 几何掩盖功率错误。

## 2. 当前能力状态

```text
status = test_backed_energy_sanity
geometry = flat layer
official R/T = 3D DtN auxiliary amplitudes
official A = volume absorption
full mesh convergence = not claimed
```

## 3. 运行前提

必须使用 complex PETSc；port 两侧应是均匀层。先运行 Stage1/2A，确认基础 H(curl) 和 Floquet。

## 4. PyCharm preset

```python
ACTIVE_PYCHARM_PRESET = "3d_stage4a_flat_layer_direct"
```

该案例 p=1、h=2 nm，属于轻量 sanity。

## 5. `main.py` 修改位置

`_STAGE4_FLAT_3D` 由 demo Stage4 配置派生并覆盖 flat geometry、10 nm 周期、上下各 5 nm、p=1、h=2 nm。

## 6. 完整参数块

```python
replace(
    STAGE4_GRATING_3D,
    stage_case="stage4_flat_layer_sanity",
    nedelec_degree=1,
    mesh_target_size=2.0,
    period_x=10.0,
    period_y=10.0,
    air_height=5.0,
    substrate_thickness=5.0,
    stage4_boundary_model="dtn_port",
)
```

## 7. 参数含义

| 参数 | 作用 |
|---|---|
| `n_substrate` | complex epsilon 与吸收 |
| `air_height/substrate_thickness` | port plane/吸收积分域 |
| `stage4_dtn_order_policy` | 当前 flat sanity 可用 zero order |
| `stage4_dtn_assembly` | 3D 当前 auxiliary |
| `diffraction_probe_fraction` | diagnostic sample plane |
| `mesh_target_size` | 功率和 A_volume 精度 |

## 8. Qualification 边界

平坦层 sanity 不证明 block grating 或 target h5/h3/h2 收敛。改变尺寸理论上不改无限平面物理，但有限元网格和 port 位置会改变离散误差。

## 9. CLI 等价命令

```text
python src/main.py --preset 3d_stage4a_flat_layer_direct \
  --results-root benchmarks/artifacts/cases/020
```

## 10. 真实调用链

```text
run_3d_cases::_run_stage_config
-> solve_maxwell_3d_stage_4a_flat_layer_sanity::run_stage4a_flat_layer_sanity_3d_case
-> dtn_port_3d::solve_stage4_dtn_port_total_field
-> augmented F/C/D/H solve
-> common_3d_postprocess / diffraction_3d
```

## 11. 输出与字段

查看 `num_nedelec_dofs`、`num_auxiliary_dofs`、linear residual、`R_total/T_total/A_volume_total`、`R_plus_T_plus_A_volume`、energy closure 和 modal orders。

## 12. ParaView

打开 3D VTU/PVD，用横向 Slice 检查场在平坦界面前后变化；用 material tag Threshold 确认没有意外 grating cell。

## 13. 成功 Gate

```text
linear residual <= 1e-8
R,T,A >= 0
abs(1-R-T-A) <= 1e-6
auxiliary amplitude 可回代
probe 仅作 diagnostic
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| 出现 grating 衍射 | stage_case/geometry 未切 flat |
| T=0 或 A≈1 | port mode/功率平面错误 |
| A_volume 与 balance 不同 | 材料标签或吸收积分域错误 |
| 跑成大规模 | period/height 没有覆盖为 10/5/5 |

## 15. 从 flat 进入新层状案例

一次增加一个层或材料，保持横向均匀并与 transfer-matrix/Fresnel 参考比较；通过后再进入 Stage4B grating。

## 16. 链接

- Stage 理论：[`../theory/3d_stages_and_validation_ladder.md`](../theory/3d_stages_and_validation_ladder.md)
- RTA：[`../theory/official_and_diagnostic_rta_methods.md`](../theory/official_and_diagnostic_rta_methods.md)
- 代码：[`../reference/code_walkthrough/22_3d_dtn_augmented_system.md`](../reference/code_walkthrough/22_3d_dtn_augmented_system.md)
- Case020：[`../../benchmarks/cases/020_3d_stage4a_flat_dtn/README.md`](../../benchmarks/cases/020_3d_stage4a_flat_dtn/README.md)
