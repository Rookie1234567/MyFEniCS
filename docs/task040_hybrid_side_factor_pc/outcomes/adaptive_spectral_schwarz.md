# Adaptive spectral Schwarz outcome

## 状态

```text
status = NOT_RUN_DUE_TO_TRUE_RESOURCE_GATE
```

Review V7 §10.3 的 wall/resource Gate 是独立停止边界；本轮 corrected moving-PML formal 在
第一个 source 的 one-apply/FGMRES 之前因 `wall_timeout` 达到该 Gate，因此 adaptive 未启动。
这不是 adaptive negative。若 moving-PML 得到 valid positive，按 Review 路由应进入
factor-free local service；本轮没有 valid PML signal。

这不是 adaptive 的数值 negative，也不是 0.7 nm capacity 的否定；没有构造 local coarse、
没有运行 sweep、没有产生 residual、memory、factor 或 Full3D handoff 数据。依赖该路线的
factor-free local service、完整 Hybrid、h3、0.7 nm 和 arbitrary Full3D 均保持未运行/未资格化。

本轮 stop 的 resource evidence 见
[moving-PML outcome](moving_pml_sweep.md)：peak process-tree RSS=`40560816128 B`，swap=`0`，
elapsed=`21601.760233s`，硬线=`45 GiB`、wall=`21600s`。在新的 Review 决定前不启动
adaptive 或任何第三次 heavy formal。
