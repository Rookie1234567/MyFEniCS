# Review V5：一个新增 x 网格、云端三层资格与原尺寸成本准入

## 0. 联合裁决与冻结身份

**接受 Response V4 的四角方向判断，主线下一步只增加 Gx784（14×4×14）一张网格，复用已有 Gx/F5；同时生成原尺寸真实 AUTO 清单和资源账。dot 的新入口可以在持久保存条件落实后进入 p6 组件和 p4 参考链，但紧凑周期分块全链仍需单独资格。当前不能批准原尺寸大规模求解。**

本轮优先得到一个新的精度结论和实际成本瓶颈，不重跑背景归因、Gx/Gz、历史 X/XZ/Y，不无条件展开 h/p/M 扫描。本报告正式回应已发布的 Response V4，保留 V1–V4 和全部负结果。

| 冻结项 | 本次远程核实 |
|---|---|
| 日期 | 2026-10-03 |
| 主线分支 / 审阅基准 | task40extra_0p7nm_engineering / ba7dec1d733bb5f4a0f775ae74b63730ed3c1205 |
| dot 分支 / 审阅基准 | task40extra_dot_parallel_cloud / eb5b0ecc1afe593f626b44a6038f7f26651b3317 |
| 主线最新正式回应 | [Response V4](response_v4.md)、[summary](outcomes/summary.md)、[运行索引](outcomes/records/run_index.json) |
| 当前权威 | [task](task.md)、[Review V4](review_report_v4.md)的未被本轮替代部分，以及本 V5 的下一轮范围；不创建平行补充任务书 |
| 本次改动 | 仅新增本报告到主线；不修改求解源码、dot、master，不启动计算 |
| 总体状态 | pass_with_qualifications；无 merge approval，无原尺寸运行许可 |

最终对象仍为**50×25×140 nm、λ=0.7 nm、完整三维**的规则光栅基线，保留未来非可分三维缺口的自由度、全部模式及内部场恢复能力。硬约束为**整机十进制 2,000,000,000,000 B、swap=0、完整必要流程 ≤172,800 s**。计时包括冷 JIT、构造/装配、全部分解、迭代、完整场恢复、规定输出与校验；缩小模型、组件和代数残差均不能替代原尺寸精度及资源验收。

| 对象 | 本轮准入裁决 | 可做工作的终点 |
|---|---|---|
| 主线下一精度实验 M1 | **GO：只新增 Gx784**；先按既有实际内存压力政策确认本机可运行 | 新网格与两已有场的固定口径比较；失败也完成分类后收口 |
| dot C1a / C1b | **有条件 GO**：实际持久保存位置、源码/环境身份及小任务资源门满足后，可直接开始，不必再等一轮文字审批 | p6 真实组件、p4 稠密端口参考链分别出 worker/checker/持久收据 |
| dot C1c 紧凑分块全链 | **允许有界接线与资格，不是现成 PASS**；须 C1b 提供新环境参考 | 同一个 p4/532 fixture 的紧凑两单元、全部 q、regular/notch 完整原方程对照 |
| 原尺寸 AUTO 清单 / 成本探针 | **清单与尺寸账立即 GO**；实际 JIT/端口投影成本探针待 C1 和参数化接线条件满足 | 完整有序模式下的有界端口/投影成本，不做原尺寸 factor/PDE |
| 原尺寸大规模完整求解 | **NO-GO / HELD** | 缺原尺寸精度、AUTO 接线/截断、真实填充、完整时间和后端证据；本轮不得升级规模 |

本次通过 GitHub 直接读取两分支树、增量源码、任务材料、历次 review/response 及已提交记录，并从接口标量独立复算比例和存储量。本次没有访问忽略目录中的完整场数组，也没有运行 FE/PETSc、pytest 或 PDE；本地命令执行工具未能启动。以下 measured 指对应历史收据，derived 指本报告的计算，not_run/unknown 不继承历史 PASS。

## 1. 主线：四角证据足以选择 x，但不足以宣布收敛

### 1.1 本轮接受什么

现有模型把三个方向均缩小为 7/135，包含非可分三维空气缺口；它不是沿 y 完全不变的规则光栅。p6 表示完整电场，准确 p4 作为迭代校正。p4 输入矩阵行数/非零项数不包含 LU 分解产生的额外非零项，不能代替因子成本。

| 已发布模型 | x×y×z 单元 | p6 完整存储自由度 | p4 界面 rows / NNZ | 原 A6 真残差，门槛 1e-6 | 同时进程树 RSS 峰值 B |
|---|---:|---:|---:|---:|---:|
| F3 / G00 | 6×4×14 = 336 | 229,680 | 29,332 / 11,293,034 | 7.5936104e-7 | 4,006,539,264 |
| Gx / G10 | 10×4×14 = 560 | 380,040 | 48,660 / 18,782,900 | 9.7334769e-7 | 5,255,675,904 |
| Gz / G01 | 6×4×22 = 528 | 359,904 | 45,460 / 17,879,806 | 9.7452954e-7 | 5,434,322,944 |
| F5 / G11 | 10×4×22 = 880 | 595,512 | 75,540 / 29,765,186 | 8.7353225e-7 | 7,754,170,368 |

四场任务 swap 为 0，PSS 未采样。Gx/Gz 全 workflow 分别约 1925.721/1917.757 s；F5 约 2448 s。它们是旧环境相应运行的成本，不是新 case 上限或原尺寸外推。

[四角接口包](outcomes/records/review_v4_four_corner_interface_v1.json)保留全部输入、坐标、材料、相位、模式、范数和源码身份。公共物理体积为 24.3966874968 nm³，精确轴并集为 12×4×28 个积分子块，每轴 7 点 Gauss，材料 tag 不匹配为 0。

| 量；本表数值均为无量纲比例，乘 100 才是百分数 | Gx−F5 / F5 同量范数 | Gz−F5 / F5 同量范数 | 结论 |
|---|---:|---:|---|
| Fresnel 散射 E | 1.375971034e-6 | 2.611862439e-2 | x 细、z 粗已接近 F5；仅 z 细仍失败 |
| 散射 curl(E)/k0 | 8.788076449e-7 | 2.750353735e-2 | 独立 curl 支持相同方向判断 |
| 总 E | 1.976081550e-7 | 3.750989700e-3 | 总场分母较大，不能覆盖散射失败 |
| 总 H | 1.262070398e-7 | 3.949829126e-3 | 同上 |
| top(0,0,s) 复幅值 / F5 幅值 | 3.234128416e-7 | 1.550759198e-2 | 同时检查幅度与相位，不能仅看功率 |

散射 E 的 Gx−F5 差范数为 1.233501447e-6，除以固定 F5 范数 0.8964588763 得到首行；scaled-curl 为 7.877327394e-7 / 0.8963653696。Gz/Gx 误差比约 18,982 / 31,296，混合增量相对范数仅约 1.05444e-6 / 3.93253e-6，支持当前误差主要对 x 敏感。微小差值已接近求解残差的数量级，**不能把这些数读成六位连续解精度，残差也不是场误差的严格上界**。

原 F3→F5 散射 E / scaled-curl 仍为 **2.611883% / 2.750374%**；冻结 11 个显著复模式最大差 **1.555605%**，其中 bottom(-1,0,s) 为 **1.274430%**，均按原门槛保留失败。Gx→F5 的 11 模式最大差为 **0.010866%**，其分母仍是该比较首场 Gx；不能混为表中的 F5 分母。最大能量闭合差约 4.56e-8，只证明相应离散解的能量核对，不替代 1% 场/复幅值门。

### 1.2 源码与原始记录核对

[网格计划](../../src/geometry/task40_nonseparable_plan.py)用有理数生成材料界面分段；Gx 确为 G1 的 x 加 G0 的 y/z，Gz 相反。[保存场比较](../../src/postprocessing/task40_saved_field_h_comparison.py)恢复实际 p6 场，直接在 DG6 计算 UFL curl，并减去解析 layered-Fresnel 背景的 curl；[全模式后处理](../../benchmarks/postprocess_task40_review_v4_modes.py)核对完整 340 keys，并复用原冻结显著集合。源码未显示靠改背景、相位拟合或删模式取得本轮方向结论。

| 证据身份 | 固定值 |
|---|---|
| Gx/Gz 求解源码 | 9fd295624444cf16b6ba393a0a7c3522f0070f73 |
| 体积 / 全模式分析源码 | 9fd0e5aec0019c522741ecc1df41f195831dc752 / 55feda2c6f5c0e0b9ec4b57a341d209ec8b566d2 |
| 四角接口 SHA256 | 44a878f85c6e50f5aa5c6b53f58addf1350041c33593cf72ea8cb6b961f29e43 |
| 体积原始记录 | benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/four_corner_volume_v1.json；SHA256 5f8004f51cb7d9543730281ace16f296cdc47b0358c66038302bf4f39ac40c17 |
| 全模式原始记录 | benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/four_corner_modes_v1.json；SHA256 e723cf5fd6dc761e3642582af12b921c05453c581903eaf47abac07816d17df2 |
| M2 有序清单 digest | 7336482596276ee033f211ea84635d91678591f40705b208025622a0a35dd253 |

预算 allowlist 拒绝、父进程意外 MPI 初始化及模块启动 import 失败，均发生于对应正式计算之前或启动阶段；后续修复/重试已有独立身份，保留为工程失败。延迟导入的改动不改变弱形式。没有理由为本报告再跑一次 Gx/Gz。体积分析峰值 934,637,568 B、864.838 s 是独立离线 worker；模式分析未单独采样进程树，二者不能伪合并成一个实测峰值。

## 2. M1：只新增 Gx784，预登记通过、失败与停止

### 2.1 唯一新物理配置

**采用 Gx 的 z=14 和完全相同的 y=4 节点，只把 x 从 10 段提高到 14 段。**原尺度 x 界面为 0、16.5、25、33.5、50 nm，四区间分别等分 **4/3/3/4** 段，再整体乘 7/135。旧 Gx 四区间为 3/2/2/3；新网格每区间都更细，保留材料和缺口界面。用有理数配方生成节点，不能先四舍五入；无需强求所有旧内部节点嵌套。

| 项目 | 新 case 预登记 |
|---|---|
| 名称 / 网格 | Gx784；14×4×14 = 784 单元 |
| y/z | 从 Gx 的精确数组复用，不能仅以相同段数重新均匀生成 |
| x 最大物理步长，derived | 外侧区间 0.213888889 nm；内侧区间 0.146913580 nm |
| p6 维数，derived | 完整存储 530,400；周期约束后独立 512,064；内部 352,800；保留 trace 加 340 ports 为 159,604 |
| p4 维数，derived | 完整存储 160,512；独立 152,320；内部 84,672；界面加端口 67,988 |
| 为什么选它 | x 明确超过现有 10；p6 行数和 p4 界面行数仍低于已完成 F5，能用一个较小的新解检验“x=10 是否足够”；不保证 LU 峰值必然更低 |
| 唯一允许变化 | 精确 x 节点及由其导致的网格/离散量；必要的参数化 mesh 注册、预算登记和保存场比较接线 |

其余固定：非可分缺口几何、λ=0.7 nm、θ=89°/掠角1°、φ=0°、s 入射 E0=1、Si 折射率 0.9998851703688496+4.3236152269189515e-6i、μr=1；p6/准确 p4、FGMRES32/max2048、零初值、既定 p4 分解/精化、MPI1/threads1、M2 全 340 模式、物理端口平面、周期相位与 Fresnel 背景全部不变。复用当前 runner，不再复制一个带数值核心的 task 脚本。

主线只需读取 Gx/F5 的已有合格原始场完成两个新比较；F3/Gz 旧结果直接引用。保存场后处理在 **Gx、F5、Gx784 的精确轴并集**上积分，维持相同公共物理体积、每轴 7 点规则和材料核对。现有四角函数仅针对四个既定轴组合，不能把新网格硬塞进旧 G00/G10/G01/G11 含义；需要时做最小通用配对接线，核心仍放 src/postprocessing。

### 2.2 比较口径与验收

| 验收项 | 固定要求 |
|---|---|
| 求解可信度 | 完整原 A6 真残差 ≤1e-6，原有 strict identity 1e-10、准确 p4 原 A4 目标 1e-10及既定精化规则不变；有限场、周期约束和恢复完整 |
| 场比较 | 分别计算 Gx784−Gx 与 Gx784−F5 的总/散射 E、H、直接 curl、scaled-curl；两对的每项相对差均 ≤1% |
| 场分母 | 两对均使用已归档接口的 F5 同量范数；例如散射 E 0.8964588762723267、scaled-curl 0.8963653695824167；不得换成新解范数 |
| 模式比较 | 固定原 11 keys；Gx→Gx784 仍以 Gx 幅值作首场分母，F5→Gx784 以 F5 作首场分母；两对最大复幅值相对差均 ≤1%；补充统一 F5 分母诊断，不能替换首场门 |
| 完整输出 | 保留全部 340 模式 real/imag、功率和 near-zero/非有限分类；不重新选显著模式，不删除旧失败通道 |
| 功率 | 两对 R/T/A_balance/A_volume 的绝对差 ≤1e-3；每个官方场能量闭合及两种吸收之差 ≤1e-5；R00_s、R00_p、R00_total 分列 |
| 诊断量 | 差范数的物理单位、各材料分区贡献和固定入射范数归一化值同时记录；这些诊断不替换 1% Gate |
| 禁止改判 | 不换背景、分母或模式，不拟合相位/复系数；不以功率闭合、残差或对旧 F3 的某个好看指标覆盖失败 |

新比较以物理端口的 outgoing_amplitude_at_boundary 和 exp(i*kz*z_boundary) 为准。旧 F3→F5 的失败即使新两对通过也不删除。

| 结果分支 | 本轮处理；不自动追加第二张网格 |
|---|---|
| 两对全部通过 | 标为 tested_x_agreement_pass：在当前缩小三维缺口模型、固定 y/z/p/M 下，通过新增 x 分辨率检验；保留 best available discrete reference 身份。主线转入接口/成本收口，不再追求多做一张网格 |
| 任一场或显著模式 >1% | 标为 accuracy_not_closed，列最坏物理量、具体模式、复差与分区；说明 x=10 尚不足或变化未减弱。完成成本账后停止，不自动 x18/x20、提高 p/M 或只细化缺口 |
| 求解残差/恢复未过 | 不能用于正式物理 Gate；区分离散求解未完成和精度失败。真正局部实现错误允许一次修复重放；max2048 耗尽不是“bug 重试”理由 |
| 资源受控停止 | 保存已经获得的网格、对象尺寸、阶段峰值/耗时；不改物理输入找一个更容易通过的替代 case，不启动 F5/Gx 重跑 |

**本轮不例行补全局 direct 或 y 加密。**已有 G0/M0 direct 对照验证过当时离散解，但它只有 80 模式，不是当前 340 模式/新网格的独立参考。只有新结果与原方程/完整输出自相矛盾、或求解误差确实影响 1% 裁决时，才在下一次明确决策中选择同离散独立参考；不能仅因为“独立参考总是更稳妥”再做一次昂贵求解。

原尺寸规则结构在 φ=0、y 不变材料和均匀入射下具有 y 平移对称性，精确解应在对应对称子空间中；可以用已保存的完整模式和方程结构判断是否需要新的 y 精度实验。**当前三维缺口破坏这个对称性，不能借此宣布缺口的 y 已收敛。**若 M1 通过且没有额外 y 误差证据，先推进原尺寸规则基线的资源/接口工作；未来缺口精度仍开放。若剩余场差及非零 n 模式提示 y 相关误差，再登记一个有明确反证量的 y 检验，而不是本轮自动追加。保留完整三维算子和全部 q/alias，不以二维求解替换生产路线。

## 3. dot：环境已恢复，新的数学资格仍待执行

### 3.1 新事实取代旧阻塞，但不继承旧通过

新 [运行时收据](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/official_runtime_recovery_imports_v1_zh.md)已解决此前官方包源/依赖缺失问题；[portable 合同](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/portable_retained_h_qualification_contract_v1_zh.md)和[remaining gaps](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/original_target_remaining_gaps_recovery_v1_zh.md)中的旧“不可安装”状态已被后续记录替代。它们关于实际 FE、持久 raw、原尺寸成本的未完成项仍有效。

| 证据类别 | 当前可确认事实 | 不能继承的结论 |
|---|---|---|
| 已发布历史数值 | V13 X、V14 XZ、V15 Y 的缩小 p4/manual532 全三维链和独立 checker 曾通过 | 不是新环境 PASS，更不是原尺寸精度/容量 |
| 中断前后历史组件 | p6 紧凑组件与 532 分解前对照曾报告通过；只读 pivot 曾导致 checker 崩溃，修复复核后云环境中断 | 最终旧 checker 仍 UNKNOWN；原始数组缺失，不能补写通过 |
| 精确恢复源码 | 两个 quotient/audit 模块有字节身份恢复证据 | 不等于完整旧 p6 补丁和旧原始数据已恢复 |
| 新运行时 | Python3.12.13，DOLFINx/Basix0.10.0，MPC0.10.5，PETSc/petsc4py3.25.6 complex128/int32，MPICH5.0.1；MPI1 导入/API 检查通过 | UCX_TLS=self 只支持当前 MPI1；MUMPS5.8.2 已安装不等于已做实际 factor |
| 新 C1 源码 | [79 项非 FE 合约测试](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/records/fresh_c1_source_v1/targeted_contract_tests.json)通过，1.095 s；新入口及完整依赖已提交 | 新 JIT、FE/MPC action、p6 组件、p4 求解、公共后端均 NOT_RUN |
| 持久证据 | [source checkpoint](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/records/fresh_c1_source_v1/source_checkpoint.json)明确 raw_artifacts_durable=false、storage_approval_pending=true | 源码可取回不代表原始数值证据可取回 |

新代码已处理只读 LU pivot：先校验范围，再用私有可写 int32 副本回代；仍须真实 checker 运行验证。FFCx 包版本 0.10.1 / module 0.10.0 的双身份已有记录，按实际 ABI 收据绑定，不凭字符串差异重装整个环境。

远程 eb5 与恢复本地候选 7951c6e1448c28b59a1c4a2ec30b9df7adf56a57 的树对应，不应伪装为相同提交图。启动参数 expected-head 必须是**实际执行 checkout 的完整 SHA**，另记录远程/tree 对应；不能为了通过身份门修改收据里的 SHA。

### 3.2 最短执行序列与三种 PASS

紧凑端口表示把原本容易重复保存的大矩阵改成原始 H 对角值以及按需计算的内部耦合项，收益是省存储，代价是每次应用时做局部运算。它必须保留任意内部载荷和端口载荷的影响。两单元周期分块则利用规则 y 周期，将参考逆分成全部 q 相位分支；它改变参考逆的构造成本，不删除原三维未知量，缺口引起的跨分支耦合仍由原方程处理。

| 顺序 / 独立状态 | 做什么、为什么 | 验收及边界 |
|---|---|---|
| C0：保存条件 | 确认执行者被授权的持久目录/对象存储、容量及取回方法；新 raw 落地，索引进入 dot 分支 | 先落实位置，随后每阶段归档后在新空目录取回、核验成员 shape/dtype/hash 与 checker 收据；没有保存位置就不开始易丢失的大量 JIT/FE |
| C1a：P6_COMPONENT_PASS | 用新入口的同一 80-cell full3D、φ5°、p6/manual532 live carrier 比 dense H/Hhat 与 compact；36,000 内部自由度、全部非零内部 RHS 和非零端口 RHS，全恢复 | action/recovery ≤1e-11；制造解完整原方程残差 ≤1e-10；独立代数恒等式 ≤1e-12；独立 checker 从原始单元张量重建，不只读取 status |
| C1b：P4_DENSE_PORT_REFERENCE_CHAIN_PASS | 绑定 C1a 新源码/环境/fixture/hash 后，p4、4 个 q、532 通道，regular/notch、四类 RHS 和全部 8,640 内部 RHS；建立新环境参考 | 稀疏 FE/凝聚/q 矩阵，端口 H/Hhat 仍稠密；原方程 ≤1e-10，恢复/重复回代/线性 ≤1e-11，原有模式、泄漏及近零门全部保留 |
| C1c：P4_COMPACT_QUOTIENT_CHAIN_PASS | 同一 fixture，将已存在的紧凑 H 与两单元 quotient 接入完整链；与 C1b 同矩阵定义、RHS、全部 q/532 输出逐项比较 | 真实原方程、完整内部/slave 恢复、任意内部与端口 RHS、regular/notch 跨 q 耦合、完整 observable vector 均通过；不能只比较两个 q 或一个端口矩阵 |
| C2a：PUBLIC_BACKEND_PASS | 先 tiny complex 非 Hermitian 单块，再复用 C1c 的全部实际 q 块切换到公开 PETSc 后端；其余不变 | 原残差 ≤1e-10、重复回代/线性 ≤1e-11；记录全部因子共存、实际 fill、setup/solve 时间及整数宽度 |
| C2b：AUTO_PORT_COST_MEASURED | 使用第5节真实 AUTO 全清单，执行有界真实求积/端口/投影测量 | 成本证据，不是完整 AUTO 求解 PASS，不是 AUTO 截断收敛 PASS |

C1a 的制造解是“先指定完整解，再从原方程生成载荷”来检验恢复和符号；它不是一个物理入射问题已经求解。物理 DiXiB 可能很小，现有独立材料量级负控制要保留，检查漏项、错号、错误共轭和把 Hhat 当原 H；不能改物理材料制造耦合。近零参考归一化幅值 ≤1e-8 时，补充绝对归一化误差 ≤1e-12；**该补充不替换原有操作尺度门**。

当前 [runner](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/benchmarks/run_y_orbit_sparse_probe.py)只明确提供 fresh-fixture-c1 的 p6-component / p4-chain；[p4 实现](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/src/solvers/y_orbit_sparse_probe.py)仍使用完整 Ny 参考装配和稠密端口。因此 C1c 需要最小接线和定向测试，不能从 CLI 存在或 C1a/C1b 成功中继承。数值核心仍放 src/solvers，不创建第二套参考求解器。

C1a 使用 [新 p6 核心](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/src/solvers/fresh_c1_p6_component.py)及[独立保存数据 checker](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/benchmarks/check_fresh_c1_p6_component.py)。它们保留原始张量、方向变换、MPC 映射、全部单元与端口支持；checker 重建内部矩阵并自行分解，不以保存的 LU 结果作唯一权威。这个设计满足有界真实试验的入口要求，仍没有实际运行结果。

每阶段成功后才进入下一阶段。允许在同一源冻结中先补好 C1c 接线，减少重建；若后续改动影响 C1a 的数值依赖，重做受影响的组件。纯 runner/文档变化可用明确的依赖文件哈希对应旧收据，不能简单改 expected_source 继承 PASS。不新增 p6 全局全链实验；那仍是后续集成缺口。

### 3.3 资源与公共后端边界

C1 及本轮 C2 有界测量保持 **每 worker/checker ≤3 GiB（3,221,225,472 B）、≤4500 s、MPI1/threads1、swap0**，实际容器余量更小时收紧。JIT/import 位于监督器内；启动前满足动态物理余量和另留 128 MiB 证据余量。未压缩 raw 预算 512 MiB、可用磁盘至少 2 GiB；超预算受控停，不假定压缩比。p4 四因子 512 MiB 是策略 allowance，**不是已经测到的 fill**。

源码的 component packet 绑定不等于远程持久保存检查；进入下一阶段前由执行流程确认取回验证收据，不能仅凭 raw_remote_storage_verified 字段或一个 worker PASS。已有符合本轮条件的阶段直接复用，不因报告更新重跑。

公共 PETSc 需要真实复数非 Hermitian 数学资格。setFactorSetUpSolverType 创建并配置 factor 对象不等于完成分析；公开 PC.setUp 路径组合 symbolic/numeric，不能在 Python 中虚构一个两者之间已通过的准入点。按[官方 factor 对象说明](https://petsc.org/release/manualpages/PC/PCFactorSetUpMatSolverType/)、[PCLU实现](https://petsc.org/release/src/ksp/pc/impls/factor/lu/lu.c.html)及安装版本源码/API核对；若缺少合同所需的可控阶段，小例可以在总体硬预算内完成 setup，原尺寸后端保持 HELD，不发展私有 ctypes 绕行。当前 PETSc.IntType=int32，对 rows、NNZ、indptr、转换和后端 offset 必须分配前检查；PETSc int64 也不自动等于 MUMPS full64，参照[官方 MUMPS 接口](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)与实际构建记录。

## 4. 双方接口：共用定义，暂不伪造数值等价

主线 φ=0°、p6/M2=340；云端 φ=5°、p4或p6/manual532。几何、阶次、入射、模式不同，不能直接比较复幅值后称算法误差。新四角接口包是主线的冻结定义来源，dot 输出一份对应字段映射即可，不需要重跑主线模型。

| 必须对齐的接口字段 | 主线负责 / dot 对应要求 |
|---|---|
| 物理身份 | λ、n/μ、几何/缺口、精确轴、θ/φ/偏振/E0、实际边界及 reference planes；不把缺口 y 移位当相同模型 |
| 模式 | 完整有序 side/m/n/pol、Bloch 波数、出射方向、基向量、gamma/alias、传播和实能流标志、digest；340/532分列 |
| 相位与幅值 | outgoing_amplitude_at_boundary、实际 exp(i*kz*z_boundary)、E0 和功率归一化；无拟合或平移修正 |
| 场与单位 | 总场、Fresnel 背景、散射场、直接 curl/k0；主线 H 为 A/m，dot native scaled H 不是 A/m，转换系数必须显式记录 |
| 完整恢复 | 内部和端口 RHS、trace/interior/port 排列、MPC slave 恢复及原方程 action；不能仅移交缩聚残差 |
| 资源 | 同时树/cgroup峰值、系统基线和余量、各对象共享/复制/释放时间、端到端时间；不相加各阶段历史峰值 |

主线接口中的 H 单位换算在当前 E0=1 下约为 0.002654418727984993 A/m 每 native scaled-H 单位；执行方以已冻结物理常数和单位重新核对，不能把 nm 制 curl 直接当 SI curl。dot 的原生面通量除以 nm² 面积和 |E0|²，不是瓦特。340 清单中 80 propagating 与 210 positive-real-flux/power-carrying 是不同分类，不能对齐成“210 个传播通道”。

分工固定：**主线负责 M1、物理/观测接口和原尺寸准入总账；dot 负责 C1/C2 的紧凑表示、周期参考逆、内部恢复及后端实测。**后续移植只列最小依赖文件组和对应 fresh evidence，不整体 merge/cherry-pick dot。本轮主控不修改 dot 专属分支，也不向已运行进程目录写新源码。

## 5. 现在就推进原尺寸资源账，不等待全部云端结果

### 5.1 先生成真实 AUTO 清单

[历史原尺寸库存](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/records/full_size_port_inventory_v1.json)给出 φ=0°、50×25 nm 周期、λ=0.7 nm 的 **32,060 通道、8,015 个 (m,n)、非零 n 通道 31,488**，m 实际范围 -142…0、n -35…35；但 ordered_key_hash 为 null。它是旧传播库存计数，不是当前完整有序清单，更不是已通过的端口截断收敛。

TARGET_LEDGER 与 Gx784 求解互不依赖，可以先用实际模式生成器输出完整 keys、顺序、传播/实能流分类、全部复波数、材料/入射及 source digest，再与历史库存逐项核对。执行记录使用 TARGET_LEDGER 名称，与缩小模型的 M2=340 模式配置区分。清单不需要 FE 装配；不为它另写近似计数公式，也不要求 dot 重做一份。后续若真实 AUTO 含额外倏逝模式，按实际清单计账，不能锁死 32,060 来压成本。

为使资源账有具体尺度，本报告给一个**仅用于计数的原尺寸候选**：若将 Gx784 四区间的物理 x 步长搬到原界面，段数为 ceil(4×135/7)、ceil(3×135/7)、ceil(3×135/7)、ceil(4×135/7)，即 78/58/58/78、nx=272。临时取 ny=4、nz=14，得到：

| 原尺寸计数例；全部 derived、不是 mesh/PDE 资格 | 数量 |
|---|---:|
| 单元 | 15,232 |
| p6 完整存储 / 周期独立 / 内部自由度 | 10,228,620 / 9,948,672 / 6,854,400 |
| p6 trace 加历史 32,060 ports | 3,126,332 |
| p4 界面加历史 ports | 1,346,364 |
| 一个 p6 完整 complex128 系数向量 | 163,657,920 B |
| 一个 p6 保留空间 complex128 向量 | 50,021,312 B |

这个例子**没有证明原尺寸的 y/z 或 x 精度**，Gx784 自身也尚未运行。原尺寸参数表最终必须在精度决定后冻结；表中向量很小不意味着因子、端口和缓存很小。它的用途是立刻把“2 TB 大概够”转成带维数、待测项和生命周期的账，不是批准采用该网格。

### 5.2 必须闭合的整机同时成本

| 成本项 | 下一轮可交付的具体证据 | 当前缺口 / 禁止推断 |
|---|---|---|
| AUTO H / Hhat | 原始 H 对角保存 16M B；记录全部内部修正的实际表示 | M=32,060 时原 H 对角 512,960 B、单个稠密 H 16,445,497,600 B；节省一个 H 不能覆盖整个算法 |
| 求积、JIT与端口基函数 | p4/p6 实际 compiled 节点、kernel/cache、编译子进程峰值、一次冷编译时间 | 旧公式 max(10,2p+max_order+6)在 order142 给 degree156/160、名义79²/81²点；不冒充实际编译输出 |
| C/D 和 Di/XiB | 每物理支持类的形状、dtype、稀疏 NNZ、边界/内部耦合、缓存唯一数和复制数 | 不能沿用旧 clipped/p2 内部零耦合假设，不只统计最终对象 |
| 投影工作区 | 每 q 的最大 lp×rq、16lp·rq B、left/right product、COO→CSR及累加同时存活量 | 当前源码仍可能形成稠密矩形，compact H 并未自动消除它 |
| 单元与内部恢复 | 原始单元张量、450×450内部 LU、变换模板、MPC映射、共享类/每 twist 实例、恢复批次 | dot 已有模板复用，按真实唯一类计数，不重新实现，也不按所有单元等量复制线性外推 |
| 全部 q 因子及 fill | 各块 rows/NNZ、backend/order/pivot、L/U 非零与字节、workspace、全部因子驻留时间线 | 四因子512MiB策略预算、输入NNZ或小例RSS均不能替代填充 |
| 原三维 outer / Krylov | 原算子载体、FGMRES基向量与预条件后向量两组、RHS/残差/临时向量实际个数 | 不能只计一个向量或一个 q；不得忽略 retained ports 和重启时工作区 |
| 输出、独立校验、系统余量 | 完整场恢复、写出缓冲、checker与对象重叠、文件缓存/cgroup口径、OS/监督器余量 | 不把2TB全分配给solver；不把进程树峰值声称整机峰值 |
| 完整时间 | cold JIT、build、all-q setup、每次PC应用、外层步数、恢复/输出/checker逐阶段成本 | 历史弱缺口3–4步和旧X/XZ/Y秒数不能代替原尺寸迭代/耗时 |

整机准入使用同一时刻仍存活对象与实际进程/系统计量，取最大同时量；各阶段独立峰值既不能简单求和，也不能漏掉常驻因子。必须有大于零、按实机冻结的系统/监督余量。最终实际整机占用 ≤2e12 B，swap=0。时间则对一次必要完整流程计总账，≤172800 s。未知 fill、未知外层步数或未计成本不能按零处理；预测只能标 predicted，不能写 solver pass。

### 5.3 AUTO 有界探针及最可能的瓶颈

[投影源码](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/src/solvers/y_orbit_two_cell_block_audit.py)的原始对角 H 路径已避免整块稠密 H；但 CachedPortCorrection 仍计算 dual_di = L.conj().T @ Di、xib_primal = XiB @ R，继而 projected = dual_di @ xib_primal，再转稀疏并累加。因此必须测的不是“向量 H 能否分配”，而是**完整 AUTO 支持下这个稠密矩形及后续因子是否可承受**。

C2b 只使用一份完整 AUTO 清单、p4/p6 各自所需求积：至多选上下介质各一个代表边界面及一个最大支持内部修正类，保存其覆盖依据。若不能证明覆盖全部支持类，只能给已测类成本，不能推出全局上界。允许按完整模式批次处理以控制临时内存，所有 keys 最终必须出现；不截断 n、不删弱模式。超过 3 GiB/4500 s 前受控停，分配前尺寸仍是有效结果。

当前 quotient/profile 的 p4、532 和固定映射断言代表真实支持边界。AUTO 扩展需要参数化完整映射并以 C1c 同 fixture 反证对照；不能删掉断言后称 AUTO 已支持。C2b 不构造原尺寸完整体积矩阵，不启动目标规模 LU。C2a、C2b 分别出 backend 与 port-cost 结论；一项受阻不抹掉另一项已有成果。

**路线判断：**紧凑 H、按需内部修正和两单元参考构造确实减少若干重复/稠密存储，值得继续；当前主线全局准确 p4 加 dot 稠密端口参考链，尚不足以支撑原尺寸 AUTO。现有证据也未证明紧凑路线一定失败，所以本轮先用上述一个精度点与有界成本探针作决定，不再做方法清单式探索。

只有出现对应实测瓶颈时才选一个替代：

- 若先卡在 projected 稠密矩形，而最终稀疏支持可承受，优先做**精确分片收缩/输出**：按端口子块生成同一完整矩阵，减少临时矩形，保留全部模式与内部修正；以 C1b/C1c 同矩阵的全输出和原残差作独立对照。不做低秩截断，不重启旧 clipped C/D 路线。
- 若单个 q 可承受、但全部因子并存超预算，可先核算**有界因子批次与精确重算**的生命周期：减少驻留会增加每次PC应用的分解时间，必须把这些重复成本乘实际应用次数计入48小时。若时间不成立则直接否决；若单个 q 已超限，此替代也无效。
- 若单块 fill 或完整时间本身无法进入目标预算，报告“当前精确参考逆路线无法支持该目标参数”，不继续扩大机器/改swap或扫描旧全局低阶/BLR方案。后续只可从 Task40 已登记、尚未实测的有界局部加递归物理粗纠错设计中选一个固定反证试验，需另行冻结范围；本轮不自动实现一套新求解器。

上述是按瓶颈选择的有界出口，不是三个追加实验许可。当前报告不能宣布工作站大规模验证就绪。

## 6. 历史路线核对：复用成果，保留失败

以下是与本轮选择直接相关的台账；详细数值和原路径继续以 [Review V4](review_report_v4.md)、[task035](../task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md)、[task035b](../task035b_high_order_local_hp_resource_envelope/outcomes/summary.md)、[task039 Schur记录](../task039_extra_physical_multilevel/outcomes/p4_schur_v14.md)及 dot 历次 response 为准，不复制另一份平行历史权威。

| 已有路线 | 已试 / 失败 / 设计 | 对本轮的约束 |
|---|---|---|
| 主线两种背景、真实 p6/MPC 背景表示 | 已完成；扣除表示差后 E 差仍有99.7384%、curl差94.8710%；incident-only仍超1% | 不重跑归因；旧 h_agreement 生成器未知不升级为“旧程序有bug”，也不继续无界追查 |
| 主线 M1→M2、分区/模式 | 模式扩展影响小，各材料散射误差相近；不能解释2.6%–2.8%负结果 | 不重复模式扫描或盲目只细化缺口 |
| 主线 Gx/Gz 四角 | 已完成且方向假设成立；x10本身未收敛认证 | 只新增 Gx784，复用全部四角 |
| task035 自适应 | residual式p2/p3精度代价比均匀网格差；DWR曾有收益，但既有结构化p4 h7.5更优 | 不泛化为“自适应都不行”，也不重启无目标的指标扫描 |
| task035b 分区阶次/轴向网格 | p5 trace/p6 interior h13仍10/12；例如 top(-4,0,s)功率差4.81518e-9 >1.08649e-9，top(-5,0,s)幅值差6.58997e-6 >1.11321e-6；额外top-z/x路线亦未全过 | 历史轴向加密存在；本轮新信息是当前0.7nm配对证据后的一次x分辨率检验 |
| task039 宏块/近似粗逆 | 42块精确Schur内存约旧基线1.510倍；三份固定RHS的完整A4相对残差分别37.272/0.7264/41.826，超过各自0.5/0.2/0.5限值 | 不重新扫相同宏块、强全局低阶、BLR或固定75维粗空间 |
| Task40 已有工程 | 积分/缓存复用已有；P5两个q放大worker失败保留；真实450/432局部划分有证据，某些大维局部证据只是合成 | 不把组件/合成扩展当原尺寸；局部加递归粗纠错仍为设计，不能写已验证替代 |
| dot clipped→边界相位 | 旧p2原H小量及C/D裁零曾失败；后续边界相位/raw532组件和p4完整链有历史正结果 | 不重复裁小耦合、仅换坐标就称物理恢复；沿新fresh完整原方程核验 |
| dot V13–V15 X/XZ/Y | 120/168/120单元旧环境完整三维通过；Y的notch做过周期移位 | 不重跑规模扫描，也不把Y作为相同几何的y精度对照 |
| dot 新79测试 | 新NumPy/元数据/启动合同通过；FE尚未运行 | 直接做有保存条件的C1，不继续堆同类纯代数测试冒充推进 |

## 7. 执行边界、有限自修复与交付

主线沿 task 的 physical-memory-pressure 政策冻结实际 RAM/cgroup、MemAvailable、任务/系统基线和 OS 余量；不沿用输入中的旧8/10GiB数值作为实际 stop authority。保持 max2048 和既定求解规则，不以历史耗时任意中断正常计算；用户本轮完整必要流程48小时为硬上界，执行前明确计时起点及监督范围。新网格只有一个，一次只跑一个 heavy case，不能与已有任务争抢相同资源。云端保持第3节更小的4500s硬预算。

| 阻塞或失败 | 最多做什么 |
|---|---|
| 主线已在执行/未提交修改 | 先接续现有状态和输出；用已登记工作树安全取得报告，不reset、不覆盖、不重启相同case |
| 保存场路径失效 | 按既有索引查找一次；若关键Gx/F5原始场确实丢失，明确缺项并停配对精度Gate，仍完成新场/成本账可独立部分；不偷偷重做两基准 |
| 局部脚本、ABI加载、shape/pivot错误 | 最多两轮局部修补/定向测试；每个数值case至多一次受影响重放，保留失败/source/raw；不增加物理配置 |
| 纯粹数值不收敛、精度超限 | 不是自修复额度；完成对应负结果、最坏误差与下一选择依据后停止 |
| dot持久保存未落实 | 保持C1 held，主线继续M1/TARGET_LEDGER；不重新安装已通过imports的环境或反复跑79测试等待 |
| 新checker失败/中断 | 完整原方程/恢复资格未通过或UNKNOWN；只修当前fixture，不进下一阶段，不继承旧通过 |
| AUTO/JIT/投影/填充超小预算 | 保存分配前尺寸、阶段和真实停止；应用第5节一个匹配的有界出口，未获证据前不启动原尺寸 |
| 公共后端阶段或整数范围不成立 | 交付已完成小例与具体限制，原尺寸后端held；不绕过容量检查或使用私有FFI |

阶段收口更新既有 response、summary、run_index 和模型总账，记录 source/输入/环境/raw hash、全部正式量、资源口径、失败/停止。主线只需**一个新网格结果、两个新配对比较、接口映射与原尺寸准入账**；dot 每层单独交资格。按实际相关改动运行最小测试和任务规定的必要检查；已绑定同源码/环境/输入的昂贵通过项不因文档改动重跑。小规模通过仍不能写 TARGET_SCALE_0P7NM_PASS。

待确认事项集中为：dot持久raw位置与取回收据；主线已有场的实际可读性和机器余量；真实AUTO有序清单；最终原尺寸网格、全部q填充/整数范围、端到端时间。它们各自只阻塞依赖步骤，不阻塞主线一次新增精度实验。

主控 Codex 可直接执行以下文本：

> 在 canonical clone 的 task40extra_0p7nm_engineering 跟踪分支读取 review_report_v5.md；本轮审阅基准 ba7dec1d733bb5f4a0f775ae74b63730ed3c1205，dot只读基准 eb5b0ecc1afe593f626b44a6038f7f26651b3317。先保留当前作业和未提交改动，安全取得报告；不改dot/master、不merge、不重跑已完成Gx/Gz/背景归因。主线只新增Gx784=14×4×14：原x界面[0,16.5,25,33.5,50]按4/3/3/4等分再乘7/135，y/z精确复用Gx，固定p6/准确p4、φ0、全340模式和原求解/相位/背景。复用Gx/F5保存场按报告公共体积、固定F5场分母与冻结11模式完成两对比较；原A6≤1e-6，场和显著复模式≤1%，功率差≤1e-3、能量≤1e-5，旧F3/F5失败保留。通过就收口，不自动追加网格；失败、max迭代或资源停止也按预登记收口。每case最多一次真正局部bug修复重放。独立推进TARGET_LEDGER：真实原尺寸AUTO完整keys/digest及全流程对象/生命周期/资源账，不启动原尺寸矩阵分解。dot由其执行方在持久保存落实后依次做C1a真实p6组件、C1b p4稠密端口全q规则/缺口参考链、C1c紧凑两单元完整链，三者分别验收；再做C2公共PETSc后端及有界AUTO端口成本。云端每worker/checker≤3GiB/4500s、MPI1/threads1/swap0，任一阶段失败或保存未完成则停其下游；本机按实际内存压力与系统余量执行。最终目标整机≤2e12B、swap0、完整必要流程≤172800s，当前原尺寸大规模求解仍HELD。不要删除模式、改分母/背景或拟合相位；不要把79测试、组件或参考链通过写成原尺寸就绪。提交各自范围的结果、负结果、停止和证据；主线更新下一response及既有summary/总账并推送同一执行分支，返回完整SHA待审。

交付核验：本轮只做远程源码/记录审阅、标量复算、Markdown结构和链接核对；不声称本地测试或CI通过。网页渲染状态在提交回执中单独说明，不以结构检查替代 rendered-view Gate。
