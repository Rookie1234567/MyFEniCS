# V36：原尺寸合同与按需完整端口准备

本轮解决一个存储问题：旧端口作用虽分批计算，仍把所有模态的边界系数留在内存。新provider按固定顺序只交出当前批系数，消费后释放；有限元方程、Floquet相位及归一化不变。它用反复生成／读取换取较小系数缓存，**不是新的全局求解器或神经加速**。

## 范围与实际资格

| 工作包 | 实际结果 | 边界 |
|---|---|---|
| A 原尺寸输入、完整mode、解析容量 | GENERATED＋独立CHECKED | 未建原尺寸体积mesh／全量DoF编号／矩阵 |
| B 有界owner-local provider | 默认64mode／64MiB，取更严格者 | ordinary default保持；单mode越界明确拒绝，不暗增cap |
| C micro真实表面＋独立保存数组checker | PORT_COMPONENT_QUALIFIED_ON_MICRO | 仅边界组件，不是完整Maxwell解 |
| D 部署／缺口包 | TARGET_SOLVE_NOT_AUTHORIZED_OR_NOT_QUALIFIED | 缺匹配全局solver、精度与完整资源证明 |
| 旧V35七／八块PC；目标PDE；NN训练 | CLOSED／NOT_RUN／NOT_RUN | V35真实负结果保持，未追加周期 |

formal inventory／FE组件source为`19eb5dc9ca4d245612d7ddbf9f1a750387b9c8d4`；最终纯cache checker为`730e8f3336ddd6f9449b70430a48c77cdc1750e3`。新metadata寿命修复只把重复440条加载记录压到40份mode累计记录，加载次数仍440；原真实FE向量／hash不变，未因它重复FE组装。最后文档HEAD不替代这些source。

## 原尺寸物理与容量

规则首对象是完整3D的50×25nm周期、z=−10..130nm，Si块x=16.5..33.5、y=0..25、z=0..120；双Floquet、上下开放DtN、layered背景，grazing1°／azimuth0／s／幅值1。air n=1、mu=1。substrate、block、背景Si及下端口统一读取canonical用户表：source标签0.699999988明确alias到nominal0.7，n=[0.999885140474,4.32477054e-6]，epsilon=n*n；不插值、不使用旧13.5nm材料。

physical合同hash=`7da1f5b5f1ef0345c499c656965cb3c9820c3f8beec850ef2889efd605b8eaa8`；材料hash=`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`；target原ordered mode hash=`ae785ecbdaaa7ff11ef7897b1ab00c58232aaf1d97f851a8960206063496eeda`。上下各16030／总32060是原函数及独立整数枚举得到，非硬编码dot数字；色散相对缺陷4.4286660119e-16。当前清单均propagating，外部截断精度仍CHANNEL_TRUNCATION_UNQUALIFIED。

旧`positive_x_middle_y_z40_80`另作非可分能力见证：legacy坐标下midpoint规则实际选x=16.5..33.5、y=0..6.25、z=40..80的块内部分。它不是规则首对象，也不声称旧不对齐网格表示了解析缺口。已分别保存几何hash和对齐的一维轴列表。

| p6／最大轴间距0.7／q15容量情景 | 解析值 | 解释 |
|---|---:|---|
| 轴cell数／总cells | 73×36×202／530856 | 材料与端口平面对齐；不是精度生产资格 |
| 完整FE storage | 345771066 | 含未配对周期slave存储 |
| canonical trace／内部／slave | 105298704／238885200／1587162 | 内部未知量单独恢复，slave不增独立未知量 |
| 全port | 32060 | 全ordered复输出及功率，不仅零级 |
| 单complex128完整FE向量 | 5532337056B | 确切数组载荷，非RSS |
| 条件GMRES256向量组 | 434673050112B | 假设258条trace向量；未授权该目标算法 |
| 单稠密Nport²表 | 16445497600B | 约16.45GB；一张不是2TB。Hhat可能dense，Hp diagonal不等于Hhat diagonal |
| 全cell dense矩阵条件载荷 | 6607449967104B | naive同时保留时超过2TB；不是必需实现或已测峰 |
| 单全边界functional pair上界 | 9082376B | 64MiB约可容7份此上界，字节门先于64mode门；owner分布另计 |

Nédélec edge／face／cell计数已独立复核；旧8×6×8/p3重得18144trace、13824内部、34050storage、2082slave。p3/h0.175仅纸面风险对照，未运行扫描。Int64实际环境；本情景最大row id仍在有符号Int32范围内，但编号／ghost图、cell class存储、JIT／PETSc／MPI、全局solver、IO和同时生命周期仍unknown。各数组下界或条件上界不能相加冒充峰上界。

## 真实组件与独立数值审核

一个受监督actor创建原1.4×1.05×1.4nm／384hex／p3／q15表面空间，完整34050FE存储／18144canonical trace／40mode；两侧各20。tag1=200（含8notch air）、tag2=48、tag3=136。只构造四个原表面form与原Floquet/MPC约束及DtN shell metadata；没有体积form、全局fine系数矩阵、LU、QR、KSP、训练或参考读取。

旧resident原作用保持独立；伴随从旧C/D分别计算，不假定D=Cᴴ。新provider重新调用原表面assembler，经完整方向与MPC后给owner-local rows。两个seed423611／423613产生未拟合非零复输入，另测zero／complex scaling；MPI2／4小fixture含空owner并保存实际汇总全向量。

| 数学Gate，两seed | measured最大缺陷 | 固定门限 |
|---|---:|---|
| 完整forward／完整40复振幅／modal RHS | 0／0／0 | 非零量相对≤1e-10；零单独精确检查 |
| 完整adjoint | 1.0888902683433186e-16 | ≤1e-10 |
| 复dual／复线性 | 4.7442031580e-18／2.2031476003e-16 | 抵消前operand尺度≤1e-10 |
| 每通道单位振幅功率 | ≤1e-10，实际差见原记录 | 保留全部40项，不用near-zero相对误差 |
| 独立cache replay、H／参考面与逐通道功率 | CHECKED | 从保存数组／原mode k,E重算，不信status |
| 原Schur/native／total/scattered E/H／curl／R/T/A/A_volume／能量 | NOT_RUN | 没有新物理解；上述随机边界见证不能授完整解资格 |

验收保留分子／分母、原零值及operation尺度：[原组件](records/component_result_v36.json)、[独立checker](records/component_checker_v36.json)、[完整原始日志／资源索引](records/raw_evidence_index_v36.json)。大数组及完整32060清单在ignored artifact，路径与逐成员hash见[run index](records/run_index_v36.json)。未读旧七因子、ActionPacket数值载荷、warm、REF7、网络权重或dot因子。

## 生命周期、真实费用与代价

micro最多2mode／1MiB配置，实测cache与active lease均82960B、live功能对象最多2、438次淘汰、清空后无被creator／consumer保留的旧numeric数组。creator conditional NumPy/vector workspace界5718144B，另有FE／MPC／JIT／库分配，不能仅报cache。对照时旧resident的1187408B载荷同时驻留，因此本actor峰不是旧／新各自独立峰，更不能授NN20%峰改善。最终每mode累计记录为O(Nport)，累计load/hash/visit计数不清零。

| shared-workstation实测 | 值／口径 |
|---|---|
| INVENTORY／COMPONENT／CHECK／DEPLOY监督wall | 24.481769902／11.306872300／4.744587441／4.714764241s |
| 组件mesh/MPC／表面JIT／resident生成 | 0.586284980／4.094272160／0.081993785s |
| 新apply5次／adjoint2次／recover2次／modal RHS2次 | 0.783487614／0.352583230／0.262895052／0.264056207s；inclusive |
| 新generation／hash | 1.391014592／0.067271366s；已嵌套于新作用，不重复相加 |
| 新表面assembler调用／provider加载／归约 | 880／440／180；只有尾2mode缓存命中，不是全清单warm复用 |
| 整批已收费wall | 175.774027562 s，包含失败、测试、MPI、探针与交付辅助；≤1800s |
| 同时整树采样峰／组件采样峰 | 603471872／352448512B；0.5s采样含launcher/JIT/MPI，非连续cgroup峰 |
| ownswap／GPU／数学线程 | 0／未使用／getter实际1；每阶段实时避开busy SMT选核 |
| 新ignored数据／Task042全部逻辑唯一文件 | 以[storage](records/storage_v36.json)最终值为准；cap512MiB／20GiB，disk≥50GiB |

载入／hash／输出字节与source各分开保存；cache checker logical payload bytes可重算，物理磁盘IO及输出serialization/hash独立时钟没有测量，保留unknown且已包含stage总wall，不补造exclusive耗时。旧全部研究费、失败和N=1 unknown不清零。曾发生环境无threadpoolctl、父进程MPI初始化污染launch、非关键Ruff／字符串格式及collector CPU字段错误；同轮定位最小修复，原stderr/source/hash/费用均保留。最终19个定点、MPI2／4、真实FE及保存checker通过；没有全仓PDE重跑或CI声明。

全树保护复用自有subreaper、0.5sRSS／swap／PSI、不可刷新的UTC＋monotonic＋boot_id；组件warn6/hard8GiB，aux2GiB，每次使用独立cache和自有锁。没有可写独占cgroup，因此不声称安装了内核连续限额。没有持续PSI压力观测；缺邻任务可比进度指标，性能干扰INCONCLUSIVE，不能承诺零影响。未调整邻任务的环境、CPU、优先级、锁或watchdog。

## 部署及继续条件

四个实际one-run入口见input下`v36_target_inventory.dat`、`v36_port_component.dat`、`v36_port_checker.dat`、`v36_deployment_package.dat`；本轮已执行，结束后scope closed，不授权重复actor。只读查看已生成部署包不会重开窗口：

```bash
cd /home/fenics/Projects/NN-Lab
export TASK042_CACHE_NAMESPACE=v36/view PYTHONDONTWRITEBYTECODE=1
source scripts/activate_task042.sh pure
python -c 'import json; from src.io.port_preparation import read_stage; print(json.dumps(read_stage("DEPLOY")[0], ensure_ascii=False))'
```

mode超过cap时，需要按canonical surface-row tile先累计投影、每mode batch完成一致collective、再按同tiles散射coupling；伴随相同共轭约定。这个最小协议已列出，尚未实现／资格化，不能静默放大cache。

dot只读snapshot5be1210…的p4／120cells／532手动port／材料与本合同不匹配；没有找到等价的真正byte-bounded provider。没有修改dot、等待其工作代替本包、迁移其求解器或加载不同身份的factor。差异和需提供字段见[部署包](records/deployment_package_v36.json)、[身份缺口](records/dot_identity_gap_v36.json)。

48h必要条件是完整setup＋solver＋每次端口供应／作用＋恢复／审核＋IO（若有NN还含全部训练与推理）≤172800s。target每作用成本、总次数和同时峰均unknown，不能用micro的40mode线性外推32060mode的全表面。2TB单表容量不代表当前独占配额。NN20%要相同正确性下完整N=1时间或同时峰≤最佳合格非NN的0.8倍，另一项合规；当前无该完整基线，传统流式存储收益不能归NN。

唯一下一建议：取得与本轮physical／mode合同匹配的dot冻结全局solver包，按部署清单做一次逐字段身份与端口接口验收；本轮不自动实施。

GitHub精确review页访问Cache miss，没有视觉证据：NOT_VERIFIED。本地新表格、链接及math围栏另验；未擅改review。旧task/review/response/raw及历史closed账逐字保护，不merge master，不授原尺寸／48h或micro完整物理资格。

未单独监督的实现／元数据读写时间为unknown，已包含日历elapsed；受监督wall与探针和bootstrap的精确和单列，不把它冒充完整N=1或把unknown记成0。
