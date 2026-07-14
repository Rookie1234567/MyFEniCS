# 第一阶段前向模型冻结范围

## 1. 决策状态

```text
status = approved current-phase scope
scope_applies_to = Task031–Task034
reference_wavelength = 13.5 nm
material = existing validated Si optical constant
instrument_model = deferred
wavelength_continuation = deferred_to_Task035
```

本文件是 [`project_service_requirements_and_forward_model_roadmap.md`](project_service_requirements_and_forward_model_roadmap.md) 的当前阶段执行补充。若主规划文档中关于 Task032–Task034 的材料扰动或多波长验证与本文件冲突，以本文件为准。

---

## 2. 当前阶段冻结的物理问题

Task031–Task034 统一使用：

```text
wavelength = 13.5 nm
grazing angle alpha = 1–10 deg from surface
azimuth = parameterized, current primary benchmark phi = 0 deg
polarization = S and P
geometry = current regular periodic structure
material system = current Si setup
```

当前 Si 复折射率继续使用项目中已经验证的 13.5 nm 数值：

$$
n_{\mathrm{Si}}
=
1-0.000997695141
+i\,0.00182649365.
$$

等价写为：

$$
n_{\mathrm{Si}}
=
0.999002304859
+i\,0.00182649365.
$$

当前阶段不扫描材料不确定性，不设置折射率上下包络，也不把材料参数作为反演未知量。材料只作为固定、已知的 Maxwell 输入。

---

## 3. 当前阶段暂不考虑的因素

以下内容不进入 Task031–Task034 的 Maxwell 前向模型和通过门槛：

```text
- detector absolute calibration
- absolute incident intensity
- detector gain
- detector background and dark current
- measurement noise model
- measurement uncertainty or covariance
- beam divergence
- missing pixels
- beam stop
- saturated pixels
- material optical-constant uncertainty
- wavelength uncertainty
```

这些因素属于后续实验数据层和反演似然层。当前只要求前向模型保持明确、稳定的功率归一化，并输出可供以后映射到实验强度的复振幅和归一化衍射效率。

---

## 4. 当前阶段必须支持的输入和输出

### 4.1 输入

```text
- parameterized geometry
- wavelength fixed at 13.5 nm
- grazing angle alpha in 1–10 deg
- azimuth phi
- S or P polarization
- fixed validated Si optical constant
- mesh/discretization controls
```

### 4.2 输出

```text
- reflected complex amplitudes r_mn
- reflected diffraction efficiencies R_mn
- transmitted amplitudes and efficiencies when applicable
- R_total / T_total / A_volume
- mode identity and propagating/evanescent classification
- reported residual
- condensed true residual
- full augmented true residual
- energy closure
- modal truncation error estimate
- FEM discretization error estimate
- DoF / mode count / memory / iterations / time
- commit / command / image digest / material-data identity
```

近场 `E/H` 保留为开发、验证和诊断输出，但不作为当前反演观测量的硬要求。

---

## 5. 角度验证范围

第一阶段默认覆盖：

```text
alpha = 1°, 2°, 3°, 4°, 5°, 6°, 7°, 8°, 9°, 10°
```

低成本筛选可使用：

```text
1°, 2°, 3°, 5°, 7.5°, 10°
```

若在材料临界角、衍射级 cutoff 或响应快速变化区发现明显非平滑行为，可局部增加角度点；但不因此引入新的材料或实验不确定性模型。

---

## 6. 对后续 Task 的约束

### Task031

仍只优化当前 13.5 nm 完整 3D benchmark 的内存，不改变物理模型。

### Task032

建立 13.5 nm 下的 hybrid FEM–Modal 直接法，并验证：

```text
full 3D reference
vs
bottom local 3D FEM
+ middle z-invariant modal propagation
+ top local 3D FEM
```

Task032 的参数化范围只包括角度、方位角、S/P 偏振和几何；材料保持固定。

### Task033

在 13.5 nm、固定材料下构造面向 `1–10° + S/P` 的 robust h/p 自适应公共网格。当前不加入材料扰动样本。

### Task034

针对 Task033 的最终 hybrid-adaptive 离散系统构造参数鲁棒迭代法。鲁棒性首先指：

```text
- 1–10° grazing-angle range
- S/P polarization
- geometry variations within the planned parameterization
```

不要求对波长和材料色散同时鲁棒。

### Task035

只有 Task032–Task034 在 13.5 nm 下完成正确性、内存和求解鲁棒性验证后，才启动：

```text
13.5 nm
→ 5 nm
→ 2 nm
→ 1 nm
→ 0.7 nm
```

从 Task035 开始，每个波长再更新对应的材料复折射率、传播衍射级、截面本征模和资源预算。

---

## 7. 当前统一结论

```text
第一阶段只解决：
13.5 nm
+ 当前已验证 Si 材料
+ 1–10° 掠角
+ S/P 偏振
+ 规则周期结构
+ 归一化逐衍射级前向输出。

第一阶段暂不解决：
实验绝对强度
+ 背景和噪声
+ 测量不确定性
+ 材料不确定性
+ 多波长鲁棒性。

先证明新 hybrid 方法、自适应离散和迭代框架在 13.5 nm 下成立，
再在 Task035 处理波长缩短和材料色散。
```