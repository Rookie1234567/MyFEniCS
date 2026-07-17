# 高阶 H(curl) Floquet 与 Hybrid h/p 可行性

> 观测状态（2026-07-17）：Case090 证明 p3/p4 直接 3D Floquet 核心正确；QEP
> p3/p4 分片通过但全局跟踪 aggregate 未资格化；Hybrid/full3D 仍只在 p2/h5、p2/h3
> 有同阶同网格对照。本文中的 adaptive/graded/buffer 部分保留为延期理论与实现入口。

## 0. 文档身份

本文是 Task033 的理论与实现边界说明，覆盖：

- 六面体第一类 Nédélec `N1curl(p)` 的高阶边、面自由度；
- 双 Floquet 周期面的 orientation 与复相位约束；
- 相位无关拓扑缓存和分布式稀疏约束；
- 高阶截面 QEP、匹配 trace 与 Hybrid direct anchor；
- 固定阶次 p、conforming graded h、接口 buffer 和资源 Gate；
- 当前 DOLFINx/Basix 环境下 variable-p 的能力边界。

本文不把 Task033 描述成最终 hp 自适应 production solver。Task033 的目标是得到可复核的资格证据和等精度资源比较，为 Task034 的 scalable modal core 选择输入离散；最终 0.7 nm 路线仍需后续可扩展 QEP、迭代法和 continuation。

对应代码入口：

```text
src/constraints/high_order_floquet_trace.py
src/constraints/floquet_3d_high_order.py
src/constraints/floquet_3d.py
src/common/high_order_quadrature.py
src/constraints/cross_section_floquet.py
src/modes/quadratic_beta_eigenproblem.py
src/geometry/task033_periodic_graded_mesh.py
benchmarks/task033_resource_gates.py
benchmarks/task033_variable_p_capability.py
```

`papers/` 中的二维/三维 self-adaptive hp FEM、adaptive edge FEM DtN、hybrid FEM–mode-matching 和 FEM–RCWA 论文是研究背景；本仓库的可运行资格仍只由 Case090/091、clean-source record、MPI 回归和统一 checker 决定。

---

## 1. 高阶 H(curl) 离散

频域 Maxwell 弱式采用项目统一的 `exp(-i omega t)` 约定：

$$
\int_\Omega \mu_r^{-1}
(\nabla\times \mathbf E)\cdot
\overline{(\nabla\times \mathbf v)}\,d\Omega
-
k_0^2\int_\Omega \varepsilon_r
\mathbf E\cdot\overline{\mathbf v}\,d\Omega
=
\ell(\mathbf v).
$$

第一类 Nédélec 六面体空间的局部维数随 p 增长为：

$$
N_{\mathrm{loc}}(p)=3p(p+1)^2.
$$

自由度不只是顶点值。p=1 只有最低阶边矩；p>=2 还包括高阶边矩和面切向矩，p>=3 继续增加面与体内矩。因此，把周期面上的自由度按坐标逐点匹配，或对整张边界做 dense 拟合，不足以保证一般 orientation 下的 H(curl) 一致性。

对物理切向场的 Piola 映射必须与 Basix 的实体变换一致。若局部实体编号或方向改变，系数向量通过实体变换矩阵 T 变换；同一物理 trace 的两侧系数不能仅靠一个正负号关联。

---

## 2. 双 Floquet 条件和 orientation

横向周期长度为 $L_x,L_y$，Bloch 波数为 $k_x,k_y$。连续场满足：

$$
\mathbf E(x+L_x,y,z)=e^{i k_x L_x}\mathbf E(x,y,z),
$$

$$
\mathbf E(x,y+L_y,z)=e^{i k_y L_y}\mathbf E(x,y,z).
$$

角点同时跨越两个周期方向：

$$
\mathbf E(x+L_x,y+L_y,z)
=e^{i(k_xL_x+k_yL_y)}\mathbf E(x,y,z).
$$

离散约束写成：

$$
u_s=\phi\,T_{s\leftarrow m}u_m,
$$

其中 $u_s,u_m$ 是 slave/master 实体系数，$\phi$ 是 x、y 或 xy Floquet 相位，$T_{s\leftarrow m}$ 由边/面 orientation 变换构成。必须先确定实体角色和唯一 master，再生成 corner/edge/face 约束；若分别独立处理 x、y 两张周期面，会在交线与角点产生重复 slave 或相位不一致。

Case090 的 action 等价性不是比较同一段代码的两个包装，而是比较：

$$
A_r q
\quad\text{与}\quad
C^H A_f Cq,
$$

其中 $A_f$ 是实际装配的 coercive curl-curl-plus-mass 稀疏算子，$C$ 是独立构造的稀疏约束延拓。slave 输入置零、free/master 输入非零，避免零向量产生无意义通过。

---

## 3. 相位无关拓扑缓存

约束分成两层：

1. 相位无关层：周期实体配对、ownership、局部/全局 DoF、orientation block；
2. 相位相关层：把当前 $e^{ik_xL_x}$、$e^{ik_yL_y}$ 乘入已有稀疏 block。

拓扑缓存 key 包含 mesh/function-space 身份、degree、周期几何和分区相关身份。缓存命中时只更新相位与 MPC 系数，不重新遍历整张周期边界。

正式 p1--p4 路径要求：

```text
distributed entity exchange
exact Basix edge/face transforms
sparse MPC coefficients
no full-boundary allgather
no dense boundary-square matrix
no probe/pseudo-inverse fallback
```

通信量应随本 rank 需要配对的边界实体近线性增长；不能随全局 boundary DoF 的平方增长。旧的 p1/p2 gather 实现只保留为私有诊断代码，不能作为 `auto` 或正式 record 的后端。

---

## 4. 积分阶次与几何阶次

高阶单元不能继续沿用为 p=1/2 调出的固定 quadrature。Task033 采用统一保守策略：

$$
q=2p+2g+c+2,
$$

其中 p 是场阶次，g 是几何映射阶次，c 是额外材料/系数复杂度修正。冻结的一阶几何、默认系数下，p=1,2,3,4 对应的主积分阶次是 6,8,10,12。

正式 QEP/Hybrid 记录需保存 resolved quadrature degree，并用更高积分阶次做敏感性对照。若升阶积分改变 beta 或物理量超过容差，当前结果只能标为 quadrature-sensitive，不能升级为高阶收敛。

---

## 5. 高阶截面 QEP

z 不变中间区域的截面离散保持二次特征值形式：

$$
Q(\beta)e
=
(K_0+\beta K_1+\beta^2K_2)e
=0.
$$

每个系数矩阵都先用精确双 Floquet 延拓 C 稀疏约化：

$$
K_{j,r}=C^H K_j C,
\qquad j=0,1,2.
$$

资格化不能只检查“返回有限 beta”。至少要同时检查：

- 与均匀介质解析传播常数的 beta 误差；
- QEP residual；
- left/right 双正交和被动分支；
- 相邻 p、h 与参数点的 mode/subspace tracking；
- full/reduced DoF、NNZ、保留向量 bytes 与时间；
- raised-quadrature 稳定性。

p3/p4 是否有收益必须相对 p2 比较；若 p4 在更高成本下没有降低 beta 或物理误差，应保留为工程负结果，而不是因其“能运行”就判定成功。

---

## 6. 匹配接口与 Hybrid anchor

局部 3D FEM 和中间截面使用同一 x/y 匹配网格。高阶 trace 投影要保持：

- 同一 Nédélec degree；
- 同一周期相位与 orientation 约定；
- bottom/top 显式法向符号；
- electric trace 与 magnetic traction 的左右作用一致；
- MPI ownership 不依赖最后一个 rank 聚集。

Task033 的高阶 Hybrid anchor 只用于 current-scale 代数与物理对照：小规模 augmented direct 与 `modal-schur-memory-minimal` 应在相同 p、h、M、source SHA 下比较。单个 M=80 只是漏斗点，正式物理资格至少需要 M80/M120/M160；若 M120 到 M160 未收敛，才条件增加 M240。

截断误差与 FE 离散误差必须分开：先在固定 p/h 上用 M 漏斗确认 modal truncation，再在各自通过截断 Gate 的 M 上比较 p/h。

---

## 7. 固定 p 与 conforming graded h

Task033 的第一版局部 h 路线采用周期同步的 conforming graded hexahedral mesh，不引入 hanging-node H(curl) 自定义约束。流程是：

```text
physics-informed marks
-> periodic mark synchronization
-> Dörfler selection / axis rebuild
-> neighbor-ratio and fitted-plane checks
-> solve and same-accuracy qualification
```

第一层 indicator 优先覆盖材料界面、局部端部、Hybrid 接口和强场梯度。代码同时提供 residual/jump 数组入口，但没有把未验证的复杂 DWR 包装成已经完成的 production indicator。

对候选 c 和 reference r，只有下列物理 Gate 通过后才计算等精度压缩：

$$
\max(|\Delta R|,|\Delta T|,|\Delta A|)\le 10^{-5},
$$

$$
\delta_{\mathrm{orders}}\le 10^{-3},
$$

$$
\delta_E\le5\times10^{-3},
\qquad
\delta_H\le10^{-2}.
$$

随后分别报告：

$$
\rho_{\mathrm{DoF}}
=
\frac{N_{\mathrm{local,ref}}}{N_{\mathrm{local,c}}},
$$

$$
\rho_{\mathrm{rows}},\quad
\rho_{\mathrm{NNZ}},\quad
\rho_{\mathrm{RSS}},\quad
\rho_{\mathrm{time}}.
$$

压缩身份按 Review V2 固定为：小于 1.3 倍是 weak，1.3--2 倍是 positive，2--3 倍是 clear，至少 3 倍是 engineering，至少 5 倍是 strong。3 倍不是 p2 h-adaptive 的最低通过线。

---

## 8. 接口 buffer 联合预算

Task033 比较 10、7.5、5、2.5 nm 对称 buffer，对应接口：

```text
10.0 / 110.0 nm
7.5 / 112.5 nm
5.0 / 115.0 nm
2.5 / 117.5 nm
```

接口向端部靠近会减少 local 3D FEM 体积，但可能需要更多截面模态。目标函数不是单独最小化 local DoF，而是：

$$
\mathrm{Cost}_{\mathrm{total}}
=
\mathrm{Cost}_{\mathrm{local\ FEM}}
+
\mathrm{Cost}_{\mathrm{QEP/modes}}
+
\mathrm{Cost}_{\mathrm{interface/Schur}}.
$$

因此每个 buffer 都必须在自己的 M 漏斗通过后，记录 local cells/DoF、trace DoF、rows、NNZ、QEP storage、RSS、时间与物理误差。只因 2.5 nm local DoF 最小，不能自动选它作为 Task034 输入。

---

## 9. variable-p 能力审计

“Basix 能创建多个 degree 的 element”不等于“DOLFINx 能在相邻 cell 上直接维护 cellwise variable-order H(curl) 空间”。正式能力至少要同时覆盖：

- 单一 function space 内的 cellwise variable degree；
- p 不同邻接单元间的切向连续性；
- paired periodic faces 的同步 p；
- high-order interface trace；
- MPI partition 后 ownership；
- submesh/multimesh 耦合维护成本。

当前审计若不能找到稀疏、原生、可测试的公开路径，就必须输出 fail-closed：

```text
native_variable_p_qualified = false
bespoke_arbitrary_variable_p_implemented = false
```

Task033 此时仍可完成固定 p2 graded-h、全局 p3/p4 等精度比较和 hp zoning 设计报告；不得临时自造任意 variable-p mortar/constraint 系统来制造完成感。

---

## 10. 14 GiB 资源治理

运行前需要两种独立中心预测和一个保守上界。只有：

```text
both center predictions <= scaled 11.5 GiB gate
conservative upper <= scaled 12.8 GiB gate
container limit readable
host available memory readable
swap current = 0
clean source
external watchdog enabled
```

才允许启动正式大算例。环境上限小于 14 GiB 时，阈值按比例缩小并保留安全余量。

运行时内存权威是：

$$
M_{\mathrm{authority}}(t)
=
\max\left(
\sum_{r\in\mathrm{live\ workers}}\mathrm{RSS}_r(t),
\mathrm{cgroup\ current}(t)
\right).
$$

warning 和 controlled termination 必须实时使用这个最大值，而不只是事后摘要。swap、worker RSS、cgroup current、container limit 或 host available memory 任一不可读，正式资源资格都 fail closed。

未运行组合必须显式写成 `not_run_by_memory_gate`，不能留空，也不能依赖 swap 或 OOM 来探测边界。

---

## 11. 资格层级与证据身份

证据从弱到强分为：

1. unit/contract：实体变换、角点 ownership、schema、watchdog 负例；
2. microfixture：Fixture A/B 的 p1--p4、h 与 MPI 一致性；
3. component：QEP、trace、Hybrid augmented/Schur anchor；
4. physical funnel：同 p/h 下 M80/M120/M160，必要时 M240；
5. equal-accuracy：通过物理 Gate 后的 p/h/graded/buffer 资源比较；
6. task classification：统一 Case090/091 checker 在同一 clean SHA 上给出结论。

所有正式 large record 必须来自 tracked-source-clean commit。ignored artifacts 可保存 raw log、VTU、mesh、eigenvector、matrix、factor 和 memory timeline；tracked records 只保留紧凑摘要、SHA256、单位、baseline 和 evidence path。

---

## 12. Task033 能证明与不能证明的内容

若全部 Gate 通过，Task033 可以证明：

- p3/p4 双 Floquet 高阶 trace 在微型 3D 问题上的 orientation 与 MPI 正确性；
- 高阶约束保持 sparse、distributed、phase-cacheable；
- 在当前 13.5 nm、当前结构与安全 p/h 范围内，QEP/Hybrid 的精度和资源趋势；
- p2 conforming graded-h 与四种接口 buffer 的可行性/负结果；
- 当前 native variable-p 是否足以进入最小 hp 原型；
- measured compression 对 1 TiB 路线分类的影响。

Task033 不能单独证明：

- 任意几何、任意材料和 1--10 度 S/P 的 production 鲁棒性；
- h2 完整场等精度，除非存在同口径 h2 field record；
- 0.7 nm 已可运行；
- 当前 direct QEP/Hybrid 路径已经可扩展到最终生产尺度；
- 未通过 M 漏斗的单点结果具有物理资格。
