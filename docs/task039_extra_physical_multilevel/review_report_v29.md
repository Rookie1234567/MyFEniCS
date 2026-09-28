# Task39extra Review V29：V30证据闭合与反向投影单主线优化

## 0. 本轮决定与执行身份

**V30的同离散解可信，但未获得端到端提速，且整树峰值比V29高约718 MB。本轮先用已有文件补清setup、峰值和版本化检查器，再只尝试一条新的在线优化：统一张量积内部积分点顺序，并优化反向投影的固定形状收缩。仍在笔记本验证，不改工作站。**

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task39extra
review_date                = 2026-09-29
reviewed_base_HEAD         = 3d631d9cdf99d281fe971f008a5f33467244be73
base_latest_commit         = docs(task39extra): close out V30 workstation-guided run
previous_review_response   = review_report_v28.md / response_v31.md
V30_formal_source          = 254f0cf78f950246655dc86af9409139b9a97680
V29_speed_baseline_source  = 780f58918b0e5a9868cd2ea3de26d451bc6b5d86
batch_id                   = review_v29_evidence_and_projection_v31
suggested_profile          = physical_p6_trace_projection_layout_v31
suggested_input            = input/task39extra/v31_projection_layout_original_h7p5.dat
suggested_run_id           = task39extra_v31_projection_layout_original_h7p5_v1
response_required          = response_v32.md
execution                  = R0 -> R1 -> R2 -> R3 -> conditional R4 -> R5
normal_new_full_PDE_limit  = 1
extra_engineering_p4_factor= 0
formal_MPI_math_threads    = 1 / 1
workstation_changes        = NOT_AUTHORIZED
ordinary_default_change    = NOT_APPROVED
master_merge               = NOT_APPROVED
```

**本轮消除的blocker：** 现有性能账尚不能解释新增资源成本，版本检查器未对齐；高阶局部作用持续进行反向投影、积分点重排和临时数组搬运。这些工作会随单元数和迭代次数累积。目标是减少不改变数学定义的执行成本，并防止为局部提速引入更高峰值。

最终目标仍为约2 TB整机物理内存内的0.7 nm、complex128、Nédélec H(curl)、双Floquet、Fourier-DtN、周期单胞内任意非可分三维Maxwell。**本轮不解决全局p4直接因子的增长，不声称0.7 nm已可行，也不因其尚未可行而放弃Full3D iterative主线。**

执行前读根与适用目录AGENTS、[工作原则](../repository_work_principles.md)、[原task](task.md)、[V22补充](user_authorization_v22_b_capacity.md)、[V23补充](user_authorization_v23_physical_memory.md)、[Review V28](review_report_v28.md)、[Response V31](response_v31.md)、[summary](outcomes/summary.md)。被后续review覆盖的旧一次性运行和停止合同不重新生效。本review是新批次，不复用或清零旧replay账本。

仅在canonical登记的笔记本task39extra worktree工作；不SSH操作工作站、不改其源码/监控/线程/因子/资源上限，不停机、不重启、不启动工作站PDE。工作站2026-09-28证据只作为已冻结背景，不冒充其当前状态。若分支出现新提交，先核对差异，不reset、不自动merge/rebase其他分支。

## 1. 对V30的正式审阅与保留项

### 1.1 已确认的结果与未关闭事项

依据：[V30 outcome](outcomes/workstation_guided_local_v30.md)、[compact](outcomes/records/workstation_guided_local_v30_compact.json)、[checker](outcomes/records/workstation_guided_local_v30_checker.json)、[components](outcomes/records/workstation_guided_local_v30_components.json)，均按本review的base HEAD冻结。V29分母见[原compact](outcomes/records/a4_tensor_h6_v29_compact.json)。以下为同一original、p6/h7.5、粗p4、990单元、80模式完整场，时间单位秒，RSS单位B。

| 实测项 | V29速度基线 | V30 | 审阅判断 |
|---|---:|---:|---|
| workflow monotonic | 2422.426388672 | 2532.7591178629955 | V30慢110.332729191秒，4.554637% |
| setup monotonic | 533.7549639960052 | 626.9310128289799 | 增93.176048833秒，尚未完整归因 |
| pure KSP | 1837.17495212 | 1854.603096447 | 增17.428144327秒，0.948638% |
| workflow conservative realtime | 2643.634584208 | 2762.5454779499923 | 两套时钟各自比较，不混加 |
| iterations | 126 | 126 | 未以少迭代换取结果 |
| 原A6最终相对残差 | 9.283162362107749e-7 | 9.283162411158622e-7 | 均低于1e-6 |
| watchdog整树RSS峰 | 7326449664 | 8044191744 | 增717742080 B，约9.8%，不是峰值中性 |
| H6对角准备 | 4.798956676997477 | 1.873419773997739 | 局部节省约2.93秒 |
| H6 power10 | 39.08678095601499 | 49.74741284799529 | 次数仍20次B6，不能归因增加迭代次数 |

V30离线全FE L2/scaled-curl差为1.4028635388466484e-14/3.3312391899680165e-14，80模式复振幅相对差1.9013904912668762e-14，功率/体吸收一致性通过。保留`PASS_WITH_AUTHORITY_LIMITATION`数值范围；不称连续网格收敛、工作站资格或性能PASS。

V30旧V25动态checker的`backend_identity`为FAIL，独立数值checker通过。**两份证据同时保留；不能直接忽略版本门，也不能因旧字符串失配否认已验证的同离散场。** R2补齐实际版本化接线检查后，另出重审记录，不覆盖旧FAIL和worker五个`NOT_ATTEMPTED` reference checkpoint。

### 1.2 后续默认继承与禁止扩大范围

保留V29的A6融合、快速完整A4、blocked Gram、双层凝聚、BAL_H，以及V30合格的reference-metric对角与低扰动RSS监控。除非R1找到明确不必要对象或错误接线，不因一次跨场变慢就整体回滚新对角/PSS关闭策略。

L3多列局部RHS候选与L4流式端口仍不采用；真实24-cell负结果仅覆盖其测试范围，不宣称大规模所有批处理/流式方法均无效。本轮不重试它们，不再新增几何分类、类型舍入、参考矩阵生成平台或H6前移工程。

**冻结MUMPS后端、排序、主元、ICNTL、BLR/OOC、线程和ABI；不换p4、不试p3/p2、不改PC、restart或精度，不尝试多核/GPU/新DD。** 数值核心进src，benchmark/checker只负责编排与核验，不复制巨型task runner。

## 2. R1：用已有日志闭合setup与内存问题，不为分账重跑

### 2.1 setup与计时

从V30已结束run的stages、worker summary、watchdog、JIT记录和同源配置提取明确开始/结束边界；V29有相同边界时才逐项比较。最少分为：空间/约束/端口/JIT、p4局部装配/symbolic/numeric、H6对角/power10、p6 builder、bridge/QA、收尾。原始文件只做必要的单次流式归约，保存小摘录、行号/事件ID/hash。

区分同场父子区间、worker/parent/编译子进程CPU与wall，不能相加重复桶。没有子计时就写unknown，不能把93.18秒差额叫Python、MUMPS、PSS或新对角开销。若缺失旧记录，记录缺口后继续，不为复现旧时长反复跑完整PDE。

### 2.2 精确定位整树峰值

找到V30的8044191744 B对应样本，列UTC/monotonic、阶段、PID/start_ticks、角色/命令、各成员RSS及其和、附近少量样本。核对root与后代是否重复计入，主控/编译/checker是否在该时刻重叠；这只是核对，不预先认定它们是原因。

对V29沿同一口径取峰值样本；另列setup、KSP、release、postprocess采样峰。**不以不同时间的worker峰和整树峰相减归因，不将RSS减MUMPS used叫作额外Python内存。** 不能通过剔除parent/编译器、缩窄监督范围、降低采样频率或重置peak来制造省内存。

若现有证据明确显示重复数值对象、无用大缓存或整段日志常驻：只修这一处生命周期/流式整理，保留完整检查覆盖和因子依赖顺序。清理一个不必要副本不等于可删除权威输入、正在使用的矩阵或恢复数据；改变的live-set及最后使用点须有测试。禁止无依据加入malloc_trim、修改系统allocator/THP或全局环境。

本轮继续PSS=`disabled_by_profile`，未采值为null并有状态；不恢复smaps扫描来补账。快速RSS/status、任务swap观察、PID、失联/超限和subreaper清场链保持。若只能确认峰值阶段、不能精确分摊每个对象，允许`PARTIALLY_ATTRIBUTED`，不无限扩大诊断；明确证据不足不等于泄漏。

**性能目标仍参照V29约7.326 GB，不将V30的8.044 GB偷偷提升为目标或新预算。** 目标不是运行期硬停止线；正式仍服从已授权的实际物理压力与系统余量保护。未发现真实安全/实现错误时，历史差额尚未完全解释不阻断有界局部候选；新完整场负责测量所选组合峰值，未回到目标就如实不授予资源提升资格。

## 3. R2：版本化接线检查与历史证据重审

增加或修正通用checker的显式V30/V31规则，依据所选profile和真实raw字段，而不是把V25期待的backend名称套到所有新版本。复用原检查器的数值/账本核心，避免复制另一份巨型checker。

| 必须核对 | 合格做法 |
|---|---|
| A6/A4/B6/H6实现 | 读实际backend/component、fused状态、阶次、quadrature/point/weight/coefficients身份与调用数；旧native作为独立oracle继续存在 |
| 线程与空间 | 读manifest、原始运行配置、已有库/线程证据；仅配置不能证明实际运行时则标明边界，不能用新现场状态补写旧场 |
| PC与精化 | 区分逻辑C、实际MatSolve、每次完整A4、额外精化、best-state和port状态；不同scope不机械相除 |
| 监控 | PSS显式缺项不等于RSS失联；RSS/swap记录和退出清场仍检查 |
| 负向检查 | 故意改变backend、线程声明、积分身份或去掉关键字段的轻量fixture必须拒绝/未决，不能全字符串放行 |

V30静态`calls_per_PC`仍出现H6=2/B6=4，而累计H6为131、B6为282（包含power10的20次）。先按作用scope和实际回调核对这种旧模板字段，**不要因元数据过时更改真实H6算法次数**，也不要让旧标签掩盖实际错误。

对现有V30 raw离线重审，另存`v30_reaudit`并绑定checker源码SHA。没有足够原始证据时仍写`EVIDENCE_LIMITED`，不反向伪造PASS；新场启动前用小fixture把当前实际接线闭合。检查器与文档修复本身不需要重算V30物理场。

## 4. R3：唯一新数值候选——内部自然序与固定形状反向投影

### 4.1 为什么改这里

V30的B6局部kernel累计apply约560.837761272秒，其中`reference_backward`=282.997334055秒、`coefficient_transform`=177.123514209秒、`reference_forward`=67.104819046秒、metric=25.069077036秒。它包含power10等调用，不能再加到H6累计532.759961520秒。**反向投影占该局部桶约50.5%，但其中有多少属于拷贝、多少属于算术尚未拆清；不能先承诺整体加速比例。**

核对入口：[fullspace_n1e_sum_factor.py](../../src/solvers/fullspace_n1e_sum_factor.py)的`_field_from_polynomial`、`_polynomial_from_field`、`_project`、`_integrate_polynomial`。当前前向从自然张量顺序用索引转换为原积分点顺序，反向又用索引转换回自然序，然后执行三个方向的einsum。

通俗地说：同一批积分点并没有变化，只是反复换排列和中间数组。候选先让内部值、旋度、材料加权、投影一直使用同一种排列，再为反向投影选择更适合固定形状的连续运算。这是执行重组，不是近似积分或新的预条件器。

### 4.2 数学不变量

以一个局部项说明。设Q把原FFCx积分点顺序变成自然张量序，E为原顺序的求值算子，W含原积分权、材料和几何；必要时Q隐含对向量分量的恒等扩展。

```math
E_n=QE,\qquad W_n=QWQ^H,\qquad
E^HWE=E_n^H W_n E_n.
```

只把对应的weights、point-dependent数据和索引在setup准备一次。仿射单元常量metric可以不重排；任何随积分点变化的数据都必须一起转换。Q/Q逆正确性、每一项自己的规则都保存身份；curl与mass积分规则不同时，分别保持各自自然序，不能强行合并成同一低阶规则。

对已加权单分量数据F，反向投影为：

```math
r_{bijk}=\sum_{x,y,z}
\overline{X_{xi}}\,\overline{Y_{yj}}\,\overline{Z_{zk}}\,F_{bxyz}.
```

本机p6主形状为batch<=8、Q=8×8×8、每轴多项式数7；完整Nédélec系数882，多项式系数3×7³=1029。保留小型非等轴积分点数fixture，避免三个轴都是8时掩盖错轴。上述共轭来自投影伴随，**不得额外共轭复材料，也不得假设真实Maxwell矩阵Hermitian。**

### 4.3 实现顺序与可回退子项

先实现**自然序贯通**：删掉各值/导数/投影分支之间不必要的往返高级索引；公共外部接口、输入/输出所有权和native oracle不变。缓存键包括完整积分规则、顺序及dtype，不能修改被旧/新对象共享的只读数组。

随后在同一候选内尝试**固定形状反向收缩**：用实际连续布局将z、y、x三个收缩组织为可复用的矩阵乘法或已存在执行栈的短内核，必要transpose/pack显式计入成本。允许自然序与新投影分别开关以识别收益，正常最多基线、自然序、自然序加投影三个组合；不扫描大量batch、einsum路径和库版本。

不要求matmul必然胜过einsum；必须展示完整B6/H6调用确实减少成本。没有结果变化不代表性能通过。只对`_project`做微基准不能成为采用依据；只将旧`reuse_projection_work`、`shared_contractions`或实虚堆叠开关重新打开，不算新实现。若自然序没有收益但新的反向组织有收益，可以只选后者，反之亦然。

用少量附加计时区分reorder/copy、三次反向收缩和累加，不能在每个单元/积分点写日志。保留原系数转换数学和准确系数，不截断小值、不换有限元基、不建立稠密全局算子/全域求值表。工作区只随固定batch、局部p/q增长，不随单元总数或外层步数常驻增长。

默认固定batch8，沿V30数学线程1。新增常驻数据仅为必要参考表/排列和有界scratch；记录底层buffer去重后的字节、临时峰值和BLAS潜在拷贝，不能把`out=`等同于零临时分配。调用返回后引用、异常清理和重复调用稳定性都要检查。

### 4.4 用小而真实的配对决定，而不是再造完整求解探针

先做局部复数代数、顺序与伴随测试，再复用真实990-cell组件和已保存的两个代表性合法向量（早期与后期；若不可取，固定种子并明确diagnostic）。最少核对：完整B6、固定同一D/谱窗的H6、新旧A6完整作用及A4完整验算差均<=1e-10，零尺度沿原绝对规则；保留复Floquet、方向、非均匀DG0、非零内部/端口数据的既有回归。改变公共投影时不得只测试H6而遗漏A6/A4。

增加原求值/投影伴随内积检查，以及旧实现和独立native作用对照；新候选不能成为自己的唯一oracle。最终H6仍用规定power10种子、20次B6与原谱窗生成规则，不用历史窗口冒充新setup。

计时warm-up单列，最多3轮交错AB/BA，保存全部wall/CPU样本、完整apply与子项、调用/拷贝次数、scratch。配对同scope、同线程/监控、输入不变；不以一次最快值决定，不将1%左右且落在波动内的变化称可靠提速。无需p4全局因子，不新建完整C配对；完整C和精化接线在随后唯一正式工作集验证。

H6是主目标。通用路径对A6或A4产生稳定退化时，优先给H6限定启用并保留已成功融合A6/快速A4；若所有相关作用都有收益才共享采用。无明确收益的子项撤出，不升级复杂编译框架或开启下一套PC研究。

## 5. 不变的正式数学与检查

```math
A_6x=b_6,\qquad C_4=P_{64}F_4P_{64}^H,\qquad
M_6=C_4+(I-C_4A_6)H_6(I-A_6C_4).
```

同V29/V30的13.5 nm、original、1°、azimuth0、s偏振、Si/air、p6/h7.5、990单元[9,5,22]、80个完整有序DtN keys、同网格p4、双层单元凝聚。p6保留199340行、p4凝聚84680行；复杂材料/边界/积分/几何与原始非可分适用目标不变。

初次粗求解及每次精化后的**完整原A4验算一项不减**，不降低频率、不用便宜筛查、不替换为因子或凝聚残差。内部目标1e-10，最多两次额外同因子精化；耗尽后有限且完整时返回已验算最佳FE/alpha/A4c/e同一状态并继续外层。真正非finite、因子/约束/端口错误仍停止。不得因希望省一次MatSolve而调大目标。

right FGMRES32/max2048、零初值、每次两次逻辑C和一次H6；每8步原A6、每32步场，终态完整原A6及释放后<=1e-6。126步不是硬条件，舍入引发变化要实报，不能放宽最终精度。最终FE L2/scaled-curl、同坐标E/H/界面、80复模式相对差<=1e-4；R/T/A/A_volume绝对差<=1e-5，逐模式功率差<=1e-6，能量/吸收一致性<=1e-5，不拟合相位。没有独立更细网格仍为AUTHORITY_LIMITED。

## 6. 执行流程、运行数量与资源

| 阶段 | 工作 | 进入下一步的规则 |
|---|---|---|
| R0 | canonical worktree/HEAD/ABI/输入和新batch确认 | 不改旧账本，不重复启动已有run |
| R1 | V30 setup/RSS峰值离线闭合；若有明确原因，最小生命周期修复 | 未能完全归因则如实保留；真实风险先修，不强行编造原因 |
| R2 | V30/V31版本化checker、负向fixture、旧raw重审 | 保留旧FAIL；当前关键执行接线必须可核验 |
| R3 | 自然序与固定形状反向投影实际实现和短配对 | 不只补timer；不合格子项回退 |
| R4 | 唯一selected组合，clean源码后完整h7.5 | 有采用的生产内核/生命周期/运行接线改动才启动一次；无改变则不为凑表重跑 |
| R5 | 独立原始检查、三阶段账、response与推送 | 无论有无性能收益，都集中收口，不停在候选待审 |

本轮正常**最多一场fresh PDE**，不重跑V29/V30作为并行对照，不建额外工程全局p4因子。若只补历史分账/离线checker且候选全部不采用，R4=NOT_RUN，保留已完成V30的数值证据；不是又把未完成的必跑场搁置。若有合格生产变化，冻结后直接完成一次R4，不额外请求阶段批准。新的后台任务、工作站推广或第二个研究方向不在授权内。

正式入口：`python scripts/run_case.py input/task39extra/v31_projection_layout_original_h7p5.dat`，一dat一run，新结果目录和账本。提交clean源码后，合格JIT按原身份复用，局部数据与唯一p4 factor本场build；setup通过后同进程同因子继续KSP。启动后不改该运行工作树HEAD/源码；结束后再提交证据。

全程接电、固定电源模式、MPI1/数学线程1，一次一个heavy。沿现有physical-memory-pressure保护与明确的time/swap observe_only合同，保持系统余量、磁盘、快速RSS/失联/清场；实际swap必须披露并限制性能结论，不用交换内存撑预算。PSS仍null；不得把关闭PSS写成关闭监控。正式前验证complex128、ABI、MUMPS原设置、输入/physical SHA、网格/keys、fresh MemAvailable与实际监控链。

不提高MUMPS额度，不恢复过时固定预测阻断，也不把V29/V30时间和RSS成绩当运行停止线。最终报告以全过程整树峰值为准，包括parent、编译及必要checker重叠；内存目标未达到不等于数学失败，但不得宣称更省。

真正实现bug有原始失败记录与最小修复后，本批至多一次必要定向重放；资源耗尽、普通不收敛、性能不佳不是bug重放理由。安全停止清场后不自动扩大范围。没有改善就停止这条候选的继续调参，返回具体负结果，而不是开启新扫描。

## 7. 交付、分母和提交计划

主要速度/资源分母保持V29：workflow2422.426388672、setup533.7549639960052、KSP1837.17495212秒，watchdog RSS7326449664 B；V30同时列为最近已测控制。不得只与较慢V30比较来放大收益；同进程组件配对与跨次完整wall分别陈述。monotonic、realtime、CPU同事件记录，时钟差不随意归因。

| 最终三大块 | 必须有的细目 |
|---|---|
| setup | 空间/端口/JIT、p4局部装配/symbolic/numeric、H6对角/power10、p6 builder、bridge/QA；明确相邻父区间与子桶 |
| KSP | 两次C及PH/reduce/MatSolve/recover/完整A4/port/P/精化；A6/H6/B6、反向投影子项；Schur、正交化、固定检查；未计字段写unknown |
| 后处理 | 完整恢复、原A6终检、释放及后验、正式物理输出；全过程峰值所在事件及成员 |

内核性能、setup变化、完整时间、迭代数与资源分别判断。若组件快但整场不快，保留事实，不拼凑各场最优子项；若RSS仍偏高，给出真实峰值样本和剩余未知，而非宣布中性。新功能仅为显式profile，保留全部历史。

建议四次提交：D1历史重审/版本checker及最小明确修复；D2投影候选和组件证据；D3唯一选择、输入/profile与最终相关测试；D4正式证据或NOT_RUN裁定及response。测试集中跑变更相关集合、compileall与可用静态检查；Ruff/全库/MPI2/4/CI未运行如实写，不以缺少工具静默宣称通过，也不为此升级资格环境。

```text
response_v32.md
outcomes/projection_layout_v31.md
outcomes/records/projection_layout_v31_v30_reaudit.json
outcomes/records/projection_layout_v31_components.json
outcomes/records/projection_layout_v31_selection.json
outcomes/records/projection_layout_v31_compact.json
outcomes/records/projection_layout_v31_checker.json
```

可合并小型证据，事实不能省；NOT_RUN不用伪造运行compact。新checker源码应跟踪提交，命令、输入hash、工具SHA与输出绑定，不能只有PASS JSON。保留input_original.dat、resolved_config、run_manifest、input/physical/source SHA、run_summary、环境与场/模式/资源hash，重型文件继续ignored。更新summary/test_summary/run_index、development_progress和模型总账；旧reference checkpoint/失败不覆写。

最终选择性工作站清单只增加“本轮已测/未采用/未验证”的最小依赖；不把本机p4性能比例套到TB因子。工作站大规模C和全局因子仍未由此解决，后续必须用实测评估达到真实残差的总成本，而非只看kernel倍数。未经新授权不执行迁移。

## 8. 技术参考与文档核验

- [NumPy copies and views](https://numpy.org/doc/2.0/user/basics.copies.html)：高级索引产生副本，reshape/transpose是否复制取决于布局。它说明重排有成本，不证明当前283秒都由重排造成。
- [NumPy einsum](https://numpy.org/doc/2.0/reference/generated/numpy.einsum.html)：执行路径与输出布局影响临时存储；不能仅凭调用写法推断更快。这里只引用语义，不授权升级本机NumPy。
- [Linux proc](https://docs.kernel.org/filesystems/proc.html)：RSS/PSS与采样范围不同；本批不为精细内存账恢复昂贵PSS扫描。

遵守[Markdown标准](../markdown_rendering_standard.md)：独立公式用fenced math，表格列数一致；检查本地预览并尝试GitHub渲染，不可访问要明确披露。最终推送task39extra，回读完整HEAD、upstream/ahead-behind和工作树状态，统一等待审阅；不合并master。
