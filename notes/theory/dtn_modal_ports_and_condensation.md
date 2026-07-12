# Fourier-DtN、辅助未知量与精确凝聚

## 1. 周期端口模态

在均匀上下端口，对每个二维衍射级 `(m,n)`：

$$
\alpha_m=k_x+2\pi m/L_x,\qquad
\gamma_n=k_y+2\pi n/L_y,
$$

介质波数 `k=k0*n`，纵向传播常数

$$\beta_{mn}=\sqrt{k^2-\alpha_m^2-\gamma_n^2}.$$

代码选择满足出射/衰减条件的平方根分支：传播级取正确外向相位，倏逝级取远离计算域衰减的符号。接近 `beta=0` 是 Rayleigh 截止，必须用容差标记，不能用普通浮点符号硬分类。

3D 每个非退化横向波数有两种切向极化；`common/modes_3d.py::outgoing_port_modes_3d` 枚举 order、构造 s/p 基、E/H 向量、模态功率和 top/bottom 出射模式。

## 2. DtN 算子

Dirichlet-to-Neumann 算子把边界切向电场 Fourier 系数映射为 Maxwell traction。抽象写作

$$
T\mathbf E_t=\sum_j Y_j\langle\mathbf E_t,\mathbf q_j\rangle\mathbf q_j,
$$

其中 `q_j` 含 order、极化、相位和边界法向，`Y_j` 是对应 modal admittance/traction。传播模态贡献实功率，倏逝模态仍参与边界反应但平均远场功率为零。

2D TM/TE 的 admittance 不相同；代码分别在 `solve_port_maxwell::run_port_case` 和 `solve_te_maxwell::run_te_port_case` 形成，不能复用一个标量公式。3D 的 traction、投影、入射源和功率统一由 `dtn_port_3d::solve_stage4_dtn_port_total_field` 组装。

## 3. 显式低秩装配

把所有 FE 边界投影向量收为 Q、modal coefficient 收为 Y，显式算子是

$$A_{exp}=F+Q^H YQ$$

（正负号由弱式和 Q/Y 定义吸收）。它适合小系统做参考，但直接外积会给 FE 矩阵增加非局部稠密耦合。2D `explicit` 路径保留它作为交叉核验，不是大规模首选。

## 4. auxiliary 增广装配

引入少量端口幅值 `a`，把系统写为

$$
\begin{bmatrix}F&C\\D&H\end{bmatrix}
\begin{bmatrix}e\\a\end{bmatrix}
=
\begin{bmatrix}f\\g\end{bmatrix}.
$$

`e` 是 FE 自由度，`a` 是端口模态辅助未知量；C/D 只连接边界 trace 与模态，H 是小型 modal block。这样保留 FE 块稀疏性。当前 3D 端口逐模插入 `H[j,j]=1`，所以已验证实现严格为 `H=I`；这是一种实现选择，不是一般 DtN 理论要求。`dtn_port_3d::solve_stage4_dtn_port_total_field` 负责分布式增广系统，辅助幅值同时成为 official R/T 的直接来源。

## 5. 精确 Schur 凝聚

若 H 可逆，第二行给出

$$a=H^{-1}(g-De).$$

代回第一行：

$$
\boxed{A_c e=(F-CH^{-1}D)e=f-CH^{-1}g.}
$$

求得 e 后按上式回代 a。这里“精确”指代数上与同一增广离散系统等价，不代表连续物理或网格误差为零。

`solvers/condensed_dtn.py` 的映射：

| 数学 | 代码 |
|---|---|
| 提取 F/C/D/H | `extract_petsc_condensed_blocks` |
| `H^-1` | `condensed_dtn::SmallDenseInverse` |
| `A_c x` | `condensed_dtn::CondensedDtnMatContext.mult` |
| matrix-free shell | `condensed_dtn::create_matrix_free_condensed_operator` |
| condensed RHS | `condensed_dtn::condensed_rhs` |
| 显式参考 | `condensed_dtn::build_explicit_condensed_operator` |
| 回代 | `condensed_dtn::recover_petsc_auxiliary` |

matrix-free action 按 `Fx-C(H^-1(Dx))` 计算，不显式形成稠密 Schur 更新。

`SmallDenseInverse` 当前先 MPI 收集 H，再执行 `np.linalg.inv(H_dense)`，然后用显式 inverse 乘 RHS；它不是 LU factor object。对当前约 80 x 80 的良态 H 可用，但若辅助模态显著增长，应改为 factor/solve 接口。

`build_explicit_condensed_operator` 只是代数回归 reference：它先验证 `H` 在 `1e-13` 绝对容差内等于单位阵，再形成 `F-C@D`。非单位 H 会抛 `NotImplementedError`；一般可逆 H 仍由 matrix-free action 正确处理，不能把 explicit helper 描述为一般分布式 Schur builder。

## 6. 转置与 Hermitian

端口系统含复相位、损耗和出射条件，通常既非实对称也非 Hermitian。代码/测试必须区分 `transpose` 与 `Hermitian transpose`。`test_22_condensed_dtn.py` 同时比较 dense、explicit、matrix-free、回代以及转置 action；不能因公式外观看似对称就设置 CG 或错误共轭。

## 7. 三种残差

迭代生产路径同时记录：

1. PETSc reported relative residual；
2. 重新执行 matrix-free `A_c e-b_c` 的 condensed true residual；
3. 回代 a 后原增广系统的 full true residual。

三者接近才说明监控范数、凝聚 action 和回代一致。RTA 只在 full residual 低于阈值时执行。

## 8. 资格边界

- 2D auxiliary/explicit 的小案例等价由 benchmark 002 证明。
- 3D condensed matrix-free 的代数等价由 benchmark 022/`test_22` 证明。
- 工作站 h=5/3/2 记录证明特定 target case 可解，不证明所有 DtN 几何都具有同样迭代次数。
