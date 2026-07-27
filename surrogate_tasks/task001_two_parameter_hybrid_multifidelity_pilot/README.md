# Task001：高度/宽度两参数 Hybrid 多保真 pilot

## 当前身份

```text
status = ready_for_codex_execution
execution_branch = codex/only-one-13p5nm-surrogate-inversion
hardware = local 16 GB Windows laptop + WSL2 Ubuntu-24.04
wavelength = 13.5 nm fixed
invertible_parameters = grating_height_nm, grating_width_x_nm
bulk_dataset_generation = out_of_scope
surrogate_training = out_of_scope
inversion_production = out_of_scope
```

Task000 已通过 ChatGPT Review V1。Task001 不直接生成完整训练集，而是完成本地 Hybrid 高/低保真资格化、p6/h7.5 资源判定、候选入射条件筛选以及高度/宽度的局部可辨识性确认。

## 固定物理范围

名义几何：

```text
height h0 = 120 nm
width_x w0 = 17 nm
width_y = period_y = 25 nm
period_x = 50 nm
period_y = 25 nm
```

第一版窄先验：

```text
height h in [115, 125] nm
width_x w in [16, 18] nm
```

固定项包括 13.5 nm、现有 Si 复折射率、矩形截面、垂直侧壁、基底、周期、无 PML、Floquet、辅助 DtN 和现有参考平面定义。不得在 Task001 中增加侧壁角、圆角、粗糙度、材料、波长或其他反演参数。

## 候选保真度

```text
requested high fidelity:
    Hybrid static / memory-minimal M120
    p5 trace / p6 interior exact-sequence contract
    nominal h_mesh = 7.5 nm

fallback high fidelity:
    同一 Hybrid static M120
    p5 trace / p6 interior
    h_mesh = 10 nm

primary low fidelity:
    Hybrid p4 / h10 / M120

fallback low fidelity:
    Hybrid p5 / h10 / M120
```

p6/h7.5 只有在预测峰值和运行时 watchdog 都满足本机安全内存上限、无 swap、完整 residual/physics Gate 通过时，才可成为 high fidelity。否则记录受控停止，并采用同源资格化后的 p6/h10 Hybrid static M120。

## Pilot 几何与入射条件

局部/边界 9 点：

```text
center:       (120, 17)
height axial: (117.5, 17), (122.5, 17)
width axial:  (120, 16.5), (120, 17.5)
corners:      (115, 16), (115, 18), (125, 16), (125, 18)
```

首轮候选照明：

```text
theta = 70°, 80°     # 使用当前代码相对法线的角度约定
phi   = 0°, 90°
polarization = S, P
```

先由低保真在 9 个几何点上筛选，再由选定高保真在中心差分 5 点上确认。若 70°/80° 两档无法区分高度与宽度，才允许增加 theta=75° 的二级筛选；不得自动扩展到连续角度扫描。

## 固定衍射输出窗口

正式 compact dataset 只保留 `n=0` 的 9 个 x 向衍射级：

```text
m = 0, -1, -2, -3, -4, -5, -6, -7, +1
```

这组固定窗口覆盖当前 50 nm 周期、13.5 nm、70°/80°、phi=0°/90° 候选中有物理意义的 n=0 传播级，同时避免保存任意高 `|m|`。每个条目必须包含传播状态、反射/透射、outgoing S/P 分量功率和可用时的复振幅。所有 `n!=0` 模式不进入训练向量，只汇总为数值泄漏诊断。

## 主要交付

```text
surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/
    outcomes/summary.md
    outcomes/test_summary.md
    outcomes/fidelity_qualification.md
    outcomes/illumination_identifiability.md
    outcomes/task002_dataset_plan.md
    response_v1.md

benchmarks/cases/110_surrogate_two_parameter_pilot/
    README.md
    config.json
    expected.json
    test_command.txt
    records/
```

代码优先放入 `src/forward_data/` 的参数化、order extraction、resource watchdog 和 identifiability 模块；不得复制 Hybrid/FEM 数值核心。

## 完成定义

Task001 只有在以下事项均明确后才结束：

- 当前 clean source 上至少一个 Hybrid high-fidelity 模型完成 formal nominal qualification；
- p6/h7.5 被真实分类为 `qualified` 或 `controlled_stop_resource`；
- 一个低保真 Hybrid 被选定并与高保真局部敏感度方向一致；
- 低保真候选照明 pilot 完成；
- 选定照明组合经高保真 5 点确认后，噪声加权 Jacobian rank=2；
- 报告高度/宽度相关系数、Fisher 条件数以及 reflection-only 与 R+T 两种可辨识性；
- 冻结 Task002 的 49 个低保真设计、9 个高保真锚点和后续自适应预算；
- 不开始完整数据集生成、代理拟合或正式反演。