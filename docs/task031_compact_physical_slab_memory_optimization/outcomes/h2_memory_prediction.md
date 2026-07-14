# h2 内存预测

## 已知点

```text
Task031 h5: n=44,698, simultaneous worker peak=1.6195983887 GiB
Task031 h3: n=198,438, simultaneous worker peak=3.4743461609 GiB
Task030 h3 baseline=3.7929115295 GiB
Task030 h2 baseline=9.374729 GiB
h2 n=615,108
```

## 模型 A：h5/h3 DoF–RSS 仿射外推

以 `M(n)=a+b*n` 穿过 Task031 h5/h3 两点并外推到 h2：

```text
M_h2_affine = 8.5011300444 GiB
```

该模型把固定运行时开销与随 DoF 线性增长部分分开，是偏保守的中心预测。

## 模型 B：Task030 h2 按 h3 实测比例迁移

Task031/Task030 h3 比例为 `3.4743461609 / 3.7929115295 = 0.9160103350`。将同一结构收益迁移到 Task030 h2：

```text
M_h2_ratio = 9.374729 * 0.9160103350 = 8.5873486520 GiB
```

该模型独立使用 Task030 跨分辨率 h2 baseline，不依赖 h5/h3 仿射斜率。

## 保守上界

h5 的观测收益最弱，仅 4.03248%。将这一较弱收益应用到 Task030 h2，再增加 5% allocator/采样余量：

```text
M_h2_upper = 9.374729 * (1 - 0.0403247681) * 1.05
             = 9.4465299886 GiB
```

两个中心预测都 `<=8.8 GiB`，保守上界 `<=10.0 GiB`。实测 h2 为 7.8976745605 GiB，低于两套中心预测和上界。

## 限制

预测基线与 Task030 历史 peak 的采样实现不完全相同，因此它是安全放行工具，不是统计置信区间。最终分类只使用 h2 full-run external simultaneous RSS 实测。
