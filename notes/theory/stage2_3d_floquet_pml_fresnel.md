# Stage 2：3D 双周期 Floquet、z 向 PML 和 Fresnel 验证

## 2026-06-19 更新：MPI Floquet 整面拟合约束已通过 h500/h300 smoke

上一轮的主要风险是：MPI 下 `create_box` 生成的相对侧面三角剖分不完全一致，逐 facet 配对会在 h500/h300 时产生很大的 Floquet mismatch 或超时。现在 MPI 路径已改成整张周期侧面拟合一个 Nedelec slave-to-master 变换：

```text
master side dofs -> probe matrix
slave side dofs  -> probe matrix
slave = phase * transform * master
```

这条路径保留了串行 facet-wise 约束逻辑；只有 MPI 多进程时使用 side-wide transform。

最新实跑：

```text
floquet_airbox MPI 2 h500:
  floquet_x/y mismatch = 1.18e-15 / 1.34e-15
  elapsed = 3.412 s

floquet_airbox MPI 2 h300:
  floquet_x/y mismatch = 3.75e-15 / 4.72e-15
  elapsed = 3.084 s

pml_airbox MPI 2 h900:
  floquet_x/y mismatch = 6.20e-16 / 7.13e-16
  pml_decay_ratio_bottom = 0.0561

fresnel_interface serial p2/h300, Floquet+PML:
  R/T/R+T = 0.018669 / 0.935656 / 0.954324
  Fresnel analytic R/T = 0.033736 / 0.966264
```

因此当前判断是：2A 的 MPI Floquet smoke 已通过；2B 的 MPI PML 路径可继续用于小网格验证；2C Fresnel 仍需更细网格或更稳的 R/T 后处理才能作为定量验收。

同一轮又补跑了第一组小扫描：

```text
oblique Floquet MPI 2 h300:
  mismatch ≈ 4e-15，通过

PML p1/h900:
  theta=30/60、alpha=10、thickness=350 都能完成，Floquet mismatch 约 1e-15
  bottom decay ratio 随厚度增加有改善，但 pml_reflection_proxy 仍偏大

Fresnel sanity:
  n_sub=1, no PML/Floquet, p2/h200:
    R/T/R+T = 3.16e-4 / 1.0101 / 1.0105，通过隔离 sanity
  n_sub=1, Floquet+PML, p2/h300:
    R/T/R+T = 0.0657 / 1.0783 / 1.1440，未通过
```

这个对比很关键：Fresnel 体方程和基本 R/T 拟合不是完全错误，主要风险转移到 Floquet+PML 组合后的采样平面、PML 入口附近场拟合，以及 p 偏振功率分解。

## 2026-06-18 历史记录：Fresnel 收敛趋势和 MPI Floquet 风险

本轮继续定位后，2C 的结论需要更新：

```text
p1/h700 的 Fresnel smoke 不可信。
原因包括网格过粗，以及旧网格没有强制 interface/PML 入口成为单元面。
```

串行修正后，`mesh_builder_3d.py` 会让 z 方向包含：

```text
domain_z_min
physical_z_min
interface_z
physical_z_max
domain_z_max
```

Fresnel normal s 的收敛定位结果：

```text
p2/h300, no PML, no Floquet: R/T = 0.061439 / 1.229299
p2/h200, no PML, no Floquet: R/T = 0.062094 / 0.964772
p2/h150, no PML, no Floquet: R/T = 0.037266 / 0.940779
Fresnel analytic R/T:          0.033736 / 0.966264
```

加回 Floquet 和 PML 的粗网格结果：

```text
p2/h300, Floquet only:        R/T = 0.018938 / 0.955782
p2/h300, Floquet + PML:      R/T = 0.018669 / 0.935656
```

因此当前判断是：串行 Fresnel 路径有收敛趋势，PML 版可以作为粗 smoke，但还需要更细网格或更稳的后处理才能定量验收。

MPI 方面当前仍有风险：

```text
floquet_airbox MPI 2 h900: mismatch ≈ 1e-15
floquet_airbox MPI 2 h500: mismatch ≈ 0.57 / 0.68
floquet_airbox MPI 2 h300: 超时
pml_airbox MPI 2 h900: completed，但 mismatch ≈ 0.51
```

所以在修好 3D MPI Floquet 的多 facet pairing/probe transform 前，MPI 结果只能作为路径 smoke，不能作为物理验收。

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

代码没有使用 `dolfinx_mpc` 的高层 periodic helper，因为当前 H(curl) Nedelec 空间不能直接走这个接口。现在分两条实现路径：

串行路径仍然按 facet 配对：

1. 在 x_max/x_min 和 y_max/y_min 面上寻找对应 facet。
2. 对每对 facet 插值一组探针场。
3. 用探针场恢复 Nedelec 面自由度之间的线性变换。
4. 把 `slave_dofs`、`master_dofs`、`coefficients`、`owners`、`offsets` 交给 `dolfinx_mpc.MultiPointConstraint.add_constraint`。

MPI 路径改用整面拟合：

1. 收集 x_min/x_max 或 y_min/y_max 整张侧面的 Nedelec 自由度。
2. 用同一组探针函数构造 master side 和 slave side 的 dof 值矩阵。
3. 用伪逆拟合 `slave = phase * transform * master`。
4. 每个 rank 只提交自己拥有的 slave dof 约束，master dof 使用全局编号和 owner rank。

这样可以避免 MPI `create_box` 中相对侧面三角剖分不一致导致的 facet-by-facet 配对错误。

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
fresnel_interface normal, serial, p1, h700 nm, direct, s/p
fresnel_interface normal, serial, p2, h150 nm, direct, s
fresnel_interface normal, serial, p2, h300 nm, direct, s, Floquet+PML
floquet_airbox normal, MPI 2, p1, h900 nm, direct
floquet_airbox normal, MPI 2, p1, h500 nm, direct
floquet_airbox normal, MPI 2, p1, h300 nm, direct
pml_airbox normal, MPI 2, p1, h900 nm, direct
```

未完成或未通过：

```text
早期 fresnel_interface p1/h700 与 Fresnel 解析值严重不一致，不能验收
fresnel_interface p2/h150 串行已有收敛趋势，但仍需更细定量扫描
pml_airbox MPI 2 h900 已运行且 Floquet mismatch 通过，但 PML reflection proxy 仍需参数扫描解释
fresnel_interface p2/h300 Floquet+PML 目前只是粗网格 smoke，R/T 还不能作为最终定量验收
```

下一轮可以继续 Stage 2 参数扫描，但不建议直接上大网格。更稳的顺序是先做小网格角度/偏振/厚度扫描，再用串行 p2/h150 或更细网格确认 Fresnel+PML 的 R/T 趋势。

当前 MPI 版 3D Floquet 已能跑 h500/h300 smoke test。后续如果要把它作为大规模生产路径，还需要继续优化 side-wide transform 的探针插值、dense transform 内存，以及更高阶单元下的约束稀疏性。
