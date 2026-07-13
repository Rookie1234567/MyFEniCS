# 工作站迭代器与预条件器

## 1. 求解对象

正式迭代器不直接处理完整辅助增广矩阵，而处理精确凝聚后的 FE 算子

$$A_c=F-CH^{-1}D,$$

其 action 由 PETSc shell matrix 实现。H 很小且精确求逆；求得 FE 解后回代辅助幅值，并在原增广系统重算 full residual。

## 2. 为什么是 right-preconditioned FGMRES

系统非 Hermitian、不定；预条件器内含局部迭代、两次 smoother 和 coarse correction，不必是固定线性自伴算子。FGMRES 允许每步预条件作用变化。右预条件形式

$$A_cM_k^{-1}y=b,\qquad e=M_k^{-1}y$$

使外层 residual 仍对应原方程。PETSc 使用 `KSPFGMRES`、right PC、restart=100，官方接口见 <https://petsc.org/release/manualpages/KSP/KSPFGMRES/>。

## 3. 75 维物理 coarse space

沿 z 取 25 个 hat 中心，每个中心乘 x/y/z 三个场分量和已知横向 Floquet 相位，得到 75 个候选方向。依次正交化并压缩为稀疏向量 Z，Galerkin coarse operator：

$$A_0=Z^HA_cZ.$$

coarse correction 为 `Z A0^-1 Z^H r`。每次 setup 检查 rank=75 与 condition；condition 超阈值即资格失败。实现位于 `benchmarks/run_workstation_iterative._fixed_floquet_hat_basis` 和 `physical_slab_two_level.SparseGalerkinTwoLevelPc`。

## 4. shifted-F 物理 slab smoother

从 FE 块 F 构造带吸收位移的局部近似，概念上

$$F_s=F-i\sigma D_F,$$

代码以对角尺度和 `absorption_shift=0.1` 稳定局部不定问题。物理域沿 z 分 16 个带 0.25 layer overlap 的 slab；每个 slab 提取子矩阵，用 GMRES(1)+ILU(1) 近似解，连续做两次 smoother action。

## 5. owner-computes Schwarz

每个 slab 只由一个 MPI owner 保存/分解，避免所有 rank 复制所有子域因子。`balanced_subdomain_owners` 按负载分配；apply 时 owner 计算局部结果，再装配到全局向量。two-color assembly 降低同时写入冲突。`test_23` 覆盖空 owner、cache、sm2 生命周期、MPI4 ownership 和销毁顺序。

## 6. 两级组合

`SparseGalerkinTwoLevelPc.apply` 先 coarse，再用 residual 驱动 smoother（代码中的精确顺序以实现为准）。核心作用分工：

| 组件 | 主要消除 |
|---|---|
| coarse | 跨越全厚度的低频/Floquet 慢方向 |
| shifted slab | 局部高频误差与材料/网格耦合 |
| exact H inverse | DtN 辅助小块，不把 modal error 留给 FE PC |

## 7. 资格参数

| 参数 | 固定值 |
|---|---:|
| p / MPI | 2 / 4 |
| h | 5、3、2 nm |
| coarse slabs/dim | 24 / 75 |
| physical slabs/overlap | 16 / 0.25 |
| shift/ILU | 0.1 / 1 |
| local GMRES | 1 step |
| smoother actions | 2 |
| FGMRES restart/rtol/max_it | 100 / `1e-6` / 3000 |

任何偏离均写入 `qualification_deviations` 并标为 experimental。

## 8. 三残差与 RTA Gate

reported、condensed true、full augmented true 三者必须 `<=1e-6` 且相互差满足 Gate。只有 full residual `<=1.1e-6` 才做 official RTA。`ksp_reason>0`、coarse condition、总 RSS 和能量闭合也属于资格条件。

## 9. 已知边界

该 PC 对一个 80 度、13.5 nm、Si、50 x 25 x 140 nm target case 的 h=5/3/2 有证据。尚未证明角度无关、材料无关、任意层厚鲁棒或 h<2 可行；这些是后续研究问题，不应从三点结果外推。
