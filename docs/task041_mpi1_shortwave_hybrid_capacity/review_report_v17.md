# Task041 Review V17：冻结已实现变更，完成V16验证并连续交付M400

## 0. 裁决与版本

**当前远端新增的是V16实现，不是新的数值终态。维持同一固定BAL_H/S_B候选和已批准的R30/600试验，不再次增加步数、不再设计新PC。停止扩展诊断功能，优先把当前实现转化为真实tiny收敛、生产资源链通过和M400完整场。**

```text
repository              = Rookie1234567/MyFEniCS
branch                  = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date             = 2026-10-15 Asia/Singapore
reviewed_HEAD           = 8b5948ce15a35bdb92baf595ab9c028893c08d01
latest_commit_time      = 2026-10-15 09:21:49 UTC+8
latest_commit           = Implement Task041 V16 MemAvailable phase admission and tiny FE lifecycle diagnostics
latest_results_response = response_v17.md (V15的240步终态，不是V16执行回应)
previous_review         = review_report_v16.md
response_required       = response_v18.md (统一回应V16及本补充，不另开一轮回应)
solver_policy_keep      = task041_v13_consistent_fixed_balh_modal_surrogate
row_contract_keep       = task041.v15.original_modal_row.terms_backward.v1
resource_policy         = task041_v16_memavailable_phase_v1
M400_large_slots_left   = 1，按已有实际消耗核对，不因新增review重置
merge_approval          = NO
```

本报告是**V16的执行收束补充**。不撤销、重置其数学与运行授权；已完成或正在健康执行的同身份工作继续，不为同步本文件重新求解。V16及本报告条件满足后，主控在当前授权内直接衔接M400，不再向用户重复申请同一范围。

本轮消除的blocker是“前置功能已实现但缺实测闭环，以及诊断/配置继续扩大而挤占数值验证”。最终目标仍为0.7 nm、目标50×25 nm单胞、约2 TB物理RAM及余量、48 h完整计算。Hybrid仅覆盖适用模态内部区域的结构，不等于任意非可分三维Full3D资格。

## 1. 仓库事实：代码已经前进，结果尚未刷新

已读取当前ref、commit/diff与文件统计、任务目录、最新review/response、相关规则和关键源码。task及既有治理文档blob未变，沿用已读合同；目录未列额外补充任务书。最新任务outcomes树仍为`8a7143e9f3848eff75b60b48c17c12fefde980d3`，与V16审阅前相同；没有response_v18或新600步/M400结果。**这不能证明工作站没有在运行，只能证明新结果未在远端发布。** 本次没有访问其实时进程，也未执行工作站测试。[R1–R4]

| 对象 | 可核对事实 | 审阅结论 |
|---|---|---|
| 最近数值结果 | 2172×2172真实FE；R30/240；原相对残差3.189718552739508e-7，高于5e-9；PC行门240/240通过，最大eta约7.75e-14 | 预算内未收敛；并非新PC行拒绝，不足以定性停滞或bug |
| 新tiny源码 | test347设置max_it600、restart30、RIGHT FGMRES、rtol5e-9、atol0、零初猜；含中间真残差及生命周期记录 | 预算与观测已写入；不能再列为“尚待开发”，也不能称已跑通过 |
| 新资源源码 | 版本化kernel MemAvailable读取、初始/阶段准入、rank有效内存范围及service/workflow/outer路由 | 生产路径已有实现；运行贯通资格仍须由实际测试/参数证明 |
| 变更规模 | 相对d673756共12文件，新增6368行、删除468行；三个测试文件新增4352行 | 说明本轮投入主要在前置代码。行数不是缺陷证明，不要求为了变短重写；现在应冻结范围并执行 |
| M400 | 最近完整记录仍是800列S_B与owner LU完成后，旧PC行门拒绝；根因UNCONFIRMED | 不把tiny反推成旧场根因，不重复旧失败分类，不宣称新M400已启动 |

V16的条件推算仍只是假设：最后几个30步窗口的报告范数约减半，240步距门约63.79倍，因而600值得试；它不是已测600结果，更不是M400时间预测。该真实FE fixture用解析模式及代数制造RHS，不是0.7 nm真实入射散射场。[R2–R3]

## 2. 当前代码的针对性收口，不再扩大诊断工程

### 2.1 新资源规则必须显式选中，代码存在不等于运行启用

`task041_resource_policy_binding`对None/旧V8仍走旧路径；新规则只在显式请求`task041_v16_memavailable_phase_v1`且匹配注册W0.7/V13候选时使用。**这是已确认的选择机制，不是已确认本机参数选错；当前ignored准备包实参未由本次审阅取得。**[R1、R5]

下一次正式启动前，沿原public/service入口明确使用：

```text
--task041-resource-policy task041_v16_memavailable_phase_v1
```

核对resolved binding、实际argv、launch manifest、worker、stage/outer receipt与finalizer记录同一版本。不能只改Python常量，继续拿旧sealed argv期待自动启用；不把旧QEP producer资源身份改成新版本。只做已有prepare/validate和相关轻量路由测试，不重跑800列测试参数。

本规则保持：

```math
J=\max(\mathrm{treeRSS},\mathrm{jobCgroupCurrent}),\qquad
J+\Delta+W\le\mathrm{cap},
```

```math
\mathrm{MemAvailable}\ge\mathrm{reserve}+\Delta+W,
\qquad H_{\mathrm{each\ finite\ ancestor}}\ge\Delta+W.
```

启动门仍是MemAvailable至少reserve+cap；cap/warning/W=80/72/8 GiB，reserve=384 GiB。只对default/unbound且有效节点覆盖全部正常RAM节点适用；host内存不能替代cgroup限制。旧MemFree与node1 MemFree门只观测，swap继续observe-only；不放松OOM、非有限值、磁盘及硬件保护。[S2–S3]

### 2.2 辅助观测不能发展成新的求解前提

当前test347已增加较长的buildSolution、scratch、计数与冻结现场检查。先使用已有合成fixture检验该接口的实际能力；有通过证据就复用。不得再加新的采样框架、monitor状态机或通用checkpoint库。[R3]

**补充两条范围明确的防误判规则：**

- 中间buildSolution观测是有条件的诊断；若启动前小fixture证明本机不支持且不会污染对象，统一在该测试attempt开始前关闭该中间观测并记录原因，保留报告曲线、退出后独立原Ax-f及全部PC/owner/p4门。不得在一个可能破坏MPI collective或修改输入的异常之后“吞错继续”。接口有能力时正常使用，不以此无故省掉已可用观测。[S1]
- 当前代码要求每rank的`scratch_written=true`。若某rank局部向量长度为零，空数组前后相同不能证明buildSolution没工作；这一静态边界只影响诊断断言，不是已观察到的当前失败。遇到该情况按所有权检查修正，不强迫空rank制造数据，也不扩展成新研究。真实输入污染、非有限值或原A作用异常仍必须拒绝。

不要为改名、getter unavailable、旧文档字段或序号展示重跑数学验证。安全返回后的completion与自有副本要在销毁前冻结，销毁后读取冻结副本的断言无论数值成功与否都执行；不能重新引入borrowed对象销毁后getter。所有观测工作单独计时，不暗计成PC加速或额外迭代。

## 3. 执行顺序：通过一项立即继续下一项

先只读核对工作站当前source、dirty/stash、unit/PID、runroot和已经产生的completion。若已有R30/600、MPI2或生产资源测试结果，优先上传并独立核验，不因Git中暂缺就从头重跑。若已有健康授权作业继续它，不热改、不重计时。

| 顺序 | 本轮动作 | 转移规则 |
|---|---|---|
| P0 | 当前代码的必要定向回归；补已有结果到轻量record | 只测受影响资源/调用链/生命周期，数学不变不重复全A/B/C、13.5 nm、W5或QEP |
| P1 | 同一真实FE R30/600、原A/f/B/S_B及容差不变 | 正reason且独立Ax-f/f≤5e-9、行/owner/p4/输入/生命周期门通过即结束；不凑600 |
| P1b（条件） | 仅R30/600正常预算用尽时，按V16做一次R60/600同PC同零初猜对照 | R30通过则不运行；两者失败不再扩步或扫描PC。PC/数据错误不能用R60掩盖 |
| P2 | 通过设置的registered真实FE MPI2完整求解与生命周期；新资源策略全链定向测试 | 最终相关源码已有同等证据则复用；合成writer测试不冒充真实FE收敛 |
| P3 | 上述门满足，直接使用剩余1次M400大型构造授权 | 主控内部审核后继续，不以“等待新的dispatch授权”回到用户；默认不暂停在准备包 |

R30/R60可以安全共用仍存活的tiny因子；它们是独立零初猜求解，不拼接曲线、不拿R30终解当R60初猜。正确处理KSP/PC所有权。tiny参数不暗改正式M400的restart32及原有一次有据restart64规则。正式数值策略仍是一致固定B/S_B，禁止旧side128/modal32嵌套回退。

本补充不因为没有新数值就推翻V16或设计更强PC。当前唯一正确性准入缺口是完整tiny/MPI2的原系统验收，不能仅凭PC门通过跳过；也不能把tiny要几百步直接称为M400必需几百步。[R2–R3、S4]

## 4. M400必须形成连续实算，而不是再交一个ready快照

保持W0.7、10×5 nm、p6/h0.70、M400、MPI8×1、接口2/22、matched L20/N29、PORD/entity_closure、V15行合同及准确p4固定作用。只通过正式`python scripts/run_case.py <one-case.dat>`链，MPI由现有入口负责，不嵌套mpiexec。CPU map由当前可用的允许物理核显式请求并核验，default/unbound不变，不恢复节点页分布硬门。

复用合格QEP。已有合法S_B数组/成熟复用入口可在物理、离散、mode keys、布局与固定B身份充分一致且独立action门通过后复用；没有则构造一次，不先开发缓存框架。已退出的p4因子不能恢复。前8列纳入最终800列，不弃算；ready后连续进入原外层、最小恢复包、release_before_recovery、完整E/H/R/T/A/A_volume/衍射/清理。

**原五项真实残差各≤5e-9，原A4/owner及V15逐分量门≤1e-10；其他traction、projection、能量与恢复合同不变。** 行门成功不是最终场成功，失败现场仍须完整保存。W5弱显著级继续延期，不为它启动polish；W2、node1维修、BIOS、GPU及额外kernel扫描不占本轮主线。

在同一场内报告完整原残差第1/4/8/16/32及重启边界、实际B/P4工作、累计时间和内存。不要仅报KSP对象数量或“进程还在”。没有重启窗口或独立真残差证据，不声称停滞；有限停止沿V13/V16已批准规则，不新增过短timeout，不用本报告重置最大步数。

## 5. 实质接近2 TB/48 h：用真实成本而不是再增大tiny预算

现有M400校准是：800列S_B构造11355.683 s（约3.154 h），失败warm服务12811.424 s（约3.559 h），服务tree峰46.62 GB；旧QEP mode-prep1460.470 s是另一次测量。它们均不是完整成功cold时间，也不能用tiny471秒推目标规模。[R4]

```math
T_{cold}=T_{QEP}+T_{setup}+T_{S_B}
+T_{outer}+T_{recovery/check/cleanup}.
```

M400的有效迭代数与每步成本尚未取得，故现在没有依据承诺48 h。下一场应优先给出两个量：原残差每降低一个数量级所需的实际wall；全部固定B/p4回代及精化总量。不要把计时中相互嵌套的rank-max子项累加成全流程wall。48 h是目标，不是健康下降作业的自动强杀线。

首场通过后按既有授权做同几何M400→600及h0.70→0.525的必要资格；每场独立dat和对应packet，按实际准入串行。先取得场，不为新增相邻profile延误M400。相邻差未达标时称best available discrete reference，不冒充网格收敛。

随后才选择一个安全的几何放大点。目标50×25 nm的预算分别列p4矩阵/factor填充及工作区、QEP与mode基、trace/DtN、S_B与LU、Krylov及恢复重叠，标measured/derived/predicted/unknown。S_B存储随M平方、LU约随M立方、列构造随M与B作用成本增长；小矩阵payload不是整场RSS。约2 TB是整机物理容量而非作业可占满的RSS，实际MemTotal、单位与reserve必须明确。

若M400行/owner门通过后原外层仍低效，先区分固定B侧区误差和重启损失，再选一个针对性改进；本轮没有新M400曲线，不批准凭猜测换PC。Hybrid放大成功也不等于任意非可分三维Full3D通过。

## 6. 避免再因普通bug结束整轮

纯路径/CLI/资源字段/fixture问题：保留失败，最小修复、受影响测试通过后在本授权内继续；同根因两次先在轻量fixture解决，不第三次原样重建。大构造前的脚手架失败不消耗数学试验额度；大型额度沿V14剩余1次，不重置。大型数值阶段真正的原方程/PC错误、非有限或容量不足不伪装成普通bug。

原结果或有效QEP不因文档、finalizer或后处理路径错误重算。已经有可信解/恢复包时优先恢复与重验；真实数值失败不能补成PASS。启动目录OUT/SUP职责及manifest-before-spawn沿已有修复，不另写一套调度器。不得误停其他项目或覆盖stash。

当前新增代码规模已经很大，本轮不再增加新的审计层、资源policy版本或求解器selector；也不为了压缩行数重写已可用代码。先执行，确有缺陷才薄修。已有定向测试证据按其source和scope复用，不要求所有历史case在同一最终SHA一次全绿才能前进。

## 7. 交付与提交

仍以`response_v18.md`统一回应V16和本补充。先补当前运行状态与已有未推completion，再连续执行；不把“代码已提交”当作“计算已完成”。进度首屏只需明确：正在/已完成哪项，最近原残差及步数，当前wall/RSS，下一个实际动作，若阻塞其具体原因和证据路径。长阶段沿现有机制至少每小时更新轻量状态，不新增监控项目。

最终必须分别给R30结果、R60是否触发、真实MPI2、销毁后证据、生产MemAvailable同版本贯通、M400实际阶段及全场/资源/时间结论。保留V5既有历史并唯一计账；runtime source与后续文档SHA分开。普通commit/push，只在原分支，不amend/force-push、删除负结果、覆盖stash或merge master。

**裁决：CODE_IMPLEMENTED_RUNTIME_EVIDENCE_PENDING；CONTINUE_V16_TO_RESULTS。** 本报告没有宣布600通过或M400可行，也未发现可以据现有公开结果确定的新正式失败根因。现在的重点是把已经批准且已实现的路线运行到底；必要门满足即可衔接，不再开启另一个准备循环。

## 8. 来源与审阅范围

- [R1 当前提交及diff](https://github.com/Rookie1234567/MyFEniCS/commit/8b5948ce15a35bdb92baf595ab9c028893c08d01)：实现与统计；源码存在不证明本机测试执行。
- [R2 最新已发布Response V17](https://github.com/Rookie1234567/MyFEniCS/blob/8b5948ce15a35bdb92baf595ab9c028893c08d01/docs/task041_mpi1_shortwave_hybrid_capacity/response_v17.md)及[summary](outcomes/summary.md)：240步结果；outcomes树尚未更新。
- [R3 当前test347](https://github.com/Rookie1234567/MyFEniCS/blob/8b5948ce15a35bdb92baf595ab9c028893c08d01/src/test/test_347_task041_balh_physical_operator.py)：600/30、buildSolution、同factor绑定与取证逻辑。重点读了求解/monitor段，不宣称逐行复现全部测试。
- [R4 M400历史结果](outcomes/records/task041_v14_modal_row_terminal_20261014.json)、[Review V16](review_report_v16.md)及[Review V15](review_report_v15.md)：沿用数值、预算、分层停止与历史根因边界。
- [R5 当前资源定义](https://github.com/Rookie1234567/MyFEniCS/blob/8b5948ce15a35bdb92baf595ab9c028893c08d01/src/io/input_validation.py)及[workflow](https://github.com/Rookie1234567/MyFEniCS/blob/8b5948ce15a35bdb92baf595ab9c028893c08d01/benchmarks/task041_balh_workflow.py)：显式版本选择与阶段预算。
- [S1 PETSc KSPBuildSolution](https://petsc.org/release/manualpages/KSP/KSPBuildSolution/)与[KSPGMRESSetRestart](https://petsc.org/main/manualpages/KSP/KSPGMRESSetRestart/)：collective、向量所有权及restart成本；以实际锁定ABI为准，不升级环境。
- [S2 Linux proc](https://docs.kernel.org/filesystems/proc.html)、[S3 cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)：kernel MemAvailable与独立cgroup边界。
- [S4 PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：预条件一致性/可用性不替代原系统收敛。

本次ChatGPT只审阅并提交报告，不修改求解器、不运行工作站测试。Markdown静态检查与远端内容核对单列；无法取得GitHub视觉渲染时如实记录，不将其包装为已完成视觉验收。
