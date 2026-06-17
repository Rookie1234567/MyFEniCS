# PML 复坐标公式更新说明

本文记录 2026-06-09 对 PML 实现做的修改。修改目标是把原来较简化的 `s_y = 1 + i alpha d^2` 拉伸，换成和官方 DOLFINx Maxwell PML demo 一致的复坐标映射。

## 1. 用户指定的公式

官方 demo 使用的复坐标形式可以写为：

```text
x' = x + i * alpha / k0 * x * (|x| - l_dom/2) / (l_pml/2 - l_dom/2)^2
```

这里：

```text
x       当前坐标，公式假设物理区域中心在 x=0
x'      复坐标
alpha   PML 吸收强度参数
k0      真空波数，k0 = 2*pi/lambda0
l_dom   不含 PML 的物理区域长度
l_pml   含 PML 后的总长度
```

它的思想是：不要直接手写一个吸收材料，而是先把坐标延拓成复数坐标，再根据坐标变换的 Jacobian 生成等效的各向异性介电常数和磁导率。

## 2. 为什么代码里要先平移 y

官方公式默认物理区域关于 0 对称，例如：

```text
[-l_dom/2, l_dom/2]
```

但本项目的物理 y 范围是：

```text
physical_y_min = -substrate_thickness
physical_y_max = air_height
```

默认值为：

```text
physical_y_min = -350 nm
physical_y_max =  850 nm
```

中心是：

```text
y_center = (physical_y_min + physical_y_max)/2 = 250 nm
```

所以代码先定义：

```text
eta = y - y_center
```

然后对 `eta` 使用官方公式：

```text
eta' = eta + i * alpha / k0 * eta * (|eta| - l_dom/2) / (l_pml/2 - l_dom/2)^2
```

最后再平移回原坐标：

```text
y' = y_center + eta'
```

这样只是改变坐标原点，不改变 PML 的物理含义。

## 3. 顶部和底部 PML 如何取 l_pml

物理高度为：

```text
l_dom = physical_y_max - physical_y_min
```

对于顶部 PML，代码使用：

```text
l_pml_top = l_dom + 2 * pml_top_thickness
```

对于底部 PML，代码使用：

```text
l_pml_bottom = l_dom + 2 * pml_bottom_thickness
```

默认上下 PML 厚度相等，所以这和官方对称公式完全一致。若以后上下 PML 厚度不同，这种写法也能让顶部和底部各自使用自己的 PML 厚度。

## 4. 从复坐标到材料张量

PML 区域的坐标映射为：

```text
(x, y) -> (x, y')
```

代码计算 Jacobian：

```text
J = grad((x, y'))
```

再扩展为三维矩阵：

```text
J3 = [[J00, 0,   0],
      [0,   J11, 0],
      [0,   0,   1]]
```

令：

```text
A = inv(J3)
```

则 PML 等效材料为：

```text
epsilon_pml = det(J3) * A * epsilon_background * A^T
mu_pml      = det(J3) * A * mu_background      * A^T
```

本项目中：

```text
顶部 PML: epsilon_background = eps_air
底部 PML: epsilon_background = eps_substrate
mu_background = 1
```

这保持了“顶部是空气延拓、底部是基座延拓”的设计。

## 5. 对应代码位置

主要修改在：

```text
src/common/pml.py
```

关键函数：

```text
_pml_coordinate
_y_pml_coordinate
_pml_tensors_from_coordinate_map
top_pml_tensors
bottom_pml_tensors
```

求解器中仍然通过：

```text
top_pml_tensors(x, cfg)
bottom_pml_tensors(x, cfg)
```

得到 PML 材料张量，所以 Maxwell 弱式的主结构没有改变。

## 6. 如何验证

建议优先看散射场法，因为散射场法默认启用上下 PML：

```text
calculation_method = "scattered"
constraint_backend = "both"
scattering_background = "layered"
```

运行后检查：

```text
solver_log.txt
run_summary.json
E_scat_norm.png
fields_for_paraview.vtu
```

合理现象是：

```text
1. 求解器正常收敛
2. official MPC 与 manual 后端结果接近
3. E_scat 进入 PML 后整体衰减
4. 物理区域内 E_total_abs 不应出现由 PML 入口制造的硬突变
```

端口总场法默认不使用 PML，因此它主要用于和 COMSOL 周期端口做对比；如果显式设置 `port_use_pml=True`，才会同时受到本 PML 修改影响。

## 7. 本次重新运行结果

我在 Docker complex DOLFINx 环境中重新运行了 `config.py` 当前默认的全部方法：

```text
calculation_method = "all"
constraint_backend = "both"
port_boundary_model = "all"
scattering_background = "layered"
mesh_target_size = 15.0
nedelec_degree = 2
```

结果目录：

```text
results/run_air_substrate_grating_all_bg_layered_port_all_dtn1_20260609_095504/
```

五个方法均成功求解：

```text
scattered layered mpc_official: R=0.022112910, T=0.979624581, R+T=1.001737492, Poynting=1.001842494
scattered layered manual:       R=0.022112910, T=0.979624581, R+T=1.001737492, Poynting=1.001842494
port robin mpc_official:        R=0.021927723, T=0.989427546, R+T=1.011355268, Poynting=1.002585068
port robin manual:              R=0.021927723, T=0.989427546, R+T=1.011355268, Poynting=1.002585068
port dtn manual:                R=0.022117491, T=0.980299708, R+T=1.002417199, Poynting=1.002577824
```

同一物理方法下的 official/manual 后端仍然高度一致：

```text
scattered layered:
R_total_difference      = 5.41e-15
T_total_difference      = 1.93e-14
R_plus_T_difference     = 2.49e-14
poynting_R_plus_T_diff  = 4.33e-14

port robin:
R_total_difference      = 1.42e-14
T_total_difference      = 9.27e-13
R_plus_T_difference     = 9.13e-13
poynting_R_plus_T_diff  = 8.21e-13
```

这说明新的 PML 复坐标公式可以正常装配、求解，并且没有破坏 Floquet 约束两种实现的相互印证。
