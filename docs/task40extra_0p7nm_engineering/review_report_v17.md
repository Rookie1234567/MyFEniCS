# Review V17：关闭恢复回退、解除稀疏构建尺度限制并验证 Ny=8

## 0. 主审裁决

**V16 的 Gx560 新构建路线取得了真实完整解，数值结果可信；它只小幅缩短了 worker 时间，尚未降低可用于容量判断的同时内存，也没有推进到新的 E1 求解。下一轮保持 V15 数值合同，直接复用已存在的局部恢复精化，完成真正按行分块的稀疏构建，并把 p6、同几何 Ny=8 的原生映射组件列为必做项。E1 按真实资源条件继续，不能把一个保存数组上的局部恢复失败当作全部工作的前置门。**

这份报告接续已正式回应的 V16，不重做 V15，也不把报告中的建议写成已取得的新求解结果。最终目标保持：真空波长 **0.7 nm**，**50×25×140 nm**，真实非可分三维材料/几何，**complex128 Nédélec H(curl)**，x/y Floquet 与 z Fourier-DtN；约 **2,000,000,000,000 B 物理内存**须留系统余量，任务零 swap；单场必要构建、求解、恢复、输出及检查全过程 **不超过 172800 s**。

| 审阅对象 | V17 裁决 | 含义 |
|---|---|---|
| V16 Gx560 完整离散解 | pass_with_qualifications | A6、物理输出、与 V15 保存场比较通过；原尺寸精度和完整成本仍未资格化 |
| V16 构建优化 | 保留显式研究路线 | worker 时间改善约 5.54%；cgroup 峰值上升，不授予容量改善结论 |
| V16 E1 | NOT_ADMITTED_PREBUILD | 本轮没有进入网格、symbolic、numeric 或 KSP；不得写成一次新资源停止或不收敛 |
| V16 32,060 模式组件 | COMPONENT_GATE_FAIL 保留 | 向量读回及端口方程子门通过，两个 known-state 恢复前向门失败 |
| V11 保存数组精化 | 保留历史合格候选 | 同一 S2 数组上有已通过的局部精化；本轮应核对并复用，不能复制历史 PASS 给新调用 |
| 一般 Ny、目标索引/因子增长、2 TB / 48 h | NOT_QUALIFIED | 有明确待验证接口与资源缺口，不等于已证明目标不可计算 |
| 后续执行 | 按第 8 节连续推进 | 主控收到用户转交本报告后续作；本次 ChatGPT 审阅不启动计算 |
| master / ordinary default | 不批准合并或改变 | 保持同一执行分支及显式 opt-in |

下一轮应交付新的**构建能力和映射证据**，而不只增加测试通过数，或再次报告同一个 Gx560 三步收敛。若生产构建代码确有相关改变，进行一场必要的 Gx560 完整资格运行；没有影响求解的改变则复用 V16 场，不为 review 换序号重算 PDE。

## 1. 本次审阅的固定身份与范围

| 项目 | 固定值 |
|---|---|
| repository | Rookie1234567/MyFEniCS |
| execution branch | task40extra_0p7nm_engineering |
| 审阅 base HEAD | efe79a1f9bdb33dd1694ea737139d807172b1f31 |
| base 提交时间 | 2026-10-07T23:18:07Z |
| base 提交说明 | Task40 V16: close Gx560 build comparison and target component evidence |
| 上一份 review 提交 | 0ddc939b093895bdf426bfd2d98852edc89d3f6a |
| Gx560 V16 实际数值源码 | 54b98a871632a1eef1c34e3542788f5859ee255c |
| P4 helper 源码 HEAD | 3fffbddc3ebdf597cf25eed5600095d09f24d918 |
| canonical worktree | /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering |
| 已记录 ABI | WSL2；PETSc 3.25.6 complex128 / int32；MPICH 5.0.1；MPI1、数学线程1 |
| 本报告 | docs/task40extra_0p7nm_engineering/review_report_v17.md |
| 下一轮回应 | response_v17.md |

本次读取了最新 response、四份 V16 compact、run index、summary/test summary、V11 局部恢复记录、V16 以来五次提交的改动及相关数值源码。四份 compact 和 response/summary/test summary 的远程内容 SHA-256 与 run index 登记一致。该核对只证明这些文档的内容身份，不能代替本机 ignored 原始数组、进程树或现场资源检查。

数值证据应继续绑定实际 source SHA。P4 helper 在 Gx560 之后加入，且没有接入该次正式 Gx560 路线；不能用收口 HEAD 替代 Gx560 的数值源码，也不能称 Gx560 已验证 P4 新 helper。[S1]、[S2]、[S3]、[S4]

执行仍由既有主控与执行者完成：执行者实现、测试、运行，不 commit/push；主控审查、冻结数值源码并集中提交推送。只用上述 worktree 和执行分支，不另建聊天、项目、checkout/worktree，不启用 collaboration subagents 或定时任务，不 SSH、不操作工作站、dot、Task042 或其他项目，不合并 master。最新 review 的执行顺序覆盖旧导航中的“本轮为 V10”；历史记录不修改。

## 2. 已取得的结果，及其工程含义

### 2.1 Gx560 的数值通过是实质进展

Gx560 为 560 cells（10×4×14）、p6 target、340 retained modes，使用四 q p6 参考预条件器。预条件器提供外层迭代修正，真实求解对象仍是带三维缺口的原 Maxwell 算子。

| 指标 | V16 实际结果 | 验收或解释 |
|---|---:|---|
| 外层迭代 | 3 | 与 V15 相同；不是全过程成本 |
| 释放参考对象后原 A6 | 4.70443000240316e-9 | ≤1e-6 |
| 独立 native A6 witness | 4.704309875855315e-9 | ≤1e-6 |
| target condensed/native identity | 5.592504268634092e-11 | 原 1e-10 门保留 |
| R | 0.0761240670863029 | official |
| T | 0.9057692200997514 | official |
| A_balance / A_volume | 0.018106712813945713 / 0.01810671257728056 | 吸收一致性约 2.36665e-10 |
| R00_s / R00_p | 0.0761235935066231 / 7.341919406880154e-22 | 极化分别报告 |
| V16/V15 E、H、scaled curl 最大相对 L2 差 | 1.6316487264432077e-12 | ≤1e-4；共同子单元积分 |
| 全部 340 模式功率最大绝对差 | 2.368105711525459e-13 | ≤1e-6 |
| 冻结 11 个显著模式复振幅最大相对差 | 1.2580188762004668e-10 | ≤1e-4；不拟合相位 |
| 输出 checker | PASS | 与完整 worker 时间是否重叠应单独说明 |

物理、网格轴、几何、MPC、carrier 和有序模式身份一致；两份输入文件字节 SHA 不同。这是同一离散问题的实现一致性，不是 y/z 网格收敛，也不是原尺寸精度。[S2]

V16 compact 未汇总每次实际 PC 的所有 V15 准入最大值、旧 strict FAIL 数及初始探针明细。下一轮从已有 events/receipts 提取这些字段即可；缺失项保持 unknown，不能挪用 V15 数字，也不能为补表重跑 PDE。三次 PC 均没有增广修正，因此仍不能把此生产轨迹当作“修正分支已被实际调用”的证据。[S2]、[S4]

### 2.2 速度有所改善，同时内存尚未改善

以下都是对应记录的 worker 时间或明确子阶段。旧版本不是同一时刻的受控缓存对照，比例是观察值比较。

| 指标 | 历史 p6 target + p4 PC | V15 p6 reference PC | V16 新构建 |
|---|---:|---:|---:|
| worker workflow | 1925.863 s | 2407.572 s | 2274.267 s |
| 同时树 RSS 峰 | 5.256 GB | 10.295 GB | 10.205 GB |
| cgroup 峰 | 本表未重列 | 11.675 GB | 11.908 GB |
| 外层步数 | 171 | 3 | 3 |
| 原 A6 | 9.73348e-7 | 4.70440e-9 | 4.70443e-9 |

V16 相对 V15 少 **133.305 s（5.54%）**，约 **37.90 min**；相对历史 p6 target+p4 PC 仍长 **18.09%**，树 RSS 约 **1.94 倍**。p4 是历史预条件器阶数，不能把该历史 p6 场降格成 p4 target。[S2]、[S4]、[S5]

| V15 → V16 构建/内存项 | 记录变化 | 主审解释 |
|---|---|---|
| 两 sector 装配父计时 | 422.540 → 408.214 s | 只减少约 3.39% |
| sparse accumulation 子计时 | 275.837 → 16.777 s | 该子阶段减少约 93.92%，但不代表全过程同幅改善 |
| V16 新 pattern construction | 110.582 s | 父子时间不得重复加和；其余父时间不能强行归因 |
| 四 q stored NNZ | 61,991,755 → 62,024,788 | 增加 33,033；V16 保留精确零结构槽，不等于改变物理 |
| 四 q MUMPS allocated 上界合计 | 4.645 → 4.692 GB | 增加 47 MB，不是节省 |
| 树 RSS | −90,046,464 B | 约 −0.875% |
| cgroup 峰 | +233,033,728 B | 约 +2.00%；不能认定同时内存下降 |

V16 KSP-only 为 148.350 s，仅占 worker 约 **6.52%**。非 KSP 差额约 2125.918 s，尚不能全部称作装配。完整 PC 父调用为 67.116 / 17.492 / 9.798 s，合计约 94.407 s，已包含内部 native evaluation；四 q numeric 子阶段合计 18.651 s 也不是全部 setup。下一项优化依据应来自最大的实际父阶段与同时对象，不继续仅围绕迭代步数。[S3]、[S4]

B0 构建组件本身为 candidate 94.430 s、legacy 65.417 s；组件通过不意味着新构建在所有尺寸都更快。保留这个负性能观察，不反复择优重跑。[S2]

### 2.3 当前还不能给出完整单场时间

2274.267 s 是 worker monotonic；2526.263 s 是保守 realtime budget interval。外部必要 checker 和保存场比较未全部包含，完整单场关键路径仍为 unknown。29.976 s 离线比较、0.616 s C1 复核不能任意拼成“完整总时间”。现场须区分外部必需检查与一次性的版本资格比较，按实际依赖和起止时间归属。

任务树/cgroup swap 为 0。WSL 全局记录有 52 页 swap-in、0 页 swap-out，归属未知；不能把全局计数解释为任务用了 swap，也不能宣称宿主全程零 swap。[S4]

## 3. 先关闭已保存局部恢复的回退，不再把它扩大为整轮阻塞

### 3.1 已有证据支持什么

V16 P4 top/bottom 的 known-state 前向误差分别为：

- 2.202932653970648e-11；
- 2.42442721473547e-11。

原门为 **1e-11**，故当前两项确实失败。局部方程约 9.73e-16 / 1.11e-15 及端口方程约 1.5e-16 的通过不能覆盖前向误差失败。

这两个值与 Review V11 记录的 V10 直接 LU 负结果相同。V11 后续在**同一 S2 数组 SHA** `d656ff94510836a0592ff36f3579c2c46cbfbd5ae77695228488b5cc25024273` 上，将恢复前向差降至 5.3524732442130614e-14 / 5.143310794873929e-14，并通过原/约化局部及端口方程。当前 V16 回放没有调用精化。源码中仍有 `task40_w1_local_probe.solve_local_rhs`，原 `stream_boundary_correction` 已用它处理多个局部 RHS。[S1]、[S6]、[S7]、[S8]

**主审判断：存在很强的“回放退回未精化路径”证据，应先核对并复用已有实现；尚未逐项重放本机数组，不能宣布全部差异已唯一归因为舍入或接线。** 同一数组哈希不自动证明运行中的 RHS 表达式、LU、dtype、方向和坐标接口完全一致。

### 3.2 明确授权的修复步骤

1. 在现有 S2/S5 保存数组上核对 Vii、Vit、fi、trace、Bi-alpha、known state、LU/pivots、原始/平面 gauge、面法向、坐标原点及有序模式。逐数组列 shape/dtype/hash。历史代表面的坐标与完整目标解析坐标之间若有变换，必须保留其已有映射，不能靠移点对齐。
2. 先复现并保留 V16 直接 LU 的负结果；再对**相同已保存 complex128 方程及 RHS**调用已有 `solve_local_rhs`。复用同一局部因子，不重装体积、不重建全局因子、不重解 PDE。
3. 沿已有实现最多 **3 次额外局部残差修正**，逐次保留残差、前向差、是否接受、停止原因和成本。修正选择只能依赖原方程残差改善；known state 只作验收，不参与构造“正确答案”。
4. 原始 Vii 必须参与残差检查，不能用 LU 重构矩阵的自洽作用替代。更宽累加仅沿既有局部残差实现，并记录实际 epsilon、mantissa 和 dtype；输入、解和生产 FE 仍为 complex128。LAPACK 同类方法的用途也是改善线性系统解并估计误差，不赋予它自动通过资格。[P1]
5. 保持 **前向 1e-11、原/约化方程 1e-10**。读取保存输出后的独立 checker 必须重新计算这两类结论；旧直接 LU FAIL 与新 refined candidate 分别记录。
6. 若仍超限，分离“同一舍入系统的解误差”与“制造 RHS 相对理想已知态的误差”，沿原始矩阵做有判别力的局部检查；不增加无依据 floor，不改门槛，不原样反复重试。该组件保持 FAIL，继续独立的 Ny/CSR/资源工作。

这三次**局部恢复**修正不改变 V15 **每次 PC 至多一次完整增广修正**的限制。不得为了修一个保存块给所有 production cell 无条件增加三次精化，或为此保留全体每-cell raw Vii 副本。若真正采用到共享 Hhat/恢复代码，必须给出新增 raw-matrix owner、调用次数、成本及受影响入口测试。

### 3.3 P4 组件还缺少的独立性

V16 两面确实覆盖了 top 0–16029、bottom 16030–32059 的模式索引，使用完整 882 行（450 interior、432 trace）、q60、mode batch 16、point chunk 64。约 8.005 s 是该组件范围时间；树 RSS 约 0.770 GB、cgroup 约 0.844 GB。它没有生成 32,060² 方阵。[S11]、[S12]

但这里的 **32,060 是向量长度，不是 32,060 个独立 RHS 的全矩阵验证**。现有 P4 是两个代表面上的向量作用，不能推广为全边界、全目标 q 矩阵或算子范数资格。[S11]

D 坐标读回仍调用 production gauge helper，`same_factor_XiB_comparison=0` 也只是同一因子路径的一致性。下一轮用现有独立 full-row quadrature / analytic moment reference，重算 raw D 的方向、符号、归一化和原/约化端口方程，避免 checker 与被检对象共用同一转换作为唯一依据。覆盖全部已有模式及完整 882 行；有限个 deterministic 非零 trace/interior/alpha 探针只能按实际探针范围表述，不冒称任意 RHS 已证。

run_01 的近零 interior 分母已按完整 882 项尺度修正：Balpha 的 top/bottom 全尺度差为 1.13e-13 / 1.04e-14，interior 差相对全尺度约 1e-15。保留原 subset-relative 诊断与独立前向 FAIL，不能把“分母修正已通过”扩写成整个 P4 通过。

可在这一有限组件中审计哪些端口耦合由实际 H(curl) 切向迹和实体拓扑严格限制。必须结合真实 Basix dof/方向映射、Piola 变换和两面全部行给出证明；**不能因 Bi-alpha 很小就数值截零，也不能先用未资格化的 84 行替代 882 行检查**。即使证明某些局部项严格为零，也不能推断全局端口 Schur 或因子不再有 mode² 耦合。

## 4. 当前最明确的尺度阻塞：全 shape bitset 必须退出必要构建路径

### 4.1 V16 的“有界”仍有尺寸上限

`_assemble_v16_bitset_pattern` 给一个 q block 分配 `rows × ceil(columns/8)` 字节的全 shape 位图，再加 32 MiB reserve。纯方形位图在 256 MiB staging 合同下的推导边界约 **43,344 行**，实际还受 support、解码和 CSR 临时对象限制。Gx560 最大 q 只有 28,576 行，E1 历史 q 约 38,508 行，因此小案例通过不能证明目标可扩展。[S3]、[S9]

目标的 3,126,332 trace-plus-port 派生总行数不能直接当作某一个 q 的 shape。每 q 行数须从真实模式分配和原生映射得到；但 current builder 的限制取决于每个 q 的矩形行列积，不能通过“目标总行数能放入 int32”消除。

V16 的投影和数值累加已分块，Hhat contribution 也可按列流式生成；这些改进应保留。问题是稀疏结构仍对全部行列建位图，属于**稀疏构建的规模限制**，不是 Maxwell 模型或目标迭代不收敛。

### 4.2 下一版构建的必要设计

稀疏结构只说明“哪些行列位置可能有项”。下一版应按输出行分块，先数清每行的唯一列位置，再写入排序后的 CSR 索引和数值；全程不需要保存一个全行列方格。

- 使用 row tile 与实际 support 的压缩索引/区间描述，或等价的有界 sorted merge。临时预算仍沿现有 **256 MiB total staging**，最终 CSR、已有 FE 对象和所有其他 live owner 另受整树资源门约束，不能藏到预算之外。
- 建立贡献到输出行块的关系，避免每个 tile 都重新扫描全部贡献、重新生成所有 FE 数值，或反复构造全部 Hhat。分别记录 layout 遍历数、局部数值生成次数、projection 次数、flush/merge 和磁盘 I/O。
- 不保留全模式 COO 列表、全局 Python row sets 或全 shape 位图。对端口密集 support 可保留有身份的结构描述；最终真实 dense coupling 所需 NNZ 不得省略。
- prefix sums、rows、columns、NNZ、indptr[-1]、中间偏移和字节乘法先用 Python 整数或经检查的宽计数完成，再与当前 PETSc.IntType 上限比较，最后转换；不得先 int32 溢出再检查。
- 合并重复项必须保留原矩阵。允许评估精确零的显式整理，但不得按幅值阈值删除小项。V16 比 V15 仅多 33,033 stored slots，不能预先把精确零清理包装成数 GB 的内存突破。
- 使用已有参数化入口；不要因 review 序号继续复制整套 runner/solver。确需新增 strategy/scope 时集中注册，并在真实当前 window 下测试 allowlist、dispatch、ABI 和 saved-output route，避免完成长构建后才发现普通注册错误。

### 4.3 完整 off-diagonal 检查可以保留而减少存活对象

目前每个 sector 同时形成 00、01、10、11 四个 CSR，检查两个 off-diagonal block 后只返回 diagonal q matrices。可用按行完整累加后的 tile 计算 off-diagonal Frobenius norm，并保存需要的比较/见证，在检查结束后释放该 tile，而不长期保留两个完整 off-diagonal CSR。

该改法只有在**每个 tile 已汇集全部贡献**后才能求范数，再按互不重叠行块累积平方和；不能把各贡献范数相加，也不能只抽样几个向量来替代原完整 off-diagonal 门。原 mapping **1e-12**、operator/off-diagonal **1e-11** 保持。B0 小组件应比较全部四块的完整数值与作用，包括旧零/近零 off-diagonal；可在小组件中保留完整矩阵作 oracle。[S9]

因子化前仍须完成所有 q 的正式矩阵和资源准入。不能把“某一 q 的峰”当作全部四 q 因子同时存在的峰。

### 4.4 验证要越过旧限制，且区分算法与物理证据

先做相关软件测试，再做一个真实 B0 p6 四块构建组件。至少增加一个逻辑 shape 超过旧 43,344 行限制、具有已知稀疏结构的边界测试，验证没有全 shape 分配和 int32 提前转换；它只证明 builder 能处理该 shape，**不是目标 FE 容量通过**。

随后将 builder 接到真实目标结构计数/有界结构块，记录其实际 q shape、support 来源、完整覆盖和最大 staging。若新的生产构建改变了 Gx560 路线，才执行一次必要 Gx560 完整求解与 V16 保存场比较。纯保存后处理修复、计时归属修正或文档更新不触发这场 PDE。

## 5. 一般 Ny 的下一步必须产生真实组件结果

### 5.1 先给出可检验的推导，不能只改常数

当前 `Task40V10FullLayout`、`TwoCellNativeTransport`、branch coordinates、profile 和 all-q 检查多处固定 global Ny=4、local Ny=2。V16 的 Ny=8 为 NOT_RUN。[S11]、[S9]、[S10]

若下一组件**继续采用两个相邻 y 单元作为局部窗**，沿现有 real-Bloch（单位模 Floquet 相位）合同，设全局有 Ny 个等宽、可平移匹配的参考单元，局部窗长为 ell=2，则 K=Ny/ell 是局部窗的平移副本数。Ny=8 时这个候选给出 **K=4 个 twist，每个 twist 2 个局部分支，共 8 个 global q**；不是 K=8。以下是这个候选的数学推导，尚非原生 FE 实测：

```math
N_y=K\ell,\qquad \theta=k_yL_y,\qquad
\eta_b=\exp\!\left(\frac{\mathrm{i}(\theta+2\pi b)}{N_y}\right),\qquad
\tau_b=\eta_b^{\ell},\qquad \tau_b^K=\exp(\mathrm{i}\theta).
```

```math
(F_bx)_s=\frac{1}{\sqrt K}\sum_{r=0}^{K-1}\overline{\tau_b}^{\,r}x_{s+r\ell},
\qquad
(L_by)_{s+r\ell}=\frac{\tau_b^{\,r}}{\sqrt K}y_s,
\qquad q=b+jK.
```

其中 b=0,…,K−1，s、j=0,…,ell−1。这些表达式只描述 canonical 坐标中的 fold/lift；native primal/dual 还必须通过实际实体方向变换。H、RHS、alpha 的尺度须结合真实局部/全局端口面积、规范与 gauge 单独推导，不能把全部 2 替换为 K。等宽/可平移前提若不成立，应报告不适用，不能移动 target 缺口或默改网格来凑周期性。

### 5.2 本轮必做的 p6、Ny=8 小组件

优先沿已有 B0 小物理几何，固定 x/z、材料、入射、模式清单和未移动的四分之一缺口边界，只把 y 网格从 4 细化到 8；明确该组件与 Ny=4 基线的身份关系。直接使用实际 Basix/dofmap、MPC 和方向数据，覆盖：

| 必须输出的证据 | 接受条件 |
|---|---|
| 实际 Ng/local ell/K/twist/q inventory | 所有数量由实际构造读回；无重复或遗漏 q |
| 全部 interior/edge/face 的 native ↔ canonical 映射 | 全覆盖，保留原 1e-12 mapping 门 |
| primal lift、dual fold 与工作/伴随恒等式 | 原尺度与原门；正反方向分别验证 |
| 完整 retained mode 到 sector/q 分配 | 全部有序 keys 一次且仅一次覆盖；实际 K 归一化 |
| 原生 regular-reference action 与组合 action | 原 operator 1e-11 门；完整 off-diagonal 检查按可负担的小组件执行 |
| H、RHS、alpha、平面 gauge/入射扣除 | 独立归一化恒等式；不能由同一转换自证 |
| 资源与源码 | component wall、树/cgroup 峰、task swap、source/input/ABI/数组 hashes |

除实际基线相位外，必要的纯映射测试应覆盖非零 Bloch 相位，以免 phi0 的特殊对称性掩盖方向错误。Basix 的 entity_dofs、entity_closure_dofs 和 entity transformations 是相关原生接口，但官方文档不是当前运行 ABI 的资格回执。[P3]

本组件不启动 Ny=8 正式 target KSP，不自动扩展 V15 四 q PC 合同。将来正式扩展时，总因子数、每 PC q solves、允许的增广修正调用数和同时内存必须随实际 q inventory 一起资格化。Ny=8 小组件成功也不等于所有非均匀 Ny、所有几何或原尺寸 y 精度通过。

## 6. E1：保留目标，先证明资源缺口确已缩小

| 事项 | V16 / 历史记录 | 解释 |
|---|---:|---|
| 原 E1 | 760 cells；10×4×19；588 retained modes | 136 传播 + 452 倏逝；不改成 AUTO 136 |
| V16 现场 dynamic launch cap | 13,432,152,064 B | 仅该次现场值 |
| 沿用的保守总投影 | 19,192,602,560 B | 不是 V16 新 E1 实测峰 |
| 总投影超 cap | 5,760,450,496 B | 约 5.76 GB，足以保持 prebuild HELD |
| 四 q 未来 numeric 估算 | 6,530,000,000 B | 历史 INFOG16/17 派生估算，不是实际因子分配 |
| V16 post-symbolic Gate | NOT_RUN/UNKNOWN | 没有开始 E1 构建 |
| 历史 E1 p6 target+p4 PC | A6 9.78167e-7；worker 4580.375 s | 保存场继续复用，不是新参考 PC 的成绩 |

[S1]、[S3]、[S4]、[S5]

V16 的 identity cache 每套只缓存一个 450×450 float64 单位阵，单对象 1,620,000 B；target 与两套 local sector 独立持有。它不是新的全局共享 transform/Schur/LU/recovery bank。当前账目没有证明它带来数 GB 节省。[S3]

按历史 E1 NNZ 推导的一份四 q CSR 约 1.699 GB；即使能够去掉一整份真实重复拷贝，仍不能单独解释 5.76 GB 缺口已关闭。source/canonical CSR 可能是 alias，不能先算作两份；PETSc、MUMPS workspace 与 local/native recovery 的必需对象也不能靠删除检查解除。[S13]

下一轮从已保存 Gx560/E1 库存与新 builder 组件提取**实际独立 backing、持有者、最后使用阶段、释放证据**，更新 E1 保守投影。旧 19.193 GB 不应被永久当作新实现的精确需求，也不能无依据打折。只用有身份的当前构建增量、实际释放和保守未知项修订，分别报告：

```math
M_{\mathrm{live}}+\Delta M_{\mathrm{needed}}+R_{\mathrm{system}}
\le M_{\mathrm{effective\ cap}},
\qquad
\Delta M_{\mathrm{needed}}+R_{\mathrm{system}}
\le M_{\mathrm{available}}.
```

这些不等式按现场值和原 watchdog 语义判断，live、未来增量与余量各自只计一次；若某一 cap 已明确扣过同一项余量，须说明口径，不能重复扣款或凭空释放预算。预构建预测通过不等于 post-symbolic 通过；all-q symbolic 后再次据实际估计判断全部 numeric、startup、KSP 和输出余量。

若有可信资源和剩余完整时间预算，**直接进入原 E1 必要流程，完成 all-q symbolic → numeric → startup → KSP → 恢复/输出/checker**，不用再把 Gx784 设成机械门。若缺口仍不能解释性关闭，不盲目重新构建 E1；继续第 5、7 节。不得提高实际物理 cap、用 swap/OOC 绕过、减少模式或削弱缺口。原 p6 Gx560/Gx784/E1 与 E2 保存场的身份复用继续有效。

## 7. 把 2 TB / 48 h 的未知项变成可计算的结构与成本证据

### 7.1 目标结构计数可以先于目标数值因子完成

现有候选为 272×4×14=15,232 cells；full-storage 10,228,620、periodic-independent 9,948,672、interior 6,854,400、trace-plus-AUTO-port 3,126,332，均为派生计数。32,060 AUTO 传播模式有冻结 manifest，并不包含最终所需倏逝截断的资格。[S11]、[S4]

原解析几何固定 x 分界 0/16.5/25/33.5/50 nm、y 缺口 6.25/18.75 nm、z 分界 −10/0/40/80/120/130 nm；现有候选 x 各段 78/58/58/78、y=4、z 各段 1/4/4/4/1。它只是候选计数，不授予精度。

本轮授权在本机资源门内做**必要拓扑、原生 support 与索引分块计数**，不建原尺寸全局数值算子、不建原尺寸 numeric factor、不启动原尺寸 PDE：

- 将候选节点 recipe、材料/缺口标签、MPC/方向关系与局部 support 来源绑定；能完成实际原生结构时记录实际身份。
- 逐 q 输出 rows/columns、端口数、精确 structural NNZ 或有推导证明的上下界、indptr 终值/上界、最大中间偏移、CSR 字节及边界/体积/端口项分类。
- 可以利用经原生校准的重复 stencil 和压缩区间遍历完整候选拓扑；仅外推小模型 NNZ/cell 不是精确结构计数。若只得到界，必须标 derived bound，不能写 measured NNZ。
- 统计 local geometry/material/orientation class 的真实或可证明上界；Gx560 的 55 类不能直接复用为目标类数。
- 若完整拓扑本身超本机 cap，保留已完成的最大真实片段与未覆盖量，不改称全目标完成；继续输出经证明的界及需要更大平台才能确认的项目。

目标索引若超当前 int32，先产出具体超限字段和 64 位 ABI 迁移清单。PETSc 索引宽度由构建配置决定，将 NumPy 数组改为 int64 不会改变当前 PETSc ABI。[P2] 本轮不重装现有环境、不远程修改工作站。

### 7.2 端口库存必须区分局部形状、最终结构和同时峰值

单个 32,060² complex128 方阵的 payload 为 **16,445,497,600 B**；这不是全流程峰值。P4 helper 没分配此方阵，仍不证明所有 production path 都已消除此类对象。

每面 16,030 模式：450×M_face 的 Bi/XiB 或 M_face×450 的 Di 单份为 115,416,000 B；432×M_face 的 Bt/Dt 为 110,799,360 B；完整 882 行 coupling 单份为 226,215,360 B。这些是形状派生量，不是已分配对象。[S1]、[S4]

逐项追踪实际 H/Hhat、C/D/XiB、q port-port block、PETSc CSR 与 factor 的副本和生命周期。即使 Hhat 中间量按向量或列块计算，最终稀疏图中的端口耦合及消元造成的因子填充仍可能稠密；不能从原 H 对角直接得出 mode² 问题消失。

### 7.3 精度和运行成本是两条都必须完成的证据链

原尺寸名义 hy=6.25 nm、hz 常见 10 nm 不能因为 λ=0.7 nm 就只按真空 k0h 判死，也不能凭 p6、小 A6、能量闭合判准。斜入射分量、三维散射和倏逝近场不同，须用固定物理几何的 x/y/z 方向误差和模式截断比较来选择最终网格。

下一轮将现有 x 对照、未来 Ny=8 的固定几何 y 对照、保持分层界面的 z 对照、传播/倏逝 mode 扩展列出准确输入和唯一变量。这里首先完成一般 Ny 的映射资格；**不以 Ny 小组件冒充 y 收敛，不额外启动一组未有预算的精度 PDE 扫描**。

完整单场预算至少包含必要 JIT/准备、volume/local condensation、全部 q 构建与因子、startup/native 检查、KSP、恢复、输出、释放与最终必需 checker。四 q MUMPS 当前 allocated/used 上界、raw INFOG9、simultaneous factors 与未知 factor-entry 数分开。没有本版本可靠解码则 INFOG9 继续 raw/unknown。

需要报告一个完整起止区间或经依赖核对的关键路径。父子时间不叠加、并行阶段不重复计时，WSL/UTC/monotonic 差异按原保守计费规则处理。cold 构建、身份复用的 build/write/read/recovery 成本、版本资格测试和开发 campaign charge 分列。历史缺失计时不通过重跑 PDE 补齐；新必要运行增加直接测量。

最终容量判断使用实际物理预算减系统/其他必要占用，再比较全过程同时峰值。树 RSS 与 cgroup 不相加，单对象 payload 与各阶段历史峰不冒充同时内存。小模型时间按 cells 或 mode 数线性外推只能列为假设场景，不能承诺 2 TB / 48 h。

## 8. 连续执行顺序、普通 bug 和固定窗口

| 阶段 | 必须推进的工作 | 依赖及继续条件 |
|---|---|---|
| P0 | 核对当前 HEAD/工作树/进程/旧窗口终态；复用 V16 科学数据，抽取已有计时、PC 门与 E1 库存 | 不重建历史 PDE；缺失字段原样保留 |
| P1 | 同一 S2/S5 保存数组重放已有局部精化，关闭或准确定位 P4 恢复门；补独立 raw D/端口读回 | 局部失败不阻断 P2/P3 |
| P2 | 完成 p6、同几何 Ny=8 原生映射及全模式组件 | 本轮必做尝试；在大求解前安排，不再作为末尾可选清单 |
| P3 | 实现并验证真正按行分块的 CSR；保留完整四块/off-diagonal 门，补结构与 owner 计数 | 相关软件/真实 B0 组件通过后，主控冻结将用于正式求解的源码 |
| P4 | 原目标拓扑/support/index 分块计数；端口生产路径与 simultaneous owner 账；更新 E1 投影 | 不依赖 E1 容量通过；不建原尺寸 numeric factor/PDE |
| P5 | 按改动依赖做必要完整 anchor；有生产构建改变则一场 Gx560，安全时直接原 E1 | 保存有效场后，输出/checker bug 用保存场恢复；没有相关改变则复用旧场 |
| P6 | response_v17、四份 compact、summary/test summary、run index、项目账本；主控提交推送 | 数值失败、resource stop、not_run 和 unknown 分别保留 |

P2/P3/P4 的独立轻量工作可由既有主控安排顺序，但不新建执行者或并行 heavy case。若 P2 的通用映射改动影响已验证 Ny=4 生产入口，先完成相关 B0 必要完整 anchor；若 Ny=8 完全隔离为组件，不因它重跑 Ny=4 PDE。涉及 target 作用、实际恢复语义或物理输出改变时按已有数值影响规则选择必要 anchor，不能用“只改 helper”逃避真实入口资格。

在授权窗口内，普通 NameError、维数断言、scope/ABI 注册、序列化、checker、输出或可定位 owner 生命周期错误，**先修复、做最小相关验证、由主控冻结后继续**，不在一次普通 bug 后停为 WAITING_FOR_REVIEW。先查真实调用链，防止多个 allowlist 漏项逐次暴露；不因每个小修复重跑全库/全 PDE。

同一根因重复失败时换有判别力的局部检查，不能原样第三次重跑。NaN/Inf、真实身份/数值/物理失败、task swap、实际资源不足或窗口终态停止受影响路径，保留证据并继续不依赖它的工作。不能把这些失败叫作无害 bug，也不能抬门槛。

主控状态询问不是 kill 指令；只有明确用户停止或真实 watchdog 条件才终止完整进程组。求解期间不热改冻结源码。执行者不因历史凭据或推送回执启动自己的 commit/push。

### 固定窗口

旧窗口 T0=2026-10-06T23:21:33.326800586Z，deadline=2026-10-07T23:21:33.326800586Z，SHA-256 为 `226f64427d3e7c413e1b65992f5071041283499adaa06e4493d1865aae78d185`。V16 收口观察记 remaining_numerical_seconds=0、累计 charge=85892.89690395721 s。[S4]

**主控收到用户转交本报告后，先核对旧窗口确已终态且无重叠任务，再建立一个独立、最长 24 h 的 V17 工程窗口，预留 600 s 收口。** 不复活或刷新旧窗口，不清零历史费用；新窗口也不能因提交、bug 或重启反复刷新。新旧窗口、monotonic/realtime 与预算扣款分开记录。窗口结束后保全结果、清场并收口；本次 ChatGPT 不创建或启动该窗口。

开发 24 h 窗口与最终单场 48 h 生产目标不同。窗口内允许必要实施与修复，不授予新主机、swap 或物理合同例外。

## 9. 不变的真实数值、物理与模式验收

| 项目 | 保持的要求 |
|---|---|
| reference PC | NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15；保留旧 strict 检查及其 FAIL |
| actual per-q MatSolve / native 消元 FE / 完整增广 FE / 非抵消预算 | 分别满足其原 1e-8 条件；按原公式与尺度，不通过相消掩盖端口误差 |
| 初始 factor probe | strict 1e-10 |
| alpha closure | 1e-9，原尺度及冻结尺度均保留 |
| 完整增广修正 | 每次 PC 至多一次；当前四 q 最多额外四次 q MatSolve |
| 原 target A6 / 释放后 A6 | ≤1e-6；原 target identity 1e-10 |
| 能量闭合与体吸收一致性 | 原绝对 1e-5 门 |
| 同离散场/复模式比较 | FE L2、E/H/scaled curl、显著复模式 1e-4；R/T/A 绝对 1e-5；各模式功率绝对 1e-6；近零量另报绝对差，不拟合相位 |
| 结构/映射组件 | 原 mapping 1e-12、operator/off-diagonal 1e-11；局部恢复前向 1e-11、原/约化方程 1e-10 |
| solver/environment | 零初值；FGMRES restart=32、max_it=2048；MPI1、数学线程1、complex128 |
| 因子设置 | 既有 MUMPS 后端、排序、主元、BLR、OOC、线程；不作参数扫描 |
| 真实模型 | 不降 p6 target、不减少规定传播/倏逝模式、不改变材料损耗、缺口、Floquet 或 DtN 来制造通过 |

中间迭代的真实残差尚高于终态门是未收敛状态，按正常迭代规则继续；不能再次把 target KSP 未启动或中间未达终态门写成目标迭代不收敛。任何候选数值策略变化必须显式审阅，本报告没有新增放宽后的 PC 合同。

## 10. 交付物和下一次主审的判定

沿现有通用 runner 与核心模块实现，关键算法不只留在 ignored artifact-local driver。大型场、矩阵、factor、timeline 不进入 Git；只提交轻量证据及其路径/hash。建议维持四份 compact，避免平行权威扩散：

| 文件 | 必须能回答的问题 |
|---|---|
| review_v17_component_closure.json | S2 相同数组直接/精化/独立检查怎样变化？P4 raw D 独立性是否关闭？Ny=8 实际 K、q、映射和模式门是什么？ |
| review_v17_sparse_capacity.json | 是否消除全 shape 位图？真实 staging 与四块门是否通过？目标 q rows/NNZ/indptr 是 measured、derived bound 还是 unknown？ |
| review_v17_formal_results.json | 哪些是复用，哪些是必要新场？Gx/E1 的原 A6、物理、全部模式、每 PC 原合同及源码身份是什么？ |
| review_v17_cost_and_readiness.json | 完整单场时间是否已闭合？同时内存哪个阶段最大？E1 缺口减少了多少、依据是什么？目标剩余哪一项阻塞？ |

同步 response_v17、summary、test summary、run index、development_model_registry、development_progress。只对最终相关代码做必要 targeted/component Gate；昂贵回归按真实变更影响和仓库要求执行，不把不同 source 的 tests 相加，不虚报全仓 pytest/MPI4/Ruff/CI。

**本轮有价值的结束状态**是：保存恢复问题得到可复核的修复或具体归因；Ny=8 有真实原生组件结果；CSR 构建越过旧形状限制且保持原四块门；目标结构/索引库存新增可证明数据；有相关生产改变时取得必要完整场；E1 若仍未准入，给出与当前实现绑定的缺口及已完成的独立进展。只有更多报告、相同 HELD 数字或又一次未改变能力的 Gx560，不足以作为主要成果。

本次裁决为 **pass_with_qualifications，继续研究执行；原尺寸生产目标仍 NOT_QUALIFIED，不批准 master 合并**。本报告是审阅与后续执行文本，本次只新增该文档，没有运行 FE/PDE、修改数值源码或启动 Work/计算任务。远程内容、引用和 Markdown 结构需核验；GitHub 网页实际 rendered view 若受当前读取能力限制，应明确保留未验证状态，由既有主控补查，不以此重算科学任务。

## 证据入口

以下仓库链接固定到本次审阅 base，不随执行分支后续提交漂移。

[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/docs/task40extra_0p7nm_engineering/response_v16.md
[S2]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/docs/task40extra_0p7nm_engineering/outcomes/records/review_v16_formal_results.json
[S3]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/docs/task40extra_0p7nm_engineering/outcomes/records/review_v16_build_and_memory.json
[S4]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/docs/task40extra_0p7nm_engineering/outcomes/records/review_v16_cost_and_readiness.json
[S5]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/docs/task40extra_0p7nm_engineering/review_report_v16.md
[S6]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/docs/task40extra_0p7nm_engineering/outcomes/records/review_v11_local_recovery.json
[S7]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/docs/task40extra_0p7nm_engineering/review_report_v11.md
[S8]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/src/solvers/task40_w1_local_probe.py
[S9]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/src/solvers/task40_v10_p6_yorbit.py
[S10]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/src/solvers/task40_v10_p6_periodic_profile.py
[S11]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/docs/task40extra_0p7nm_engineering/outcomes/records/review_v16_target_components.json
[S12]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/src/solvers/p6_cell_condensed_action.py
[S13]: https://github.com/Rookie1234567/MyFEniCS/blob/efe79a1f9bdb33dd1694ea737139d807172b1f31/src/solvers/task40_v10_p6_mumps.py
[P1]: https://www.netlib.org/lapack/explore-html/d5/da4/group__gerfs_ga2aaa4e39caf445d7a9429942f60ed362.html
[P2]: https://petsc.org/release/manualpages/Sys/PetscInt/
[P3]: https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.finite_element.html
