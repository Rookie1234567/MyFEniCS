# Review V4：迁移已测 p4 快路径与 p3 低内存能力，CPU23 顺序执行 5 nm / 2 nm

## 0. 决定、执行身份与职责

**批准 Codex 在现有工作站分支中做依赖组级的选择性代码集成：以已测 Q4 r2 快路径为正式基线，同时迁入直接 p6→p3 的可选能力；正常只做一场 5 nm Si p6/h4、coarse p4，通过后继续一场 2 nm Si p6/h1.5、coarse p4。ChatGPT 本轮只新增本 review，不迁移代码、不合并分支、不启动计算。**

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task39extra_para_workstation_capacity
review_date                = 2026-09-23
reviewed_target_HEAD       = 16cd8d2f00f27cec3d6de8056c61d668bf7ee7a9
previous_target_review     = review_report_v3.md
latest_target_response     = response_v4.md; no response_v5.md at reviewed HEAD
source_branch              = task39extra
reviewed_source_HEAD       = bb541cf3286b89734181d1da1a0ecfd2a5078243
source_latest_review       = review_report_v25.md
source_latest_response     = response_v27.md
common_ancestor            = 450255f4575792d052c1bac29837d39955ee1039
Q4_speed_numerical_source   = 4bf2bba56cc2e568d56ff3096aeb4a108744f28d
Q3_qualified_source        = cad282e25ed53cad1f9e4a5a70c14f3dd40e6d32
batch_id                   = review_v4_native_q4_speed_5nm_then_2nm
execution                  = M0 -> M1 -> M2 -> F5 -> conditional F2 -> Z
normal_full_PDE_count      = 2 total; one 5nm and one 2nm; both coarse p4
formal_MPI                 = 1
math_threads               = 1
worker_cpu                 = 23
parent_watchdog_cpu        = 9
resource_policy            = measured_tree_rss_only_v3
rss_hard_limit_bytes       = 1300000000000
response_required          = response_v5.md
full_branch_merge          = NOT_APPROVED
master_merge               = NOT_APPROVED
```

本轮消除的 blocker：**工作站目前仍停留在较旧的双凝聚执行路径，尚未继承已测的高阶算子加速与可选粗阶能力；需要把这些成果变成同一物理/离散下可核验的短波计算，而不是再按慢实现重复最大案例。** 最终目标仍是约 2 TB 物理内存内的 0.7 nm、complex128、Nédélec H(curl)、双 Floquet、Fourier-DtN、任意非可分三维周期单胞。此次原始结构的两场容量试验不等于任意三维或连续精度资格。

本 review 是新执行授权，覆盖 V3 的旧 donor SHA、“只做 5 nm / 不启动 2 nm”和旧批次用尽等限制；不覆盖原方程、精度或历史证据。**不先完成旧 V3 的一场 5 nm，再重复跑本批 5 nm；只执行本批最终选定的新实现。** 原 task、V1–V3 review、旧 response/profile/失败和账本原样保留，未执行项按 superseded/not_run 说明，不能改为已通过。

用户称上一任务未执行，结合仓库应区分“长算例未执行”和“准备代码已有提交”：目标 HEAD 的提交为 `complete V20 retained D2 migration`，已存在 V3 profile、retained runner/checker 和 RSS-only 接线；最新 response 仍为 V4，summary 仍主要是旧 2 nm 终态。M0 核对已做部分与现场证据，继续完成，不删除重做，也不因提交标题就承认整个迁移已资格化。

## 1. 已核对成果：迁什么，不能把什么当作成功

读取根/目录 AGENTS、[仓库原则](../repository_work_principles.md)、本任务 [task](task.md)、[V3](review_report_v3.md)、[当前 response](response_v4.md)、[summary](outcomes/summary.md)，并按冻结源 SHA 阅读源 task、补充授权、最新 review/response 和如下证据。远程读取不替代 Codex 对现场 ignored 原始数据及导入路径的核对。

| 已测对象 | 完整 workflow / 纯 KSP（s） | 步数 / 原 A6 残差 | 同期整树 RSS（B） | 本批定位 |
|---|---:|---|---:|---|
| Q4 r2，13.5 nm、p6/h7.5、990 cells | 3114.283619607013 / 2284.681783819 | 126 / 9.283165086752956e-7 | 7390937088 | 51.9047 分钟速度基线；正式迁移对象 |
| Q3，13.5 nm、同 p6/h7.5、990 cells | 7065.949492944987 / 6082.501362726 | 361 / 9.460140452867132e-7 | 4031815680 | 低内存可选能力；117.7658 分钟，并非更快 |
| V26 setup-efficiency，同 Q4 模型 | 3595.9571450339936 / 2716.518828 | 126 / 9.283164976754267e-7 | 7381557248 | 离散一致性通过，但完整流程约 59.93 分钟，不替代 r2 |

证据固定入口：

- [Q4 r2 compact](https://github.com/Rookie1234567/MyFEniCS/blob/bb541cf3286b89734181d1da1a0ecfd2a5078243/docs/task039_extra_physical_multilevel/outcomes/records/v25_q4_ac_swap_observe_r2_result.json)。动态 checker 的 `partial=true` 表示只覆盖动态计数/接线，不能独自代替完整 A6、场和物理核验。
- [Q3 compact](https://github.com/Rookie1234567/MyFEniCS/blob/bb541cf3286b89734181d1da1a0ecfd2a5078243/docs/task039_extra_physical_multilevel/outcomes/records/a6_h6_coarse_degree_v25_q3.json)与[粗阶比较](https://github.com/Rookie1234567/MyFEniCS/blob/bb541cf3286b89734181d1da1a0ecfd2a5078243/docs/task039_extra_physical_multilevel/outcomes/a6_h6_coarse_degree_v25.md)。同一 cad282... 批次 Q4→Q3 的 RSS 降低约 45.44%，步数 126→361；不能把 Q3 当成对 p4 的全面替代。
- [源 selective manifest V25](https://github.com/Rookie1234567/MyFEniCS/blob/bb541cf3286b89734181d1da1a0ecfd2a5078243/docs/task039_extra_physical_multilevel/outcomes/selective_merge_manifest_v25.md)：sum-factorized A6/H6、直接 p6→q、准确单元凝聚与测试的依赖范围。
- [源 Response V27](https://github.com/Rookie1234567/MyFEniCS/blob/bb541cf3286b89734181d1da1a0ecfd2a5078243/docs/task039_extra_physical_multilevel/response_v27.md)及[Review V25](https://github.com/Rookie1234567/MyFEniCS/blob/bb541cf3286b89734181d1da1a0ecfd2a5078243/docs/task039_extra_physical_multilevel/review_report_v25.md)：V26 没有整场提速；最新 review 中进一步的工作集/p6 setup 优化是待执行计划，不是已完成成果。

上述 PASS 均保留 `AUTHORITY_LIMITED`：没有独立 h7.5 连续精度资格。51.90 分钟是笔记本上的特定完整运行，不是工作站 5 nm/2 nm 的 ETA，也不能把不同运行中的供电、频率或缓存影响全部归为算法改进。p6/h7.5 指 h=7.5 nm，**这些源成果的真空波长是 13.5 nm，不是 7.5 nm**。

Q3 是在保留 p6 主方程的前提下，直接用 p3 代替 p4 作为中间修正空间；不是 p6→p4→p3 三层递归，也不是把最终解降为 p3。源中部分账本仍叫 `native_A4` 或 `p4_solve`，在 q3 时实际是 A3，迁移后须显式记录真实 coarse_degree，不让旧字段名改变数学解释。

## 2. 分支关系与 Codex 的集成方式

远程 compare 已确认两分支的共同祖先是 450255...；在本次审阅快照下，源独有 135 个提交、工作站独有 40 个提交，状态 `diverged`。**确实同源，可以复用代码，但不能 fast-forward；普通三方 merge 在 Git 语义上可做，不代表没有文本冲突或运行语义冲突。** 本轮没有执行试合并，不声称“已无冲突”。[Git merge 文档](https://git-scm.com/docs/git-merge)仅解释版本控制语义，不提供数值正确性保证。

因此批准的是 **Codex 按依赖组进行文件/补丁级集成**，不是整分支 merge、squash、reset 到源 HEAD，也不是把 `src/` 整目录覆盖。源 branch 只读，目标 branch 保留其 native Linux、int64/PORD64、CPU23、600/3904 通道、输入语义、RSS-only 及旧结果。目标 V3 已移入的同功能模块应在原位置增量完善，避免再造平行求解框架。

M0 生成一个紧凑 migration manifest：每个依赖组列 donor commit/blob、目标原 blob、需要的差异/冲突处理、共同依赖与验证。比较使用共同祖先及两端内容，而不是只比较源 HEAD 与空文件；API compare 的文件表可能受条数限制，Codex 用 canonical clone 的完整本地 diff 确定实际清单。

### 2.1 固定 donor 与允许迁入的功能

**正式数值行为以 Q4 r2 的 4bf2bba... 为锚点；p3 资格依据 cad282...，同一参数化代码在选定 donor 中的适用性须核对。** bb541... 用来审阅最新状态，不要求全盘采用其中 V26 或尚未完成的 V27 研究。源后续继续前进不阻塞本批，也不自动追随。

| 依赖组 | 允许的内容 | 主要已有入口，实际 import 依赖在 M0 核定 |
|---|---|---|
| 双凝聚基础 | p6 retained Schur/action/恢复，p4/p3 装配时单元凝聚与一份准确全局 trace/port 因子 | `hcurl_assembly_time_condensation.py`、`hcurl_affine_isotropic_tensor.py`、`p4_cell_condensed_inverse.py`；现有 retained runner/adapter |
| 真实高阶作用加速 | 已测 N1E sum-factorization；A6 物理作用、H6 apply 与 power10 的一致后端；保留独立 native witness | `fullspace_n1e_sum_factor.py`、`fullspace_partial_assembly.py`、`physical_equivalent_fast.py`、`physical_light_setup.py`、`fullspace_quadrature_diagonal.py`、`fullspace_mpc_action.py` |
| 粗阶参数化 | 直接 p6→q，q=4/3，各自空间/MPC/传递/凝聚/恢复与原 Aq 检查 | `fullspace_same_mesh_hcurl_pmg_runtime.py`及已测粗阶 runtime、profile/schema 的必要片段 |
| p4 返回修复 | 同因子有界显式精化，完整 FE/端口累计修正，动态计数 | `p4_cell_condensed_inverse.py`、`physical_reference_diagnostics.py`及现有 native adapter |
| 外层和生命周期 | J 增广逆桥、retained FGMRES、源已有共享只读缓存、编译前置与安全释放 | `src/solvers/physical_retained_fgmres.py`；`src/runners/physical_retained_outer_adapter.py`与目标 `physical_retained_condensed_v20.py` |
| 接线与证据 | 显式 coarse_degree/backend、公共入口识别、动态 checker 与相关小测试 | 目标 `src/io/native_capacity_profile.py`、既有 input/launcher/runner/checker；按需参考源 V25 |

表中无目录前缀的 numerical 文件默认在 `src/solvers/`。文件清单是审查入口，不授权无条件覆盖每个文件。源特有的大 runner 只抽取必要功能，目标现有 V3 dispatcher/监督可复用；禁止为两个波长各复制一份千行脚本。

不得迁入：源 WSL activation/二进制/JIT 缓存、6/8 GiB 库存限制、128 MiB 笔记本余量、4687 MB MUMPS 配额、源 990-cell 网格、80 通道常量、源任务账户/服务 ID、源 replay 配额和计费规则；不得迁入 Q2/p2、宏块、BLR、PML、DD、recycling、GPU、多线程或其他历史试验作为当前默认。

V26 的四项局部 setup 优化不作为本批必需项，不额外复制源 Review V25 的工作集研究；只有为已选路径兼容/正确性必需的后续小修复可以引入，需单独记录来源和影响。不要为了选最快版本再在工作站重跑多个完整 13.5 nm 基准。

## 3. 数学与实现合同

### 3.1 不变的主方程与改变的内部表示

p6、q=4/3 都先在每个单元内消去内部自由度；p6 外层迭代共享 trace 加端口，最终准确恢复所有内部未知量。粗层只装配凝聚矩阵并做一次全局 LU，每个输入缩减、回代、恢复。局部消元改变表示，不降低 p6 的物理离散阶次；减少全局向量和因子规模的代价是局部缓存与恢复成本。

```math
A_q=P_{6q}^{H}A_6P_{6q},\qquad C_q=P_{6q}A_q^{-1}P_{6q}^{H},\qquad
\mathcal B_{6,H}^{(q)}=C_q+(I-C_qA_6)H_6(I-A_6C_q),\quad q\in\{4,3\}.
```

该 Galerkin 等价须在原共同积分与完整 DtN 下检验；不能只凭不同阶空间名字推断。**两场正式运行 q=4；q=3 仅完成可用接口和组件资格，不额外跑完整短波 Q3，也不在 Q4 运行中/失败后自动降阶。** 内存足够是本轮选择 p4 的研究判断，不是 2 nm 已测容量通过。

保留 V3 第 4 节的复非 Hermitian 三块凝聚、非零内部/端口 RHS、Bi/Di、原 Hp 与 Hhat、方向变换与 MPC primal/dual 规则。完整 curl 与复材料项先相加再消元；不能分别凝聚后相加。凝聚与 p 传递不一般交换，不截取 P 的 trace 行后假设 S4 是 S6 的直接 Galerkin 粗算子。

retained PC 使用已测 `J M_aug J^H` 逆桥，不重新发明接口。zero retained start 不等于删去非零内部载荷特解。任何旧细层数组、另一波长解、Krylov 空间或因子不得进入初值。

### 3.2 必须真正接入快路径

sum-factorization 把单元内三维基函数作用拆成逐方向计算，减少重复运算；它利用有限元基函数结构，不要求整个器件沿 z 均匀。实际源实现通过 Basix N1E 系数矩阵和一维 Legendre 表转换，不能仅把 profile 标签改为“fast”。正式 manifest 写出真实 factory/class、模块路径、后端与配置，至少验证 A6 体作用、DtN、H6 apply 和 power10 的接线。

选定行为对应源 `isotropic_sum_factorized_n1e_v26` 后端及 `isotropic_sum_factorized_n1e_v26_apply_and_power10` 规则；这里后端字符串中的 v26 不是后续整个 setup-efficiency V26 profile。**不能因字符串相同就混淆两个版本的全部优化。** 允许目标使用清晰别名，但须保存源名和显式映射。

保持实际 Nédélec 变体、complex128、原 quadrature 点/权重/顺序及材料；不 fast-math、不减少积分/通道、不假设短波无损。批量工作区有界，分类缓存按真实几何/材料/积分/方向身份复用，不按任意舍入强行合并局部类型；遇到源不支持的实际单元要明确处理，不静默回退慢实现后仍称为已测快路径。

### 3.3 每次粗修正的返回质量

原 Aq 返回残差限值保持 1e-10，分母为原始输入 g。一次凝聚/回代/恢复后检查 `g-Aq*c`；必要时使用同一因子最多额外两次显式修正。每次修正必须累计完整 FE 与端口状态，保留原 Hp 闭合和 strict slave-zero；不只修 FE 忽略端口。MUMPS 内部自动精化不与这两次混用，沿已测 `ICNTL(10)=0`、BLR 关闭。

源旧 h7.5 一次 A4 超限是历史负结果；后续已实现并取得正式结果的有界修复应一起迁移，不能又从“没有修复”的 V20 开始。零 RHS 可直接返回零；非零近零输入沿已有尺度规则，不能放大分母获得通过。修正后仍超限，保存 g/c/r 和因子身份并以数值未合格收口，不更换排序或 PC 反复试。

每次 BAL_H 仍两次逻辑粗调用；MatSolve = 实际非零裸求解 + 精化求解。setup、每步迭代、检查分别计数，不硬填 126/262/267 或每场精化固定为 5。每个 case 只建一份粗因子，不为每个向量或预检重建。

## 4. 两场正式模型与输出身份

新 dat 以目标工作站原 5 nm/2 nm 的物理语义为基底，只更换显式 solver/backend/resource 配置及 run_id；**不要从源 h7.5 dat 改一个 wavelength 就启动**。

| 项目 | F5 | F2 |
|---|---|---|
| 真空波长 / 主空间 | 5 nm / p6 | 2 nm / p6 |
| 网格 | 原目标 p6/h4，boundary-fitted affine hex | 原目标 p6/h1.5，boundary-fitted affine hex；旧实际 54332 cells |
| 正式粗阶 | p4 | p4 |
| substrate/grating | Si，n=0.99396854453+0.00435380777i | Si，n=0.99880148307+0.000213688647i |
| 材料来源 | 已提交用户输入，density=2.33 g/cm3，epsilon=n*n | 同左，不自行数据库替换 |
| DtN inventory | 原规则重新核对全部 600 通道 | 原规则重新核对全部 3904 通道，旧 propagating=3902 |
| 比较对象 | 已完成旧 5 nm fullspace BAL_H | 未完成旧 2 nm fullspace 构建/停止记录；无旧完整解 |
| 建议新输入 | `input/task39extra_para_workstation_capacity/original_5nm_si_p6h4_q4_speed_v4.dat` | `input/task39extra_para_workstation_capacity/original_2nm_si_p6h1p5_q4_speed_v4.dat` |
| 建议新 profile | `dual_condensed_speed_native_5nm_q4_v4` | `dual_condensed_speed_native_2nm_q4_v4` |

两场共同：50×25 nm 周期，z=-10…130 nm；原 grating x/y 宽17/25 nm、高120 nm、substrate厚10 nm，无 notch；1° grazing、azimuth0、s、幅值1；air n=1、mu_r=1；双 Floquet、原 Fourier-DtN/背景与端口符号。top/bottom 探针127.5/−7.5 nm，内部平面10/30/60/90/110 nm及原采样侧别不变。

旧 task 中的 W 标签已由后续用户的 Si 输入明确替代；本批不恢复旧标签。两场材料不同，不把跨波长时间变化称为纯网格单变量结果。实际网格坐标、cell/tag、约束与 mode identity 分别绑定；不得引入源 990-cell 的 neutral alignment planes、源80通道或旧13.5 nm行数硬编码。

5 nm 历史 run=`20260911T065955.813489Z`，source=`85a681b9bd61104466888546b83df87c27806169`，physical SHA=`96b548e4cd7fbec7f5397d6be7fa22cf5f9e0faaaeb2f70ff95cf01f0f8af88d`。2 nm 历史 run=`20260918T035017.294454Z`，source=`41caf5141493ad6c5d6c518a64ee74fda8d7a7db`，physical SHA=`fb8d259274ea968deb243ab9fa2b5c360b74f19dd8ebcf606aeba643cb59b6ef`。新 input/source SHA 重新计算；若新 schema 的 physical hash 包含执行字段，保存逐字段物理等价桥，不强填旧 hash。

相同配置算出的 mode 数或几何与旧事实不符时先调查身份原因，不减通道迎合预期，也不仅凭通道数量相同认定全量 keys 等价。600/3904是匹配锚点，不取代计算 inventory。源 Q3 可迁入通用 degree=3 参数或独立组件 profile，但本批只允许其小型验证。

## 5. 工作站运行、资源政策与证据连续性

延续已授权 V3：**worker CPU23、父监督器CPU9、MPI1、所有数学库线程1；两场顺序运行。** 不为了追平笔记本51分钟切核心/加线程，不更换系统 BLAS 或源的 WSL 栈。CPU23/preferred_node1/允许node0,1沿目标既有设置并读回，记录实际 NUMA 页面、可得频率/温度和邻负载；观察不到写 unknown，不能宣称无共享带宽竞争。

优先沿工作站现有 task-local complex128/PETSc int64/PORD64 栈，验证实际 Python、NumPy/SciPy、PETSc/petsc4py、DOLFINx/MPC/Basix/FFCx、MPI 与动态库映射；不复制笔记本二进制或编译 cache。局部索引与全局 rows/NNZ/CSR 指针分别核对范围，不能把源 int32 cast 直接用于可能溢出的全局结构。ABI 两场尽量一致并冻结；与旧5 nm不同则明示工程比较限制。

```text
resource_stop_policy        = measured_tree_rss_only_v3
rss_hard_limit_bytes        = 1300000000000  # decimal 1300 GB
rss_warning_bytes           = 1170000000000
swap/global_swap/faults     = observe_only
prediction_admission        = record_only
memavailable_runtime       = observe_and_warn_only
time_limit_mode            = none
screen128                   = progress_only; not a termination gate
MUMPS_ICNTL23              = 0; read back; no laptop-derived memory quota
```

仅对本批新 profile 继承该策略，不放宽旧 profile。实际可读的本任务同期整树 RSS 达 Gate 时立即按已验证机制停止和清场；预测、后端 allocated/used、swap 或全机小量换页不单独触发政策停止。**必须检查全链路，包括外部 service/wrapper、worker、粗因子、retained构建和checker，不能把源最新 wrapper 的 strict/observe 不一致再次带进来。** 启动前有实际内存/cgroup/磁盘与系统余量检查，沿目标启动余量128 GiB；不能通过预测×2、静态对象库存或源4687 MB额度重新拒绝已授权的 numeric。

不关闭安全监督，不执行全机 swapoff、swappiness、memory.swap.max、系统服务、热保护或邻任务修改。持续监控丢失、数值失败、不可恢复的实现/I/O错误、用户停止、max2048仍要正确收口；正常退出尾样本不可读不是新根因。换页如实记录 `SWAP_OBSERVED` 或全局归因未决，RSS-policy通过不等于严格zero-swap/0.7 nm生产资格；OS自身OOM或管理员信号也不是本代码可保证避免的事件。

本任务不并发自己的5/2 nm。隔壁Hybrid独立，既有授权并跑事实可记录，但不得修改或停止其进程；资源不满足启动条件时等待而非抢占。本机代码/输出/worktree独立，SSH断开不应令父监督器消失，正式前做一次已运行入口的轻量生存/清场检查。读旧源用于迁移，不操作笔记本。

## 6. 执行顺序：准备复用，5 nm 通过后自动进入 2 nm

| 阶段 | 内容 | 继续条件 |
|---|---|---|
| M0 | 确认两端SHA、目标已有D1/D2代码/测试、旧运行清场；记录增量迁移清单、两场输入及选择矩阵 | 保留已有工作和历史，没有身份冲突 |
| M1 | Codex集成r2快路径、p3可选接口、有界粗修复；复用并贯通native RSS-only接线 | 组件import/配置与职责清楚，普通默认不变 |
| M2 | 一组合并的真实小FE/代数/监督测试；两种材料、q4/q3、真实边界及原A6 witness | 必要正确性和监督闭合；不以必须快几倍作为入场门槛 |
| F5 | clean source下，一场5 nm p6/h4、q4；同run setup核验→同因子KSP→恢复/原A6/物理/旧结果比较 | 数值、自身物理、适用的历史比较、当前资源与证据Gate通过 |
| F2 | F5通过后，无需再等一次用户批准，做一场2 nm p6/h1.5、q4 | 独立实际预检、同run构建和检查；完成或真实边界后收口 |
| Z | 汇总迁移、两场结果及旧对照、p3备选范围、未知与负结果；提交response_v5 | 推送本分支，集中review；不合并master |

M2 不能只用 mock：包括复非Hermitian/非零内部及端口RHS、Bi/Di、MPC复相位/方向、完整凝聚与原方程等价、J桥非交换反例、恢复、输入不变、重复调用、同因子精化、释放依赖；q3/q4各做真实小型粗解及直接传递测试。A6/H6 fast 对独立 native 使用操作尺度1e-10核验；H6对角/谱窗/seed与 power10 规则一致。小例也检查新流程实际未构造完整全局p6/p4大矩阵；源固定尺寸guard应参数化，不删掉所有guard。

源51分钟数值行为的短组件核对即可，不新增一场完整13.5 nm基准。按本批5/2 nm实际材料、局部几何类及积分验证，尤其不能用13.5 nm的小例替代所有短波检查。模式构建与完整F5/F2 setup身份在本run可复用已有对象验证，避免为一次探针重建大因子。q3独立备选组件若确有未闭合项，不写“已迁移通过”；只要与q4隔离且q4完整资格通过，可记录q3缺项并推进正式q4，不让备用研究无限拖延。

**F5→F2是本轮明确批准的两点计划，不再要求补做3 nm、旧notch或先执行旧V3。** 5 nm缺少旧完整数组时，优先复用已有600通道及可读物理采样；不足项标`REFERENCE_ARRAYS_PARTIAL`，不为补参考重跑60小时旧方法。适用比较和自身Gate通过可以进入F2，不能把“缺参考”改成“比较通过”。真实数值/物理/身份或监控失败未关闭，则F2保持未运行。

正常仅两场，不对q3/q4、旧/新或V26/r2各跑一轮完整短波。登记的真实实现bug允许每个case至多一次必要修复重放，保留失败、新source和根因；性能慢、内存达到Gate、真实不收敛不是bug replay。输出错误优先从同一保存解恢复，不能重解。新batch额度与旧V3/笔记本耗尽账本分开，不能用旧额度拒绝本次已授权首场。

## 7. 数值、物理、恢复与验收 Gate

| 检查 | 本批要求 |
|---|---|
| 主问题 | 完整恢复后独立原A6相对true residual≤1e-6；Schur残差另列，不能替代 |
| 粗返回 | 每次原Aq相对残差≤1e-10；最多2次额外同因子精化，裸值/修正值均保存 |
| 代数/MPC | 局部与组合操作尺度等价≤1e-10；原更严方向/约束要求不放宽；端口闭合≤1e-8 |
| 外层 | right FGMRES32/max2048，zero retained start，一个KSP；无warm-start/recycling或隐藏内层KSP |
| 检查频率 | 原A6每8步及最终；独立native见证、checkpoint沿r2已测合同；每32步保存可恢复场/身份，终态必存 |
| 自身物理 | abs(R+T+A_volume-1)≤1e-5、abs(A_balance-A_volume)≤1e-5；复E/H/curl、全部幅值/功率finite及被动性/通道和检查 |
| 新旧5 nm | R/T/A/A_volume最大绝对差≤1e-5；可用canonical场L2/scaled-curl/selected E/H相对差≤1e-4；全600复振幅相对差≤1e-4、逐通道功率绝对差≤1e-6 |
| 2 nm | 完整3904通道、自身数值/物理/资源/证据；无旧完整2 nm解，不编造旧场回归 |
| 资源资格 | 新policy从启动到清场的连续整树样本，RSS与swap/后端数据分列；无缺口才能给对应完整资源结论 |

源r2包含live fast action与独立native witness，不能为性能只保留候选自身检查。最终保存完整解与原A6残差/身份；先恢复必需内部场并保存最小packet，再销毁KSP/粗因子及无用矩阵，完成释放后同场残差/后处理。MUMPS仍借用矩阵时不得detach或提前销毁；恢复仍需要的局部LU不能提前释放。不为检查重建完整因子，不把allocator未回收说成RSS下降。

单场内原矩阵/缓存身份不变；跨机器浮点差异不要求逐字节相同，应按固定尺度核验并解释。相位、归一化和坐标不可事后拟合。非有限、粗逆仍超限、错方程、max2048未收敛或物理未过如实停止对应路径，不自动降q3、改h、缩几何或降mode。

成功仍只表示固定离散求解与一致性通过；没有p/h或独立误差资格不写网格收敛。p4凝聚后仍有增长型全局LU，不称factorization-free、通用production PC或0.7 nm已通过。原始短波结构通过也不直接外推任意非可分结构。

## 8. 时间、内存与旧方法的正确比较

旧工作站5 nm基线：[compact](outcomes/records/5nm_formal_attempt1.json)、[资源覆盖](outcomes/records/5nm_resource_coverage.json)。旧2 nm：[终态](outcomes/records/2nm_h1p5_measured_terminal_snapshot_v1.json)、[运行中阶段](outcomes/records/2nm_h1p5_measured_running_snapshot_v1.json)。

| 比较量 | 旧5 nm p6/h4 fullspace BAL_H | 边界 |
|---|---:|---|
| iterations / PC | 698 / 698 | 已测 |
| solve / workflow | 206568.51908412296 / 217665.16384237396 s | 历史计时；分别约57.38 / 60.46 h |
| p4 logical / MatSolve / refinements | 1396 / 1419 / 23 | 已测 |
| 原A6 residual | 9.986638454029182e-7 | own数值通过 |
| R / T | 0.7331834812424759 / 0.00022243948430485038 | own输出，通过但reference limited |
| A / A_volume | 0.26659407927321926 / 0.26659407694262094 | 独立能量差约2.33e-9 |
| RSS已观察峰 | 50161172480 B | 存在约8h34m监督断档；不是完整RSS authority |

新5 nm完整wall与旧217665.16 s比较；纯KSP与旧solve字段只有边界确认一致才给精确比值。区分少迭代、每步变快、setup变化与ABI/缓存/负载差异；51.90分钟只作源版本选择，不作为工作站验收时限或速度分母。

旧2 nm在numeric未完成、outer未开始时因全机71页活动停止，旧watchdog峰635625377792 B、另guard接管峰640141377536 B分别保留。它们不是旧方法完整峰值，34.36 d不是旧实测总时间。新2 nm只能和旧已完成的同scope阶段（如p4体装配105595.2284 s）比较，不能声称从“实测34天”加速到某时长，也不能据两个中途峰给完整内存节省率。

每场至少报告：full/independent/interior/slave/trace/port rows；粗矩阵stored/allocated NNZ、MUMPS symbolic/numeric/allocated/used/factor entries；去重局部cache与临时payload；p6准备、p4凝聚装配、H6对角/power10、LU、P/PH、A6/Aq、DtN、完整PC、纯KSP、原残差检查、恢复/输出/清场时间；完整及阶段RSS/PSS、swap、CPU/NUMA/ABI/JIT与邻负载。

父子inclusive计时不相加成wall，首次编译和warm缓存分列；真实发生于formal root的构建/核验不能从wall里扣除。derived bytes、MUMPS used/allocated不冒充RSS。对旧5 nm只能给“相对旧已观察峰”的限定比较，不追认旧连续RESOURCE_PASS；新慢/内存回退同样是有效结果，不自动追加参数扫描。

2 nm setup/numeric及前8/16/32/128步有单独marker和心跳，及时落盘真实成本；预计耗时只作规划，不成为隐藏停止条件。不要求numeric结束就重建对象去做另一轮基准。若仍然很慢，保存具体热点与运行状态供用户判断，不自动改变当前方程或计算身份。

## 9. Codex提交与交付

建议提交顺序：M0/M1增量集成与测试；M2新profile/输入/监督及真实小资格；冻结正式数值source；F5证据与阶段结论；条件F2证据；Z收口。两场尽量用同一数值实现，source与后续文档提交分别记录。正式前clean，运行中不pull/切分支/改库；同时写文档时使用独立文档工作树并保留正在运行的源码SHA。

全部写入当前执行分支，源task39extra/Hybrid/master只读，不amend、不强推、不整体合并。只新增必要配置与数值模块，旧profile行为可回归。迁移源码由Codex执行，本review提交不代表已经完成任何功能迁移或新PDE。

至少覆盖下列轻量内容，可合理合并文件但不能缺信息：

```text
docs/task39extra_para_workstation_capacity/response_v5.md
outcomes/q4_speed_shortwave_v4.md
outcomes/records/q4_speed_v4_migration.json
outcomes/records/q4_speed_v4_components_and_policy.json
outcomes/records/q4_speed_5nm_v4_compact.json
outcomes/records/q4_speed_5nm_v4_checker.json
outcomes/records/q4_speed_2nm_v4_compact.json
outcomes/records/q4_speed_2nm_v4_checker.json
outcomes/records/q4_speed_v4_comparison_and_decision.json
outcomes/summary.md / outcomes/test_summary.md / outcomes/records/run_index.json
```

每场保留input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json；环境/MPI/线程/affinity/实际policy、网格/mode身份、原残差与完整资源/输出hash不可少。大矩阵、因子、场、cache、长资源日志在ignored，不上传Git。必要计数用标量流式写入，不每次PC导出巨型数组。

同步本分支development_progress/model_registry；保留V3准备已有代码、旧swap停止、源Q3成功/Q2未完成、旧h7.5 A4缺项及其后续修复各自历史。执行最小相关真实FE/监督/旧profile回归、compileall/diff、文档与渲染检查；未跑全库/CI如实记。源码分支最新研究未完成不是阻塞本批已冻结成果的理由。

Response首屏必须回答：实际迁入哪套r2/sum-factorized/p3功能；目标已有D2复用了哪些；新5 nm/2 nm是否各自完成及具体Gate；是否仍固定CPU23/MPI1/thread1、RSS-only全链路是否一致；5 nm相对旧方法的可靠收益与限制；2 nm的真实阶段/步数/成本和未闭合精度；p3组件是否合格但未跑短波；完整commit、测试、异常、源与目标差异。

**正常交付：Codex完成可审计的功能迁移，p4正式5 nm通过后继续p4正式2 nm；p3作为已迁入、经小资格的备选能力。不要把两个分支整体合并，不再执行过期V3长场，也不要把51.90分钟或“2 TB应该够”当成短波成功保证。**
