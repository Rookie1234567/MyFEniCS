# 输出总结

## 任务

根据 ChatGPT 审查报告清理 Stage 4 验证口径：统一 R/T 来源说明，固定 EUV 13.5 nm 与 Si 光栅复折射率入口，并建立本轮最小可信验证表。

## 分支

`codex/20260703-stage4-validation-cleanup`

## 改动文件

详见 `changed_files.md`。

## 运行命令

- `python -m compileall -q src`
- Docker：`python3 -m unittest discover -s src/test -p "test_*.py"`
- Docker：13.5 nm Stage 4A flat-layer sanity，`mesh_target_size=50 nm`，`stage4_dtn_order_policy=zero_order`
- Docker：13.5 nm Stage 4B zero-contrast，`mesh_target_size=50 nm`，`stage4_dtn_order_policy=zero_order`

## 物理模型

本轮没有把真实 Si block grating 粗网格结果当成物理结论。真实 grating 的光栅材料入口已固定为：

```text
material_label = Si / silicon
n_grating_complex = 0.999002304859 + 0.00182649365j
lambda0 = 13.5 nm
```

基座复折射率已按用户要求使用同一个 Si 复数：

```text
substrate_material_label = Si / silicon
n_substrate_complex = 0.999002304859 + 0.00182649365j
```

由于基座和真实光栅材料都含虚部，本轮开始记录吸收余额 `A_balance = 1 - R - T`。本轮轻量运行仍统一标记为 `numerical_sanity_only`，表示它们用于验证代码路径、功率口径和 zero-contrast 对照，不是最终物理 benchmark。

## 数值设置

两条轻量运行均使用：

```text
lambda0 = 13.5 nm
nedelec_degree = 1
mesh_target_size = 50 nm
stage4_boundary_model = dtn_port
stage4_dtn_order_policy = zero_order
diffraction_zero_order_only = true
validation_role = numerical_sanity_only
```

Stage 4A flat-layer 无 grating；Stage 4B zero-contrast 保留 block 几何，但设置 `n_grating = 1 + 0j`，使 grating 区域与空气背景无介电常数对比。两者的基座均为 Si 复折射率。

## 关键结果

- Docker 内完整单元测试通过：`Ran 60 tests in 2.681s, OK (skipped=10)`。
- Stage 4A flat-layer 跑通，`R+T = 0.9999761292198394`，`A_balance = 2.38707801606868e-05`。
- Stage 4B zero-contrast 跑通，`R+T = 0.9999761292198392`，`A_balance = 2.38707801607977e-05`。
- 两条轻量运行的 R/T 在数值上匹配，说明 zero-contrast block 几何没有额外引入散射。
- 两条运行均写出 `physical_benchmark_candidate = false`，避免把路径跑通误写成物理 benchmark。

## 能量检查

本轮不再把 `R+T=1` 作为目标，因为基座含吸收。对有吸收材料，`A_balance = 1 - R - T` 解释为从入射端口到出射端口之间的吸收/损耗余额。它仍不能单独证明物理正确，后续还需要 h 收敛和更高阶传播级检查。

| 案例 | R | T | R+T | A_balance |
| --- | ---: | ---: | ---: | ---: |
| Stage 4A flat-layer | 0.9998437464349123 | 0.00013238278492706267 | 0.9999761292198394 | 2.38707801606868e-05 |
| Stage 4B zero-contrast | 0.9998437464349121 | 0.00013238278492706275 | 0.9999761292198392 | 2.38707801607977e-05 |

## 网格 / 自由度 / 求解成本

| 案例 | cells | DoF | elapsed_seconds | max_rss_mb |
| --- | ---: | ---: | ---: | ---: |
| Stage 4A flat-layer | 12 | 75 | 8.981464774988126 | 281.125 |
| Stage 4B zero-contrast | 27 | 144 | 8.536891061987262 | 280.5 |

## 最小可信验证表

| 阶段 | 目的 | 当前状态 | 是否可作物理 benchmark |
| --- | --- | --- | --- |
| Stage 4A flat-layer sanity | 检查 flat-layer / dtn_port 路径，并记录 Si 基座吸收余额 | 本轮轻量运行通过 | 否，仍需 h 收敛 |
| Stage 4B zero-contrast | 检查 grating 几何/tag 不引入额外散射 | 本轮轻量运行与 Stage 4A 匹配 | 否，仍需 h 收敛 |
| Stage 4A EUV auto_propagating h 收敛 | 检查传播级和网格收敛 | 未运行 | 未满足 |
| Stage 4B real Si block | 使用 Si 光栅复折射率讨论真实 grating | 只固定了参数入口，未运行可信物理结果 | 前三项稳定且基座复折射率给出前不能讨论 |

## 已知问题

- 本轮确认基座使用 Si 复折射率，并开始记录吸收余额；但 h=50 nm 太粗，不能作为正式 EUV 物理 benchmark。
- 本轮轻量运行使用 `stage4_dtn_order_policy=zero_order`，不替代后续 `auto_propagating` h 收敛。
- dtn_port 路径的总功率来源是 `dtn_auxiliary_port_amplitudes`；`diffraction_3d.py` 的 probe 后处理官方来源是 E/H Fourier，两者在 summary 中需要分开读。

## 给审查的下一步问题

- `official_result` 与 `physical_benchmark_candidate` 的区分是否足够清楚？
- 当前 `A_balance` 是否足以作为轻量吸收 sanity，还是需要再补体吸收积分作为交叉检查？
- 下一轮 h 收敛应优先跑 Stage 4A auto_propagating，还是先跑真实 Si block 的粗网格对照？
