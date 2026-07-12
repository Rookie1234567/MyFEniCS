# 3D Stage2B PML 空气盒教程

## 1. 功能与物理图景

Stage2B 在双 Floquet 盒的 z 顶部和底部增加复坐标拉伸 PML，验证 3D 各向异性本构张量、PML cell tags 与开放边界装配路径。

## 2. 当前能力状态

```text
status = experimental_not_accuracy_qualified
path smoke = pass
analytic attenuation/reflection convergence = missing
recommended production boundary = no
```

## 3. 运行前提

先通过 Stage2A。PML 厚度必须由网格解析，且只在 PML cell tags 上使用拉伸张量。

## 4. PyCharm preset

```python
ACTIVE_PYCHARM_PRESET = "3d_stage2b_pml_smoke"
```

## 5. `main.py` 修改位置

```python
replace(
    STAGE2_NO_GRATING_3D,
    stage_case="pml_airbox",
    use_pml=True,
)
```

## 6. 完整参数示例

```python
Stage2NoGratingInputs3D(
    stage_case="pml_airbox",
    use_floquet_xy=True,
    use_pml=True,
    pml_top_thickness=250.0,
    pml_bottom_thickness=250.0,
    pml_alpha=5.0,
    nedelec_degree=1,
    mesh_target_size=300.0,
)
```

## 7. 参数含义

| 参数 | 单位 | 影响 |
|---|---|---|
| `pml_top/bottom_thickness` | nm | 吸收传播距离 |
| `pml_alpha` | 无量纲 | 复拉伸强度 |
| `mesh_target_size` | nm | PML 每层单元数 |
| `stage4_pml_outer_bc` | - | Stage4 诊断路径外边界，不等同本 smoke |
| `use_floquet_xy` | bool | 横向双周期 |

## 8. Qualification 边界

当前没有 PML 厚度/alpha/网格收敛，也没有解析反射误差，因此只能声明 assembly/solve path。不要在 capability matrix 写 supported accuracy。

## 9. CLI 等价命令

```text
python src/main.py --preset 3d_stage2b_pml_smoke \
  --results-root benchmarks/artifacts/cases/012
```

## 10. 真实调用链

```text
run_3d_cases::_run_stage_config
-> solve_maxwell_3d_stage_2b_pml_airbox::run_stage2b_pml_airbox_3d_case
-> mesh_builder_3d::build_airbox_mesh_3d
-> common_3d_forms::_build_variational_forms
-> pml_3d coefficient/tensor construction
-> direct solve/postprocess
```

## 11. 输出和字段

检查 `use_pml`、PML cell count/tags、stretch parameters、residual、max field、RSS 和完整配置。Case012 没有 canonical physical record。

## 12. ParaView

用 Threshold 分别显示 physical/PML cell tags，再画 `E_total_abs` 的 z 向 line plot。场应向外衰减，但仅目视衰减不构成精度 Gate。

## 13. 成功 Gate

```text
PML tags 非空
复杂本构装配成功
solve 完成、field 有限
Floquet constraints 仍通过
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| PML 区场不衰减 | tags/拉伸方向/符号错误 |
| 外边界反射明显 | 厚度、alpha 或网格不足 |
| 矩阵病态 | 拉伸过强且离散不足 |
| 用 smoke R/T 宣称精度 | 缺少 reference/convergence |

## 15. 如何形成精度 benchmark

固定解析平面波，扫描厚度、alpha 和 PML 网格，测量物理域反射与解析衰减；同时做至少两级 physical mesh。关闭这些 Gate 前保持 experimental。

## 16. 链接

- PML 理论：[`../theory/pml_robin_and_open_boundaries.md`](../theory/pml_robin_and_open_boundaries.md)
- 代码：[`../reference/code_walkthrough/21_3d_floquet_and_pml.md`](../reference/code_walkthrough/21_3d_floquet_and_pml.md)
- Case012：[`../../benchmarks/cases/012_3d_stage2b_pml/README.md`](../../benchmarks/cases/012_3d_stage2b_pml/README.md)
