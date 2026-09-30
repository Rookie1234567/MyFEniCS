# V16：已有表示辅助原有限元全空间 LSQR

本批执行 Review V13，固定原0.7nm三维缺口384hex/p3/q15、原材料／背景／入射RHS、MPC与40端口。方法的目的，是保留少量有用方向，同时让准确解能够离开这些方向；最终trace为Qc加完整空间外修正v。它不是纯神经预测，也没有训练隐藏层。完整有限元资格为 **0/6**，最终0.7nm目标模型／48小时资格仍未获得。

## 1. 身份与实现

| 身份／单位 | 实际冻结值 |
|---|---|
| base／Review V13 | ccd357885f7f9be84efe3be07868cc94f13d93fc／399c6a0f2568261c4dcaf7cdfb29499986e577bb |
| 正式物理与验证source | ef60675dada2556a5527101f90fc83540d60e242 |
| GPOLY原A/U/R构造source | 01ed98655c9eb2949ea29a35fd82d1881a5a2508；只复用hash合格因子，未重复QR |
| canonical worktree／upstream | /home/fenics/Projects/NN-Lab／origin/task42_neural_coarse_inverse |
| 材料与alias | SI_OPTICAL_CONSTANTS_USER_20260929_V1；source字符串0.699999988明确alias到nominal0.7；n=.999885140474+4.32477054e-6i；epsilon=n*n |
| physical／mode SHA256 | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de／93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| full／trace／internal／slave／port | 34050／18144／13824／2082／top20+bottom20 |
| Q库存 | G0 1560＋共同补充1538＝3098；NN文件保存1544列，只取既有前1538；Q和原master顺序绑定 |

可复用数值核进入src/solvers，runner只作薄分派。五个dat逐项validate，再在clean源码上执行；[run index](records/run_index_v16.json)绑定每次source、输入、resolved、manifest、数组与监督证据。文档HEAD不是运行source。

## 2. 算法与真实准入

H是原凝聚40×40 Hhat，保留全部端口并精确闭合；它不是原Hp。Q是trace方向，U是这些方向经过原方程作用后的方向。先构造A=barS Q=UR，再把迭代限制在已经处理部分的正交补上；投影只按向量作用，不生成18144阶投影矩阵。

```math
P_t=I-QQ^H,\quad P_r=I-UU^H,\quad
M=P_r\bar S P_t,\quad M^H=P_t\bar S^H P_r,\quad f=P_r\bar b.
```

每次原方程审核都重建完整候选，而非只检查迭代估计：

```math
v=P_t y,\quad c=\operatorname{solve}(R,U^H(\bar b-\bar S v)),\quad
t=v+Qc,\quad \alpha=H^{-1}(b_p-Ft),\quad
\bar b-\bar S t=f-My.
```

R使用三角求解，Hhat只作40维小解。投影产生的已知零空间不表明原Maxwell奇异。空Q与非空Q的小型非Hermitian复数／非零port／明显Q外解、错误共轭与混Q/U反例已测。省去前向Pt在精确算术中因Pr消去barS Q而可等价，不能伪造反例；漏Pt的反例检查Q外分量的坐标定义；在配对精确且c重新求解时，省略Pt也可能给出相同完整t，不能伪称它必然造成残差失败。错误共轭／Q-U混用则独立以原作用和残差检查。

空Q/GPOLY已保存真实dot/projector/恒等式和Q外代数见证；两库Q/U正交、原A重组、三列／两组合及Hhat均已保存。GNN虽进入了真实物理解算，控制流表明内部准入成功，但其M/MH dot/projector标量未持久化，随kill丢失，checker将该项列为unknown，不伪造合格数值。详情见[接口检查](records/projected_operator_checks_v16.json)。真实非零见证只作代数恢复，不求第二个难RHS，不覆盖原b；齐次误差恢复去掉内部特解。

GPOLY实测Q／U正交缺陷为6.923e-16／7.164e-16，A=UR重组差9.709e-16；两像基有效秩均3098，固定阈值1e-12。Hhat条件数13284.1630低于1e10限值。原作用制造的非零Q外／40端口见证，已知完整z回收差3.818e-13、制造方程残差4.064e-16、去除内部特解后的齐次恢复配对9.361e-17；这些仅认证接口代数，不是原物理RHS的求解通过。

首次未缩放随机压力状态的原残差恒等式 **1.1125765e-7>1e-8，FAIL** 原样保留。该状态的原作用远超本micro物理b尺度。最小接线复核采用非零随机状态，其barS响应规范到norm(barb)，固定norm(原b)分母与1e-8门限保持；新实测为1.0282828e-12。该通过不认证任意巨大幅值状态；物理路线每64步仍独立用原b检查同一恒等式。监督器尾部route_budget只读Mapping序列化错误也保留，Task042边界改成结构化metadata，未修改安装环境。两项明确错误合为一次修复批／一次短重放，原3098列A与QR未重算；原运行source/失败raw与采样wall下界保留。

## 3. 三条独立物理路线

| 路线／同一0.7nm micro | 维数Q＋完整补空间 | GK更新／原作用次数 | 原Schur／native残差 | 停止原因 |
|---|---|---|---|---|
| CLOSED-LSQR-0 | 0+18144 | 4096／8523 | 0.0694190731／0.026920979 | STAGNATION_CONTROLLED_STOP |
| AUG-LSQR-GPOLY | 3098+15046 | 816／1698..1714上界 | 0.0126178958／0.00489326771 | RESOURCE_CONTROLLED_STOP；原审核768／向量仅256 |
| AUG-LSQR-GNN | 3098+15046 | 85／181..197上界 | 0.122363732／0.0474531179 | RESOURCE_CONTROLLED_STOP；原审核64／向量仅0 |


三条均y=0，不互相warm start、无参考初值。审核每64步；正常最小快照为0/256/1024/2048/最终；资源kill未保存最近完整迭代，形成明确证据缺口，不把旧快照称中断终态或可续跑checkpoint。缺失点按实际not_run。[完整迭代历史](records/iteration_history_v16.csv)包含原Schur/native/port、估计与实际残差、Qc/v系数范数和成本；[固定空间底限](records/space_floor_v16.json)仅是浮点估计。空间外v允许突破旧约.518／.580平台，但只有原1e-6及全部物理门限通过才算合格。

[同工作量比较](records/matched_work_comparison_v16.json)分别列同更新／同在线原作用次数与同冷wall截止附近的真实审核值。wall用原审核点包围，不插值制造残差。GPOLY的首次失败设置、短重放全部计入统一2700s；GNN单独建像一次。两条增强都包含共同神经G0，GPOLY并非完全无神经；两者只隔离局部补充差异。没有hidden训练收益声明。

GPOLY在PSI full avg10达到0.1、连续三个每5秒health观测后受控SIGKILL，own RSS2.498GB／swap0，停止并清场；未重启。标量历史最后完整更新816，原审核最后768（Schur.0126178958/native.00489326771），但其向量未持久化。最后可用向量是256步，标量不能重造其后场。表中GPOLY-FINAL只是最后可用快照的索引名，独立场验证实际使用256步，并非816步终态；[停止与计数边界](records/controlled_stop_snapshot_v16.json)单列。组件S/SH计数及投影/审核叶计时随进程丢失；已记录组合调用下界1698、保守cap上界1714，并为一个可能未落盘audit预留预算，不把这些上界当精确实测。停止五分钟后的一次只读复核PSI avg10=.04、余量合格，才准入独立GNN；未改变压力阈值或邻任务。因果归因INCONCLUSIVE，比较条件发生变化。

GNN在完成3098列像、QR和秩检查后，实际推进到85步，最近原审核为64步（Schur.1223637316/native.04745311785）。持续PSI full avg10=.19/count3触发同一资源停止，own tree4.0026112GB／swap0并清场；没有重启。只保存0步向量，GNN-FINAL在下表仅表示该索引，不能以0步场当作85步场或方法终态失败。其原作用组合下界181／cap上界197、setup作用3118可核；两个中断合计32作用和2audit保守预留，组件计数及叶计时unknown。随后第二次、仅针对低内存VERIFY的有限资源复核PSI恢复0，允许一次独立验证；不再运行任何求解器。两次停止都没有可比较的邻任务阶段吞吐记录，不能将自然阶段变化或PSI直接归因于Task042。

## 4. 冻结后的一次独立有限元审核

全部路线、选择及状态hash冻结后，独立进程才读旧REF7。参考本次独立native为 **1.43744487e-12**；没有新LU、参考反馈、拟合、相位或幅值校准。一次FE环境验证6个去重状态，含两个旧组合基线、空Q完整终态／1024快照和GPOLY256／GNN0最后可用快照。[参考身份](records/reference_audit_v16.json)、[全部复通道](records/field_channel_checks_v16.csv)、[场／selected E/H／功率差](records/field_channel_checks_v16.json)逐项保留。

| 独立验证状态／相对误差无量纲 | Schur／native | 散射E／scaled-curl | total E／scaled-curl | 40复通道 | 严格资格 |
|---|---|---|---|---|---|
| V15-UNION-POLY | 0.517713838／0.200771384 | 0.283235368／0.283293409 | 0.0296391153／0.0296457515 | 0.011883817 | FAIL |
| V15-UNION-NN | 0.579985792／0.224920683 | 0.766070574／0.766240878 | 0.0801653204／0.0801846636 | 0.0258087695 | FAIL |
| ZERO-FINAL | 0.0694190731／0.026920979 | 0.999924826／0.999905525 | 0.104636957／0.104636923 | 0.104507689 | FAIL |
| ZERO-1024 | 0.075671135／0.0293455523 | 0.999952615／0.999937884 | 0.104639865／0.10464031 | 0.104519499 | FAIL |
| GPOLY-FINAL（仅落盘256步） | 0.0469482476／0.018206708 | 0.14699703／0.147016298 | 0.0153824783／0.0153847866 | 0.00961350225 | FAIL |
| GNN-FINAL（仅落盘0步） | 0.579985792／0.224920683 | 0.766070574／0.766240878 | 0.0801653204／0.0801846636 | 0.0258087695 | FAIL |


严格原Schur/native/增广/port≤1e-6，恢复/identity≤1e-10、slave-zero；total/scattered E/H、scaled-curl、selected复场与40复通道≤1e-4；R/T/A/A_volume差≤1e-5、逐通道功率差≤1e-6、能量闭合≤1e-5。残差与场分别判断，未合格功率仅为diagnostic；以下不是official R/T/A。

本模型各区mu_r=1且频率相同，H由E的curl乘同一复常数得到，因此表中total/scattered scaled-curl相对误差也给出对应H的相对误差；selected H另以完整复值逐项保留。全部通道保持原模式键、极化和参考面，复误差不用于校相或重归一化。

| 最终状态；仅未资格diagnostic | R00_s／R00_p／R00_total | R_total／T_total／A_balance | A_volume | 能量闭合差 |
|---|---|---|---|---|
| ZERO-FINAL | 0.113414647／6.92046423e-16／0.113414647 | 0.113415022／0.885141132／0.00144384546 | 0.00531416009 | 0.00387031463 |
| GPOLY-FINAL（仅落盘256步） | 0.116669264／1.66147737e-08／0.116669281 | 0.116670296／0.87075277／0.0125769334 | 0.00527406943 | 0.00730286395 |
| GNN-FINAL（仅落盘0步） | 0.101495832／5.08402478e-07／0.101496341 | 0.101499785／0.837834135／0.0606660801 | 0.00510533807 | 0.055560742 |


Qc与v是系数正交分解，不能把它们的物理场能量直接相加。已保存的完成步快照包含GK递推向量及保存时计数，0步只作初始状态证据；后续审核计数另记。没有递推resume适配，这些不是可直接续跑checkpoint。两次资源SIGKILL没有冻结最近完整迭代，只能使用较早落盘证据；所有部分作用与失败仍计费。

## 5. 资源、时间与不存在的对象

| 成本／资源口径 | 实测／边界 |
|---|---|
| 固定窗口 | start 2026-09-30T12:02:44.363096Z；重负载截止15:47:44.363096Z；总截止16:02:44.363096Z；未刷新 |
| 统一单路线 | 2700s，含设置／加载／保存；最多4096更新，无阻尼／新尺度／新PC；其余上限按原review |
| 正式监督wall新增下界 | 4447.81145 s；首次尾部JSON失败只有最后采样elapsed下界，完整launch结束时刻unknown |
| 同时整树RSS采样峰／own swap／VRAM | 4003057664 B／0／0；launcher＋worker＋后代，0.5s采样，不冒称连续cgroup内核限额 |
| 历史正式费用 | 至V15下界16776.579534446006s；至V16新下界21224.391s；旧辅助unknown保留，测试／失败另记 |
| CPU与环境 | 每stage现场选空闲物理核、MPI1／数学1／DataLoader0；GPU不用；Task042独立activation/cache/ownlock，ABI complex128/int64复核；邻任务设置未改 |
| 计数／容量上限 | 全批原S+SH cap上界16724≤50000；新A列6196／2套image QR；audit预算计数上界90≤240；场状态6≤10，两个中断预留32作用／2audit，组件精确总数unknown |

[分阶段资源](records/resource_costs_v16.json)记录装配作用列、QR、秩检查、加载、投影、三角解、原作用、audit及I/O总体成本。各叶计时嵌套，不与包含它们的phase wall重复相加；triangular_solve计时含UH收缩。Q/U/R与所有workspace计入树峰，事前常驻上界7.6e9B≤8GiB；只常驻一套大基，保存两套必要U/R，不保存A或完整Krylov基；新增持久artifact限3GiB，总Task限20GiB／free50GiB。

| 正式阶段；shared-workstation，单位s | 监督wall实测／下界 | 说明 |
|---|---:|---|
| 首次GPOLY预检／设置 | 647.893234下界 | 尾部Mapping写出失败，完整结束wall未知；A列作用279.609031、QR104.244424、秩检查91.144571已单独保存 |
| 短预检重放 | 28.463185 | 复用hash合格U/R；没有第二次image QR |
| 空Q4096步 | 1300.011071 | 完整终态、标量和叶计时可用 |
| GPOLY物理迭代 | 1963.633901 | 持续压力停止；加已计费设置669.987160，路线合计2633.621061；中断叶计时unknown |
| GNN设置与物理迭代 | 486.673703 | A列作用163.460998、QR57.703288、秩检查48.565617已保存；其余中断叶计时unknown |
| 一次独立VERIFY | 21.136353 | 6个实际冻结状态，旧REF7仅在本阶段读取 |

新ignored artifact逻辑体积2,127,996,850B，加本批results约73.0MB，合计小于3GiB；全Task042 artifact约9.87GB，独立完整资源流与旧数组未删除。各正式阶段现场审核后恰好均选CPU0，并非永久预留该核；MPI1、数学线程1，避开当时忙碌物理核及SMT同胞。

候选作用仅使用原local action packet，未构造全局FE S、正规方程、全投影方阵、全局p4因子或fallback。确实存在3098阶像QR三角块与40维Hhat小因子；独立FE验证复用原未凝聚组装审核，其矩阵不作为在线逆。旧准确REF7离线生成成本仍在历史账中。不能将上述边界泛化成整个项目“从未装配或分解”。

所有成本为shared-workstation。自身swap、余量、PSI和短邻阶段观测保留；没有建立可比邻任务吞吐证据，不能证明绝对零干扰。未达到相同严格精度时不报加速倍数，旧基生成不是免费setup，最大模型的单步投影／存储与48小时预算仍unknown。

## 6. 收口

本批三路线均已启动并按真实停止条件收口；两个增强路线是资源中断，终态配对未完成，不能归为已充分执行的数值方法失败。独立验证只审核实际保存状态，历史V11–V15失败和旧p4研究关闭状态保留。字段与norm从raw重算，checker不相信status。[资格与分流](records/qualification_and_dispatch_v16.json)、[测试](test_summary.md)、[changed_files](changed_files.md)、[发布／GitHub表格公式](records/publication_checks_v16.json)为入口；GitHub服务端结构与未观察的浏览器glyph明确分开。

现存可审核向量中最低Schur是GPOLY256步，不能称终态赢家。空Q4096步突破固定空间残差平台，散射场仍近乎未恢复；GPOLY256步同时改善原残差与散射场，但远未合格。GNN终态缺失，局部神经／多项式的完整配对贡献INCONCLUSIVE；参考未用于挑点。唯一下一建议：在新的review授权和稳定资源准入下，仅做一次冻结GPOLY/GNN的有界配对复试，每64步审核以两个滚动槽先原子保存完整递推／候选，再写汇总，补齐中断终态及同工作量证据；算子、基、精度和迭代预算保持，本批不实施。 本批无新p4参考、最大模型、hidden训练、行尺度、GPU或merge。
