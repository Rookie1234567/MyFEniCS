# 层级设计与实际结论

## 已实现的基础设施

首版采用材料面对齐、周期面对配的 boundary-fitted hexa 网格：fine `h5/p2` 为 `12×5×28` 单元，coarse `h10/p1` 为 `6×3×14` 单元。传递算子按 coarse active/master DoF 逐列构造，使用公开的 DOLFINx nonmatching interpolation 数据，并在每列执行 MPC backsubstitution 与 homogenize；restriction 固定为 Hermitian transpose。

此外盘点了 `h5/p1` 和 `h7.5/p1`，为后续多层扩展保留了 5160、2232、792 active DoF 的层级序列。当前只对 `h10/p1 -> h5/p2` 建立了完整 MPI4 transfer 与精确 condensed Galerkin coarse operator：

```text
A_c = P^H (F - C H^-1 D) P
```

`H=I` 的当前 Stage4 合同被显式断言；全部 80 个传播模态都进入 Galerkin action，没有降模态近似。

## 性能结论

代数层级通过，但作为当前目标 RHS 的 coarse correction 失败。相同 Task27 slab smoother：

- 不加 p/h coarse 的 20 步真残差为 `0.381817`；
- 加 792 维 p/h Galerkin coarse 后反而为 `0.685751`。

五个正式 p/h 候选在 100 步仍停留于 `0.3749–0.6802`，比 Task27 基线差 146–264 倍。因此不能把“transfer 正确”包装成“真正多重网格已有效”。本任务最有效的全局慢误差机制仍是 Task27 的 75 维 Floquet z-hat 波动粗空间。

复杂度口径也保持显式：p/h 两级的 grid complexity 为 `(44698+792)/44698 = 1.0177`，assembled coarse operator complexity 为 `(4840396+36216)/4840396 = 1.0075`，另有 transfer/F nnz ratio `145998/4840396 = 0.0302`。最终 75D dense coarse 的 grid complexity 在 h5/h3/h2 分别只有 1.00168/1.00038/1.00012，coarse operator complexity 约 1.00116/1.00027/1.00009；实际内存仍主要来自 F、slab factors、work vectors 和 FGMRES basis，而不是 coarse matrix。

## 合并边界

active DoF map、非匹配 H(curl) transfer、MPI cache、精确 condensed Galerkin 和小型 multilevel/low-rank 组件具有独立基础设施价值；失败的 p/h solver profile 不得提升为 ordinary 或 workstation 默认。
