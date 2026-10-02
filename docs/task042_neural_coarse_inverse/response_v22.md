# Response V22：p1来源trace Galerkin校正的真实暖冷对照

本批按Review V19完成真实p1传递、固定粗层与PC资格、无PC暖对照N、PC暖校正P、独立零trace路线Z，以及冻结后的独立FE审核V。条件T未准入。原方程合格0/3，新候选完整同离散资格0/3；连同历史暖参照，审核0/4。没有新合格解、神经训练增量或同严格精度加速，最终0.7nm大模型/48小时仍NOT_QUALIFIED。

本次让低阶有限元场提供一组可跨单元耦合的修正方向：先把真正的p1边/面矩插值到原p3有限元空间，再取独立trace。将原p3方程投影到这些方向，得到1248阶小粗矩阵；解粗矩阵后仍保留全部fine方向继续GMRES。它改变每次残差校正，不改变原有限元方程。收益候选是减少困难方向的搜索；代价是真实传递构造、一个有容量上限的全局粗LU、每次额外fine作用与粗解。结果没有显示本固定配置能突破暖残差平台。

## 固定身份与实现

原模型为0.7nm、384hex/p3/h0.175nm/q15、三维缺口、1度/azimuth0/s、双Floquet/Fourier-DtN。full34050、trace18144、interior13824、slave2082；top20+bottom20，完整z18184。材料唯一canonical路径是`input/materials/si_optical_constants_v1.json`，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`，Si n=0.999885140474+4.32477054e-6i、epsilon=n*n；source字符串0.699999988仅明确alias到nominal0.7，未插值/联网替换。

本批实际求解source：`24fbbad55fbef07b75533e60fc1869749a2f8777`（S/N/P/Z）；独立验证source：`7a7a44ea567abfc119e4eeec474e3e1bea46b519`。正式run均clean，最终文档HEAD不冒充运行source。Review锚点`4d14192e082117e69f76cd3a94c549557ce5693b`；冻结base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。samebranch linked worktree/common Git与upstream已核验，未操作其他工作树、合并或改写历史。

物理SHA `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`；材料SHA `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`；模式SHA `93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262`；action NPZ SHA `9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454`。全量路径、文件/成员hash、input_original/resolved/manifest/source与实际CPU见[run index](outcomes/records/run_index_v22.json)。

粗层准确名称 **P1_TRACE_GALERKIN**。p1 full1494、独立1248；T是18144×1248、217296个存储项、4,418,500B CSR载荷。所有列只按欧氏范数归一化，不删小项/截列；TᴴT数值秩1248，特征值范围约[0.9999999999999941,1.0000000000000069]。3个真实FE见证（2个固定随机复系数、1个单边）与独立DOLFINx插值最大系数差7.812e-16、场差1.097e-15、curl差5.438e-15；复杂Floquet、方向、高阶矩、共享实体、MPC和对偶配对通过。先验证完整场传递再取trace，不能将其齐次恢复内部场等同于插值p1内部场。

Ac从全部原cell Schur及Floquet展开局部累加，端口项使用原C/F/Hhat；没有分别凝聚curl/mass。8个原barS粗见证最大运算尺度差6.444e-16（限1e-10）。Ac 1248²，array SHA `fc36fbd1d1e74e05922d8a849273f4a03861c06439d972f52dcfba42ad2dcddd`。固定complex128部分选主元LU、每个粗RHS恰好一次残差精化，rcond1估计0.000269972629637312、cond1估计3704.079192558983；不是fine条件数。8个粗解最大相对残差2.235e-15（限1e-8），零RHS精确零，未调shift/drop/排序/p级或精化次数。

Ac+LU+pivots显式载荷49,845,120B；粗矩阵/workspace规划204,711,936B，完整同时规划3,613,375,308B<8GiB；完整transfer临时上界289,325,056B<1GiB。载荷/规划与采样RSS分开。S/P/Z共3个独立数值LU，同一Ac/LU/pivot hash配对；未构造global fine K/S/CSR或p4因子，没有ILU/旧Q-U-R/神经权重/hidden fallback/private audit CSR。

明确登记 **GLOBAL_BOUNDED_TRACE_GALERKIN_FACTOR_PRESENT**。这是有界全局粗因子，不是factor-free、独立p1重新离散方程、已资格化p1/p3 V-cycle或目标规模可扩展证明。独立离线误差投影另外有一次1248阶Gram Cholesky，仅用于诊断，不进入PC/loss或候选。

右PC保持完整fine方向：

```math
A=\bar S,\quad A_c=T^HAT,\quad \tau=\sqrt{1248}/\|A_c\|_F=0.13558083643793006,
\qquad B(r)=\tau r+T A_c^{-1}T^H(r-\tau Ar).
```

外层每周期解(A B)y=r，M=None、y0=0，再用t_new=t+B(y)，绝不把y当trace。固定GMRES256/maxiter1/callback_type=pr_norm、相对容差0、atol=1e-8*norm(原完整b)，正式原方程门限仍1e-6。原Hhat闭合40端口与原仿射内部恢复保留；Hhat不是Hp，F未假定Cᴴ。复杂非Hermitian/非互伴40port小测试、真实PC线性/重复性/粗平衡以及真实dat→PC→GMRES→close→保存→独立audit接线均通过。

原ActionPacket数学apply/recover/uncondensed/audit保留，class64为独立精确opt-in作用；每周期新/旧原残差差/b检查通过。审计包装只计费，未将旧oracle重定向到新backend。旧V21作用成本配对可复用，本批没有重跑旧工程campaign，也没有新exclusive class64计时记录；不能从嵌套wall相减声称无争用加速。

## 物理求解与独立资格

N和P均独立从原V21 C-FINAL开始；该文件SHA `680f58e5e58704fc69f0b539c8c411131ce697b7811445eb9643bbf92a736072`。reader只解压trace/port/z/residual，x/CU/方向不解压。Z新进程只读物理/packet/T/Ac，从零trace开始，端口和内部特解按原b闭合/恢复，不强行置零；名称是ZERO_TRACE_FROM_FROZEN_OPERATOR，不是从几何开始的全流程fresh run。

下面原rho是完整norm(b-Sz)/norm(b)，native是恢复内部后原未凝聚方程残差，二者分母不同且必须分别过Gate。全部为measured；表中wall含原审核与保存，B内部fine作用计入总S+SH。

| 路线 | 完整周期 | Arnoldi内步 | 原rho起点 | 原rho最终 | native最终 | S+SH | 监督wall(s) | 真实停止原因 |
|---|---|---|---|---|---|---|---|---|
| N | 4 | 1024 | 2.5281170328e-06 | 2.50988202767e-06 | 9.73341741358e-07 | 1060 | 142.759495938 | FIXED_CYCLE_LIMIT |
| P | 4 | 1024 | 2.5281170328e-06 | 2.51429776221e-06 | 9.75054180268e-07 | 2106 | 361.332815065 | FIXED_PROGRESS_RULE_STOP |
| Z | 32 | 8192 | 1 | 0.00411726221107 | 0.00159668985526 | 16778 | 2001.9549088 | FIXED_CYCLE_LIMIT |

N的暖残差下降约0.72%，P约0.55%；相同4×256内步，P原残差略高于N且成本更高，未满足10%继续条件，没有突破原2.5e-6平台。P散射场较N略小并不替代方程/逐通道功率Gate，不称加速。Z每4周期满足20%继续条件，累计约243倍残差下降；32周期后仍为0.004117262211，按固定上限收口，不能将有限未通过推广为永久不能求解。T需要P通过或至少5倍rho改善，实际两者均未满足，not_run不是转移失败。

返回后先原子保存y/By/实际trace，再保存完整z/port/residual、旧oracle审核和commit；0/最终及每周期状态/hash均在ignored V22 artifact。不存在FIRST_EQUATION_PASS，未做抛光或用参考选最好checkpoint。历史负结果和V21 B读取失败保持FAIL_RETAINED，新增reader反例不追溯改写历史。

全部求解/选择/hash冻结且actor退出后，一次独立FE环境才读取既有REF7；4个去重物理状态，另3个离线误差分量积分，总field_states7≤12。没有新reference LU、参考warm start、监督拟合或回算。REF7本次原native=3.0179630439596658e-12、独立total-native=1.4374448661883937e-12、Schur=6.4241465032853714e-12，实际小残差保留而非置零。

全部4状态recovery≤4.807e-13、原Schur/native恒等式≤5.421e-13、slave storage=0；端口full-b和运算尺度残差≤1.842e-16。接口可信不代表原方程合格。

| 冻结状态 | Schur≤1e-6 | native≤1e-6 | 独立total-native≤1e-6 | 散射E≤1e-4 | 散射H/curl≤1e-4 | 单通道功率差≤1e-6 | 完整资格 |
|---|---|---|---|---|---|---|---|
| V21-C-FINAL | 2.5281170328e-06 | 9.80413346383e-07 | 3.40202831061e-07 | 7.81608038914e-05 | 7.81769668025e-05 | 1.71964465112e-06 | FAIL |
| N-FINAL | 2.50988202767e-06 | 9.73341741358e-07 | 3.37748990869e-07 | 7.80692408032e-05 | 7.80854267327e-05 | 1.70671444066e-06 | FAIL |
| P-FINAL | 2.51429776221e-06 | 9.75054180268e-07 | 3.38343204781e-07 | 7.79710706735e-05 | 7.79872769396e-05 | 1.69129085703e-06 | FAIL |
| Z-FINAL | 0.00411726221107 | 0.00159668985526 | 0.000554050400082 | 0.022911848074 | 0.022911564544 | 0.00266031533569 | FAIL |

| 状态 | total E≤1e-4 | total H/curl≤1e-4 | selected E≤1e-4 | selected H≤1e-4 | 40复通道≤1e-4 | 能量≤1e-5 |
|---|---|---|---|---|---|---|
| V21-C-FINAL | 8.17912356651e-06 | 8.18097018782e-06 | 9.08427294495e-06 | 7.16511649663e-06 | 3.21045778938e-06 | 1.9398597273e-06 |
| N-FINAL | 8.16954196326e-06 | 8.17139081153e-06 | 9.06904725693e-06 | 7.16267953575e-06 | 3.18368130359e-06 | 1.92935189602e-06 |
| P-FINAL | 8.15926896731e-06 | 8.16111974879e-06 | 9.05356968757e-06 | 7.15864125971e-06 | 3.16141875666e-06 | 1.90665089428e-06 |
| Z-FINAL | 0.0023976063091 | 0.0023976221406 | 0.00239961027075 | 0.00239619737624 | 0.00239530818708 | 0.00442591237104 |

在原mu=1、H=curl(E)/(i*k0*mu)约定下，全域scaled-curl相对误差也是相应H误差的derived等价指标；selected复E/H独立保留。表中场误差相对同mesh/p3参考，不是离散误差或continuum收敛。完整40复通道的原键、极化、参考面和复误差逐项保存，未校幅相。

| 状态（unqualified diagnostic） | R00_s | R00_p | R00_total | R_total | T_total | A_balance | A_volume |
|---|---|---|---|---|---|---|---|
| V21-C-FINAL | 0.117644973437 | 7.01536540619e-13 | 0.117644973438 | 0.117646030384 | 0.87704950259 | 0.00530446702554 | 0.00530640688527 |
| N-FINAL | 0.117644975915 | 6.89132171785e-13 | 0.117644975916 | 0.117646032863 | 0.877049489659 | 0.00530447747772 | 0.00530640682961 |
| P-FINAL | 0.117644968735 | 6.77591854755e-13 | 0.117644968736 | 0.117646025683 | 0.877049474236 | 0.00530450008093 | 0.00530640673182 |
| Z-FINAL | 0.119393593766 | 8.12783946375e-15 | 0.119393593766 | 0.119394699074 | 0.879708145904 | 0.000897155022207 | 0.00532306739325 |

以上R/T/A均为未合格场的UNQUALIFIED_DIAGNOSTIC，不发布official结果。暖PC最大R/T/A/A_volume绝对差1.89766232e-6、能量1.90665089e-6通过对应1e-5门限，但最大单通道功率差1.691290857e-6>1e-6，故完整失败。Z最大总量差0.004409242721、体吸收差1.666964709e-5、单通道差0.002660315336、能量0.004425912371，均超相应限值。逐通道功率用原批准公式从160项已保存振幅离线derived复算，与原max/R/T配对差≤1e-12；未新增FE或求解。

## 一个离线误差诊断

冻结后只对暖原点做一次17.005972665s离线诊断。误差e=ref-warm，正确场为recover(e)-recover(0)=recover(ref)-recover(warm)，先去掉内部特解；两种恢复运算尺度差1.478e-12。trace Gram投影c=(TᴴT)^-1*Tᴴe_trace只作诊断，port用零完整RHS齐次闭合，补空间保留完整误差之差。参考权重/误差没有回填任何候选。

| 同一暖误差；measured | 完整误差 | T投影 | 补空间 |
|---|---|---|---|
| trace欧氏范数 | 9.30427771721e-5 | 9.25730736218e-5 | 9.33725998978e-6 |
| 齐次场L2 | 1.56642854474e-5 | 1.47523239820e-5 | 1.57150500629e-6 |
| 齐次scaled-curl | 1.56670914461e-5 | 1.55827465376e-5 | 5.25080938569e-6 |
| 原barS trace作用范数 | 2.09020359788e-7 | 0.000511750874547 | 0.000511750880481 |

trace投影保留约98.992898%的平方范数；场投影L2约为完整误差94.18%，curl约99.46%，补空间curl仍为33.51%，不能按系数范数忽略它。场分量并不正交：L2复交叉实部1.26345738613e-11，curl实部-1.24676172396e-11；平方和加交叉项与完整值最大运算尺度缺陷4.617e-15。原A作用的复交叉实部-2.61888938791e-7，两项均远大于组合；完整原作用恒等式差2.930e-12。

这说明当前trace度量下表示覆盖较强，但细层补空间作用与粗作用有强抵消。它不是物理L2最佳投影、fine条件数、谱结论或通用误差界；强抵消不自动等于病态，也不证明唯一失败原因。粗矩阵自身安全、小解准确、映射通过与外层未收敛同时成立，必须分别报告。

## 全过程费用、隔离与停止

全批不可刷新start **2026-10-02T03:54:44.446861Z**；重负载截止07:24:44.446861Z，总截止07:54:44.446861Z。UTC/monotonic/boot落盘，恢复上下文、新stage、commit/push及交付前读实时钟，未扣除未知间隔。数值队列结束立即保存minimum_result_package；最终实际交付时刻由final_git_receipt记录，准备时刻不冒充push时刻。

| stage | 实际CPU | 监督wall(s) | launch wall(s) | 同时树峰(B) | S+SH | B | 粗三角解（保守） | audit |
|---|---|---|---|---|---|---|---|---|
| SETUP | 10 | 513.252565132 | 514.681474237 | 738320384 | 21 | 4 | 60 | 1 |
| N | 0 | 142.759495938 | 144.535282872 | 545697792 | 1060 | 0 | 0 | 5 |
| P | 0 | 361.332815065 | 362.750218954 | 624783360 | 2106 | 1040 | 4168 | 5 |
| Z | 0 | 2001.9549088 | 2003.34080855 | 625074176 | 16778 | 8292 | 33176 | 33 |
| VERIFY | 0 | 73.587434014 | 74.978655354 | 830451712 | 9 | 0 | 2 | 5 |

正式one-run监督wall合计 **3092.88721894s**；launch wall **3100.28643996s**。外层solve监督3029.612315732s与verify监督77.017783043s已包含这些子阶段，不能再相加。真实transfer构造495.332829614s、coarse装配1.725844726s、S粗LU/cond setup0.270902258s；P/Z内部PC总时间189.568333443/1114.732272262s，其中coarse solve69.668712874/420.808529151s是嵌套，不重复累计。独立完整FE审核阶段73.587434014s含17.005972665s离线诊断。

辅助监督实测合计130.337806194s（截至最终相关回归/文档修复快照），包含原失败；其余实现/等待/交付时间不从总elapsed扣除。辅助成本采用[费用快照](outcomes/records/resource_costs_v22.json)逐项实测，失败fixture、超时清场测试、API/ABI、schema、checker、后处理均保留；后续低负载交付费用计入真实总elapsed，旧辅助精确累计unknown保持。正式研发历史下界为 **74063.4870035s**，不是单一成功解的端到端成本。暖点依赖V14/V15库、V16 image、V17/V18 LSQR、V19 L及V21C；精确per-solution上游拆账unknown，暖尾部几分钟不能当整个解时间。Z本批不读神经warm/basis，但仍依赖此前冻结packet/映射，其packet生成费用不能消失。

预算charged S+SH19974/40000、B9336/20000、coarse triangular保守37472/41000、原audit49/160、field_states7/12；T/Ac各1次、独立PC因子3/4。37406是显式LU解/精化及诊断Gram解的保守L/U pass计数，另为3次gecon内部未知次数按现场LAPACK3.12.0官方ZLACN2 ITMAX5和ZGECON每请求2个三角解追加66次上界（[ZGECON](https://raw.githubusercontent.com/Reference-LAPACK/lapack/v3.12.0/SRC/zgecon.f)、[ZLACN2](https://raw.githubusercontent.com/Reference-LAPACK/lapack/v3.12.0/SRC/zlacn2.f)）；没有伪造内部实测数，也不清零原run账。真实setup原作用21≤512。

全过程采样同时整树峰 **912175104B（0.849529GiB）**，包含launcher/worker/JIT/BLAS/全部后代；不是显式数组或各阶段峰的和。own swap0、VRAM0。MPI1、数学线程1、DataLoader0，GPU隐藏；实测OpenBLAS3个入口均1线程。S实际CPU10，N/P/Z/V实际CPU0，各stage现场核对空闲物理核并避开忙SMT，编号不固定。自身nice10/ionice idle，未改邻任务/共享prefix/环境/锁/watchdog/系统BLAS、CUDA或全机swap。

规划≤8GiB、整树warning12/hard16GiB、0.5秒监督及原PSI full avg10≥0.1百分数连续3次5秒保护保留；本机未获独立cgroup权限，不能宣称kernel连续硬限额。正式健康样本PSI full avg10最大0、无数值资源停止/重入/修复（交付辅助修复另列），最低effective available约1.970728e12B，保留系统10%+邻增长128GiB+Task04216GiB。可读邻阶段缺少可比同时指标，因果影响INCONCLUSIVE，不承诺绝对零干扰；全部成本标shared-workstation，无争用加速INCONCLUSIVE。新artifact约150.1MB（费用快照）<2GiB；全部大数组/缓存位于NN-Lab ignored目录。

| 未运行项 | 原因与分类 |
|---|---|
| T历史L-GNN转移 | P原方程不通过且rho仅降约0.55%，未达5倍准入；not_run |
| FIRST_PASS抛光 | 没有原方程通过点；not_run |
| 新p4参考、最大模型、其他波长、GPU、NN训练 | 本批边界，not_run |
| 旧p4强逆/ILU ordering/fill/shift/level/drop、列尺度/rank/网络扫描 | 研究路线关闭或未授权，not_run |
| 全仓pytest/MPI2/4/CI/环境升级 | 本批共享MPI1 focused范围，不声明CI；not_run |
| GitHub视觉公式/表格 | 精确Review/结果页面未取得视觉证据；NOT_VERIFIED；本地结构不替代视觉 |

没有正式数值重放、资源重入或数值实现根因修复。交付辅助R01修正基线reader的相对/绝对路径，R02修正新journal链接的.json/.jsonl扩展名；原失败费用/日志保留，只重放轻量static检查；R03将schema测试的validate-only子进程隔离为自身fixture，实际冻结窗口/ledger不变；R04修正自身进程检查将检查shell源码误报为actor的匹配边界，未杀任何进程，没有重复PDE。计划内fixture首次9pass/1fail使用了比真实driver atol更严的期望，保留原失败成本；只更正小测试期待为真实1e-8残差/1e-7解差，并未放宽生产Gate。最终相关事务/映射/reader/超时/投影与离线checker合并回归33passed/1deselected；治理/Markdown12passed/1旧总账failed，两个失败字段在起点逐项相同。最终本地结构/历史保护通过；详见最终records。旧task/review/response/raw保护，导航/总账仅新增前缀，不覆写历史结论。

## 唯一下一建议与证据入口

唯一下一建议：在同一冻结T、同一暖点原残差上，仅比较一次原作用像最小残差粗校正与当前Galerkin粗校正。前者直接用barS*T的薄QR求能减少当前原残差的T系数，保留原40端口及完整fine方向；不读REF7，不造正规方程，不改T/rank/tau或扫参数。目的是区分“同一粗空间中的左测试/粗细耦合选择”与“必须增加空间”这两个可能性。依据是约99%的trace误差平方范数已有表示，但其两个分量的原A作用约为完整误差作用的2448倍并抵消；这尚不证明唯一根因或病态。本批未实施，须下一review另行授权。

- [来源/物理/材料/array身份](outcomes/records/source_inventory_v22.json)、[正式run index](outcomes/records/run_index_v22.json)、[checkpoint](outcomes/records/checkpoint_inventory_v22.json)。
- [真实传递](outcomes/records/transfer_checks_v22.json)、[coarse容量/原作用](outcomes/records/coarse_identity_capacity_v22.json)、[LU/估计](outcomes/records/coarse_lu_v22.json)、[右PC](outcomes/records/right_pc_checks_v22.json)。
- [逐周期残差](outcomes/records/cycle_history_v22.csv)、[候选对照](outcomes/records/candidate_comparison_v22.csv)、[独立原方程/场](outcomes/records/field_checks_v22.json)、[40复通道](outcomes/records/field_channels_v22.csv)、[逐通道功率](outcomes/records/per_channel_power_v22.csv)。
- [一个离线暖误差](outcomes/records/offline_warm_error_v22.json)、[cold读取与历史lineage](outcomes/records/lineage_cold_access_v22.json)、[环境](outcomes/records/environment_identity_v22.json)。
- [独立Gate](outcomes/records/qualification_and_dispatch_v22.json)、[成本/资源](outcomes/records/resource_costs_v22.json)、[journal](outcomes/records/progress_journal_v22.jsonl)、[修复/重入](outcomes/records/repair_reentry_v22.json)。

本批已清场，停止等待ChatGPT review；不merge master或其他分支。
