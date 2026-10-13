# Task041 Review V14：修复启动链，恢复实算授权，完成既有一致BAL_H候选

## 0. 审阅决定与身份

**当前首要阻塞是执行链，不是新的数值负结果。V13主场在S_B构造入口因资源回调漏传退出；修复后的重试又因准备脚本提前创建supervisor专属目录，在public子进程启动前失败。新的一致固定BAL_H候选尚未获得M400/MPI8完整验证，不能据此更换PC、增加内层迭代或重新设计数值方法。**

本轮只关闭两个明确接线缺口及其真实调用链测试，随后连续执行现有W0.7 pilot。接受可追溯的既有A/B/C组件资格，不为获得“同一最终SHA整组一次通过”的表述重跑全部测试。重新明确运行授权，避免零点几秒的启动事故耗尽一次数学试验机会。原方程、精度、资源保护和负结果保留。

```text
repository                  = Rookie1234567/MyFEniCS
branch                      = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                 = 2026-10-14, Asia/Singapore
reviewed_HEAD               = 6aa6a7c20d1d1edf85e1248e58577debd031feaf
latest_commit               = docs(task041): close out V13 warm dispatch retry
previous_review             = review_report_v13.md
reviewed_response           = response_v15.md
response_required           = response_v16.md
batch                       = task041_v14_launch_repair_and_deliver
solver_policy_keep          = task041_v13_consistent_fixed_balh_modal_surrogate
primary                     = W0.7 / 10x5 nm / p6 h0.70 / M400 / MPI8x1
memory_policy_keep          = system_default_unbound; membind_node=null
last_qualified_rank_map     = [0,1,13,14,15,16,17,18] (must recheck availability)
W5_weak_channel             = DEFERRED_BY_USER; original comparison FAIL retained
swap_policy                 = observe_only
master_merge                = NOT_APPROVED
```

最终目标仍为0.7 nm、50×25 nm目标单胞、约2 TB整机物理内存及系统余量、48 h从QEP到核验/清理的完整计算。Hybrid只覆盖内部满足模态传播假设的结构，不替代任意非可分三维Full3D资格。本轮消除的是“已实现且通过小规模验证的候选无法进入正式计算”的blocker。

**覆盖关系：** Response V15已经回应V13，故新增V14，旧review不改。明确覆盖V13旧两场额度耗尽后的停工限制，授权下述修复及新主场；沿用最新代码/Response V15记录的用户后续default/unbound内存决定和双节点合计384 GiB reserve，不恢复V13正文中的旧node0-only门。此次不增加数值算法、不增加pilot内存上限、不放宽误差门。ChatGPT只提交review；代码、测试、重启计算由Codex执行，均不是本报告已经完成的事实。

## 1. 事实、根因与资格边界

已读最新Response V15、summary、V13 outcome、近期提交，以及当前workflow/supervisor/solver有关调用。根AGENTS、docs/AGENTS、repository_work_principles已核对；task与V13保持此前已读blob，任务目录没有独立README、AGENTS或额外补充任务书。工作站ignored原脚本、stderr和准备包未由本次远程审阅直接取得；这些部分依据已提交的具体终态、调用链和工件索引，现场仍需回读原件。[R1–R6]

| 对象 | 最新证据 | 审阅判断 |
|---|---|---|
| V12旧数值场 | 14.543 h、outer至11、末次modal eta=0.472902；完整物理解未得 | 保留嵌套PC的数值负结果；不是V13新候选的测量 |
| V13数学组件 | A/B分批合同通过；registered entity_closure、p6、2×2×2 tiny FE、12模态，serial/MPI2通过 | 支持新组合继续试验，不证明M400性能或全场 |
| V13主warm | source 94361c2e24ca1c24b0bce9c0e3d6b368e1482a69；Invocation 86a98c566c574e34969f5c8dbc58dece；1369.03024578 s | workflow未传factory已有fresh-authority callback，builder在S_B入口拒绝；无outer/最终残差/physics |
| callback修复 | 当前workflow在V13路线向LDU builder传入factor_stage_factory.v13_fresh_authority_callback；限定serial测试通过 | 源码缺口已有修复；原测试使用fake factory/AST表达式，尚不是实际回调与启动链全部通过 |
| 最新重试 | Invocation 817bc0e2a56e42feb9a8cce040c9a486；0.445147259 s；FileExistsError；launch_manifest_missing | 准备binder抢先创建SUP；supervisor独占mkdir失败，发生在manifest/public spawn之前，无worker/MPI数值运行 |
| 最新清场 | 已提交终态MainPID=0、ControlGroup为空，无活动Task041任务；短寿命start_ticks/PGID/SID未持久化 | 不虚构丢失身份；现场启动前重新核对，不把历史快照当实时状态 |
| 数值/时间结论 | 尚无V13完整800列S_B、outer、五残差、恢复和RTA | 新候选有效性、速度和48 h均未证明；也未证明其失败 |

V5账本271项、charged_seconds=608046.3500231376，是跨阶段历史累计，不是一场0.7 nm耗时，也不能当本轮净运行时间。两次V13服务分别计1369.03024578 s与0.445147259 s，已有费用不得再次追加；日志/文档修正不触发PDEDE重算。[R1–R3]

### 1.1 两个问题的直接修复

**回调漏传：** 保留已经合入的V13专用转交，不删除fresh资源检查，不让缺回调返回假PASS。实际收到的必须是当前stage factory闭包，绑定本Invocation、源码、进程组、rank map及现行资源政策；V12/ordinary不得读取V13专属属性。单纯callable检查不能代替正式阶段的真实资源采样。

**目录冲突：** 当前`task041_supervisor.py`的顺序是独占创建supervision root → 写launch manifest → `_run_phase`启动public child。`exist_ok=False`正是拒绝复用/混写目录的保护。错误在准备方与运行方的目录职责冲突，不在这个保护本身。[R4][S1]

将ignored审阅包`results/task041_v13_warm_dispatch_scaffold_failure_review_20261013T092853Z/proposed/minimal.patch`作为现场核对起点；先读原binder/guard，再将最小修正应用到新的准备实例。不能声称本次ChatGPT已检查或应用该ignored patch。

## 2. P0：一次修好准备目录与正式目录的职责

本轮固定下列关系，沿现有工具实现，不建新的调度框架：

```text
OUT  准备目录：binder创建，存runtime config、sealed argv、准备收据和服务stderr
SUP  监督目录：启动前必须不存在，只由production supervisor独占创建
RUN  数值工件目录：沿原consumer职责创建，不与OUT/SUP混用
```

OUT与SUP采用不同兄弟路径，runtime config不得放在尚待独占创建的SUP内部。检查日志重定向、`mkdir(parents=True)`、tar解包及checksum准备是否间接创建SUP。准备guard只验证OUT中的配置/argv和SUP不存在；不以建立SUP测试可写性，可在已存在的父目录做独立临时写入检查。

**禁止**改`exist_ok=False`为True、删掉旧SUP重用、删除失败raw、给旧目录补成功manifest、把旧unit重新包装为新Invocation。新启动使用唯一OUT/SUP/RUN/unit；任何同名目录（含空目录或符号链接）已存在都选择新的运行身份并保留冲突证据，不自动清理。guard的先验检查不替代supervisor的原子独占创建。

binder和dispatch guard原先位于ignored results；修改必须保存原件与diff/hash。只在现有薄准备入口中统一这两项职责，禁止本轮继续复制多份互不一致的binder。需要抽取共用路径检查时，只加一个最小helper与测试，不把数值核心移入脚本。

## 3. P1：补真实调用链测试，不重做整套数学验证

本轮测试必须覆盖出错路径，而不只是增加selector数。只补或复用以下两个集成边界；数学/collective未变时不重跑A/B/C、13.5 nm、W5或QEP。

| 集成边界 | 最小证明 | 必须拒绝的负例 |
|---|---|---|
| 准备→supervisor→manifest→spawn | 在临时目录运行真实准备路径与真实supervisor入口，证明准备后SUP不存在、supervisor创建SUP并写manifest后才spawn。利用已有测试依赖注入，把数值child换成仅写标记并退出的小进程；保留真实目录和参数解析。该测试不算PDE | 预建SUP、OUT/SUP相同、runtime config位于SUP下；均在数值child前拒绝且不改旧目录 |
| workflow→LDU→fresh callback | 通过实际candidate helper/函数调用验证同一个callback被传到builder；用现有资源snapshot fixture在I/O边界提供输入，执行实际回调判定的pass/refuse分支，验证V12/None隔离。不只AST提取调用字符串 | callback缺失、错Invocation/source、真实资源不足，不生成假通过；正式运行仍实时采样 |

优先扩展已有test351/352及现成fixture。不要为了启动链测试再运行完整FE；不要用stub整个supervisor或整个factory的方式把两个已知错误一起绕掉。测试替代数值child仅限测试环境，正式入口和验收不新增可绕过参数。

如果尚无可复用的轻量spawn fixture，允许在现有测试文件中增加最小临时child；不建立另一套生产runner、ledger或通用canary系统。明确记录“测试覆盖启动边界，不证明数值收敛”。现有MPI8 ABI按相同native库、桥、线程和请求CPU map可复用其相应资格；Python源码的新数学正确性不能由ABI证明，纯文档变化也不要求重测ABI。

**收口条件：** 两处回归及受影响Ruff/compile检查通过，runtime source已冻结，真实config/argv经过现有resolve/validate-only，随后进入P2。`validate-only`不是spawn测试，也不是最终结果；不再为了整理旧分批测试为一次整组PASS而延期。主控在当前授权内内部审核通过即可继续，不把每个小步骤重新交给用户申请。

## 4. P2：正式运行授权与防止再度“额度用完停工”

本review明确批准：P0/P1完成、fresh资源/环境/目录检查通过后，启动一场新的W0.7 V13数学候选warm。它是新增授权，不倒改已用掉的两次V13 Invocation。

**重试分层：**

- public worker尚未启动，或未发生任何大型数值装配/分解的脚手架失败，按工程attempt完整记账；不消耗本轮数学候选验证次数。明确路径、变量、CLI、fixture或schema错误可最小修复后自行继续，不需要用户再次授予相同范围。相同根因出现两次，必须先在轻量fixture复现并通过反例修复，不能第三次原样dispatch。
- 已发生大型构造的尝试，本批最多两次：一场主构造，及确认实现缺陷、针对性测试通过后的至多一场必要重建。两次额度是防止昂贵盲重跑，不是鼓励提前结束健康作业。能从已存合格packet/解恢复时不得重建。
- 真正的矩阵作用错误、非有限、原数值门失败、S_B不可可靠求解或原外层停滞，保留负结果，不按“脚手架bug”自动重复。新的数学候选或超预算需另作技术裁决；本轮不偷偷换算法。

在同一原生activation shell中使用仓库入口：`python scripts/run_case.py <one-case.dat>`；沿现有service/supervisor启动MPI，禁止嵌套两次mpiexec。reuse packet经原validator/hydration进入consumer，不因路径或PC修改重求有效QEP。启动前回读当前branch/upstream/dirty、保护stash、目标unit及其他heavy，绝不覆盖工作树、热改运行源码或误停邻项目。

若主机资源暂不可用，提交具体空闲量/不足项及已完成代码，沿现有协作方式等待合法窗口；不能擅自停止邻任务或承诺无工具的后台监控。已有健康授权作业继续，不为“换review、换计时”强杀。

## 5. 本轮保持的数学与数值合同

V13策略ID保持不变，不再新增第二个算法selector。两侧一致的固定BAL_H作用B和小型近似模态矩阵满足：

```math
S_B=C-LBG,\qquad y=Br_s,\qquad S_Ba=r_m-Ly,\qquad z_s=y-BGa.
```

```math
Lz_s+Ca=Ly+(C-LBG)a=r_m.
```

沿实际原算子的符号/方向实现并检查最后一式，不凭这项恒等式宣称原D与B已经匹配。它解决的是各PC块的代数一致性；外层是否经济收敛仍未知。RIGHT FGMRES始终作用在原A/f，不把近似S_B当作物理方程。[S2]

冻结W材料、0.7 nm、10×5 nm、z=-2..26、接口2/22、p6/h0.70、M400、matched L20/N29/h=20/29 nm、complex128、双Floquet/DtN、PORD/compact/identity-sharing与registered entity_closure路径。每Q仍一次固定数学精化、原A4 physical/augmented residual<=1e-10，零分支以实际证据处理；普通owner的5e-13/max2设置不被修改。

两侧因子可用后，连续构建800列S_B。前8个既定列保留在最终矩阵，不丢弃重算；每列使用各侧一次固定B，禁止调用旧side128步FGMRES。S_B单complex128数组10,240,000 B只是payload；保持owner新增模态预算256 MiB和全树cap。矩阵作用一致性、复线性/重复与原S_B求解门<=1e-10；完整PC的原modal row单独验证，不用小LU残差替代。禁止伪逆、shift、删模态、任意phase fit或隐式准确D逆Schur回退。

构造完成立即进入原外层，不在factor/S_B ready时主动退出。保留V13初始restart32，以及有已完成窗口的重启损失证据时、在solve返回安全边界一次改restart64/MGS的授权；继续用可信x、原f和累计计数。不能在PC回调内替换KSP，不恢复V12的side/modal嵌套状态机。实际side内层KSP solve和modal内层KSP solve计数均应为0；存在p4直接LU对象不等于违反该计数。

最终reported/global/bottom/top/modal五项各<=5e-9；traction/projection<=1e-8、external-q<=1e-10；能量闭合及A-A_volume<=1e-5；E/H、canonical、完整衍射复幅/功率及法向通量仍按原合同输出核验。无通过的原方程解，不生成official RTA。原残差有效下降时连续完成；真正持续停滞按V13两个16步窗口及必要一次Krylov调整规则保存可信解/残差后收口，不无限加max_it。

## 6. 资源与CPU：沿用后续用户决定，不恢复过期NUMA门

Response V15和当前production源码都明确使用system_default_unbound。此次review据此明确覆盖旧V13的node0-only措辞；这不是宣称node1性能故障已修复，也不是授权本轮调BIOS。[R1–R4]

| 项目 | 本轮要求 |
|---|---|
| MPI与CPU | MPI8，每rank一个数学线程；使用显式请求并核验的8个不同物理核。最新已验证map为[0,1,13,14,15,16,17,18]，fresh可用性仍需核对 |
| map改变 | 只在原任务允许的CPU集合中通过现有请求参数选择，不在源码硬编码新列表；新map重新绑定配置并验证实际rank，summary不能反向充当期望值 |
| 内存放置 | OS default/unbound，不强制membind到node0或node1；允许节点集合按cgroup继承核验；页落在哪个节点只记录，不作为分布比例Gate |
| 作业预算 | hard80 GiB=85,899,345,920 B；warning72 GiB=77,309,411,328 B；阶段缓冲W8 GiB |
| 宿主余量 | node0+node1合计reserve384 GiB=412,316,860,416 B；沿当前已注册的node1至少80 GiB可用性门，不把它解释为页必须落node1 |
| 独立保护 | host、父cgroup有限headroom、磁盘、OOM/分配失败、真实硬件异常仍检查；不能把host与节点空闲量相加重复算容量 |
| swap | 保持observe-only，不单独拒绝启动、停止或判最终失败；不靠swap扩大允许的物理驻留预算 |

阶段fresh authority仍保留。用当前驻留B、下一笔新增需求和W与冻结总cap比较，不把已经驻留的p4因子再加一次；删除对象的nbytes不等于RSS已返还。默认内存策略并不能保证性能稳定，实际CPU/内存/线程分布及performance_not_isolated边界如实记录，不为此重启硬件诊断旁线。

## 7. 实质交付、时间判定与向目标规模推进

本轮交付不是“目录已修复”或“另一个准备包”，而是至少取得当前正式candidate的：真实fresh callback记录、S_B列进度及构造/LU门、连续原外层残差轨迹；若通过则完整场与物理量。未到这些阶段时必须列出唯一具体阻塞、已运行最小复现与下一动作，不将代码提交数当数值进展。

沿现有marker记录SUP创建/manifest/public PID、worker进入、packet有效、两侧numeric、S_B的8/其余列完成数、outer第1/4/8/16/32及restart边界、恢复与finalizer。区分进程活跃、等待资源、numerical_running、数学失败、脚手架失败；长阶段沿现有日志至少每小时更新轻量状态，不另造监控系统，不以周期hash大文件拖慢计算。

```math
T_{cold}=T_{QEP}+T_{setup}+T_{S_B}+T_{outer}+T_{recovery/check/cleanup}.
```

warm、真实fresh、旧producer实测加本场warm的组合估计、研发账本四个口径分开。48 h是目标，不是正常下降的作业到点强杀线；既有S_B阶段的成本筛查仍须记录真实8列成本和假设，不把预测当实际完成时间。数学阶段的B/P4回代/精化、A6/H6、S_B LU、outer原A作用计数与非重叠wall一起汇总，不将rank-max子项重复相加成总时间。

首场成功后接续V13已授权的必要M/h验证：先同几何M400→600（需相应新packet及安全预算），再h0.70→0.525，matched N由真实生成器确定；每场独立dat，不能为了相邻profile扩展阻塞首场。RTA/体吸收相邻差1e-4、显著级幅度/功率1e-3、E 5e-3、H 1e-2沿用；未达保留best available discrete reference。

再按对象建立50×25 nm目标的容量/时间模型：p4填充、QEP/模式基、trace/DtN、S_B与LU、Krylov和恢复分别估算。S_B存储O(M²)、LU O(M³)、列构造O(M·cost(B))，不能只看pilot小矩阵或把53 GB乘一个倍率就宣布2 TB可行。若当前候选原modal row通过而side相关残差停滞，保存原A作用和误差方向证据后再设计针对性PC改进，不本轮切换十种方法。W5弱显著级继续延期；W2只保留已有证据，不绕开主线启动新heavy。

## 8. 提交与最终状态

仅原Task041分支普通commit/push，不amend、force-push、merge master或覆盖保护stash。建议三组提交：启动准备/集成测试薄修；clean数学源下真实主场及阶段证据；Response V16与总结。文档提交不改变运行数学源码资格，不要为每次文档hash变化重新打包整个artifact树。

继续既有V5账本；每个attempt/Invocation唯一计账，派生总数由原entries核算，不重放finalizer补账，不把608046秒历史总额归零。输出`response_v16.md`及中心outcome/轻量record，更新summary顶部、test_summary、development_progress、development_model_registry。source、input_original.dat、resolved_config、physical/numerical SHA、run manifest、环境/MPI、原残差与artifact hash保持可追溯。

最终必须分别回答：两个根因是否修复并有真实启动链证据；是否执行正式worker；S_B是否完成且数值通过；原outer是否收敛及完整E/H/RTA是否得到；总wall和阶段瓶颈；2 TB/48 h/目标尺寸/精度分别还缺什么。失败raw仍为原分类，可新增root_cause解释，不能将缺manifest的旧Invocation补成成功。

**裁决：V13主数学候选维持APPROVED_RESEARCH_CANDIDATE、M400_PILOT_NOT_YET_EVALUATED；本V14授权LAUNCH_REPAIR_AND_CONTINUOUS_EXECUTION。不能声称新PC已有M400负结果，也不保证修启动后一定收敛。现在必须先让它进入真正的数值验证。**

## 9. 固定来源与技术依据

- [R1 Response V15](https://github.com/Rookie1234567/MyFEniCS/blob/6aa6a7c20d1d1edf85e1248e58577debd031feaf/docs/task041_mpi1_shortwave_hybrid_capacity/response_v15.md)：两场终态、后续用户内存决定、额度与测试边界。
- [R2 V13 outcome](https://github.com/Rookie1234567/MyFEniCS/blob/6aa6a7c20d1d1edf85e1248e58577debd031feaf/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/w0p7_consistent_block_pc_v13.md)：目录职责、ignored patch入口与已有数学实现。
- [R3 summary](https://github.com/Rookie1234567/MyFEniCS/blob/6aa6a7c20d1d1edf85e1248e58577debd031feaf/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)：最新请求CPU map、费用与阶段概况。
- [R4 supervisor](https://github.com/Rookie1234567/MyFEniCS/blob/6aa6a7c20d1d1edf85e1248e58577debd031feaf/src/runners/task041_supervisor.py)：约2326行独占mkdir及随后manifest/public spawn；该实现未被本审阅修改。
- [R5 workflow](https://github.com/Rookie1234567/MyFEniCS/blob/6aa6a7c20d1d1edf85e1248e58577debd031feaf/benchmarks/task041_exact_side_workflow.py)：factory回调定义、挂载与V13调用参数转交。
- [R6 block-LDU](https://github.com/Rookie1234567/MyFEniCS/blob/6aa6a7c20d1d1edf85e1248e58577debd031feaf/src/solvers/hybrid_fem_modal_block_ldu.py)及[Review V13](review_report_v13.md)：固定B/S_B及独立原modal行验收；本轮不重写数学核心。
- [S1 Python pathlib](https://docs.python.org/3.13/library/pathlib.html#pathlib.Path.mkdir)：exist_ok=False遇已有路径应抛FileExistsError；仅支持目录语义，不代表已验证工作站脚本。
- [S2 PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：原外层保持RIGHT FGMRES；在线文档不替代本机已锁定ABI，也不作为升级库的指令。
