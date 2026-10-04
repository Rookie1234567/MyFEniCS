# V41：原尺寸实际拓扑与分布式边界接口完成，完整前向解尚未完成

| 对象／单位／身份 | measured结果 | 资格及边界 |
|---|---:|---|
| 原0.7nm规则三维光栅，50×25nm周期、z=-10..130nm | native MPI2实际530856hex；555814顶点、1642171边、1617214面 | [真实库存](records/actual_topology_inventory_v41.json)；只有低阶geometry/topology，未建目标p6空间 |
| 同一个连接64hex，三tag、内部共享面、跨rank周期角点 | 顺序真实MPI1/2/4，p6全局45000行；构建累计192hex | 分布式native bridge通过1e-10；不是p6/h≤0.7精度证明 |
| 实测精确cell类及rank使用 | raw270，oriented858；MPI2私有份数306／900 | 精确IEEE宽度/tag，不合并近似数；[容量](records/original_size_integration_capacity_v41.json) |
| 目标新增方向 | 62种，逐种原native p6双轴变换通过 | 先停止路由资格，再用旧raw882补审；无新mesh/kernel/LU；旧小见证覆盖不虚填 |
| 全边界owner通信及旧q30作用 | 378432行、上下各2628面、32060完整端口；最大相对差1.3930219660660015e-15 | 独立literal checker及新MPI2消费通过；原体积callback未连接 |
| 保存数组／原始日志 | 17 NPZ／708实际与逻辑成员，别名0；当前557归档版本 | 字节／shape／dtype／C-order hash全验；[库存](records/array_inventory_v41.json)、[raw](records/raw_evidence_index_v41.json) |
| 整树同时采样峰／ownswap | 1895116800B／0 | shared-workstation；非连续cgroup硬峰，实际采样间隔另列 |
| 完整原尺寸PDE、E/H、功率、2TB48h、NN20% | NOT_RUN／NOT_QUALIFIED／NOT_DEMONSTRATED | 无新official R/T/A、R00_s/p/total或A_volume，无训练 |

本轮把原来每个rank都收集全部trace行号的做法，换成以完整边／面实体为单位、只向实际owner请求所需条目的接口。一个边保留6个矩，一个面保留60个矩；周期角点只归一个master。正向乘原Floquet相位，对偶散布乘共轭相位。实际native实体ID与按实体中心建立的canonical边界moment行号分别保存：后者不是尚未构造的全目标DOLFINx p6编号。

原尺寸530856cell的真实几何、拓扑、方向和材料库存已经产生，这比仅从结构轴推算多了一项可审阅的实际准入依据。没有构建345771066行对象、目标完整p6 dofmap、A/SH、32060²端口矩阵或全trace字典。原边界q30组件保持不变；新调用用于检验owner接线，不再做积分、q60或测速campaign。原尺寸还缺匹配的分布式体积引擎和可靠求解方法，不能把接口通过称为前向解。

## 阶段身份与有限真实MPI

[新envelope](records/stage_dependencies_v41.json)绑定原材料表、轴、三tag、basis、q、全mode、相位、dtype、index和slave语义，按几何、class、求积、恢复分别核对产出source与相关函数／源码hash，并核对system实际列出的class manifest。旧V40成功packet未改写。**V40正确计数为11包，129逻辑=120实际+9别名；旧138重复加了别名，保留旧记录并在本轮纠正，非丢数组。**

64hex见证采用目标真实材料面及完整大周期，x四段、y四段、z四段，连接且包含air/substrate/grating。真实native p6/MPC不编译form、不装配矩阵。MPI1/2/4完整一般复向量、零、复缩放、原MPC展开／共轭散布与独立literal相配；最大全向量差1.4814494150199548e-15<1e-10，计算slave严格0。MPI4实际跨rank周期边为2/1/3/41，周期面为0/0/0/16；不是用合成MPI替代。[全部小见证与方向](records/native_numbering_witness_v41.json)。

MPI1自然方向只有部分面反射，MPI2/4自然编号已覆盖边反向、面旋转和反射，所以没有额外重编号mesh副本。目标遇到62个新cell方向码时暂停相关资格，保留拓扑库存；仅在public native变换API与独立p6生成矩阵的双轴比较逐种过1e-10后恢复路由。这是实际遇到方向的必要补审，无新kernel/LU、全p6目标空间或高精度库。

## 原尺寸owner边界与独立消费

| 完整输入／作用（门1e-10） | 相对差 | 数据范围 |
|---|---:|---|
| 两rank完整owner提取合并 vs V38原x | 1.3930219660660015e-15 | 全378432行，每行一次 |
| recover振幅 vs V38 q30_a | 2.2101136192453272e-16 | 全32060有序复端口 |
| forward vs V38 q30_a | 5.200704032750467e-16 | 全边界复向量 |
| adjoint（独立y）／modal（原alpha） | 0／0 | 输入身份与旧记录一致 |
| 新MPI2进程extract／共轭scatter | 全部通过 | 只重载保存的owner边界条目，不创建volume向量 |

独立checker从native实体键／ID／owner／方向、字面MPC、原相位及完整保存向量重算；target原宽度/tag按每个owned cell几何重算，全部边／面／外表面闭合。边界checker不调用生产adapter来生成expected，独立复合p6变换再计算提取与对偶散布；同时要求完整实体、完整行、owner唯一。错source/material/phase/class、错owner、遗漏一面／rank、错方向及错误散布有拒绝反例。Basix原basis数据是明确共享依赖，不是独立物理求解器。[checker](records/component_checker_v41.json)。

[可调用接口](records/consumer_interface_v41.json)提供CompleteEntityAdapter与OwnerEntityRouter，consumer必须提供实际volume编号绑定、独立trace、内部RHS、非零port RHS、forward/adjoint、原空间recover及full explicit residual。V40的非零fi/g／仿射恢复MPI1包按hash作为anchor；本批没有把该MPI1恢复包升为MPI4体积求解器，也没有用零volume callback授资格。[新进程消费](records/deployment_package_v41.json)。

## 失败、最小修复和真实成本

| 已发生步骤（shared-workstation） | 秒 | 分类及继续方式 |
|---|---:|---|
| BRIDGE1首次／从保存packet补方向 | 7.956151535／11.246686003 | native T_apply需要flat数组；修复后不重建64hex |
| BRIDGE2／BRIDGE4 | 61.287228275／36.174171101 | 顺序真实MPI2/4；只一套冻结fixture |
| 原尺寸TOPOLOGY | 41.160119517 | 一次MPI2真实构建，入场规划4253140864B<6GiB；实测树峰1232334848B |
| 新62方向必要补审 | 70.441853583 | 只读旧raw882，无新张量/LU |
| ROUTING首次／完整作用比较／修复输入后 | 10.565562749／23.203239070／17.741380801 | 文件库存reader错误、adjoint用了x而旧见证用y；原FAIL保留，复用已保存数组，只补受影响作用 |
| 独立CHECK／新进程DEPLOY／CAPACITY | 73.727033095／4.937083396／4.065080434 | 保存数组独立审查；消费不重复整套审查；容量只derived对象清单 |

另有fixture极小相位精确等号、pytest内嵌MPI影响超时测试、checker计数变量被覆盖、两次Ruff接线、旧runner未准入V41已完成但不合格的阶段修复等错误，全部日志／source hash和消费留存。最终已提交source上的38项科学／接线测试通过，compileall、Ruff与15项文档合同测试通过；byte/source对应表见[tests](records/tests_v41.json)。没有删除失败、抬高门限或把普通负结果当bug扩算。

窗口从2026-10-04 09:35:15.130953671 UTC冻结，monotonic1031509.98、boot fd8f4b00-1e17-46af-a6fa-da3a32dbeba3，24h总／23h重。最终监督、probe、bootstrap保守3s及最后元数据结算保守5s逐项见[完整费用](records/resource_costs_v41.json)；native保守4800s、目标2400s是总有载7200s内的上限，实际子集不重复累加。历史监督下界81027.72151924176s继续累计，旧未监督实施和完整N=1成本unknown，不补造精确旧账。

整树峰1895116800B在BRIDGE4，全部ownswap0；默认0.5s采样，实测最大间隔约1.72276s，不能宣称连续硬峰。独立cgroup未委派，使用持续自有subreaper/watchdog和parent-death保护；native warn6GiB/hard8GiB，辅助2GiB，所有rank数学线程1、GPU不用。CPU按每次现场tick／邻任务线程及SMT重新选择，例如目标rank为3/4、MPI4为16/33/41/43，非永久CPU14。系统余量、邻任务后续增长和PSI门保持，full avg10采样最大0；缺乏可比邻阶段速率，干扰INCONCLUSIVE。[逐样本与CPU重算](records/resource_samples_audit_v41.json)。

保留全部17个科学NPZ及失败向量。接近256MiB交付储备时只收回本轮早期重复Python bytecode缓存，保留逐件hash和回收量；未删除科学数组、日志或旧JIT。最终新增存储、归档共存、20GiB Task上限和free≥50GiB逐项结算，不能把压缩文件字节、数组载荷或历史峰当RSS。

## 实测库存带来的容量更新与剩余准入

| 条件对象／字节口径（derived，不是实测factor RSS） | 节点共享 | MPI2按rank私有 |
|---|---:|---:|
| 270 raw882 complex128矩阵；私有306份 | 3360631680B | 3808715904B |
| raw class450内部LU、恢复、RHS投影、432 Schur＋共享单位阵 | 3363223680B | 3813057504B |
| 若另物化858 oriented882矩阵／私有900份 | 10679340672B | 11202105600B |
| 实际目标拓扑packet显式数组载荷 | 639674764B | 已含两rank对象，不另重复加 |
| 一份完整complex128 native向量（未构造） | 5532337056B | 分区/ghost另计 |

LU清单采用保守int64 pivot载荷，不是V40 SciPy pivot实测。raw/oriented/约束后局部类不是同一概念；约束可独立施加，不代表每cell要一份LU。858方向类若物化也会显著增加缓存，但尚未实施任何factor共享试验。alias压缩不会自动共享解码内存。除上述对象，还需完整列入owner/ghost索引、E/EH、源／目标／通信缓冲、解码与IO、PC/Krylov活跃向量、恢复与audit生命周期，后四项仍unknown。

旧86880B仅一项条件载荷，不是构建峰：旧882×84 float64方向数组本身592704B。新接口最大face变换60²×16=57600B、三份单实体临时2880B；持久owner/ghost/发送接收/源目标缓冲另列在actual packet和资源记录，不能把这60480B当整个进程内存。[完整对象合同](records/original_size_integration_capacity_v41.json)及[就绪矩阵](records/integration_readiness_v41.json)。

48h只能写成原成本约束，不填造K：

```math
K\leq\frac{172800-T_{setup}-T_{recovery}-T_{audit}-T_{IO}}{T_{volume}+T_{boundary}+T_{adapter}+T_{PC}}.
```

新的actual native库存、owner路由、构建峰已可作为下一次准入依据；完整volume单步、PC、K、目标恢复与审核仍unknown。没有可靠PC，旧七／八块已关闭，接口不能自行解锁完整solve。原full residual≤1e-6、完整场／复通道≤1e-4、R/T/A/A_volume≤1e-5、逐通道功率≤1e-6、能量≤1e-5及hp/mode截断全部NOT_RUN。本轮无NN训练，传统编号／通信／缓存收益不归NN，20%完整耗时或同时峰门仍未证明。

唯一下一建议：将同物理、同basis的分布式体积引擎接入本轮实际native实体／owner协议，以有限非零RHS及完整原作用证明消费，再申请目标容量／求解Gate；不再单开边界测速。本批不自动运行。

[Review V38](../review_report_v38.md) · [response](../response_v41.md) · [运行source](records/run_index_v41.json) · [原始证据](records/raw_evidence_index_v41.json) · [依赖分组](records/selective_merge_manifest_v41.json)。GitHub精确页未取得视觉证据，NOT_VERIFIED；本地检查不是网页渲染或CI。
