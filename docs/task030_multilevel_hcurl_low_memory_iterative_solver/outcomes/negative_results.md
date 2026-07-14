# 负结果与停止理由

## 已继承的边界

- Task011 的 full-complex AMS/HX 不稳定；real positive proxy 的内存也高，不能直接外推到复 Floquet/DtN。
- Task019/025 的同网格 p2→p1 coarse 对真实 RHS 很弱，不能冒充 h-GMG。
- Task022/023 已证明全模态 low-rank selector 的瓶颈是 FE response 质量，不是 80 模态本身。
- Task027 的大 z-slab ILU1 能收敛，但 h2 峰值达到 13.08 GB。

## Task030 新负结果

1. **跨网格 `interpolation_matrix` 误用**：产生大量零行。改用 nonmatching point ownership、active-column assembly、MPC backsub/homogenize 后关闭正确性问题。
2. **五类 p/h coarse 候选**：Jacobi、层 patch、柱 patch、cell patch、slab patch 的 100 步真残差为 `0.375–0.680`，是基线的 146–264 倍。transfer 与 Galerkin action 已通过，因此根因是 792 维 p1 coarse 对当前波动慢误差不适配，而非实现 bug。
3. **p/h coarse 主动伤害**：相同 ILU1-sm2 slab 的 20 步残差从无 p/h coarse 的 `0.381817` 恶化到 `0.685751`。不能继续用参数扫描掩盖机制失败。
4. **全 80 模态 Woodbury**：在弱 p/h FE inverse 上只把 20 步残差从 `0.676603` 改到 `0.657702`，且内存上升；在 Task27 PC 上也从 baseline smoke 的约 `0.033745` 恶化到 `0.036275`。small Schur 条件数不是主瓶颈。
5. **去 overlap 且仅 pre-smooth**：100 步 `0.00329134`，比基线差 27.9%，触发 negative Gate。
6. **扩大波动 coarse 到 225 维 x harmonics**：100 步 `0.00279637`，没有达到 weak-positive，内存接近基线。非对称 `{-2,-1,0}` 更差。
7. **增加 z coarse 节点**：32/48 slabs 未形成稳定收益，48 slabs condition 上升至约 1747。
8. **单次廉价 post smooth**：20 步 `0.0746202`，明显负面；已从正式实现删除。
9. **restart80**：内存更低但 100 步 residual ratio `0.8905`，未通过 weak-positive；restart90 是最后一个通过点。
10. **h2 首次 1800 步**：峰值 9.342 GB 通过内存，但真残差 `1.461e-6` 未通过。只允许同一最终候选做资格复跑，不展开第二个 h2 参数族；该同候选随后在 1873 步通过，首轮仍作为严格的负/不完整证据保留。

这些负结果都保留为证据；没有把 AMS、失败 p/h profile、Woodbury、x-harmonic 或 restart80 接入普通默认。
