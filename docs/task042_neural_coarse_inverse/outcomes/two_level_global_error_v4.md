# V4：有界全局误差空间与两层修正，未突破严格收敛

| 结论 / 身份 | 实际结果 | 证据 |
|---|---|---|
| 本批终态 | `BOUNDED_TWOLEVEL_NEGATIVE`；P0、P1、两条P2和两条P3已完成；六个非零诊断均256步未达原1e-10 | [独立Gate](records/gate_decisions_v4.json)、[逐RHS](records/two_level_comparison_v4.csv) |
| 空间 | OLDPOD与ERROR的snapshot / Schur有效rank均128；全部两层恒等式与真实S配对合格 | [编码/谱/恒等式](records/coarse_space_algebra_v4.json) |
| 研究分流 | physical与mixed的原A4和固定Schur/RHS均未达到预登记0.1；没有候选被选中 | 0.1只用于研究分流，正式精度仍1e-10 |
| 未使用终测 | seed420620：zero＋5非零独立家族×3变体=16；未生成、未读取、未求解，保持unconsumed | [fresh not_run](records/fresh_qualification_v4.json) |
| 原方程 / 无全局因子 | 同原13.5nm Si、1°/phi0/s、p6/h10对应p4、252cells、quad15、双Floquet、完整80通道；无候选global p4 LU/私有audit CSR/fallback | [预登记](records/two_level_design_v4.json)、[逐run构建与释放](records/run_index_v4.json) |
| 正式物理结果 | F5/p6外层、R/T/A、A_volume、场和正式衍射通道均not_run | 原A4严格粗返回未资格化；本批无F5授权 |

## 方法与这次对照究竟检验什么

局部PC把模型分成许多相邻小区域，分别修正后拼回，内存较低，但可能留下跨越整个模型的误差。本批固定V3的局部步骤B，另外保存最多128个全局解方向：先处理这些方向能表示的残差，再做局部修正，最后去掉局部步骤重新引入的同类残差。这样可以检验问题是否能由一小组可跨RHS复用的全局方向改善，代价是两份长基数组、一个小三角求解和每次PC额外一次原S作用。

```math
SZ=UR,\quad U^HU=I,\quad C=Z\,\mathrm{solve}(R,U^H\cdot),\qquad
B_2=C+(I-CS)B(I-SC).
```

S是完整trace＋port的原Schur算子；Z保存解方向，U保存SZ的正交像，R连接两者。使用SC=UUH，每次B2实测2次C、1次B、1次S，不生成全局dense S/C/B2、法方程、逆矩阵或p4全局因子。旧native编码U/R不能用于这个目标；OLDPOD只读取旧Q并重新做同一Schur编码。当前旧R-LIN在固定Q/native范数下已是精确最小残差解；本批没有声称同Q MLP能胜过它，也没有训练新网络。

局部 `R-GEO-CELL80-v3` 的FE支撑、Floquet master映射、canonical限制、次数平均延拓与port处理保持原样：252个192trace＋80port的272行patch，边/面trace借FE邻接重叠，同一个端口在所有patch中参与后按次数平均；不存在缩减80通道、额外shift或patch扫描。局部实现blob与Review基线完全相同。

## P0：身份、真实接口与代数检查

| 必要检查 / 身份 | 结果 |
|---|---|
| Git | NN-Lab canonical linked worktree；同一精确分支，从4503安全FF到实际远程Review333f；base和初始任务提交均祖先；实现正式运行前clean提交 |
| ABI / 环境 | 独立activation、解释器/缓存/results/artifacts/TMP/bytecode；complex128/int64、MPI1，原生prefix仅只读复用；未重装F0 |
| 原A4/A6与非零接口 | 复用合格V2 F1原A4=P^H A6 P差3.366e-15、非零内部/端口制造解A4/A6残差1.226e-14/2.094e-14；本批未重复组装p6 |
| 新P0真实S与native配对 | independent Schur最大1.128e-16，native map最大6.048e-15；同CSR SHA，未用mock替代 |
| 新P0两层 rank4 | 最大B2SZ缺陷4.957e-14；小型非Hermitian复数tests覆盖四恒等式、lstsq配对、线性/相位/尺度、zero、不变输入、数值秩拒绝和ownership |
| Review渲染 | 实际GitHub Review333f为7张列数一致表和5个math-renderer，无原始math围栏；未修改review |

P0真实S配对与两层自检见[algebra记录](records/coarse_space_algebra_v4.json)，ABI与执行前测试见[pre-run记录](records/pre_run_checks_v4.json)。原CSR身份为 `150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560`，n=21824、NNZ=8184464，p4 FE storage=53084；physical与80mode哈希在[设计账](records/two_level_design_v4.json)。

## P1/P2：未泄漏的解误差与两个冻结空间

只选原train index12–27：按原标签序的两类各8个独立whole_problem，不用validation/heldout或诊断解。只读取同一合格32对batch中的所需记录，准确teacher来自原clean source `b72448bb2117a0221f041f1b47ac41049750a3c7`，manifest SHA `99c354ea4ce85b2dd8284b8f91dab4f2e453b4b9d426034aa47af43e89a14783`。16个teacher重新过原5项检查，最大原A4残差1.82736770949e-13。

每题从零运行固定B最多64步，实际全部64步，8/16/.../64各捕获一次，共128个非零误差。误差是同一归一化canonical reduced坐标里的准确解减当前解，不是残差；S e = r − teacher_residual关系最大operation缺陷7.47486600215e-15。保留原复相位，每列除自身2范数，再乘该家族实际8个有效快照的1/sqrt(8)。原始state/error/residual在ignored目录，compact[快照manifest](records/training_snapshot_manifest_v4.json)有标签、尺度、权重、误差关系、来源和hash。

| 空间 | 训练信息 | snapshot / SZ有效rank | R条件数 | QR重建差 | U正交差 | 最大B2SZ缺陷 |
| --- | --- | --- | --- | --- | --- | --- |
| OLDPOD | 旧256 train对，只读取Q | 128 / 128 | 334.013156158 | 6.59943666833e-16 | 5.36509756152e-16 | 3.17130130774e-14 |
| ERROR | 16原train轨迹、128解误差 | 128 / 128 | 586.120457064 | 8.49787542333e-16 | 5.46356838837e-16 | 1.11160595622e-13 |

两次秩审计仅用固定相对1e-10阈值；没有补方向、阈值扫描、正则或伪逆，也没有发生依赖方向剔除。ERROR的最小误差快照奇异值约3.738e-6、最大2.159，实际保留128并非凑配额。Z和U的正交差、SZ谱、四恒等式、独立原作用、固定checkpoint SHA、冻结UTC和容量均在[空间账](records/coarse_space_algebra_v4.json)。两基均在P3前冻结，后来未更新。

旧Q使用256训练对，新空间使用16条带准确参考的局部轨迹，训练信息和离线成本不同。旧teacher384对和旧oracle的历史成本没有按比例编造为这次16对成本。本批复用teacher，不建新的全局参考因子；准确解只用于离线误差捕获，不进入在线PC或测试初值。新的teacher、NN训练和GPU均not_run。

## P3：六次唯一诊断，平台与严格门限

下表全部是同三项已消费RHS：physical index0、port-only10、mixed11，不是fresh；每项RIGHT FGMRES32/max256、rtol1e-12/atol0、零初值，各运行一次。原A4相对残差除以原有效RHS操作尺度；固定Schur相对残差除以该RHS起始Schur范数。port operation-relative除以原方程参与项尺度，分母可能随状态改变，因此同时保留绝对port和固定起点port尺度，不能拿相对port下降单独判改善。

| 路线 / 已消费RHS | 原A4相对残差 | 固定Schur/RHS | port绝对范数 | port operation-relative | 严格返回 |
| --- | --- | --- | --- | --- | --- |
| TWOLEVEL-OLDPOD-V4 / 0 | 0.99858818727 | 0.999092817197 | 0.0333030546374 | 0.0654894807753 | False |
| TWOLEVEL-OLDPOD-V4 / 10 | 0.949242609663 | 0.971634245187 | 0.000954707150083 | 0.480383202996 | False |
| TWOLEVEL-OLDPOD-V4 / 11 | 0.905073739084 | 0.97721673465 | 0.000949297617596 | 0.235770374702 | False |
| TWOLEVEL-ERROR-V4 / 0 | 0.999863649936 | 0.99961809965 | 0.0256415022841 | 0.0849928945237 | False |
| TWOLEVEL-ERROR-V4 / 10 | 0.937175812499 | 0.957474274981 | 0.000927512266936 | 0.334601298612 | False |
| TWOLEVEL-ERROR-V4 / 11 | 0.901084822725 | 0.963534624076 | 0.000946698188098 | 0.203706802155 | False |

| RHS / index | V3固定GEO原A4 | V4 OLDPOD原A4 | V4 ERROR原A4 | 平台判断 |
| --- | --- | --- | --- | --- |
| physical / 0 | 0.891957825531 | 0.99858818727 | 0.999863649936 | 未解锁P4，未取得严格资格 |
| port-only / 10 | 0.935861877336 | 0.949242609663 | 0.937175812499 | 未解锁P4，未取得严格资格 |
| mixed / 11 | 0.932010701839 | 0.905073739084 | 0.901084822725 | 未解锁P4，未取得严格资格 |

两条路线全部strict 0/3，并且physical/mixed未达到预登记的native和固定Schur各0.1。末段全历史见[廉价每步/边界完整历史CSV](records/two_level_history_v4.csv)：非边界native/port列留空，明确没有在那里重算。完整原始历史有hash索引；总54个boundary/最终审核之外，各返回尝试还执行完整严格审核。reported与显式Schur固定分母差最大2.19714915235e-15，native映射最大3.20242841666e-15，独立cell S配对最大9.19179770666e-16；recovery、Floquet slave零存储及独立identity通过。不存在把残差映射错误修成“收敛”的证据。

固定B完全未改，因此新旧差异来自全局空间/两层组织，而不是改进局部耦合。本批的两个有限空间没有把困难全局方向变成有效的严格收敛；部分RHS数值下降也没有达到研究分流，更没有达到1e-10。空间内精确作用不等于空间外问题都容易。现有数据不能证明具体谱根因、所有粗空间无效或所有神经方法无效；下一步需要review决定如何表示剩余方向，不能据此扩展同Q MLP。

## 资源、无全局因子与全过程成本

| 内存口径 | 数字 / 身份 | 范围 |
|---|---|---|
| 几何＋cell/port全部局部因子 | 302047392 B，实际payload | maxpatch272、port80；无global p4 factor |
| 小三角R | 262144 B，实际payload | 128×128 complex128，用三角解；全部因子合计302309536 B<512MiB |
| Z＋U | 89391104 B，实际数组载荷 | 两份21824×128 FP64复数；不用全局投影矩阵 |
| 在线表示/索引/FGMRES与工作缓冲上界 | 120352256 B，derived conservative budget | 包含80个full向量包络，不重复计同一backing |
| 构建表示/库workspace峰上界 | 481062400 B，derived conservative envelope | ten tall/twelve small矩阵及向量/索引；构造前<512MiB，非RSS实测 |
| 全正式阶段同时整树RSS最大 | 1128828928 B，0.5s sampled measured | 含监督父进程及worker/所有后代；不同阶段峰取最大，不相加 |
| Task042 swap / VRAM | 0 / 未创建GPU context | CPU-only，VRAM任务分配0；没有GPU争用或驱动变更 |

| 阶段 | 真实 clean source SHA | 现场CPU / math线程 | 整树wall s | 同时整树RSS峰 B | own swap B |
| --- | --- | --- | --- | --- | --- |
| V4-P0 | `8b792d78b06903ef874fbcf14fa06d951ae9c2ff` | 0 / 1 | 102.422415896 | 927145984 | 0 |
| V4-P1 | `8b792d78b06903ef874fbcf14fa06d951ae9c2ff` | 0 / 1 | 449.207465587 | 979628032 | 0 |
| V4-P2-ERROR | `5691d79abe87d3582ede5bbaf8369c5487e7c392` | 0 / 1 | 114.887444319 | 1128828928 | 0 |
| V4-P2-OLDPOD | `5691d79abe87d3582ede5bbaf8369c5487e7c392` | 0 / 1 | 112.648601859 | 1112412160 | 0 |
| V4-P3-OLDPOD | `5691d79abe87d3582ede5bbaf8369c5487e7c392` | 0 / 1 | 377.740587706 | 1040433152 | 0 |
| V4-P3-ERROR | `5691d79abe87d3582ede5bbaf8369c5487e7c392` | 0 / 1 | 377.101768567 | 1040003072 | 0 |

正式六阶段整树wall合计1534.00828393s。每次启动前重新核实48物理核/无SMT、已有worker/监督器/loader及活动wide线程，实际六阶段均选CPU0；这个编号不是永久空闲配置。实际affinity和三OpenBLAS库均1线程，MPI1、nice10/idle I/O，自有nonblocking lock、一次一个阶段、独立缓存。

整树hard16GiB/warn12GiB、own swap0；无独立cgroup委派，0.5s subreaper整树采样、低开销health和仅自身停止已核验，不能宣称连续内核硬限额。每次MemAvailable约0.95TB，保留max(128GiB,10%系统内存)＋128GiB邻增长＋本任务16GiB；磁盘约3.45TB空闲、min50GiB/artifact20GiB门保持。未观察到持续PSI/资源停止，邻身份和CPU推进保留；邻短phase缺可比最新耗时，不能证明零干扰或定量排除影响。所有成本shared-workstation、performance inconclusive，不使用V3逐步审核成本相减来编造新实测加速。

| 本批离线工作 / 口径 | 实测秒 | 包含与限制 |
| --- | --- | --- |
| 16个已登记teacher原方程重查 | 36.5929394058 | 新teacher factor=0；不是重跑384对 |
| 16条64步轨迹KSP inclusive | 307.733704865 | 包含局部PC、捕获和boundary审核，子项不相加 |
| 误差状态捕获 child | 17.5689407755 | 128个真正x_star−x_m，已包含于轨迹 |
| P1原方程boundary审核 child | 107.808541777 | 每轨迹0/32/64，已包含于轨迹 |
| P1原始快照I/O | 0.155277478974 | ignored；独立hash |
| ERROR空间抽取/薄SVD | 2.36852256896 | unit-error与family权重、阈值固定1e-10 |
| ERROR完整Schur编码/QR | 10.655659636 | 不复用native U/R |
| ERROR两层与独立作用审核 | 6.34660128201 | 上述三子阶段属于construction inclusive |
| OLDPOD Q抽取 | 0.529399062041 | 只加载Q；旧U/R和NN weights未读 |
| OLDPOD完整Schur编码/QR | 10.681457785 | 与ERROR同公式、同128容量 |
| OLDPOD两层与独立作用审核 | 6.49931848107 | 不作为泛化通过 |
| 两个冻结basis I/O | 0.686743975966 | 属于阶段wall；不另加到总wall |
| 新NN训练 / 新teacher LU | 0 / not_run | 本批无授权，不归功于NN |

| 路线 / 三诊断合计 | solve+strict inclusive s | KSP inclusive s | B2 inclusive s | C child s | B child s | S in B2 child s | boundary child s | strict审核 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OLDPOD | 282.171711502 | 275.41768657 | 159.169600237 | 28.7258233597 | 77.9755588513 | 52.1437411787 | 58.4949260611 | 6.331597151 |
| ERROR | 281.602290634 | 274.696261182 | 158.839214066 | 28.7237168312 | 77.394004647 | 52.4037135275 | 57.5203618482 | 6.4834199301 |

solve/KSP/B2是嵌套inclusive计时，C/B/S、boundary是子项，表中列不可相加。每条P3实际768次B2、1536次C、768次B、768次PC内S；完整KSP向量构建、显式monitor S、最后恢复、严格审核、失败packet与历史I/O、各阶段setup/释放在[逐run成本](records/run_index_v4.json)。正式wall已包含这些费用。[辅助账](records/post_checks_v4.json)另列全部已监督测试/聚合/后处理与失败尝试，publication费用单列；编辑、Git、阅读和整个会话没有连续RSS计量，不冒充全过程会话峰。

## 实现、未运行项与交付边界

数值核心在src/solvers，research显式opt-in，runner只编排；普通默认/旧B0/GEO均保留。正式源码P0/P1=`8b792d78b06903ef874fbcf14fa06d951ae9c2ff`，P2/P3=`5691d79abe87d3582ede5bbaf8369c5487e7c392`；文档HEAD不是运行source。P1清场后检查未执行P4时发现manufactured RHS生成与验证同进程可能保留构造状态，作一次局部修复：新增独立RHS-only生成stage，验证拒绝solution/x_star/initial_guess字段，RNG/16问题/阈值/预算不变，affected tests通过。此修复发生在任何fresh数组生成之前，本批P4没有解锁，也没有重放已通过数值；[修复证据](records/p4_privacy_repair_v4.json)。

| 项目 | 本批状态 / 原因 |
|---|---|
| P4 generation与qualification | not_run：两条P3不符合预登记分流，既存seed420620集合仍未消费；未换种子 |
| 新teacher全局参考因子 / 新NN | not_run：参考合格可复用，本批不训练新网络；G-neural not_run |
| F5/p6、短波、正式RTA/A_volume/field/channels | not_run：本批无授权，且无严格粗逆资格 |
| 参数扩大/重试 | not_run：不加rank/迭代/patch/shift/epoch或放宽残差；正常停滞没有当作bug |
| resource / performance资格 | 资源检查在预算内，性能inconclusive；无global因子是实现证据，不替代数值资格或正式20%加速/节省Gate |
| 历史 | 原task、Review V1、response_v1–v3、全部旧raw/负结果逐字保留；summary只在前面加V4，旧正文不改 |

用户最新授权只允许Task042受控共享CPU，覆盖原§2.3 heavy禁令/全机独占锁，不取消资源、精度、provenance或停止条件，不代表F0正式review。Review V1明确允许局部停滞轨迹继续构造全局空间，替代V3旧停止前提；本批已实际做到P1/P2/P3，没有因neighbor heavy回到F0。邻任务的程序、环境、affinity、优先级、watchdog与锁均未操作。

| selective merge依赖组 | 内容 / 测试 / fresh FE证据 | 合入边界 |
|---|---|---|
| production numerical/core | 无新的production资格；原A4/A6/MPC/DtN不改 | 不提升默认，不merge |
| research core | learned_two_level＋backend可选低频observer；复数代数/ownership与真实P0/P2/P3 | 两个候选未资格化，仅research |
| reusable runner/watchdog | 原own-tree监督与单一入口复用；V4显式profile/纯stage发布与RHS-only guard | 依赖research core，无共享父组或邻锁变更 |
| checker/benchmark | 独立norm Gate、固定两空间dat和配置、focused测试 | 依赖原协议；不复制数值核 |
| compact evidence/docs | V4 data/space/Gate/source/cost、response和两总账 | 保留旧负结果，按同分支review |
| do-not-merge | ignored env/JIT、原始states/bases/teacher/cache/logs | 不进Git；推送仅任务分支，之后等待review |

执行前/最终focused、Ruff/compileall、保护历史、文档表格/链接及继承checker边界见[测试页](test_summary.md)。推送后的实际GitHub V4页面渲染另写publication evidence；这不代表CI或数学通过。
