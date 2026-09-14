# Task39extra Review V18：装配时单元凝聚的准确p4逆与可选BLR

## 0. 决定、身份与权限

**关闭V17原p4上的阈值试验。新主线不是42宏块，也不是另造接口近似PC，而是复用Task035b已有的装配时单元静态凝聚：直接装配p4独立trace与原DtN端口的凝聚矩阵，保留它的一份准确全局LU，以局部缩减／恢复返回完整p4修正。准确路线合格后，允许对这份新的凝聚矩阵做一次可选BLR；压缩失败或收益不足，不否定准确凝聚路线，也不阻断后者的完整p6验证。**

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task39extra
review_date                = 2026-09-14
reviewed_base_SHA          = d03320fcaeaed24ad8e3250c3123d96790131346
latest_commit             = Record V17 BLR tradeoff rejection and Response V18 evidence
previous_review/response  = review_report_v17.md / response_v18.md
closed_V17_source         = a1bc6b54e613ebf91c5c97ecddcc14555b084ee0
accepted_full_p4_Q1_source = 6a8b273c383d5bd9da37d6630a48bd24d6a90cce
new_batch_identity        = review_v18_p4_cell_condensed
suggested_profiles        = physical_p4_cell_condensed_exact_v18
                            physical_p4_cell_condensed_blr_v18
execution                 = U0 -> conditional U1 -> U2 -> optional U3 -> U4/U5 -> U6
response_required         = response_v19.md
time_policy               = observe_only
ordinary_default          = unchanged
master_merge              = NOT_APPROVED
```

本轮消除的blocker是：**已成功BAL_H所需的准确p4全局响应，是否因完整p4装配和因子组织而付出了可避免的存储成本？** 保持p6上的真实方程、H6和BAL_H；不把最终物理解降成p4。它仍含全局trace因子，是准确粗逆的工程改进，不是0.7 nm任意三维、2 TB内的最终可扩展生产资格。

用户本轮明确授权单元凝聚准确路线及其后一次BLR。因此，本文件对新profile覆盖V14的42宏块路线、V16/V17只压缩原完整p4的限定，以及“BLR不满足内存收益就不准任何p6”的旧分流；旧profile、checker、负结果和账本不追溯修改。读根／docs AGENTS、仓库原则、task及本review后连续执行，不在每个小检查后停审。本批仍只做本机13.5 nm、MPI1；不运行5 nm/0.7 nm，不修改Task41或并行工作站线，不整体merge/cherry-pick。

## 1. 本次审阅结论与必须改的项目

证据：[最新回应](response_v18.md)、[V17决策](outcomes/records/p4_blr_tradeoff_v17_decision.json)、[汇总](outcomes/summary.md)。以下是仓库记录的measured/derived值，不是本review新运行。

| 当前结果；单位与范围 | 原p4准确Q1 | 原p4 BLR 1e-5 | 最新原p4 BLR 1e-3 |
|---|---:|---:|---:|
| p4三输入完整树RSS，B（measured） | 2,825,973,760 | 2,741,243,904 | 2,672,054,272 |
| 相对Q1的RSS降幅（derived） | 0 | 3.00% | 5.4466% |
| 因子条目（后端原生计数） | 53,417,584 | 53,040,280 | 48,706,124 |
| 三输入场L2相对差 | 0，复现已存参考 | 0.000469 / 0.000638 / 0.000518 | 0.604297 / 0.682241 / 0.620539 |
| 三输入原A4残差 | 最大6.56e-11 | 0.012748 / 0.000717 / 0.017678 | 4.787742 / 0.194757 / 6.063574 |
| 完整p6／非可分验证 | 另有V5历史，不属于本表 | not_run | not_run |

最新T1的BLR fronts=33、覆盖比例49%；条目减少8.8201%，并非“压缩从未启用”。质量与内存线均未过，T2=1e-4未运行符合V17合同。T1的WORKER_FAILED/exit4是数值拒绝后的wrapper终态，不是OOM／超时／MPI崩溃；后续新checker应分开写执行完整性、数值质量和资源收益，不把“正确读出负结果”记作solver PASS。

| 审阅问题 | 本轮最小修改 | 禁止的误读或补救 |
|---|---|---|
| 42宏块准确Schur增加内存 | 改为逐单元装配时凝聚及紧凑类型缓存；不创建宏块对象或42份MUMPS实例 | 不把旧宏块负结果改判，不承诺新路径必省一半 |
| 三个T1输出各4个slave存储项约1e-18非零 | 新凝聚系统不求解slave identity rows；返回向量先全置零，再填独立解与内部解；真实物理backsubstitution另用副本 | 不放宽旧strict-zero，不修改已存T1向量；这不是60%场误差的根因 |
| T1缺矩阵内容hash | 对每个新全局凝聚矩阵在factor前流式记录shape/dtype/CSR内容hash与映射hash；前后核验未被修改 | 不把rows/NNZ相同当数值相同；不因旧Q1缺hash重做全部历史 |
| 未约束载荷与MPC存储向量混用风险 | 明确primal/dual/independent/storage转换；支持非零内部RHS | 不把P64^H q再次当未约束载荷做C^H，不只截取trace |
| p4通过与完整p6通过混淆 | 实际接通所选逆、完整original和条件notch | 不以NOT_RUN占位或三输入PASS结束可执行主线 |

不为补上述旧metadata再跑V17。新输出必须补齐，旧缺口保持；本review不宣称已经本地重放全部原始数组。

## 2. 复用依据与冻结的物理／数值身份

[Task035b历史汇总](../task035b_high_order_local_hp_resource_envelope/outcomes/summary.md)记录了MPI8 p6/h10：完整装配35.024 GiB，装配后Schur29.212 GiB，**装配时凝聚且保留全局factor16.998 GiB**；后续释放／heap trim为另一种生命周期，最低记录15.964 GiB。35.024到16.998的约51.5%下降是该历史workflow的工程结果，不是对当前p4/MPI1的预测。不要将不同MPI、入射、后处理和采样范围拼成同一对照。

当前分支已含可复用模块，无需从Task41整体迁移：

| 模块 | 本轮用途与边界 |
|---|---|
| `src/solvers/hcurl_assembly_time_condensation.py` | FFCx单元核、方向变换、独立trace编号、精确预分配、按类型的LU／恢复数据；优先复用 |
| `src/solvers/hcurl_cell_static_condensation.py` | 历史数学oracle／小fixture；不以先组装全矩阵的路径冒充assembly-time |
| `src/solvers/fullspace_p4_reference.py` | 原A4/端口增广及准确逆接口参照；不得在新候选后台构建旧全局factor |
| `src/solvers/condensed_dtn.py`及现有carrier | 复用端口装配思想，但严格桥接符号与左右耦合；旧F-CH^-1D命名不能直接替代本任务V+BH^-1D |
| `src/solvers/physical_balanced_coupling.py`、已有完整p6 runner | 保留BAL_H/H6及原A6/后处理；只替换p4 inverse适配，不复制庞大研究runner |

在本次base核对的assembly-time模块仍为blob `9472c135d51dffe4ce5d5c1dac28fae762dfc9d8`。其现成辅助函数分别接收未约束向量或MPC向量，不能只按函数名接线；其部分投影函数要求内部RHS为零，不适合一般p4残差。

| 冻结项 | 值／规则 |
|---|---|
| 模型 | 原50×25 nm单胞、z=-10..130 nm、Si/air、252 hex；13.5 nm、grazing1度、azimuth0、s |
| 材料 | n_Si=0.999002304859+0.00182649365i，mu_r=1；全部角色、材料tag与原数值不变 |
| FE及边界 | p6/h10真实算子；同网格物理p4；complex128、双Floquet、原80 DtN条目的key/顺序/相位/法向/归一化全部不变 |
| 环境 | 已资格化Linux DOLFINx/Basix 0.10系列、PETSc complex128/int32、MPI1/线程1、已链接MUMPS 5.6.2；记录实际库路径，无ABI升级 |
| 物理SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ordered mode SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| 三控制RHS | `A2R160_BAL_H_p4_01`、`A2R160_BAL_H_p4_02`、`LIGHT448_BAL_H_p4_09`；复用原hash-bound参考 |
| 非可分验证 | V5冻结8个canonical cell keys的实际材料实体；不重新选较易缺口 |

原p4独立／存储行为48,960／53,084，全局端口增广53,164；预计单元内部为252×108=27,216，独立trace为21,744，加80端口后21,824。**这是已有拓扑/元素计数的核对预期，正式值须从Basix entity DoFs和MPC实际映射取得**，不能硬编码绕过检查。历史p4凝聚NNZ=8,184,464只作背景，不要求当前物理矩阵数值或排序与它相同。

## 3. 数学合同：准确单元凝聚，不改变p4逆

### 3.1 先组成完整单元物理张量，再消元

原目标仍为：

```math
A_6x=b_6,\qquad A_4=P_{64}^H A_6P_{64},\qquad
A_4=V+BH^{-1}D,\qquad
\mathcal A_4=\begin{bmatrix}V&B\\-D&H\end{bmatrix}.
```

单元V_K必须包含同一积分合同下完整curl、复材料质量及所有相关体积项，再计算局部Schur。**不能分别凝聚curl项和质量项再相加**；一般Schur(K-M)不等于Schur(K)-Schur(M)。不加正定shift、不改quadrature，不降低trace阶次，不丢任何p4基函数的物理影响。

以i表示仅本单元拥有的内部自由度，t表示保留的独立trace，alpha表示原端口。Floquet按合法局部延拓实施，解释性分块写在独立坐标上：

```math
\begin{bmatrix}
V_{ii}&V_{it}&B_i\\
V_{ti}&V_{tt}&B_t\\
-D_i&-D_t&H
\end{bmatrix}
\begin{bmatrix}c_i\\c_t\\\alpha\end{bmatrix}
=\begin{bmatrix}g_i\\g_t\\0\end{bmatrix},
\qquad V_{ii}=\operatorname{diag}_K V_{ii}^{(K)}.
```

这里是252个单元内部小块，不是42个宏块；i之间无跨单元耦合必须从FE支撑及约束核验。内部块不可逆／局部LU不稳定时如实停止共同核心，不以正则化、伪逆或丢未知量“修复”。小块使用已有complex128 LAPACK LU，不为每个单元启动MUMPS。

### 3.2 端口也按完整消元处理

下式给出一般情况，避免错误假定高阶端口向量内部项必为精确零：

```math
\begin{aligned}
S_V&=V_{tt}-V_{ti}V_{ii}^{-1}V_{it},&
\widehat B&=B_t-V_{ti}V_{ii}^{-1}B_i,\\
\widehat D&=D_t-D_iV_{ii}^{-1}V_{it},&
\widehat H&=H+D_iV_{ii}^{-1}B_i,\\
\widehat g_t&=g_t-V_{ti}V_{ii}^{-1}g_i,&
\widehat g_p&=D_iV_{ii}^{-1}g_i.
\end{aligned}
```

```math
\widehat{\mathcal A}_4
=\begin{bmatrix}S_V&\widehat B\\-\widehat D&\widehat H\end{bmatrix},\qquad
\widehat{\mathcal A}_4\begin{bmatrix}c_t\\\alpha\end{bmatrix}
=\begin{bmatrix}\widehat g_t\\\widehat g_p\end{bmatrix},\qquad
c_i=V_{ii}^{-1}(g_i-V_{it}c_t-B_i\alpha).
```

若实际B_i、D_i严格为零，相关项自然为零；否则使用已有左右向量凝聚和局部bilinear处理，不能直接截断。尤其原增广端口RHS为零，不代表消元后的端口RHS仍为零。D不是B的共轭转置；不得强行Hermitian化。保留稀疏trace系统与80端口，不显式展开全局稠密DtN或全局稠密Schur。

局部贡献在生成时直接累计到最终独立trace/端口稀疏系统；新候选的全局原p4矩阵、全p4 LU、完整含slave trace中间矩阵都不分配。局部小稠密张量是允许的，并须计入缓存／工作集。

### 3.3 一次p4调用与坐标合同

输入g是BAL_H给出的原生p4合法slave-zero存储向量，代表已施加MPC的dual右端。先读取其独立坐标；不得再做一次C^H造成重复约束。每次调用执行：局部RHS缩减 -> 一次全局凝聚回代 -> 非零内部特解与trace/port响应恢复 -> 返回原p4存储向量。每次调用都必须完成内部恢复，不能等到最终p6后处理才补。

输出先分配零向量，仅填入独立trace和内部坐标，slave存储位置保持精确零。物理场的MPC backsubstitution在单独副本或既有P64/场映射中完成，不污染代数输出。零RHS可直接返回零；非零输入每次全局MatSolve恰好一次。准确路线无p4内层Krylov、无后端／外部refinement；局部LU与全局LU均在setup建立并复用，不每个g重新分解全部单元。

按原carrier计算独立残差，而不是只查凝聚方程：

```math
r_4=g-A_4c=e_{\rm top}-BH^{-1}e_{\rm port},\qquad
\begin{bmatrix}e_{\rm top}\\e_{\rm port}\end{bmatrix}
=\begin{bmatrix}g\\0\end{bmatrix}
-\mathcal A_4\begin{bmatrix}c\\\alpha\end{bmatrix}.
```

此处H是原H，不是hat-H。native A4继续使用已有matrix-free/streaming action；不为检查残差在候选流程里重新装配全局原p4矩阵。

## 4. 存储与生命周期：省的是完整装配与重复对象，不是物理自由度

按已有单元类型缓存LU和恢复/RHS作用。缓存键必须涵盖实际单元算子所依赖的材料／复系数、k0、尺寸/Jacobian、方向、p、积分与基函数身份；仅同tag不足以证明相同矩阵。报告owned cells、unique raw/oriented classes、命中数以及各类张量/LU/恢复矩阵总bytes。无需规定必须只有若干类；任意非可分cell-wise材料不能通过错误合并类型来省内存。

**不保留42份宏块MUMPS，也不改成252份单元MUMPS。** 允许紧凑单元类型LU与局部恢复算子，不形成全局稠密逆／全局稠密恢复矩阵。不同时保存无需使用的raw tensor、多个同义Schur副本、CSR/COO全副本；确认所有权再释放，不能清账但保留引用。新owning adapter的destroy必须释放其自有矩阵/factor/cache/工作向量，不能以旧helper只destroy矩阵就宣称缓存已清空。

本批按用户指定测量“保留全局凝聚因子”的主实现：control中保留至第三RHS评价/保存结束；完整p6中因子跨全部外层步骤复用，并保留至本场最终恢复与物理检查结束后再统一销毁。显式记录`retain_through_postprocess_v18`。**不要在本批同时引入release/heap-trim优化来制造收益。** 这是新研究profile的生命周期限定，不修改既有production或其他profile的release_before_recovery；未来重型运行仍应使用已建立的安全生命周期。因子占用触及本批硬资源线仍必须停止。

理论上减少全局矩阵尺寸、避免完整装配与重复内部对象有节省的理由；但LU填充、缓存和峰值叠加可能抵消收益。正式结论由全过程RSS和反复调用工作集决定，不能承诺50%，也不能用21,824/53,164直接预测内存比例。

## 5. U0–U2：一次适配，先取得准确凝聚对照

### U0：必要正确性与接线

确认branch/HEAD/canonical worktree/clean source、ABI、线程、input/physical/mode、磁盘/宿主空间、MemAvailable/cgroup、swap及watchdog。复用已通过且未受改动影响的基础资格，不重研EIO、MUMPS版本、ICNTL49或旧BLR失败。

集中做一批小复数代数和实际单元/两单元fixture：非Hermitian左右耦合、非零g_i、非零B_i/D_i、复Floquet primal/dual、内部恢复、原增广残差恒等式、零RHS／线性／重复新g、输入不改、一次factor反复solve、strict slave-zero、destroy/异常清理。用fixture的完整矩阵作oracle是允许的，但不在正式252单元候选中保留全矩阵oracle。

sum-before-Schur、方向变换和Galerkin/原native action操作尺度相对误差各不超过1e-10；零量用预先定义的正操作尺度。新CSR hash在装配结束、numeric之前取得；顺序遍历owned canonical rows/columns/complex128值，记录shape、dtype、字节序、nnz语义和hash算法，不gather稠密矩阵。exact与BLR应引用同一凝聚输入矩阵身份；完整与凝聚矩阵形状不同，不能要求两者hash相等。

实际模块已有有限几何支持，本轮只使用已资格化的轴对齐仿射hex和cell-wise材料；不得为这次任务重写全网格/全部FFCx/MPI后端。记录该边界，不称已支持任意曲面。必须提供真实完整p6 dispatch的小型mock/契约测试，不能保留NOT_RUN分支却写实现完成。

### U1：基线复用，最多一场必要matched control

数值参考优先使用既有Q1三输入与V5 original/notch，不重建完整p6参考。资源基线先桥接Q1的原始全树轨迹、公共对象、装配/评价与因子保留政策；仅算法对象及其必要生命周期不同是比较内容，不要求给凝聚候选额外分配旧完整矩阵。

若ABI、测量窗口、冷/暖缓存、公共评价对象或非算法实现变化使旧Q1不足以公平比较，允许**最多一场新原p4未压缩control**，仅作同口径分母，独立进程、同三RHS。缺历史矩阵内容hash本身不是强制重跑理由。未能建立公平分母时给`MEMORY_COMPARISON_INCONCLUSIVE`，新准确路线仍可继续数值验证，不假造百分比。

原Q1约2.826 GB是p4 control，不是完整p6峰值；V5约3.466 GB是完整p6历史背景，生命周期不同，不用于本批p4节省分母。原宏块Schur约4.267 GB只作为历史负对照，不重跑。

### U2：装配时单元凝聚，准确全局trace LU

新准确profile：全局factor的ICNTL(35)=0、ICNTL(10)=0；complex128、原Q1排序/主元/缩放策略，无OOC、无BLR、无shift。记录真实控制及排列（可得时），不扫描ordering。局部精确LU不受全局BLR开关影响。

构建一次凝聚矩阵和factor，对冻结三RHS各做一次完整p4调用，立即保存原g、c/alpha、r4、原范数、场/curl及计数。质量Gate：每份原A4相对残差<=1e-10、匹配参考L2/scaled-curl<=1e-8、原残差恒等式<=1e-10、strict slave-zero；检查全局无原p4矩阵/宏块factor，并从实际库存证明单元cache策略。

在同一factor上，追加最多三次不使用新参考的廉价调用：重复01；01+i*02；09-01。检查重复性、线性和新RHS特解，记录局部/全局factor计数仍不增长，原A4相对残差仍<=1e-10；不得扩成新的方向筛选。主要三RHS资源对照窗口单列，新增三次调用与全run峰值另报，不与旧三次工作流混算。

**准确性和系统安全通过即保留为U4的默认选项；内存未达10%或50%不是拒绝准确路线的理由。** 本轮不再用旧BLR收益线阻断等价准确逆的完整复现；内存增加如实报告，不把它写成优化成功。共同核心不等价时停止U3–U5并修其原因，不能用BLR掩盖。

## 6. U3：只对新凝聚矩阵试一次BLR，失败可退回准确路线

U2数值合格且资源允许后，在同一凝聚矩阵上做**唯一tau=1e-5**控制，不压缩单元内部LU。选择这个保守起点是为了保住已知准确逆；新矩阵/缩放/消元图已经变化，旧完整p4的压缩率及误差均不可照搬。不得继续旧1e-3、补旧1e-4，或扫描其他阈值。

ICNTL(35)=2、CNTL(7)=1e-5均在symbolic前设置和读回；ICNTL(10)=0，ICNTL(36/37/38)=本机已冻结0/0/600；其余同U2。无需新装后端或调查49。与U2全局factor顺序存在，分母同scope；不同时保留两套factor。若使用缓存/矩阵加载改变了生命周期，明确冷启动与复用观测，不能用warm减cold。

同三RHS各一次全局MatSolve（加必要局部缩减／恢复，不含内层迭代）；保存原A4残差/场误差、BLR原生entries、fronts/coverage可得值、allocated/used、完整及factor-live RSS/PSS。理论满秩条目分母使用**新凝聚矩阵本次**INFOG(29)，不是原p4的53,417,584。

| U3结果 | 对本批的唯一影响 |
|---|---|
| 三RHS均rho<=0.5、L2/curl<=0.25，正确性与安全合格；且相对U2完整RSS<=0.90，或live<=0.80且完整<=1.05，实际压缩存在 | 允许选择凝聚BLR进入U4；仅称p4控制准入 |
| 质量不足／实际不压缩／收益不足／支持字段确实不可取得 | BLR标为optional negative或unqualified；**选择U2准确凝聚进入U4**，不加refinement/第二回代 |
| BLR独有factor/资源失败，完整清场且共同精确核心仍合格，重新安全预检通过 | 明确记录独立失败；U4使用准确凝聚，不自动提高任何cap |
| 发现共同矩阵、映射、文件系统或监控错误 | 停止受影响运行；不能把共同错误当BLR-only绕过 |

前述BLR收益线只决定是否采用压缩版本，不决定准确凝聚是否完成。用户要求“压缩不了也没关系”在此落实为明确回退，而不是把两条路线一起判失败。

## 7. U4/U5：所选p4逆接回BAL_H，完整原始与缺口裁决

U4的dat从U2/U3决策生成并冻结`backend=exact`或`blr`，manifest引用决策hash；一个dat只表示一种明确算法。每次BAL_H保持：

```math
\begin{aligned}
g_1&=P_{64}^Hq,& c_1&=F(g_1),& z_c&=P_{64}c_1,\\
s&=H_6(q-A_6z_c),& g_2&=P_{64}^HA_6s,& c_2&=F(g_2),\\
z&=z_c+s-P_{64}c_2.
\end{aligned}
```

F现在是“单元内部缩减 -> 一次全局凝聚回代 -> 完整内部恢复”。H6不变；不叠加旧I4四步、C_U/S-p2、macro-DD、接口SVD、recycling或新MR。两次g_i在线生成，不拿旧固定反馈RHS替代。记录两次粗缺陷和BAL_H闭合，操作尺度<=1e-8；准确F与原准确p4接口的小量对照不能要求每步浮点轨迹逐字节相同。

right FGMRES32、零初值、最多2048步；每8步原A6真残差/计数/资源，每32步先存解再评价。64步原rho>0.10作进展停止；通过则同一个KSP继续，不反复重启整场。时间只观察。精确分支若不再接近V5的数值行为，优先核对等价桥，不以加步数或放宽残差补救。

若选定BLR的U4未通过数值/物理Gate，但U2准确核心仍合格且资源安全，**只允许一次显式exact-only original对照**，新dat、新run，零初值，不在同一KSP内暗换factor。BLR失败保留；准确对照若也失败即收口。exact是默认时不再增加第二种fallback。输出/保存错误可从同一合格checkpoint恢复，不重复求解清洗失败。

获得完整original通过的backend后立即U5同配置notch；实际材料重新组装并分解，不复用original数值factor。U5失败保留适用边界，不对缺口另调tau或再开第二backend。原始未通过则notch不运行。

| 最终Gate | original与notch均要求 |
|---|---|
| 原A6方程 | full explicit norm(b-A6x)/norm(b)<=1e-6；递推与真实值分列 |
| 同离散场 | L2/scaled-curl<=1e-4；复E/H、同位置近场，无拟合整体相位 |
| 功率 | R/T/A/A_volume各自参考绝对差<=1e-5 |
| 独立守恒 | R+T+A_volume-1及A-A_volume绝对值<=1e-5 |
| 全部80模式 | 复幅值向量相对差<=1e-4；逐通道功率最大绝对差<=1e-6 |
| provenance与资源 | 输入/物理/源码/模式/数组hash齐全；全过程RSS/PSS与计时、zero swap、清场 |

不通过原A6残差不发布official功率。完整p6只能报告本批实际峰值；没有同生命周期完整p6对照，不能把p4百分比说成整体节省。因子保留至本场最终评价后再清理，测量第4节策略而非混入释放优化。

## 8. 公平资源、次数与停止条件

| 项目 | 本批合同 |
|---|---|
| 全树RSS | 启动min(8 GiB,effective_available-reserve)；沿已修正动态检查，含父子/JIT/compiler，不能重复扣当前RSS |
| reserve | max(4 GiB,15% effective_total)，实际cgroup与宿主余量；一次仅一个heavy |
| 数值常驻库存 | 总计<=6 GiB，含全局factor/矩阵、单元缓存、H6、transfer、向量；不对各对象分别给6 GiB |
| 临时工作集 | 最大同时1 GiB，含单元核、CSR/COO、后端、评价/保存副本；只计同时存活而非历史累加 |
| 配额 | 延续V11 symbolic-sized规则及V16完整研究profile口径；取本版本较保守估计，不用默认压缩率冒充容量 |
| swap/磁盘 | zero job swap及无新增global swap，禁止OOC；空间/写入异常停止，不自动修盘/迁移/升级ABI |
| 时间 | 全链路observe_only；不恢复600秒、25/30秒、1800/5400秒或总wall终止线，仍记录实际耗时 |
| 正常计算上界 | U2准确control一次、U3压缩control最多一次；U1匹配full control最多一次；original最多一个选定backend加一个条件exact回退；notch一次 |
| factor创建 | 每个control/完整run本场一次global factor；新run可fresh重建并计费，无因子序列化新平台；禁止逐RHS重新numeric |
| 实现bug | 本批至多一次有证据的受影响formal重放；负数值、压缩不足不是bug，不能借此换tau |

沿用一dat一run入口`python scripts/run_case.py <case.dat>`及显式profile/解析参数。U1/U2/U3使用同三RHS和对应phase边界；额外线性调用单列。原p4对照、准确凝聚、凝聚BLR分别列峰值与在场对象，不相加，不从峰值差直接推factor-only bytes。

各场分列cold/warm、setup/单元核/局部Schur/全局装配/symbolic/numeric/RHS缩减/全局回代/内部恢复/native核验/后处理/清理。首次构建成本不能摊掉后冒称冷启动峰值；局部缓存与全局factor计数要随调用验证不增长。不要求再研发通用内存审计或重跑历史长测试。

新账本`review_v18_p4_cell_condensed`只追加新费用，引用旧V14/V16/V17 ledger及unknown，不返还旧600秒政策占用，也不把它写成本场实耗。若硬资源未允许或共同正确性失败，停止并保存已完成证据；剩余预算不构成继续试新算法的理由。

## 9. 提交、证据与最终回答

阶段commit：①最小单元凝聚inverse适配、坐标/hash与测试、真实dispatch；②U1/U2准确对照；③U3可选BLR与固定选型；④U4/U5正式结果；⑤response及汇总。正式计算使用clean source；不amend、不强推、不删旧负结果，不改master/普通默认值。相关定向测试在最终代码修改后重跑；未运行Ruff/full pytest/CI如实说明，checker正确退出不等于数值成功。

必需轻量中心交付：

```text
response_v19.md
outcomes/p4_cell_condensed_v18.md
outcomes/records/p4_cell_condensed_v18_compact.json
outcomes/records/p4_cell_condensed_v18_decision.json
outcomes/records/run_index.json                # 增量
outcomes/summary.md / outcomes/test_summary.md # 增量，旧记录保留
```

同步维护development_progress、development_model_registry和selective边界。每场保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary、matrix/mode/map/局部类型hash、RHS/参考/output hash、环境/MPI和artifact索引。大矩阵/factor/场只进ignored。新矩阵内容hash必须真实计算；历史Q1缺项不人工补PASS，维度一致与数值等价分列。

U6首屏必须回答：

1. **准确单元凝聚是否仍为同一个p4逆？** 非零内部RHS、三参考输入、重复/线性、原A4及恢复场的实值；完整p6与notch是否复现。
2. **内存究竟省在哪里、多少？** 原full p4、旧宏块历史、新cell exact、新cell BLR的同scope表；包含缓存/所有因子/装配及恢复；无公平分母就只报实值。
3. **BLR有没有额外价值？** 相对新cell exact的压缩条目与RSS、单次完整逆质量、实际采用哪个backend；失败不抹去准确路线。
4. **后续保留什么？** 准确路线通过且实测节省则保留为显式中间层实现；BLR仅在额外收益与完整资格成立时保留；准确却不省内存则标PASS_NUMERICAL_ONLY_NO_MEMORY_GAIN，不再把本批叫容量突破。全部保持固定13.5 nm资格，不自动启动5 nm/0.7 nm。

本review的最终判断是“授权这项有依据的准确实现对照”，不是预先给数值／资源PASS。只写rows下降、局部测试通过、factor被创建或三份RHS结束，不足以完成已获准的整批交付。

## 10. 主要来源与验证边界

仓库事实以本文第0节base固定：最新response/decision，Task035b的summary与`high_p_memory_anatomy.md`，现有assembly-time、fullspace_p4_reference、BAL_H及DtN模块。上述历史GiB数据只说明可复用机制，不证明当前p4可减少一半。

- [DOLFINx 0.10静态凝聚示例](https://docs.fenicsproject.org/dolfinx/v0.10.0.post1/python/demos/demo_static-condensation.html)：单元核中消元、装配凝聚系统的官方示例；物理是线弹性，不作为本Maxwell的收敛证明。
- [PETSc MATSOLVERMUMPS](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)：公开LU/BLR与控制接口；在线新版本不覆盖本机5.6.2已验证能力。

第3节一般端口消元与恢复式来自直接分块代数；reference仅用于评价，不进入factor/PC/初值。文档需fenced math、表格/链接静态检查及本地预览，GitHub rendered view可用时回读核验；访问受限须明示，不能声称网页视觉已通过。ChatGPT本轮不执行项目PDE、不修改solver和账本，只新增此review。
