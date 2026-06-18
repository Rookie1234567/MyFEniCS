# Stage 2：3D 双周期 Floquet、z 向 PML 和 Fresnel 验证

## 2026-06-18 更新：数值指标和十层测试口径

本轮把 Stage 2 验证拆成十层测试，测试代码放在：

```text
src/test/
```

测试说明和实跑结果放在：

```text
notes/test/
```

同时修正 2B/2C 指标口径：

```text
pml_reflection_proxy
```

现在表示物理区数值场拟合出的向上波/向下波幅值比，不再只是点值误差。

```text
R_total / T_total
```

现在由 `fresnel_interface` 求解后的数值场拟合得到，再与 Fresnel 解析值比较；不能把解析值直接写入数值结果。

当前验收顺序是：

```text
Level 0-3 公式和工具函数
Level 4-6 空气盒与 Floquet PDE
Level 7 PML 空气盒
Level 8-10 Fresnel、PML 和最终 sanity
```

其中 `n_sub=1` 的 Fresnel sanity 是硬门槛：平界面消失时应有 `R≈0`、`T≈1`。

## 2026-06-18 更新：Stage 2 第一版实现口径

本阶段先把 3D 周期边界和上下开放边界的基础设施搭起来，不提前实现 3D modal port、衍射级功率分解或真实 3D 光栅。

当前 3D 入口仍然是：

```text
src/main.py
```

最重要的新变量是：

```python
STAGE_CASE_3D = "floquet_airbox"
```

可选值如下：

```text
stage1_airbox        保留原来的六面 Dirichlet 3D 空气盒回归
floquet_airbox       2A：x/y 双周期 Floquet，z 顶/底解析边界
pml_airbox           2B：x/y 双周期 Floquet，上下 z-PML
fresnel_interface    2C：空气/基底平界面 Fresnel manufactured reference
stage2_all           依次运行 2A、2B、2C
```

求解器默认重新设为：

```python
SOLVER_PROFILE_3D = "direct"
```

迭代求解器仍然保留在代码里，但 Stage 2 验收不以迭代结果为准。

## 2A：3D 双周期 Floquet

3D Floquet 条件是：

```text
E(x + Lx, y, z) = E(x, y, z) exp(i kx Lx)
E(x, y + Ly, z) = E(x, y, z) exp(i ky Ly)
```

角线处的复合相位是：

```text
exp(i kx Lx) * exp(i ky Ly)
```

代码没有使用 `dolfinx_mpc` 的高层 periodic helper，因为当前 H(curl) Nedelec 空间不能直接走这个接口。现在的实现是：

1. 在 x_max/x_min 和 y_max/y_min 面上寻找对应 facet。
2. 对每对 facet 插值一组探针场。
3. 用探针场恢复 Nedelec 面自由度之间的线性变换。
4. 把 `slave_dofs`、`master_dofs`、`coefficients`、`owners`、`offsets` 交给 `dolfinx_mpc.MultiPointConstraint.add_constraint`。

summary 中重点看：

```text
floquet_x_face_mismatch
floquet_y_face_mismatch
floquet_edge_corner_mismatch
max_face_pairing_coordinate_error
nedelec_orientation_factor_stats
floquet_num_local_slaves
```

这里的 `floquet_x_face_mismatch` 和 `floquet_y_face_mismatch` 是约束构造的 probe residual，不是粗网格内部采样误差。

## 2B：z 向 PML

PML 只沿 z 方向加在上下：

```text
top PML
physical air / future structure region
bottom PML
```

当前第一版采用解析场 manufactured reference。也就是说，z 外边界仍然给解析切向场，用来先验证：

```text
PML cell tag 是否正确
PML 张量是否能装配
PML 区域是否进入 ParaView domain_tag
物理区内数值场是否和解析参考一致
```

summary 中重点看：

```text
pml_parameters
pml_reflection_proxy
pml_decay_ratio_top
pml_decay_ratio_bottom
```

注意：`pml_airbox` 的入射波默认从上往下传播。对这个 manufactured incident wave 来说，top PML 不是“出射吸收层”，所以 `pml_decay_ratio_top` 可能大于 1；这不等价于 PML 一定错误。更关键的是物理区域误差和后续 Fresnel/散射场验证。

## 2C：Fresnel 平界面

`fresnel_interface` 构造空气/基底平界面，不放光栅。参考解使用 Fresnel 解析系数：

```text
R_total ≈ R_Fresnel
T_total ≈ T_Fresnel
R + T ≈ 1    lossless 情况
```

当前第一版仍是 manufactured reference：用解析 Fresnel 场作为边界和后处理参考。它的目的不是替代 Stage 4 的 modal port，而是先检查：

```text
入射角定义
s/p 偏振定义
PML cell tag
Poynting 方向
R/T 归一化字段
ParaView 单位输出
```

输出文件包括：

```text
run_summary.json
solver_log.txt
fields_3d_for_paraview.vtu
power_metrics_3d.json
```

## 已验证和已知限制

已实跑通过：

```text
stage1_airbox, serial, p1, h300 nm, direct
floquet_airbox normal, serial, p1, h300 nm, direct
floquet_airbox oblique, serial, p1, h300 nm, direct
floquet_airbox normal, MPI 2, p1, h900 nm, direct
pml_airbox normal, serial, p1, h350 nm, direct
```

尚未完成实跑：

```text
fresnel_interface smoke test
floquet_airbox MPI 2, h300 nm
pml_airbox MPI 2
```

原因是本轮 Docker 执行额度在 Fresnel 验证前被系统拒绝。代码路径已经写入，但这些 case 需要下一轮继续跑。

当前 MPI 版 3D Floquet 已能跑极小网格 smoke test；更细网格会明显变慢。后续如果要把它作为大规模生产路径，需要继续优化低层约束构造中的探针插值和 facet 数据交换。
