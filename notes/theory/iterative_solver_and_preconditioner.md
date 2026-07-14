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

## 10. Task030：为什么对称平滑能降内存而 p/h coarse 失败

Task030 验证了真正的 nonmatching p2/p1 H(curl) transfer 与

$$A_H=P^H(F-CH^{-1}D)P,$$

但 792 维 `h10/p1` coarse 在五类 smoother 下的 100 步 residual 都比基线差两个数量级。代数正确不代表 coarse space 覆盖了 Maxwell 的慢误差；一个有效 coarse 通常还要处理梯度/近核、curl-commuting 映射、材料界面和 grazing-wave 方向。

相反，保留 75D 波动 coarse 后，对称组合

$$y_1=M_s^{-1}r,quad r_1=r-Ay_1,quad
y_2=y_1+Z(Z^HAZ)^{-1}Z^Hr_1,
\quad r_2=r-Ay_2,quad
y=y_2+M_s^{-1}r_2$$

把 pre-only 的互补误差再交给局部平滑器，因此配置上可从 ILU1 改为 ILU0 而不丢失该冻结目标的收敛。当前 PETSc `global_slab_factor_nnz` 对 ILU1/ILU0 报告相同值，不能据此宣称 stored factor fill 已减少；该测量保持 unresolved。随后只在 local submatrix 加 diagonal shift、setup 后只保留 factor、释放 source submatrix/KSP/PC wrapper，并把 FGMRES restart 从 100 降到 90；已观测内存下降主要归因于这些生命周期与 Krylov-basis 变化，而不是已证明的 factor-nnz compression。这些存储优化不改变 outer exact operator。

Task030 h5/h3 的 full true residual 与 R/T/A 已通过，但该组合仍是显式 experimental profile。h2 和参数域外鲁棒性必须由实测决定，不能从对称公式推导出无条件收敛保证。

factor-only 生命周期只在 qualified local image 的 PETSc 3.24.0 complex build 完成 action/destroy 回归；`PC.getFactorMatrix()` 的跨版本引用计数与生命周期语义必须重新验证。

## 11. Task031：assembled-F-free public form action、PC 合法性与内存/时间交换

### 11.1 “Condensed matrix-free”仍可能保留 assembled F

`A_c=F-CH^{-1}D` 用 shell matrix 不等于 `F` 本身没有装配。旧路径的 shell action 内部仍调用 assembled `F.mult`，同时 slab extraction/coarse setup 也依赖 F。Task031 把 solve action 改为 bilinear form 与 MPC field 的 public action：

$$y_F = a(u,\cdot),$$

其中输入 active vector 先写入 MPC Function、backsubstitute 到 slave，再由 `dolfinx_mpc.assemble_vector(ufl.action(a,u))` 形成输出；MPC slave 行保持原 assembled operator 的 unit-row 约定。h5/h3/h2 action error 均小于 `10^{-15}`，而 solve ledger 中不再出现 F。

这不是“零存储”：form、Function、MPC map、C/D/H、coarse basis、slab factors、Krylov vectors 和装配临时量仍存在。它也不是已缓存优化的低层 element-kernel matrix-free；当前每次 apply 仍进行 vector assembly 和通信。memory-free 与 matrix-free 不是同义词。

### 11.2 非线性 PC 为什么必须用 FGMRES

若局部两步 GMRES 根据输入 residual 自适应生成 Krylov 系数，则一般有

$$M^{-1}(\alpha x+\beta y)\ne\alpha M^{-1}x+\beta M^{-1}y.$$

Task031 的随机向量 certificate 给出 linearity error `2.374308e-2`，因此普通 GMRES、TFQMR、BCGS 的固定线性 PC 假设不成立。FGMRES 保存每一步实际预条件向量，允许 $M_k^{-1}$ 随迭代变化。固定 Richardson 变体虽把 error 降到 `3.611e-15`，但 200 步 residual 为 0.7703，说明算法合法性与实际平滑能力必须分别验证。普通 GMRES 是已实现但被当前 PC 阻塞的 port；TFQMR/BCGS 只是未 target-qualified 的 exposed interfaces。

### 11.3 overlap 与 factor 存储

把 16 slabs overlap 从 0.25 降到 0.125，使 h5 factor nnz 从 7,046,752 降到 5,666,368（-19.59%），但 200-step residual 从 `8.612e-4` 变为 `1.107e-3`。这是典型的内存/迭代交换：factor 更小并不自动意味着总时间或迭代更优。Task031 只有在 h5/h3/h2 full true residual 全通过后才接受该组合。

对 factor 做 exact hash 后，16 个 fingerprints 全部不同。周期/材料对称性不能替代离散矩阵完全相等；任务禁止 approximate reuse，所以没有 dedup 正结果。

### 11.4 内存口径

Task031 的 peak authority 是同一 0.25 s 采样时刻四个 live MPI worker 当前 RSS 之和：

$$M_{\rm worker}(t)=\sum_{r\in\mathrm{live}}\mathrm{RSS}_r(t),\qquad
M_{\rm peak}=\max_t M_{\rm worker}(t).$$

不能用 $\sum_r\max_t\mathrm{RSS}_r(t)$ 代替，因为各 rank 的峰值可能不同时发生。cgroup current/peak、process tree 与 swap 分开记录。compact lifecycle 让 h2 solver release 后 current RSS 从 peak 附近降到约 6.50 GiB，但 peak success 仍只使用全 run 最大值 7.897675 GiB。

### 11.5 最终边界

Task031 h2 external simultaneous / legacy internal peak 为 7.897675 / 8.176441 GiB。相对 Task030 历史 9.374729 GiB 的辅助观察降幅约 15.8% / 12.8%，但 sampler 不完全同口径，故保守结论为从约 9.4 GiB 压到约 8.0–8.2 GiB。solve time 增至约 5.01x，主要来自每次 public form action 的装配/通信，不是一次性释放 `F`。因此它是 memory-first opt-in，不是 ordinary speed profile。所谓“保证收敛”只指 frozen target 的 reported/condensed/full residual 与 official R/T/A 全部通过，不是参数域外的谱界或数学无条件保证。
