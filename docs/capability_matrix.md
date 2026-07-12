# 能力矩阵

| 能力 | 2D | 3D | MPI | 正式程度 | 主要限制 |
|---|---:|---:|---:|---|---|
| Floquet periodic constraints | 是 | 是 | 是 | 稳定 | 高阶3D使用topological trace |
| DtN modal port | 是 | 是 | 是 | 稳定 | 参考面影响有损基底中的T |
| complex refractive index | 是 | 是 | 是 | 稳定 | 必须complex PETSc |
| volume absorption | 是 | 是 | 是 | 稳定 | 仅在有损区域积分 |
| official R/T/A | 是 | 是 | 是 | 稳定 | 以DtN modal amplitudes为准 |
| direct solve | 是 | 是 | 是 | 默认 | 细网格因子内存高 |
| exact static condensation | 数学通用 | 是 | 是 | 稳定模块 | 当前端口辅助块较小 |
| workstation iterative p2 h5/3/2 | 不适用 | 是 | MPI4 | 显式候选 | 固定目标几何与profile |
| h1.5 production solve | 不适用 | 否 | 未完成 | 不支持 | 需要后续验证 |
| wavelength/angle/geometry sweep鲁棒性 | 部分 | 未完成 | 未完成 | 不支持 | 先逐点与direct交叉验证 |
| spectral/GenEO coarse | 不适用 | 实验失败 | 研究分支 | 不支持 | 不进入普通API |
