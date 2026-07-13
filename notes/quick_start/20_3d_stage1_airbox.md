# 3D Stage1 均匀空气盒教程

## 1. 功能与物理图景

Stage1 在均匀 3D 空气盒中传播解析平面波，验证 N1curl 空间、curl-curl 弱式、入射方向、场重建和 direct solve，是所有 3D 功能的最低层基线。

## 2. 当前能力状态

```text
status = validated lightweight smoke
ordinary PyCharm default = yes
canonical record = Case010 Stage1 MPI2 reference
production grating claim = no
```

## 3. 运行前提

complex PETSc 镜像可用；第一次运行建议 serial 默认。要复核 canonical MPI 行为，使用 Case010 的 MPI2 脚本。

## 4. PyCharm preset

```python
ACTIVE_PYCHARM_PRESET = "3d_stage1_airbox_smoke"
```

无参数运行即选择它。

## 5. `main.py` 修改位置

`STAGE1_AIRBOX_3D = Stage1AirboxInputs3D()`。用户变体用 `replace` 创建新 preset，不改默认基线。

## 6. 完整参数块

```python
Stage1AirboxInputs3D(
    stage_case="stage1_airbox",
    case="normal",
    nedelec_degree=1,
    visualization_degree=1,
    mesh_target_size=5.0,
    lambda0=633.0,
    period_x=10.0,
    period_y=10.0,
    air_height=5.0,
    substrate_thickness=5.0,
)
```

## 7. 参数含义与资格影响

| 参数 | 单位 | 含义 | 改动后 |
|---|---|---|---|
| `period_x/y` | nm | 盒子横向尺寸 | 用户变体 |
| `air_height+substrate_thickness` | nm | z 总高度 | 用户变体 |
| `lambda0` | nm | 波长 | 需重新检查误差 |
| `case` | - | normal/oblique 基线 | 改变方向/偏振 |
| `nedelec_degree` | - | H(curl) 阶数 | 改 DoF |
| `mesh_target_size` | nm | 网格尺度 | 需网格收敛 |

## 8. Qualification 边界

Stage1 只证明均匀介质平面波和基础 3D 离散；它不证明 Floquet、PML、界面、DtN、grating 或 R/T/A。

## 9. CLI 等价命令

```text
python src/main.py --preset 3d_stage1_airbox_smoke
sh benchmarks/cases/010_3d_stage1_airbox/run.sh
```

Case010 脚本内部已经包含 `mpiexec -n 2`，不要再套一层 MPI。

## 10. 真实调用链

```text
run_3d_cases::main
-> run_3d_cases::_run_stage_config
-> solve_maxwell_3d_stage_1_airbox::run_stage1_airbox_3d_case
-> common_3d_case_flow::run_prepared_3d_case_flow
-> common_3d_forms::_build_variational_forms
-> common_3d_solve::_solve_direct
-> postprocess_3d::postprocess_3d_fields
```

## 11. 输出和 JSON

重点字段：`num_nedelec_dofs`、`linear_system_relative_residual`、`E_relative_error`、`H_relative_error`、`poynting_direction_cosine`、`total_peak_rss_mb`。

## 12. ParaView

serial 打开 `fields_3d_for_paraview.vtu`；MPI 打开 PVD。用 Slice 查看相位/幅值沿传播方向变化，用 Glyph 前确认矢量场方向。

## 13. 成功 Gate

```text
residual <= Case010 threshold
Poynting direction cosine 接近 1
E/H error 有限
MPI 输出完整
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| 默认运行很重 | preset 被改成 Stage4 |
| 方向余弦为负 | 入射方向/法向约定混淆 |
| MPI 只显示一块 | 打开 rank VTU 而非 PVD |
| p2 名字出现但预期 p1 | CLI 覆盖或旧结果目录 |

## 15. 从 Stage1 进入新案例

先改变盒子尺寸或入射方向并保持均匀材料，确认解析误差；需要周期边界时进入 Stage2A，不要在 Stage1 中偷偷加入 grating。

## 16. 链接

- 理论：[`../theory/maxwell_strong_weak_and_fem.md`](../theory/maxwell_strong_weak_and_fem.md)
- 代码：[`../reference/code_walkthrough/20_3d_staged_architecture.md`](../reference/code_walkthrough/20_3d_staged_architecture.md)
- Benchmark：[`../../benchmarks/cases/010_3d_stage1_airbox/README.md`](../../benchmarks/cases/010_3d_stage1_airbox/README.md)
