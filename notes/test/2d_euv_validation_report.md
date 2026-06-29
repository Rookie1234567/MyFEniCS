# 2D EUV 光栅验证报告

## 2026-06-29 更新：完整 method / mesh / thickness validation 已跑完

本轮按照验证计划把 2D EUV 光栅 DtN 主线完整跑了一遍，没有因为额度不足中断。

已完成：
```text
1. method_compare
   目录：results/studies/2D_EUV_method_compare_20260629_020935
   结论：DtN auxiliary 与 DtN explicit 在 triangle / quadrilateral 上结果一致。

2. mesh_convergence
   目录：results/studies/2D_EUV_mesh_convergence_20260629_021059
   结论：triangle h=1.0 nm 已满足连续两次核心指标变化小于 0.1%；
        quadrilateral h=1.0 nm 仍未达到这个严格阈值，只作为对照。

3. air_scan
   目录：results/studies/2D_EUV_air_scan_20260629_021811
   使用：triangle, h=1.0 nm

4. substrate_scan
   目录：results/studies/2D_EUV_substrate_scan_20260629_022910
   使用：triangle, h=1.0 nm

5. combined_scan
   目录：results/studies/2D_EUV_combined_scan_20260629_023718
   使用：triangle, h=1.0 nm

6. 编译与单元测试
   python3 -m compileall -q src
   python3 -m unittest discover -s src/test -p "test_*.py"
   结果：Ran 48 tests, OK (skipped=8)
```

未完成：
```text
无。
```

### 方法对比

固定参数：`period_x=100 nm`，`air_height=100 nm`，`substrate_thickness=50 nm`，`grating=50 x 50 nm`，`lambda0=13.5 nm`，`TM`，法向入射，`n_substrate=1.1`，`n_grating=1.2`。

```text
triangle, h=4 nm:
  DtN auxiliary R/T/R+T = 4.307971e-03 / 9.956920e-01 / 1.000000e+00
  DtN explicit  R/T/R+T = 4.307971e-03 / 9.956920e-01 / 1.000000e+00
  Robin 诊断    R/T/R+T = 4.872214e-03 / 7.580139e-01 / 7.628861e-01

quadrilateral, h=4 nm:
  DtN auxiliary R/T/R+T = 6.943688e-03 / 9.930563e-01 / 1.000000e+00
  DtN explicit  R/T/R+T = 6.943688e-03 / 9.930563e-01 / 1.000000e+00
  Robin 诊断    R/T/R+T = 6.408301e-03 / 7.088834e-01 / 7.152917e-01
```

判断：正式功率结果以 DtN auxiliary 或 DtN explicit 为准。Robin/probe-line 只保留为历史诊断路径，在这个 EUV 多衍射级问题中不能作为正式 R/T。

### 网格收敛

triangle 收敛表：
```text
h=4.0 nm   dofs=10662   R=4.307971e-03   T=9.956920e-01   I_grating=2477.358806
h=3.0 nm   dofs=18022   R=4.410719e-03   T=9.955893e-01   I_grating=2473.089271
h=2.0 nm   dofs=38502   R=4.468479e-03   T=9.955315e-01   I_grating=2473.589425
h=1.5 nm   dofs=69700   R=4.479036e-03   T=9.955210e-01   I_grating=2473.817527
h=1.25 nm  dofs=96400   R=4.481090e-03   T=9.955189e-01   I_grating=2473.877023
h=1.0 nm   dofs=150500  R=4.482375e-03   T=9.955176e-01   I_grating=2473.913568
```

triangle 最近两次相对变化：
```text
h=1.5 -> 1.25 nm: max relative change = 4.586e-04
h=1.25 -> 1.0 nm: max relative change = 2.867e-04
```

这满足本轮设定的严格判据：连续两次核心指标变化小于 `0.1%`。

quadrilateral 收敛较慢：
```text
h=1.25 -> 1.0 nm: max relative change = 2.909e-03
```

所以厚度扫描采用 `triangle, h=1.0 nm` 作为当前可信网格。

### 空气厚度扫描

空气厚度：`60, 70, 80, 90, 110, 120, 150 nm`。端口功率全部满足 `R+T=1` 到数值舍入精度。

```text
R_total range = 4.482327e-03 到 4.485282e-03，relative range = 6.591e-04
T_total range = 9.955147e-01 到 9.955177e-01，relative range = 2.969e-06
I_grating range relative = 4.760e-06
I_sub_near range relative = 9.178e-06
```

解释：改变上方空气厚度时，光栅附近场和端口 R/T 基本不变，说明 DtN 上端口位置移动没有引入明显腔长伪效应。`I_air_near` 会随空气高度定义变化而变化，因为当前积分区域上限会受空气厚度影响。

### 基座厚度扫描

基座厚度：`10, 20, 30, 40, 70, 100 nm`。端口功率全部满足 `R+T=1` 到数值舍入精度。

```text
R_total range = 4.482703e-03 到 4.486329e-03，relative range = 8.087e-04
T_total range = 9.955137e-01 到 9.955173e-01，relative range = 3.643e-06
I_grating range relative = 7.327e-06
I_air_near range relative = 3.513e-06
```

解释：基座厚度对正式端口 R/T、光栅积分和空气近场积分影响很小。`I_sub_near` 会随很薄基座变化明显，因为厚度小于近场积分区域默认下探深度时，实际积分面积也变了。

### 空气/基座组合扫描

随机组合厚度共 8 组。端口功率全部满足 `R+T=1` 到数值舍入精度。

```text
R_total range = 4.482905e-03 到 4.488317e-03，relative range = 1.206e-03
T_total range = 9.955117e-01 到 9.955171e-01，relative range = 5.436e-06
I_grating range relative = 7.397e-06
```

判断：组合扫描中 R 的相对变化略高于 `0.1%`，但 R 本身只有约 `4.5e-3`，绝对变化约 `5.4e-6`；T、R+T、光栅近场积分都非常稳定。因此当前 2D EUV DtN 主线已经足够作为后续结构验证基准。

### 当前建议

正式 2D EUV 验证建议优先使用：
```text
calculation_method = port_total
port_boundary_model = dtn
port_dtn_assembly = auxiliary
mesh_cell_shape = triangle
mesh_target_size = 1.0 nm
polarization = TM
```

对于 lossless 实折射率案例，正式验收看 `dtn_auxiliary_power_metrics.json` 或 study 汇总 CSV 中的 `R_total / T_total / R_plus_T`。内部 `power_metrics.json` 的 probe-line 结果仍可帮助看场，但不作为正式能量守恒判据。

## 2026-06-29 更新：2D EUV DtN 输入、网格和近场积分 smoke 通过

本轮新增内容：

```text
1. src/main.py
   新增 Inputs2D / EUVGratingInputs2D，用 dataclass 管理 2D EUV 参数。

2. src/geometry/mesh_builder.py
   新增 mesh_cell_shape = triangle / quadrilateral。
   新增 mesh_lock_near_field_template，用于厚度扫描时锁定光栅附近网格坐标。

3. src/postprocessing/near_field_2d.py
   定义 grating、air_near、sub_near 的积分区域和参考面积。

4. src/postprocessing/power_metrics.py
   在 power metrics 中写入近场积分：
     I_grating
     I_air_near
     I_sub_near

5. src/studies/run_2d_euv_validation.py
   新增 method_compare、mesh_convergence、air_scan、substrate_scan、combined_scan 批量研究入口。
```

## 测试结果

宿主 Python 快速检查：

```text
python -m compileall -q src
结果：通过

python -m unittest discover -s src/test -p "test_16_2d_euv_inputs_and_mesh.py"
结果：Ran 5 tests, OK
```

Docker / DOLFINx 完整测试：

```text
. dolfinx-complex-mode && python3 -m compileall -q src
. dolfinx-complex-mode && python3 -m unittest discover -s src/test -p "test_*.py"
结果：Ran 48 tests, OK (skipped=8)
```

## PDE smoke：triangle, h=5 nm

命令要点：

```text
stage = 2D EUV grating
mesh_cell_shape = triangle
mesh_target_size = 5 nm
port_boundary_model = dtn
port_dtn_assembly = auxiliary
port_use_diffraction_orders = True
```

结果目录：

```text
results/2D_grating_tm_port_ptdtn_dtnauto_aux_p2_h5p0_tri_lam13p5_t0p0_man_20260629_015357
```

关键结果：

```text
mesh cells = 1200
N1curl dofs = 6100
reduced residual = 1.342e-14
Floquet mismatch total dof = 0

probe-line power_metrics:
  R/T/R+T = 1.019124e-02 / 6.945273e-01 / 7.047185e-01

DtN boundary-integral port:
  R/T/R+T = 6.317552e-03 / 9.936824e-01 / 1.000000e+00

DtN auxiliary amplitude:
  R/T/R+T = 6.317552e-03 / 9.936824e-01 / 1.000000e+00
```

近场积分：

```text
I_grating  = 2614.2807578231755
I_air_near = 7190.107110521212
I_sub_near = 4708.133630737182
```

说明：

```text
probe-line 后处理在这个 EUV 小周期多衍射级案例中仍然偏差较大。
正式 R/T 以 DtN boundary-integral 或 DtN auxiliary amplitude 为准。
两者当前一致到线性求解舍入误差。
```

## PDE smoke：quadrilateral, h=5 nm

结果目录：

```text
results/2D_grating_tm_port_ptdtn_dtnauto_aux_p2_h5p0_quad_lam13p5_t0p0_man_20260629_015500
```

关键结果：

```text
mesh cells = 600
N1curl dofs = 4900
reduced residual = 1.302e-14
Floquet mismatch total dof = 0

probe-line power_metrics:
  R/T/R+T = 1.146909e-02 / 5.913327e-01 / 6.028018e-01

DtN boundary-integral port:
  R/T/R+T = 2.669180e-02 / 9.733082e-01 / 1.000000e+00

DtN auxiliary amplitude:
  R/T/R+T = 2.669180e-02 / 9.733082e-01 / 1.000000e+00
```

## 下一步建议

正式收敛研究按这个顺序：

```text
1. method_compare
   先确认 DtN auxiliary 与 DtN explicit 在同一粗网格上一致。

2. mesh_convergence
   triangle 和 quadrilateral 分别扫 h = 4, 3, 2, 1.5, 1.25, 1 nm。
   判据：总 R/T 和近场积分连续两次相对变化小于 0.1%。

3. air_scan
   使用收敛网格，扫 air_height = 60,70,80,90,110,120,150 nm。

4. substrate_scan
   使用收敛网格，扫 substrate_thickness = 10,20,30,40,70,100 nm。

5. combined_scan
   固定随机种子抽样空气/基座组合。
```
