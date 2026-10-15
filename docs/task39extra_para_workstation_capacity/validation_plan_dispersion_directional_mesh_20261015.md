# 0.7 nm RCWA–FE 差异：数值色散与方向网格的延后验证方案

日期：2026-10-15。作者：ChatGPT。本文只新增验证思路，不修改既有结果、活跃源码、输入或监督器。

## 0. 生效边界、身份与所消除的 blocker

**当前先完成用户告知的 5 nm 计算。本文不触发任何计算，不要求中途 pull、停止、重启、换网格或改变该场的资源合同。待该场求解、恢复、输出、检查及进程树清场全部结束，且用户明确交接执行本文后，才进入下述验证。** GitHub 文档不是工作站进程状态证明；执行者必须现场核实，不能只凭“solver done”启动下一场。

| 项目 | 冻结记录 |
|---|---|
| repository / branch | `Rookie1234567/MyFEniCS` / `task39extra_para_workstation_capacity` |
| task directory | `docs/task39extra_para_workstation_capacity` |
| 本次读取的 branch HEAD / 文档 base | `37a76ecc7bfc2ea45e4cd55bebc38f1e98115516` |
| 该提交 | `Document 0.7 nm RCWA versus FE diffraction comparison`；2026-10-15 01:43:21 UTC |
| 最新编号 review / response | `review_report_v7.md` / `response_v7.md`；后者和 summary 首屏仍为启动前迭代合同，不代替已完成直接解的原始终态 |
| 被验证 FE 的 source | `9a3c4a3fd9a41702fff4069280cb9507cefb163d` |
| 被验证 FE 的 run | `v7_interleave_0p7nm_aniso_p6_direct_q160_n0_full`，`20261014T062635.999684Z` |
| FE 身份 | p6 三维 Nédélec、单元静态凝聚、MUMPS direct、MPI1、572 个 N0 端口；不是 p4/BAL_H 迭代结果 |
| 本文件状态 | `DEFERRED_PLAN_AWAITING_USER_ACTIVATION_AFTER_5NM`；所有实际 FE 验证均 `NOT_RUN` |
| 当下写入范围 | 仅本文件；不写 `src/`、input、outcomes 结果，不生成 review_v8，不修改 master，不合并 |

本验证消除的 blocker 是：已得到 0.7 nm 离散解，但尚不知道主要 RCWA–FE 差异来自体离散传播、实际端口、还是其他机制，因而不能选择 accuracy-qualified 且资源可行的各向异性网格。它服务于最终“0.7 nm + 任意非可分三维 + 约 2 TB + 48 h”的路线；本规则光栅的成功不等于任意三维通过。

本文是 V7 已有回应之后新增的、延后激活的独立验证范围，不回写历史 V7。旧 V7 的“本批只算一场、不新增小模型”不被本文立即覆盖；只有用户激活本文时，才限于以下诊断范围扩展。旧直接解与 V7 迭代方案的身份差异必须保留。

## 1. 已有事实、首要假设与明确未证明的结论

[完整对比报告](outcomes/rcwa_fe_comparison_0p7nm_20261015/README.md)、[provenance](outcomes/rcwa_fe_comparison_0p7nm_20261015/provenance.json)、[实际输入](outcomes/rcwa_fe_comparison_0p7nm_20261015/fe_input_original.dat)是本次比较入口。

| 量 | FE | RCWA reported | FE − RCWA |
|---|---:|---:|---:|
| R | 0.08592253473181985 | 0.0702787390763 | +0.01564379565551985 |
| T at z=-10 nm | 0.6522079390017288 | 0.668830211715 | -0.016622272713271213 |
| A_volume | 0.26186952633636734 | 0.260891048523 | +0.000978477813367351 |

差异几乎全由零级贡献，但 -1 等弱衍射级仍有显著相对差异。FE 原 A6_n0 残差约 7.43e-8、独立能量闭合约 6.99e-11；这些不是 h/p 收敛。RCWA 有 reported Fourier/深基底/材料与吸收积分扫描，但其原始工程与校准 JSON 不在当前证据包内，未独立复现。

**首要待检验假设 Hx：当前 p6、hx=0.5 nm 的横向数值色散，经近临界掠入射放大，主导总 R/T 偏差。** 不能写成“全部误差已定位”，不能承诺 hx 减半即可使复场与全部衍射级合格。

数值色散指有限元离散后的波传播关系偏离连续关系。对于本场 y 不变、phi=0、S 偏振，可在相应 TE 子空间分析：

```math
k_0=2\pi/0.7,\quad k_x=k_0\cos(1^\circ),\qquad
k_{z,\mathrm{Si}}^2/k_0^2=\varepsilon_{\mathrm{Si}}-\cos^2(1^\circ)
=7.48516616\times10^{-5}+i\,8.64957815\times10^{-6}.
```

Floquet 已固定跨胞相位，不意味着离散导数对这个相位的作用精确。用 lambda_x,h 表示离散横向特征值，而不是把输入 kx 随意改成另一个物理波矢：

```math
K_xv=\lambda_{x,h}M_xv,\qquad
\delta_x=(\lambda_{x,h}-k_x^2)/k_0^2,\qquad
k_{z,h}^2/k_0^2=\varepsilon-k_x^2/k_0^2-\delta_x.
```

### 1.1 对话中的独立诊断，不冒充实际 FE evidence

ChatGPT 使用标准连续 Qp、一致质量、充分 Gauss 积分和 Bloch 条件，得到以下小矩阵诊断；本轮在对话容器复算一致。它不是运行源码中的实际 Basix/FFCx/MPC 张量验证。

| p / hx (nm) | 诊断 delta_x | 相对 Si 法向平方实部 |
|---|---:|---:|
| 6 / 0.5 | 7.9379548e-6 | 10.605% |
| 7 / 0.5 | 2.1577869e-7 | 0.2883% |
| 8 / 0.5 | 4.4276843e-9 | 0.005915% |
| 6 / 0.25 | 2.5760098e-9 | 0.003441% |

再以光栅材料零阶 Fourier 系数 `eps_bar=1+(17/50)*(eps_Si-1)` 构成空气10 nm / 平均光栅120 nm / Si10 nm 的分层诊断，z 用解析传播；只将上述 delta_x 加入有限厚区段的传播关系，外部物理阻抗保持不变。无需拟合，诊断 R 从 0.07025521665 变为 0.08590959020，T 从 0.66885684947 变为 0.65222479392；变化接近报告差异。

此结果只支持 Hx 的数量级与响应模式。零阶材料诊断没有非零级耦合、角点或 z 离散，既不是严格均匀化资格，也不能用于证明 z 网格足够。实际端口、场与 3D 误差仍未知。诊断脚本未并入数值核心；执行者应从实际 FE 实现独立核验，不通过调材料/角度复现这些数字。

## 2. 未来验证冻结项与允许/禁止修改

目标光栅保持 lambda=0.7 nm、alpha=1 deg、phi=0、S、幅值1、period=50×25 nm；Si block x=16.5..33.5 nm、y宽25 nm、z=0..120 nm；上下边界 z=130/-10 nm。n_Si=0.9998851259969171+4.325285938225562e-6 i、eps=n²、air=1、mu_r=1；layered background、双 Floquet、无 PML。R/T/A 定义与原报告一致。

原始网格 Nx/Ny/Nz=100/2/234；x段33/34/33，y两层；z段17/200/17，对应 hx=0.5、hy=12.5、hz=10/17或0.6 nm。完整光栅验证先保持 n=0、m=-142..0、上下s/p的572项和原 q160 合同，不同时改变边界截断。

未来允许：实际局部张量/传播/端口动作诊断、独立小平面校准、单变量 x 与 z 网格对照、必要的小型接口修复与针对性测试。保持完整三维 p6 及已资格化求解路径；小场优先原 direct，比较时把代数误差压到远低于被测 observable 差异。

禁止：材料/角度拟合；把平均材料诊断替代真实光栅；删除高阶通道以凑 R/T；同时换 PC、p、x/z网格与端口；默认改 2D/2.5D；新 NN/PC 扫描；无容量预检的 93600-cell direct；重开旧大任务或干预当前 5 nm。若确需改变求解器，单列配对等价验证，不混入网格误差归因。

## 3. 顺序：先便宜地区分原因，再做有界 PDE

### V0：5 nm 收口后重新建立启动身份

用户激活后，先确认 5 nm 的恢复、输出、检查和子进程已结束。记录新 branch/HEAD/worktree、5 nm 终态与锁、运行源码、ABI/complex128、MPI/线程、实际输入与physical SHA、材料面/网格/外部keys、磁盘、MemAvailable/cgroup与watchdog。文档提交 SHA 不是旧场 source SHA；不得热更新活跃 worktree。

### V1：实际 FE 的横向色散和端口一致性

从生产入口实际使用的 Basix/FFCx 张量建立 y 不变 Ey 子空间的 Kx/Mx，或用等价、可审计的短周期均匀条带。记录 degree约定、每分量多项式空间、Jacobian、方向变换、复 MPC 与真实积分阶数；不能只另写一次理论 Q6 矩阵。

物理传播分支用解析波投影和参数连续追踪辨识；当前 kx*hx约4.487>pi，不能盲取最小特征值，或仅按数组顺序选择折叠分支。输出 hx=0.5/0.25/0.125 的 p6 结果；p7/p8仅作有界组件交叉检查，不启动整场高阶分解。与第1节诊断不一致时，先定位基空间、分支、积分或缩放差异，不能改测量结果。

并行于原因分析、非并行 heavy run：用实际端口投影/traction和入射组装核对一个解析平面波的作用，检查坐标相位、法向、共轭、归一化及 background/total-field转换。端口积分充分性先在小组件上单独提高积分核验，不整场重建大矩阵。插值解析波后的非零残差本身可能是离散误差；看随h/p变化及分项一致性，不能直接判bug。

V1分类：`HX_SYMBOL_SUPPORTED`、`HX_SYMBOL_MISMATCH` 或 `INCONCLUSIVE`，都不是原光栅 accuracy pass。保留纯理论数字与 actual-FE 数字的区别。

### V2：小平面校准，隔离体传播与端口

去掉光栅，保留同一材料、入射、z参考面、背景和实际 FE/端口实现，与平面 Si 解析解比较。校准目标由公式重算，不硬填期望：

```math
q_a=k_0\sin\alpha,\quad q_s=\sqrt{k_0^2\varepsilon_{\mathrm{Si}}-k_x^2},\quad
r_s=(q_a-q_s)/(q_a+q_s),\quad R=|r_s|^2,
\quad T_{-10}=(1-R)\exp[-2\operatorname{Im}(q_s)\,10].
```

选择无源向外衰减分支，参考面复相位另明确。解析 R约0.1134908093、T_-10约0.8105414526；这是平面而非光栅目标。

为了避免平面测试本身成为大模型，可利用平面几何的平移不变性选固定 Lx=1 nm（p6 hx=.5/.25/.125 对应 Nx=2/4/8），Ly=25 nm、Ny=2；z网格先保持原分段与精度。新小平面的物理周期、模式清单、Floquet相位和来源 SHA 必须重新生成，标记 `FLAT_COMPONENT_NOT_ORIGINAL_GRATING`。不允许把原光栅缩到1 nm。小平面不能验证原50 nm单胞的全部143通道耦合，其有限边界写清楚。

保持 z与端口实现不变，测x加密；若小平面资源仍不准入，保留V1并报告，不直接跳完整大模型。记录复r、t、E/H、分区吸收及必要沿z拟合的传播波数，不能只看R。解析波数拟合须包含双向波，不用局部两点比值误判驻波。

若误差随x加密明显下降且传播偏差吻合，支持Hx；若误差停滞，单独检查端口/入射/z离散，不能无限继续x加密。V1/V2结果与参考不吻合不是继续大场的理由。

### V3：完整光栅的方向对照；先预算，不自动启动

| case | x网格 | z网格 | 用途 |
|---|---|---|---|
| A | 原hx=.5 | 原17/200/17 | 已有46800-cell结果；只读复用合法证据 |
| B | hx=.25，Nx=200 | 与A相同 | 隔离x影响；93600 cells，必须单独容量Gate |
| C | 与A相同 | 候选9/100/9；buffer=10/9、grating=1.2 nm | 隔离z粗化；只作诊断，不能以欠收敛A给精度资格 |
| D | 与B相同 | 与C相同 | 与B比较z粗化，与C比较x加密；47200 cells |

A/B、B/D是主要的因果对照。C是预算允许的补充，不要求为凑矩阵自动多跑一场。不得仅比较A/D就把变化归因于x，或宣布D网格收敛；两方向误差可能相消。B放不下时，D可被单独批准为资源候选，但只能记 `CROSS_CHANGED_GRID_DIAGNOSTIC`，不能充当单变量证据。后续可在较小、同物理机制的组件建立方向趋势，不能冒充原尺寸场资格。

先评估最大传播级与现有场的可观测量需求，再确定是否采用1.2 nm的z候选；该数字不是预先批准的生产网格。p7/p8全模型及第二轮加密不自动授权。一次相邻网格接近只证明该方向的有限对照；如要宣布精度资格，须有独立参考和所需量的进一步稳定性证据。

## 4. 为什么 z 可探索粗化，但不能直接删减

本场空气中 n=0 时：

```math
k_{x,m}/k_0=\cos(1^\circ)+0.014m,\qquad
\lambda_{z,m}=0.7/\sqrt{1-[\cos(1^\circ)+0.014m]^2}\quad\mathrm{nm}.
```

| m | 派生z相位周期/nm |
|---:|---:|
| 0 | 40.1091 |
| -1 | 4.17553 |
| -2 | 2.97101 |
| -5 | 1.90246 |
| -20 | 1.00845 |
| -71 | 0.700012 |

零级慢不等于全部场慢。强度干涉、角点、材料面、倏逝衰减和未来z=60 nm缺陷还会增加局部尺度。本场高阶尾部功率小，允许研究“总量容许误差下”的z减配，但不能据此认证高阶相对误差或局部E/H。z=0、120与端口必须精确匹配；任何新增缺陷的上下表面也要匹配。独立诊断采用解析z，不是z粗化证据。

## 5. 有方位角或局部y缺陷时，不能继承原网格/通道资格

对掠角alpha、方位phi的入射：

```math
k_x=k_0\cos\alpha\cos\phi,\quad k_y=k_0\cos\alpha\sin\phi,\quad
k_z=-k_0\sin\alpha,\qquad
\lambda_y^{\mathrm{inc}}=0.7/(\cos\alpha\,|\sin\phi|).
```

phi=1/5/10/30/45 deg时，入射y相位周期分别约40.115/8.033/4.032/1.400/0.990 nm。小方位角允许考察较粗y，但不是“一有方位角就统一三轴细化”；大方位角时y可能与x一样严格，甚至成为主传播方向。普通Floquet只约束跨胞相位，不会替单元内部精确表示exp(i*ky*y)。

材料严格y不变时，物理解可写 `E=exp(i*ky*y)*Ehat(x,z)`；真正2.5D需要在Maxwell算子中使用 `partial_y -> i*ky` 并保留矢量耦合。这是专门的方程表示，不等于当前三维网格只有两层。phi=0时原物理解在y不变子空间，但完整三维p6仍存储y自由度。

若在z=60 nm附近只有部分y区间出现材料缺陷，y平移不变性被破坏。即使phi=0，也出现 `ky,n=2*pi*n/25 nm` 的散射谐波；应同时检查缺陷几何面、局部y/z场梯度、跨胞周期一致性与外部(m,n) inventory。不能继续仅保留N0端口。也不要求一开始全域y都与x同细：从几何匹配的局部方向加密起步，按复场、衍射谱和误差指标扩展。

小体积缺陷不保证局部场或弱衍射信号误差小。当前周期边界会把缺陷随单胞重复，不代表单个孤立缺陷。新增phi或缺陷仅在本文解释适用边界，**不是本轮追加PDE授权**。

## 6. 验证 Gate、资源和停止条件

| 层次 | 判断要求 |
|---|---|
| algebra | 沿用原作用域独立true residual<=1e-6、恢复/约束/端口闭合；小平面另检线性误差对输出的影响小于目标比较误差的1/10；不以内部KSP量代替 |
| own physics | abs(R+T+A_volume-1)<=1e-5，abs(A_balance-A_volume)<=1e-5；finite、被动性与分区吸收检查 |
| Hx机制 | 实际符号偏差、平面复场/通量、单变量h变化共同支持；仅R接近不称根因定位 |
| 网格比较 | 继承原task G参考标准：R/T/A/A_volume绝对差<=1e-4；显著级功率/复幅值相对差<=1e-3；selected E相对L2<=5e-3、H<=1e-2。显著级取两场功率>=1e-8的并集，弱/近零量另报绝对误差 |
| reference | RCWA工程、orders复幅值、kinematic/flat calibration原件取得并核身份后才提升参考资格；缺项可继续解析平面诊断，不伪造相位或原始hash |
| scope | n0通过不称full-DtN通过；保留AUTHORITY_LIMITED/FULL_DTN_NOT_VERIFIED，除非对应缺口被实际关闭 |

同坐标/同材料侧别比较复E/H，不直接减不同网格的native向量，不拟合整体相位，不把采样网格当FE网格。m0、-1、-2、-4、-5、-7与高阶分组至少明确列出；匹配横向原点及上下参考面。保留所有143级，不以总量合格掩盖弱级不合格。

未来新验证按长期目标规划：一次一个heavy、系统余量、任务zero swap、进程树watchdog、无OOC。建议沿原task小组件32 GiB硬上限及24 GiB规划上限起步，且受现场更紧可用量约束。完整光栅重新分阶段做FE/trace/port/CSR、symbolic/numeric、恢复峰值预算；禁止把单元数×旧RSS当准入依据，禁止假设47200 cells与旧46800场成本相同。direct沿已资格化release-before-recovery生命周期。

旧V7的swap observe-only和高RSS合同不在活跃5nm上被本文改变。本文激活时应明确冻结新验证的资源合同；若不能满足zero-swap与系统余量，则不启动压力PDE，不以旧豁免宣称长期目标通过。

预检失败、容量不足、true residual/能量失败、进程监控失效时保存证据并停止受影响PDE。普通局部实现错误允许最小修复和针对性重测，不放宽Gate，不重装环境，不反复重跑大场。数值假设被否定时继续现有文件/小组件的独立分析，报告已排除项；不得靠调材料或删通道制造吻合。

## 7. 交付与提交计划（由用户激活后执行）

每个正式PDE使用 `python scripts/run_case.py input/task39extra_para_workstation_capacity/<one_case>.dat`；一个dat一次计算。新source必须clean并绑定input_original/resolved_config/run_manifest/run_summary、input/physical/source SHA、ABI/MPI/资源与artifact hashes。

建议分三类原子提交：实际符号/端口组件及测试；有界平面/网格输入与实现；轻量证据和收口。不要amend/强推，不覆盖旧失败，不merge master。重型矩阵、场与因子只留ignored路径。

执行结果放 `outcomes/dispersion_directional_validation_20261015/`，至少含 `summary.md`、`symbol_checks.json`、`flat_calibration.json`、`directional_grid_comparison.csv`、`resource_and_scope.json` 及run/hash索引。未执行项写NOT_RUN或BLOCKED；本文不提前创建这些结果文件。

新增独立回应 `response_dispersion_validation_20261015.md`，保留response_v7；更新任务outcomes/summary与项目总账时区分旧迭代合同和已完成direct。首屏回答：Hx得到支持/否定/仍未定？x减半改善哪些量？z最多粗化到哪个已测试网格而不损害哪些量？原端口是否经过实际验证？还缺哪些复场/衍射/资源资格？不得只写PASS。

## 8. 理论参考

- Ainsworth (2004), *Dispersive properties of high-order Nédélec/edge element approximation of the time-harmonic Maxwell equations*, DOI 10.1098/rsta.2003.1331：https://strathprints.strath.ac.uk/64/ 。张量积Nédélec与一维离散传播关系；不直接提供本仓库的精度证书。
- Basix 0.10 官方文档：https://docs.fenicsproject.org/basix/v0.10.0/index.html 。用于核对实际基函数、映射和方向变换，不要求升级当前ABI。
- Meep官方 *2d Cell with Out-of-Plane Wavevector*：https://meep.readthedocs.io/en/latest/2d_Cell_Special_kz/ 。说明解析提出不变方向相位与矢量耦合；坐标轴须对应到本项目y方向，不是建议移植Meep求解器。

**下一最小可审计动作是V1的实际FE传播关系检查；不是立即把原光栅x加密、z粗化并启动一次TB级分解。**
