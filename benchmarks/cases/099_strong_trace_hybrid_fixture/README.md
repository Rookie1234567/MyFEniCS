# Case099：strong trace-subspace Hybrid 小型资格化夹具

本目录只保存 Task036 Review V3 所需的轻量、可复现夹具证据。它回答的是：

> strong-trace 方程、接口行映射、Floquet 方向和 standard/static 两条代数路径是否按设计实现？

它不是 production benchmark，也不证明正式 `p5/h10/M120` Hybrid 已通过物理精度
Gate。正式 A004-S 结果仍因能量闭合和固定衍射通道失败而受控停止；详见
[strong_trace_hybrid_anchor_results.md](../../../docs/task036_forward_solver_bugfix_hardening/outcomes/strong_trace_hybrid_anchor_results.md)。

## 证据

- [strong_trace_exact_fixture_v1.json](records/strong_trace_exact_fixture_v1.json)
  - 固定随机种子的 lossy Petrov dense fixture；
  - 实际 H(curl)/Floquet standard 与 static micro-fixture；
  - MPI1、MPI2、MPI8 测试命令和结果；
  - `D R = I`、trace complement 排除、方形系统、无 dense interface square；
  - factor 释放后再执行 static field recovery。
- [a004_strong_trace_fixed_channels_v1.csv](records/a004_strong_trace_fixed_channels_v1.csv)
  - A004-S 全部 96 个固定通道；
  - old projection-only 与 new strong-trace 相对 Full3D 的正式误差口径；
  - significant/weak 分类、逐通道 pass/fail 和 old/new 差值。

本目录没有 runner、campaign、watchdog 或状态机。权威实现仍位于
`src/solvers/hybrid_strong_trace_direct.py`，普通 Hybrid 默认路径未改变。
