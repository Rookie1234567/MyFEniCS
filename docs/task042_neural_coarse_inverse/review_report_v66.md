# Review V66：可靠完成已准备的L5，不再以重复准备和原因追查代替完整场

## 0. 裁决、目标和唯一执行身份

**V67为部分完成，按`pass_with_qualifications`接受M4完整离散解、有限模式增量和可恢复资产；L5为`INTERRUPTED_NO_RETURN_UNKNOWN_CAUSE`，不授空间精度、生产收益或目标资格。** 已核对的外层退出143与SIGTERM相符，但没有定位发信者或确切受信进程，不能改写成OOM、内存不足、MUMPS不收敛或用户主动停止。授权 **V68_DURABLE_L5_COMPLETION**：有限追查和修复执行链，从已资格体矩阵完成同一L5，并交付完整物理比较及费用。

本轮消除的blocker是：**已支付约3.36小时的局部p5体矩阵准备，却因分解阶段执行链中断没有场；当前缺少的是这份完整空间参照，不是更多模式、网格或训练。** 不再次生成健康矩阵，不重跑M4，不把查出历史发信者作为无期限总前置。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-10 Asia/Singapore
reviewed_HEAD          = 6216525665b49dac6dfd4e7d4eb9db50770122a5
latest_result_UTC      = 2026-10-09T14:47:02Z
latest_result_local    = 2026-10-09 22:47:02 +08:00
latest_response        = response_v67.md
previous_review        = review_report_v65.md
previous_review_commit = 067da63d90a7c659f8c7c159a9a16644e5049b48
previous_review_blob   = bf44a3a309db42425f21e6dc037ee882b7dbe0fd
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V68_DURABLE_L5_COMPLETION
required_response      = response_v68.md
ordinary_default       = UNCHANGED
NN_training_PC         = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

最终目标保持：真空0.7nm、原50×25nm周期及z=-10..130nm，单胞内任意非可分三维材料/几何，complex128 Nédélec H(curl)、双Floquet、完整Fourier-DtN、复E/H/衍射/R/T/A/独立体吸收；必要构建至输出及检查≤172800s。约2e12B是整机物理内存，必须留系统余量。本批s=7/135缩尺完整问题不等于原尺寸资格。

新合同只覆盖V67已用尽的尝试额度和已关闭窗口，授权新的同空间L5恢复求解。旧SIGTERM、费用上下界、模式PASS和空间NOT_RUN原样保留。无需改写旧report或令旧ledger重新active；不提高原L5的256GiB规划额度。

## 1. 实际审阅与最新科学结论

读取固定HEAD的根/文档规则、仓库原则、原task身份、最新response/summary、六次提交差异、checkpoint和中断记录，以及实际scope/provider与subreaper代码。上一份完整review读取挂载副本并核对远端同blob；任务目录未检出新的独立supplement或Review V66。没有SSH、工作站新PDE或大数组重演；以下measured是仓库已交付记录，不是审阅端复测。

核心证据：[Response V67](response_v67.md)、[summary](outcomes/summary.md)、[中断](outcomes/records/interruption_classification_v67.json)、[矩阵保存](outcomes/records/body_checkpoint_v67.json)、[模式归因](outcomes/records/mode_error_attribution_v67.json)、[原场比较](outcomes/records/paired_results_v67.json)、[最终费用](outcomes/records/resource_costs_final_v67.json)、[离散参照](outcomes/records/discrete_reference_contract_v67.json)。

| recorded measured | L5：局部p5/828 | M4：局部p4/1188 |
|---|---:|---:|
| 同一冻结tet数 | 25576 | 25576 |
| 独立FE / 完整系统行 | 1943745 / 1944573 | 1042964 / 1044152 |
| 体K存储项 | 439529923 | 151551034，复用父K |
| 准备/求解状态 | K及两列原作用通过；numeric中断，无完整场 | 完整场及独立输出完成 |
| 原true/native | NOT_RUN，无解 | 2.27239910138e-10，formal1e-6通过 |
| direct1e-10 | NOT_RUN | FAIL，独立单列 |
| 新PREPARE完整进程/s | 12095.1191837 | 本批未重建父体K |
| 完整prepared-start/s | 未取得 | 2118.53027283 |
| 已观测树峰/GiB | 89.2909355164，仅中断前样本 | 55.4556083679 |

M4的R/T/A_volume为0.0762184730788/0.905665213511/0.0181163134122，独立能量差1.74349423787e-12。旧L4F与M4完整散射E/H增量7.10606408e-6/7.85932583e-6，240点最大六向量差2.11931195e-5，物理复通道2.18801710e-6，逐mode功率1.09809561e-9，两固定分母的联合门均通过。新增360模式由旧场实际投影，不是填零。该PASS只属于此p4网格的828→1188有限增量，不能继承给p5或无限模式极限。

按已保存范数的三角不等式，P6/M4散射E差下界3.33317903e-4、H差下界3.42090731e-4，仍超过1e-4。这是derived界，不是新增P6/M4积分；它排除了“本次p4增加360模式足以消除原跨空间差异”，不能指定任何场是真解。

L5外层调用计费区间为[1432.07390935,2057.882138]s；内部从最后观测到首次确认消失的结算另有1970.727970s上界，二者起止口径不同，不混写成精确连续时长。最后样本以后RSS、信号来源与真实停止时刻仍unknown。PREPARE加失败调用区间[13527.1930931,14153.0013217]s全部保留，不与嵌套子计时重复相加。不能用中断前89.29GiB样本宣布完整factor能装下。

## 2. 工作取舍：完成原定的场，而不是再开旁支

这条线已从神经粗逆试验转为确定性准确性参照：固定相位改善解析平界面，局部装配降低同空间存储，标准四面体提供独立于旧hex凝聚的参照，系数收缩使原式审核可用，checkpoint避免重付装配费用。它们不是NN收益。当前M4又给出了明确的有限模式证据；未决问题收窄到L5实际空间响应和后续精度成本。

本批只计划一个新全域求解：同L5/25576tet/p5/828。先完成L4F/L5和P6/L5比较，再依据结果作下一决策。不重标记，不改theta，不追加p6/p7、1188以上模式、载波或单元家族；不重算M4/P6/L4。一次存储/监督小测试通过不是整批完成，L5的完整场、比较和费用才是主交付。

完整源链仍是标准UFL/FFCx体矩阵、原MUMPS、独立PUBLIC_BASIX系数积分；全部内部自由度留在全局系统，无静态凝聚。此次不把有限direct路线改装成生产PC，也不要求立即研发新的matrix-free求解器。

## 3. S：执行链修复要有界，历史未知不得形成死锁

### 3.1 只追查本次直接证据

先读取V67对应run目录、外层command/timeout、原launcher/worker日志、last resource sample、window/role配额与有权限读取的同时间系统/cgroup记录，核对PID/start_ticks/PGID/SID和已记录父链。历史取证目标30分钟、上限45分钟；不全盘扫描其他任务日志，不读邻任务smaps，不申请sudo/auditd/eBPF或修改系统审计。检查不到的记录写unavailable，不推断发信人。

退出143在Bash规则下与128+15相符，但不能证明是哪一层进程被终止，更不证明原因是内存。当前`preparation_interruption.py`是丢失返回后的保守结算器，不是发信者追踪器。若没有足够历史证据，应结论`HISTORICAL_SENDER_UNRESOLVED`；**只要新执行链可靠，仍准许本批主解，不再等待一个可能不可恢复的名字。** 若明确是用户/管理员停止或仍有效的权限禁令，不得绕过。

### 3.2 不重写watchdog，只补最短的可持续、可记录调用链

复用`benchmarks/subreaper_watchdog.py`和现有Task042 launcher。当前源码将收到的TERM/INT先放入内存列表，stop_event先写summary对象，再清理后代后完成最终收据；这提供了改进落盘时序的具体位置，但不证明V67由该处造成。仅对本批显式opt-in：首次收到信号、每次主动发停止信号、例外清场前，先将原因/信号/UTC/monotonic/boot/发送者本进程身份/目标PID及start_ticks/PGID/适用预算写入追加事件并flush；关键终止事件做fsync。不得每个0.5s样本都全量fsync。

接收记录只说明该控制器收到信号；无法取得原发信者时写unknown，不能将所有收到TERM都标为用户主动停止。数值进程可能在C/Fortran分解中，不能依赖它的Python handler及时执行来保证留证；记录应由仍受监督的独立控制父进程完成。STOP阈值和清场语义不变，不吞信号、不忽略TERM/INT、不延长hard-stop grace。

区分三种时限：交互工具的一次等待、科学worker/role的总时限、整个campaign截止。执行前记录实际可见的所有timeout和stop策略，发现更短的外层一次性命令timeout就修正调用方式。使用已有可持久轮询的会话/job handle监控同一个受监督任务；一次轮询结束不应在`finally`中默认杀死仍合法的数值worker。没有会话句柄时，仅可采用已支持、已验证的长调用，其命令超时覆盖剩余role预算及清场。不得用无记录的nohup/disown、关闭watchdog或删除父进程保护“保证不停”，也不新装守护服务。真实用户取消、资源/时钟/监督失败和截止仍必须清理自身后代。

只做两项合计不超过90秒的pure-process控制：一次跨短轮询继续运行直至正常结束；一次对自有fixture发送明确停止请求，验证事件先落盘且清理后代。不得用真实factor验证信号处理。相关定点回归完成后直接进入主解；接线与修复合计目标90分钟，不能将本批变成通用调度框架研究。当前链确实不能保持监督/停止能力时标`EXECUTION_PATH_UNQUALIFIED`，完成其他只读成果而不盲算。

## 4. R：精确重用L5资产，不重新支付三小时准备

唯一主资产位于`benchmarks/artifacts/task042/v67/body_K/manifest.json`，manifest SHA256：

```text
4516d89efe3d919e8e658b8fe497b606cac5c355bf5c753b6b2cb503130cd0bf
```

体K nnz439529923，已保存载荷8863726552B。原资格收据：`benchmarks/artifacts/task042/v67/task042_v67_local_p5_solve_complete_20261009T130237983420Z/body_original_action_qualification.json`，SHA256=`06315a299808ff828299522b59282591add67c7e85ef1dcf49e7f2e33e62c7a6`；两列作用记录SHA256=`b7dfbdb3480ad44e6d9607c0b609c8a9c1c8e8cb30f959ffaff28e386c902ae3`。原科学source=`53c01f124f090351747324b711599b2d8793e456`。初始ASSEMBLED_NOT_YET_ORACLE_VERIFIED标签保留，通过资格另用收据证明。

核对原manifest、COMMIT和成员校验、未舍入mesh/tag/parent、basis/MPC/dtype、p/q/kappa及body fingerprint；一次有界顺序校验后只读重载，不重复复制8.86GB矩阵来凑新证据。q47/q63只读复用同L5的健康包，不能误用M4或p4边界。因子没有完成或保存，本次必须重新做symbolic和numeric；不得宣称从中断factor进度恢复。

冻结mesh SHA256=`c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c`；25576tet、1000个NOTCH tet、native1979985、独立FE1943745、系统1944573行、Basix p5/local140/superdegree5。lambda0.7nm、grazing1°/azimuth5°/s/幅值1；kappa=(8.94046081729244,0.7821889682108057,0)。Si n=0.999885140474+4.32477054e-6i、epsilon=n*n、mu=1，canonical材料SHA256=`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。所有828物理mode键/参考面/非零载荷保持。

生产body q13、独立body q15，表面生产q47/独立q63。重建解释空间允许；重新调用production_body、旧PREPARE或构建不同K不允许。资产真实缺失/损坏则标`ASSET_BLOCKED`，保留可用部分，不猜造hash。source HEAD变化不自动使原K失效：只改scope/日志时核对数学依赖闭包后复用；数学改变必须明确宣告受影响身份，不静默使用旧K。

新scope显式指定`parent_namespace=v67, parent_role=PREPARE`及资格指针，不依赖V68当前PREPARE、不调用旧closed window的require_stage、不清空旧attempt计数。沿现有parameterized solve/prepared_provider作薄适配，不复制整套solver。旧两列完整资格在同数学和同字节下直接引用，不重跑旧24cell、旧p5/P6 PDE或全套原作用资格；加载器确实改变时，只消费一列已保存见证核对重开，没有新的随机实验队列。

## 5. L5完整求解、保存、比较连续完成

预启动身份/资源和execution-path通过后，原K和q包重载，按当前真实RSS及symbolic重新准入。保留原MUMPS排序、精度、ICNTL22=0和有界ICNTL23设置，不扫描ordering/shift/ILU/BLR/OOC，不用旧场warm-start或造RHS。首次完整解返回即原子保存x/u/port与所有身份，再完成生产true及独立原式；最多两次既有同因子精化，严格direct目标未过仍单列，不能无限精化。

完整解及最小recovery packet保存后，释放KSP/PC/因子、无用矩阵、prepared/mmap拥有者并记录RSS，再做完整E/H/curl、240点、828模式、R/T/A/A_volume和必要IO。后处理/JSON/checker失败只从保存场补消费，不再次factor。独立coef-first原式不读生产K；不取消其全cell及完整边界作用。

正式true/native/augmented/port各≤1e-6，direct1e-10单列；MPC/切向连续性/恢复及操作身份≤1e-10。全域total/scattered E/H/curl、240点完整六向量、物理参考面复通道的增量门为1e-4；逐mode功率≤1e-6，R/T/A/A_volume及每份独立能量≤1e-5。单位、背景、floor和q23/q31物理分母不变，不校幅相、不删点、不以total或守恒覆盖散射FAIL。

只做两项主比较：L4F/L5、P6/L5。共同积分域为冻结L4子tet，核对真实父映射，分别评价原场；一次差平方分子和两固定分母评分沿V66已资格路径。不得为换分母反转到不能容纳子单元不连续性的积分网格；不得投影一方。M4已完成且不改，引用模式PASS，不重算其PDE或全域比较。可从同一新积分结果汇总区域/分量，但不额外加载全部历史场评分。

不能要求L5同时贴近已相差3.5e-4的L4F和P6。L4F/L5用于同网格p增量，P6/L5用于跨空间一致性，两项分别裁决。任一粗端点FAIL不能自动取消其他消费者。若L5/P6通过而L4F/L5不通过，保留较粗p4不足的证据，不回头改旧FAIL；若相反，说明该固定网格升阶稳定但与P6仍不一致；两者都不通过，收口这一固定验证，不自动再加局部p6、全域p7或新标记。任何通过都不代表连续真解或原尺寸目标。

## 6. 资源、时限与可继续的修复边界

新12h总研发窗、科学有载≤10h、最后1h交付；L5从重载至输出和其补消费累计≤8h，全部实现/失败/修复/等待计费，UTC/monotonic/boot从首次工作冻结。旧V67时间及尝试不刷新。准备已存在，不再给body构建预留三小时；forecast必须在本次numeric前写出，依据已存symbolic FLOP、类似case实测及当前阶段，明确区间和不确定性，不把上次中断时长当完成factor估计。numeric前保留其预测上界及至少4500s完整审核/输出余量。

| 本批唯一role | planning / warning / sampled stop | 范围 |
|---|---|---|
| S、无factor消费与收尾 | 64 / 80 / 96GiB | 不能暗藏factor |
| L5恢复求解及其必要审核 | 256 / 320 / 384GiB | 同1944573行；上限2000000 |

仍以live树RSS + 2×可靠INFOG16/17(decimal MB) + 2GiB≤256GiB才numeric。V67的104405MB估计及258539093632B准入记录是历史依据，不是本次免检票；中断后段峰unknown，不以89.29GiB外推。保持原ABI complex128/int64、MPI1/math1/CPU1、GPU/Loader0、ownswap/OOC0、原PSI/cgroup/宿主及384GiB邻增长余量、合格物理核避忙SMT；一个自身heavy actor和一个global factor，不能修改邻任务、系统或共享Git配置。

一个计划numeric/完整solve；最多第二次仅限无合法返回且已定位并修好的执行故障或科学实现错误，仍同K/物理及总预算。若再次原因不明中断，不进行第三次、不用不停重启冒充连续执行；若明确用户/管理员停止或持续资源危险，不自动重放。合法场已返回时只补消费，不使用备用numeric槽。每次非scientific writer修复不消耗PDE重解，不能以“已commit/测试通过”作为停止点。

修复累计≤2h；同根因两次失败换诊断或隔离，不盲第三次重试。真正数学/ABI/映射/监督不可信必须修复或停止依赖；数值场比较FAIL不是软件bug。现场资源等待间隔≥120s、累计≤1800s且计入总窗，保护不降低。新增ignored≤32GiB、Task去重≤512GiB、free≥50GiB且证据余量512MiB；K/边界不复制入新namespace，仅保存父引用、新向量和必要输出，原子双份写入事前规划。

## 7. 让这份有限参照服务规模化，而非继续无限精度循环

本批的第一里程碑是完整L5和两项物理比较；第二里程碑是在同一记录里给出可消费的离散参照、成本与未决项。更新已有`discrete_reference_contract_v67.json`对应的新V68记录，引用健康K/原作用/物理输入/空间/MPC/mode/场，而不是复制数千行父metadata。

分四栏报告：离散方程通过；有限空间增量；有限模式增量；连续/目标资格。前三者不能合并造出第四项。已有M4的模式结论不能自动授给p5；未取得连续精度也不禁止其他路线在完全相同离散系统上验证可扩展求解器，但必须显著标注仅代数同离散资格。

成本至少列：本次prepared-start实际T_N1；父L5 PREPARE12095.1191837s；V67失败区间；本批研究/修复/比较；所有非重叠总计。缓存复用是实际减少重复工作的收益，不能把它冒称从几何开始的fresh速度比。没有新fresh控制不为凑加速比重建K。目标仍需要准确表示、局部/分层消元、凝聚trace上的分布式迭代、matrix-free原作用、streaming DtN与分块恢复；256GiB有限direct许可不等于允许把全局LU推广到2TB。

只给一个下一完整pilot建议，并说明它消除精度、全局factor、接口向量库或模式存储中的哪个blocker、哪些旧能力直接复用。不创建或启动它。若L5仍不一致，禁止默认同类升阶续扫；应依实际新差分选择一个可证伪问题。若有限一致性成立，给出当前物理准确性局限及可交接同离散基线，不再以重复小测试为本轮成果。

相邻路线已只读核对：Task42extra `5838d9c7560403164bdfee8b60d997bf4e18eeba`为V37神经新机制准入/旧族关闭，未授权新训练；工程 `1d9936104af1eeb151a5bdba500b40cf9922a226`为V20原尺寸分阶段组件与E2资源停止；dot `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、NN-V3 `1f01ae46bbe21f17200350a46513ef5f33e5cf6a`仅核对ref。本支不复制其NN、参考PC、通用CSR或目标端口任务，不向邻工作树发命令或移植不同空间的资格。

## 8. 最小测试、提交和一次交付

复用现有scope/provider/solver；只为新父资产绑定、可持续启动/停止记录、恢复状态和比较清单作最小修改。S的两个process fixture、父asset读取/数学身份、停止事件先落盘、返回场禁止重解的定点回归足够；改过的相关测试在最终source上跑一次，相关Ruff/compile/dat validate保留。不full pytest/CI、全仓索引/历史hash扫描、不重做旧FLAT、24cell、15表、慢oracle、M4或旧P6。文档结构和新文件hash一次检查，目标≤15分钟；网页不能取得就写NOT_VERIFIED，不为视觉重跑PDE。

提交计划：先提交最小执行链和V68薄适配，clean/validate后冻结运行source；有数学无关的保存修复另commit并仅补消费；最后提交结果、费用和简短导航。不能在同一活跃actor运行时修改其受检源码。旧task/review/response/raw不改。

以下为待创建入口，尚未实现不得声称可运行：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v68_l5_resume_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v68_l5_solve_complete.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v68_compare_verify_cost.dat
```

PRECHECK/VERIFY不暗藏factor/solve，scope只管理新窗口，恢复不重开V67。每dat一项明确计算，保存input_original/resolved/manifest/input与physical SHA、source、环境/MPI/资源及artifact hash。运行期间持续消费已保存状态，不因普通bug或提交动作等待下一review。

交付`response_v68.md`、`outcomes/durable_l5_completion_v68.md`和紧凑records：执行链有限取证与不确定性、新启动/stop记录、资产复用、完整场/原式/两项比较、真实graph/fill/峰/gap/费用、失败及唯一下一步。同步summary、README、development_progress、development_model_registry短入口，不复制整段历史。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

核对完整remote SHA/upstream/clean、closed/active null、后代清场和锁释放后交付暂停，不merge、不改master/邻支、不自动开下一窗口。发布报告和下载文件必须为同一blob。

## 参考与审阅端边界

[Bash退出状态](https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html)说明128+N的约定；[Python subprocess](https://docs.python.org/3.11/library/subprocess.html)区分`run(timeout)`和`Popen.wait/communicate`的超时行为。它们支持检查等待与终止语义，不证明V67实际发信来源。审阅端只核对远程文档/源码、有限算术与文件身份，没有运行新工作站PDE或复算大场数组；GitHub页面视觉无证据时保持NOT_VERIFIED。
