# 3D Stage2C Fresnel 界面教程

## 1. 功能与物理图景

Stage2C 在双周期域中加入平坦空气/基底界面和 scattered-field 分解，目标是对照 Fresnel 反射/透射并验证材料标签、界面连续性和开放边界路径。

## 2. 当前能力状态

`status=experimental_not_accuracy_qualified`。界面代码和 smoke 存在，但当前粗网格结果未形成 Fresnel 精度/角度/偏振 convergence record。

## 3. 运行前提

先通过 Stage2A；基底材料和界面位置必须与背景场一致。该 preset 同时使用 Floquet 和 PML 路径。

## 4. PyCharm preset

```python
ACTIVE_PYCHARM_PRESET = "3d_stage2c_fresnel_smoke"
```

## 5. `main.py` 修改位置

```python
replace(
    STAGE2_NO_GRATING_3D,
    stage_case="fresnel_interface",
    use_floquet_xy=True,
    use_pml=True,
)
```

## 6. 完整参数示例

```python
Stage2NoGratingInputs3D(
    stage_case="fresnel_interface",
    case="normal",
    lambda0=633.0,
    n_substrate=1.45,
    use_floquet_xy=True,
    use_pml=True,
    nedelec_degree=1,
    mesh_target_size=300.0,
)
```

## 7. 参数含义

| 参数 | 物理作用 |
|---|---|
| `n_substrate` | Fresnel impedance/wave number |
| `incident_theta/phi_deg` | 入射面与角度 |
| `polarization_kind` | s/p/custom |
| `air_height/substrate_thickness` | 界面两侧域厚 |
| `pml_*` | z 截断 |
| `scattering_background` | layered incident/background field |

## 8. Qualification 边界

改变角度或偏振后必须与对应 Fresnel 解析式对照；normal smoke 通过不能外推到 grazing incidence。PML 精度仍继承 Stage2B 限制。

## 9. CLI 等价命令

```text
python src/main.py --preset 3d_stage2c_fresnel_smoke \
  --results-root benchmarks/artifacts/cases/013
```

## 10. 真实调用链

```text
run_3d_cases::_run_stage_config
-> solve_maxwell_3d_stage_2c_fresnel_interface::run_stage2c_fresnel_interface_3d_case
-> material/background construction
-> common_3d_forms::_build_variational_forms
-> Floquet + PML constraints
-> direct solve / Fresnel diagnostics
```

## 11. 输出和字段

检查 material tags、interface z、incident/reflected/transmitted reference、residual、field errors 和 PML diagnostics。Case013 明确没有 canonical accuracy record。

## 12. ParaView

用 z-normal Slice 查看界面两侧场，固定色标；用 Plot Over Line 穿过界面，检查切向 E 连续与波长变化。不要从颜色图手算 R/T。

## 13. 成功 Gate

```text
air/substrate tags 与界面位置正确
scattered-field solve 完成
场有限、residual 通过 smoke 阈值
解析 Fresnel accuracy 尚不作为当前 pass 条件
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| 界面出现不合理跳变 | 材料/切向迹/背景定义错误 |
| R/T 与解析式偏差大 | 粗网格、PML 或功率口径 |
| s/p 结果混淆 | 入射面和 polarization vector 定义错误 |
| 宣称 supported | 忽略 experimental 状态 |

## 15. 如何关闭精度资格

至少对 normal 和一个 oblique s/p 案例做网格收敛，对比解析 Fresnel R/T、角度和场；同时做 PML 参数收敛。完成前不升级状态。

## 16. 链接

- staged 理论：[`../theory/3d_stages_and_validation_ladder.md`](../theory/3d_stages_and_validation_ladder.md)
- 代码：[`../reference/code_walkthrough/20_3d_staged_architecture.md`](../reference/code_walkthrough/20_3d_staged_architecture.md)
- Case013：[`../../benchmarks/cases/013_3d_stage2c_fresnel/README.md`](../../benchmarks/cases/013_3d_stage2c_fresnel/README.md)
