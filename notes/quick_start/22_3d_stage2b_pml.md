# 3D Stage 2B PML

```bash
python src/main.py --preset 3d_stage2b_pml_smoke
```

Stage 2B 在双 Floquet 空气盒上下加入 z 向复坐标拉伸和各向异性变换材料。它的目标是检查 PML 张量、标签、衰减和外边界处理，不是证明真实 Stage 4 光栅已收敛。

## 参数与诊断

| 参数 | 先做什么 |
|---|---|
| `pml_top/bottom_thickness` | 至少两档厚度 |
| `pml_alpha` | 与厚度联动测试 |
| `mesh_target_size` | 确保 PML 内有足够层数 |
| 外边界 | 区分 natural 与 zero tangential 的影响 |

检查 PML 内包络衰减、物理区场误差、外边界反射和矩阵残差。当前能力矩阵把 Stage 2B 标为实验性验证路径，不得写成任意角度/材料的生产资格。

理论见 [`../theory/pml_robin_and_open_boundaries.md`](../theory/pml_robin_and_open_boundaries.md)。
