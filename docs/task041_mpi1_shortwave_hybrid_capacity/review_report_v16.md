# Task041 Review V16：批准tiny有界收敛验证，统一MemAvailable后连续推进M400

## 0. 明确裁决

**选择先完成一次同方法的有界验证：同一个test347真实FE、原A/RHS、固定B/S_B、RIGHT FGMRES、restart30、rtol=5e-9、atol=0不变，仅将本次tiny的max_it从240提高到600。不要先开展新的PC研究或大型谱分析。** 同时离线整理已有restart窗口，补少量独立原残差记录；生产MemAvailable口径统一可独立推进，不互相等待。

若R30/600正常用尽且原残差仍不合格、但没有PC/算子/取证错误，才允许一次同tiny、零初猜、同PC/容差的R60/600对照；只改restart，不同时改正交化或精化。R30通过则该备选不运行。通过必要serial/MPI2与生命周期验证、生产资源链统一后，主控可连续启动V14仍剩的1次M400大型构造，无需另一次相同范围审批；不重置额度，不现在直接启动M400。

```text
repository             = Rookie1234567/MyFEniCS
branch                 = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date            = 2026-10-14 Asia/Singapore
reviewed_HEAD          = b1e8e7f95786033b064e45a7d982d5befee66cdd
latest_commit          = Record V15 tiny FE 240-step nonconvergence
previous_review        = review_report_v15.md
reviewed_response      = response_v17.md
response_required      = response_v18.md
solver_policy_keep     = task041_v13_consistent_fixed_balh_modal_surrogate
row_contract_keep      = task041.v15.original_modal_row.terms_backward.v1
tiny_primary           = R30 / max_it600 / original rtol5e-9 / atol0
conditional_tiny_only  = R60 / max_it600 / otherwise unchanged
M400_large_slots_left  = 1 (inherited, not reset)
memory_policy          = system_default_unbound
swap_policy            = observe_only
W5_weak_channel        = DEFERRED_BY_USER
merge_approval         = NO
```

本轮消除两个明确blocker：受测真实FE尚未完成原方程验收；测试与生产的宿主可用内存定义不同。V15已回应，故新增V16并保留旧review。覆盖tiny旧240步停止授权及本报告§5限定的MemFree/node1硬门解释；不改数学PC、最终精度、普通默认或其他任务资源政策。最终仍是0.7 nm目标50×25 nm周期单胞、约2 TB整机RAM及余量、48 h从QEP到清理的完整计算；Hybrid不代表任意非可分三维Full3D已通过。

## 1. 审阅事实与边界

本次实际读取分支ref、Response V17、machine record、summary、当前test347求解/记录代码和近期提交；核对AGENTS、docs/AGENTS、repository_work_principles、task及V15。task和既有规则blob保持原版本；目录未列额外任务补充书。ignored工件只有远端摘要/hash索引，本审阅未在工作站复现FE，也没有访问其实时进程。用户报告当前无运行；执行前仍须现场核查。

| 对象 | 实测或源码事实 | 裁决 |
|---|---|---|
| 真实FE tiny | 2172×2172；FGMRES/RIGHT；restart请求及setter30、getter不支持；max_it240；零初猜；reason=-3 | 正常迭代预算未达标，不是新行门拒绝；不能称停滞、无解或PC bug |
| 原方程终检 | 分子0.29822161297582517；分母934946.4789603328；relative=3.189718552739508e-7；门5e-9 | 超门63.794371倍，旧结果仍FAIL |
| PC模态行 | 240次attempt/success/record；序号8–247；最大eta_inf=7.753508102198664e-14；同次owner记录通过 | 受测内部一致性通过，不替代全局收敛或正式五残差 |
| 报告范数 | 150/180/210/240步分别2.765550/1.202951/0.606899/0.298222 | 持续下降；不是逐步独立真实残差 |
| 费用/资源 | pytest父wall471.35805576085113 s；runner authority峰973332480 B | 小型测试计时与峰值，不是M400耗时/容量 |
| 生命周期 | completion在数值断言前保存；随后reason断言失败，销毁后冻结快照断言未执行 | 必须补测，不得写已通过 |
| 正式M400 | V15新场not_run；V14旧场失败现场缺失，根因UNCONFIRMED | tiny不能反推历史根因；剩余1次大型额度未使用 |

当前test347使用真实FE算子和解析非QEP模式，但RHS由既有已知代数向量生成：f=A*x_star。它是端到端代数求解资格，不是0.7 nm入射散射场或目标几何精度资格。测试中的lambda/材料/12模态fixture不替换成更容易的模型，也不把其迭代数外推为M400步数。[R1–R4]

## 2. 为什么先提高一次有界预算，而不是先重写PC

后四个30步周期的报告范数比值依次约0.48386、0.43498、0.50451、0.49139。若后续仍约每30步减半，当前相差63.794倍约需6个周期，即再约180步、总约420步；用120–240步的平均比值约0.47794估计则约409步。**这些只是对已记录报告范数的条件推算，不是收敛保证、真实残差历史或时间承诺。** 600是一次给足余量的有限上限，不再逐次申请300/360/420。

```math
\rho_{240}=3.189718552739508\times10^{-7},\qquad
\tau=5\times10^{-9},\qquad
30\,\frac{\log(\tau/\rho_{240})}{\log(0.5)}\simeq180.
```

max_it限制总工作量；restart限制每个周期保留的Krylov空间。保持restart30而增大max_it不会因基向量数量而线性增加Krylov峰值；新增日志/证据存储仍须有界。增大restart可能改善也可能不改善收敛，且增加存储与正交化成本；目前没有R60实测，不能先认定R30就是根因。[S1–S2]

PC模态行满足定义也不保证PC足够强。对合并侧区D、固定B，PC中y=B*r_s、S_B*a=r_m-L*y、z_s=y-B*G*a；可直接推得：

```math
r_s-(Dz_s+Ga)=(I-DB)(r_s-Ga),\qquad
Lz_s+Ca=r_m.
```

因此，模态一致性很好与侧区误差仍需很多外层步骤可以同时发生。现有证据支持测量收敛效率，不支持以修改后向误差分母、删模式或改变原A取得通过。无需先物化2172×2172的预条件算子或求全谱；已有迭代轨迹足以决定这一次有限验证。

## 3. P0：同一tiny的R30/600完整验证

### 3.1 冻结身份，只扩展预算

复用`test_task041_v13_real_fe_condensed_sides_build_same_fixed_b_ldu`及现有fixture/入口。保持原mesh/MPC/entity_closure、dtype、解析模式、原A、同一固定B、S_B、原RHS生成式、零初猜、rtol5e-9、atol0、divtol、norm、正交化、p4固定精化和原行门。将该selector预算改为600，实际restart仍30；相关metadata用真实变量生成，避免改了KSP仍输出max_it240或“未授权扩步”的旧字符串。普通solver和M400 max_it不跟随修改。

用户已说明旧进程退出；不得称复用旧live factor或从第240步原地续算。默认一次新tiny构造后从零运行到正常收敛或600步；新曲线可与旧前缀比，但不拼接为一次实测。旧60/240样本保留。不要为读取不到restart getter开发C桥；记录setter来源，已有KSP.view可用则旁证，getter unsupported不是停工理由。

### 3.2 最小必要观测

保留每步PETSc报告rnorm。每个完成的30步周期与终点记录独立原A残差；在monitor中取得近似解须使用已支持的KSP.buildSolution写入自有scratch，不能假定getSolution始终是当前GMRES组合解。不得改变KSP解/RHS/PC，也不得新增一次PC调用；独立A作用与观测时间单列。[S3]

只增加一个已有monitor边界的薄实现；接口能力先用现有合成tiny验证。若本机buildSolution不支持，不手写Krylov重构，也不为此重跑数小时：保留报告曲线和必须的退出后独立Ax-f，明确缺少中间true样本；不得用报告范数触发“已证实真实停滞”的新结论。中间真残差不是新全局收敛容差。

终态至少输出：正负reason、actual iterations、原分子/分母/relative、RHS未改、PC attempted/success/delta与逐行最大eta、同次owner/p4门、setup/S_B/solve/观测/cleanup分段wall。tiny已有x_star可额外计算相对向量误差与各块绝对残差作diagnostic；不另设未经条件数依据的新前向误差硬门，不用x_star作初猜或偷偷替换解。

### 3.3 生命周期断言不能再被reason断言短路

先在安全返回点冻结自有数值记录及completion，再按既有所有权顺序清理KSP/context/借用对象；无论正常预算不足或收敛，都运行冻结副本销毁后可读的检查。最后综合断言数值与生命周期。不得把失败reason改成PASS；completion/cleanup失败作为独立或次生项保存。保留原异常，不能由新getter覆盖。

tiny的全解仅2172个复数，可在既有证据目录保存终态x/f及布局身份，不开发通用checkpoint框架。全量PC小向量诊断仅tiny使用；正式M400保持V15有界control/legacy-reject/terminal快照，不把600份全场复制带入生产。

### 3.4 停止与通过条件

| 情形 | 决定 |
|---|---|
| KSP真实收敛reason>0，独立原Ax-f/f<=5e-9，全部V15行/owner/p4/输入/生命周期门通过 | R30 tiny通过，提前正常结束；不为了凑600步继续算 |
| 600步正常用尽且仍高于原门，所有PC/数据门正常 | 保留预算负结果；按§4允许一次R60对照，不再单纯增加上限 |
| 报告残差与独立残差明显不一致 | 先核监测解版本、范数和原A身份；不能宣称收敛、停滞或直接加预算 |
| 原行门/A4/owner错误、NaN/Inf、输入污染、ABI或真实资源错误 | 现场保存并按既有安全链停止；不启动R60掩盖错误 |

本tiny不新增复杂的提前停滞状态机，不因到240步、某一个周期下降较慢或单个block暂时波动就退出。600是明确的总迭代上限；不附加任意短wall timeout，不改默认收敛测试为“达到上限即正reason”。本轮允许次数是一个主tiny加一个条件对照，不是无限扩步或参数扫描。

## 4. 条件R60对照、MPI资格与M400衔接

仅当R30/600正常预算用尽且没有实现/原行检查错误时，在同一次tiny对象生命周期内（可行则）顺序运行R60/600；仍从零、同A/f/B/S_B、同rtol/atol/正交化开始。比较一项变量，不能用R30终态作R60初猜再宣称R60更快。保留两次独立KSP计数/时间与各自原残差；不复用已经被KSP.destroy销毁的Python PC context。优先在原KSP安全返回后reset解并调restart/上限，核对实际context/factor身份，无需重分解。对象所有权不支持安全复用时允许一次tiny重建，不能影响历史结果。

R60通过只支持“该fixture更大搜索空间有效”，不证明波长鲁棒性。两者都失败则保存终解和窗口数据，主线停在可定位的外层效率问题；不启M400、不跑R90/R120或数千步。若R30通过，R60标not_run—不阻塞正式交付。

在通过的tiny设置上完成一次registered真实FE MPI2完整求解及销毁后断言（已有最终相关source的同等证据可复用），使用同一原方程门。此前MPI2合成builder/writer通过不冒充这项；MPI2分区可能改变迭代数，不要求逐步等于serial或和serial恰好同一维数。该test生成的代数x_star依赖编号，不做未经canonical映射的跨MPI逐元素等价声明。最多同样600步；未通过就报告，不能只用serial放行涉及MPI的真实M400。

串行/必要MPI2完成、V15尚需的缩放/注错/取证门在最终相关源码有证据、§5生产内存链通过后，**主控在本轮授权内直接衔接V14剩余1次大型构造**，不以“需要新的dispatch裁定”再返回用户。M400沿V13生产初始restart32及原有一次有据restart64授权；tiny的R30/R60不暗改生产32/64，不将tiny600上限复制成生产参数。M400必须持续记录原残差、固定B/p4工作量与总wall；tiny通过是正确性准入，不是性能通过。

## 5. P1：生产MemAvailable口径一次性统一

Response V17明确：只有tiny runner已采用kernel MemAvailable，正式producer/authority/consumer/supervisor链尚未统一。本节授权在当前注册W0.7/V13路径做窄范围实现，和tiny独立推进；不升级内核、PETSc或重写资源框架。

**新宿主authority：直接读取`/proc/meminfo`的MemAvailable，按内核kB转换为bytes。** 这是内核估计的不需要交换即可供新应用使用的内存，已经考虑可回收cache和watermark，不是MemFree，也不是再把Cached相加。[S4]

限定前提：system_default_unbound，worker及所有rank的有效内存节点覆盖该工作站全部正常RAM节点（现为0/1），没有隐藏单节点membind/cpuset限制。若有效节点受限，host MemAvailable不能证明受限范围可支付，应明确拒绝该policy而不是猜测节点MemAvailable。

| 项目 | 本轮精确定义 |
|---|---|
| 作业cap/warning/W | 80/72/8 GiB不变；hard=85,899,345,920 B；W=8,589,934,592 B |
| 宿主reserve | 384 GiB=412,316,860,416 B不变，现对host MemAvailable执行 |
| 启动前 | MemAvailable>=reserve+cap；父cgroup独立headroom满足原预留要求；cap不因可用RAM多而提高 |
| 阶段准入 | 当前驻留J=max(tree RSS, dedicated cgroup current)；J+Delta+W<=cap；MemAvailable>=reserve+Delta+W；各有限祖先cgroup headroom>=Delta+W |
| 运行中 | 按现有watchdog监测hard、host reserve、真实分配/OOM/硬件/磁盘；大分配前再查阶段准入；不把已经驻留的J再次从当前MemAvailable扣掉 |
| 节点观测 | node0/node1 MemFree、合计MemFree、页分布仍记录。旧合计MemFree>=reserve与node1 MemFree>=80 GiB不再是本新policy硬门；不杜撰node1 MemAvailable或把节点空闲与host可用相加 |
| swap | observe-only不变；不把swap纳入cap或物理余量，不执行swapoff、清cache或扩swap |

此处**明确覆盖**V14/V15的aggregate MemFree及node1可用性硬门，而不是偷偷让checker容错；旧attempt的字段和判定不重算。新增一个资源policy版本/authority字段标识就够，不新增solver selector。被复用且已退出的QEP producer保留原运行资源身份；当前warm新准入不能倒改其manifest，也不因资源policy改变而重求QEP。

沿现有公共入口逐点统一resolver/配置→service/supervisor→workflow→stage callback/outer guard→consumer终检/finalizer。复用同一读取/判定helper，保留原字段为observation或legacy，不让下游继续暗用MemFree取min而再次拒绝。审批CPU map与ABI、fresh时间/source/Invocation关联不删除。

最少定向负例：MemFree低但MemAvailable足且job/cgroup有余量时通过；MemAvailable不足、祖先headroom不足、J+Delta+W超cap、有效节点受限、字段缺失/单位错误各拒绝。同一sealed样本从入口到终检结论一致；保护测试不可用假的MemAvailable或未验证的PASS绕过。只测相关资源与实际路由，不重跑800列验证资源schema。

## 6. M400真正要回答的问题与执行边界

现在不再讨论换十种PC。保留W0.7 reduced、10×5 nm、p6/h0.70、M400、MPI8×1、接口2/22、matched L20/N29、PORD/entity_closure、一致固定B/S_B，原A4及owner门1e-10、V15分量门1e-10、最终五原残差各5e-9与原物理门。复用合格QEP与已有成熟的S_B复用路径；缺少矩阵或充分身份时只构造一次，不因开发缓存阻塞；已退出的p4因子不能恢复。

两侧factor与800列完成后连续进入原outer、最小恢复包、release_before_recovery、完整E/H/R/T/A/A_volume/衍射，不在某个PC通过时退出。旧M400失败仍UNCONFIRMED；新行门通过不追认旧场成功。将800列成本、每步B成本、原残差下降率、p4精化和非重叠wall计入48 h完整预算，不能用tiny约400步推M400 ETA。48 h是目标不是强杀线；正式有限停滞规则沿V13，不无限加max_it。

原tiny每30步近似减半是“有效但不快”的信号。即使600内通过，也不能把固定B称为通用强逆；若真实M400在行门通过后外层停滞，才针对侧区误差方向和restart效率作下一轮改进。M400成功后再按已有M/h及放大阶梯推进，不把缩减案例或本次tiny当作目标单胞、2 TB或任意3D通过。W5弱显著级继续延期，W2/node1/BIOS/GPU不抢占本轮。

## 7. 提交、停止状态与实际交付

先核canonical worktree、branch/HEAD/upstream/dirty和protected stash，所有项目Python/MPI使用现有native activation。用户报告当前无计算，仍核unit/PID避免重复启动，不新建环境或误停邻任务。普通fixture/元数据小bug最小修复及相关回归后继续；同根因两次失败先轻量复现，禁止第三次原样支付大构造。数值门失败不标成普通脚本错误。

建议提交两组：tiny预算/证据及生产内存窄修改与测试；条件满足后的M400与最终文档。文档hash变化不重做已绑定数学证据。V5现287项、636119.0079768548 s属历史研发账；仅按既有所有者追加新attempt/Invocation唯一费用，不合并60/240/新600曲线，不重复计ABI。

完成后提交response_v18.md、中心outcome/机器record，并更新summary顶部、test_summary及项目总账。必须分别回答：R30真实收敛与否、R60是否触发/作用、MPI2及销毁后断言、MemAvailable生产贯通、剩余M400额度是否消耗及实际阶段、最终原方程/物理/时间/内存缺项。长场沿现有机制更新轻量阶段，不用新的整套审计框架替代实算。

**本轮裁决为APPROVED_BOUNDED_TINY_COMPLETION_AND_MEMORY_ALIGNMENT；M400仍为CONDITIONAL_ON_REQUIRED_GATES。** ChatGPT只提交本review，不运行工作站计算、不修改solver源码；普通commit/push，同一分支，不amend、force-push、覆盖stash或merge master。

## 8. 固定证据与技术依据

- [R1 Response V17](https://github.com/Rookie1234567/MyFEniCS/blob/b1e8e7f95786033b064e45a7d982d5befee66cdd/docs/task041_mpi1_shortwave_hybrid_capacity/response_v17.md)：240步、行门、内存口径和未运行边界。
- [R2 240步machine record](https://github.com/Rookie1234567/MyFEniCS/blob/b1e8e7f95786033b064e45a7d982d5befee66cdd/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v15_tiny_fe_fgmres240_terminal_20261014.json)：原残差、窗口数值、source map和V5。
- [R3 test347](https://github.com/Rookie1234567/MyFEniCS/blob/b1e8e7f95786033b064e45a7d982d5befee66cdd/src/test/test_347_task041_balh_physical_operator.py)：原A构造RHS、max_it240/restart30、completion与生命周期断言。
- [R4 当前summary](https://github.com/Rookie1234567/MyFEniCS/blob/b1e8e7f95786033b064e45a7d982d5befee66cdd/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)及[Review V15](review_report_v15.md)：当前/历史资格与沿用合同。
- [S1 PETSc KSPGMRESSetRestart](https://petsc.org/release/manualpages/KSP/KSPGMRESSetRestart/)：restart与存储、收敛取舍；不证明本案例R60有效。
- [S2 PETSc KSPConvergedDefault](https://petsc.org/main/manualpages/KSP/KSPConvergedDefault/)：达到上限可返回负reason，不将预算用尽改成正reason。
- [S3 PETSc KSPBuildSolution](https://petsc.org/release/manualpages/KSP/KSPBuildSolution/)：构造实际当前近似解、collective与存储所有权；观测只做必要周期。
- [S4 Linux /proc meminfo](https://docs.kernel.org/filesystems/proc.html)：MemAvailable是内核对无交换新增应用可用RAM的估计，不等于MemFree。[S5 cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)用于独立核对祖先限制；host估计不替代cgroup headroom。

在线官方文档用于语义依据，实际API能力与ABI以工作站锁定版本为准，不作为升级环境指令。窗口预测与块误差式为本次推导，非文献对本案例的结论。
