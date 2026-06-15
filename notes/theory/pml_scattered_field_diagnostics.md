# PML 区域散射场诊断记录

本记录对应用户提出的问题：当前算例中 `E_scat` 在上下 PML 区域内不是零，是否说明 PML 或代码有问题。

## 结论

`E_scat` 在 PML 内不应被要求处处为零。PML 的作用是吸收从物理区域传播进去的出射场，所以正确现象通常是：

```text
物理区域中的散射场 -> 进入 PML -> 沿 PML 深度方向衰减
```

真正不合理的情况是：

```text
PML 自己在无散射源时产生散射场
```

或者：

```text
散射场进入 PML 后完全不衰减，甚至在外截断边界附近仍然很强
```

本次诊断显示：PML 自身没有凭空制造散射场；当前底部 PML 内较强的 `E_scat` 主要来自当前散射场公式的背景场定义，而不是 PML 单独出错。

## 当前代码中的散射场定义

当前代码求解的是：

```text
curl curl(E_scat) - k0^2 epsilon_r E_scat
  = k0^2 (epsilon_r - epsilon_air) E_inc
```

其中 `E_inc` 是空气中的解析平面波：

```text
E_inc = p exp(i(kx x + ky y))
```

这意味着当前 `E_scat` 是相对于“全空间都是空气”的背景场来定义的。

因此，只要加入基座：

```text
epsilon_substrate != epsilon_air
```

整块基座都会进入右端项：

```text
(epsilon_r - epsilon_air) E_inc
```

换句话说，在这个公式里，基座本身就是一个很大的散射源。底部 PML 里看到的强 `E_scat`，很大一部分不是光栅单独造成的，而是“空气背景场需要修正成基座中的真实场”造成的。

这点很容易导致和 COMSOL 的 scattered field 变量不一致。COMSOL 如果使用端口、背景场或周期端口求解，里面的 scattered field 可能是相对于“平坦空气/基座结构”或端口模场来定义的，而不是相对于全空气平面波。

## 已运行的诊断实验

诊断脚本：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/src/tools/diagnose_pml_fields.py
```

### 1. 当前光栅算例

读取结果：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/results/air_substrate_grating_mpc_official/fields_for_paraview.vtu
```

统计文件：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/results/air_substrate_grating_mpc_official/pml_field_diagnostics.json
```

关键结果：

```text
top PML 入口附近 E_scat_abs mean  = 0.1973
top PML 外边界附近 E_scat_abs mean = 0.0775

bottom PML 入口附近 E_scat_abs mean  = 1.4148
bottom PML 外边界附近 E_scat_abs mean = 0.2067
```

解释：

- 顶部 PML 中散射场进入 PML 后衰减；
- 底部 PML 入口处散射场很强，但到外边界附近明显衰减；
- 底部 PML 的强场不等于 PML 生成了场，而是下方基座方向有很强的出射/修正场进入 PML。

### 2. 全空气基准算例

设置：

```text
n_air       = 1.0
n_substrate = 1.0
n_grating   = 1.0
```

此时：

```text
epsilon_r - epsilon_air = 0
```

理论上右端项为零，应该得到：

```text
E_scat = 0
```

实际运行结果：

```text
max |E_scat| = 0.0

top PML    E_scat_abs max = 0.0
bottom PML E_scat_abs max = 0.0
```

结果文件：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/results/homogeneous_air_pml_check_manual/fields_for_paraview.vtu
```

解释：

这个实验说明 PML 和 Floquet 约束不会在无散射源时凭空产生 `E_scat`。

### 3. 平坦基座基准算例

设置：

```text
n_air       = 1.0
n_substrate = 1.45
n_grating   = 1.0
```

这里光栅区域材料设为空气，所以材料分布等价于：

```text
上方空气 + 下方平坦基座
```

没有真正的凸起光栅材料扰动。

实际运行结果：

```text
max |E_scat| = 1.2569

bottom PML 入口附近 E_scat_abs mean  = 1.1966
bottom PML 外边界附近 E_scat_abs mean = 0.1694
```

结果文件：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/results/flat_substrate_reference_check_manual/fields_for_paraview.vtu
fenics_vector_maxwell_floquet_demo_v2_parallel/results/pml_flat_substrate_diagnostics.json
```

解释：

即使没有光栅凸起，底部 PML 中仍然有很强 `E_scat`。这证明当前底部强散射主要来自“基座相对空气背景”的修正，而不是光栅或 PML 独有错误。

## 对 COMSOL 对比的建议

当前最可能的误差来源是：COMSOL 和本代码的 scattered field 定义不一致。

对比时建议优先做下面几步：

1. 只在物理区域比较，不把 PML 区域作为物理结果比较。
2. 优先比较 `E_total_abs`，而不是直接比较 `E_scat_abs`。
3. 确认 COMSOL 中入射场振幅是否为 1 V/m；本代码输出是归一化场，默认入射振幅为 1。
4. 如果 COMSOL 使用的是平坦基座作为背景场，那么本代码也应改成“分层背景场散射公式”，右端项只包含光栅相对平坦基座的扰动。

更接近 COMSOL 周期端口设置的公式应该是：

```text
E_total = E_bg + E_scat_grating
```

其中 `E_bg` 不是全空气平面波，而是“平坦空气/基座结构”的解析或数值背景场。此时散射源应近似写成：

```text
k0^2 (epsilon_actual - epsilon_background) E_bg
```

这样平坦基座本身不会再被当作散射体，`E_scat_grating` 才更接近“光栅额外引起的散射场”。

## 当前判断

当前结果中，PML 内 `E_scat` 非零这件事本身不是错误。

## 2026-06-09 补充：PML 公式已改为官方复坐标形式

当前 `src/common/pml.py` 已经不再使用早期简化的：

```text
s_y = 1 + i alpha d^2
```

而是改为官方 DOLFINx PML demo 的复坐标公式：

```text
x' = x + i * alpha / k0 * x * (|x| - l_dom/2) / (l_pml/2 - l_dom/2)^2
```

本项目实际将它作用在 y 方向，并先把 y 坐标平移到物理区域中心。这个改动会改变 PML 内的场衰减形态，所以旧诊断记录中的具体数值只表示当时旧版 PML 的结果；新的判断应以重新运行后的 `E_scat_norm.png`、`pml_field_diagnostics.json` 或 ParaView 中的 PML 区域为准。

但当前公式不适合直接和 COMSOL 的“基于端口/分层背景”的 scattered field 逐点比较。若要和 COMSOL 严格对比，需要统一背景场定义。下一步更合理的代码修改方向是实现“平坦空气/基座背景 + 光栅扰动散射”的版本，而不是继续要求 PML 内的 `E_scat` 必须为零。

## 2026-06-09 补充：端口法下如何理解 PML

现在代码已经新增：

```text
--formulation port_total
```

这个方法直接求 `E_total`，默认不生成上下 PML，而是把上下边界改成端口边界：

```text
上边界：入射端口
下边界：出射端口
```

所以如果你的目标是尽量模仿 COMSOL 的“上端口入射、下端口出射、左右 Floquet”，建议先比较 `port_total` 的 `E_total_abs`，而不是继续纠结旧散射场法里 PML 区域的 `E_scat_abs`。

如果你显式加：

```text
--port-use-pml
```

则端口法会保留上下 PML，并把端口放在最外边界。这个选项主要用于实验，不是当前和 COMSOL 周期端口对比的首选。

如果 COMSOL 周期端口中启用了多个衍射级次，可以不用 PML，改用：

```text
--formulation port_total --constraint-backend manual --port-order-count N
```

这时上下边界不再靠 PML 吸收，而是通过 Fourier 模态端口让 `m=-N...N` 的传播/倏逝级次满足出射关系。

配置式运行时，对应变量是：

```python
calculation_method = "port"
port_boundary_model = "dtn"
port_dtn_order_count = N
port_use_pml = False
```
