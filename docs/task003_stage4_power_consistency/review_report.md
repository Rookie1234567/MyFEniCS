# REVIEW REPORT 20260703：Stage 4 功率一致性修复

## 1. 审查对象

本报告审查分支：

```text
codex/20260702-rta-output-volume-absorption
```

本报告属于任务目录：

```text
docs/task003_stage4_power_consistency/review_report.md
```

对应任务书：

```text
docs/task003_stage4_power_consistency/task.md
```

对应 outcomes：

```text
docs/task003_stage4_power_consistency/outcomes/
```

本轮审查重点是判断 Stage 4 flat-layer 功率一致性是否已经修复，尤其关注：

1. `port` 主功率口径是否可信；
2. `A_volume` 体吸收是否与 port 能量余额闭合；
3. analytic-only probe/net_flux/volume 测试是否通过；
4. small-cell flat-layer 是否能作为后续标准 benchmark；
5. probe/net_flux 在 FEM 场下是否仍需要作为 diagnostic only；
6. 是否应该继续强制 real block 作为小电脑验收目标。

---

## 2. 总体结论

本轮任务已经基本完成了“Stage 4 flat-layer 主功率闭合修复”。

可以认为：

```text
port + volume_absorption 主线已经基本通过；
probe_eh_fourier 与 net_flux 目前仍应保留为 diagnostic only；
真实 100 nm grating 不应作为当前小电脑阶段的必需验收项。
```

相比 task002，本轮有实质性进展：

1. 新增了 flat-layer 解析参考模块；
2. 修正了 `A_volume` 的 code-unit 归一化；
3. 修正了有损基底底部端口的参考平面功率口径；
4. 修正了 auxiliary DtN traction 相关符号；
5. analytic-only 的 probe/net_flux/volume 测试全部通过；
6. small-cell flat-layer 中 `port` 与 `A_volume` 可以达到机器精度能量闭合；
7. 原 100 nm flat-layer 下近全反射的问题已经被定位为大横向周期、粗 p1 网格和大量 auto-propagating 端口模态共同造成的数值诊断失败，而不是 flat interface 的物理结果。

因此，本轮结果可以作为后续 Stage 4 flat-layer 验证链条的基础。但是，本分支仍不应被描述为“完整 3D grating 物理 benchmark 已完成”。

---

## 3. 已完成的关键修复

### 3.1 A_volume 归一化修复

上一轮 `A_volume` 使用：

```text
P_abs = integral 0.5*k0^2*Im(epsilon_r)*|E_total|^2 dV
```

本轮已改为：

```text
P_abs = integral 0.5*k0*Im(epsilon_r)*|E_total|^2 dV
```

这个修改与当前代码单位一致：

```text
H_code = curl(E)/(i*k0*mu_r)
S_code = 0.5*Re(E x conj(H_code))
```

analytic-only volume absorption 测试表明，该公式可以与解析有损平面波的 flux loss 对齐。因此，`A_volume` 当前可以作为材料体吸收的主检查指标。

### 3.2 flat-layer analytic reference 已建立

新增模块：

```text
src/postprocessing/flat_layer_reference_3d.py
```

它已经能够区分：

```text
port planes
probe planes
```

这点很重要。对于有损 substrate，透射功率必须取决于底部参考平面位置，不能只使用界面处 Fresnel 透射率。

### 3.3 port 有损底部功率口径已修正

`dtn_port_3d.py` 中已经加入端口面相位/衰减口径，用于底部有损 substrate 中的投影分母和功率计算。这样 `T_port` 与解析 port-plane reference 可以在同一参考面比较。

### 3.4 auxiliary DtN traction 符号已修正

本轮 outcomes 记录，auxiliary DtN traction 已改为：

```text
curl(E) x n
```

这一点解决了 task002 中 port 主口径不可信的重要嫌疑。当前 small-cell 结果也支持 port 主线已经明显变好。

---

## 4. Analytic-only 测试评价

本轮 analytic-only 测试全部通过：

| test | status | 评价 |
|---|---|---|
| lossy flat reference attenuation | pass | 有损基底中 bottom plane 衰减已纳入参考值 |
| analytic E/H -> probe_eh_fourier | pass | probe 公式本身能恢复解析 R/T/A |
| analytic E/H -> net_flux | pass | Poynting flux 符号和透射方向在解析场下正确 |
| analytic volume absorption | pass | `0.5*k0*Im(eps)|E|^2` 与 flux loss 一致 |
| lossless substrate A_volume | pass | 无损材料下体吸收为 0 |

这说明一个关键结论：

```text
probe_eh_fourier / net_flux / A_volume 的公式层面已经基本修正。
```

如果后续 FEM 场下 probe/net_flux 仍然与 port 不一致，应优先从 FEM 离散场采样、curl 重构、probe plane 位置、低阶 p1 误差等角度排查，而不是直接否定后处理公式。

---

## 5. 100 nm flat-layer 结果评价

原始 `100 nm x 100 nm` flat-layer 仍然表现不理想。

### 5.1 h=10 nm

结果几乎全反射：

```text
R_port ≈ 1
T_port ≈ 0
A_volume ≈ 0
```

这不是 flat interface 的物理结果。

### 5.2 h=5 nm

结果明显改善：

```text
R_port ≈ 0.0217
T_port ≈ 0.9187
A_volume ≈ 0.0596
R_port + T_port + A_volume - 1 ≈ 机器精度
```

此时 `port` 与 `A_volume` 已经闭合，但仍有约 2.17% 数值反射。

### 5.3 h=3 nm

h=3 nm 未完成。该算例达到：

```text
N1curl DoF ≈ 186235
auxiliary modes = 708
base matrix nnz ≈ 6.18e6
```

单进程 direct LU 超时停止。

### 5.4 对 100 nm flat-layer 的判断

flat-layer 在 x/y 方向均匀，理论上不会产生高阶衍射级。即使 `auto_propagating` 枚举出大量传播模态，高阶模态的物理幅值也应为 0。

但是在离散系统中，大量高阶端口模态仍会进入 auxiliary DtN 系统。对于粗 p1 网格，这些高频边界模态会放大投影误差、正交性误差和求解病态。

因此，100 nm flat-layer 不应继续作为 small-computer 阶段的标准 flat-layer benchmark。

---

## 6. small-cell flat-layer 补充验证评价

本轮最有价值的补充是 small-cell flat-layer：

```text
period_x = 10 nm
period_y = 10 nm
air_height = 5 nm
substrate_thickness = 5 nm
```

该设置仍然是同一个 flat air/Si interface，只是去掉了不必要的大横向周期。由于 `period_x = period_y = 10 nm`，`auto_propagating` 只保留零级 x/y 四个端口模态，而不再引入 708 个 auxiliary port modes。

small-cell 结果显示：

| mesh_nm | R_port | T_port | A_volume | closure |
|---:|---:|---:|---:|---:|
| 2.7 | 3.169e-03 | 9.894e-01 | 7.418e-03 | -1.55e-15 |
| 2.0 | 5.938e-04 | 9.915e-01 | 7.938e-03 | -8.55e-15 |
| 1.5 | 1.755e-04 | 9.917e-01 | 8.155e-03 | -1.11e-16 |
| 1.0 | 6.616e-05 | 9.917e-01 | 8.262e-03 | -2.22e-15 |

这组结果支持以下判断：

1. `port` 不再出现全反射；
2. `R_port` 随网格细化持续下降；
3. `T_port` 与解析 port-plane reference 已经很接近；
4. `A_volume` 与 `A_port` 完全一致；
5. `R_port + T_port + A_volume - 1` 达到机器精度；
6. small-cell flat-layer 可以作为后续 Stage 4 flat interface 的标准验证模型。

因此，目前可以认为：

```text
port + A_volume 主线已经通过 flat-layer small-cell 验证。
```

注意：这并不等价于所有物理量完全收敛。h=1 nm 时仍有少量离散误差，例如 `R_port` 仍高于解析反射率。但误差已经随网格细化下降，且主能量闭合稳定。

---

## 7. probe_eh_fourier 和 net_flux 的当前地位

small-cell 中，probe/net_flux 随网格细化有所改善，但仍明显不如 port/volume 稳定。

例如 h=1 nm：

```text
port:
  R ≈ 6.62e-05
  T ≈ 0.99167
  A_volume ≈ 0.00826

probe_eh_fourier:
  R ≈ 3.75e-03
  T ≈ 0.96218
  A ≈ 0.03407

net_flux:
  R ≈ 3.49e-02
  T ≈ 0.95955
  A ≈ 0.00554
```

由于 analytic-only 测试已经通过，这些偏差更可能来自：

1. p1 Nédélec 离散场在 probe plane 上的采样误差；
2. `H = curl(E)/(i*k0*mu)` 的低阶重构误差；
3. probe plane 位置对离散误差敏感；
4. 后处理采样阶次和网格尺度不匹配；
5. 低阶 p1 对 EUV 短波下局部场梯度表示不足。

因此，当前不应使用 probe/net_flux 否定 port。更合理的结论是：

```text
port 为 primary；
volume_absorption 为 absorption_check；
probe_eh_fourier 和 net_flux 暂时为 diagnostic only。
```

下一轮应专门研究 p=2 是否能显著改善 probe/net_flux 与 port 的一致性。

---

## 8. 对 zero-contrast 和 real block 的评价

本轮没有继续运行 zero-contrast regression，也没有运行 real Si block。按照 task003 原始验收标准，这属于未完全闭环。

但是，结合本轮新发现，原任务中要求尽快回到 real block 的策略需要调整。

原因是：

1. flat-layer 已经证明大横向周期会引入大量端口模态并显著增加数值负担；
2. small-cell 都需要接近 h=1 nm 才能让 p1 结果足够稳定；
3. 真实 100 nm 周期 grating 在 13.5 nm EUV 下会真正激发多个衍射级，计算规模远大于 flat-layer small-cell；
4. 小电脑上强行要求 real block h=3/h=1 通过不现实；
5. 当前阶段更应该确认主线公式、端口、体吸收和 p 阶收敛，而不是把 real block 作为必需验收。

因此，real block 应改为：

```text
未来高资源条件下的应用验证目标，
而不是当前 small-computer 阶段的必需验收项。
```

---

## 9. 是否建议合并

当前不建议把该分支作为“最终物理 benchmark”直接合并。

但 task003 的主要技术目标已经基本完成：

```text
Stage 4 flat-layer 的 port + A_volume 主功率闭合已修复。
```

建议在同一分支继续做 task004，完成以下补充后再考虑合并：

1. small-cell flat-layer p=1 / p=2 收敛性对比；
2. 检查 p=2 是否改善 probe_eh_fourier 与 net_flux；
3. 固化 small-cell flat-layer 为标准 benchmark；
4. 运行 Stage 1 / Stage 2 / Stage 4 的轻量回归测试，确认 task002/task003 的修改没有破坏其他功能；
5. 明确 real block 只作为未来高资源验证，不作为当前验收标准。

---

## 10. 建议的 task004 方向

下一轮建议任务名称：

```text
task004_small_cell_p_convergence_and_regression
```

目标不是继续扩大真实结构，而是用 small-cell flat-layer 做一个可控、可重复、可在小电脑上完成的收敛性验证。

建议内容：

1. 使用 small-cell flat-layer：

```text
period_x = period_y = 10 nm
air_height = substrate_thickness = 5 nm
lambda0 = 13.5 nm
n_substrate = 0.999002304859 + 0.00182649365j
```

2. 同时测试 p=1 和 p=2：

```text
p=1: mesh_target_size = 2.7, 2.0, 1.5, 1.0 nm
p=2: mesh_target_size = 4.0, 3.0, 2.0, 1.5 nm
```

具体 p=2 网格可以根据实际 DoF 和内存调整。

3. 记录并比较：

```text
R_port, T_port, A_port
A_volume
R_port + T_port + A_volume - 1
R_probe, T_probe, A_probe
R_flux, T_flux, A_flux
相对解析参考的误差
DoF, cells, aux_modes, elapsed_s, max_rss_mb
```

4. 判断 p=2 是否比 p=1 更快收敛，尤其关注：

```text
probe_eh_fourier 是否更接近 port；
net_flux 是否更接近 port；
R_port 是否更接近 analytic R_ref；
A_volume 是否更接近 analytic A_ref。
```

5. 收敛性通过后，再运行轻量完整回归：

```text
Stage 1
Stage 2A / 2B / 2C
Stage 4A small-cell flat-layer
Stage 4B zero-contrast smoke test
```

不要求真实 100 nm real block 在本轮通过。

---

## 11. 最终结论

本轮 task003 可以评价为：

```text
基本通过，但不是最终物理 benchmark 完成。
```

更具体地说：

```text
通过：
- A_volume 公式修正；
- analytic-only 后处理测试；
- flat-layer 解析参考；
- small-cell flat-layer port + volume absorption 闭合；
- 端口主功率口径可信度显著提高。

未完全通过：
- probe_eh_fourier / net_flux 在 FEM 场下仍与 port 有明显差异；
- p=2 收敛性尚未验证；
- Stage 1/2/4 全链条回归尚未完成；
- 真实 100 nm grating 仍不适合作为当前小电脑验收项。
```

因此，当前应把 `port` 作为主结果，把 `A_volume` 作为吸收闭合检查，把 `probe_eh_fourier` 和 `net_flux` 降级为诊断工具。下一轮重点应转向 small-cell p=1/p=2 收敛性与全阶段轻量回归。
