# S3：V6收口后追加的p3中间阶组件结果

本节记录用户在Review V6收口后追加的候选：细层仍为p6 Maxwell空间，粗修正改用p3实际离散的A3并对其作准确全局MUMPS因子分解。拟议正式外层right FGMRES(32)求解p6凝聚后的trace加全部port未知量（5 nm为600个port，2 nm为3904个port）；原完整未凝聚p6 A6用于full residual及相关作用，场重构后仍按原路线检查。已完成的18-cell组件只执行三次固定完整PC见证，没有运行外层FGMRES或形成外层步数。每次粗修正把细层残差送入较小的p3 A3空间准确求解，再映回p6；它减少粗矩阵自由度，但不减少p6细层离散、模式数或Krylov向量空间。它不是低精度逆，也没有更改A3/Aq门限、方向、complex MPC、完整DtN、单元恢复或物理积分。

这是V6之后的独立补充记录，不是“Review V7”，不回写V6历史成功或未运行结论。已通过的5/2 nm工作仅为18-cell有限元/MPC组件见证；完整场PDE、完整收敛与0.7 nm精度/容量资格仍未运行。

## 状态与组件证据

| 阶段 | 实测范围与结果 | 资格边界 | 证据 |
|---|---|---|---|
| p3传递矩阵修复 | 新的显式V6_P3 profile使用canonical共享边/面参考映射；每个局部映射替换72条边迹行与360条面迹行，共432条p6细层迹行；450条内部行继续使用原Basix映射。P和PH由同一矩阵产生，方向缓存沿用同一policy。 | 只对显式p3 profile启用；旧p4/q4、H6和默认映射不变。owner一致性仍为原绝对差`max\|candidate-reference\|<=1e-11`。 | [S3 compact](records/p3_mid_order_s3_components_v1.json)；C2报告SHA `cf6004ff734d08c970b28dc2e3e85300b1749c142dd743afc7aa10ff938e5a3d`；NPZ SHA `207d8cf01d70fa62bd55ce0245ee43ada26996885bbf1c8cb871118dbfdfa113` |
| 5 nm首个组件尝试 | 因测试夹具要求`Di>0`及诱导端口RHS非零而exit1；本拓扑`Di=0`合法，非A3/A6/Aq门失败。 | 保留失败；`g`与复数`gp`仍非零，原A3/端口方程未放宽。 | attempt目录`tmp/p3_mid_order_0p7/attempts/5nm_20261004T054256Z`；worker报告SHA `e8298657ad854e5c2ac5ff9f15f006c62da14945d316d3dc25a54505be149d23` |
| 5 nm owner Gate尝试 | 原独立cell映射最大绝对差`3.253907165344266e-11`，8行超过原`1e-11`门；A3/Aq见证通过。 | 保留失败，不抬高门限。后来同一C2保存包原矩阵同序复放最大差为0；canonical候选最大`3.637978807091713e-12`，超门行为0行。 | attempt目录`tmp/p3_mid_order_0p7/attempts/5nm_20261004T054949Z_v5`；报告SHA `cbe6479262682318a8bccffc916237586b9e69ce4b3ca15f2292419ed392de68`；C2与NPZ见上行 |
| 5 nm p3组件 | 18 cells、600 modes；三次完整PC重复，每次C1/C2均通过原A3/端口Gate；1/1/8 symbolic/numeric/solve，共用一个因子；额外精化0。A3全空间联合RHS残差`1.03389e-14`，原端口残差`2.99666e-14`，Aq通过；本拓扑`Di=0`且诱导内部端口RHS为0。 | **组件PASS，仅此scope**；`Di=0`不是强内部端口耦合压力试验。未跑3780-cell完整场。 | run `tmp/p3_mid_order_0p7/attempts/5nm_p3_canonical_trace_map_20261004T073927Z`；终态compact SHA `5ecb08478ac79b8f53c326dd4d96dc8829acf6e622cb22594d784aed5f19f2c8`；主审终态receipt SHA `45fbefa6e6050364f3bffa47171aeafaba796243bac37bbf2174aba60e42da7f` |
| 2 nm p3组件 | 18 cells、3904 modes；三次完整PC重复，每次两次C调用通过原A3/端口Gate；1/1/8 factor调用，额外精化0。原A3联合RHS相对残差`6.53025e-15`、原端口`3.84736e-15`、显式端口凝聚残差`4.09364e-15`；Aq volume/DtN相对差`1.71757e-15/1.64224e-14`。`sum_Frobenius_norm(Di)=5.58775e-12`、诱导内部端口RHS范数`1.61291e-15`，近舍入量级，不构成强耦合压力证据。 | **组件PASS，仅此scope**；不代表完整2 nm场、16步pilot或收敛资格。 | run `tmp/p3_mid_order_0p7/attempts/2nm_p3_canonical_trace_map_20261004T075827Z`；worker报告SHA `f8ae31208c32c2960570d8c18a569d9161eca6010bccec3b6fb836f81aeaec33`；主审终态receipt SHA `07a2badfc8fa961994c81759c533ecc0670bf02d8ffb73202d0b4079edf2c0af` |

5 nm旧owner失败显示的是被1e-11绝对Gate拒绝的真实映射差异；修复以共享实体参考映射让相同边/面迹行由共同构造生成，不靠数值截断或过滤行。保存C2包重放仍由原Gate执行。原型v1/v2/v3、v1/v2的方向/批序问题、负向错误边矩量映射，以及聚焦测试首轮V5 schema失败均在compact中保留路径和hash；最终受影响测试为`9 passed / 5.87 s`。没有重跑旧H6、p6 tensor或额外完整FE。

测试report沿用`P4_RETURN_PASS`这一历史状态枚举，但本S3的实际字段明确为`coarse_degree=3`、`coarse_operator=A3`；不表示运行了p4。

## 构建与固定PC时间（2 nm 18-cell组件）

| measured项 | 时间 | 解释 |
|---|---:|---|
| runtime build调用 | 221.760345 s wall；125.761418 s process CPU | 包含mesh/space及原生动作准备；不是全场完整setup，不能称setup提速。 |
| p6原生A6动作准备 | 133.426905 s | build内子项。 |
| p3原生A3动作准备 | 61.013354 s | build内子项；A6/A3准备时间不与build重复相加。 |
| 完整PC重复 | 5.145336 / 5.160140 / 5.129730 s；均值5.145069 s | 固定18-cell、固定输出工作量，不代表外层步数或完整场速度。 |
| 每个PC两次C父计时 | C1均值0.128535 s；C2均值0.133349 s；合计0.261884 s | PC均值减已计时BAL_H子项的4.640656 s未归因；不把差额归给粗逆。 |

历史E3 q4 math1小组件PC均值为2 nm `6.180631/6.252757 s`，两次C均值`0.480420/0.439009 s`。这是已有同18-cell/模式/RHS/PC次数范围的非配对历史数据，不是受控单变量试验；不能据此承诺完整场、每步或0.7 nm提速。5 nm历史均值`0.449162/0.542274 s`对本次p3 `0.298199 s`也仅作未配对组件参考。

P6端口缓存记录是shape/nbytes元数据，不读数组值，也不等于RSS。18-cell中12个cell无输入port项；18个`Hlocal`都是由`H=None`生成的零矩阵引用，本场显式H引用为0。`Hp/Hhat`各为`(3904,3904) complex128`、每个`243,859,456 B`。所有缓存角色合并按ndarray对象和backing root去重为146个对象/根、`640,002,592 B`；各角色的shape直方图见compact。引用载荷不可与RSS、MUMPS后端内存或其他重叠inventory相加。

2 nm watchdog一次流式核验：706/706状态可读、解析错误0、warning0，最大间隔`0.388181 s`、末样本距clock_end `0.038676 s`；进程树RSS峰`3,351,232,512 B`，低于真实硬线`1.3e12 B`，tree swap峰0、PSS/USS关闭、后代清场。全机pswpin/out变化0/0单独记录。主审按watchdog配置、summary和live样本确认实际RSS硬线为`1.3e12 B`。compact v2另解释summary的12 GB launch/planning cap是诊断字段；未修改launcher。

## 待启动审阅的5 nm正式回归草案

草案为唯一的5 nm、p6细层/p3精确A3粗层完整场回归，待主审审核最终clean source、命令和准入后另行放行。输入身份固定为`v6_interleave_5nm_p6h4_q3`，`execution_mode=full_solve`，input SHA `4ca279159a4b391fe4b05f47c5ef13891db3eade68993db71ade806158a42818`、physical SHA `96b548e4cd7fbec7f5397d6be7fa22cf5f9e0faaaeb2f70ff95cf01f0f8af88d`、resolved SHA `17a9657bd9cfb76baeed5aec07453057026ca20c1725c10fa44096bbab35d4d1`。模式库存600，mode SHA `dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645`；粗算子是真实A3，准确MUMPS因子一次，外层为零初值right FGMRES32、max2048，实际未知空间是p6凝聚trace+全部600个port变量；未凝聚原生p6 A6负责full residual与相关核验。未来运行source必须是最终clean完整SHA；目前e312ff721f0918c20d9b87ed1d72928b23d349df仅为当前base/文档收口HEAD，不能代替运行source。

几何比较分两条证据：

1. **自动同离散物理见证**：`physical_retained_condensed_v20.py`将该V6 profile经`V6_BASE_PROFILES`映射到`compare_retained_v5_output`，继而进入`compare_retained_5nm_output`。该函数内置的原始同物理完整场和600模式见证是`results/euv_grazing1_phi0/original_5nm_si_p6h4_balanced_h6_p4_native__full3d_iterative__mpi1__Mna/20260911T065955.813489Z`，不是V6 F5 `20261002T153058.967208Z`。旧reference轻量manifest显示source `85a681b9bd61104466888546b83df87c27806169`、同物理SHA；summary和所需见证文件存在。manifest内历史`status=launching`是占位值，不作为终态结论。
2. **V6 F5独立性能/已合格结果对照**：运行`20261002T153058.967208Z`、source `1828bc675f2862025e0eaed0beccf15982eb09e6`已由主审完整通过，且它本身通过上面的旧reference。它作为独立性能和已合格结果背景列出；当前runner不会因此自动执行p3与该V6 F5的直接pair comparison，不能把它写成自动门。

自动同离散门按Review V6 §4及既有比较器：FE L2与scaled-curl相对差各`<=1e-4`；同坐标E/H复场相对L2 `<=1e-4`，不拟合相位并保留原近零量绝对差报告规则；完整600模式复振幅向量相对差`<=1e-4`且不拟合相位；逐模式R/T功率最大绝对差`<=1e-6`；标量R/T/A/A_volume最大绝对差`<=1e-5`；能量闭合仍按`1e-5`。完整原生A6真残差`<=1e-6`继续由final packet实际调用`runtime.fine[physical_action]`核算；PC里的融合A6动作单独报告，不能替代它。A3每次完整原算子返回保持`<=1e-10`、最多两次同因子额外精化。所有其他方向、Floquet、complex MPC、DtN、恢复和物理Gate原样保持。

reference的V6 F5对应tracked compact `records/v6_5nm_terminal.json` SHA `1812c3f8fd368f6783277b3e95df45abfb994591add7f5a0ff75c5302de7f71c`，主审receipt SHA `b06c8044736c06b6db00bd792f83e1b075493d8e8869ac3813b6b500212cabd3`。实际boundary-fitted cell count必须从将来runtime mesh审计读取并记录；接受的same-discrete目标是3780 cells。输入`derived.mesh_cells=[13,7,35]`只代表名义初始划分，不能用其乘积替代真实3780。

完整启动草案JSON：[p3_full5nm_p3_regression_launch_draft_v1.json](records/p3_full5nm_p3_regression_launch_draft_v1.json)。状态`DRAFT_NOT_APPROVED_NOT_STARTED`，当前未运行、未冻结最终运行source。草案资源合同保留PORD64/int64/complex128、MPI1/math1、root CPU9、worker CPU24、interleave node0-1、effective available至少`1437438953472 B`、真实进程树RSS hard `1300000000000 B`、PSS/USS关闭、无时间截止；每次正式启动仍fresh检查主机、邻负载、ABI、内存、磁盘和任务锁。后续是否运行由主审审核具体clean-SHA包决定。
