# Task40extra：0.7 nm三维Maxwell工程路线——笔记本起步任务书

## 0. 目标、权限与执行身份

**首先消除的blocker：目前缺少一组真实0.7 nm材料、三维非可分几何、完整端口和可复核场输出的笔记本PDE，以及用于区分“离散不够准”和“求解器不够可扩展”的基准。首批先用已经成功的双凝聚准确p4路线把这件事完成，再决定下一项无全局大因子的工程候选。**

最终目标为：约2 TB整机物理内存的单节点上，得到0.7 nm、complex128、Nédélec H(curl)、x/y双Floquet、z开放Fourier-DtN、周期单胞内任意非可分三维Maxwell的准确可复现工程解，输出复E/H、R/T/A、体吸收、全部衍射级和近场。**首批缩小几何的成功只关闭一部分问题，不称目标尺寸成功。**

```text
repository                     = Rookie1234567/MyFEniCS
task_id                        = Task40extra_0p7nm_engineering
execution_branch               = task40extra_0p7nm_engineering
task_directory                 = docs/task40extra_0p7nm_engineering
parent_branch                  = task39extra
reviewed_parent_evidence_SHA   = e09bd1612c4f6ca5fb5cf3572835748ad5c16207
branch_base_SHA                 = 7bb3243e657cbeecfff974f985f09569bfa6e094 (closeout ancestor; see provenance)
branch_binding_record          = branch_provenance.json
parent_final_report            = ../task039_extra_physical_multilevel/final_report.md
phase_I_response               = response_v1.md
phase_I_execution              = N0 -> N1 -> N2 -> N3 -> N4 -> conditional N5 -> N6
phase_I_normal_formal_PDEs      = 2 iterative + at most 1 same-discrete direct reference
phase_I_MPI_math_threads        = 1 / 1
workstation_changes            = NOT_AUTHORIZED
ordinary_default_change        = NOT_APPROVED
master_merge                   = NOT_APPROVED
```

### 0.1 分支base不能猜
本轮用户选择B线：保留远端已存在的`task40extra_0p7nm_engineering`及其全部提交，不新建、重命名、reset、rebase或强推分支。既有Task40分支原始base为`95dacd01e86f0f7f1d29ee2d5e5a16039bb41871`，续作前远端HEAD为`ffd89005096590c106324b6bb39a8d17c96a87ff`。Task39收口提交`7bb3243e657cbeecfff974f985f09569bfa6e094`通过普通非快进merge成为第二父提交；当前merge commit为`3e961a2bf3f547dce5b8829c6cfab74befb26dd4`。因此收口SHA是当前Task40的祖先，但不能声称此既有分支最初从该SHA创建。

`branch_provenance.json`记录真实关系：`branch_base_sha`绑定已成为祖先的Task39收口SHA；另列原始Task40 base、续作前远端HEAD、merge commit和两父提交。还要记录`reviewed_parent_evidence_sha`、父报告Git blob与文件SHA256、父closeout response路径、用户选择与范围、canonical linked-worktree身份、UTC记录时间及交付包manifest SHA256。实现前确认closeout祖先关系、remote upstream与工作树；不得修改master。

本任务与已存在的Task040/Hybrid-side任务无关。父任务的普通数值资产继承，但旧任务一次性实验额度、8GiB停止线、13.5nm默认物理身份和工作站许可不继承。

### 0.2 第一批的优先级

**第一优先是0.7nm完整小模型，不是又写一份容量预测后停审。** 首批不要求先研制出通用无全局因子PC才能运行，也不允许完成一个便宜辅助方程就声称真实Maxwell已解。

继承准确p4作为小规模可靠求解工具；明确记录它是reference/bridge engineering路线。后续生产路线必须摆脱全域p4因子的无界增长，但应在首批真实误差与成本证据基础上设计，不能在本批同时铺开AMG、LOR、PML、DD、神经网络、GPU多个方向。

## 1. 必须阅读的材料与继承原则

先读根AGENTS、docs/AGENTS、仓库工作原则、[父最终报告](../task039_extra_physical_multilevel/final_report.md)、[父收口review](../task039_extra_physical_multilevel/review_report_v30.md)、父response_v33/v34及其证据。涉及源码时读相应目录AGENTS。历史方法背景只需查与新候选直接相关的父`prior_attempts_retrospective.md`和`literature_review.md`，不重写全项目历史。

首批继承：装配时单元凝聚、p6 trace/port外层、同网格准确p4、BAL_H、A6融合、完整快速A4、blocked Gram、reference-metric H6对角、H6自然序、PSS禁用/快速RSS监督、正确恢复和独立原A6检查。

不依赖“函数名有0.7nm参数就一定生效”。必须检查旧runner中的固定13.5nm材料、几何、参考hash、积分/端口和后处理常量。必要的0.7nm参数化进入通用src模块和dat/schema；benchmark只编排、核验，不复制另一份巨型任务求解器。

## 2. 第一批物理与几何合同

### 2.1 真正的0.7nm材料

真空波长固定为 **0.7 nm**；air/vacuum与Si为首批材料，mu_r沿既有非磁模型。Si的复折射率必须来自已有正式0.7nm材料记录及其原始出处；如果本分支不含该记录，可读取其他任务已审阅的材料包，选择性复制数据并记录source SHA，不能整分支迁移算法。

找不到合格记录时，允许从官方CXRO/Henke等原始材料来源建立一次材料记录：保存原始数据、密度、波长/能量单位、插值方法、邻近吸收边处理、时间谐波与n/epsilon符号约定，原始数据hash和输出数值。不得拿13.5nm或2nm的n直接使用，不靠只修改k0冒充0.7nm。公开数据库结果不能写成现场测量。

核对：0.7nm输入贯穿k0、复epsilon、入射相位、Floquet alpha、DtN外部纵向波数与功率归一化、H重建、体吸收。生成新的physical-model SHA。

若材料来源缺失或矛盾，物理PDE为`MATERIAL_BLOCKED`。可继续不依赖该材料的纯代数测试和文档，但不得用未知材料启动“正式0.7nm”求解。**本文件不编造一个0.7nm Si数值。**

### 2.2 小电尺寸、三维非可分测试单胞

为在笔记本上得到完整参考链，将父任务的几何长度统一乘以：

```math
s=\frac{0.7}{13.5}=\frac{7}{135}.
```

以nm为单位，定义**新的解析几何benchmark**：

| 几何 | 解析定义 |
|---|---|
| 周期单胞x | 从-25s到25s，周期50s，约2.592593nm |
| 周期单胞y | 从-12.5s到12.5s，周期25s，约1.296296nm |
| z域 | 从-10s到130s，总高140s，约7.259259nm |
| 下部Si区域 | z小于0直到下端口；下端外部半空间材料为Si |
| 主grating | x从-8.5s到8.5s，所有y，z从0到120s，Si |
| 三维缺口 | 从主grating扣除air盒：x从0到8.5s，y从-6.25s到6.25s，z从40s到80s |
| 其他区域 | air；上端外部半空间air |

缺口在x/y/z同时有有限范围，材料分布既不是沿y均匀，也不是沿z简单挤出；记录材料集合在三个方向的切片/体积分数，核实没有空缺口。此几何按解析边界固定，**不是把旧网格cell-center筛选后的几何误称为相同实体**。它也不是用户最终实际器件的代理证明。

仍采用原1° grazing、azimuth0°、s偏振、同归一化入射。两个水平端口位于各自均匀材料区。首次输出几何、材料与方向图可用既有网格可视化，不能只靠tag数量判断非可分。

缩小后部分特征处在很小的长度尺度；本task验证的是既定连续介质Maxwell数值模型，不证明局部bulk介电模型在原子尺度上的适用性，更不以该模型作制造结论。

### 2.3 两张边界拟合网格，物理几何完全相同

必须包含以下平面（整列乘s）：

```text
x: -25, -8.5, 0, 8.5, 25
y: -12.5, -6.25, 6.25, 12.5
z: -10, 0, 40, 80, 120, 130
```

各相邻平面之间均匀细分，按真实长度与目标h的比值向上取整；整数/有理数计算或明确稳健规则避免浮点ceil多切一格。六面体方向/MPC按生产路径。冻结两个mesh的解析平面、轴分点、实际cell数和几何hash。

| mesh_id | 最大目标边长 | 预期轴段数 | 预期cell数 | 用途 |
|---|---:|---|---:|---|
| G0 | 10s nm，约0.518519nm | 6×4×14 | 336 | 第一场真实0.7nm非可分PDE；同离散参考对象 |
| G1 | 7.5s nm，约0.388889nm | 10×4×22 | 880 | 同几何h细化，判断误差与资源增长 |

这些数目是由上述规则**派生的计划值**，正式仍由网格构建核验；不把派生值标measured。G0与G1不要求嵌套，但几何实体、材料、入射和外部模式合同相同。p6最终空间和同网格p4首批固定。端口/材料边界不能因重划网格移动。

这两张网格只用于形成第一组误差趋势，**0.388889nm不是已经证明足够的工程网格**。不得为取得pass随意移动缺口、增加损耗、减少通道或改低阶。无法容纳G1时保留G0结果及容量blocker，不临时缩小几何而保留同一case名称。

### 2.4 实际外部通道与积分

按0.7nm、实际周期、外部材料、入射Bloch向量和既有合格截断规则重新生成ordered keys、传播/倏逝统计及近cutoff信息。**不强制沿用80通道，也不能为省内存只取几个零阶。**

G0/G1同物理比较使用同一份合格外部key清单；若算法生成与mesh绑定的不同截断，先固定覆盖两网格的共同清单，记录不混为纯h误差。对未做独立截断收敛的部分写`CHANNEL_TRUNCATION_UNQUALIFIED`，不因能量闭合小就声称cutoff已足够。

体积、端口、质量、curl及功率积分规则沿既有正确实现，明确identity。不同项规则不强行合并。真实Maxwell非Hermitian，不能在端口左右耦合或复材料上额外共轭。

## 3. 首批解法：先可靠得到场，再谈扩展性

### 3.1 准确p4双凝聚首批路线

```math
A_6x=b_6,\qquad
C_4=P_{64}F_4P_{64}^{H},\qquad
M_6=C_4+(I-C_4A_6)H_6(I-A_6C_4).
```

p6在trace/端口空间运行right FGMRES32/max2048、零初值；不装全局p6矩阵。p4装配时单元凝聚后分解一次，MUMPS现有后端/排序/主元/BLR/OOC/线程设置保持。H6保持相同数学处理、power10种子规则及20次B6，不直接复制旧13.5nm谱窗数值。

p4初次求解和每次额外精化后**完整原A4检查**，目标1e-10，最多两次额外同因子精化。未达目标但有限、约束与端口状态完整时返回最佳同一FE/alpha/A4c/e状态继续FGMRES；NaN/Inf、因子或实现损坏仍停止。不能为了更快降低检查频率或引入便宜筛查。

0.7nm下还须核对相容传递、A4与P^H A6 P的体积/端口作用、凝聚与恢复的非零内部及端口RHS一致性。**更短波长允许真实PC表现改变，不能只因旧例126步就强求新例同样步数。**

### 3.2 独立参考：条件性一场，不绑架首个结果

在G0迭代及G1完成后，若没有同离散独立参考且预检显示安全，允许**最多一场G0的完整p6凝聚直接reference**。用独立原FFCx/native体积积分路径与原端口定义装配p6凝聚系统，MUMPS后端保持，最终恢复并计算原A6残差。它只用于小例reference，不能成为新生产路线的“兜底”。

先检查实际行数、NNZ、symbolic与当前可用内存以及必要恢复空间，不能等OS OOM。reference不安全则`REFERENCE_RESOURCE_BLOCKED`，不增加额度、不通过粗化后冒称同离散、不自动另开几场参考。已有独立数据身份确实匹配则直接复用而不重复PDE。

独立参考解希望原A6<=1e-10；未达到时报告其真实精度，不用较差reference给更细解授予强精度资格。凝聚实现部分共享不能证明全部代码独立；以独立原A6、局部积分对照和可追溯reference范围共同限定结论。

### 3.3 内核与生命周期只作必要参数化

保持V31成功内核。仅为新0.7nm配置支持、正确性、明确的无用对象重叠或必要provenance做修改；不再以同一小模型扫描batch/einsum/库版本。必要JIT可在大factor前准备，编译成本和后代RSS纳入同一run，不用未计账预热制造加速。

局部缓存按真实几何/材料/方向身份复用。记录unique backing-buffer字节，不能把view按对象id重复相加。首批不新增尺寸舍入来合并不同单元，不为每个cell复制一个全矩阵/全inverse。当前几何类型有限的优势必须明示，不能当一般曲面网格的内存承诺。

## 4. N0–N6连续执行及数量

| 阶段 | 工作 | 完成与进入下一步条件 |
|---|---|---|
| N0 | 完成父任务离线收口，绑定新分支base；核对ABI/线程/输入路径/所有旧硬编码 | 新分支真实HEAD与依赖可追踪；不运行旧13.5nm重演 |
| N1 | 正式0.7nm材料来源；解析非可分几何；G0/G1 axes、mode inventory、provenance冻结 | 材料/外部定义未知则停止物理PDE，不用旧值 |
| N2 | 一批最小组件测试：波长贯通、P/PH、A4投影、局部凝聚/恢复、非零port RHS、独立A6和监控 | 使用生产src；不只mock矩阵，复用未变旧测试；不建立额外全局工程factor |
| N3 | 第一场G0、0.7nm非可分、p6/p4双凝聚完整iterative | 无安全/真实实现错误则完成到原A6判据；立刻保存完整场/功率/计时 |
| N4 | G0通过且G1安全时，同几何G1完整iterative；离线h比较 | 不在G0小成功后停审；G1资源不够则记录，不改变已冻结物理 |
| N5 | 条件G0独立direct参考一场；离线同离散比较 | reference不可容纳不反复试；缺口保持，不否定已完成的原A6求解 |
| N6 | 三阶段时间/内存、h精度、通道边界、2TB容量起点与下一候选决策，response_v1并push | 全部正负结果集中收口；不自动启动Phase II或工作站 |

正常最多3场正式PDE：G0 iterative、G1 iterative、条件G0 direct。N2最多一个合并的tiny实体场fixture（至多64cells）用于波长/边界贯通；它是诊断，明确记录成本，不隐藏成免费验证。纯代数测试无须新PDE。不得给每个局部函数分别建立全局因子。

新case路径建议：

```text
input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4.dat
input/task40extra_0p7nm_engineering/nonseparable_g1_p6_q4.dat
input/task40extra_0p7nm_engineering/nonseparable_g0_p6_direct_reference.dat
```

所有正式运行均经 `python scripts/run_case.py ...dat` 和合格独立watchdog。source提交且clean后启动。不是只做setup/action后留在`WAITING_FOR_MAIN_REVIEW`；完成当前被授权可执行阶段后集中回应。遇到真正安全/数值失败，保存结果并停止受影响后续运行，不暗换方法重试。

## 5. 数值、物理、离散与性能Gate分开

### 5.1 每场求解Gate

原A6相对残差及释放后检查均<=1e-6。保留每8步完整原A6、每32步场/解checkpoint和终态检查。reported retained残差与原A6残差各自说明归一化，不混合拟合收敛率。达到max2048未达标为该配置`NUMERICAL_FAIL`，不是所有Full3D不可能。

E/H/旋度、全部有序通道复振幅与功率、R/T/A_balance/A_volume均输出有限值；R+T+A_volume与A_balance-A_volume绝对闭合<=1e-5，通道求和一致。零级反射按s/p分别记录。official结果只在原A6通过后生成；停止场的诊断量与正式量分开。

### 5.2 同离散reference Gate

G0直接reference与G0iterative：FE L2/scaled-curl、同坐标E/H、模式复幅值相对差<=1e-4，R/T/A/A_volume绝对差<=1e-5，逐模式功率绝对差<=1e-6。近零量同时报告绝对差，不拟合全局相位。若reference不存在，明确`AUTHORITY_LIMITED`，不能把能量恒等式代替全场对照。

### 5.3 h细化的工程观察门槛

G0/G1几何、材料与keys相同，使用共同物理坐标和稳定跨网格积分/投影；不比较不同自由度编号的裸数组。报告总E/H、散射E/H和scaled-curl：只看总场可能掩盖弱散射误差。散射量按同一入射场定义，近零分母用入射场尺度给出绝对误差，不靠除以近零值下结论。

首批工程目标：体积/固定采样的E/H和scaled-curl相对变化<=1%，R/T/A/A_volume绝对变化<=1e-3，并报告每个显著衍射级的变化。散射场额外报告相对变化与入射归一化绝对变化，缺口棱角不以奇异点单一max范数代替整体误差；界面邻域结果单列。

这些是**新研究的工程接受目标，不是已证明误差估计器**。两张网格接近只能称`TESTED_H_AGREEMENT`，不能称连续极限已收敛；未达到则`DISCRETIZATION_UNQUALIFIED`，保留两份真实场并给下一次有针对性的h/p计划，不自动多跑第三张网格。

### 5.4 性能与容量Gate

比较同场setup、factor、所有PC局部求解总次数、A6/H6/A4、桥接、Krylov、固定检查、恢复/输出和全过程wall/CPU/RSS。父子计时不可重复相加；warm JIT、数字缓存build、compiler时段和峰值所属成员都说明。

速度没有预定“必须126步/38分钟”的目标。首批交付优先是**真实0.7nm完整解 + 可追溯成本**；不为未出现预期提速重跑。未获独立匹配精度时，不把某个粗网格最快结果称为工程最优网格。

## 6. 资源、环境与停止策略

首批在笔记本已资格化WSL/Linux环境，使用其实际DOLFINx/Basix/PETSc版本、complex128、实际IntType，不能根据长期目标标签假定v0.10或int64已经安装。数学库环境和运行时库线程读回写入manifest；MPI1、数学线程1、接电、固定电源模式。一台机器一次一个heavy，不与旧任务同时计算。

沿可解释的physical-memory-pressure监督：每场读取真实MemAvailable、effective RAM/cgroup、当前使用量和OS/监督余量，冻结本场`resource_policy.json`并记录实际stop authority、单位与scope。RSS成绩、derived库存、cgroup current、MUMPS used不能混作阈值。**不继承旧8GiB停止线，不把旧13.3GB启动cap当新场常数；真实系统或cgroup限制也不能忽略。**

新首批要求任务scope不使用swap来撑预算。启动前记录任务和系统基线，运行中用快速status/任务cgroup的适用计数观察；本任务VmSwap出现非零应按显式新策略受控停止并保留证据，不改OS全局swap配置。全机已有累计换出页数不擅自归因本任务。旧任务observe-only历史不追溯改写；若环境只能提供观察而不能证明任务scope，应标资源证据不足，不能声称强制zero-swap通过。

PSS禁用时写null/状态；仍保留RSS/status、进程身份、系统余量、失联、超限、后代清场。必要JIT和checker子进程不能逃出范围。OOM不是正常验收机制。reference symbolic只用来做该reference的预审，不把旧固定2×symbolic公式重新用作整个任务普遍否决线。

本批不靠任意时间线停止已授权计算；默认time observe_only并记录全部成本，max迭代与真实安全规则保持。性能不佳、超过旧步数或内存成绩不是实现bug。真正实现bug只做最小修复，保留旧attempt/source/raw证据，最多一次受影响case的定向重放；不用于数值不收敛、资源不足或重复挑选快样本。

## 7. 面向2TB的容量研究：必须同时记录的增长项

本批N6用已有两次真实小模型和工作站固定快照建立起点，不启动目标规模factor。公式推导必须写清假设，不能由两点宣称渐近容量已校准。

```math
M_{\mathrm{peak}}=\max_t\{M_{\mathrm{mesh}}+M_{\mathrm{operators}}+M_{\mathrm{local}}+
M_{\mathrm{coarse}}+M_{\mathrm{ports}}+M_{\mathrm{Krylov}}+M_{\mathrm{other}}\}(t).
```

```math
M_{\mathrm{main\,FGMRES\,vectors}}\simeq16N_{\Gamma}(2m+1).
```

需要分别列出：独立FE/trace行数、原始/定向局部类型数量、局部LU/恢复/Schur真实backing库存、p4矩阵与后端allocated/used、各live Krylov及工作向量、端口原始carrier/派生块、MPI复制、JIT及输出重叠。小例几何类型重复好，不代表一般几何不会出现每cell独立稠密缓存。

可对同一解析族的长度倍率1.5和2做**纯计数与有界metadata**评估，保持0.7nm和已定义解析能力，重新生成通道inventory；不做全尺寸网格大数组、全局矩阵或因子。明确电尺寸k0L确实增大，而不是继续同步缩λ与L制造虚假的扩展性。

工作站冻结2nm数据只引用其source/snapshot：已经双凝聚，仍有约916.7GB MUMPS used和约106GB端口数组库存，说明全局p4和显式大耦合不能无界扩大。2TB是总物理内存，不是可分配单程序RSS；正式迁移时必须另定资源余量、ABI/int64及并发规则，不能直接沿用笔记本cap。

## 8. Phase II路线图：本批不自动执行，但下一review必须作选择

首批完成后，以真实误差与成本选**一个**主候选，不再提出一长串名称并逐一抽签。

### 8.1 首选架构方向：有界局部问题 + 多层全局波动纠错

目的不是继续寻找“又低内存、又几乎精确的全局p4逆”，而是让整个p6问题不依赖一个覆盖全域的大因子。示意：

```math
\mathcal M_\Gamma r=\mathcal M_{\mathrm{local}}r+
P_0\mathcal C_0R_0\bigl(r-S_\Gamma\mathcal M_{\mathrm{local}}r\bigr).
```

局部问题有明确尺寸上限；全局纠错需要处理真实跨子域传播/反射，而不只是正定低频误差。粗层继续分层/有限迭代，最低层直接问题有界；所有局部因子**总和**也要纳入预算。保留原始A6/DtN，辅助吸收只在PC内，不能给真实材料加损耗。

这不是把旧42宏块换名复做：必须说明新增的传播/接口/粗空间机制，读取父任务相关负结果，给固定同物理的准确p4参考对照。内部有限工作后可返回不精确修正，由FGMRES和最终A6判断；不要求每个局部问题都达到1e-10，也不把昂贵内部数百步藏在“外层少步”后面。

low-order-refined/de Rham相容辅助空间可作为高阶局部处理候选；它不是同网格直接降到p1，也不是对高频不定Maxwell的自动保证。相关理论主要覆盖对应扩散型辅助算子。参数、局部边界、coarse机制与验证次序须在下一review冻结后才执行。

### 8.2 端口和缓存方向

高通道组件必须使用接近真实p6的450内部/432trace尺寸及左右独立耦合，不再主要依赖2×2局部玩具证明工作站可扩展。以少量真实局部块、逐级通道数和有界scratch比较缓存/分块/流式；同时报告重复local solve时间。不能只省内存却将每次作用拖慢几个数量级。

曲面或变化材料下，局部稠密缓存可能比Krylov更先超预算：研究类型共享、受控缓存、结构化局部解/重计算或完整空间matrix-free的权衡。双凝聚是本任务的可靠起点，不是强制所有后续任意几何永远采用的唯一表示。

### 8.3 验证阶梯

首批缩小几何0.7nm → 同物理误差资格 → 增大电尺寸的有限序列 → 单节点分布/共享内存实现 → 已有5nm或适当中间波长迁移锚点 → reduced/非可分0.7nm扩大 → 目标尺寸。当前主张不等于现有worker已具备这些能力。

Hybrid可利用结构中真实可模态传播区域，但本任务不以沿z均匀/准二维/层平均/RCWA代替非可分Full3D核心。多核/GPU后续可以验证，不在首批为加速MUMPS自动改变环境。

## 9. 允许/禁止修改和代码组织

| 范围 | 决定 |
|---|---|
| 新材料/解析几何/网格与0.7nm输入 | 允许，必须显式新身份和独立记录 |
| 通用src参数化与必要正确性修复 | 允许，最小可说明改动和对应测试 |
| 新profile、run_case接线、必要checker | 允许；旧普通默认及schema行为不变 |
| MUMPS更换、排序/主元/BLR/OOC/线程扫描 | 禁止首批尝试 |
| 旧task39extra数值源码或历史结果反向改写 | 禁止；后续新数值实现留本分支 |
| 工作站SSH操作、热改、迁移、5nm/2nm/目标0.7nmheavy | 未授权 |
| 同时实现新的DD/LOR/FFT/NN/GPU方法 | 未授权；Phase II由下一review选择 |
| 减少物理通道、降低完整A4检查频率、拟合输出相位 | 禁止 |
| 新branch合并master | 未批准 |

## 10. 提交、交付与首批成功定义

建议提交：T0新任务文档/provenance；T1材料和几何/dat及必要schema；T2通用实现/组件资格后冻结clean source；T3G0结果；T4G1/条件reference及最终response。正式运行期间不得热改数值worktree。小测试集中，不要求每个阶段等待主控，但授权范围结束后停止扩展。

```text
README.md
task.md
branch_provenance.json
response_v1.md
outcomes/summary.md
outcomes/test_summary.md
outcomes/material_and_geometry_identity.md
outcomes/accuracy_and_capacity.md
outcomes/records/run_index.json
outcomes/records/phase_I_contract.json
outcomes/records/phase_I_results.json
```

可合并轻量证据文件，但每个数字要有raw字段/路径/hash；重型数据留ignored artifact。更新`docs/development_progress.md`和`docs/development_model_registry.md`的新Task40extra小节，不改父历史。所有新增公式用fenced math，GitHub渲染和文档合同检查如实记录。

`response_v1.md`首先回答：是否真正得到0.7nm非可分三维FE解，哪个mesh、准确到什么证据范围，setup/KSP/输出及峰值各多少；h细化是否支持工程网格；p4全局因子、端口及局部库存谁限制扩展；下一项**唯一主候选**是什么。不能只给多个PASS布尔值。

| 状态 | 能说什么 |
|---|---|
| `REDUCED_0P7NM_DISCRETE_SOLVE_PASS` | 至少G0真实0.7nm原A6、恢复、输出通过；不是目标尺寸通过 |
| `TESTED_H_AGREEMENT` | 两网格达到明示工程比较目标；不称连续极限证明 |
| `MATCHED_DISCRETE_REFERENCE_PASS` | 与实际同离散独立reference比较通过 |
| `AUTHORITY_LIMITED` / `DISCRETIZATION_UNQUALIFIED` | 求解可通过，但reference/网格或通道资格有缺口 |
| `NUMERICAL_FAIL` / `RESOURCE_BLOCKED` / `MATERIAL_BLOCKED` | 明确哪个case哪个门、实际值与规则；保留负结果 |
| `TARGET_SCALE_0P7NM_PASS` | 本批不授予；只有后续目标尺度与完整误差/资源证明才能授予 |

**这份任务书授权的是快速形成0.7nm工程起点和有效证据，不承诺首批就解决任意三维目标规模。不得因此退回只做文档：材料与资格齐备时应完成已授权的真实PDE。**

## 11. 外部技术依据与阅读边界

- [CXRO官方X-Ray Interactions With Matter](https://henke.lbl.gov/)：材料来源入口；正式数值仍须保存实际数据与处理流程。
- [Pazner、Kolev、Dohrmann：Low-order preconditioning for the high-order finite element de Rham complex](https://arxiv.org/abs/2203.02465)：低阶细分辅助空间及H(curl)等问题的理论/实现，不是本项目高频不定DtN系统的现成收敛保证。
- [Bonazzoli等：Domain decomposition preconditioning for high-frequency time-harmonic Maxwell equations with absorption](https://arxiv.org/abs/1711.03789)：说明吸收、子域、粗空间与尺度条件的重要性；不将其充分条件自动套用到真实弱损耗材料。
- 父[历史经验](../task039_extra_physical_multilevel/prior_attempts_retrospective.md)与[文献报告](../task039_extra_physical_multilevel/literature_review.md)：避免重做已知无收益组合。
