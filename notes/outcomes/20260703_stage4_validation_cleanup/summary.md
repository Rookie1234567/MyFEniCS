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

基座复折射率仍等待用户提供。因此本轮实际轻量运行使用 `n_substrate = 1.45 + 0j` 作为占位数值参数，并统一标记为 `numerical_sanity_only`。

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

Stage 4A flat-layer 无 grating；Stage 4B zero-contrast 保留 block 几何，但设置 `n_grating = 1 + 0j`，使 grating 区域与空气背景无介电常数对比。

## 关键结果

- Docker 内完整单元测试通过：`Ran 59 tests in 2.702s, OK (skipped=10)`。
- Stage 4A flat-layer 跑通，`R+T = 1.0000000000000064`。
- Stage 4B zero-contrast 跑通，`R+T = 1.0000000000000073`。
- 两条轻量运行的 R/T 在数值上匹配，说明 zero-contrast block 几何没有额外引入散射。
- 两条运行均写出 `physical_benchmark_candidate = false`，避免把路径跑通误写成物理 benchmark。

## 能量检查

本轮能量检查只说明 dtn_port 功率归一化和边界端口在该轻量网格下没有明显炸掉，不能单独证明物理正确。

| 案例 | R | T | R+T | A_balance |
| --- | ---: | ---: | ---: | ---: |
| Stage 4A flat-layer | 0.9999103959913871 | 0.0000896040086193742 | 1.0000000000000064 | -6.46513821211253e-15 |
| Stage 4B zero-contrast | 0.9999103959913880 | 0.0000896040086193743 | 1.0000000000000073 | -7.35338439444844e-15 |

## 网格 / 自由度 / 求解成本

| 案例 | cells | DoF | elapsed_seconds | max_rss_mb |
| --- | ---: | ---: | ---: | ---: |
| Stage 4A flat-layer | 12 | 75 | 8.678286976995878 | 280.80859375 |
| Stage 4B zero-contrast | 27 | 144 | 8.327802566986065 | 281.0859375 |

## 最小可信验证表

| 阶段 | 目的 | 当前状态 | 是否可作物理 benchmark |
| --- | --- | --- | --- |
| Stage 4A flat-layer sanity | 检查 flat-layer / dtn_port 路径 | 本轮轻量运行通过 | 否，基座复折射率仍是占位值 |
| Stage 4B zero-contrast | 检查 grating 几何/tag 不引入额外散射 | 本轮轻量运行与 Stage 4A 匹配 | 否，仍是占位基座参数 |
| Stage 4A EUV auto_propagating h 收敛 | 检查传播级和网格收敛 | 未运行 | 未满足 |
| Stage 4B real Si block | 使用 Si 光栅复折射率讨论真实 grating | 只固定了参数入口，未运行可信物理结果 | 前三项稳定且基座复折射率给出前不能讨论 |

## 已知问题

- 用户尚未给出基座材料复折射率，因此本轮不能完成正式 EUV 物理 benchmark。
- 本轮轻量运行使用 `stage4_dtn_order_policy=zero_order`，不替代后续 `auto_propagating` h 收敛。
- dtn_port 路径的总功率来源是 `dtn_auxiliary_port_amplitudes`；`diffraction_3d.py` 的 probe 后处理官方来源是 E/H Fourier，两者在 summary 中需要分开读。

## 给审查的下一步问题

- `official_result` 与 `physical_benchmark_candidate` 的区分是否足够清楚？
- 是否需要在用户提供基座复折射率后，把 Stage 4A/4B 的默认基座占位值从代码中移除？
- 下一轮 h 收敛应优先跑 Stage 4A auto_propagating，还是先补真实基座材料表？

