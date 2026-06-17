# Fourier-DtN 端口的辅助变量法与自动衍射级

本文记录 2026-06-16 对 TM 端口总场法的补充。目标不是替换旧功能，而是在原有显式 Fourier-DtN 端口基础上，增加一条更适合未来大规模 3D 的实现路线。

## 1. 这次新增了什么

原来的 DtN 端口仍然保留，配置名是：

```python
port_dtn_assembly = "explicit"
```

它直接把端口非局部算子装成矩阵外积，适合作为 reference/debug。

新增的默认路线是：

```python
port_dtn_assembly = "auxiliary"
```

它为每个端口、每个 Floquet 衍射级增加一个辅助未知量 `a_m`。这个 `a_m` 就是端口面上第 `m` 级的 Fourier 模态幅值。这样可以避免直接形成端口边界自由度之间的密集外积块，为以后 3D 大端口做准备。

衍射级也新增了一个更直观的开关：

```python
port_use_diffraction_orders = False
```

只使用 0 级。

```python
port_use_diffraction_orders = True
```

自动寻找上端口和下端口中明确传播的 Floquet 衍射级。由于上方空气和下方基座折射率不同，顶部和底部选到的级次可以不一样。

## 2. 旧的 explicit 方法是什么

在端口边界 `Gamma` 上，把切向电场的 `Ex` 展开成 Floquet 级次：

```text
Ex(x) ~= sum_m a_m exp(i alpha_m x)
```

其中

```text
alpha_m = kx + 2*pi*m/L
```

`L` 是周期长度，也就是 `period_x`。

对有限元解向量 `u`，代码先构造一个端口投影向量：

```text
ell_m,i = integral_Gamma exp(i alpha_m x) conjugate(phi_i,x) dGamma
```

这里 `phi_i,x` 是第 `i` 个 Nedelec 基函数的 `x` 分量。

于是模态幅值可以写成：

```text
a_m = (1/L) ell_m^H u
```

出射 DtN 条件给每个级次一个导纳：

```text
beta_m = sqrt((n k0)^2 - alpha_m^2)
Y_m = (n k0)^2 / beta_m
q_m = -i Y_m
```

代码里的端口矩阵项等价于：

```text
A_port,m = (q_m/L) ell_m ell_m^H
```

所有级次求和：

```text
A_port = sum_m (q_m/L) ell_m ell_m^H
```

这就是 `port_dtn_assembly="explicit"`。它非常直接，数学上清楚，结果也容易检查。但如果端口边界自由度数是 `N_Gamma`，一个外积就是接近 `N_Gamma^2` 的耦合。2D 小模型问题不大，3D 大端口就会很吃内存。

## 3. 新的 auxiliary 方法是什么

辅助变量法不直接装：

```text
Q^H Y Q
```

而是把每个模态幅值 `a_m` 当成一个新的未知量。对单个级次，写成两条方程：

```text
A u + q_m ell_m a_m = b
a_m - (1/L) ell_m^H u = 0
```

把所有端口、所有选中的级次放在一起，就是块系统：

```text
[ A   B ] [ u ] = [ b ]
[ C   I ] [ a ]   [ 0 ]
```

其中：

```text
B_m = q_m ell_m
C_m = -(1/L) ell_m^H
```

第二行的意思是：

```text
a = (1/L) ell^H u
```

如果把 `a` 消去：

```text
a = (1/L) ell^H u
```

代回第一行：

```text
A u + q_m ell_m (1/L) ell_m^H u = b
```

就得到：

```text
(A + (q_m/L) ell_m ell_m^H) u = b
```

这正是旧的 explicit 形式。因此 auxiliary 和 explicit 在数学上等价。

## 4. 为什么它更适合大规模 3D

explicit 的问题是：端口上的所有自由度互相耦合。哪怕有限元体矩阵本来很稀疏，`ell ell^H` 也会在端口边界上制造一个接近密集的块。

auxiliary 的矩阵结构不同。每个端口模态只连接：

```text
端口边界 dof <-> 一个辅助 dof
```

矩阵新增的是“细长列”和“细长行”，而不是端口自由度之间的两两耦合。对 3D 来说，这比显式外积更容易保持稀疏结构，也更容易过渡到 PETSc 的块预条件、FieldSplit 或矩阵自由低秩算子。

## 5. Floquet 周期约束怎么处理

左右边界的 Floquet 约束仍然只作用在有限元自由度 `u` 上：

```text
u = C q
```

辅助变量 `a_m` 是全局端口模态幅值，不属于左/右边界上的有限元自由度，所以不参加 Floquet 周期约束。

manual 后端里实际使用的是块嵌入：

```text
[ u ] = [ C  0 ] [ q ]
[ a ]   [ 0  I ] [ a ]
```

也就是：

```text
C_aug = block_diag(C, I_aux)
```

然后求：

```text
C_aug^H A_aug C_aug x = C_aug^H b_aug
```

这样可以保持旧的手写 Floquet 消元逻辑，同时让辅助模态自由度独立存在。

## 6. 自动衍射级控制

旧配置 `port_dtn_order_count=N` 表示强行使用：

```text
m = -N, ..., 0, ..., +N
```

新配置更适合日常使用：

```python
port_use_diffraction_orders = False
```

只选：

```text
top    = [0]
bottom = [0]
```

```python
port_use_diffraction_orders = True
```

代码会根据传播条件自动选级次。对某一侧介质 `j`：

```text
|kx + 2*pi*m/L| < n_j k0
```

满足这个条件的级次就是传播级次。代码会分别检查顶部空气侧和底部基座侧，所以可能出现：

```text
top    = [-1, 0]
bottom = [-1, 0, 1]
```

0 级永远会包含。这样即使某些极端角度下 0 级接近临界，程序也会保留最基本的入射/出射通道，并在 metadata 里给出提示。

## 7. Rayleigh anomaly 提示

当：

```text
beta_m = sqrt((n_j k0)^2 - alpha_m^2) ~= 0
```

这个衍射级处在传播和倏逝的临界附近，也就是 Rayleigh anomaly 附近。此时：

```text
Y_m = (n_j k0)^2 / beta_m
```

会变得很大，线性系统可能病态。

代码会在日志和 `run_summary.json` 里记录：

```text
side
order
alpha
beta
is_propagating
is_near_rayleigh
```

如果接近 Rayleigh anomaly，会在 `solver_log.txt` 里看到 warning。

## 8. 后处理现在有哪几套 R/T

普通的水平探测线法仍然保留：

```text
power_metrics.json
diffraction_orders.csv
```

它在结构上方和下方的均匀区域各取一条水平线，用 `Ex` 和由 `curl(E)` 恢复的 `Hz` 拆分上下行波。它适合所有方法统一对比，但会受采样线位置、网格、数值导数影响。

DtN 端口法会额外输出端口面法：

```text
dtn_port_power_metrics.json
dtn_port_diffraction_orders.csv
```

这组结果直接复用装配 DtN 端口时的压缩投影向量 `ell_m`，重新从有限元解 `u` 计算：

```text
a_m = (1/L) ell_m^H u
```

如果使用 auxiliary，还会额外输出：

```text
dtn_auxiliary_amplitudes.json
dtn_auxiliary_power_metrics.json
dtn_auxiliary_diffraction_orders.csv
```

这组结果直接使用线性系统中求出来的辅助未知量 `a_m`。理论上：

```text
dtn_auxiliary_power_metrics ~= dtn_port_power_metrics
```

差别应当只来自线性求解误差。

## 9. 本次小网格验证

我用很粗的验证网格跑了 4 个小算例，参数为：

```text
mesh_target_size = 120.0
nedelec_degree = 1
incident_angle_deg = 15
port_boundary_model = dtn
constraint_backend = manual
```

结果如下：

| 方法 | 自动衍射级 | 选中级次 | R_port | T_port | R+T_port | R+T_probe |
|---|---:|---|---:|---:|---:|---:|
| explicit | False | top=[0], bottom=[0] | 0.020207960694 | 0.979792039306 | 1.000000000000 | 1.298951835478 |
| auxiliary | False | top=[0], bottom=[0] | 0.020207960694 | 0.979792039306 | 1.000000000000 | 1.298951835478 |
| explicit | True | top=[-1,0], bottom=[-1,0,1] | 0.025026127839 | 0.974973872161 | 1.000000000000 | 0.911096794081 |
| auxiliary | True | top=[-1,0], bottom=[-1,0,1] | 0.025026127839 | 0.974973872161 | 1.000000000000 | 0.911096794081 |

这个表说明：

1. explicit 和 auxiliary 对同一组选中衍射级给出相同端口功率。
2. auxiliary 直接用 `a_m` 算出的 R/T 与 trace 重新投影法一致。
3. 水平探测线法和端口面法可以不同。DtN 端口对比 COMSOL Periodic Port 时，优先看端口面法；水平探测线法保留作诊断。

## 10. 未来 3D 还可以怎么进一步省资源

辅助变量法是第一步。以后如果升级到大规模 3D，还可以继续考虑：

1. PETSc FieldSplit 块预条件  
   把有限元自由度 `u` 和端口模态自由度 `a` 当成两个 field，分别预处理。这样比把所有未知量混在一个大矩阵里更可控。

2. 矩阵自由低秩算子  
   对 DtN 项不显式装矩阵，只实现：

   ```text
   y = A u + Q^H Y Q u
   ```

   Krylov 迭代时需要矩阵乘法，就临时做投影和回投影。这对很多模态时更省内存。

3. 分布式端口投影  
   3D 端口面很大时，`ell_m` 不应该集中到单进程。更自然的做法是每个 MPI rank 只保存自己拥有的端口自由度片段，然后用 MPI allreduce 得到模态幅值。

4. 自适应模态截断  
   现在自动模式只加入明确传播级次。以后可以按需要额外加入少量近场倏逝级次，但用阈值控制，不再盲目使用 `-N...N`。

5. H-matrix 或快速多极近似  
   如果未来一定要保留显式边界非局部算子，可以考虑压缩边界矩阵。不过这比辅助变量和矩阵自由复杂得多，不建议作为第一步。

6. PML 作为局部替代模型  
   对某些 3D 问题，如果只关心场分布而不是端口 S 参数，PML 是局部体积分，矩阵天然稀疏。但它不能直接给出 COMSOL periodic port 那样的衍射级功率，因此更适合场吸收边界，不适合作为端口功率定义。

当前代码先保留 explicit，并把 auxiliary 设为默认推荐路线。这样短期内可以用 explicit 做公式对照，长期再把 auxiliary 迁移到真正的 PETSc/MPI 分布式实现。
