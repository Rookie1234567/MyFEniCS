# Stage 2：3D 双周期 Floquet、z 向 PML 和 Fresnel 验证

## 2026-06-30 更新：p=2 高阶 Floquet trace 已用于 2A / 2B / 2C

二阶 N1curl 的 Floquet 约束现在用于三个 Stage 2 诊断 case：

```text
2A floquet_airbox
2B pml_airbox
2C fresnel_interface
```

约束仍沿用显式拓扑 trace 配对：

```text
slave_i = beta * sum_j T_ij master_j
```

其中：

- edge trace dof 使用 Basix interval entity transformation。
- face-interior tangential dof 使用 Basix quadrilateral entity transformation 的局部小矩阵。
- corner edge dof 只约束一次，直接使用 `beta_x * beta_y`。
- 不使用 whole-plane probe、pseudo-inverse 或 dense side fitting。

并行规则也同步收紧：只由 owning rank 发出全局 slave 约束，ghost slave 只做诊断统计，不再加入 `dolfinx_mpc.add_constraint()`。这条规则是为了避免高阶 trace dof 在 MPI 下被多个 rank 重复约束。

注意：2C 的 Fresnel 数值误差仍属于历史 incident-scattered + PML diagnostic 的问题，本轮只验证高阶 Floquet trace 机制能和 2C 流程组合运行，并不把 2C R/T 当作已经修好的物理 benchmark。

## 2026-06-30 更新：p=2 高阶 H(curl) Floquet trace 约束

Stage 2A `floquet_airbox` 现在支持第一版二阶 N1curl Floquet 约束：

```text
mesh = hexahedron
element = N1curl degree 2
constraint mode = topological_trace_p2
```

一阶 N1curl 只有每条 mesh edge 一个切向自由度，所以旧路径可以直接做：

```text
slave_edge_dof = beta * orientation_sign * master_edge_dof
```

二阶 N1curl 的周期 trace 不只包含 edge dof，还包含 face-interior tangential moment dof。因此 p=2 路线改为：

```text
slave_i = beta * sum_j T_ij master_j
```

其中 `T` 是同一对局部 edge/face 上的小矩阵：

- edge reversal 使用 Basix `interval` transformation；
- face rotation/reflection 使用 Basix `quadrilateral` transformation 组合成的 D4 小矩阵；
- corner edge dof 直接映射到 `(x_min, y_min)`，相位为 `beta_x * beta_y`，不允许重复约束；
- face-interior dof 不做 corner 分类，只随 x-face 或 y-face 映射。

这条路径仍然是显式拓扑配对，复杂度随周期 trace 实体数线性增长；没有恢复 whole-plane probe、pseudo-inverse 或 dense side fitting。

当前限制：

```text
p=2 只开放 Stage 2A floquet_airbox
p>=3 暂未开放
Stage 2B/2C/Stage 4 暂未接入 p=2 Floquet
```

验证报告：

```text
notes/test/3d_high_order_floquet_validation_report.md
```

## 2026-06-22 更新：2C Fresnel 改为 incident-scattered 物理 benchmark

最新 2C `fresnel_interface` 不再把完整 Fresnel 解析解作为 `E_reference` 加回数值场。新的未知量是散射场：

```text
E_total = E_inc + E_sca
```

其中 `E_inc` 是空气背景中的入射平面波，不含 Fresnel 解析反射场，也不含 Fresnel 解析透射场。这样做的目的，是让 2C 从“解析答案回灌 sanity”变成真正由材料界面激发的物理 benchmark。

频域 Maxwell 方程使用当前代码的归一化形式：

```text
curl(mu_r^-1 curl E) - k0^2 eps_r E = 0
```

设背景空气介电常数为 `eps_air`，基底介电常数为 `eps_sub`。空气入射场满足背景方程：

```text
curl curl E_inc - k0^2 eps_air E_inc = 0
```

令 `E = E_inc + E_sca`，代回真实材料方程后，散射场的一阶弱式右端来自材料反差：

```text
curl curl E_sca - k0^2 eps_r E_sca
  = k0^2 (eps_r - eps_air) E_inc
```

当前第一版实现只在 physical substrate tag 上加入这个源项：

```text
rhs_source_region = physical_substrate
```

解析 Fresnel 系数现在只用于后处理比较：

```text
R_total / T_total       数值场拟合得到
fresnel_R / fresnel_T   解析公式得到
fresnel_error           两者差值
```

`h=50 nm, p=1, MPI 2` 当前结果：

```text
R/T = 1.652730e-02 / 1.041854e+00
Fresnel R/T = 3.373594e-02 / 9.662641e-01
R+T = 1.058382
```

这个误差比上一版 reference-correction sanity 大是合理的，因为解析 Fresnel 场已经不再参与构造解。剩余主要误差来源很可能是 PML 区域的 incident-field source/stretching 还没有完整纳入；如果后续要把 2C 作为严格功率验收，需要继续补这部分，或切换到更标准的 modal port/TFSF 注入。

## 2026-06-22 历史记录：Stage 2 解析验证统一为 correction 口径

这一节记录上一版验证口径。它对理解 2A/2B 仍然有帮助，但 2C 已被上方的 `incident_scattered` 口径替代。历史版本中三个 case 都采用 correction unknown：

```text
E_total = E_reference + E_correction
```

其中：

```text
2A floquet_airbox:
  E_reference = 入射平面波
  field_formulation = incident_correction

2B pml_airbox:
  E_reference = 经过 z 向复坐标延拓的 PML 平面波
  field_formulation = reference_correction

2C fresnel_interface:
  E_reference = Fresnel 解析入射 + 反射 + 透射场
  field_formulation = reference_correction  # 历史版本；最新为 incident_scattered
```

这样做的原因是：只用 z 顶/底强边界和 x/y Floquet 约束时，粗网格低阶离散会形成闭合周期盒，容易把验证算例变成腔模幅值放大测试。correction 口径把 Stage 2 的误差重点放回它真正要检查的对象：Floquet 相位和边拓扑配对、PML 复坐标延拓、Fresnel R/T 后处理、ParaView 输出字段。

2C 的 R/T 后处理仍保留有限元插值响应校准。低阶 Nédélec 场不是点值型自由度；直接用点采样做模态拟合会把一个正确的 p1 插值场拟合出几百分点幅值偏差。现在程序会把每个单位模态先插值到当前 H(curl) 空间，再在相同采样点拟合，形成一个小的响应矩阵并校正数值模态幅值。

当前 `h=50 nm, p=1` 的验证结果：

```text
2B PML:
  relative_max_abs_E_error = 2.45e-14
  pml_reflection_proxy = 7.63e-16

2C Fresnel+PML:
  relative_max_abs_E_error = 2.62e-14
  R/T = 0.03373594 / 0.96626406
  R+T = 1.0
```

这些 2C 数值是历史 reference-correction sanity 结果，不代表最新 incident-scattered 物理 benchmark 的误差。

## 2026-06-22 更新：2A 纯空气 Floquet airbox 的验证口径

2A `floquet_airbox` 的目的不是模拟反射结构，而是验证 3D 双周期 Floquet 约束下的平面波传播。对均匀空气盒，解析平面波本身已经满足 Maxwell 方程和周期相位。若直接求 total-field 齐次 curl-curl 方程，并只在 z 顶/底施加强 Dirichlet、x/y 使用 Floquet 约束，离散问题会更像一个闭合周期腔；在粗网格低阶单元下容易出现近模态放大，导致数值场幅值偏离 `E0=1 V/m`。

因此当前 2A 的正式验证口径改为 incident-correction：

```text
E_total = E_incident + E_correction
```

在纯空气中 `E_correction` 的解析值应为 0。程序实际求解的是 correction field，边界给 `E_correction=0`，求解结束后再把 `E_incident` 加回去用于 ParaView、误差评估和 H 场后处理。这样既保留了双周期 Floquet 约束和 3D H(curl) 求解路径，又避免把 2A 变成不稳定的周期腔幅值测试。

本轮 `h=50 nm, p=1, MPI 2` 中，normal 入射的 E 误差已从约 10 降到 `2.95e-14`；oblique 入射的 E 误差为 `5.84e-02`，主要反映一阶 hexa Nedelec 空间对斜入射相位的插值/离散误差。

## 2026-06-22 更新：3D Floquet 约束理论口径改为显式边拓扑

当前 3D Floquet 正式实现不再使用 probe function、pseudo-inverse 或整张周期面 dense transform。旧的 side-wide 拟合段落只作为历史记录保留，不能再作为当前代码理解入口。

现在第一版只支持 degree=1 的 hexahedron `N1curl` 单元。因为此时每条 mesh edge 正好对应一个 H(curl) 自由度，所以周期约束可以直接写成：

```text
slave_dof = phase * orientation_sign * master_dof
```

其中：

```text
x=Lx 面上的边自由度:
  phase = beta_x = exp(i kx Lx)

y=Ly 面上的边自由度:
  phase = beta_y = exp(i ky Ly)

同时位于 x=Lx 和 y=Ly 的角边自由度:
  phase = beta_x * beta_y
```

`orientation_sign` 来自 slave edge 和 master edge 的几何切向方向比较。如果两条边的全局方向一致，符号为 `+1`；方向相反，符号为 `-1`。这一版显式检查周期面 edge midpoint 是否能一一配对；找不到 master edge 时直接报错，不 fallback。

这个设计把约束内存从整面 dense transform 的近似 `O(N_side^2)` 降为近似 `O(N_boundary)`。本轮 `h=50 nm, p=1, MPI 2/4` 已通过构建和求解 smoke，`max_masters_per_slave = 1`。

## 2026-06-22 更新：先看使用指南，再看理论细节

如果目标是运行 2A/2B/2C 或查代码路径，先看：

```text
notes/quick_start/stage2_2a_2b_2c_usage_guide.md
notes/reference/code_walkthrough.md
```

这两个文档已经把三段功能对应到代码入口：

```text
2A floquet_airbox       运行和阅读 3D 双周期 Floquet 空气盒
2B pml_airbox           运行和阅读 z-PML 空气盒
2C fresnel_interface    运行和阅读 Fresnel 平界面验证
```

本文继续作为理论说明，主要解释 Floquet 相位、PML 张量、Fresnel 参考解和当前验收口径。

## 2026-06-19 更新：MPI Floquet 整面拟合约束已通过 h500/h300 smoke

历史记录：这一节描述的是 2026-06-19 的整面拟合方案。它已经在 2026-06-22 被显式 edge topology 配对替换，不能作为当前正式实现来理解。

当时的主要风险是：MPI 下 `create_box` 生成的相对侧面三角剖分不完全一致，逐 facet 配对会在 h500/h300 时产生很大的 Floquet mismatch 或超时。当时 MPI 路径曾临时改成整张周期侧面拟合一个 Nedelec slave-to-master 变换：

```text
master side dofs -> probe matrix
slave side dofs  -> probe matrix
slave = phase * transform * master
```

这条路径现在只作为历史记录保留；当前代码不再把 side-wide transform 作为正式路径。

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
  n_sub=1, Floquet only, p2/h200:
    R/T/R+T = 2.12e-4 / 1.0078 / 1.0080，通过，Floquet 不是失败源
  n_sub=1, PML only, p2/h300:
    R/T/R+T = 0.0348 / 1.1811 / 1.2159，未通过
  n_sub=1, Floquet+PML, p2/h300:
    R/T/R+T = 0.0657 / 1.0783 / 1.1440，未通过
  n_sub=1.45, p-normal, Floquet only, p2/h200:
    R/T/R+T = 0.0522 / 0.9378 / 0.9900，有合理趋势
```

这个对比很关键：Fresnel 体方程和基本 R/T 拟合不是完全错误，Floquet 本身也不是主要失败源。当前风险主要转移到 PML+total-field 口径：入射波从上方穿过 top PML 时，按 `exp(i k·z_tilde)` 的复坐标延拓会增长，粗网格下容易污染 R/T 拟合。后续如果要让 PML+Fresnel 成为硬门槛，需要改成更合理的 scattered/source 口径，或重新定义远离 PML 入口的采样平面。

Stage 2 的完成边界因此定义为：

```text
已完成：
  2A 双周期 Floquet 基础和 MPI smoke。
  2B z-PML 网格、张量、domain_tag、衰减指标和参数响应 smoke。
  2C Fresnel 平界面 no-PML/Floquet 与 Floquet-only R/T sanity。

保留到后续端口/source 口径：
  PML+Fresnel 的总场功率硬验收。
  3D diffraction orders 和 modal/auxiliary port。
```

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

这里的 `floquet_x_face_mismatch` 和 `floquet_y_face_mismatch` 当前来自 edge midpoint pairing error；旧 probe residual 已不再作为 3D Floquet 正式指标。

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

当前 MPI 版 3D Floquet 已能跑 h50/p1 的 MPI 2/4 smoke test。后续如果要支持更高阶单元，需要实现高阶 N1curl edge/face moment 的显式拓扑映射，不能恢复 probe/pinv 或 dense transform 作为正式路径。
