# Geometry Validation

## 结论

本轮 task008 采用 50 x 25 x 140 nm 计算域、17 x 25 x 120 nm 光栅、10 nm 基座和 10 nm 顶部空气层。`air_height` 参数在代码中表示从界面 z=0 到顶部边界的高度，因此本轮传入 `air_height=130 nm`，总高度为 `130 + 10 = 140 nm`。

## Full-Span Y Grating

`grating_width_y = period_y = 25 nm` 在当前 mesh builder 中是合法输入。代码检查允许 `cfg.y_min <= grating_y_min < grating_y_max <= cfg.y_max`，因此 y 方向全周期填充不会被拒绝。本轮没有把宽度偷偷改成 24.999 nm。

## Material Tags

光栅材料区域为 x 方向 17 nm、y 方向 25 nm、z 方向 0 到 120 nm。基座为 z=-10 到 0 nm，空气区域为 z=0 到 130 nm 中未被光栅占据部分。由于 y 方向全跨周期，结构可理解为 y 方向 extruded ridge / full-span periodic block。

## Boundary Compatibility

x/y Floquet MPC 仍按周期边界处理。full-span y grating 与 y 周期边界共面，但材料判定基于单元 midpoint，因此没有为了避开周期边界而改变用户指定尺寸。

## 实际参数

| parameter | value |
| --- | --- |
| period_x | 50 nm |
| period_y | 25 nm |
| grating_width_x | 17 nm |
| grating_width_y | 25 nm |
| grating_height | 120 nm |
| substrate_thickness | 10 nm |
| air_height | 130 nm |
| total_height | 140 nm |
