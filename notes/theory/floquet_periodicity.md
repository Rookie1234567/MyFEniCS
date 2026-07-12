# Floquet 周期条件

## 1. 连续条件

对 x 周期 `Lx`、y 周期 `Ly` 的 Bloch 波：

$$
\mathbf E(x+L_x,y,z)=e^{ik_xL_x}\mathbf E(x,y,z),\qquad
\mathbf E(x,y+L_y,z)=e^{ik_yL_y}\mathbf E(x,y,z).
$$

第 `(m,n)` 个衍射级横向波数为

$$
\alpha_m=k_x+\frac{2\pi m}{L_x},\qquad
\gamma_n=k_y+\frac{2\pi n}{L_y}.
$$

Floquet 条件只处理横向周期；上下开域由 PML、Robin 或 DtN 另行处理。

## 2. H(curl) 自由度为什么不只是节点乘相位

Nedelec 自由度是带方向的边/面切向矩。周期配对必须同时处理：

1. 几何平移后的实体对应；
2. `exp(i*k*L)` 复相位；
3. 边方向相反时的 orientation 符号；
4. x/y 周期面交线和角点的主从链；
5. p=2 的高阶 trace moment，而不只是 p=1 边积分。

忽略第 3 至 5 项会得到“约束数量看似正确、场分量或功率却错误”的系统。

## 3. 离散映射

把完整自由度表示为 `u=C u_r`，其中 C 的从属行含相位和方向系数。Galerkin 约化：

$$A_r=C^HAC,\qquad b_r=C^Hb.$$

求得 `u_r` 后再用 C 重构完整场。这个共轭转置不是普通转置；复相位问题中两者不可替换。

## 4. 2D 实现

| 文件 | 作用 |
|---|---|
| `constraints/floquet_constraint.py` | TM Nedelec 边迹配对、manual 约束、mismatch |
| `constraints/floquet_scalar_constraint.py` | TE 标量节点配对 |
| `solve_vector_maxwell.py` | manual `C^HAC` 或 `dolfinx_mpc` |
| `solve_te_maxwell.py` | 标量对应路径 |

2D manual 当前只支持串行；MPI 应使用允许的 `mpc_official` 路径，DtN 非局部边界仍受 runner 限制。

## 5. 3D 实现

`constraints/floquet_3d.py::build_double_floquet_mpc` 根据阶次选择：

| 模式 | 用途 |
|---|---|
| `topological_edges_p1` | p=1 拓扑边配对 |
| `topological_trace_p2` | p=2 高阶切向 trace 配对 |
| `auto` | 根据阶次安全选择 |
| `sparse_facet` | 历史 p=1 别名 |

x、y 两组从属关系由同一个 MPC 生命周期管理，避免 corner master chain 循环。`test_05/06/12/17` 检查配对、解析场相位、方向和 p=2 trace。

## 6. 验证层级

| 检查 | 能发现 | 不能证明 |
|---|---|---|
| pairing coordinate error | 几何配错 | 相位/方向正确 |
| probe reconstruction | 相位函数错误 | PDE 已正确求解 |
| DOF mismatch | 重构后边界不一致 | 端口功率正确 |
| 解析平面波 Stage 2A | Floquet+PDE 联合错误 | PML/DtN/光栅正确 |
| MPI1/MPI4 对照 | 分区依赖 | 网格收敛 |

改变网格类型、p、周期或约束模式后必须重新跑对应层级。
