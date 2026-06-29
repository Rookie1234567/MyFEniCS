# 2D EUV 光栅验证报告

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
